"""Tests for silent_failures.py: offline parsing and formatting."""

from __future__ import annotations

import pytest
from abaqus_mcp_pro.silent_failures import (
    SilentFailureFinding,
    SilentFailureReport,
    format_silent_failures_markdown,
    format_silent_failures_compact,
    parse_silent_failures_results,
    SILENT_FAILURE_CHECKS_CODE,
)


class TestSilentFailureFinding:
    def test_to_dict(self):
        f = SilentFailureFinding(
            category="mesh_integrity",
            severity="error",
            check_id="mesh_zero_elements",
            passed=False,
            detail="Part has 1 cell but 0 elements",
            suggestion="Check elemShape",
            evidence={"part": "MyPart", "cells": 1, "elements": 0},
        )
        d = f.to_dict()
        assert d["category"] == "mesh_integrity"
        assert d["severity"] == "error"
        assert d["check_id"] == "mesh_zero_elements"
        assert d["passed"] is False
        assert d["detail"] == "Part has 1 cell but 0 elements"
        assert d["suggestion"] == "Check elemShape"
        assert d["evidence"]["part"] == "MyPart"

    def test_passed_finding(self):
        f = SilentFailureFinding(
            category="mesh_integrity",
            severity="info",
            check_id="mesh_ok",
            passed=True,
            detail="Part has 1 cell, 32 elements, 49 nodes",
        )
        assert f.passed is True
        assert f.severity == "info"


class TestSilentFailureReport:
    def test_empty_report(self):
        r = SilentFailureReport(model_name="TestModel")
        assert r.model_name == "TestModel"
        assert len(r.findings) == 0
        assert r.passed_count == 0
        assert r.failed_count == 0
        assert r.warning_count == 0

    def test_add_finding_increments_counts(self):
        r = SilentFailureReport()
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="info", check_id="mesh_ok",
            passed=True, detail="ok",
        ))
        r.add_finding(SilentFailureFinding(
            category="volume_logic", severity="error", check_id="volume_zero",
            passed=False, detail="zero volume",
        ))
        r.add_finding(SilentFailureFinding(
            category="unconstrained", severity="warning", check_id="unconstrained_instance",
            passed=False, detail="instance has no BCs",
        ))
        assert r.passed_count == 1
        assert r.failed_count == 1
        assert r.warning_count == 1
        assert len(r.findings) == 3

    def test_to_dict(self):
        r = SilentFailureReport(model_name="Test")
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="info", check_id="mesh_ok",
            passed=True, detail="ok",
        ))
        d = r.to_dict()
        assert d["model_name"] == "Test"
        assert d["passed_count"] == 1
        assert d["failed_count"] == 0
        assert len(d["findings"]) == 1


class TestFormatSilentFailures:
    def test_markdown_empty_report(self):
        r = SilentFailureReport(model_name="TestModel")
        md = format_silent_failures_markdown(r)
        assert "## Silent Failure Detection" in md
        assert "No checks run" in md
        assert "No silent-failure checks were executed" in md

    def test_markdown_with_findings(self):
        r = SilentFailureReport(model_name="TestModel")
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="error", check_id="mesh_zero_elements",
            passed=False, detail="Part has 1 cell but 0 elements",
            suggestion="Check elemShape",
            evidence={"part": "MyPart", "cells": 1, "elements": 0},
        ))
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="info", check_id="mesh_ok",
            passed=True, detail="Part has 1 cell, 32 elements",
            evidence={"part": "MyPart", "cells": 1, "elements": 32, "nodes": 49},
        ))
        md = format_silent_failures_markdown(r)
        assert "## Silent Failure Detection" in md
        assert "TestModel" in md
        assert "FAIL" in md
        assert "mesh_zero_elements" in md
        assert "Check elemShape" in md
        assert "PASS" in md
        assert "mesh_ok" in md

    def test_markdown_grouped_by_category(self):
        r = SilentFailureReport(model_name="Test")
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="error", check_id="check1",
            passed=False, detail="Mesh error",
        ))
        r.add_finding(SilentFailureFinding(
            category="volume_logic", severity="warning", check_id="check2",
            passed=False, detail="Volume warning",
        ))
        md = format_silent_failures_markdown(r)
        # Categories should appear as sections
        assert "Mesh Integrity" in md
        assert "Volume Logic" in md

    def test_compact_format(self):
        r = SilentFailureReport(model_name="Test")
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="error", check_id="check1",
            passed=False, detail="Mesh error",
        ))
        r.add_finding(SilentFailureFinding(
            category="mesh_integrity", severity="info", check_id="check2",
            passed=True, detail="Mesh ok",
        ))
        compact = format_silent_failures_compact(r)
        assert "[FAIL]" in compact
        assert "[PASS]" in compact
        assert "Test" in compact


