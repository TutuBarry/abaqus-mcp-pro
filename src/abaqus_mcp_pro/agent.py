"""Abaqus-side socket agent.

This file intentionally uses only the Python standard library so it can run
inside Abaqus 2024's bundled Python 3.10 without installing project deps there.
"""

from __future__ import annotations

import ast
import os
import hmac
import hashlib
import time
from collections import OrderedDict
from .protocol import read_message
import contextlib
import difflib
import io
import inspect
import json
import platform
import re
import socketserver
import sys
import threading
import traceback
from typing import Any

DEFAULT_HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))

_GLOBALS: dict[str, Any] = {
    "__name__": "__ABAQUS_MCP_exec__",
    "__doc__": None,
}
_EXEC_LOCK = threading.RLock()
# ── Optional auth token (set via env ABAQUS_MCP_TOKEN) ──
_AUTH_TOKEN: str | None = None
import os as _os
_ENV_TOKEN = _os.environ.get("ABAQUS_MCP_TOKEN")
if _ENV_TOKEN:
    _AUTH_TOKEN = _ENV_TOKEN

# ── ODB session management ──
_OPEN_ODBS: dict[str, Any] = {}  # handle -> odb object
_ODB_HANDLE_COUNTER = 0
_ODB_LOCK = threading.Lock()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return {
            "repr": repr(value),
            "type": f"{type(value).__module__}.{type(value).__name__}",
        }


def _node_source(node: ast.AST) -> str | None:
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _key_literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Index):  # pragma: no cover - compatibility for older ASTs
        return _key_literal(node.value)
    return None


def _extract_tb_lineno(exc: BaseException) -> int | None:
    """Extract the line number where the exception was raised from its traceback."""
    if hasattr(exc, "lineno") and getattr(exc, "lineno") is not None:
        return getattr(exc, "lineno")
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<abaqus-mcp-pro>":
            return tb.tb_lineno
        tb = tb.tb_next
    return None


def _find_subscript_parent(code: str, missing_key: Any, lineno: int | None = None) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    candidates: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _key_literal(node.slice) == missing_key:
            src = _node_source(node.value)
            if src is not None:
                candidates.append((getattr(node, "lineno", 0), src))
    # Fallback: if no candidates and lineno is provided, match any Subscript on the failed line
    if not candidates and lineno is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                node_lineno = getattr(node, "lineno", None)
                if node_lineno == lineno:
                    src = _node_source(node.value)
                    if src is not None:
                        candidates.append((node_lineno, src))
    if not candidates:
        return None
    if lineno is not None:
        candidates.sort(key=lambda c: abs(c[0] - lineno))
    return candidates[0][1]


