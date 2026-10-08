# -*- coding: utf-8 -*-
"""
Abaqus ODB to VTK Unstructured Grid (.vtu) Exporter

Runs inside Abaqus Python (no pip packages required).
Uses only: json, os, xml.etree.ElementTree, datetime, sys

Incorporates element-nodal averaging and full invariant extraction
from Liujie-SYSU/odb2vtk.

Output:
  {output_dir}/
    model.json         -- metadata (element types, field list, frame index)
    frame_0000.vtu     -- frame 0
    frame_0001.vtu     -- frame 1
    ...

Usage (inside Abaqus Python):
    from viewer.export.export_to_vtk import export_odb_to_vtk
    export_odb_to_vtk("job.odb", output_dir="./vtk_out")

Command line:
    abaqus python export_to_vtk.py job.odb --output-dir ./vtk_out
"""

from __future__ import annotations
import json
import math
import hashlib
from xml.sax.saxutils import escape
import os
import sys
from datetime import datetime

# VTK Cell Type constants
VTK_VERTEX = 1
VTK_LINE = 3
VTK_TRIANGLE = 5
VTK_QUAD = 9
VTK_TETRA = 10
VTK_PYRAMID = 14
VTK_WEDGE = 13
VTK_HEXAHEDRON = 12
VTK_QUADRATIC_EDGE = 21
VTK_QUADRATIC_TRIANGLE = 22
VTK_QUADRATIC_QUAD = 23
VTK_QUADRATIC_TETRA = 24
VTK_QUADRATIC_HEXAHEDRON = 25
VTK_QUADRATIC_WEDGE = 26

# Abaqus -> VTK element type mapping
ELEMENT_TYPE_MAP = {
    "C3D4": (VTK_TETRA, 4),
    "C3D5": (VTK_PYRAMID, 5),
    "C3D6": (VTK_WEDGE, 6),
    "C3D8": (VTK_HEXAHEDRON, 8),
    "C3D8R": (VTK_HEXAHEDRON, 8),
    "C3D8I": (VTK_HEXAHEDRON, 8),
    "C3D10": (VTK_QUADRATIC_TETRA, 10),
    "C3D10M": (VTK_QUADRATIC_TETRA, 10),
    "C3D15": (VTK_QUADRATIC_WEDGE, 15),
    "C3D20": (VTK_QUADRATIC_HEXAHEDRON, 20),
    "C3D20R": (VTK_QUADRATIC_HEXAHEDRON, 20),
    "C3D20H": (VTK_QUADRATIC_HEXAHEDRON, 20),
    "S3": (VTK_TRIANGLE, 3),
    "S3R": (VTK_TRIANGLE, 3),
    "S4": (VTK_QUAD, 4),
    "S4R": (VTK_QUAD, 4),
    "S5": (VTK_QUAD, 4),
    "S6": (VTK_QUADRATIC_TRIANGLE, 6),
    "S8": (VTK_QUADRATIC_QUAD, 8),
    "S8R": (VTK_QUADRATIC_QUAD, 8),
    "S9": (28, 9),
    "STRI3": (VTK_TRIANGLE, 3),
    "STRI65": (VTK_QUADRATIC_TRIANGLE, 6),
    "M3D3": (VTK_TRIANGLE, 3),
    "M3D4": (VTK_QUAD, 4),
    "M3D4R": (VTK_QUAD, 4),
    "M3D6": (VTK_QUADRATIC_TRIANGLE, 6),
    "M3D8": (VTK_QUADRATIC_QUAD, 8),
    "M3D8R": (VTK_QUADRATIC_QUAD, 8),
    "M3D9": (28, 9),
    "B21": (VTK_LINE, 2),
    "B22": (VTK_QUADRATIC_EDGE, 3),
    "B31": (VTK_LINE, 2),
    "B31H": (VTK_LINE, 2),
    "B32": (VTK_QUADRATIC_EDGE, 3),
    "B32H": (VTK_QUADRATIC_EDGE, 3),
    "B33": (VTK_LINE, 2),
    "T2D2": (VTK_LINE, 2),
    "T2D3": (VTK_QUADRATIC_EDGE, 3),
    "T3D2": (VTK_LINE, 2),
    "T3D2H": (VTK_LINE, 2),
    "T3D3": (VTK_QUADRATIC_EDGE, 3),
    "R2D2": (VTK_LINE, 2),
    "R3D3": (VTK_TRIANGLE, 3),
    "R3D4": (VTK_QUAD, 4),
}

