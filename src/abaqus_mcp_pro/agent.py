"""Abaqus-side socket agent.

This file intentionally uses only the Python standard library so it can run
inside Abaqus 2024's bundled Python 3.10 without installing project deps there.
"""

from __future__ import annotations

import ast
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

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 48152

_GLOBALS: dict[str, Any] = {
    "__name__": "__ABAQUS_MCP_exec__",
    "__doc__": None,
}
_EXEC_LOCK = threading.Lock()
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


def _read_message(request: socketserver.BaseRequestHandler) -> dict[str, Any]:
    chunks: list[bytes] = []
    while True:
        chunk = request.request.recv(4096)
        if not chunk:
            raise RuntimeError("socket closed before a complete message was received")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break
        chunks.append(chunk)
    message = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(message, dict):
        raise RuntimeError("protocol message must be a JSON object")
    return message


def _send_message(request: socketserver.BaseRequestHandler, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request.request.sendall(data + b"\n")


_MAX_OUTPUT = 1_000


_READ_LOCK = threading.Lock()

def _execute(code: str, read_only: bool = False) -> dict[str, Any]:
    """Execute Python code in Abaqus kernel.

    If read_only=True, uses a shared lock instead of the exclusive lock,
    allowing concurrent read-only queries.
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

    # Use shared lock for read_only, exclusive lock for write
    lock: threading.Lock = _READ_LOCK if read_only else _EXEC_LOCK  # type: ignore[assignment]

    with lock, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
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
        steps_info.append({"name": sname, "procedure": str(getattr(step, "procedure", "")), "num_frames": len(step.frames)})
    instances_info = []
    for iname, inst in odb.rootAssembly.instances.items():
        instances_info.append({
            "name": iname,
            "nodes": len(inst.nodes),
            "elements": len(inst.elements),
            "element_types": list(set(e.type.name for e in inst.elements)),
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
                "constraints": list(model.constraints.keys()),
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
    step = steps_list[step_index]
    frames_list = list(step.frames)
    if frame_index < 0:
        frame_index = len(frames_list) + frame_index
    frame = frames_list[frame_index]
    if field_name not in frame.fieldOutputs:
        raise KeyError(f"Field '{field_name}' not found in step {step_index} frame {frame_index}")
    fo = frame.fieldOutputs[field_name]
    values = []
    for val in fo.values:
        entry: dict[str, Any] = {"node_label": val.nodeLabel, "element_label": val.elementLabel}
        if hasattr(val, "data"):
            d = val.data
            if hasattr(d, "__len__"):
                entry["data"] = [float(x) for x in d]
            else:
                entry["data"] = float(d)
        if hasattr(val, "mises"):
            entry["mises"] = float(val.mises)
        if hasattr(val, "invariants") and val.invariants:
            entry["invariants"] = {str(k): float(v) for k, v in val.invariants.items()}
        values.append(entry)
    return {
        "field": field_name,
        "step": step_index,
        "frame": frame_index,
        "frame_time": float(frame.frameValue),
        "values": values[:5000],  # cap at 5000 values
        "total_values": len(values),
        "truncated": len(values) > 5000,
    }

class AbaqusMcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        request_id = None
        try:
            message = _read_message(self)
            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params") or {}

            # Auth check (if token is configured)
            if _AUTH_TOKEN is not None:
                req_token = params.get("token") or message.get("token")
                if req_token != _AUTH_TOKEN:
                    raise PermissionError("Invalid or missing auth token. Set ABAQUS_MCP_TOKEN on server and client.")

            if method == "ping":
                result = _ping()
            elif method == "execute":
                code = params.get("code")
                if not isinstance(code, str) or not code.strip():
                    raise ValueError("params.code must be a non-empty string")
                read_only = params.get("read_only", False)
                result = _execute(code, read_only)
            elif method == "odb_open":
                result = _odb_open(params)
            elif method == "odb_close":
                result = _odb_close(params)
            elif method == "odb_list":
                result = _odb_list()
            elif method == "odb_summary":
                result = _odb_summary(params)
            elif method == "mdb_info":
                result = _mdb_info()
            elif method == "extract_field":
                result = _extract_field(params)
            elif method == "cleanup":
                result = _cleanup()
            elif method == "reset":
                result = _reset()
            else:
                raise ValueError(f"unknown method: {method!r}")

            _send_message(self, {"id": request_id, "ok": True, "result": result})
        except Exception as exc:
            _send_message(
                self,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "message": str(exc),
                        "type": f"{type(exc).__module__}.{type(exc).__name__}",
                        "traceback": traceback.format_exc(),
                    },
                },
            )


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