class TestParseSilentFailuresResults:
    def test_empty_result(self):
        raw = {"model_name": "Test", "findings": [], "passed_count": 0, "failed_count": 0, "warning_count": 0}
        report = parse_silent_failures_results(raw)
        assert report.model_name == "Test"
        assert len(report.findings) == 0

    def test_with_findings(self):
        raw = {
            "model_name": "TestModel",
            "workdir": "/tmp",
            "findings": [
                {
                    "category": "mesh_integrity",
                    "severity": "error",
                    "check_id": "mesh_zero_elements",
                    "passed": False,
                    "detail": "Part 'A' has 1 cell but 0 elements",
                    "suggestion": "Check elemShape",
                    "evidence": {"part": "A", "cells": 1, "elements": 0},
                },
                {
                    "category": "mesh_integrity",
                    "severity": "info",
                    "check_id": "mesh_ok",
                    "passed": True,
                    "detail": "Part 'B' has 1 cell, 32 elements",
                    "suggestion": "",
                    "evidence": {"part": "B", "cells": 1, "elements": 32, "nodes": 49},
                },
            ],
            "passed_count": 1,
            "failed_count": 1,
            "warning_count": 0,
        }
        report = parse_silent_failures_results(raw)
        assert report.model_name == "TestModel"
        assert report.passed_count == 1
        assert report.failed_count == 1
        assert len(report.findings) == 2

        # Check first finding
        f0 = report.findings[0]
        assert f0.category == "mesh_integrity"
        assert f0.severity == "error"
        assert f0.passed is False
        assert "0 elements" in f0.detail

        # Check second finding
        f1 = report.findings[1]
        assert f1.category == "mesh_integrity"
        assert f1.passed is True
        assert "32 elements" in f1.detail


class TestSILENT_FAILURE_CHECKS_CODE:
    """Verify the embedded code string is syntactically valid Python."""

    def test_code_is_valid_python(self):
        """The SILENT_FAILURE_CHECKS_CODE should be syntactically valid Python."""
        import ast
        try:
            ast.parse(SILENT_FAILURE_CHECKS_CODE)
        except SyntaxError as e:
            pytest.fail(f"SILENT_FAILURE_CHECKS_CODE has syntax error: {e}")

    def test_code_contains_all_categories(self):
        """The code should contain all 7 check categories."""
        code = SILENT_FAILURE_CHECKS_CODE
        assert "mesh_integrity" in code
        assert "constraint_coverage" in code
        assert "volume_logic" in code
        assert "contact_validity" in code
        assert "element_quality" in code
        assert "job_output" in code
        assert "dat_warnings" in code
        assert "post_processing" in code
        assert "unconstrained" in code

    def test_code_has_findings_output(self):
        """The code should produce a findings list."""
        assert "findings" in SILENT_FAILURE_CHECKS_CODE
        assert "result" in SILENT_FAILURE_CHECKS_CODE
        assert "element_c3d8_locking" in SILENT_FAILURE_CHECKS_CODE
        assert "element_c3d4_stiff" in SILENT_FAILURE_CHECKS_CODE
        assert "element_low_density" in SILENT_FAILURE_CHECKS_CODE
        assert "passed_count" in SILENT_FAILURE_CHECKS_CODE
        assert "failed_count" in SILENT_FAILURE_CHECKS_CODE
        assert "warning_count" in SILENT_FAILURE_CHECKS_CODE

    def test_code_has_placeholders(self):
        """The code template should have placeholders for model_name and workdir."""
        assert "__MODEL_NAME__" in SILENT_FAILURE_CHECKS_CODE
        assert "__WORKDIR__" in SILENT_FAILURE_CHECKS_CODE