def _lookup_vtk_type(abaqus_element_type):
    """Substring-based Abaqus -> VTK cell type mapping (fallback)."""
    et = abaqus_element_type.upper()
    if "C3D4" in et:
        return (10, 4)
    if "C3D5" in et:
        return (14, 5)
    if "C3D6" in et:
        return (13, 6)
    if "C3D8" in et:
        return (12, 8)
    if "C3D10" in et:
        return (24, 10)
    if "C3D15" in et:
        return (26, 15)
    if "C3D20" in et:
        return (25, 20)
    if "S3" in et or "STRI3" in et:
        return (5, 3)
    if "S4" in et:
        return (9, 4)
    if "S6" in et:
        return (22, 6)
    if "S8" in et:
        return (23, 8)
    if "S9" in et:
        return (28, 9)
    if "M3D3" in et:
        return (5, 3)
    if "M3D4" in et:
        return (9, 4)
    if et.startswith(('B22', 'B32')):
        return (21, 3)
    if "B31" in et or "B33" in et:
        return (3, 2)
    if "T2D2" in et or "T2D3" in et:
        return (3, 2)
    if "T3D2" in et or "T3D3" in et:
        return (3, 2)
    if "R2D2" in et:
        return (3, 2)
    if "R3D3" in et:
        return (5, 3)
    if "R3D4" in et:
        return (9, 4)
    raise KeyError("Unsupported element type: %s" % abaqus_element_type)


# Field definitions -- Liujie-SYSU/odb2vtk element-nodal approach
# (read_strategy, ncomp, component_labels, invariant_attr_names)
# "nodal": direct fo.values (U, RF, A, V)
# "elem_nodal": getSubset(position=ELEMENT_NODAL) + count-avg (S, E, ...)
_ELEMENT_NODAL_POS = 1  # Abaqus ELEMENT_NODAL constant

FIELD_DEFS = {
    "U": ("nodal", 3, ["X", "Y", "Z"], []),
    "RF": ("nodal", 3, ["X", "Y", "Z"], []),
    "A": ("nodal", 3, ["X", "Y", "Z"], []),
    "V": ("nodal", 3, ["X", "Y", "Z"], []),
    "TEMP": ("nodal", 1, [], []),
    "S": ("elem_nodal", 6, ["XX","YY","ZZ","XY","XZ","YZ"],
          ["mises","maxPrincipal","midPrincipal","minPrincipal",
           "press","tresca","inv3"]),
    "E": ("elem_nodal", 6, ["XX","YY","ZZ","XY","XZ","YZ"],
          ["mises"]),
    "LE": ("elem_nodal", 6, ["XX","YY","ZZ","XY","XZ","YZ"],
           ["maxPrincipal","midPrincipal","minPrincipal"]),
    "PE": ("elem_nodal", 6, ["XX","YY","ZZ","XY","XZ","YZ"],
           ["maxPrincipal","midPrincipal","minPrincipal"]),
    "PEEQ": ("elem_nodal", 1, [], []),
    "SDV": ("elem_nodal", 1, [], []),
    "HFL": ("elem_nodal", 3, ["X", "Y", "Z"], []),
    "CSTRESS": ("elem_nodal", 6, ["XX","YY","ZZ","XY","XZ","YZ"],
                ["mises","maxPrincipal","midPrincipal","minPrincipal",
                 "press","tresca","inv3"]),
    "CF": ("elem_nodal", 3, ["X", "Y", "Z"], []),
}

