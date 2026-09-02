"""Unit tests for _format_error_to_markdown."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.tools import _format_error_to_markdown


class TestFormatErrorToMarkdown:

    def test_keyerror_full(self, sample_keyerror_result):
        output = _format_error_to_markdown(sample_keyerror_result)
        assert "KeyError" in output
        assert "at line 42" in output
        assert "Set-Fixed" in output
        assert "Container:" in output
        assert "models" in output
        assert "Available:" in output
        assert "Set-Left" in output
        assert "Similar:" in output
        assert "Code:" in output

    def test_keyerror_prefix_dedup(self, sample_keyerror_result_with_prefix):
        output = _format_error_to_markdown(sample_keyerror_result_with_prefix)
        assert output.count("KeyError:") == 0  # prefix dedup correctly removed
        assert "Set-Fixed" in output

    def test_keyerror_available_keys_truncation(self):
        result = {
            "ok": False,
            "error_type": "KeyError",
            "core_error": "KeyError: 'bad'",
            "error_line": 1,
            "recovery": {
                "missing_key": "bad",
                "available_keys_sample": [f"key_{i}" for i in range(25)],
            },
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "..." in output
        assert "key_19" in output
        assert "key_20" not in output

    def test_attribute_error(self, sample_attribute_error_result):
        output = _format_error_to_markdown(sample_attribute_error_result)
        assert "AttributeError" in output
        assert "Missing Attribute:" in output
        assert "getElement" in output
        assert "Object Type:" in output
        assert "Part" in output
        assert "Object Path:" in output
        assert "Similar:" in output
        assert "getElements" in output

    def test_name_error(self, sample_name_error_result):
        output = _format_error_to_markdown(sample_name_error_result)
        assert "NameError" in output
        assert "Undefined Variable:" in output
        assert "abaqusConstants" in output
        assert "Import Suggestion:" in output
        assert "from abaqusConstants" in output

    def test_syntax_error(self, sample_syntax_error_result):
        output = _format_error_to_markdown(sample_syntax_error_result)
        assert "SyntaxError" in output
        assert "Syntax Error offset:" in output
        assert "12" in output
        assert "Problem text:" in output
        assert "fr i" in output

    def test_type_error(self, sample_type_error_result):
        output = _format_error_to_markdown(sample_type_error_result)
        assert "TypeError" in output
        assert "Call Target:" in output
        assert "EncastreBC" in output
        assert "Expected Signature:" in output
        assert "Description:" in output
        assert "Similar Keywords:" in output

    def test_simple_error_no_recovery(self, sample_simple_error_result):
        output = _format_error_to_markdown(sample_simple_error_result)
        assert "RuntimeError: Something went wrong" in output
        assert "at line" not in output

    def test_code_excerpt_only_marked_line(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 5,
            "code_excerpt": "  3 | a = 1\n  4 | b = 2\n>>5 | c = d\n  6 | e = 4",
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "Code:" in output
        assert "c = d" in output
        assert "a = 1" not in output
        assert "b = 2" not in output
        assert "e = 4" not in output

    def test_code_excerpt_no_marked_line(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 5,
            "code_excerpt": "  3 | a = 1\n  4 | b = 2",
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "Code:" not in output

    def test_code_excerpt_with_pipe_format(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 5,
            "code_excerpt": ">>5 | x = invalid()",
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "Code: x = invalid()" in output

    def test_short_stdout_shown_fully(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 1,
            "stdout": "short output",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "stdout: short output" in output

    def test_long_stdout_summarized(self, sample_long_output_result):
        output = _format_error_to_markdown(sample_long_output_result)
        assert "stdout: (captured, 6 lines)" in output
        assert "stderr: (captured, 4 lines)" in output

    def test_no_stdout_stderr(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 1,
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "stdout:" not in output
        assert "stderr:" not in output

    def test_none_stdout_stderr(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 1,
            "stdout": None,
            "stderr": None,
        }
        output = _format_error_to_markdown(result)
        assert "stdout:" not in output
        assert "stderr:" not in output

    def test_empty_result(self):
        output = _format_error_to_markdown({})
        assert "Unknown" in output
        assert "Unknown error" in output

    def test_error_type_with_dots(self):
        result = {
            "ok": False,
            "error_type": "abaqus_mcp_pro.protocol.ProtocolError",
            "core_error": "socket closed",
            "error_line": None,
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "ProtocolError: socket closed" in output
        assert "abaqus_mcp_pro.protocol" not in output

    def test_generic_fallback_recovery(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 1,
            "recovery": {
                "parent_object_path": "some.path",
                "import_suggestion": "from x import y",
                "unknown_field": "should be ignored",
            },
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "Object: some.path" in output
        assert "Import Suggestion: from x import y" in output
        assert "unknown_field" not in output

    def test_recovery_not_dict(self):
        result = {
            "ok": False,
            "error_type": "Error",
            "core_error": "test",
            "error_line": 1,
            "recovery": "not a dict",
            "stdout": "",
            "stderr": "",
        }
        output = _format_error_to_markdown(result)
        assert "Object:" not in output
