#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-click ODB → 3D viewer.

Usage:
    python serve_viewer.py

Then open http://localhost:8080 in your browser.
Enter an ODB path, click "Export from ODB", and the 3D result appears.

Requires: Abaqus with Python API on the local machine.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

VIEWER_DIR = Path(__file__).resolve().parent
STATIC_DIR = VIEWER_DIR / 'dist'
SAMPLES_DIR = VIEWER_DIR / 'samples'
HOST = "0.0.0.0"
PORT = 8080

# ── VTU v3.0 Export (via viewer/export/export_to_vtk.py) ──

VTU_EXPORT_SCRIPT = r"""
from __future__ import print_function
import json, os, sys
sys.path.insert(0, r__VIEWER_DIR__)
from export.export_to_vtk import export_odb_to_vtk

result = export_odb_to_vtk(
    odb_path=r__ODB_PATH__,
    output_dir=r__OUTPUT_DIR__,
    step_index=__STEP_IDX__,
    frame_step=__FRAME_STEP__,
    deformation_scale=__DEF_SCALE__,
    fields=__FIELDS__,
    binary=False,
)
if result:
    md = json.loads(open(result).read())
    print("MODEL_JSON_PATH:" + result)
    print("NODES:" + str(md.get("num_nodes", 0)))
    print("ELEMS:" + str(md.get("num_elements", 0)))
    print("FRAMES:" + str(len(md.get("frames", []))))
else:
    print("ERROR:Export returned no result")
    sys.exit(1)
"""

class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + POST /api/export."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def translate_path(self, path):
        # Try static dir first, then fall back to viewer root
        import posixpath
        base = super().translate_path(path)
        if os.path.exists(base):
            return base
        # Fallback to samples dir
        sample_path = str(SAMPLES_DIR / posixpath.basename(path))
        if os.path.exists(sample_path):
            return sample_path
        # Fallback to viewer root
        viewer_path = str(VIEWER_DIR / posixpath.basename(path))
        if os.path.exists(viewer_path):
            return viewer_path
        return base

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}", flush=True)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/export":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        odb_path = data.get("odb_path", "").strip()
        if not odb_path:
            self._json_response({"error": "odb_path is required"}, 400)
            return

        if not os.path.isfile(odb_path):
            self._json_response({"error": f"ODB file not found: {odb_path}"}, 404)
            return

        step_index = data.get("step_index", -1)
        frame_step = data.get("frame_step", 1)
        deform_scale = data.get("deformation_scale", 1.0)
        fields = data.get("fields", ["S", "U", "PEEQ", "RF", "E"])

        # Output directory: next to ODB
        base = os.path.splitext(odb_path)[0]
        output_dir = base + "_vtk"

        # Fill in VTU_EXPORT_SCRIPT template
        import shlex
        viewer_dir_escaped = str(VIEWER_DIR).replace("\\", "/")
        script_body = (
            VTU_EXPORT_SCRIPT
            .replace("r__VIEWER_DIR__", repr(viewer_dir_escaped))
            .replace("r__ODB_PATH__", repr(odb_path))
            .replace("r__OUTPUT_DIR__", repr(output_dir))
            .replace("__STEP_IDX__", str(step_index))
            .replace("__FRAME_STEP__", str(frame_step))
            .replace("__DEF_SCALE__", str(deform_scale))
            .replace("__FIELDS__", repr(fields))
        )

        # Write export script to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(script_body)
            script_path = f.name

        try:
            abaqus_cmd = os.environ.get("ABAQUS_COMMAND", "abaqus")
            cmd = [abaqus_cmd, "python", script_path]
            print(f"[export] Running: {' '.join(cmd)}", flush=True)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            print(f"[export] stdout: {proc.stdout}", flush=True)
            if proc.stderr:
                print(f"[export] stderr: {proc.stderr}", flush=True)

            if proc.returncode != 0:
                self._json_response({
                    "error": "Abaqus export failed",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr[-2000:],
                }, 500)
                return

            # Parse output
            model_json_path = ""
            node_count = 0
            elem_count = 0
            frame_count = 0
            for line in proc.stdout.splitlines():
                if line.startswith("MODEL_JSON_PATH:"):
                    model_json_path = line.split(":", 1)[1].strip()
                elif line.startswith("NODES:"):
                    node_count = int(line.split(":")[1])
                elif line.startswith("ELEMS:"):
                    elem_count = int(line.split(":")[1])
                elif line.startswith("FRAMES:"):
                    frame_count = int(line.split(":")[1])

            self._json_response({
                "ok": True,
                "output_path": model_json_path,
                "output_dir": output_dir,
                "format_version": "3.0",
                "node_count": node_count,
                "elem_count": elem_count,
                "frame_count": frame_count,
            })
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    print(f"Serving viewer on http://{HOST}:{PORT}", flush=True)
    print("Enter an ODB path in the sidebar and click 'Export from ODB'.", flush=True)
    server = http.server.HTTPServer((HOST, PORT), ViewerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
