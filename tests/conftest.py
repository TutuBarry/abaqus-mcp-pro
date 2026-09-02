"""Shared test fixtures for abaqus-mcp-pro."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_keyerror_result() -> dict:
    """A typical KeyError crash payload from the Abaqus bridge."""
    return {
        "ok": False,
        "error_type": "KeyError",
        "core_error": "KeyError: 'Set-Fixed'",
        "error_line": 42,
        "recovery": {
            "missing_key": "Set-Fixed",
            "parent_object_path": "mdb.models['Model-1'].rootAssembly.instances['Part-1-1'].sets",
            "available_keys_sample": ["Set-Left", "Set-Right", "Set-Top", "Set-Bottom"],
            "possible_keys": ["Set-Left", "Set-Fix"],
        },
        "code_excerpt": "  40 | inst = mdb.models['Model-1'].rootAssembly.instances['Part-1-1']\n>>41 | region = inst.sets['Set-Fixed']\n  42 | mdb.models['Model-1'].EncastreBC(name='Fixed', createStepName='Step-1', region=region)",
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_keyerror_result_with_prefix() -> dict:
    """KeyError where core_error already has the type prefix."""
    return {
        "ok": False,
        "error_type": "KeyError",
        "core_error": "KeyError: 'Set-Fixed'",
        "error_line": 42,
        "recovery": {
            "missing_key": "Set-Fixed",
            "available_keys_sample": ["Set-Left", "Set-Right"],
        },
        "code_excerpt": ">>41 | region = inst.sets['Set-Fixed']",
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_attribute_error_result() -> dict:
    """A typical AttributeError crash payload."""
    return {
        "ok": False,
        "error_type": "AttributeError",
        "core_error": "'Part' object has no attribute 'getElement'",
        "error_line": 15,
        "recovery": {
            "missing_attribute": "getElement",
            "object_type": "Part",
            "parent_object_path": "mdb.models['Model-1'].parts['Part-1']",
            "possible_members": ["elements", "getElements", "nodes", "faces"],
        },
        "code_excerpt": "  14 | p = mdb.models['Model-1'].parts['Part-1']\n>>15 | e = p.getElement(1)",
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_name_error_result() -> dict:
    """A typical NameError crash payload."""
    return {
        "ok": False,
        "error_type": "NameError",
        "core_error": "name 'abaqusConstants' is not defined",
        "error_line": 3,
        "recovery": {
            "missing_variable": "abaqusConstants",
            "import_suggestion": "from abaqusConstants import *",
        },
        "code_excerpt": ">>3 | abaqusConstants.THREE_D",
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_syntax_error_result() -> dict:
    """A typical SyntaxError crash payload."""
    return {
        "ok": False,
        "error_type": "SyntaxError",
        "core_error": "invalid syntax",
        "error_line": 7,
        "recovery": {
            "syntax_line": 7,
            "syntax_offset": 12,
            "syntax_text": "    fr i in range(10):\n",
        },
        "code_excerpt": ">>7 |     fr i in range(10):",
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_type_error_result() -> dict:
    """A typical TypeError/callable crash payload."""
    return {
        "ok": False,
        "error_type": "TypeError",
        "core_error": "EncastreBC() got an unexpected keyword argument 'region'",
        "error_line": 25,
        "recovery": {
            "call_target": "mdb.models['Model-1'].EncastreBC",
            "callable_signature": "EncastreBC(name, createStepName, region=None)",
            "callable_summary": "Create an encastre boundary condition",
            "possible_keywords": ["name", "createStepName", "region"],
        },
        "code_excerpt": ">>25 | mdb.models['Model-1'].EncastreBC(name='BC-1', createStepName='Step-1', regon=inst.sets['Fixed'])",
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_simple_error_result() -> dict:
    """Minimal error with no recovery info."""
    return {
        "ok": False,
        "error_type": "RuntimeError",
        "core_error": "Something went wrong",
        "error_line": None,
        "stdout": "",
        "stderr": "",
    }


@pytest.fixture
def sample_long_output_result() -> dict:
    """Error with long stdout and stderr."""
    return {
        "ok": False,
        "error_type": "ValueError",
        "core_error": "Invalid input",
        "error_line": 10,
        "stdout": "line1\nline2\nline3\nline4\nline5\nline6",
        "stderr": "err1\nerr2\nerr3\nerr4",
    }
