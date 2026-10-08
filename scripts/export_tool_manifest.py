"""Generate the installed MCP schemas for review without touching the user's plugin."""
import asyncio
import json
import os
from pathlib import Path
import tempfile


async def main():
    with tempfile.TemporaryDirectory() as plugins:
        os.environ['ABAQUS_MCP_PLUGIN_DIR'] = plugins
        from abaqus_mcp_pro import server
        tools = await server.mcp.list_tools()
        prompts = await server.mcp.list_prompts()
        resources = await server.mcp.list_resources()
        output = Path(__file__).resolve().parents[1] / 'docs/reference/tool-manifest.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        data = {'version': server.mcp.version,
                'counts': {'tools': len(tools), 'prompts': len(prompts), 'resources': len(resources)},
                'tools': [t.model_dump(mode='json', exclude_none=True) for t in tools],
                'prompts': [p.model_dump(mode='json', exclude_none=True) for p in prompts],
                'resources': [r.model_dump(mode='json', exclude_none=True) for r in resources]}
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(data['counts']))


if __name__ == '__main__':
    asyncio.run(main())
