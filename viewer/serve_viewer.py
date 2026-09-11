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


# ── VTP v2.0 Export functions ─────────────────────────────────

_ELEMENT_FACES = {
    "C3D8":  (8, [(0,1,2,3), (4,7,6,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
    "C3D8R": (8, [(0,1,2,3), (4,7,6,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
    "C3D4":  (4, [(0,1,2), (0,2,3), (0,3,1), (1,3,2)]),
    "C3D10": (4, [(0,1,2), (0,2,3), (0,3,1), (1,3,2)]),
    "C3D6":  (6, [(0,1,2), (3,4,5), (0,1,4,3), (1,2,5,4), (2,0,3,5)]),
    "C3D15": (6, [(0,1,2), (3,4,5), (0,1,4,3), (1,2,5,4), (2,0,3,5)]),
    "C3D20":  (20, [(0,1,3,2), (4,6,7,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
    "C3D20R": (20, [(0,1,3,2), (4,6,7,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
}


def _triangulate_faces(face_nodes):
    if len(face_nodes) == 3:
        return [(face_nodes[0], face_nodes[1], face_nodes[2])]
    if len(face_nodes) == 4:
        return [(face_nodes[0], face_nodes[1], face_nodes[2]),
                (face_nodes[0], face_nodes[2], face_nodes[3])]
    tris = []
    for k in range(1, len(face_nodes) - 1):
        tris.append((face_nodes[0], face_nodes[k], face_nodes[k + 1]))
    return tris


def _build_vtp_xml(points, triangles, field_arrays):
    n_pts = len(points)
    n_polys = len(triangles)

    points_list = []
    for (x, y, z) in points:
        points_list.append("%s %s %s" % (x, y, z))
    points_xml = chr(10).join(points_list)

    conn_list = []
    for tri in triangles:
        for idx in tri:
            conn_list.append(str(idx))
    conn_xml = " ".join(conn_list)

    offsets_list = []
    for i in range(n_polys):
        offsets_list.append(str((i + 1) * 3))
    offsets_xml = " ".join(offsets_list)

    pd_arrays_list = []
    for name, vals in field_arrays.items():
        ncomp = 1
        comp_attr = ""
        if vals and isinstance(vals[0], (list, tuple)):
            ncomp = len(vals[0])
            comp_attr = ' NumberOfComponents="%d"' % ncomp
            vec_strs = []
            for vec in vals:
                vec_strs.append(" ".join(str(v) for v in vec))
            vals_xml = chr(10).join(vec_strs)
        else:
            s_vals = []
            for v in vals:
                s_vals.append(str(v))
            vals_xml = chr(10).join(s_vals)
        pd_arrays_list.append(
            '        <DataArray type="Float64" Name="%s"%s>' % (name, comp_attr)
            + chr(10)
            + "%s" % vals_xml
            + chr(10)
            + "        </DataArray>"
        )
    pd_arrays_xml = chr(10).join(pd_arrays_list)

    vtp_lines = []
    vtp_lines.append('<?xml version="1.0"?>')
    vtp_lines.append('<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">')
    vtp_lines.append('  <PolyData>')
    vtp_lines.append('    <Piece NumberOfPoints="%d" NumberOfVerts="0" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="%d">' % (n_pts, n_polys))
    vtp_lines.append('      <PointData>')
    vtp_lines.append(pd_arrays_xml)
    vtp_lines.append('      </PointData>')
    vtp_lines.append('      <Points>')
    vtp_lines.append('        <DataArray type="Float64" Name="Points" NumberOfComponents="3">')
    vtp_lines.append(points_xml)
    vtp_lines.append('        </DataArray>')
    vtp_lines.append('      </Points>')
    vtp_lines.append('      <Polys>')
    vtp_lines.append('        <DataArray type="Int32" Name="connectivity">')
    vtp_lines.append(conn_xml)
    vtp_lines.append('        </DataArray>')
    vtp_lines.append('        <DataArray type="Int32" Name="offsets">')
    vtp_lines.append(offsets_xml)
    vtp_lines.append('        </DataArray>')
    vtp_lines.append('      </Polys>')
    vtp_lines.append('    </Piece>')
    vtp_lines.append('  </PolyData>')
    vtp_lines.append('</VTKFile>')
    return chr(10).join(vtp_lines)


def export_vtp(odb_path, output_prefix, step_index, frame_step, deform_scale, fields):
    from odbAccess import openOdb

    if fields is None:
        fields = ["S", "U", "PEEQ", "RF"]

    print("Opening ODB: %s" % odb_path)
    odb = openOdb(path=odb_path, readOnly=True)

    try:
        steps = list(odb.steps.values())
        if not steps:
            raise ValueError("No steps found in ODB.")
        if step_index < 0:
            step_index = len(steps) + step_index
        step = steps[max(0, min(step_index, len(steps) - 1))]

        all_frames = list(step.frames)
        if not all_frames:
            raise ValueError("No frames found in step.")
        selected = all_frames[::frame_step] or [all_frames[-1]]

        instance = odb.rootAssembly.instances[list(odb.rootAssembly.instances.keys())[0]]

        # Build nodes (1-indexed)
        nd = {}
        for n in instance.nodes:
            nd[n.label] = list(n.coordinates)
        nodes = [None]
        max_label = max(nd.keys()) if nd else 0
        for i in range(1, max_label + 1):
            nodes.append(nd.get(i, [0.0, 0.0, 0.0]))

        # Triangulate elements into surface triangles
        all_tris = []
        for elem in instance.elements:
            conn = [n.label for n in elem.connectivity]
            etype = elem.type.name
            ncorners, faces = _ELEMENT_FACES.get(etype, (4, [(0,1,2,3)]))
            for face in faces:
                face_nodes = [conn[ln] for ln in face[:len(face)]]
                tris = _triangulate_faces(face_nodes)
                for tri in tris:
                    all_tris.append(tuple(nid - 1 for nid in tri))

        print("  Nodes: %d, Surface triangles: %d" % (max_label, len(all_tris)))

        # Field metadata (from last frame)
        last_frame = all_frames[-1]
        fos = last_frame.fieldOutputs
        field_meta = []
        for fn in fields:
            if fn in fos:
                fo = fos[fn]
                label = fo.description or fn
                field_meta.append({
                    "name": fn, "key": fn, "component": "",
                    "label": label, "unit": "",
                })

        # Process each frame
        vtp_files = []
        frames_index = []
        for fi, frame in enumerate(selected):
            print("  Frame %d/%d (t=%s)..." % (fi, len(selected)-1, frame.frameValue))
            fouts = frame.fieldOutputs

            # Read node values for each field
            point_field_vals = {}
            for fname in fields:
                if fname not in fouts:
                    continue
                fo = fouts[fname]
                val_map = {}
                for val in fo.values:
                    nid = val.nodeLabel
                    if hasattr(val, 'mises'):
                        val_map[nid] = val.mises
                    elif hasattr(val, 'magnitude'):
                        val_map[nid] = val.magnitude
                    elif hasattr(val, 'data'):
                        d = val.data
                        if isinstance(d, float):
                            val_map[nid] = d
                        elif hasattr(d, '__len__'):
                            if len(d) == 3:
                                val_map[nid] = (float(d[0]), float(d[1]), float(d[2]))
                            else:
                                val_map[nid] = float(d[0])
                    else:
                        val_map[nid] = 0.0
                arr = []
                for i in range(1, max_label + 1):
                    arr.append(val_map.get(i, 0.0))
                point_field_vals[fname] = arr

            # Read displacement
            disp_arr = None
            if "U" in fouts:
                ufo = fouts["U"]
                disp = [None]
                for i in range(1, max_label + 1):
                    disp.append([0.0, 0.0, 0.0])
                for val in ufo.values:
                    nid = val.nodeLabel
                    d = val.data
                    disp[nid] = [float(d[0]), float(d[1]), float(d[2])]
                disp_arr = disp[1:]

            # Build deformed points
            coords = [nodes[i] for i in range(1, max_label + 1)]
            pts = []
            for j in range(max_label):
                x, y, z = coords[j]
                if disp_arr and deform_scale > 0:
                    dx, dy, dz = disp_arr[j]
                    s = deform_scale
                    x += dx * s
                    y += dy * s
                    z += dz * s
                pts.append((x, y, z))

            # Compact vertex optimization (only vertices referenced by triangles)
            vert_set = set()
            for (a, b, c) in all_tris:
                vert_set.add(a)
                vert_set.add(b)
                vert_set.add(c)

            vert_map = {}
            compact_pts = []
            for vi in sorted(vert_set):
                vert_map[vi] = len(compact_pts)
                compact_pts.append(pts[vi])

            compact_tris = []
            for (a, b, c) in all_tris:
                compact_tris.append((vert_map[a], vert_map[b], vert_map[c]))

            compact_field_arrays = {}
            for fname, arr in point_field_vals.items():
                compact_arr = [arr[vi] for vi in sorted(vert_set)]
                compact_field_arrays[fname] = compact_arr
            if disp_arr:
                compact_field_arrays["U"] = [disp_arr[vi] for vi in sorted(vert_set)]

            # Write VTP file
            vtp_out = "%s_frame_%04d.vtp" % (output_prefix, fi)
            vtp_xml = _build_vtp_xml(compact_pts, compact_tris, compact_field_arrays)
            with open(vtp_out, "w") as f:
                f.write(vtp_xml)

            vtp_files.append(vtp_out)
            frames_index.append({
                "frame": fi,
                "time": frame.frameValue,
                "vtp_file": os.path.basename(vtp_out),
            })

        # Write index JSON
        index = {
            "format_version": "2.0",
            "export_time": datetime.now().isoformat(),
            "model_name": odb.name or os.path.basename(odb_path),
            "job_name": os.path.splitext(os.path.basename(odb_path))[0],
            "abaqus_version": str(odb.odbVersion) if hasattr(odb, 'odbVersion') else "",
            "deformation_scale_factor": deform_scale,
            "num_nodes": max_label,
            "num_elements": len(all_tris),
            "fields": field_meta,
            "steps": [{"name": step.name, "label": step.name, "procedure": step.procedure}],
            "frames": frames_index,
        }

        index_path = "%s_v2.json" % output_prefix
        with open(index_path, "w") as f:
            json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

        print("OK:" + index_path)
        print("NODES:" + str(max_label))
        print("ELEMS:" + str(len(all_tris)))
        print("FRAMES:" + str(len(selected)))
        return index_path

    finally:
        odb.close()


if __name__ == "__main__":
    export_v2 = len(sys.argv) > 6 and sys.argv[6].lower() in ("true", "1", "yes")
    if export_v2:
        export_vtp(
            odb_path=sys.argv[1],
            output_prefix=os.path.splitext(sys.argv[2])[0],
            step_index=int(sys.argv[3]) if len(sys.argv) > 3 else -1,
            frame_step=int(sys.argv[4]) if len(sys.argv) > 4 else 1,
            deform_scale=float(sys.argv[5]) if len(sys.argv) > 5 else 1.0,
            fields=["S", "U", "PEEQ", "RF"],
        )
    else:
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
        export_v2 = data.get("export_v2", False)

        # Output next to ODB or in temp
        base = os.path.splitext(odb_path)[0]
        if export_v2:
            output_path = base  # prefix for VTP files and index JSON
        else:
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
                str(export_v2).lower(),
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
                "format_version": "2.0" if export_v2 else "1.0",
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
