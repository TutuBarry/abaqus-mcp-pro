# -*- coding: utf-8 -*-
"""Export Abaqus ODB results to result_mesh.json for the 3D viewer.

Usage (from Abaqus/CAE Python console or abaqus python):
    from abaqus_mcp_pro.export_result_mesh import export_result_mesh
    export_result_mesh('my_job.odb', 'result_mesh.json')

Or standalone:
    abaqus python export_result_mesh.py my_job.odb result_mesh.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime


def export_result_mesh(
    odb_path: str,
    output_path: str = "",
    step_index: int = -1,
    frame_step: int = 1,
    deformation_scale: float = 1.0,
    fields: list[str] | None = None,
) -> str:
    """Export ODB mesh and field results to a JSON file for the 3D viewer.

    Args:
        odb_path: Path to the ODB file.
        output_path: Path for the output JSON file (default: odb_path + '.result_mesh.json').
        step_index: Step index to export (-1 = last step).
        frame_step: Export every Nth frame (1 = all frames).
        deformation_scale: Scale factor for displacement visualization.
        fields: List of field output variable names to export (e.g. ['S', 'U', 'PEEQ']).
                Default: ['S', 'U', 'PEEQ', 'RF'].

    Returns:
        Path to the created JSON file.
    """
    from odbAccess import openOdb
    from abaqusConstants import SCALAR, VECTOR, TENSOR_3D_FULL, TENSOR_3D_PLANAR
    from abaqusConstants import TENSOR_3D_SURFACE, TENSOR_2D_PLANAR, TENSOR_2D_SURFACE

    if not output_path:
        base = os.path.splitext(odb_path)[0]
        output_path = base + ".result_mesh.json"

    if fields is None:
        fields = ["S", "U", "PEEQ", "RF"]

    print(f"Opening ODB: {odb_path}")
    odb = openOdb(path=odb_path, readOnly=True)

    try:
        # Select step
        steps = list(odb.steps.values())
        if not steps:
            raise ValueError("No steps found in ODB.")
        if step_index < 0:
            step_index = len(steps) + step_index
        if step_index < 0 or step_index >= len(steps):
            step_index = 0
        step = steps[step_index]
        print(f"Step: {step.name} ({step.procedure})")

        # Get the last frame of the step to read mesh and field info
        all_frames = list(step.frames)
        if not all_frames:
            raise ValueError("No frames found in step.")

        # Select frames (every Nth)
        selected_frames = all_frames[::frame_step]
        if not selected_frames:
            selected_frames = [all_frames[-1]]

        # Read mesh from last frame
        last_frame = all_frames[-1]
        instance = odb.rootAssembly.instances[list(odb.rootAssembly.instances.keys())[0]]

        # Export nodes
        print("Exporting nodes...")
        nodes_dict = {}
        for node in instance.nodes:
            nodes_dict[node.label] = list(node.coordinates)
        nodes = [None]  # 1-indexed placeholder
        max_label = max(nodes_dict.keys()) if nodes_dict else 0
        for i in range(1, max_label + 1):
            nodes.append(nodes_dict.get(i, [0.0, 0.0, 0.0]))

        # Export elements grouped by type
        print("Exporting elements...")
        elements = {}
        for elem in instance.elements:
            etype = elem.type.name
            if etype not in elements:
                elements[etype] = []
            elements[etype].append([node.label for node in elem.connectivity])

        # Discover available field outputs
        print("Discovering field outputs...")
        available_fields = {}
        field_outputs = last_frame.fieldOutputs
        for fname in fields:
            if fname in field_outputs:
                fo = field_outputs[fname]
                comps = []
                for comp in fo.values[0].data:
                    if hasattr(comp, 'name'):
                        comps.append(comp.name)
                invars = getattr(fo.values[0], 'invariants', None)
                if invars:
                    for inv in invars:
                        comps.append(inv)
                available_fields[fname] = {
                    "name": fname,
                    "key": fname,
                    "label": fo.description or fname,
                    "components": comps,
                }

        # Build field metadata
        field_meta = []
        for fname, info in available_fields.items():
            for comp in info["components"]:
                field_meta.append({
                    "name": f"{fname}_{comp}",
                    "key": fname,
                    "component": comp,
                    "label": f"{info['label']} ({comp})",
                    "unit": "",
                })

        # Export frames with field data
        print(f"Exporting {len(selected_frames)} frames...")
        frames_data = []
        for fi, frame in enumerate(selected_frames):
            if fi % 10 == 0:
                print(f"  Frame {fi + 1}/{len(selected_frames)}")
            frame_dict = {
                "frame": fi,
                "time": frame.frameValue,
            }
            f_outputs = frame.fieldOutputs
            for fname, info in available_fields.items():
                if fname not in f_outputs:
                    continue
                fo = f_outputs[fname]
                # Build per-node field values
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
                        elif hasattr(d, '__len__') and len(d) > 0:
                            val_map[nid] = float(d[0])
                        else:
                            val_map[nid] = float(d)
                    else:
                        val_map[nid] = 0.0

                # Store per-node values
                values = [None]
                for i in range(1, max_label + 1):
                    values.append(val_map.get(i, 0.0))
                vmin = min(v for v in values[1:] if v is not None)
                vmax = max(v for v in values[1:] if v is not None)
                frame_dict[fname] = {
                    "values": values,
                    "min": vmin,
                    "max": vmax,
                }

            # Displacement
            if "U" in f_outputs:
                u_fo = f_outputs["U"]
                disp = [None]
                for i in range(1, max_label + 1):
                    disp.append([0.0, 0.0, 0.0])
                for val in u_fo.values:
                    nid = val.nodeLabel
                    if nid <= max_label:
                        d = val.data
                        disp[nid] = [float(d[0]), float(d[1]), float(d[2])]
                frame_dict["displacement"] = disp

            frames_data.append(frame_dict)

        # Build output
        result = {
            "format_version": "1.0",
            "export_time": datetime.now().isoformat(),
            "model_name": odb.name or os.path.basename(odb_path),
            "job_name": os.path.splitext(os.path.basename(odb_path))[0],
            "abaqus_version": str(odb.odbVersion) if hasattr(odb, 'odbVersion') else "",
            "deformation_scale_factor": deformation_scale,
            "nodes": nodes,
            "elements": elements,
            "fields": field_meta,
            "steps": [{"name": step.name, "label": step.name, "procedure": step.procedure}],
            "frames": frames_data,
        }

        print(f"Writing {output_path}...")
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))
        print(f"Done. {len(nodes) - 1} nodes, {sum(len(v) for v in elements.values())} elements, {len(frames_data)} frames.")

        return output_path

    finally:
        odb.close()

# ── VTP (v2.0) Export ─────────────────────────────────────────

# Face definitions for common Abaqus element types.
# Each entry: (face_node_count, [(local_node_indices_per_tri), ...])
# Local nodes are 0-indexed within the element connectivity.
_ELEMENT_FACES = {
    # Hex (8 corners)
    "C3D8":  (8, [(0,1,2,3), (4,7,6,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
    "C3D8R": (8, [(0,1,2,3), (4,7,6,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
    # Tet (4 corners)
    "C3D4":  (4, [(0,1,2), (0,2,3), (0,3,1), (1,3,2)]),
    "C3D10": (4, [(0,1,2), (0,2,3), (0,3,1), (1,3,2)]),
    # Wedge (6 corners)
    "C3D6":  (6, [(0,1,2), (3,4,5), (0,1,4,3), (1,2,5,4), (2,0,3,5)]),
    "C3D15": (6, [(0,1,2), (3,4,5), (0,1,4,3), (1,2,5,4), (2,0,3,5)]),
    # Quadratic brick
    "C3D20":  (20, [(0,1,3,2), (4,6,7,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
    "C3D20R": (20, [(0,1,3,2), (4,6,7,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]),
}


def _triangulate_faces(face_nodes):
    """Convert a quad face to 2 triangles, or keep a tri face as-is.
    face_nodes: list of node labels (int)
    Returns list of (a,b,c) node label tuples.
    """
    if len(face_nodes) == 3:
        return [(face_nodes[0], face_nodes[1], face_nodes[2])]
    if len(face_nodes) == 4:
        return [(face_nodes[0], face_nodes[1], face_nodes[2]),
                (face_nodes[0], face_nodes[2], face_nodes[3])]
    # Polygon fan triangulation for >4
    tris = []
    for k in range(1, len(face_nodes) - 1):
        tris.append((face_nodes[0], face_nodes[k], face_nodes[k + 1]))
    return tris


def _build_vtp_xml(points, triangles, field_arrays):
    """Build a VTK XML PolyData string.

    Args:
        points: list of (x,y,z) tuples
        triangles: list of (a,b,c) node-index tuples (0-based)
        field_arrays: dict of name -> list of float values per point
    Returns:
        VTP XML string
    """
    n_pts = len(points)
    n_polys = len(triangles)

    points_xml = chr(10).join(f"{x} {y} {z}" for (x,y,z) in points)
    conn_xml = " ".join(str(idx) for tri in triangles for idx in tri)
    offsets_xml = " ".join(str((i + 1) * 3) for i in range(n_polys))

    # Build PointData XML
    pd_arrays_xml = ""
    for name, vals in field_arrays.items():
        ncomp = 1
        comp_attr = ""
        # Check if vals are tuples/lists (vector data)
        if vals and isinstance(vals[0], (list, tuple)):
            ncomp = len(vals[0])
            comp_attr = f' NumberOfComponents="{ncomp}"'
            vals_xml = chr(10).join(" ".join(str(v) for v in vec) for vec in vals)
        else:
            vals_xml = chr(10).join(str(v) for v in vals)
        pd_arrays_xml += (
            f'        <DataArray type="Float64" Name="{name}"{comp_attr}>\n'
            f"{vals_xml}\n"
            f"        </DataArray>\n"
        )

    # Guess NumberOfVerts/NumberOfLines/NumberOfStrips from polys
    vtp = f"""<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
  <PolyData>
    <Piece NumberOfPoints="{n_pts}" NumberOfVerts="0" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="{n_polys}">
      <PointData>
{pd_arrays_xml}      </PointData>
      <Points>
        <DataArray type="Float64" Name="Points" NumberOfComponents="3">
{points_xml}
        </DataArray>
      </Points>
      <Polys>
        <DataArray type="Int32" Name="connectivity">
{conn_xml}
        </DataArray>
        <DataArray type="Int32" Name="offsets">
{offsets_xml}
        </DataArray>
      </Polys>
    </Piece>
  </PolyData>
