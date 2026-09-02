import os

base = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\src\abaqus_mcp_pro"
with open(os.path.join(base, "server.py"), "r", encoding="utf-8") as f:
    content = f.read()

# Find section boundaries
res_start = content.find('\n@mcp.resource("abaqus://session-telemetry"')
prompt_start = content.find('\n@mcp.prompt()')
skills_start = content.find('\ndef _collect_skill_files')

print(f"res_start: {res_start} (line {content[:res_start].count(chr(10))+1})")
print(f"prompt_start: {prompt_start} (line {content[:prompt_start].count(chr(10))+1})")
print(f"skills_start: {skills_start} (line {content[:skills_start].count(chr(10))+1})")

# Write tools.py
tools_content = content[content.find("@mcp.tool()"):res_start]
with open(os.path.join(base, "tools.py"), "w", encoding="utf-8") as f:
    f.write('"""MCP tool definitions for Abaqus MCP server."""\n\n')
    f.write('from __future__ import annotations\n\n')
    f.write('import json\n')
    f.write('import os\n')
    f.write('from typing import Any\n')
    f.write('from collections import defaultdict\n\n')
    f.write('from .transport import _bridge_request, _exec, DEFAULT_HOST, DEFAULT_PORT\n')
    f.write('from .solver_diagnosis import DIAGNOSE_IN_ABAQUS_CODE, DiagnosisReport, DiagnosticEvent\n')
    f.write('from .odb_lens import KPI_LENS_CODE, KPILensReport, KPIResult\n')
    f.write('from .capsule import CapsuleEntry, CapsuleStore, CAPSULE_CAPTURE_CODE, format_capsule_markdown, format_capsule_list_markdown, diff_capsules\n')
    f.write('from .contracts import check_contracts, format_contracts_markdown, format_contracts_compact\n')
    f.write('from .report import SimulationReport, format_report_markdown, build_report, save_report\n\n\n')
    f.write(tools_content)
print(f"tools.py: {len(tools_content)} chars")

# Write resources.py
res_content = content[res_start+1:prompt_start]
with open(os.path.join(base, "resources.py"), "w", encoding="utf-8") as f:
    f.write('"""MCP resource definitions for Abaqus MCP server."""\n\n')
    f.write('from __future__ import annotations\n\n')
    f.write('import json\n')
    f.write('from typing import Any\n\n')
    f.write('from .transport import DEFAULT_HOST, DEFAULT_PORT, _bridge_request\n\n\n')
    f.write(res_content)
print(f"resources.py: {len(res_content)} chars")

# Write prompts.py
prompt_content = content[prompt_start+1:skills_start]
with open(os.path.join(base, "prompts.py"), "w", encoding="utf-8") as f:
    f.write('"""MCP prompt definitions for Abaqus MCP server."""\n\n')
    f.write('from __future__ import annotations\n\n')
    f.write('from mcp.types import PromptMessage, TextContent, GetPromptResult\n\n\n')
    f.write(prompt_content)
print(f"prompts.py: {len(prompt_content)} chars")

# Write skills.py (skills registration + main)
skills_main_content = content[skills_start+1:]
skills_main_content = skills_main_content.replace('if __name__ == "__main__":\n    main()', "")
with open(os.path.join(base, "skills.py"), "w", encoding="utf-8") as f:
    f.write('"""Skills registration for Abaqus MCP server."""\n\n')
    f.write('from __future__ import annotations\n\n')
    f.write('import os as _os\n')
    f.write('import re as _re\n\n\n')
    f.write(skills_main_content)
print(f"skills.py: {len(skills_main_content)} chars")

print("Done!")
