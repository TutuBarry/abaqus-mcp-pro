#!/usr/bin/env python3
"""Abaqus MCP noGUI Server -- run inside Abaqus CAE noGUI mode.

Usage:
    abaqus cae noGUI=nogui_server.py -- [--port 48152] [--host 127.0.0.1]

This script creates a TCP socket server inside the Abaqus kernel, allowing
the MCP server to communicate with Abaqus without the GUI plugin.
Useful for headless servers and CI/CD pipelines.
"""

from __future__ import annotations

import json
import socket
import sys
import traceback
from abaqus import *
from abaqusConstants import *
import caeModules

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
    return {"status": "ok", "mode": "nogui", "models": list(mdb.models.keys()) if mdb.models else []}


def handle_run_python(params):
    code = params.get("code", "")
    if not code:
        return {"ok": False, "error": "No code provided"}
    try:
        exec_globals = {"mdb": mdb, "session": session, "__builtins__": __builtins__}
        exec(code, exec_globals)
        if "result" in exec_globals:
            return exec_globals["result"]
        return {"ok": True, "message": "Code executed successfully"}
    except Exception as e:
        tb = traceback.format_exc()
        return {"ok": False, "error": str(e), "error_type": type(e).__name__, "traceback": tb}


def handle_get_model_info(params):
    model_name = params.get("model_name", "Model-1")
    if model_name not in mdb.models:
        return {"ok": False, "error": f"Model '{model_name}' not found"}
    model = mdb.models[model_name]
    info = {
        "name": model_name,
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
    return {"ok": True, **info}


def handle_list_jobs(params):
    import glob
    workdir = params.get("workdir", ".")
    jobs = []
    for f in glob.glob(os.path.join(workdir, "*.inp")):
        jobs.append(os.path.basename(f).replace(".inp", ""))
    return {"ok": True, "jobs": jobs, "count": len(jobs)}


def handle_submit_job(params):
    job_name = params.get("job_name", "")
    if not job_name:
        return {"ok": False, "error": "No job_name provided"}
    try:
        mdb.Job(name=job_name, model=mdb.models.keys()[0])
        mdb.jobs[job_name].submit()
        return {"ok": True, "job": job_name, "status": "submitted"}
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
        import os
        filename = params.get("filename", "viewport.png")
        session.viewports["Viewport: 1"].viewport.setValues(applyOdb=params.get("apply_odb", True))
        session.printOptions.setValues(vpDecorations=ON, reduceColors=False)
        session.printToFile(fileName=filename, format=PNG, canvasObjects=(session.viewports["Viewport: 1"],))
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


def send_message(sock, msg):
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sock.sendall(len(data).to_bytes(4, "big") + data)


def read_message(sock, max_bytes=32*1024*1024):
    size_bytes = b""
    while len(size_bytes) < 4:
        chunk = sock.recv(4 - len(size_bytes))
        if not chunk:
            return None
        size_bytes += chunk
    size = int.from_bytes(size_bytes, "big")
    if size > max_bytes:
        return None
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
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
                        send_message(conn, {"id": req_id, "ok": False, "error": {"message": str(e), "type": type(e).__name__}})
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