</VTKFile>"""
    return vtp


def export_result_mesh_vtp(
    odb_path: str,
    output_prefix: str = "",
    step_index: int = -1,
    frame_step: int = 1,
    deformation_scale: float = 1.0,
    fields: list[str] | None = None,
) -> str:
    """Export ODB results to VTP v2.0 format (per-frame VTP files + index JSON).

    Args:
        odb_path: Path to the ODB file.
        output_prefix: Prefix for output files (default: odb_path without extension).
        step_index: Step index to export (-1 = last step).
        frame_step: Export every Nth frame.
        deformation_scale: Scale factor for displacement visualization.
        fields: List of field output variable names to export.

    Returns:
        Path to the created index JSON file.
    """
    from odbAccess import openOdb

    if not output_prefix:
        output_prefix = os.path.splitext(odb_path)[0]
    if fields is None:
        fields = ["S", "U", "PEEQ", "RF"]

    print(f"Opening ODB: {odb_path}")
    odb = openOdb(path=odb_path, readOnly=True)

    try:
        steps = list(odb.steps.values())
        if not steps:
            raise ValueError("No steps found in ODB.")
        if step_index < 0:
            step_index = len(steps) + step_index
        step = steps[max(0, min(step_index, len(steps) - 1))]
        print(f"Step: {step.name} ({step.procedure})")

        all_frames = list(step.frames)
        if not all_frames:
            raise ValueError("No frames found in step.")
        selected = all_frames[::frame_step] or [all_frames[-1]]

        instance = odb.rootAssembly.instances[list(odb.rootAssembly.instances.keys())[0]]

        # ── Build nodes list (1-indexed, None at 0) ──
        nd = {}
        for n in instance.nodes:
            nd[n.label] = list(n.coordinates)
        nodes = [None]
        max_label = max(nd.keys()) if nd else 0
        for i in range(1, max_label + 1):
            nodes.append(nd.get(i, [0.0, 0.0, 0.0]))

        # ── Triangulate elements ──
        all_tris = []  # list of (a,b,c) using 0-based node indices
        elem_tri_counts = []
        for elem in instance.elements:
            conn = [n.label for n in elem.connectivity]
            etype = elem.type.name
            ncorners, faces = _ELEMENT_FACES.get(etype, (4, [(0,1,2,3)]))  # fallback to tet
            for face in faces:
                face_nodes = [conn[ln] for ln in face[:len(face)]]  # use only corner nodes
                tris = _triangulate_faces(face_nodes)
                # Convert node labels (1-based) to 0-based indices
                for tri in tris:
                    all_tris.append(tuple(nid - 1 for nid in tri))
                    elem_tri_counts.append(elem.label)

        print(f"  Nodes: {max_label}, Surface triangles: {len(all_tris)}")

        # ── Field metadata (from last frame) ──
        last_frame = all_frames[-1]
        fos = last_frame.fieldOutputs
        field_meta = []
        field_names = {}
        for fn in fields:
            if fn in fos:
                fo = fos[fn]
                comps = []
                # Check if first value is scalar or vector
                v0 = fo.values[0]
                if hasattr(v0, 'mises'):
                    comps = ['Mises']
                elif hasattr(v0, 'magnitude'):
                    comps = ['Magnitude']
                elif hasattr(v0, 'data'):
                    d = v0.data
                    if isinstance(d, float):
                        comps = ['']
                    elif hasattr(d, '__len__'):
                        ncomp = len(d)
                        if ncomp == 1:
                            comps = ['']
                        elif ncomp == 3:
                            comps = ['', '']  # vector stored as single array
                        else:
                            comps = ['']
                label = fo.description or fn
                if comps and comps[0]:
                    for c in comps:
                        fname = f"{fn}_{c}"
                        field_meta.append({
                            "name": fname, "key": fn, "component": c,
                            "label": f"{label} ({c})", "unit": "",
                        })
                        field_names[fname] = fn
                else:
                    field_meta.append({
                        "name": fn, "key": fn, "component": "",
                        "label": label, "unit": "",
                    })
                    field_names[fn] = fn

        # ── Process each frame ──
        vtp_files = []
        frames_index = []
        for fi, frame in enumerate(selected):
            print(f"  Frame {fi}/{len(selected)-1} (t={frame.frameValue})...")
            fouts = frame.fieldOutputs

            # Read node values for each field
            point_field_vals = {}  # name -> [val_per_node]
            for fname in fields:
                if fname not in fouts:
                    continue
                fo = fouts[fname]
                val_map = {}
                for val in fo.values:
                    nid = val.nodeLabel
                    # Determine the scalar/vector value
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
                            elif len(d) == 1:
                                val_map[nid] = float(d[0])
                            else:
                                val_map[nid] = float(d[0])
                    else:
                        val_map[nid] = 0.0

                # Build per-node arrays (1-indexed, fill missing)
                arr = []
                for i in range(1, max_label + 1):
                    arr.append(val_map.get(i, 0.0))
                point_field_vals[fname] = arr

            # Read displacement
            disp_arr = None
            if "U" in fouts:
                ufo = fouts["U"]
                disp = [None]  # 0-index place holder (node 1 at index 1)
                for i in range(1, max_label + 1):
                    disp.append([0.0, 0.0, 0.0])
                for val in ufo.values:
                    nid = val.nodeLabel
                    if nid <= max_label:
                        d = val.data
                        disp[nid] = [float(d[0]), float(d[1]), float(d[2])]
                # Remove placeholder
                disp_arr = disp[1:]  # list of [dx, dy, dz] per node (0-based)

            # Build points (original coordinates)
            coords = [nodes[i] for i in range(1, max_label + 1)]  # 0-based flat list

            # Apply deformation if available
            pts = []
            for j in range(max_label):
                x, y, z = coords[j]
                if disp_arr and deformation_scale > 0:
                    dx, dy, dz = disp_arr[j]
                    s = deformation_scale
                    x += dx * s
                    y += dy * s
                    z += dz * s
                pts.append((x, y, z))

            # Get only the vertices referenced by triangles
            vert_set = set()
            for (a, b, c) in all_tris:
                vert_set.add(a)
                vert_set.add(b)
                vert_set.add(c)

            # Build compact vertex list for the VTP (only used vertices)
            vert_map = {}  # old_idx -> new_idx
            compact_pts = []
            for vi in sorted(vert_set):
                vert_map[vi] = len(compact_pts)
                compact_pts.append(pts[vi])

            # Remap triangle indices to compact space
            compact_tris = []
            for (a, b, c) in all_tris:
                compact_tris.append((vert_map[a], vert_map[b], vert_map[c]))

            # Build field arrays for the compact vertices
            compact_field_arrays = {}
            for fname, arr in point_field_vals.items():
                compact_arr = [arr[vi] for vi in sorted(vert_set)]
                # If the values are tuples/vectors, keep as-is
                compact_field_arrays[fname] = compact_arr

            # Add displacement as a field array
            if disp_arr:
                compact_field_arrays["U"] = [disp_arr[vi] for vi in sorted(vert_set)]

            # Write VTP file
            vtp_out = f"{output_prefix}_frame_{fi:04d}.vtp"
            vtp_xml = _build_vtp_xml(compact_pts, compact_tris, compact_field_arrays)
            with open(vtp_out, "w") as f:
                f.write(vtp_xml)

            vtp_files.append(vtp_out)
            frames_index.append({
                "frame": fi,
                "time": frame.frameValue,
                "vtp_file": os.path.basename(vtp_out),
            })

        # ── Write index JSON ──
        # Determine field_min/max across all frames for legend
        index = {
            "format_version": "2.0",
            "export_time": datetime.now().isoformat(),
            "model_name": odb.name or os.path.basename(odb_path),
            "job_name": os.path.splitext(os.path.basename(odb_path))[0],
            "abaqus_version": str(odb.odbVersion) if hasattr(odb, 'odbVersion') else "",
            "deformation_scale_factor": deformation_scale,
            "num_nodes": max_label,
            "num_elements": len(all_tris),
            "fields": field_meta,
            "steps": [{"name": step.name, "label": step.name, "procedure": step.procedure}],
            "frames": frames_index,
        }

        index_path = f"{output_prefix}_v2.json"
        with open(index_path, "w") as f:
            json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

        print(f"Done. {max_label} nodes, {len(all_tris)} triangles, {len(selected)} frames -> {index_path}")
        return index_path

    finally:
        odb.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: abaqus python export_result_mesh.py <odb_path> [output_path] [step_index] [frame_step] [scale]")
        print("  odb_path    : Path to ODB file")
        print("  output_path : Output JSON path (default: odb_path.result_mesh.json)")
        print("  step_index  : Step index (default: -1 = last)")
        print("  frame_step  : Export every Nth frame (default: 1)")
        print("  scale       : Deformation scale factor (default: 1.0)")
        sys.exit(1)

    odb_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else ""
    step_index = int(sys.argv[3]) if len(sys.argv) > 3 else -1
    frame_step = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    scale = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0

    result_path = export_result_mesh(
        odb_path=odb_path,
        output_path=output_path,
        step_index=step_index,
        frame_step=frame_step,
        deformation_scale=scale,
    )
    print(f"Result mesh saved to: {result_path}")


if __name__ == "__main__":
    main()