def _find_attribute_parent(code: str, missing_attr: str) -> str | None:
    """Find the object that was expected to have *missing_attr* via AST analysis."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == missing_attr:
            return _node_source(node.value)
    return None


def _extract_func_name(exc: BaseException) -> str | None:
    """Extract function/method name from a TypeError message."""
    msg = str(exc)
    m = re.search(r"([\w.]+)\(\)", msg)
    if m:
        return m.group(1)
    m = re.search(r"'([\w.]+)'", msg)
    if m:
        return m.group(1)
    return None


def _extract_code_excerpt(code: str, lineno: int | None, radius: int = 2) -> str | None:
    if lineno is None or lineno < 1:
        return None
    lines = code.splitlines()
    if not lines:
        return None
    index = max(0, lineno - 1)
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    excerpt_lines: list[str] = []
    for i in range(start, end):
        prefix = ">>" if i == index else "  "
        excerpt_lines.append("%s %4d | %s" % (prefix, i + 1, lines[i]))
    return "\n".join(excerpt_lines)


def _resolve_simple_expr(expr: str, namespace: dict[str, Any]) -> Any:
    """Resolve simple name/attribute/subscript expressions without executing calls."""

    def _eval_node(node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            return namespace[node.id]
        if isinstance(node, ast.Attribute):
            return getattr(_eval_node(node.value), node.attr)
        if isinstance(node, ast.Subscript):
            base = _eval_node(node.value)
            try:
                key = ast.literal_eval(node.slice)
            except Exception:
                if isinstance(node.slice, ast.Name):
                    key = namespace[node.slice.id]
                elif isinstance(node.slice, ast.Index):  # pragma: no cover - compatibility for older ASTs
                    if isinstance(node.slice.value, ast.Constant):
                        key = node.slice.value.value
                    elif isinstance(node.slice.value, ast.Name):
                        key = namespace[node.slice.value.id]
                    else:
                        raise
                else:
                    raise
            return base[key]
        raise ValueError("unsupported expression node")

    parsed = ast.parse(expr, mode="eval")
    return _eval_node(parsed.body)


def _extract_params_from_sig(sig_str: str) -> list[str]:
    m = re.search(r"\((.*)\)", sig_str)
    if not m:
        return []
    content = m.group(1)
    params: list[str] = []
    paren_depth = 0
    current_param: list[str] = []
    for char in content:
        if char in "([{":
            paren_depth += 1
            current_param.append(char)
        elif char in ")]}":
            paren_depth -= 1
            current_param.append(char)
        elif char == "," and paren_depth == 0:
            params.append("".join(current_param).strip())
            current_param = []
        else:
            current_param.append(char)
    if current_param:
        params.append("".join(current_param).strip())

    names: list[str] = []
    for p in params:
        if not p:
            continue
        word = re.match(r"^([a-zA-Z_]\w*)", p)
        if word:
            name = word.group(1)
            if name not in ("self", "args", "kwargs"):
                names.append(name)
    return names


def _extract_invalid_keyword(msg: str) -> str | None:
    m1 = re.search(r"got an unexpected keyword argument ['\"](\w+)['\"]", msg)
    if m1:
        return m1.group(1)
    m2 = re.search(r"keyword error on (\w+)", msg)
    if m2:
        return m2.group(1)
    return None


def _extract_call_target(code: str, lineno: int | None) -> str | None:
    if lineno is None:
        return None
    try:
        tree = ast.parse(code)
    except Exception:
        try:
            lines = code.splitlines()
            if lineno - 1 < 0 or lineno - 1 >= len(lines):
                return None
            tree = ast.parse(lines[lineno - 1], mode="exec")
        except Exception:
            return None

    candidates: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", start)
            if start is not None and end is not None:
                if start <= lineno <= end:
                    candidates.append(node)
            elif start == lineno:
                candidates.append(node)

    if not candidates:
        return None

    candidates.sort(key=lambda n: getattr(n, "end_lineno", getattr(n, "lineno", 0)) - getattr(n, "lineno", 0))
    return _node_source(candidates[0].func)


def _summarize_mapping_keys(mapping_obj: Any, missing_key: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available_keys_sample": [],
        "possible_keys": [],
    }
    keys_method = getattr(mapping_obj, "keys", None)
    if not callable(keys_method):
        return result
    try:
        scanned_keys = list(keys_method())
    except Exception:
        return result

    key_texts = [str(k) for k in scanned_keys]
    result["available_keys_sample"] = key_texts

    if missing_key is not None:
        try:
            near = difflib.get_close_matches(str(missing_key), key_texts, n=8, cutoff=0.45)
            result["possible_keys"] = near
        except Exception:
            pass
    return result


def _summarize_object_members(obj: Any, missing_attr: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "possible_members": [],
    }
    try:
        members = sorted([name for name in dir(obj) if not name.startswith("_")])
    except Exception:
        return result

    if missing_attr:
        try:
            result["possible_members"] = difflib.get_close_matches(missing_attr, members, n=10, cutoff=0.45)
        except Exception:
            pass
    return result


def _extract_signature_from_docstring(doc: str, target_name: str) -> str | None:
    """Search the docstring for target_name(...) and balance parentheses to handle multiline signatures."""
    pattern = r"\b" + re.escape(target_name) + r"\s*\("
    match = re.search(pattern, doc)
    if not match:
        return None
    start_pos = match.start()
    open_paren_idx = match.end() - 1
    paren_count = 0
    end_pos = -1
    for i in range(open_paren_idx, min(open_paren_idx + 1000, len(doc))):
        char = doc[i]
        if char == "(":
            paren_count += 1
        elif char == ")":
            paren_count -= 1
            if paren_count == 0:
                end_pos = i + 1
                break
    if end_pos != -1:
        sig_candidate = doc[start_pos:end_pos]
        return " ".join(sig_candidate.split())
    return None


def _summarize_callable(target_expr: str | None, namespace: dict[str, Any], invalid_keyword: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "call_target": target_expr,
        "callable_signature": None,
        "callable_summary": None,
    }
    if not target_expr:
        return summary
    try:
        target = _resolve_simple_expr(target_expr, namespace)
    except Exception:
        return summary

    target_name = getattr(target, "__name__", "function")
    try:
        sig = inspect.signature(target)
        sig_str = f"{target_name}{sig}"
    except Exception:
        sig_str = f"{target_name}(...)"

    doc = None
    try:
        doc = inspect.getdoc(target)
    except Exception:
        pass
    if not doc:
        try:
            doc = getattr(target, "__doc__", None)
        except Exception:
            pass

    if doc:
        try:
            lines = doc.strip().splitlines()
            if lines:
                first_line = lines[0].strip()
                if " -> " in first_line:
                    first_line = first_line.split(" -> ", 1)[1].strip()
                summary["callable_summary"] = first_line if first_line else None
            if sig_str.endswith("(...)"):
                extracted_sig = _extract_signature_from_docstring(doc, target_name)
                if extracted_sig:
                    sig_str = extracted_sig
        except Exception:
            pass

    if len(sig_str) > 1000:
        sig_str = sig_str[:997] + "..."
    summary["callable_signature"] = sig_str

    if invalid_keyword:
        try:
            valid_params = []
            try:
                sig = inspect.signature(target)
                valid_params = [p.name for p in sig.parameters.values() if p.name not in ("self", "args", "kwargs")]
            except Exception:
                pass
            if not valid_params:
                valid_params = _extract_params_from_sig(sig_str)
            if valid_params:
                matches = difflib.get_close_matches(invalid_keyword, valid_params, n=5, cutoff=0.5)
                if matches:
                    summary["possible_keywords"] = matches
        except Exception:
            pass

    return summary


def _format_execution_error(code: str, exc: BaseException, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    tb_str = traceback.format_exc()
    tb_lines = [l for l in tb_str.strip().splitlines() if l.strip()]
    core_error = tb_lines[-1] if tb_lines else str(exc)
    exc_type_name = type(exc).__name__
    error_type = f"{type(exc).__module__}.{exc_type_name}"
    lineno = _extract_tb_lineno(exc)
    code_excerpt = _extract_code_excerpt(code, lineno)
    traceback_tail = tb_lines[-5:] if len(tb_lines) > 5 else tb_lines

    is_key_error = isinstance(exc, KeyError) or exc_type_name.endswith("KeyError")
    is_attribute_error = isinstance(exc, AttributeError) or exc_type_name.endswith("AttributeError")
    is_name_error = exc_type_name == "NameError"
    is_type_error = isinstance(exc, TypeError) or exc_type_name.endswith("TypeError")
    is_syntax_error = isinstance(exc, SyntaxError) or exc_type_name.endswith("SyntaxError")

    detected_missing_key = None
    detected_parent_path = None
    if namespace is not None and lineno is not None:
        try:
            lines = code.splitlines()
            if 0 <= lineno - 1 < len(lines):
                line_code = lines[lineno - 1]
                tree = ast.parse(line_code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Subscript):
                        val_key = None
                        if isinstance(node.slice, ast.Constant):
                            val_key = node.slice.value
                        elif isinstance(node.slice, ast.Name):
                            val_key = namespace.get(node.slice.id)
                        elif isinstance(node.slice, ast.Index):  # pragma: no cover - compatibility for older ASTs
                            if isinstance(node.slice.value, ast.Constant):
                                val_key = node.slice.value.value
                            elif isinstance(node.slice.value, ast.Name):
                                val_key = namespace.get(node.slice.value.id)
                        
                        if val_key is not None:
                            p_path = _node_source(node.value)
                            if p_path:
                                try:
                                    p_obj = _resolve_simple_expr(p_path, namespace)
                                    keys_method = getattr(p_obj, "keys", None)
                                    if callable(keys_method):
                                        try:
                                            try:
                                                keys_list = list(keys_method())
                                                is_missing = val_key not in keys_list
                                            except Exception:
                                                is_missing = val_key not in p_obj
                                            if is_missing:
                                                is_key_error = True
                                                detected_missing_key = val_key
                                                detected_parent_path = p_path
                                                break
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
        except Exception:
            pass

    if is_key_error:
        missing_key = detected_missing_key if detected_missing_key is not None else (exc.args[0] if exc.args else None)
        parent_path = detected_parent_path if detected_parent_path is not None else _find_subscript_parent(code, missing_key, lineno)
        recovery: dict[str, Any] = {
            "missing_key": _jsonable(missing_key),
            "parent_object_path": parent_path,
        }
        if parent_path and namespace is not None:
            try:
                parent_obj = _resolve_simple_expr(parent_path, namespace)
                recovery.update(_summarize_mapping_keys(parent_obj, missing_key))
            except Exception:
                pass
    elif is_attribute_error:
        missing_attr = getattr(exc, "name", None)
        source_obj = getattr(exc, "obj", None)
        object_type = type(source_obj).__name__ if source_obj is not None else None
        parent_path = _find_attribute_parent(code, missing_attr) if missing_attr else None
        recovery = {
            "missing_attribute": missing_attr,
            "object_type": object_type,
            "parent_object_path": parent_path,
        }
        if source_obj is not None:
            try:
                recovery.update(_summarize_object_members(source_obj, missing_attr))
            except Exception:
                pass
    elif is_name_error:
        missing_var = getattr(exc, "name", None)
        if not missing_var:
            m = re.search(r"name '(\w+)' is not defined", str(exc))
            if m:
                missing_var = m.group(1)
        recovery = {"missing_variable": missing_var}
        abaqus_modules = {
            "mesh", "part", "material", "assembly", "step", "interaction", 
            "load", "section", "sketch", "job", "connector", "visualization", 
            "xyPlot", "displayGroup", "meshEdit", "connectorBehavior", "symbolicConstants"
        }
        if missing_var in abaqus_modules:
            recovery["import_suggestion"] = f"from abaqus import {missing_var}"
        elif missing_var == "C":
            recovery["import_suggestion"] = "from abaqusConstants import *"
        elif missing_var and missing_var.isupper() and len(missing_var) > 1:
            recovery["import_suggestion"] = "from abaqusConstants import *"
    elif is_syntax_error:
        recovery = {
            "syntax_line": getattr(exc, "lineno", None),
            "syntax_offset": getattr(exc, "offset", None),
            "syntax_text": getattr(exc, "text", None),
        }
    elif is_type_error:
        call_target = _extract_call_target(code, lineno)
        invalid_kw = _extract_invalid_keyword(core_error)
        recovery = {"call_target": call_target}
        if namespace is not None:
            recovery.update(_summarize_callable(call_target, namespace, invalid_kw))
    else:
        recovery = {}

    # Fallback: if no recovery hints, try to reflect the call target
    if not recovery and namespace is not None:
        call_target = _extract_call_target(code, lineno)
        if call_target:
            recovery = _summarize_callable(call_target, namespace)

    return {
        "ok": False,
        "core_error": core_error,
        "error_type": error_type,
        "error_line": lineno,
        "code_excerpt": code_excerpt,
        "traceback_tail": traceback_tail,
        "recovery": recovery,
    }


def _read_message(request):
    request.request.settimeout(float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60")))
    return read_message(request.request, int(os.environ.get("ABAQUS_MCP_MAX_MESSAGE_BYTES", 32 * 1024 * 1024)))


def _send_message(request: socketserver.BaseRequestHandler, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request.request.sendall(data + b"\n")


_MAX_OUTPUT = 100_000


_READ_LOCK = _EXEC_LOCK

def _execute(code: str, read_only: bool = False) -> dict[str, Any]:
    """Execute Python code in Abaqus kernel.

    All access is serialized because kernel objects and stdout are shared.
    read_only is retained for API compatibility; it does not permit concurrency.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()
    namespace = _GLOBALS
    returned = None
    error_response = None

    try:
        from abaqus import mdb, session  # type: ignore
    except Exception:
        pass
    else:
        namespace.update({"mdb": mdb, "session": session})

    lock = _EXEC_LOCK  # Kernel objects and stdout are shared, including read requests.

    with lock, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        namespace.pop("result", None)
        try:
            try:
                parsed = ast.parse(code, mode="eval")
            except SyntaxError:
                parsed = ast.parse(code, mode="exec")
                compiled = compile(parsed, "<abaqus-mcp-pro>", "exec")
                exec(compiled, namespace, namespace)
                returned = namespace.get("result")
            else:
                compiled = compile(parsed, "<abaqus-mcp-pro>", "eval")
                returned = eval(compiled, namespace, namespace)
        except Exception as exc:
            error_response = _format_execution_error(code, exc, namespace)

    captured_stdout = stdout.getvalue()
    captured_stderr = stderr.getvalue()
    if len(captured_stdout) > _MAX_OUTPUT:
        captured_stdout = captured_stdout[:_MAX_OUTPUT] + "\n... (truncated, total %d chars)" % len(captured_stdout)
    if len(captured_stderr) > _MAX_OUTPUT:
        captured_stderr = captured_stderr[:_MAX_OUTPUT] + "\n... (truncated, total %d chars)" % len(captured_stderr)

    if error_response is not None:
        error_response["stdout"] = captured_stdout
        error_response["stderr"] = captured_stderr
        return error_response

    return {
        "ok": True,
        "return_value": _jsonable(returned),
        "stdout": captured_stdout,
        "stderr": captured_stderr,
    }


