# -*- coding: utf-8 -*-
"""
Abaqus ODB → VTK Unstructured Grid (.vtu) Exporter
====================================================

Runs inside Abaqus Python (no pip packages required).
Uses only: json, os, struct, base64, xml.etree.ElementTree, datetime, sys

Output:
  {output_dir}/
    model.json         ← metadata (element types, field list, frame index)
    frame_0000.vtu     ← frame 0
    frame_0001.vtu     ← frame 1
    ...

Usage (inside Abaqus Python):
    from viewer.export.export_to_vtk import export_odb_to_vtk
    export_odb_to_vtk("job.odb", output_dir="./vtk_out")

Command line:
    abaqus python export_to_vtk.py job.odb --output-dir ./vtk_out
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

# ---------------------------------------------------------------------------
# VTK Cell Type constants (matching vtkCellType.h)
# ---------------------------------------------------------------------------
VTK_VERTEX = 1
VTK_LINE = 3
VTK_TRIANGLE = 5
VTK_QUAD = 9
VTK_TETRA = 10
VTK_PYRAMID = 7
VTK_WEDGE = 13
VTK_HEXAHEDRON = 12
VTK_QUADRATIC_EDGE = 21
VTK_QUADRATIC_TRIANGLE = 22
VTK_QUADRATIC_QUAD = 23
VTK_QUADRATIC_TETRA = 24
VTK_QUADRATIC_HEXAHEDRON = 25
VTK_QUADRATIC_WEDGE = 26

# ---------------------------------------------------------------------------
# Abaqus → VTK element type mapping
# ---------------------------------------------------------------------------
ELEMENT_TYPE_MAP = {
    "C3D4":  (VTK_TETRA, 4),
    "C3D5":  (VTK_PYRAMID, 5),
    "C3D6":  (VTK_WEDGE, 6),
    "C3D8":  (VTK_HEXAHEDRON, 8),
    "C3D8R": (VTK_HEXAHEDRON, 8),
    "C3D8I": (VTK_HEXAHEDRON, 8),
    "C3D10": (VTK_QUADRATIC_TETRA, 10),
    "C3D10M":(VTK_QUADRATIC_TETRA, 10),
    "C3D15": (VTK_QUADRATIC_WEDGE, 15),
    "C3D20": (VTK_QUADRATIC_HEXAHEDRON, 20),
    "C3D20R":(VTK_QUADRATIC_HEXAHEDRON, 20),
    "C3D20H":(VTK_QUADRATIC_HEXAHEDRON, 20),
    "S3":    (VTK_TRIANGLE, 3),
    "S3R":   (VTK_TRIANGLE, 3),
    "S4":    (VTK_QUAD, 4),
    "S4R":   (VTK_QUAD, 4),
    "S5":    (VTK_QUAD, 4),
    "S6":    (VTK_QUADRATIC_TRIANGLE, 6),
    "S8":    (VTK_QUADRATIC_QUAD, 8),
    "S8R":   (VTK_QUADRATIC_QUAD, 8),
    "S9":    (VTK_QUADRATIC_QUAD, 9),
    "STRI3": (VTK_TRIANGLE, 3),
    "STRI65":(VTK_QUADRATIC_TRIANGLE, 6),
    "M3D3":  (VTK_TRIANGLE, 3),
    "M3D4":  (VTK_QUAD, 4),
    "M3D4R": (VTK_QUAD, 4),
    "M3D6":  (VTK_QUADRATIC_TRIANGLE, 6),
    "M3D8":  (VTK_QUADRATIC_QUAD, 8),
    "M3D8R": (VTK_QUADRATIC_QUAD, 8),
    "M3D9":  (VTK_QUADRATIC_QUAD, 9),
    "B21":   (VTK_LINE, 2),
    "B22":   (VTK_QUADRATIC_EDGE, 3),
    "B31":   (VTK_LINE, 2),
    "B31H":  (VTK_LINE, 2),
    "B32":   (VTK_QUADRATIC_EDGE, 3),
    "B32H":  (VTK_QUADRATIC_EDGE, 3),
    "B33":   (VTK_QUADRATIC_EDGE, 3),
    "T2D2":  (VTK_LINE, 2),
    "T2D3":  (VTK_QUADRATIC_EDGE, 3),
    "T3D2":  (VTK_LINE, 2),
    "T3D2H": (VTK_LINE, 2),
    "T3D3":  (VTK_QUADRATIC_EDGE, 3),
    "R2D2":  (VTK_LINE, 2),
    "R3D3":  (VTK_TRIANGLE, 3),
    "R3D4":  (VTK_QUAD, 4),
}

def _flatten_float64(values):
    buf = bytearray()
    for v in values:
        buf.extend(struct.pack(">d", float(v)))
    return bytes(buf)


def _flatten_int32(values):
    buf = bytearray()
    for v in values:
        buf.extend(struct.pack(">i", int(v)))
    return bytes(buf)


def _make_data_array_xml(name, binary_data, num_components, offset):
    ncomp_str = ""
    if num_components > 1:
        ncomp_str = ' NumberOfComponents="%d"' % num_components
    ctype = "Float64"
    if name in ("connectivity", "offsets", "types"):
        ctype = "Int32"
    el = ET.fromstring(
        '<DataArray type="%s" Name="%s"%s format="appended" offset="%d"/>' % (ctype, name, ncomp_str, offset)
    )
    return el


def export_odb_to_vtk(
    odb_path,
    output_dir="",
    step_index=-1,
    frame_step=1,
    deformation_scale=1.0,
    fields=None,
    binary=True,
):
    if fields is None:
        fields = ["S", "U", "PEEQ", "RF", "E", "SDV"]

    if not output_dir:
        base = os.path.splitext(os.path.basename(odb_path))[0]
        output_dir = os.path.join(os.path.dirname(odb_path), base + "_vtk")
    os.makedirs(output_dir, exist_ok=True)

    import odbAccess
    from odbAccess import openOdb

    print("[VTK Export] Opening ODB: %s" % odb_path)
    odb = openOdb(path=odb_path, readOnly=True)

    try:
        steps = list(odb.steps.values())
        if not steps:
            raise ValueError("No steps found in ODB.")
        if step_index < 0:
            step_index = len(steps) + step_index
        step = steps[max(0, min(step_index, len(steps) - 1))]
        print("[VTK Export] Step: %s (%s)" % (step.name, step.procedure))

        all_frames = list(step.frames)
        if not all_frames:
            raise ValueError("No frames found in step.")
        selected_frames = all_frames[::frame_step] or [all_frames[-1]]
        last_frame = all_frames[-1]

        # ---- Gather nodes ----
        instance = odb.rootAssembly.instances[
            list(odb.rootAssembly.instances.keys())[0]
        ]
        node_map = {}
        coords_list = []
        for node in instance.nodes:
            idx = len(coords_list)
            node_map[node.label] = idx
            coords_list.append((node.coordinates[0], node.coordinates[1], node.coordinates[2]))
        num_nodes = len(coords_list)
        print("[VTK Export] Nodes: %d" % num_nodes)

        # ---- Gather elements ----
        elem_type_info = {}
        total_cells = 0
        for elem in instance.elements:
            etype = elem.type.name
            if etype not in ELEMENT_TYPE_MAP:
                if etype not in elem_type_info:
                    print("[VTK Export] WARNING: Unsupported element type '%s', skipping" % etype)
                    elem_type_info[etype] = None
                continue
            if elem_type_info.get(etype) is None:
                vtk_type, nn = ELEMENT_TYPE_MAP[etype]
                elem_type_info[etype] = {
                    "vtk_type": vtk_type,
                    "num_nodes": nn,
                    "connectivity": [],
                }
            conn = [node_map[n.label] for n in elem.connectivity]
            elem_type_info[etype]["connectivity"].append(conn)
            total_cells += 1
        print("[VTK Export] Elements: %d in %d types" % (total_cells, len([k for k, v in elem_type_info.items() if v is not None])))

        elem_type_info = {k: v for k, v in elem_type_info.items() if v is not None}

        # ---- Discover field outputs ----
        def _describe_field(fo, fo_name):
            v0 = fo.values[0]
            try:
                inv = v0.invariants
                if inv:
                    for inv_var in inv:
                        if "MISES" in str(inv_var.name).upper():
                            return (fo_name, 1, ["Mises"])
                        if "MAGNITUDE" in str(inv_var.name).upper():
                            return (fo_name, 1, ["Magnitude"])
            except Exception:
                pass
            try:
                d = v0.data
                if isinstance(d, float):
                    return (fo_name, 1, [""])
                if hasattr(d, "__len__"):
                    ncomp = len(d)
                    if ncomp == 1:
                        return (fo_name, 1, [""])
                    elif ncomp == 3:
                        return (fo_name, 3, ["X", "Y", "Z"])
                    elif ncomp == 6:
                        return (fo_name, 6, ["XX", "YY", "ZZ", "XY", "XZ", "YZ"])
            except Exception:
                pass
            return (fo_name, 1, [""])

        field_outputs_available = {}
        for fname in fields:
            if fname in last_frame.fieldOutputs:
                fo = last_frame.fieldOutputs[fname]
                try:
                    key, ncomp, comps = _describe_field(fo, fname)
                    field_outputs_available[fname] = {
                        "fo": fo,
                        "ncomp": ncomp,
                        "comps": comps,
                        "label": fo.description or fname,
                    }
                    print("[VTK Export] Field '%s': %d component(s)" % (fname, ncomp))
                except Exception as e:
                    print("[VTK Export] WARNING: Could not describe field '%s': %s" % (fname, e))

        field_meta_list = []
        for fname, info in field_outputs_available.items():
            for ci, comp in enumerate(info["comps"]):
                if comp:
                    entry_name = "%s_%s" % (fname, comp)
                    label = "%s (%s)" % (info["label"], comp)
                else:
                    entry_name = fname
                    label = info["label"]
                field_meta_list.append({
                    "name": entry_name,
                    "key": fname,
                    "component_index": ci,
                    "ncomp": info["ncomp"],
                    "label": label,
                    "unit": "",
                })

        # ---- Process each frame ----
        frames_meta = []
        for fi, frame in enumerate(selected_frames):
            print("[VTK Export] Frame %d/%d (t=%s)..." % (fi + 1, len(selected_frames), frame.frameValue))

            point_data = {}
            for fname, finfo in field_outputs_available.items():
                fo = frame.fieldOutputs.get(fname)
                if fo is None:
                    continue
                ncomp = finfo["ncomp"]
                vals = [0.0] * (num_nodes * ncomp)
                for v in fo.values:
                    nid = v.nodeLabel
                    if nid not in node_map:
                        continue
                    ni = node_map[nid]
                    try:
                        if hasattr(v, "mises"):
                            vals[ni] = v.mises
                        elif hasattr(v, "magnitude"):
                            vals[ni] = v.magnitude
                        else:
                            d = v.data
                            if isinstance(d, float):
                                vals[ni] = d
                            elif hasattr(d, "__len__"):
                                for j in range(min(ncomp, len(d))):
                                    vals[ni * ncomp + j] = float(d[j])
                    except Exception:
                        pass
                point_data[fname] = vals

            disp_data = None
            if "U" in field_outputs_available:
                u_fo = frame.fieldOutputs.get("U")
                if u_fo is not None:
                    disp_data = [0.0, 0.0, 0.0] * num_nodes
                    for v in u_fo.values:
                        nid = v.nodeLabel
                        if nid not in node_map:
                            continue
                        ni = node_map[nid]
                        try:
                            d = v.data
                            for j in range(min(3, len(d))):
                                disp_data[ni * 3 + j] = float(d[j])
                        except Exception:
                            pass

            if disp_data is not None and deformation_scale > 0:
                deformed_coords = [0.0] * (num_nodes * 3)
                for ni in range(num_nodes):
                    x, y, z = coords_list[ni]
                    dx = disp_data[ni * 3] * deformation_scale
                    dy = disp_data[ni * 3 + 1] * deformation_scale
                    dz = disp_data[ni * 3 + 2] * deformation_scale
                    deformed_coords[ni * 3] = x + dx
                    deformed_coords[ni * 3 + 1] = y + dy
                    deformed_coords[ni * 3 + 2] = z + dz
            else:
                deformed_coords = []
                for pt in coords_list:
                    deformed_coords.append(pt[0])
                    deformed_coords.append(pt[1])
                    deformed_coords.append(pt[2])

            vtu_path = os.path.join(output_dir, "frame_%04d.vtu" % fi)
            _write_vtu(
                vtu_path,
                points=deformed_coords,
                elem_type_info=elem_type_info,
                num_nodes=num_nodes,
                point_data=point_data,
                field_outputs_available=field_outputs_available,
            )

            frame_field_ranges = {}
            for fname, vals in point_data.items():
                finfo = field_outputs_available[fname]
                ncomp = finfo["ncomp"]
                fmin = min(vals)
                fmax = max(vals)
                frame_field_ranges[fname] = {"min": fmin, "max": fmax}

            frames_meta.append({
                "frame": fi,
                "time": frame.frameValue,
                "vtu_file": os.path.basename(vtu_path),
                "field_ranges": frame_field_ranges,
                "num_nodes": num_nodes,
                "num_cells": total_cells,
            })

        # ---- Global field ranges ----
        global_field_ranges = {}
        for fname in field_outputs_available:
            all_mins = [f["field_ranges"][fname]["min"] for f in frames_meta if fname in f["field_ranges"]]
            all_maxs = [f["field_ranges"][fname]["max"] for f in frames_meta if fname in f["field_ranges"]]
            if all_mins:
                global_field_ranges[fname] = {"min": min(all_mins), "max": max(all_maxs)}

        # ---- Write model.json ----
        model_info = {
            "format_version": "3.0",
            "export_time": datetime.now().isoformat(),
            "model_name": odb.name or os.path.basename(odb_path),
            "job_name": os.path.splitext(os.path.basename(odb_path))[0],
            "abaqus_version": str(getattr(odb, "odbVersion", "")),
            "odb_path": odb_path,
            "deformation_scale_factor": deformation_scale,
            "num_nodes": num_nodes,
            "num_elements": total_cells,
            "element_types": {k: {"vtk_type": v["vtk_type"], "count": len(v["connectivity"])}
                              for k, v in elem_type_info.items()},
            "fields": field_meta_list,
            "field_ranges": global_field_ranges,
            "steps": [{"name": step.name, "label": step.name, "procedure": step.procedure}],
            "frames": frames_meta,
        }

        model_path = os.path.join(output_dir, "model.json")
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(model_info, f, indent=2, ensure_ascii=False)

        print("[VTK Export] Done. %d nodes, %d cells, %d frames." % (num_nodes, total_cells, len(selected_frames)))
        print("[VTK Export] Output: %s" % output_dir)
        print("[VTK Export] Index:  %s" % model_path)
        return model_path

    finally:
        odb.close()


def _write_vtu(path, points, elem_type_info, num_nodes, point_data, field_outputs_available):
    conn_list = []
    offsets_list = []
    types_list = []
    for etype, einfo in elem_type_info.items():
        vtk_type = einfo["vtk_type"]
        for cell_conn in einfo["connectivity"]:
            for nid in cell_conn:
                conn_list.append(nid)
            offsets_list.append(len(conn_list))
            types_list.append(vtk_type)
    num_cells = len(types_list)

    all_arrs = []
    all_arrs.append(("Points", _flatten_float64(points), 3))
    all_arrs.append(("connectivity", _flatten_int32(conn_list), 1))
    all_arrs.append(("offsets", _flatten_int32(offsets_list), 1))
    all_arrs.append(("types", _flatten_int32(types_list), 1))

    for fname, finfo in field_outputs_available.items():
        ncomp = finfo["ncomp"]
        if fname in point_data:
            all_arrs.append((fname, _flatten_float64(point_data[fname]), ncomp))

    # Build appended data
    appended = bytearray()
    for name, bdata, ncomp in all_arrs:
        header = struct.pack(">I", len(bdata))
        appended.extend(header)
        appended.extend(bdata)
    padding = (3 - len(appended) % 3) % 3
    appended.extend(b"\x00" * padding)
    b64 = base64.b64encode(bytes(appended)).decode("ascii")

    # Compute offsets
    offset_cur = 0
    offsets = []
    for name, bdata, ncomp in all_arrs:
        offsets.append(offset_cur)
        offset_cur += 4 + len(bdata)

    # Build XML
    vtk_file = ET.Element("VTKFile", {
        "type": "UnstructuredGrid",
        "version": "0.1",
        "byte_order": "BigEndian",
    })
    grid = ET.SubElement(vtk_file, "UnstructuredGrid")
    piece = ET.SubElement(grid, "Piece", {
        "NumberOfPoints": str(num_nodes),
        "NumberOfCells": str(num_cells),
    })

    pd = ET.SubElement(piece, "PointData")
    for i in range(4, len(all_arrs)):
        name, bdata, ncomp = all_arrs[i]
        pd.append(_make_data_array_xml(name, bdata, ncomp, offsets[i]))

    cd = ET.SubElement(piece, "CellData")

    pts_el = ET.SubElement(piece, "Points")
    pts_el.append(_make_data_array_xml("Points", all_arrs[0][1], 3, offsets[0]))

    cells_el = ET.SubElement(piece, "Cells")
    for i in range(1, 4):
        name, bdata, ncomp = all_arrs[i]
        cells_el.append(_make_data_array_xml(name, bdata, ncomp, offsets[i]))

    # Serialize
    xml_str = ET.tostring(vtk_file, encoding="unicode", xml_declaration=True)
    full_xml = xml_str.replace(
        "</UnstructuredGrid>",
        '  <AppendedData encoding="base64">\n_%s\n  </AppendedData>\n</UnstructuredGrid>' % b64
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(full_xml)


def export_odb_to_vtk_main(argv=None):
    if argv is None:
        argv = sys.argv
    import argparse
    parser = argparse.ArgumentParser(
        description="Export Abaqus ODB results to VTK Unstructured Grid (.vtu) format."
    )
    parser.add_argument("odb_path", help="Path to the ODB file")
    parser.add_argument("--output-dir", "-o", default="",
                        help="Output directory (default: <odb_stem>_vtk)")
    parser.add_argument("--step-index", type=int, default=-1,
                        help="Step index (default: -1 = last step)")
    parser.add_argument("--frame-step", type=int, default=1,
                        help="Export every Nth frame (default: 1)")
    parser.add_argument("--deformation-scale", type=float, default=1.0,
                        help="Deformation scale factor (default: 1.0)")
    parser.add_argument("--fields", nargs="*",
                        default=["S", "U", "PEEQ", "RF", "E", "SDV"],
                        help="Field output variables to export")
    parser.add_argument("--ascii", action="store_true",
                        help="Use ASCII encoding instead of binary")

    args = parser.parse_args(argv[1:])
    export_odb_to_vtk(
        odb_path=args.odb_path,
        output_dir=args.output_dir,
        step_index=args.step_index,
        frame_step=args.frame_step,
        deformation_scale=args.deformation_scale,
        fields=args.fields,
        binary=not args.ascii,
    )


if __name__ == "__main__":
    export_odb_to_vtk_main()
