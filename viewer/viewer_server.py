#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastAPI server for Abaqus MCP Pro 3D Viewer.

Usage:
    uvicorn viewer_server:app --host 0.0.0.0 --port 8080 --reload
    python viewer_server.py
"""

from __future__ import annotations
import json, os, subprocess, sys, time, uuid, threading
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    print("FastAPI not installed. Install with: pip install fastapi uvicorn")
    sys.exit(1)

VIEWER_DIR = Path(__file__).resolve().parent
STATIC_DIR = VIEWER_DIR / "dist"
CACHE_DIR = VIEWER_DIR / ".export_cache"

sys.path.insert(0, str(VIEWER_DIR))
try:
    from cache import ExportCache
    _cache = ExportCache(cache_dir=str(CACHE_DIR))
except ImportError:
    _cache = None

app = FastAPI(title="Abaqus MCP Pro Viewer", version="2.0.0")

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

_tasks: dict[str, dict] = {}


class ExportRequest(BaseModel):
    odb_path: str
    step_index: int = -1
    frame_step: int = 1
    deformation_scale: float = 1.0
    fields: list[str] = ["S", "U", "PEEQ", "RF", "E", "SDV"]


@app.get("/api/models")
async def list_models():
    if _cache:
        return _cache.list_cached()
    return []


@app.get("/api/latest-export")
async def latest_export():
    if _cache:
        cached = _cache.list_cached()
        if cached:
            latest = max(cached, key=lambda x: x.get("cached_at", 0))
            mp = Path(latest.get("path", "")) / "model.json"
            if mp.exists():
                return JSONResponse(content=json.loads(mp.read_text(encoding="utf-8")))
    raise HTTPException(status_code=404, detail="No exports found")


@app.post("/api/export")
async def start_export(req: ExportRequest):
    odb_path = req.odb_path.strip()
    if not os.path.isfile(odb_path):
        raise HTTPException(status_code=400, detail=f"ODB not found: {odb_path}")

    # Check cache
    if _cache:
        cached = _cache.get(odb_path, req.step_index, req.frame_step, req.deformation_scale, req.fields)
        if cached and os.path.isfile(cached):
            return {"task_id": "cached", "output_path": cached, "cached": True}

    task_id = uuid.uuid4().hex[:12]
    result_dir = CACHE_DIR / task_id
    result_dir.mkdir(parents=True, exist_ok=True)

    _tasks[task_id] = {"status": "running", "progress": 0, "message": "Starting export...", "output_dir": str(result_dir)}

    thread = threading.Thread(target=_run_export, args=(task_id, odb_path, result_dir, req), daemon=True)
    thread.start()
    return {"task_id": task_id, "output_dir": str(result_dir)}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _run_export(task_id, odb_path, result_dir, req):
    try:
        _tasks[task_id]["progress"] = 10
        _tasks[task_id]["message"] = "Reading ODB..."

        abaqus_cmd = None
        for candidate in ["abaqus", "abq2024", "abq2023", "abq2022"]:
            try:
                subprocess.run([candidate, "python", "--version"], capture_output=True, timeout=5)
                abaqus_cmd = candidate
                break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        if abaqus_cmd:
            _tasks[task_id]["progress"] = 20
            _tasks[task_id]["message"] = f"Running {abaqus_cmd} python..."
            script_path = result_dir / "_export_script.py"
            script_path.write_text(
                'import sys; sys.path.insert(0, %r)\n'
                'from export.export_to_vtk import export_odb_to_vtk\n'
                'result = export_odb_to_vtk(%r, output_dir=%r, step_index=%d,'
                ' frame_step=%d, deformation_scale=%f, fields=%s)\n'
                'if result:\n'
                '  import json\n'
                '  print("OK:" + result)\n'
                '  m = json.loads(open(result).read())\n'
                '  print("STAT:" + json.dumps({"nodes":m.get("num_nodes",0),'
                '"elems":m.get("num_elements",0),"frames":len(m.get("frames",[]))}))\n'
                'else:\n'
                '  print("ERROR:Export returned no result")\n'
                % (str(VIEWER_DIR), odb_path, str(result_dir),
                   req.step_index, req.frame_step, req.deformation_scale, req.fields)
            )
            proc = subprocess.run([abaqus_cmd, "python", str(script_path)],
                                  capture_output=True, text=True, timeout=600)
            _tasks[task_id]["progress"] = 80
            _tasks[task_id]["message"] = "Processing output..."
            for line in proc.stdout.split("\n"):
                line = line.strip()
                if line.startswith("OK:"):
                    _tasks[task_id]["output_path"] = line[3:].strip()
                elif line.startswith("STAT:"):
                    try:
                        s = json.loads(line[5:])
                        _tasks[task_id].update(s)
                    except: pass
                elif line.startswith("ERROR:"):
                    raise RuntimeError(line[6:])
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"Exit code {proc.returncode}")
        else:
            _tasks[task_id]["message"] = "No Abaqus found on this machine"
            _tasks[task_id]["status"] = "error"
            _tasks[task_id]["progress"] = 0
            return

        _tasks[task_id]["progress"] = 100
        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["message"] = "Export completed"

        if _cache and _tasks[task_id].get("output_path"):
            _cache.put(odb_path, str(result_dir), req.step_index, req.frame_step, req.deformation_scale, req.fields)

    except Exception as e:
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["message"] = str(e)
        _tasks[task_id]["progress"] = 0


if __name__ == "__main__":
    import uvicorn
    print("Starting viewer server on http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