def _ping() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "thread": threading.current_thread().name,
        "open_odbs": list(_OPEN_ODBS.keys()),
        "globals_size": len(_GLOBALS),
    }
    # Try to get Abaqus-specific info without importing if not available
    try:
        from abaqus import mdb, session  # type: ignore
        info["models"] = list(mdb.models.keys())
        info["viewports"] = list(session.viewports.keys()) if hasattr(session, "viewports") else []
        info["jobs"] = list(mdb.jobs.keys())
        # Try to get Abaqus version
        try:
            import abaqus
            info["abaqus_version"] = getattr(abaqus, "version", "unknown")
        except Exception:
            pass
    except ImportError:
        pass
    return info



# ── Structured Bridge API ──

def _generate_odb_handle() -> str:
    global _ODB_HANDLE_COUNTER
    with _ODB_LOCK:
        _ODB_HANDLE_COUNTER += 1
        return f"odb_{_ODB_HANDLE_COUNTER:04d}"


def _odb_open(params: dict[str, Any]) -> dict[str, Any]:
    """Open an ODB file and return a handle with summary metadata."""
    path = params.get("path", "")
    read_only = params.get("read_only", True)
    if not path:
        raise ValueError("params.path is required")
    from odbAccess import openOdb  # type: ignore
    odb = openOdb(path=path, readOnly=read_only)
    handle = _generate_odb_handle()
    with _ODB_LOCK:
        _OPEN_ODBS[handle] = odb
    # Build summary
    steps_info = []
    for sname, step in odb.steps.items():
        frames_info = []
        for fi, frame in enumerate(step.frames):
            fields = list(frame.fieldOutputs.keys()) if hasattr(frame, "fieldOutputs") else []
            frames_info.append({"index": fi, "time": float(frame.frameValue), "fields": fields})
        steps_info.append({"name": sname, "procedure": str(getattr(step, "procedure", "")), "frames": frames_info})
    instance_names = list(odb.rootAssembly.instances.keys()) if hasattr(odb.rootAssembly, "instances") else []
    return {
        "handle": handle,
        "path": path,
        "read_only": read_only,
        "steps": steps_info,
        "instances": instance_names,
        "node_count": sum(len(inst.nodes) for inst_name, inst in odb.rootAssembly.instances.items()),
        "element_count": sum(len(inst.elements) for inst_name, inst in odb.rootAssembly.instances.items()),
    }


