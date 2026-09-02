import sys
from pathlib import Path

file_path = Path(r'R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\src\abaqus_mcp_pro\silent_failures.py')
content = file_path.read_text(encoding='utf-8')

# Find the exact text to replace
old_text = (
    '             \"No known risky element types detected.\",\n'
    '             evidence={\"risky_count\": 0})\n'
    '\n'
    '    # ---------- 6. Job / Output ----------'
)

new_text = (
    '             \"No known risky element types detected.\",\n'
    '             evidence={\"risky_count\": 0})\n'
    '\n'
    '    # Check for element configurations known to produce bad results\n'
    '    for itype in elem_types:\n'
    '        if \"C3D8\" in itype and \"C3D8R\" not in itype and \"C3D8I\" not in itype:\n'
    '            _add(\"element_quality\", \"warning\", \"element_c3d8_locking\", False,\n'
    '                 f\"Element type \'{itype}\' is fully integrated hex. \"\n'
    '                 \"In large-deformation (bending-dominated) problems, \"\n'
    '                 \"C3D8 may suffer from volumetric locking. \"\n'
    '                 \"Consider switching to C3D8R (reduced integration) or \"\n'
    '                 \"C3D8I (incompatible modes).\",\n'
    '                 \"Switch to C3D8R for general use, or C3D8I for \"\n'
    '                 \"bending-dominated problems.\",\n'
    '                 {\"element_type\": itype})\n'
    '        if \"C3D4\" in itype and \"C3D10\" not in itype:\n'
    '            _add(\"element_quality\", \"warning\", \"element_c3d4_stiff\", False,\n'
    '                 f\"Element type \'{itype}\' is linear tetrahedral. \"\n'
    '                 \"C3D4 elements are known to be overly stiff and should \"\n'
    '                 \"only be used for non-critical fill regions. \"\n'
    '                 \"Consider C3D10 (quadratic tet) for accuracy.\",\n'
    '                 \"Switch to C3D10 for structural regions; use C3D4 only \"\n'
    '                 \"for fill/transition zones.\",\n'
    '                 {\"element_type\": itype})\n'
    '\n'
    '    # Check for suspiciously low element counts\n'
    '    for part_name, part in parts.items():\n'
    '        for instance_name, instance in instances.items():\n'
    '            if part_name in instance_name:\n'
    '                cells = part.get(\"cells\", 0)\n'
    '                elements = instance.get(\"elements\", 0)\n'
    '                if cells > 0 and elements > 0:\n'
    '                    ratio = elements / cells\n'
    '                    if ratio < 4:\n'
    '                        _add(\"element_quality\", \"warning\", \"element_low_density\", False,\n'
    '                             f\"Instance \'{instance_name}\' has only {elements} elements \"\n'
    '                             f\"for {cells} cells (ratio {ratio:.1f}). \"\n'
    '                             \"This may mean only 1 element through the thickness, \"\n'
    '                             \"which is insufficient for bending.\",\n'
    '                             \"Refine mesh to have at least 4 elements through \"\n'
    '                             \"the thickness in bending-dominated regions.\",\n'
    '                             {\"instance\": instance_name, \"elements\": elements,\n'
    '                              \"cells\": cells, \"ratio\": ratio})\n'
    '\n'
    '    # ---------- 6. Job / Output ----------'
)

if old_text in content:
    content = content.replace(old_text, new_text)
    file_path.write_text(content, encoding='utf-8')
    print('Successfully inserted element_quality extensions')
else:
    print('ERROR: Could not find old_text in file')
    idx = content.find('element_types_ok')
    if idx != -1:
        print(f'Found at position: {idx}')
        snippet = content[idx:idx+300]
        print(repr(snippet))
