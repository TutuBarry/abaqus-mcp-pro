"""Non-invasive GUI automation tools for Abaqus MCP Pro.

Uses pywinauto to control an existing Abaqus/CAE GUI session without requiring
any plugin installed inside Abaqus. This is the fallback mode when the TCP
bridge or file IPC plugin cannot be installed.

Reference: abaqus-mcp-server-main (cite/abaqus-mcp-server-main/.../mcp_server.py)
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any, Optional


# Window cache
_abaqus_main_window_cache: Optional[Any] = None
_abaqus_app_instance_cache: Optional[Any] = None


def find_abaqus_window_and_app():
    """Find the main Abaqus/CAE window and connect a pywinauto Application.

    Uses pygetwindow for initial window discovery and pywinauto for connection.
    Results are cached for subsequent calls.

    Returns:
        Tuple of (Application, WindowSpecification) or (None, None) if not found.
    """
    global _abaqus_main_window_cache, _abaqus_app_instance_cache

    if (
        _abaqus_app_instance_cache
        and _abaqus_main_window_cache
        and _abaqus_main_window_cache.exists()
        and _abaqus_main_window_cache.is_visible()
    ):
        return _abaqus_app_instance_cache, _abaqus_main_window_cache

    _abaqus_app_instance_cache = None
    _abaqus_main_window_cache = None

    try:
        import pygetwindow as gw
        import win32process
        import psutil
        from pywinauto import Application, timings
    except ImportError:
        return None, None

    windows = gw.getWindowsWithTitle("Abaqus/CAE")
    found_win_obj = None
    for win_ref in windows:
        if win_ref.title.startswith("Abaqus/CAE"):
            try:
                _, pid = win32process.GetWindowThreadProcessId(win_ref._hWnd)
                proc = psutil.Process(pid)
                if "abaqus" in proc.name().lower() and (
                    "cae" in proc.name().lower() or "viewer" in proc.name().lower()
                ):
                    found_win_obj = win_ref
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    if found_win_obj:
        try:
            timings.Timings.slow()
            app = Application(backend="uia").connect(
                handle=found_win_obj._hWnd, timeout=20
            )
            main_window = app.window(handle=found_win_obj._hWnd)
            if main_window.exists() and main_window.is_visible():
                _abaqus_app_instance_cache = app
                _abaqus_main_window_cache = main_window
                return app, main_window
        except Exception:
            pass

    return None, None


async def find_abaqus_window() -> str:
    """Check if an Abaqus/CAE GUI window is available for pywinauto control.

    Returns JSON with found, title, and pid if found.
    """
    import json
    app, main_window = find_abaqus_window_and_app()
    if main_window and main_window.exists():
        return json.dumps({
            "found": True,
            "title": main_window.window_text(),
            "visible": main_window.is_visible(),
        }, indent=2)
    return json.dumps({
        "found": False,
        "detail": "Abaqus/CAE window not found.",
    }, indent=2)


async def execute_script_in_abaqus_gui(python_code: str) -> str:
    """Execute a Python script in Abaqus/CAE via File->Run Script.

    Uses Windows UI Automation (pywinauto) to automate the GUI.
    Important: Only confirms script submission, not execution output.
    Use get_abaqus_gui_message_log to see results.
    """
    global _abaqus_main_window_cache, _abaqus_app_instance_cache

    app, main_window = find_abaqus_window_and_app()

    if not main_window or not main_window.exists():
        _abaqus_app_instance_cache = None
        _abaqus_main_window_cache = None
        return "Abaqus/CAE window not found."

    script_file_path = None
    run_script_dialog = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp_script:
            tmp_script.write(python_code)
            script_file_path = tmp_script.name

        script_file_path_for_dialog = script_file_path.replace("/", "\\")

        if main_window.is_minimized():
            main_window.restore()
        main_window.set_focus()
        time.sleep(0.5)

        main_window.menu_select("File->Run Script...")
        time.sleep(1.5)

        dialog_found = False
        try:
            run_script_dialog = app.top_window()
            if run_script_dialog.exists() and (
                "Run Script" in run_script_dialog.window_text()
                or "Select file" in run_script_dialog.window_text()
            ):
                dialog_found = True

            if not dialog_found:
                time.sleep(1)
                run_script_dialog = app.active()
                if run_script_dialog.exists() and (
                    "Run Script" in run_script_dialog.window_text()
                    or "Select file" in run_script_dialog.window_text()
                ):
                    dialog_found = True

            if not dialog_found:
                possible_dialogs = main_window.children(
                    control_type="Window", top_level_only=False, visible=True
                )
                for diag in possible_dialogs:
                    if diag.exists() and (
                        "Run Script" in diag.window_text()
                        or "Select file" in diag.window_text()
                    ):
                        run_script_dialog = diag
                        dialog_found = True
                        break

            if not dialog_found or not run_script_dialog:
                raise Exception("Run Script dialog not found.")
        except Exception as e_dialog:
            return "Failed to find dialog: " + str(e_dialog)

        try:
            file_name_edit = None
            potential_edit = run_script_dialog.child_window(
                title="File &name:", control_type="Edit"
            )
            if potential_edit.exists(timeout=1):
                file_name_edit = potential_edit.wrapper_object()
            else:
                potential_edit_by_index = run_script_dialog.child_window(
                    control_type="Edit", found_index=0
                )
                if potential_edit_by_index.exists(timeout=1):
                    file_name_edit = potential_edit_by_index.wrapper_object()
                else:
                    generic_edit = run_script_dialog.Edit(found_index=0)
                    if generic_edit.exists(timeout=1):
                        file_name_edit = generic_edit

            if not file_name_edit:
                raise Exception("File name input not found.")

            file_name_edit.set_edit_text(script_file_path_for_dialog)
            time.sleep(0.3)

            ok_button = None
            potential_button = run_script_dialog.child_window(
                title_re="OK|Run|Open", control_type="Button"
            )
            if potential_button.exists(timeout=1):
                ok_button = potential_button.wrapper_object()
            else:
                potential_button_by_index = run_script_dialog.child_window(
                    control_type="Button", found_index=0
                )
                if potential_button_by_index.exists(timeout=1):
                    ok_button = potential_button_by_index.wrapper_object()
                else:
                    generic_button = run_script_dialog.Button(found_index=0)
                    if generic_button.exists(timeout=1):
                        ok_button = generic_button

            if not ok_button:
                raise Exception("OK button not found.")

            ok_button.click_input()

            return "Script submitted: " + script_file_path

        except Exception as e_interact:
            if run_script_dialog and run_script_dialog.exists():
                try:
                    run_script_dialog.close()
                except Exception:
                    pass
            return "Failed to interact: " + str(e_interact)

    except Exception as e_main:
        _abaqus_app_instance_cache = None
        _abaqus_main_window_cache = None
        return "Error: " + str(e_main)
    finally:
        if script_file_path and os.path.exists(script_file_path):
            try:
                os.remove(script_file_path)
            except Exception:
                pass


async def get_abaqus_gui_message_log() -> str:
    """Retrieve text from the Abaqus/CAE message/log area.

    Uses heuristics to find and scrape the message area.
    """
    global _abaqus_main_window_cache, _abaqus_app_instance_cache

    app, main_window = find_abaqus_window_and_app()

    if not main_window or not main_window.exists():
        _abaqus_app_instance_cache = None
        _abaqus_main_window_cache = None
        return "Abaqus/CAE window not found."

    try:
        message_area_control = None

        possible_panes = main_window.descendants(control_type="Pane")
        for pane_spec in possible_panes:
            pane = pane_spec.wrapper_object()
            if (
                pane.is_visible()
                and pane.rectangle().height > 100
                and pane.rectangle().width() > 200
            ):
                if "FXWindow" in pane.class_name():
                    texts = pane.texts()
                    if texts and any(
                        line.strip() for group in texts if group for line in group
                    ):
                        message_area_control = pane
                        break

        if not message_area_control:
            possible_edits = main_window.descendants(control_type="Edit")
            for edit_spec in possible_edits:
                edit = edit_spec.wrapper_object()
                if (
                    edit.is_visible()
                    and not edit.is_editable()
                    and edit.rectangle().height > 50
                ):
                    texts = edit.texts()
                    if texts and any(
                        line.strip() for group in texts if group for line in group
                    ):
                        message_area_control = edit
                        break

        if message_area_control and message_area_control.exists():
            log_content_lines = []
            raw_texts = message_area_control.texts()
            for text_group in raw_texts:
                if text_group:
                    for line in text_group:
                        if line:
                            log_content_lines.append(line)

            log_content = "\\n".join(log_content_lines).strip()

            if not log_content and hasattr(message_area_control, "window_text"):
                log_content = message_area_control.window_text().strip()

            if log_content:
                return (
                    "Message Log Content:\\n"
                    "------------------------\\n"
                    "%s\\n"
                    "------------------------" % log_content
                )
            else:
                return "Found message area but could not extract text."
        else:
            return "Message area not found."

    except Exception as e:
        _abaqus_app_instance_cache = None
        _abaqus_main_window_cache = None
        return "Error: " + str(e)