def _odb_close(params: dict[str, Any]) -> dict[str, Any]:
    """Close an open ODB by handle or path."""
    handle = params.get("handle", "")
    path = params.get("path", "")
    closed = []
    with _ODB_LOCK:
        if handle:
            if handle in _OPEN_ODBS:
                try:
                    _OPEN_ODBS[handle].close()
                except Exception:
                    pass
                del _OPEN_ODBS[handle]
                closed.append(handle)
        elif path:
            for h, odb_obj in list(_OPEN_ODBS.items()):
                odb_path = getattr(odb_obj, "path", "")
                if odb_path == path:
                    try:
                        odb_obj.close()
                    except Exception:
                        pass
                    del _OPEN_ODBS[h]
                    closed.append(h)
        else:
            raise ValueError("Provide 'handle' or 'path'")
    return {"closed": closed}


def _odb_list() -> dict[str, Any]:
    """List all open ODB handles with basic info."""
    odbs = {}
    with _ODB_LOCK:
        for handle, odb_obj in _OPEN_ODBS.items():
            odbs[handle] = {
                "path": getattr(odb_obj, "path", "unknown"),
                "steps": list(odb_obj.steps.keys()) if hasattr(odb_obj, "steps") else [],
            }
    return {"odbs": odbs}


def _odb_summary(params: dict[str, Any]) -> dict[str, Any]:
    """Get detailed step/frame/field info for an open ODB."""
    handle = params.get("handle", "")
    if not handle:
        raise ValueError("params.handle is required")
    with _ODB_LOCK:
        odb = _OPEN_ODBS.get(handle)
    if odb is None:
        raise KeyError(f"ODB handle '{handle}' not found. Use odb_list to see open handles.")
    steps_info = []
    for sname, step in odb.steps.items():
        frames_info = []
        for fi, frame in enumerate(step.frames):
            fields = list(frame.fieldOutputs.keys()) if hasattr(frame, "fieldOutputs") else []
            frames_info.append({"index": fi, "time": float(frame.frameValue), "fields": fields})
        steps_info.append({"name": sname, "procedure": str(getattr(step, "procedure", "")), "num_frames": len(step.frames), "frames": frames_info})
    instances_info = []
    for iname, inst in odb.rootAssembly.instances.items():
        instances_info.append({
            "name": iname,
            "nodes": len(inst.nodes),
            "elements": len(inst.elements),
            "element_types": sorted(set(str(e.type) for e in inst.elements)),
        })
    return {
        "handle": handle,
        "path": getattr(odb, "path", "unknown"),
        "steps": steps_info,
        "instances": instances_info,
    }


