"""Physics Contracts: define and validate KPI expectations.

Contracts let you specify expected ranges or thresholds for simulation
KPIs and automatically flag violations.

Contract types:
- range: value must be within [min, max]
- threshold_gt: value must be greater than X
- threshold_lt: value must be less than X
- exact: value must equal X (within tolerance)
- percent_change: change from baseline must be within X%
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Contract:
    """A single validation rule for a KPI."""

    contract_id: str
    kpi_name: str  # matches KPI query_id
    contract_type: str = "range"  # range, threshold_gt, threshold_lt, exact, pct_change
    expected: Any = None  # expected value(s)
    tolerance: float = 0.0  # allowed deviation (absolute for range, relative for exact)
    severity: str = "error"  # error or warning
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "kpi_name": self.kpi_name,
            "contract_type": self.contract_type,
            "expected": self.expected,
            "tolerance": self.tolerance,
            "severity": self.severity,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Contract":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContractResult:
    """Result of checking a single contract against a KPI value."""

    contract_id: str
    kpi_name: str
    passed: bool
    actual: Any = None
    expected_display: str = ""
    message: str = ""
    severity: str = "error"


@dataclass
class ContractReport:
    """Aggregated results for a batch of contract checks."""

    results: list[ContractResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0

    def add_result(self, result: ContractResult) -> None:
        self.results.append(result)
        if result.passed:
            self.passed_count += 1
        else:
            self.failed_count += 1

    def to_dict(self) -> dict:
        return {
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "results": [
                {
                    "contract_id": r.contract_id,
                    "kpi_name": r.kpi_name,
                    "passed": r.passed,
                    "actual": r.actual,
                    "expected_display": r.expected_display,
                    "message": r.message,
                    "severity": r.severity,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


def _check_single(contract: Contract, kpi_value: Any) -> ContractResult:
    """Check a single contract against a KPI value."""
    cid = contract.contract_id
    kpi = contract.kpi_name
    ctype = contract.contract_type
    expected = contract.expected
    tol = contract.tolerance
    sev = contract.severity

    # Handle None values
    if kpi_value is None or expected is None:
        return ContractResult(
            contract_id=cid, kpi_name=kpi, passed=False,
            actual=kpi_value, expected_display=str(expected),
            message="Cannot validate: value or expected is None",
            severity=sev,
        )

    try:
        actual = float(kpi_value)
    except (TypeError, ValueError):
        return ContractResult(
            contract_id=cid, kpi_name=kpi, passed=False,
            actual=kpi_value, expected_display=str(expected),
            message=f"Cannot convert value '{kpi_value}' to number",
            severity=sev,
        )

    if ctype == "range":
        # expected is [min, max] or {"min": ..., "max": ...}
        if isinstance(expected, (list, tuple)) and len(expected) == 2:
            lo, hi = float(expected[0]), float(expected[1])
        elif isinstance(expected, dict):
            lo = float(expected.get("min", float("-inf")))
            hi = float(expected.get("max", float("inf")))
        else:
            return ContractResult(
                contract_id=cid, kpi_name=kpi, passed=False,
                actual=actual, expected_display=str(expected),
                message="Invalid range format: expected [min, max] or {min, max}",
                severity=sev,
            )
        lo_eff = lo - tol
        hi_eff = hi + tol
        passed = lo_eff <= actual <= hi_eff
        exp_disp = f"[{lo}, {hi}]"
        if not passed:
            msg = f"Value {actual:.6g} outside range [{lo:.6g}, {hi:.6g}]"
        else:
            msg = f"Value {actual:.6g} within range [{lo:.6g}, {hi:.6g}]"

    elif ctype == "threshold_gt":
        threshold = float(expected)
        passed = actual > threshold - tol
        exp_disp = f"> {threshold}"
        if not passed:
            msg = f"Value {actual:.6g} not greater than {threshold:.6g}"
        else:
            msg = f"Value {actual:.6g} > {threshold:.6g}"

    elif ctype == "threshold_lt":
        threshold = float(expected)
        passed = actual < threshold + tol
        exp_disp = f"< {threshold}"
        if not passed:
            msg = f"Value {actual:.6g} not less than {threshold:.6g}"
        else:
            msg = f"Value {actual:.6g} < {threshold:.6g}"

    elif ctype == "exact":
        target = float(expected)
        if tol > 0:
            passed = abs(actual - target) <= tol
        else:
            passed = actual == target
        exp_disp = f"= {target} +/- {tol}"
        if not passed:
            msg = f"Value {actual:.6g} != {target:.6g} (diff: {abs(actual - target):.6g})"
        else:
            msg = f"Value {actual:.6g} == {target:.6g}"

    elif ctype == "pct_change":
        # expected is the baseline value; tolerance is max allowed % change
        baseline = float(expected)
        if baseline == 0:
            return ContractResult(
                contract_id=cid, kpi_name=kpi, passed=False,
                actual=actual, expected_display=f"baseline={baseline}, max_change={tol}%",
                message="Cannot compute percent change: baseline is zero",
                severity=sev,
            )
        pct = abs((actual - baseline) / baseline) * 100
        passed = pct <= tol
        exp_disp = f"change <= {tol}% from baseline {baseline}"
        if not passed:
            msg = f"Percent change {pct:.2f}% exceeds limit {tol}% (actual={actual:.6g}, baseline={baseline:.6g})"
        else:
            msg = f"Percent change {pct:.2f}% within limit {tol}% (actual={actual:.6g}, baseline={baseline:.6g})"

    else:
        return ContractResult(
            contract_id=cid, kpi_name=kpi, passed=False,
            actual=actual, expected_display=str(expected),
            message=f"Unknown contract type: {ctype}",
            severity=sev,
        )

    return ContractResult(
        contract_id=cid, kpi_name=kpi, passed=passed,
        actual=actual, expected_display=exp_disp,
        message=msg, severity=sev,
    )


def check_contracts(contracts: list[dict], kpis: dict[str, Any]) -> ContractReport:
    """Check a list of contracts against a dictionary of KPI values.

    Args:
        contracts: List of contract dicts (each with contract_id, kpi_name, etc.)
        kpis: Dict mapping KPI names to their values.

    Returns:
        ContractReport with all results.
    """
    report = ContractReport()
    for cdict in contracts:
        contract = Contract.from_dict(cdict)
        if contract.kpi_name not in kpis:
            # KPI key not present in results
            report.add_result(ContractResult(
                contract_id=contract.contract_id,
                kpi_name=contract.kpi_name,
                passed=False,
                actual=None,
                expected_display=str(contract.expected),
                message=f"KPI '{contract.kpi_name}' not found in results",
                severity=contract.severity,
            ))
        else:
            kpi_value = kpis[contract.kpi_name]
            report.add_result(_check_single(contract, kpi_value))
    return report


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def format_contracts_markdown(report: ContractReport) -> str:
    """Render a ContractReport as structured Markdown."""
    lines: list[str] = []
    lines.append("## Physics Contracts")
    lines.append("")

    total = report.passed_count + report.failed_count
    lines.append(f"**Results:** {report.passed_count} passed, {report.failed_count} failed (of {total})")
    lines.append("")

    if not report.results:
        lines.append("No contracts checked.")
        lines.append("")
        lines.append("---")
        lines.append("*Validated by abaqus-mcp-pro Physics Contracts.*")
        return "\n".join(lines)

    lines.append("| Contract | KPI | Status | Actual | Expected | Message |")
    lines.append("|----------|-----|--------|--------|----------|---------|")

    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        actual_str = f"{r.actual:.6g}" if isinstance(r.actual, (int, float)) else str(r.actual)
        lines.append(
            f"| {r.contract_id} | {r.kpi_name} | {status} | {actual_str} | {r.expected_display} | {r.message} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Validated by abaqus-mcp-pro Physics Contracts.*")
    return "\n".join(lines)


def format_contracts_compact(report: ContractReport) -> str:
    """Compact format for contract results."""
    lines: list[str] = []
    for r in report.results:
        marker = "[PASS]" if r.passed else "[FAIL]"
        lines.append(f"  {marker} {r.contract_id}: {r.message}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Contract builder helpers
# ---------------------------------------------------------------------------

def make_range_contract(
    contract_id: str,
    kpi_name: str,
    min_val: float,
    max_val: float,
    tolerance: float = 0.0,
    severity: str = "error",
    description: str = "",
) -> dict:
    """Create a range contract."""
    return {
        "contract_id": contract_id,
        "kpi_name": kpi_name,
        "contract_type": "range",
        "expected": [min_val, max_val],
        "tolerance": tolerance,
        "severity": severity,
        "description": description,
    }


def make_threshold_contract(
    contract_id: str,
    kpi_name: str,
    threshold: float,
    direction: str = "lt",
    tolerance: float = 0.0,
    severity: str = "error",
    description: str = "",
) -> dict:
    """Create a threshold contract (less-than or greater-than)."""
    return {
        "contract_id": contract_id,
        "kpi_name": kpi_name,
        "contract_type": f"threshold_{direction}",
        "expected": threshold,
        "tolerance": tolerance,
        "severity": severity,
        "description": description,
    }


def make_pct_change_contract(
    contract_id: str,
    kpi_name: str,
    baseline: float,
    max_pct: float,
    severity: str = "error",
    description: str = "",
) -> dict:
    """Create a percent-change contract."""
    return {
        "contract_id": contract_id,
        "kpi_name": kpi_name,
        "contract_type": "pct_change",
        "expected": baseline,
        "tolerance": max_pct,
        "severity": severity,
        "description": description,
    }
