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
