"""Run the connect_abaqus acceptance flow through a fresh MCP stdio session."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    read_timeout_seconds: float,
) -> dict[str, Any]:
    result = await session.call_tool(
        name,
        arguments,
        read_timeout_seconds=read_timeout_seconds,
    )
    if getattr(result, "is_error", False):
        raise RuntimeError(f"{name} failed: {result.model_dump_json(indent=2)}")
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", None) or []
    if content and getattr(content[0], "text", None):
        return json.loads(content[0].text)
    raise RuntimeError(f"{name} returned no structured result")


async def _run_once(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    if args.abaqus_command:
        env["ABAQUS_COMMAND"] = args.abaqus_command

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "abaqus_mcp_pro.server"],
        cwd=str(root),
        env=env,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            first = await _call_tool(
                session,
                "connect_abaqus",
                {"cwd": args.cwd or str(root), "timeout": args.timeout},
                args.timeout + 20,
            )
            second = await _call_tool(
                session,
                "connect_abaqus",
                {"cwd": args.cwd or str(root), "timeout": args.timeout},
                args.timeout + 20,
            )
            ping = await _call_tool(session, "ping", {"timeout": 5}, 10)
            report = {
                "first_connect": first,
                "second_connect": second,
                "ping": ping,
                "passed": (
                    first.get("ok") is True
                    and second.get("status") == "bridge_ready"
                    and ping.get("capabilities", {}).get("backend") == "gui"
                ),
            }
            return report


def _write_report(path: Path, report: dict[str, Any]) -> Path:
    output = path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    report = await _run_once(args)
    output = _write_report(Path(args.output), report)
    print(json.dumps({"output": str(output), **report}, ensure_ascii=False), flush=True)
    if args.keep_alive > 0:
        print("ACCEPTANCE_SESSION_ALIVE", flush=True)
        await asyncio.sleep(args.keep_alive)
    return report


async def _run_repeated(args: argparse.Namespace) -> dict[str, Any]:
    requested_output = Path(args.output)
    results: list[dict[str, Any]] = []
    for index in range(1, args.runs + 1):
        started = time.monotonic()
        report = await _run_once(args)
        duration = round(time.monotonic() - started, 3)
        suffix = requested_output.suffix or ".json"
        stem = requested_output.stem if requested_output.suffix else requested_output.name
        run_path = requested_output.with_name(f"{stem}.run-{index:02d}{suffix}")
        output = _write_report(run_path, report)
        results.append(
            {
                "run": index,
                "passed": report["passed"],
                "duration_seconds": duration,
                "first_status": report["first_connect"].get("status"),
                "second_status": report["second_connect"].get("status"),
                "ping_backend": report["ping"].get("capabilities", {}).get("backend"),
                "abaqus_version": report["ping"].get("abaqus_version"),
                "evidence": str(output),
            }
        )
        print(
            json.dumps(
                {
                    "run": index,
                    "runs": args.runs,
                    "passed": report["passed"],
                    "duration_seconds": duration,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    passed_runs = sum(1 for item in results if item["passed"])
    summary = {
        "runs": args.runs,
        "passed_runs": passed_runs,
        "failed_runs": args.runs - passed_runs,
        "passed": passed_runs == args.runs,
        "scope": "Each run starts a fresh MCP stdio process against the live GUI bridge.",
        "results": results,
    }
    output = _write_report(requested_output, summary)
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--keep-alive", type=float, default=0.0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--abaqus-command", default="")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.runs > 1 and args.keep_alive > 0:
        parser.error("--keep-alive is only supported with a single run")
    result = asyncio.run(_run_repeated(args) if args.runs > 1 else _run(args))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
