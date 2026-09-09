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
HOST = "127.0.0.1"
PORT = 8080

# ── Embedded export script (runs inside Abaqus Python) ──
EXPORT_SCRIPT = r'''
from __future__ import print_function
import json, os, sys
from datetime import datetime
from odbAccess import openOdb

def export(odb_path, output_path, step_index, frame_step, deform_scale, fields):
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        steps = list(odb.steps.values())
        if not steps:
            raise ValueError("No steps found in ODB.")
        if step_index < 0:
            step_index = len(steps) + step_index
        step = steps[max(0, min(step_index, len(steps)-1))]
        all_frames = list(step.frames)
        if not all_frames:
            raise ValueError("No frames found.")
        selected = all_frames[::frame_step] or [all_frames[-1]]
        last_frame = all_frames[-1]
        inst = odb.rootAssembly.instances[list(odb.rootAssembly.instances.keys())[0]]

        # Nodes
        nd = {}
        for n in inst.nodes:
            nd[n.label] = list(n.coordinates)
        nodes = [None]
        ml = max(nd.keys()) if nd else 0
        for i in range(1, ml + 1):
            nodes.append(nd.get(i, [0.0, 0.0, 0.0]))

        # Elements
        elems = {}
        for e in inst.elements:
            et = e.type.name
            if et not in elems:
                elems[et] = []
            elems[et].append([n.label for n in e.connectivity])

        # Field metadata
        avail = {}
        fos = last_frame.fieldOutputs
        for fn in fields:
            if fn in fos:
                fo = fos[fn]
                comps = []
                for v in fo.values[0].data:
                    if hasattr(v, 'name'):
                        comps.append(v.name)
                invs = getattr(fo.values[0], 'invariants', None)
                if invs:
                    for inv in invs:
                        comps.append(inv)
                avail[fn] = {"name": fn, "key": fn, "label": fo.description or fn, "components": comps}

        field_meta = []
        for fn, info in avail.items():
            for comp in info["components"]:
                field_meta.append({"name": f"{fn}_{comp}", "key": fn, "component": comp, "label": f"{info['label']} ({comp})", "unit": ""})

        # Frames
        frames_data = []
        for fi, frame in enumerate(selected):
            fd = {"frame": fi, "time": frame.frameValue}
            fouts = frame.fieldOutputs
            for fn, info in avail.items():
                if fn not in fouts:
                    continue
                fo = fouts[fn]
                vm = {}
                for val in fo.values:
                    nid = val.nodeLabel
                    if hasattr(val, 'mises'):
                        vm[nid] = val.mises
                    elif hasattr(val, 'magnitude'):
                        vm[nid] = val.magnitude
                    elif hasattr(val, 'data'):
                        d = val.data
                        if isinstance(d, float):
                            vm[nid] = d
                        elif hasattr(d, '__len__') and len(d) > 0:
                            vm[nid] = float(d[0])
                        else:
                            vm[nid] = float(d)
                    else:
                        vm[nid] = 0.0
                vals = [None]
                for i in range(1, ml + 1):
                    vals.append(vm.get(i, 0.0))
                vmin = min(v for v in vals[1:] if v is not None)
                vmax = max(v for v in vals[1:] if v is not None)
                fd[fn] = {"values": vals, "min": vmin, "max": vmax}

            # Displacement
            if "U" in fouts:
                ufo = fouts["U"]
                disp = [None]
                for i in range(1, ml + 1):
                    disp.append([0.0, 0.0, 0.0])
                for val in ufo.values:
                    nid = val.nodeLabel
                    if nid <= ml:
                        d = val.data
                        disp[nid] = [float(d[0]), float(d[1]), float(d[2])]
                fd["displacement"] = disp
            frames_data.append(fd)

        result = {
            "format_version": "1.0",
            "export_time": datetime.now().isoformat(),
            "model_name": odb.name or os.path.basename(odb_path),
            "job_name": os.path.splitext(os.path.basename(odb_path))[0],
            "abaqus_version": str(odb.odbVersion) if hasattr(odb, 'odbVersion') else "",
            "deformation_scale_factor": deform_scale,
            "nodes": nodes,
            "elements": elems,
            "fields": field_meta,
            "steps": [{"name": step.name, "label": step.name, "procedure": step.procedure}],
            "frames": frames_data,
        }
        with open(output_path, "w") as fp:
            json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))
        print("OK:" + output_path)
        print("NODES:" + str(len(nodes) - 1))
        print("ELEMS:" + str(sum(len(v) for v in elems.values())))
        print("FRAMES:" + str(len(frames_data)))
    finally:
        odb.close()

if __name__ == "__main__":
    export(
        odb_path=sys.argv[1],
        output_path=sys.argv[2],
        step_index=int(sys.argv[3]) if len(sys.argv) > 3 else -1,
        frame_step=int(sys.argv[4]) if len(sys.argv) > 4 else 1,
        deform_scale=float(sys.argv[5]) if len(sys.argv) > 5 else 1.0,
        fields=["S", "U", "PEEQ", "RF"],
    )
'''


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + POST /api/export."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(VIEWER_DIR), **kwargs)

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

        # Output next to ODB or in temp
        base = os.path.splitext(odb_path)[0]
        output_path = base + ".result_mesh.json"

        # Write export script to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(EXPORT_SCRIPT)
            script_path = f.name

        try:
            abaqus_cmd = os.environ.get("ABAQUS_COMMAND", "abaqus")
            cmd = [
                abaqus_cmd, "python", script_path,
                odb_path, output_path,
                str(step_index), str(frame_step), str(deform_scale),
            ]
            print(f"[export] Running: {' '.join(cmd)}", flush=True)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
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
            node_count = 0
            elem_count = 0
            frame_count = 0
            for line in proc.stdout.splitlines():
                if line.startswith("NODES:"):
                    node_count = int(line.split(":")[1])
                elif line.startswith("ELEMS:"):
                    elem_count = int(line.split(":")[1])
                elif line.startswith("FRAMES:"):
                    frame_count = int(line.split(":")[1])

            self._json_response({
                "ok": True,
                "output_path": output_path,
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
