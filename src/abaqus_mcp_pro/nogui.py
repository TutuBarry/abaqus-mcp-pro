"""No-GUI tools for Abaqus MCP Pro -- subprocess-based execution.

Provides tools that run Abaqus via command-line subprocess (``abaqus python``
and ``abaqus cae noGUI=``) without requiring a live Abaqus/CAE GUI session.
This is the preferred mode for headless servers, CI/CD pipelines, and batch
processing where the Abaqus GUI is not available.

Reference: codex-abaqus-main (cite/codex-abaqus-main/.../runner.py)
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Abaqus command auto-detection
# ---------------------------------------------------------------------------


def _find_abaqus_command() -> str:
    from .commands import find_abaqus_command
    return find_abaqus_command()


ABAQUS_COMMAND = _find_abaqus_command()

SCRATCH_DIR = Path(os.environ.get("ABAQUS_MCP_SCRATCH", Path.home() / ".abaqus-mcp-pro" / "scratch"))
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT = int(os.environ.get("ABAQUS_MCP_NOGUI_TIMEOUT", "3600"))


# ---------------------------------------------------------------------------
# Core subprocess execution
# ---------------------------------------------------------------------------


def _run_abaqus_subprocess(
    args: list[str],
    timeout: float | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run an Abaqus subprocess command and return structured result."""
    cmd = [ABAQUS_COMMAND] + args
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    try:
        from .workflow import run_process
        with tempfile.TemporaryDirectory(prefix='abaqus-process-') as logs:
            log_path = Path(logs) / 'output.log'
            return_code = run_process(cmd, cwd or os.getcwd(), log_path, effective_timeout)
            with log_path.open('rb') as stream:
                stream.seek(max(0, log_path.stat().st_size - 15000))
                output = stream.read().decode('utf-8', errors='replace')
        launcher_error = next((line.strip() for line in output.splitlines()
                               if line.lstrip().lower().startswith('abaqus error:')), '')
        return {
            "ok": return_code == 0 and not launcher_error,
            "return_code": return_code,
            "stdout": output[-10000:],
            "stderr": "",
            "command": " ".join(cmd),
            **({'error': launcher_error} if launcher_error else {}),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "ok": False,
            "return_code": -1,
            "stdout": stdout[-10000:],
            "stderr": f"Timeout after {effective_timeout}s\n" + stderr[-5000:],
            "command": " ".join(cmd),
            "error": f"Command timed out after {effective_timeout}s",
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "return_code": -1,
            "stdout": "",
            "stderr": f"Abaqus command not found: {ABAQUS_COMMAND}\n"
                       "Set ABAQUS_COMMAND environment variable to the correct path.",
            "command": " ".join(cmd),
            "error": f"Abaqus command not found: {ABAQUS_COMMAND}",
        }
# ---------------------------------------------------------------------------
# Core subprocess execution helpers
# ---------------------------------------------------------------------------
def _run_abaqus_python(script, timeout=None, cwd=None):
    script_path = SCRATCH_DIR / ("_mcp_script_%s.py" % uuid.uuid4().hex)
    script_path.write_text(script, encoding="utf-8")
    try:
        return _run_abaqus_subprocess(["python", str(script_path)], timeout=timeout, cwd=cwd)
    finally:
        try: script_path.unlink(missing_ok=True)
        except OSError: pass


def _run_abaqus_cae(script, timeout=None, cwd=None):
    script_path = SCRATCH_DIR / ("_mcp_cae_script_%s.py" % uuid.uuid4().hex)
    script_path.write_text(script, encoding="utf-8")
    try:
        return _run_abaqus_subprocess(["cae", "noGUI=%s" % script_path], timeout=timeout, cwd=cwd)
    finally:
        try: script_path.unlink(missing_ok=True)
        except OSError: pass


async def run_python_no_gui(code, timeout=None, cwd=""):
    if not code.strip():
        raise ValueError("code must not be empty")
    import anyio
    wd = cwd.strip() if cwd.strip() else None
    return await anyio.to_thread.run_sync(_run_abaqus_python, code, timeout, wd)


async def abaqus_cae_no_gui(code, timeout=None, cwd=""):
    if not code.strip():
        raise ValueError("code must not be empty")
    import anyio
    wd = cwd.strip() if cwd.strip() else None
    return await anyio.to_thread.run_sync(_run_abaqus_cae, code, timeout, wd)


