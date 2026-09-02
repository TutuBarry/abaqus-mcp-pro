"""Unit tests for solver_diagnosis module."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.solver_diagnosis import (
    DiagnosticEvent,
    DiagnosisReport,
    diagnose_logs,
    diagnose_logs_from_paths,
    format_diagnosis_markdown,
    format_diagnosis_compact,
)


# ── Sample log content builders ──────────────────────────────────────────

def _write_file(workdir: str, fname: str, content: str) -> str:
    path = os.path.join(workdir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


class TestDiagnosticEvent:
    def test_creation(self):
        ev = DiagnosticEvent(
            category="license",
            severity="error",
            pattern_id="license_unavailable",
            file="test.log",
            line=5,
            raw_line="License not available",
            suggestion="Check license server.",
        )
        assert ev.category == "license"
        assert ev.severity == "error"
        assert ev.pattern_id == "license_unavailable"


class TestDiagnosisReport:
    def test_empty_report(self):
        r = DiagnosisReport(job_name="test", workdir="/tmp")
        assert r.error_count == 0
        assert r.warning_count == 0
        assert r.info_count == 0
        assert r.events == []
        assert r.files_scanned == []

    def test_add_event_counts(self):
        r = DiagnosisReport(job_name="test", workdir="/tmp")
        r.add_event(DiagnosticEvent(
            category="license", severity="error", pattern_id="e1",
            file="x.log", line=1, raw_line="err", suggestion="fix",
        ))
        r.add_event(DiagnosticEvent(
            category="mesh", severity="warning", pattern_id="w1",
            file="x.log", line=2, raw_line="warn", suggestion="check",
        ))
        r.add_event(DiagnosticEvent(
            category="general", severity="info", pattern_id="i1",
            file="x.log", line=3, raw_line="info", suggestion="ok",
        ))
        assert r.error_count == 1
        assert r.warning_count == 1
        assert r.info_count == 1
        assert len(r.events) == 3

    def test_to_dict(self):
        r = DiagnosisReport(job_name="test", workdir="/tmp")
        r.add_event(DiagnosticEvent(
            category="license", severity="error", pattern_id="e1",
            file="x.log", line=1, raw_line="err", suggestion="fix",
        ))
        d = r.to_dict()
        assert d["job_name"] == "test"
        assert d["error_count"] == 1
        assert len(d["events"]) == 1
        assert d["events"][0]["pattern_id"] == "e1"


class TestDiagnoseLogs:
    def test_license_unavailable(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "Abaqus JOB job1\n"
            "Begin Analysis Input File Processor\n"
            "***ERROR: License for feature cae is not available\n"
            "Abaqus/Analysis exited with errors\n"
        ))
        _write_file(workdir, "job1.msg", "Analysis started\n")
        report = diagnose_logs("job1", workdir)
        assert report.error_count >= 1
        assert any(e.pattern_id == "license_unavailable" for e in report.events)

    def test_too_many_attempts(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***ERROR: Too many attempts made for this increment\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "too_many_attempts" for e in report.events)

    def test_time_increment_too_small(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.sta", (
            "STEP 1 INC 42 TIME 0.850\n"
            "***ERROR: Time increment required is less than the minimum specified\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "time_increment_required_too_small" for e in report.events)

    def test_maximum_increments_exceeded(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***ERROR: Maximum number of increments exceeded\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "maximum_increments_exceeded" for e in report.events)

    def test_rigid_body_motion(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***WARNING: Solver problem. Numerical singularity at node 12345\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "rigid_body_motion" for e in report.events)

    def test_negative_eigenvalues(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***WARNING: The system matrix has 3 negative eigenvalues\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "negative_eigenvalues" for e in report.events)

    def test_contact_overclosure(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***WARNING: There is an overclosure of 0.5 between surfaces\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "contact_overclosure" for e in report.events)

    def test_material_missing_density(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Density must be defined for dynamic analysis\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "material_missing_density" for e in report.events)

    def test_material_not_defined(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Material STEEL is not defined\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "material_not_defined" for e in report.events)

    def test_memory_allocation(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "Abaqus Error: The memory allocation exceeded the available memory\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "memory_allocation" for e in report.events)

    def test_disk_full(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "***ERROR: The disk is full. No space left on device.\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "disk_full" for e in report.events)

    def test_file_not_found(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "***ERROR: Cannot open file job1.inp. No such file or directory.\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "file_not_found" for e in report.events)

    def test_lock_file_exists(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "***ERROR: The lock file job1.lck already exists\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "lock_file_exists" for e in report.events)

    def test_odb_corrupt(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***ERROR: The ODB file job1.odb is corrupt and cannot be opened\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "odb_corrupt" for e in report.events)

    def test_keyword_error(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Unknown keyword 'MATERIALS'. Did you mean 'MATERIAL'?\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "keyword_error" for e in report.events)

    def test_element_type_unknown(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Element type C3D99 is not recognized\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "element_type_unknown" for e in report.events)

    def test_missing_node_set(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Node set FIXED_END not found\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "missing_node_set" for e in report.events)

    def test_missing_element_set(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Element set ELSET_BODY not found\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "missing_element_set" for e in report.events)

    def test_missing_surface(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.dat", (
            "***ERROR: Surface CONTACT_SURF not found\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "missing_surface" for e in report.events)

    def test_excessive_distortion(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***ERROR: Excessive distortion of element 567\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "excessive_distortion" for e in report.events)

    def test_explicit_stable_time_too_small(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.sta", (
            "***ERROR: The stable time increment is too small\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "explicit_stable_time_too_small" for e in report.events)

    def test_analysis_completed(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "analysis_completed" for e in report.events)

    def test_analysis_aborted(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.log", (
            "THE ANALYSIS HAS BEEN TERMINATED\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert any(e.pattern_id == "analysis_aborted" for e in report.events)

    def test_no_files_found(self, tmp_path):
        workdir = str(tmp_path)
        report = diagnose_logs("job1", workdir)
        assert report.files_scanned == []
        assert report.events == []

    def test_no_issues(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", "Step 1 completed\n")
        _write_file(workdir, "job1.sta", "STEP 1 INC 10 COMPLETED\n")
        report = diagnose_logs("job1", workdir)
        # The "completed" lines should match the analysis_completed pattern
        assert any(e.pattern_id == "analysis_completed" for e in report.events)

    def test_multiple_errors_in_one_file(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***ERROR: Too many attempts made for this increment\n"
            "***WARNING: There is an overclosure of 0.5 between surfaces\n"
            "***WARNING: The system matrix has 3 negative eigenvalues\n"
        ))
        report = diagnose_logs("job1", workdir)
        assert len(report.events) >= 3
        assert report.error_count >= 1
        assert report.warning_count >= 2

    def test_diagnose_from_paths(self, tmp_path):
        workdir = str(tmp_path)
        _write_file(workdir, "job1.msg", (
            "***ERROR: Too many attempts made for this increment\n"
        ))
        report = diagnose_logs_from_paths("job1", [os.path.join(workdir, "job1.msg")])
        assert any(e.pattern_id == "too_many_attempts" for e in report.events)
        assert "job1.msg" in report.files_scanned


class TestFormatDiagnosisMarkdown:
    def test_empty_report(self):
        report = DiagnosisReport(job_name="test", workdir="/tmp")
        md = format_diagnosis_markdown(report)
        assert "## Diagnosis: `test`" in md
        assert "No issues detected" in md

    def test_report_with_errors(self):
        report = DiagnosisReport(
            job_name="test", workdir="/tmp", files_scanned=["test.msg"],
        )
        report.add_event(DiagnosticEvent(
            category="license", severity="error", pattern_id="license_unavailable",
            file="test.msg", line=5, raw_line="License not available",
            suggestion="Check license server.",
        ))
        md = format_diagnosis_markdown(report)
        assert "License" in md
        assert "license_unavailable" in md
        assert "Check license server" in md
        assert "test.msg" in md

    def test_report_with_warnings_and_info(self):
        report = DiagnosisReport(
            job_name="test", workdir="/tmp", files_scanned=["test.msg"],
        )
        report.add_event(DiagnosticEvent(
            category="mesh", severity="warning", pattern_id="w1",
            file="test.msg", line=1, raw_line="mesh warning", suggestion="check",
        ))
        report.add_event(DiagnosticEvent(
            category="general", severity="info", pattern_id="i1",
            file="test.msg", line=2, raw_line="completed", suggestion="ok",
        ))
        md = format_diagnosis_markdown(report)
        assert "⚠️ 1 warning" in md
        assert "ℹ️ 1 info" in md

    def test_duplicate_patterns_deduplicated(self):
        report = DiagnosisReport(
            job_name="test", workdir="/tmp", files_scanned=["test.msg"],
        )
        for i in range(3):
            report.add_event(DiagnosticEvent(
                category="license", severity="error", pattern_id="license_unavailable",
                file="test.msg", line=i + 1, raw_line="License not available",
                suggestion="Check license server.",
            ))
        md = format_diagnosis_markdown(report)
        # Should only show license_unavailable once
        assert md.count("license_unavailable") == 1

    def test_format_compact(self):
        report = DiagnosisReport(
            job_name="test", workdir="/tmp", files_scanned=["test.msg"],
        )
        report.add_event(DiagnosticEvent(
            category="license", severity="error", pattern_id="e1",
            file="test.msg", line=1, raw_line="err", suggestion="fix",
        ))
        compact = format_diagnosis_compact(report)
        assert "test" in compact
        assert "e1" in compact
        assert "fix" in compact

    def test_format_compact_empty(self):
        report = DiagnosisReport(job_name="test", workdir="/tmp")
        compact = format_diagnosis_compact(report)
        assert "No issues detected" in compact


class TestPatternCoverage:
    """Verify all major pattern categories are covered."""

    CATEGORIES = [
        "license", "convergence", "model_setup", "contact",
        "material", "resources", "environment", "odb",
        "syntax", "explicit", "output", "scripting", "mesh", "general",
    ]

    def test_all_categories_covered(self):
        from abaqus_mcp_pro.solver_diagnosis import _PATTERNS
        covered = {p["category"] for p in _PATTERNS}
        for cat in self.CATEGORIES:
            assert cat in covered, f"Category '{cat}' not covered by any pattern"

    def test_pattern_count(self):
        from abaqus_mcp_pro.solver_diagnosis import _PATTERNS
        # Should have at least 30 patterns
        assert len(_PATTERNS) >= 30, f"Expected >= 30 patterns, got {len(_PATTERNS)}"
