#!/usr/bin/env python3
"""Abaqus MCP noGUI Server -- run inside Abaqus CAE noGUI mode.

Usage:
    abaqus cae noGUI=nogui_server.py -- [--port 48152] [--host 127.0.0.1]

This script creates a TCP socket server inside the Abaqus kernel, allowing
the MCP server to communicate with Abaqus without the GUI plugin.
Useful for headless servers and CI/CD pipelines.

Protocol: newline-delimited JSON (same as agent.py).
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import socket
import sys
import traceback
from abaqus import mdb, session
from abaqusConstants import *

HOST = "127.0.0.1"
PORT = 48152

# Parse command line args
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, arg in enumerate(args):
    if arg == "--port" and i + 1 < len(args):
        PORT = int(args[i + 1])
    elif arg == "--host" and i + 1 < len(args):
        HOST = args[i + 1]

print(f"[abaqus-mcp-pro nogui] Starting server on {HOST}:{PORT}")


def handle_ping(params):
    return {
        "python": sys.version,
        "executable": sys.executable,
        "mode": "nogui",
        "models": list(mdb.models.keys()) if mdb.models else [],
        "viewports": [],
        "abaqus_version": getattr(sys, "abq_version", "unknown"),
    }


def _jsonable(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return {"repr": repr(value), "type": f"{type(value).__module__}.{type(value).__name__}"}


def handle_run_python(params):
    code = params.get("code", "")
    if not code:
        return {"ok": False, "error": "No code provided"}
    try:
        stdout = io.StringIO()
        stderr = io.StringIO()
        namespace = {"mdb": mdb, "session": session}
        try:
            parsed = ast.parse(code, mode="eval")
        except SyntaxError:
            parsed = ast.parse(code, mode="exec")
            compiled = compile(parsed, "<abaqus-mcp-pro-nogui>", "exec")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compiled, namespace, namespace)
            returned = namespace.get("result")
        else:
            compiled = compile(parsed, "<abaqus-mcp-pro-nogui>", "eval")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                returned = eval(compiled, namespace, namespace)
        return {
            "ok": True,
            "return_value": _jsonable(returned),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {"ok": False, "error": str(e), "error_type": type(e).__name__, "traceback": tb}


def _get_model_info_dict(model):
    info = {
        "parts": list(model.parts.keys()),
        "materials": list(model.materials.keys()),
        "sections": list(model.sections.keys()),
        "steps": list(model.steps.keys()),
        "loads": list(model.loads.keys()),
        "bcs": list(model.boundaryConditions.keys()),
        "interactions": list(model.interactions.keys()),
        "constraints": list(model.constraints.keys()),
        "sets": list(model.rootAssembly.sets.keys()) if model.rootAssembly.sets else [],
        "surfaces": list(model.rootAssembly.surfaces.keys()) if model.rootAssembly.surfaces else [],
    }
    return info


def handle_get_model_info(params):
    model_name = params.get("model_name", "Model-1")
    if model_name not in mdb.models:
        return {"ok": False, "error": f"Model '{model_name}' not found"}
    model = mdb.models[model_name]
    result = {"ok": True, "name": model_name}
    result.update(_get_model_info_dict(model))
    return result


def handle_list_jobs(params):
    jobs = []
    for name in mdb.jobs.keys():
        job = mdb.jobs[name]
        item = {"name": name}
        for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory"):
            try:
                value = getattr(job, attr, None)
                if value is not None:
                    item[attr] = str(value)
            except Exception:
                pass
        jobs.append(item)
    return {"ok": True, "jobs": jobs, "count": len(jobs), "workdir": os.getcwd()}


def handle_submit_job(params):
    job_name = params.get("job_name", "")
    if not job_name:
        return {"ok": False, "error": "No job_name provided"}
    if job_name not in mdb.jobs:
        return {"ok": False, "error": f"Job '{job_name}' not found"}
    try:
        mdb.jobs[job_name].submit(consistencyChecking=False)
        mdb.jobs[job_name].waitForCompletion()
        return {"ok": True, "job": job_name, "status": str(getattr(mdb.jobs[job_name], "status", "UNKNOWN"))}
    except Exception as e:
        return {"ok": False, "error": str(e), "error_type": type(e).__name__}


def handle_monitor_job_status(params):
    job_name = params.get("job_name", "")
    if not job_name:
        return {"ok": False, "error": "No job_name provided"}
    if job_name not in mdb.jobs:
        return {"ok": False, "error": f"Job '{job_name}' not found"}
    job = mdb.jobs[job_name]
    status = str(job.status)
    return {"ok": True, "job": job_name, "status": status}


def handle_capture_viewport(params):
    try:
        filename = params.get("filename", "viewport.png")
        vp_name = session.currentViewportName if hasattr(session, "currentViewportName") else "Viewport: 1"
        vp = session.viewports[vp_name]
        session.printOptions.setValues(vpDecorations=ON, reduceColors=False)
        session.printToFile(fileName=filename, format=PNG, canvasObjects=(vp,))
        return {"ok": True, "file": filename, "message": "Viewport captured"}
    except Exception as e:
        return {"ok": False, "error": str(e), "error_type": type(e).__name__}


HANDLERS = {
    "ping": handle_ping,
    "run_python": handle_run_python,
    "get_model_info": handle_get_model_info,
    "list_jobs": handle_list_jobs,
    "submit_job": handle_submit_job,
    "monitor_job_status": handle_monitor_job_status,
    "capture_viewport": handle_capture_viewport,
}


def send_message(sock, payload):
    """Send a newline-delimited JSON message."""
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(data + b"\n")


def read_message(sock, max_bytes=32 * 1024 * 1024):
    """Read a newline-delimited JSON message."""
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        newline = chunk.find(b"\n")
        if newline >= 0:
            data += chunk[:newline]
            break
        data += chunk
        if len(data) > max_bytes:
            return None
    return json.loads(data.decode("utf-8"))


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[abaqus-mcp-pro nogui] Listening on {HOST}:{PORT}")

    while True:
        try:
            conn, addr = server.accept()
            print(f"[abaqus-mcp-pro nogui] Connection from {addr}")
            while True:
                msg = read_message(conn)
                if msg is None:
                    break
                req_id = msg.get("id", "")
                method = msg.get("method", "")
                params = msg.get("params", {})
                handler = HANDLERS.get(method)
                if handler:
                    try:
                        result = handler(params)
                        send_message(conn, {"id": req_id, "ok": True, "result": result})
                    except Exception as e:
                        send_message(conn, {"id": req_id, "ok": False, "error": {"message": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()}})
                else:
                    send_message(conn, {"id": req_id, "ok": False, "error": {"message": f"Unknown method: {method}"}})
            conn.close()
        except KeyboardInterrupt:
            print("[abaqus-mcp-pro nogui] Shutting down")
            break
        except Exception as e:
            print(f"[abaqus-mcp-pro nogui] Error: {e}")
            traceback.print_exc()

    server.close()


if __name__ == "__main__":
    main()