async def submit_job_no_gui(
    input_file, job_name="", cpus=4, double=False, user_subroutine="",
    wait=True, timeout=None, cwd="", view_result=True, unit_system="",
):
    import anyio
    inp_path = Path(input_file)
    if not inp_path.is_absolute():
        wd = Path(cwd) if cwd else Path.cwd()
        inp_path = wd / inp_path
    if not inp_path.exists():
        return {"ok": False, "error": "Input file not found: %s" % inp_path}

    job = job_name.strip() or inp_path.stem
    import re
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', job):
        raise ValueError('job_name must start with a letter and contain no spaces')
    if type(cpus) is not int or cpus < 1:
        raise ValueError("cpus must be a positive integer")
    wd = str(Path(cwd.strip()).resolve()) if cwd.strip() else str(inp_path.parent.resolve())
    input_argument = os.path.relpath(inp_path.resolve(), wd)
    if any(c.isspace() for c in input_argument):
        import shutil
        input_argument = '_mcp_input_' + uuid.uuid4().hex + '.inp'
        shutil.copyfile(inp_path, Path(wd) / input_argument)
    args = ["job=%s" % job, "input=%s" % input_argument, "cpus=%d" % cpus]
    if double: args.append("double")
    if user_subroutine.strip(): args.append("user=%s" % user_subroutine.strip())
    if wait: args.append("interactive")

    result = await anyio.to_thread.run_sync(_run_abaqus_subprocess, args, timeout, wd)

    output_files = {}
    for ext in (".odb", ".dat", ".msg", ".sta", ".log", ".prt", ".com"):
        p = Path(wd) / ("%s%s" % (job, ext))
        if p.exists():
            output_files[ext.lstrip(".")] = str(p)

    result["job_name"] = job
    result["output_files"] = output_files
    if not result.get("ok"):
        result["status"] = "failed"
    elif not wait:
        result["status"] = "submitted"
    else:
        state = await check_job_status(job, wd)
        result["status"] = state["status"]
        result["ok"] = state["status"] == "completed"
        if result['ok'] and view_result:
            from .viewer_bridge import publish_result
            try:
                result['viewer'] = await anyio.to_thread.run_sync(publish_result, output_files['odb'], unit_system)
            except Exception as exc:
                result['viewer'] = {'status': 'failed', 'error': str(exc)}
    return result


async def check_job_status(job_name, workdir=""):
    import anyio
    def _check():
        wd = Path(workdir) if workdir.strip() else Path.cwd()
        sta_path = wd / ("%s.sta" % job_name)
        log_path = wd / ("%s.log" % job_name)
        msg_path = wd / ("%s.msg" % job_name)
        odb_path = wd / ("%s.odb" % job_name)

        status = "unknown"
        errors, warnings = [], []

        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            if "ABAQUS JOB COMPLETED" in log_text:
                status = "completed"
            elif "ABAQUS ERROR" in log_text:
                status = "error"
                for line in log_text.splitlines():
                    if "ERROR" in line.upper():
                        errors.append(line.strip())
            elif "ABAQUS JOB ABORTED" in log_text:
                status = "aborted"

        if msg_path.exists():
            msg_text = msg_path.read_text(encoding="utf-8", errors="replace")
            for line in msg_text.splitlines():
                if "WARNING" in line.upper():
                    warnings.append(line.strip())

        progress = None
        if sta_path.exists():
            sta_text = sta_path.read_text(encoding="utf-8", errors="replace")
            if "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in sta_text.upper():
                status = "completed"
            elif "THE ANALYSIS HAS NOT BEEN COMPLETED" in sta_text.upper():
                status = "aborted"
            lines = sta_text.strip().splitlines()
            if lines:
                progress = lines[-1].strip()

        return {
            "job_name": job_name, "status": status,
            "odb_exists": odb_path.exists(),
            "odb_path": str(odb_path) if odb_path.exists() else None,
            "progress": progress,
            "errors": errors[-10:] if errors else [],
            "warnings": warnings[-10:] if warnings else [],
        }
    return await anyio.to_thread.run_sync(_check)


async def get_abaqus_command_path():
    return __import__("json").dumps({
        "abaqus_command": ABAQUS_COMMAND,
        "scratch_dir": str(SCRATCH_DIR),
        "default_timeout": DEFAULT_TIMEOUT,
        "platform": platform.system(),
    }, indent=2)