def _mdb_info() -> dict[str, Any]:
    """Get structured mdb model/job info directly."""
    info: dict[str, Any] = {}
    try:
        from abaqus import mdb  # type: ignore
        models_info = {}
        for mname, model in mdb.models.items():
            models_info[mname] = {
                "parts": list(model.parts.keys()),
                "materials": list(model.materials.keys()),
                "steps": list(model.steps.keys()),
                "loads": list(model.loads.keys()),
                "boundary_conditions": list(model.boundaryConditions.keys()),
                "interactions": list(model.interactions.keys()),
                "constraints": list(getattr(model, 'constraints', {}).keys()),
                "unavailable_repositories": [name for name in ('constraints',) if not hasattr(model, name)],
                "instances": list(model.rootAssembly.instances.keys()),
                "sets": list(model.rootAssembly.sets.keys()),
                "surfaces": list(model.rootAssembly.surfaces.keys()),
            }
        info["models"] = models_info
        jobs_info = []
        for jname, job in mdb.jobs.items():
            jitem: dict[str, Any] = {"name": jname}
            for attr in ("status", "type", "model", "description", "numCpus", "numDomains", "memory"):
                try:
                    val = getattr(job, attr, None)
                    if val is not None:
                        jitem[attr] = str(val)
                except Exception:
                    pass
            jobs_info.append(jitem)
        info["jobs"] = jobs_info
    except ImportError:
        info["error"] = "Abaqus module not available"
    return info