DEFAULT_FIELDS = ["U", "RF", "S", "E", "LE", "PE", "PEEQ"]
CONTACT_FIELDS = ('CPRESS', 'COPEN', 'CSHEAR1', 'CSHEAR2', 'CSLIP1', 'CSLIP2', 'CSTATUS')
DEFAULT_FIELDS += list(CONTACT_FIELDS)


def _component_labels(field_key, ncomp):
    if field_key in FIELD_DEFS:
        return FIELD_DEFS[field_key][2]
    if ncomp == 1:
        return [""]
    if ncomp == 3:
        return ["X", "Y", "Z"]
    if ncomp == 6:
        return ["XX", "YY", "ZZ", "XY", "XZ", "YZ"]
    return [str(i) for i in range(ncomp)]


def _field_data(value):
    try:
        return value.data
    except Exception:
        return value.dataDouble


def _field_unit(name, unit_system):
    if not unit_system:
        return ''
    if name in ('S', 'CPRESS', 'CSHEAR1', 'CSHEAR2'):
        return 'MPa' if unit_system == 'N-mm-s-tonne' else 'Pa'
    if name in ('U', 'COPEN', 'CSLIP1', 'CSLIP2'):
        return 'mm' if unit_system == 'N-mm-s-tonne' else 'm'
    if name in ('RF', 'CF'):
        return 'N'
    return ''


def _node_key(value):
    return (value.instance.name, value.nodeLabel)


def _read_nodal_field(frame_fo, node_map, num_nodes, ncomp):
    vals = [float("nan")] * (num_nodes * ncomp)
    for value in frame_fo.values:
        key = _node_key(value)
        if key not in node_map:
            continue
        index = node_map[key] * ncomp
        data = _field_data(value)
        row = [data] if isinstance(data, (int, float)) else list(data)
        # Abaqus 2D vectors have no third component.
        if len(row) == 2 and ncomp == 3:
            row.append(0.0)
        if len(row) != ncomp:
            raise ValueError("Unexpected field component count")
        vals[index:index + ncomp] = [float(v) for v in row]
    return vals


def _read_elem_nodal_field(frame_fo, node_map, num_nodes, ncomp, invariants, section_point=None):
    from abaqusConstants import ELEMENT_NODAL
    subset = frame_fo.getSubset(position=ELEMENT_NODAL, readOnly=True)
    sums = [0.0] * (num_nodes * ncomp)
    counts = [0] * num_nodes
    inv_sums = {inv: [0.0] * num_nodes for inv in invariants}
    inv_counts = {inv: [0] * num_nodes for inv in invariants}
    sections = set()
    for value in subset.values:
        key = _node_key(value)
        if key not in node_map:
            continue
        section = getattr(getattr(value, "sectionPoint", None), "number", 0)
        if section_point is not None and section != section_point:
            continue
        sections.add(section)
        if len(sections) > 1:
            raise ValueError("Multiple section points: select a section point before nodal averaging")
        ni = node_map[key]
        data = _field_data(value)
        row = [data] if isinstance(data, (int, float)) else list(data)
        if len(row) != ncomp:
            raise ValueError("Unexpected tensor components; use actual componentLabels")
        for j, number in enumerate(row):
            sums[ni * ncomp + j] += float(number)
        counts[ni] += 1
        for inv in invariants:
            number = getattr(value, inv, None)
            if number is not None and math.isfinite(float(number)):
                inv_sums[inv][ni] += float(number)
                inv_counts[inv][ni] += 1
    vals = [float("nan")] * (num_nodes * ncomp)
    for ni, count in enumerate(counts):
        if count:
            for j in range(ncomp):
                vals[ni * ncomp + j] = sums[ni * ncomp + j] / count
    return {"data": vals, "invariants": {
        inv: [inv_sums[inv][i] / inv_counts[inv][i] if inv_counts[inv][i] else float("nan")
              for i in range(num_nodes)] for inv in invariants}}


