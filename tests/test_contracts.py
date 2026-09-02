"""Unit tests for contracts module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.contracts import (
    Contract,
    ContractResult,
    ContractReport,
    check_contracts,
    format_contracts_markdown,
    format_contracts_compact,
    make_range_contract,
    make_threshold_contract,
    make_pct_change_contract,
)


# ---------------------------------------------------------------------------
# Contract dataclass
# ---------------------------------------------------------------------------

class TestContract:
    def test_defaults(self):
        c = Contract(contract_id="c1", kpi_name="max_stress")
        assert c.contract_id == "c1"
        assert c.kpi_name == "max_stress"
        assert c.contract_type == "range"
        assert c.expected is None
        assert c.tolerance == 0.0
        assert c.severity == "error"
        assert c.description == ""

    def test_full(self):
        c = Contract(
            contract_id="c1", kpi_name="max_stress",
            contract_type="threshold_gt", expected=100.0,
            tolerance=1.0, severity="warning", description="Stress must be above yield",
        )
        assert c.expected == 100.0
        assert c.severity == "warning"

    def test_to_dict(self):
        c = Contract(contract_id="c1", kpi_name="stress", expected=[0, 500])
        d = c.to_dict()
        assert d["contract_id"] == "c1"
        assert d["expected"] == [0, 500]

    def test_from_dict(self):
        d = {"contract_id": "c1", "kpi_name": "stress", "contract_type": "range", "extra": "ignored"}
        c = Contract.from_dict(d)
        assert c.contract_id == "c1"
        assert c.kpi_name == "stress"
        assert not hasattr(c, "extra")

    def test_from_dict_partial(self):
        d = {"contract_id": "c1", "kpi_name": "my_kpi"}
        c = Contract.from_dict(d)
        assert c.contract_id == "c1"
        assert c.kpi_name == "my_kpi"


# ---------------------------------------------------------------------------
# ContractResult dataclass
# ---------------------------------------------------------------------------

class TestContractResult:
    def test_defaults(self):
        r = ContractResult(contract_id="c1", kpi_name="stress", passed=False)
        assert r.actual is None
        assert r.expected_display == ""
        assert r.message == ""
        assert r.severity == "error"

    def test_full(self):
        r = ContractResult(
            contract_id="c1", kpi_name="stress", passed=True,
            actual=345.0, expected_display="[0, 500]", message="OK", severity="warning",
        )
        assert r.passed
        assert r.actual == 345.0


# ---------------------------------------------------------------------------
# ContractReport dataclass
# ---------------------------------------------------------------------------

class TestContractReport:
    def test_empty(self):
        r = ContractReport()
        assert r.passed_count == 0
        assert r.failed_count == 0
        assert r.results == []

    def test_add_result_pass(self):
        r = ContractReport()
        r.add_result(ContractResult(contract_id="c1", kpi_name="s", passed=True))
        assert r.passed_count == 1
        assert r.failed_count == 0

    def test_add_result_fail(self):
        r = ContractReport()
        r.add_result(ContractResult(contract_id="c1", kpi_name="s", passed=False))
        assert r.passed_count == 0
        assert r.failed_count == 1

    def test_add_mixed(self):
        r = ContractReport()
        r.add_result(ContractResult(contract_id="c1", kpi_name="s", passed=True))
        r.add_result(ContractResult(contract_id="c2", kpi_name="s", passed=False))
        r.add_result(ContractResult(contract_id="c3", kpi_name="s", passed=True))
        assert r.passed_count == 2
        assert r.failed_count == 1
        assert len(r.results) == 3

    def test_to_dict(self):
        r = ContractReport()
        r.add_result(ContractResult(
            contract_id="c1", kpi_name="s", passed=True, actual=42.0,
            expected_display="[0, 100]", message="OK",
        ))
        d = r.to_dict()
        assert d["passed_count"] == 1
        assert d["failed_count"] == 0
        assert d["results"][0]["contract_id"] == "c1"
        assert d["results"][0]["actual"] == 42.0


# ---------------------------------------------------------------------------
# check_contracts - range
# ---------------------------------------------------------------------------

class TestRangeContracts:
    def test_value_within_range(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500]}],
            {"s": 345},
        )
        assert report.passed_count == 1
        assert report.failed_count == 0
        assert "within range" in report.results[0].message

    def test_value_below_range(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [100, 500]}],
            {"s": 50},
        )
        assert report.failed_count == 1
        assert "outside range" in report.results[0].message

    def test_value_above_range(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500]}],
            {"s": 600},
        )
        assert report.failed_count == 1

    def test_range_with_tolerance(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500], "tolerance": 10}],
            {"s": 505},
        )
        assert report.passed_count == 1

    def test_range_dict_format(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": {"min": 0, "max": 500}}],
            {"s": 345},
        )
        assert report.passed_count == 1

    def test_range_dict_min_only(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": {"min": 100}}],
            {"s": 200},
        )
        assert report.passed_count == 1

    def test_range_dict_max_only(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": {"max": 500}}],
            {"s": 200},
        )
        assert report.passed_count == 1

    def test_range_invalid_format(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": "bad"}],
            {"s": 100},
        )
        assert report.failed_count == 1
        assert "Invalid range" in report.results[0].message

    def test_range_at_boundary(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500]}],
            {"s": 500},
        )
        assert report.passed_count == 1


# ---------------------------------------------------------------------------
# check_contracts - threshold_gt
# ---------------------------------------------------------------------------

class TestThresholdGt:
    def test_value_above_threshold(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "threshold_gt", "expected": 100}],
            {"s": 150},
        )
        assert report.passed_count == 1

    def test_value_below_threshold(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "threshold_gt", "expected": 100}],
            {"s": 50},
        )
        assert report.failed_count == 1
        assert "not greater than" in report.results[0].message

    def test_value_equal_threshold_no_tolerance(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "threshold_gt", "expected": 100, "tolerance": 0.0}],
            {"s": 100},
        )
        assert report.failed_count == 1

    def test_value_equal_threshold_with_tolerance(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "threshold_gt", "expected": 100, "tolerance": 1.0}],
            {"s": 100},
        )
        assert report.passed_count == 1


# ---------------------------------------------------------------------------
# check_contracts - threshold_lt
# ---------------------------------------------------------------------------

class TestThresholdLt:
    def test_value_below_threshold(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "d", "contract_type": "threshold_lt", "expected": 10}],
            {"d": 5},
        )
        assert report.passed_count == 1

    def test_value_above_threshold(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "d", "contract_type": "threshold_lt", "expected": 10}],
            {"d": 15},
        )
        assert report.failed_count == 1
        assert "not less than" in report.results[0].message

    def test_with_tolerance(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "d", "contract_type": "threshold_lt", "expected": 10, "tolerance": 1.0}],
            {"d": 10.5},
        )
        assert report.passed_count == 1


# ---------------------------------------------------------------------------
# check_contracts - exact
# ---------------------------------------------------------------------------

class TestExactContracts:
    def test_exact_match(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "exact", "expected": 345.0}],
            {"s": 345.0},
        )
        assert report.passed_count == 1

    def test_exact_mismatch(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "exact", "expected": 345.0}],
            {"s": 346.0},
        )
        assert report.failed_count == 1
        assert "!=" in report.results[0].message

    def test_exact_with_tolerance(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "exact", "expected": 345.0, "tolerance": 1.0}],
            {"s": 345.5},
        )
        assert report.passed_count == 1

    def test_exact_tolerance_exceeded(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "exact", "expected": 345.0, "tolerance": 0.1}],
            {"s": 345.5},
        )
        assert report.failed_count == 1


# ---------------------------------------------------------------------------
# check_contracts - pct_change
# ---------------------------------------------------------------------------

class TestPctChange:
    def test_within_limit(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "pct_change", "expected": 100, "tolerance": 10}],
            {"s": 105},
        )
        assert report.passed_count == 1

    def test_exceeds_limit(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "pct_change", "expected": 100, "tolerance": 10}],
            {"s": 120},
        )
        assert report.failed_count == 1
        assert "exceeds limit" in report.results[0].message

    def test_zero_baseline(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "pct_change", "expected": 0, "tolerance": 10}],
            {"s": 5},
        )
        assert report.failed_count == 1
        assert "baseline is zero" in report.results[0].message

    def test_no_change(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "pct_change", "expected": 100, "tolerance": 10}],
            {"s": 100},
        )
        assert report.passed_count == 1

    def test_negative_change(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "pct_change", "expected": 100, "tolerance": 10}],
            {"s": 90},
        )
        assert report.passed_count == 1


# ---------------------------------------------------------------------------
# check_contracts - multiple contracts
# ---------------------------------------------------------------------------

class TestMultipleContracts:
    def test_all_pass(self):
        contracts = [
            {"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500]},
            {"contract_id": "c2", "kpi_name": "d", "contract_type": "threshold_lt", "expected": 10},
        ]
        kpis = {"s": 345, "d": 5}
        report = check_contracts(contracts, kpis)
        assert report.passed_count == 2
        assert report.failed_count == 0

    def test_mixed(self):
        contracts = [
            {"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500]},
            {"contract_id": "c2", "kpi_name": "d", "contract_type": "threshold_lt", "expected": 10},
        ]
        kpis = {"s": 600, "d": 5}
        report = check_contracts(contracts, kpis)
        assert report.passed_count == 1
        assert report.failed_count == 1

    def test_all_fail(self):
        contracts = [
            {"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 500]},
            {"contract_id": "c2", "kpi_name": "d", "contract_type": "threshold_lt", "expected": 10},
        ]
        kpis = {"s": 600, "d": 15}
        report = check_contracts(contracts, kpis)
        assert report.passed_count == 0
        assert report.failed_count == 2


# ---------------------------------------------------------------------------
# check_contracts - edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_kpi_not_found(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "missing_kpi", "contract_type": "range", "expected": [0, 100]}],
            {"s": 50},
        )
        assert report.failed_count == 1
        assert "not found" in report.results[0].message

    def test_none_value(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 100]}],
            {"s": None},
        )
        assert report.failed_count == 1
        assert "Cannot validate" in report.results[0].message

    def test_none_expected(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": None}],
            {"s": 50},
        )
        assert report.failed_count == 1
        assert "Cannot validate" in report.results[0].message

    def test_non_numeric_value(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 100]}],
            {"s": "hello"},
        )
        assert report.failed_count == 1
        assert "Cannot convert" in report.results[0].message

    def test_unknown_contract_type(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "unknown_type", "expected": 100}],
            {"s": 50},
        )
        assert report.failed_count == 1
        assert "Unknown contract type" in report.results[0].message

    def test_empty_contracts(self):
        report = check_contracts([], {"s": 50})
        assert report.passed_count == 0
        assert report.failed_count == 0
        assert report.results == []

    def test_empty_kpis(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 100]}],
            {},
        )
        assert report.failed_count == 1
        assert "not found" in report.results[0].message

    def test_severity_warning(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0, 100], "severity": "warning"}],
            {"s": 200},
        )
        assert report.failed_count == 1
        assert report.results[0].severity == "warning"

    def test_float_kpi(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [0.0, 1.0]}],
            {"s": 0.5},
        )
        assert report.passed_count == 1

    def test_negative_values(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "range", "expected": [-100, 0]}],
            {"s": -50},
        )
        assert report.passed_count == 1

    def test_very_large_values(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "threshold_gt", "expected": 1e9}],
            {"s": 1.5e9},
        )
        assert report.passed_count == 1

    def test_very_small_values(self):
        report = check_contracts(
            [{"contract_id": "c1", "kpi_name": "s", "contract_type": "threshold_lt", "expected": 1e-9}],
            {"s": 1e-12},
        )
        assert report.passed_count == 1


# ---------------------------------------------------------------------------
# format_contracts_markdown
# ---------------------------------------------------------------------------

class TestFormatContractsMarkdown:
    def test_empty_report(self):
        report = ContractReport()
        md = format_contracts_markdown(report)
        assert "Physics Contracts" in md
        assert "No contracts checked" in md

    def test_with_passed(self):
        report = ContractReport()
        report.add_result(ContractResult(
            contract_id="c1", kpi_name="max_stress", passed=True,
            actual=345.0, expected_display="[0, 500]", message="OK",
        ))
        md = format_contracts_markdown(report)
        assert "c1" in md
        assert "max_stress" in md
        assert "PASS" in md
        assert "345" in md

    def test_with_failed(self):
        report = ContractReport()
        report.add_result(ContractResult(
            contract_id="c1", kpi_name="max_stress", passed=False,
            actual=600.0, expected_display="[0, 500]", message="Outside range",
        ))
        md = format_contracts_markdown(report)
        assert "FAIL" in md
        assert "Outside range" in md

    def test_mixed_results(self):
        report = ContractReport()
        report.add_result(ContractResult(
            contract_id="c1", kpi_name="s", passed=True, actual=100.0,
            expected_display="[0, 500]", message="OK",
        ))
        report.add_result(ContractResult(
            contract_id="c2", kpi_name="d", passed=False, actual=15.0,
            expected_display="< 10", message="Not less than 10",
        ))
        md = format_contracts_markdown(report)
        assert "1 passed" in md
        assert "1 failed" in md
        assert "PASS" in md
        assert "FAIL" in md

    def test_footer(self):
        report = ContractReport()
        md = format_contracts_markdown(report)
        assert "Validated by abaqus-mcp-pro Physics Contracts" in md

    def test_non_numeric_actual(self):
        report = ContractReport()
        report.add_result(ContractResult(
            contract_id="c1", kpi_name="s", passed=False,
            actual="N/A", expected_display="[0, 500]", message="bad",
        ))
        md = format_contracts_markdown(report)
        assert "N/A" in md


# ---------------------------------------------------------------------------
# format_contracts_compact
# ---------------------------------------------------------------------------

class TestFormatContractsCompact:
    def test_pass(self):
        report = ContractReport()
        report.add_result(ContractResult(
            contract_id="c1", kpi_name="s", passed=True,
            actual=100.0, expected_display="[0, 500]", message="OK",
        ))
        compact = format_contracts_compact(report)
        assert "[PASS]" in compact
        assert "c1" in compact

    def test_fail(self):
        report = ContractReport()
        report.add_result(ContractResult(
            contract_id="c1", kpi_name="s", passed=False,
            actual=600.0, expected_display="[0, 500]", message="Outside range",
        ))
        compact = format_contracts_compact(report)
        assert "[FAIL]" in compact

    def test_multiple(self):
        report = ContractReport()
        report.add_result(ContractResult(contract_id="c1", kpi_name="s", passed=True, message="m1"))
        report.add_result(ContractResult(contract_id="c2", kpi_name="d", passed=False, message="m2"))
        compact = format_contracts_compact(report)
        assert "m1" in compact
        assert "m2" in compact


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

class TestBuilderHelpers:
    def test_make_range(self):
        c = make_range_contract("c1", "s", 0, 500, tolerance=5.0, severity="warning", description="desc")
        assert c["contract_id"] == "c1"
        assert c["kpi_name"] == "s"
        assert c["contract_type"] == "range"
        assert c["expected"] == [0, 500]
        assert c["tolerance"] == 5.0
        assert c["severity"] == "warning"
        assert c["description"] == "desc"

    def test_make_range_defaults(self):
        c = make_range_contract("c1", "s", 0, 500)
        assert c["tolerance"] == 0.0
        assert c["severity"] == "error"
        assert c["description"] == ""

    def test_make_threshold_gt(self):
        c = make_threshold_contract("c1", "s", 100, direction="gt")
        assert c["contract_type"] == "threshold_gt"

    def test_make_threshold_lt(self):
        c = make_threshold_contract("c1", "s", 100, direction="lt")
        assert c["contract_type"] == "threshold_lt"

    def test_make_threshold_defaults(self):
        c = make_threshold_contract("c1", "s", 100, direction="lt")
        assert c["tolerance"] == 0.0
        assert c["severity"] == "error"

    def test_make_pct_change(self):
        c = make_pct_change_contract("c1", "s", baseline=100, max_pct=10, severity="warning")
        assert c["contract_type"] == "pct_change"
        assert c["expected"] == 100
        assert c["tolerance"] == 10
        assert c["severity"] == "warning"

    def test_make_pct_change_defaults(self):
        c = make_pct_change_contract("c1", "s", baseline=100, max_pct=10)
        assert c["severity"] == "error"
        assert c["description"] == ""


# ---------------------------------------------------------------------------
# Round-trip: builder -> check -> format
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Verify that contracts built with make_* helpers pass through check_contracts correctly."""

    def test_range_roundtrip(self):
        c = make_range_contract("c1", "stress", 0, 500)
        report = check_contracts([c], {"stress": 345})
        assert report.passed_count == 1

    def test_threshold_gt_roundtrip(self):
        c = make_threshold_contract("c1", "stress", 100, direction="gt")
        report = check_contracts([c], {"stress": 150})
        assert report.passed_count == 1

    def test_threshold_lt_roundtrip(self):
        c = make_threshold_contract("c1", "disp", 10, direction="lt")
        report = check_contracts([c], {"disp": 5})
        assert report.passed_count == 1

    def test_pct_change_roundtrip(self):
        c = make_pct_change_contract("c1", "stress", baseline=100, max_pct=10)
        report = check_contracts([c], {"stress": 105})
        assert report.passed_count == 1

    def test_roundtrip_to_markdown(self):
        c = make_range_contract("c1", "stress", 0, 500)
        report = check_contracts([c], {"stress": 345})
        md = format_contracts_markdown(report)
        assert "c1" in md
        assert "PASS" in md