def _cleanup() -> dict[str, Any]:
    """Close all open ODBs and return summary."""
    closed_handles = []
    errors = []
    with _ODB_LOCK:
        for handle, odb_obj in list(_OPEN_ODBS.items()):
            try:
                odb_obj.close()
                closed_handles.append(handle)
            except Exception as e:
                errors.append({"handle": handle, "error": str(e)})
            del _OPEN_ODBS[handle]
    return {"closed_handles": closed_handles, "errors": errors}


def _reset() -> dict[str, Any]:
    """Full kernel state reset: close ODBs, clear globals."""
    cleanup_result = _cleanup()
    _GLOBALS.clear()
    _GLOBALS.update({"__name__": "__ABAQUS_MCP_exec__", "__doc__": None})
    return {"cleanup": cleanup_result, "globals_reset": True}


def _extract_field(params: dict[str, Any]) -> dict[str, Any]:
    """Extract field data from an open ODB handle."""
    handle = params.get("handle", "")
    step_index = params.get("step_index", -1)
    frame_index = params.get("frame_index", -1) 
    field_name = params.get("field_name", "S")
    if not handle:
        raise ValueError("params.handle is required")
    with _ODB_LOCK:
        odb = _OPEN_ODBS.get(handle)
    if odb is None:
        raise KeyError(f"ODB handle '{handle}' not found")
    steps_list = list(odb.steps.values())
    if not steps_list:
        raise ValueError("ODB has no steps")
    if step_index < 0:
        step_index = len(steps_list) + step_index
    if not 0 <= step_index < len(steps_list):
        raise ValueError("step_index out of range")
    step = steps_list[step_index]
    frames_list = list(step.frames)
    if frame_index < 0:
        frame_index = len(frames_list) + frame_index
    if not 0 <= frame_index < len(frames_list):
        raise ValueError("frame_index out of range")
    frame = frames_list[frame_index]
    if field_name not in frame.fieldOutputs:
        raise KeyError(f"Field '{field_name}' not found in step {step_index} frame {frame_index}")
    fo = frame.fieldOutputs[field_name]
    values = []
    valid_invariants = {str(value) for value in getattr(fo, 'validInvariants', ())}
    for index in range(min(len(fo.values), 5000)):
        val = fo.values[index]  # Abaqus FieldValueArray does not implement slicing.
        entry: dict[str, Any] = {"node_label": getattr(val, "nodeLabel", None), "element_label": getattr(val, "elementLabel", None), "instance": getattr(getattr(val, "instance", None), "name", None)}
        try:
            d = val.data
        except Exception:
            d = val.dataDouble
        if hasattr(d, "__len__"):
            entry["data"] = [float(x) for x in d]
        else:
            entry["data"] = float(d)
        if 'MISES' in valid_invariants:
            entry["mises"] = float(val.mises)
        values.append(entry)
    return {
        "field": field_name,
        "step": step_index,
        "frame": frame_index,
        "frame_time": float(frame.frameValue),
        "values": values[:5000],  # cap at 5000 values
        "total_values": len(fo.values),
        "truncated": len(fo.values) > 5000,
    }

