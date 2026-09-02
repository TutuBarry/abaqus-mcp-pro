"""Unit tests for odb_lens module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.odb_lens import (
    KPIQuery,
    KPIResult,
    KPILensReport,
    extract_kpis,
    format_kpi_lens_markdown,
    format_kpi_lens_compact,
    make_stress_query,
    make_displacement_query,
    make_reaction_force_query,
    make_plastic_strain_query,
    KPI_LENS_CODE,
)


class TestKPIQuery:
    def test_defaults(self):
        q = KPIQuery(query_id="test", field="S")
        assert q.query_id == "test"
        assert q.field == "S"
        assert q.aggregation == "max"
        assert q.frame == "last"

    def test_full(self):
        q = KPIQuery(
            query_id="q1", field="U", component="U1",
            step="Step-1", frame="first", aggregation="min",
            region="Set-1", invariant="Magnitude",
        )
        assert q.query_id == "q1"
        assert q.component == "U1"
        assert q.aggregation == "min"


class TestKPIResult:
    def test_ok(self):
        r = KPIResult(query_id="q1", value=42.0)
        assert r.ok
        assert not r.error

    def test_error(self):
        r = KPIResult(query_id="q1", error="Something went wrong")
        assert not r.ok
        assert r.error == "Something went wrong"


class TestKPILensReport:
    def test_empty(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        assert report.odb_path == "/tmp/test.odb"
        assert report.results == []
        assert report.error_count == 0

    def test_add_result(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        report.add_result(KPIResult(query_id="q1", value=1.0))
        report.add_result(KPIResult(query_id="q2", error="fail"))
        assert len(report.results) == 2
        assert report.error_count == 1

    def test_to_dict(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        report.add_result(KPIResult(query_id="q1", value=3.14, metadata={"step": "Step-1"}))
        d = report.to_dict()
        assert d["odb_path"] == "/tmp/test.odb"
        assert d["error_count"] == 0
        assert len(d["results"]) == 1
        assert d["results"][0]["value"] == 3.14
        assert d["results"][0]["metadata"]["step"] == "Step-1"


class TestMakeQueryHelpers:
    def test_make_stress_query(self):
        q = make_stress_query("max_s", "Mises", "Step-1", "last", "CRITICAL")
        assert q["query_id"] == "max_s"
        assert q["field"] == "S"
        assert q["invariant"] == "Mises"
        assert q["aggregation"] == "max"
        assert q["region"] == "CRITICAL"

    def test_make_displacement_query(self):
        q = make_displacement_query("max_u", "Magnitude")
        assert q["field"] == "U"
        assert q["aggregation"] == "max"

    def test_make_reaction_force_query(self):
        q = make_reaction_force_query("rf", "RF2", region="FIXED")
        assert q["field"] == "RF"
        assert q["aggregation"] == "sum"
        assert q["region"] == "FIXED"

    def test_make_plastic_strain_query(self):
        q = make_plastic_strain_query("peeq_max")
        assert q["field"] == "PEEQ"
        assert q["aggregation"] == "max"


class TestExtractKPIs:
    def test_odb_not_found(self, tmp_path):
        odb_path = str(tmp_path / "nonexistent.odb")
        report = extract_kpis(odb_path, [{"query_id": "q1", "field": "S"}])
        assert report.error_count == 1
        assert "not found" in report.results[0].error

    def test_no_odb_access_outside_abaqus(self):
        """When run outside Abaqus, odbAccess is not available."""
        # This test verifies the graceful fallback
        report = extract_kpis("/nonexistent.odb", [{"query_id": "q1", "field": "S"}])
        assert report.error_count == 1
        # It will either say "not found" or "odbAccess not available"
        assert report.results[0].error


class TestFormatKPILensMarkdown:
    def test_empty_report(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        md = format_kpi_lens_markdown(report)
        assert "ODB Lens" in md
        assert "test.odb" in md
        assert "No queries executed" in md

    def test_report_with_results(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        report.add_result(KPIResult(
            query_id="max_stress", value=345.6,
            metadata={"step": "Step-1", "frame": 5, "value_count": 1234},
        ))
        report.add_result(KPIResult(
            query_id="bad_query", error="Field 'X' not available",
        ))
        md = format_kpi_lens_markdown(report)
        assert "max_stress" in md
        assert "345.6" in md
        assert "bad_query" in md
        assert "ERROR" in md
        assert "1 OK" in md
        assert "1 error" in md

    def test_report_scientific_notation(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        report.add_result(KPIResult(query_id="tiny", value=0.0000123))
        report.add_result(KPIResult(query_id="huge", value=1.23e7))
        md = format_kpi_lens_markdown(report)
        assert "1.23e" in md.lower() or "1.234e" in md.lower()

    def test_compact_format(self):
        report = KPILensReport(odb_path="/tmp/test.odb")
        report.add_result(KPIResult(query_id="q1", value=100.0))
        report.add_result(KPIResult(query_id="q2", error="fail"))
        compact = format_kpi_lens_compact(report)
        assert "q1" in compact
        assert "100" in compact
        assert "q2" in compact
        assert "fail" in compact


class TestKPILensCode:
    def test_code_contains_placeholders(self):
        assert "__ODB_PATH__" in KPI_LENS_CODE
        assert "__QUERIES_JSON__" in KPI_LENS_CODE

    def test_code_is_valid_python_syntax(self):
        import ast
        # The code is a template, replace placeholders with valid values
        code = KPI_LENS_CODE.replace("__ODB_PATH__", "'/tmp/test.odb'")
        code = code.replace("__QUERIES_JSON__", "'[]'")
        ast.parse(code)  # Should not raise SyntaxError