def _write_vtu_ascii(path, points, elem_type_info, num_nodes, point_data,
                     field_outputs_available):
    """Write VTU in ASCII format (viewer supports only format=ascii)."""
    conn_list = []
    offsets_list = []
    types_list = []
    for etype, einfo in sorted(elem_type_info.items()):
        vtk_type = einfo["vtk_type"]
        for cell_conn in einfo["connectivity"]:
            for nid in cell_conn:
                conn_list.append(nid)
            offsets_list.append(len(conn_list))
            types_list.append(vtk_type)
    num_cells = len(types_list)

    lines = []
    lines.append("<?xml version=\"1.0\"?>")
    lines.append("<VTKFile type=\"UnstructuredGrid\" version=\"0.1\" byte_order=\"LittleEndian\">")
    lines.append("  <UnstructuredGrid>")
    lines.append("    <Piece NumberOfPoints=\"%d\" NumberOfCells=\"%d\">" % (num_nodes, num_cells))

    # PointData
    pd_lines = []
    for fname in sorted(point_data.keys()):
        vals = point_data[fname]
        ncomp = 1
        if fname in field_outputs_available:
            ncomp = field_outputs_available[fname]["ncomp"]
        else:
            for fkey, finfo in field_outputs_available.items():
                if fname.startswith(fkey + "_"):
                    ncomp = 1
                    break
        nc_str = "" if ncomp <= 1 else " NumberOfComponents=\"%d\"" % ncomp
        pd_lines.append("      <DataArray type=\"Float64\" Name=\"%s\"%s format=\"ascii\">" % (escape(fname, {chr(34): "&quot;"}), nc_str))
        chunk = []
        for v in vals:
            chunk.append("%.16e" % v)
            if len(chunk) >= 6:
                pd_lines.append("        " + " ".join(chunk))
                chunk = []
        if chunk:
            pd_lines.append("        " + " ".join(chunk))
        pd_lines.append("      </DataArray>")

    if pd_lines:
        lines.append("      <PointData>")
        lines.extend(pd_lines)
        lines.append("      </PointData>")
    else:
        lines.append("      <PointData/>")

    lines.append("      <CellData/>")

    # Points
    lines.append("      <Points>")
    lines.append("        <DataArray type=\"Float64\" Name=\"Points\" NumberOfComponents=\"3\" format=\"ascii\">")
    chunk = []
    for i in range(0, len(points), 3):
        chunk.append("%.16e %.16e %.16e" % (points[i], points[i+1], points[i+2]))
        if len(chunk) >= 4:
            lines.append("          " + " ".join(chunk))
            chunk = []
    if chunk:
        lines.append("          " + " ".join(chunk))
    lines.append("        </DataArray>")
    lines.append("      </Points>")

    # Cells
    lines.append("      <Cells>")
    lines.append("        <DataArray type=\"Int32\" Name=\"connectivity\" format=\"ascii\">")
    chunk = []
    for v in conn_list:
        chunk.append(str(v))
        if len(chunk) >= 20:
            lines.append("          " + " ".join(chunk))
            chunk = []
    if chunk:
        lines.append("          " + " ".join(chunk))
    lines.append("        </DataArray>")
    lines.append("        <DataArray type=\"Int32\" Name=\"offsets\" format=\"ascii\">")
    chunk = []
    for v in offsets_list:
        chunk.append(str(v))
        if len(chunk) >= 20:
            lines.append("          " + " ".join(chunk))
            chunk = []
    if chunk:
        lines.append("          " + " ".join(chunk))
    lines.append("        </DataArray>")
    lines.append("        <DataArray type=\"Int32\" Name=\"types\" format=\"ascii\">")
    chunk = []
    for v in types_list:
        chunk.append(str(v))
        if len(chunk) >= 20:
            lines.append("          " + " ".join(chunk))
            chunk = []
    if chunk:
        lines.append("          " + " ".join(chunk))
    lines.append("        </DataArray>")
    lines.append("      </Cells>")

    lines.append("    </Piece>")
    lines.append("  </UnstructuredGrid>")
    lines.append("</VTKFile>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_pvd(pvd_path, output_dir, frames_meta, vtu_pattern="frame_%04d.vtu"):
    """Write a ParaView .pvd collection file."""
    lines = []
    lines.append("<?xml version=\"1.0\"?>")
    lines.append("<VTKFile type=\"Collection\" version=\"0.1\" byte_order=\"LittleEndian\">")
    lines.append("  <Collection>")
    for fm in frames_meta:
        fname = vtu_pattern % fm["frame"]
        t = fm.get("time", 0.0)
        lines.append("    <DataSet timestep=\"%s\" group=\"\" part=\"0\" file=\"%s\"/>" % (t, fname))
    lines.append("  </Collection>")
    lines.append("</VTKFile>")
    with open(pvd_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# Main export function

def export_odb_to_vtk(
    odb_path,
    output_dir="",
    step_index=-1,
    frame_step=1,
    deformation_scale=1.0,
    fields=None,
    binary=True,        # kept for backward compat; viewer always uses ASCII
    instance_names=None,
    ascii_format=False,  # kept for backward compat
    write_pvd=False,
    _odb_handle=None,
    section_point=None,
    unit_system='',
):
    """Export an Abaqus ODB to VTK Unstructured Grid (.vtu) files."""
    if type(frame_step) is not int or frame_step < 1:
        raise ValueError("frame_step must be a positive integer")
    if type(step_index) is not int:
        raise ValueError("step_index must be an integer")
    if section_point is not None and (type(section_point) is not int or section_point < 1):
        raise ValueError('section_point must be a positive integer')
    if not math.isfinite(deformation_scale) or deformation_scale < 0:
        raise ValueError("deformation_scale must be finite and nonnegative")
    if fields is None:
        fields = list(DEFAULT_FIELDS)
    if unit_system not in ('', 'N-mm-s-tonne', 'N-m-s-kg'):
        raise ValueError('Unsupported declared unit system')

    if not output_dir:
        base = os.path.splitext(os.path.basename(odb_path))[0]
        output_dir = os.path.join(os.path.dirname(odb_path), base + "_vtk")
    os.makedirs(output_dir, exist_ok=True)

    if _odb_handle is not None:
        odb = _odb_handle
        print("[VTK Export] Using provided ODB handle")
    else:
        from odbAccess import openOdb
        odb = openOdb(path=odb_path, readOnly=True)

    _need_close = _odb_handle is None
    try:
        steps = list(odb.steps.values())
        if not steps:
            raise ValueError("No steps found in ODB.")
        if step_index < 0:
            step_index = len(steps) + step_index
        if not 0 <= step_index < len(steps):
            raise ValueError("step_index out of range")
        step = steps[step_index]
        print("[VTK Export] Step: %s (%s)" % (step.name, step.procedure))

        all_frames = list(step.frames)
        if not all_frames:
            raise ValueError("No frames found in step.")
        selected_frames = all_frames[::frame_step] or [all_frames[-1]]
        last_frame = all_frames[-1]

        # Mesh: gather nodes (all instances)
        if instance_names is None:
            instance_names = list(odb.rootAssembly.instances.keys())
        node_map = {}
        coords_list = []
        elem_type_info = {}
        total_cells = 0
        for iname in instance_names:
            inst = odb.rootAssembly.instances[iname]
            for node in inst.nodes:
                idx = len(coords_list)
                node_map[(iname, node.label)] = idx
                coords_list.append((
                    node.coordinates[0],
                    node.coordinates[1],
                    node.coordinates[2] if len(node.coordinates) > 2 else 0.0,
                ))
            for elem in inst.elements:
                etype = str(elem.type)
                vtk_info = ELEMENT_TYPE_MAP.get(etype)
                if vtk_info is None:
                    try:
                        vtk_info = _lookup_vtk_type(etype)
                    except KeyError:
                        raise ValueError('Unsupported element type: ' + etype)
                if elem_type_info.get(etype) is None:
                    vtk_type, nn = vtk_info
                    elem_type_info[etype] = {
                        "vtk_type": vtk_type,
                        "num_nodes": nn,
                        "connectivity": [],
                    }
                labels = list(elem.connectivity)
                expected = vtk_info[1]
                # Beam connectivity can include an extra orientation node.
                if etype.startswith('B') and len(labels) == expected + 1:
                    labels = labels[:expected]
                if len(labels) != expected:
                    raise ValueError('Unexpected connectivity for ' + etype)
                if etype.startswith(('B22', 'B32')):
                    # Abaqus: end, middle, end. VTK: end, end, middle.
                    labels = [labels[0], labels[2], labels[1]]
                conn = [node_map[(iname, label)] for label in labels]
                elem_type_info[etype]["connectivity"].append(conn)
                total_cells += 1
        num_nodes = len(coords_list)
        # Connected mesh bodies remain distinct even inside a single ODB instance.
        parent = list(range(num_nodes))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for info in elem_type_info.values():
            for conn in info['connectivity']:
                for i in conn[1:]:
                    parent[find(i)] = find(conn[0])
        body_lookup = {}
        body_ids = []
        bodies = []
        for (iname, _), i in node_map.items():
            key = (iname, find(i))
            if key not in body_lookup:
                body_lookup[key] = len(bodies)
                bodies.append({'id': len(bodies), 'name': iname + ' / body ' + str(len(bodies) + 1)})
            body_ids.append(body_lookup[key])
        print("[VTK Export] Instances: %s" % instance_names)
        print("[VTK Export] Nodes: %d, Elements: %d" % (num_nodes, total_cells))
        elem_type_info = {k: v for k, v in elem_type_info.items() if v is not None}
        print("[VTK Export] Active element types: %s" % list(elem_type_info.keys()))

        # Discover available fields
        def _field_exists(fname):
            try:
                return fname in last_frame.fieldOutputs
            except Exception:
                return False

        available_field_keys = []
        contact_sources = {}
        for fname in fields:
            if fname in CONTACT_FIELDS:
                for source in last_frame.fieldOutputs.keys():
                    if source.split()[0] == fname:
                        alias = fname if source == fname else fname + '_' + hashlib.sha256(source.encode()).hexdigest()[:12]
                        contact_sources[alias] = source
                        FIELD_DEFS[alias] = ('nodal', 1, [''], [])
                        available_field_keys.append(alias)
                continue
            if fname in FIELD_DEFS:
                if _field_exists(fname):
                    available_field_keys.append(fname)
                else:
                    print("[VTK Export] WARNING: Field '%s' not found "
                          "in ODB, skipping" % fname)
            else:
                if _field_exists(fname):
                    fo = last_frame.fieldOutputs[fname]
                    try:
                        v0 = fo.values[0]
                        d = v0.data
                        ncomp = 1 if isinstance(d, float) else len(d)
                    except Exception:
                        ncomp = 1
                    FIELD_DEFS[fname] = ("nodal", ncomp,
                                         _component_labels(fname, ncomp), [])
                    available_field_keys.append(fname)
                else:
                    print("[VTK Export] WARNING: Field '%s' not found "
                          "in ODB, skipping" % fname)

        label_map = {
            "U": "Displacement", "RF": "Reaction Force",
            "A": "Acceleration", "V": "Velocity",
            "S": "Stress", "E": "Strain",
            "LE": "Logarithmic Strain", "PE": "Plastic Strain",
            "PEEQ": "Equivalent Plastic Strain",
            "SDV": "Solution Dependent Variables",
            "TEMP": "Temperature",
            "HFL": "Heat Flux",
            "CSTRESS": "Contact Stress",
            "CF": "Contact Force",
        }

        if not available_field_keys:
            raise ValueError("None of the requested fields are available")
        field_outputs_available = {}
        field_meta_list = []
        for fname in available_field_keys:
            source_name = contact_sources.get(fname, fname)
            fd = FIELD_DEFS[fname]
            fd_type, ncomp, comps, invariants = fd
            actual_labels = list(getattr(last_frame.fieldOutputs[source_name], "componentLabels", ()))
            if actual_labels:
                comps = actual_labels
                ncomp = len(comps)
                if fname == 'U' and ncomp == 2:
                    comps = comps + ['U3']
                    ncomp = 3
            elif ncomp == 1:
                comps = [""]
            valid = {str(v).replace("_", "").lower() for v in
                     getattr(last_frame.fieldOutputs[source_name], "validInvariants", ())}
            invariants = [inv for inv in invariants if inv.lower() in valid]
            finfo = {
                "fd_type": fd_type,
                "ncomp": ncomp,
                "comps": comps,
                "invariants": invariants,
                "label": source_name if fname in contact_sources else label_map.get(fname, fname),
                "source_name": source_name,
            }
            field_outputs_available[fname] = finfo
            for ci, comp in enumerate(comps):
                entry_name = ("%s_%s" % (fname, comp)) if comp else fname
                lbl = ("%s (%s)" % (finfo["label"], comp)) if comp else finfo["label"]
                field_meta_list.append({
                    "name": entry_name,
                    "key": fname,
                    "component_index": ci,
                    "ncomp": ncomp,
                    "label": lbl,
                    "unit": _field_unit(source_name.split()[0], unit_system),
                    "association": 'contact' if fname in contact_sources else 'volume',
                    "source_field": source_name,
                })
            for inv in invariants:
                field_meta_list.append({
                    "name": "%s_%s" % (fname, inv),
                    "key": fname,
                    "component_index": -1,
                    "ncomp": 1,
                    "label": "%s (%s)" % (finfo["label"], inv),
                    "unit": _field_unit(fname, unit_system),
                })
            print("[VTK Export] Field '%s': type=%s, %d comp(s), "
                  "%d invariant(s)" % (fname, fd_type, ncomp, len(invariants)))

        # Process each frame
        frames_meta = []
        for fi, frame in enumerate(selected_frames):
            print("[VTK Export] Frame %d/%d (t=%s)..." %
                  (fi + 1, len(selected_frames), frame.frameValue))

            point_data = {}
            for fname, finfo in field_outputs_available.items():
                try:
                    fo = frame.fieldOutputs[finfo['source_name']]
                except Exception:
                    point_data[fname] = [float('nan')] * (num_nodes * finfo['ncomp'])
                    for inv in finfo['invariants']:
                        point_data[fname + '_' + inv] = [float('nan')] * num_nodes
                    continue
                fd_type = finfo["fd_type"]
                ncomp = finfo["ncomp"]
                invariants = finfo["invariants"]
                if fd_type == "nodal":
                    vals = _read_nodal_field(fo, node_map, num_nodes, ncomp)
                    point_data[fname] = vals
                else:
                    result = _read_elem_nodal_field(
                        fo, node_map, num_nodes, ncomp, invariants, section_point)
                    point_data[fname] = result["data"]
                    for inv, inv_vals in result["invariants"].items():
                        point_data["%s_%s" % (fname, inv)] = inv_vals

            # Deformation
            disp_data = None
            try:
                u_fo = frame.fieldOutputs["U"]
                disp_data = _read_nodal_field(u_fo, node_map, num_nodes, 3)
            except Exception:
                pass

            if disp_data is not None and not all(math.isfinite(v) for v in disp_data):
                raise ValueError("Displacement is missing on selected nodes; cannot deform geometry")
            if disp_data is not None and deformation_scale > 0:
                deformed_coords = [0.0] * (num_nodes * 3)
                for ni in range(num_nodes):
                    base = ni * 3
                    x, y, z = coords_list[ni]
                    deformed_coords[base] = x + disp_data[base] * deformation_scale
                    deformed_coords[base+1] = y + disp_data[base+1] * deformation_scale
                    deformed_coords[base+2] = z + disp_data[base+2] * deformation_scale
            else:
                deformed_coords = [c for pt in coords_list for c in pt]

            vtu_path = os.path.join(output_dir, "frame_%04d.vtu" % fi)
            _write_vtu_ascii(
                vtu_path,
                points=deformed_coords,
                elem_type_info=elem_type_info,
                num_nodes=num_nodes,
                point_data=point_data,
                field_outputs_available=field_outputs_available,
            )

            frame_field_ranges = {}
            for fname, vals in point_data.items():
                finite = [v for v in vals if math.isfinite(v)]
                frame_field_ranges[fname] = {"min": min(finite) if finite else None,
                                             "max": max(finite) if finite else None,
                                             "missing_count": len(vals) - len(finite)}
            frames_meta.append({
                "frame": fi,
                "source_frame": fi * frame_step,
                "time": frame.frameValue,
                "vtu_file": os.path.basename(vtu_path),
                "field_ranges": frame_field_ranges,
                "num_nodes": num_nodes,
                "num_cells": total_cells,
            })

        # Global field ranges
        global_field_ranges = {}
        for fname in field_outputs_available:
            all_mins = [fm["field_ranges"][fname]["min"]
                        for fm in frames_meta if fname in fm["field_ranges"] and fm["field_ranges"][fname]["min"] is not None]
            all_maxs = [fm["field_ranges"][fname]["max"]
                        for fm in frames_meta if fname in fm["field_ranges"] and fm["field_ranges"][fname]["min"] is not None]
            if all_mins:
                global_field_ranges[fname] = {"min": min(all_mins),
                                              "max": max(all_maxs)}

        # model.json
        model_info = {
            "format_version": "3.0",
            "export_time": datetime.now().isoformat(),
            "model_name": odb.name or os.path.basename(odb_path),
            "job_name": os.path.splitext(os.path.basename(odb_path))[0],
            "abaqus_version": str(getattr(odb, "odbVersion", "")),
            "odb_path": odb_path,
            "deformation_scale_factor": deformation_scale,
            "section_point": section_point,
            "averaging": {"position": "ELEMENT_NODAL", "method": "equal_contribution",
                          "invariants": "before_averaging", "across_regions": True},
            "geometry": "VTK standard connectivity; viewer linearizes high-order cells",
            "node_ids": [{"instance": key[0], "label": key[1]} for key in node_map],
            "num_nodes": num_nodes,
            "unit_system": unit_system,
            "bodies": bodies,
            "body_ids": body_ids,
            "missing_requested_fields": [f for f in fields if f not in field_outputs_available and
                                         not any(s.split()[0] == f for s in contact_sources.values())],
            "num_elements": total_cells,
            "element_types": {
                k: {"vtk_type": v["vtk_type"],
                    "count": len(v["connectivity"])}
                for k, v in elem_type_info.items()
            },
            "fields": field_meta_list,
            "field_ranges": global_field_ranges,
            "steps": [{"name": step.name, "label": step.name,
                       "procedure": step.procedure}],
            "frames": frames_meta,
        }
        model_path = os.path.join(output_dir, "model.json")
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(model_info, f, indent=2, ensure_ascii=False, allow_nan=False)

        if write_pvd:
            pvd_path = os.path.join(output_dir, "result.pvd")
            _write_pvd(pvd_path, output_dir, frames_meta)
            print("[VTK Export] PVD: %s" % pvd_path)

        print("[VTK Export] Done.  %d nodes, %d cells, %d frames." %
              (num_nodes, total_cells, len(selected_frames)))
        print("[VTK Export] Output: %s" % output_dir)
        print("[VTK Export] Index:  %s" % model_path)
        return model_path

    finally:
        if _need_close:
            odb.close()


def export_odb_to_vtk_main(argv=None):
    """CLI entry point."""
    if argv is None:
        argv = sys.argv
    import argparse
    parser = argparse.ArgumentParser(
        description="Export Abaqus ODB results to VTK (.vtu) format."
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
    parser.add_argument("--fields", nargs="*", default=DEFAULT_FIELDS,
                        help="Field output variables to export")
    parser.add_argument("--ascii", action="store_true",
                        help="Ignored -- output is always ASCII")
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