METHODS = ("ping", "capabilities", "execute", "odb_open", "odb_close", "odb_list",
           "odb_summary", "mdb_info", "extract_field", "cleanup", "reset", "request_status")
_REQUEST_LOCK = threading.RLock()
_REQUEST_HISTORY = OrderedDict()


def capabilities():
    return {"protocol_version": "1.1", "backend": "kernel", "methods": list(METHODS),
            "serialized": True, "readonly": os.environ.get("ABAQUS_MCP_READ_ONLY") == "1"}


def dispatch(method, params=None, request_id=None):
    import math
    params = dict(params or {})
    if method == "request_status":
        with _REQUEST_LOCK:
            record = _REQUEST_HISTORY.get(params.get("operation_id"))
            return dict(record) if record else {"status": "unknown"}
    operation_id = params.get("operation_id") or request_id
    duration = float(params.get('timeout', 60))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('timeout must be finite and positive')
    semantic_params = {k: v for k, v in params.items() if k not in ('timeout', 'operation_id')}
    fingerprint = hashlib.sha256(json.dumps([method, semantic_params], sort_keys=True).encode()).hexdigest()
    if operation_id:
        with _REQUEST_LOCK:
            record = _REQUEST_HISTORY.get(operation_id)
            if record:
                if record["fingerprint"] != fingerprint:
                    raise ValueError("operation_id already used with different parameters")
                if record["status"] == "completed":
                    return record["result"]
                raise RuntimeError("Operation already accepted; query request_status before retrying")
            if len(_REQUEST_HISTORY) >= 128:
                finished = next((key for key, val in _REQUEST_HISTORY.items()
                                 if val["status"] in ("completed", "failed", "expired")), None)
                if finished is None:
                    raise RuntimeError("Bridge request queue is full")
                del _REQUEST_HISTORY[finished]
            _REQUEST_HISTORY[operation_id] = {"status": "queued", "method": method,
                                             "fingerprint": fingerprint, "accepted_at": time.time()}
    deadline = time.monotonic() + duration
    try:
        with _EXEC_LOCK:
            if time.monotonic() > deadline:
                raise TimeoutError("Request expired before execution; no changes applied")
            if os.environ.get("ABAQUS_MCP_READ_ONLY") == "1":
                if method in ("execute", "reset") or (method == "odb_open" and not params.get("read_only", True)):
                    raise PermissionError("Operation disabled by ABAQUS_MCP_READ_ONLY")
            if operation_id:
                with _REQUEST_LOCK:
                    _REQUEST_HISTORY[operation_id]["status"] = "running"
            if method == "capabilities":
                result = capabilities()
            elif method == "ping":
                result = dict(_ping(), capabilities=capabilities())
            elif method == "execute":
                code = params.get("code")
                if not isinstance(code, str) or not code.strip():
                    raise ValueError("params.code must be a non-empty string")
                result = _execute(code)
            elif method in ("odb_open", "odb_close", "odb_summary", "extract_field"):
                result = {"odb_open": _odb_open, "odb_close": _odb_close,
                          "odb_summary": _odb_summary, "extract_field": _extract_field}[method](params)
            elif method in ("odb_list", "mdb_info", "cleanup", "reset"):
                result = {"odb_list": _odb_list, "mdb_info": _mdb_info,
                          "cleanup": _cleanup, "reset": _reset}[method]()
            else:
                raise ValueError("unknown method: " + str(method))
        if operation_id:
            with _REQUEST_LOCK:
                _REQUEST_HISTORY[operation_id].update(status="completed", result=result, finished_at=time.time())
        return result
    except Exception as exc:
        if operation_id:
            with _REQUEST_LOCK:
                _REQUEST_HISTORY[operation_id].update(status="failed", error=str(exc), finished_at=time.time())
        raise


class AbaqusMcpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        request_id = None
        try:
            message = _read_message(self)
            request_id = message.get("id")
            params = message.get("params") or {}
            if _AUTH_TOKEN is not None:
                token = params.get("token") or message.get("token") or ""
                if not isinstance(token, str) or not hmac.compare_digest(token, _AUTH_TOKEN):
                    raise PermissionError("Invalid or missing auth token")
            params = {k: v for k, v in params.items() if k != "token"}
            result = dispatch(message.get("method"), params, request_id)
            _send_message(self, {"id": request_id, "ok": True, "result": result})
        except Exception as exc:
            _send_message(self, {"id": request_id, "ok": False,
                                "error": {"message": str(exc), "type": type(exc).__name__}})


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    with ThreadedTCPServer((host, port), AbaqusMcpHandler) as server:
        print("Abaqus MCP agent listening on %s:%s" % (host, port))
        server.serve_forever()


def start_background(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadedTCPServer:
    server = ThreadedTCPServer((host, port), AbaqusMcpHandler)
    thread = threading.Thread(target=server.serve_forever, name="AbaqusMcpAgent", daemon=True)
    thread.start()
    print("Abaqus MCP agent listening on %s:%s in background" % (host, port))
    return server


def main() -> None:
    """Entry point for noGUI scripts: start the TCP socket agent."""
    serve()


if __name__ == "__main__":
    main()
