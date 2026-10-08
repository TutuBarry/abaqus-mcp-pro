"""ODB Lens: declarative KPI extraction from Abaqus ODB files.

Define queries as JSON-like specs and extract max/min/sum/avg values
without writing procedural Python loops each time.

This module is self-contained (stdlib only) so it can run standalone
and be executed inside the Abaqus kernel via ``run_python``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class KPIQuery:
    """A single KPI extraction query."""

    query_id: str
    field: str  # e.g. "S", "U", "RF", "E", "PEEQ", "NT"
    component: str = ""  # e.g. "Mises", "U1", "S11", "RF2", "" for scalar
    step: str = ""  # step name, empty = first step
    frame: str = "last"  # "last", "first", or frame index (int)
    aggregation: str = "max"  # max, min, sum, avg, range, at_node, at_element
    region: str = ""  # node set, element set, or "" for ALL
    invariant: str = ""  # e.g. "Mises", "MaxPrincipal", "Tresca"


@dataclass
class KPIResult:
    """Result of a single KPI query."""

    query_id: str
    value: Any = None
    unit: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class KPILensReport:
    """Aggregated results for a batch of KPI queries."""

    odb_path: str
    results: list[KPIResult] = field(default_factory=list)
    error_count: int = 0

    def add_result(self, result: KPIResult) -> None:
        self.results.append(result)
        if result.error:
            self.error_count += 1

    def to_dict(self) -> dict:
        return {
            "odb_path": self.odb_path,
            "error_count": self.error_count,
            "results": [
                {
                    "query_id": r.query_id,
                    "value": r.value,
                    "unit": r.unit,
                    "error": r.error,
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Abaqus execution code
# ---------------------------------------------------------------------------

# This string is the minimal self-contained code that runs inside Abaqus.
# Placeholders: __ODB_PATH__, __QUERIES_JSON__

from inspect import getsource
from .kpi_runtime import query_odb

KPI_LENS_CODE = getsource(query_odb) + r'''
import json as _json
from odbAccess import openOdb
_odb = openOdb(path=__ODB_PATH__, readOnly=True)
try:
    _results = query_odb(_odb, _json.loads(__QUERIES_JSON__))
    result = {"odb_path": __ODB_PATH__, "results": _results,
              "error_count": sum(bool(r["error"]) for r in _results)}
finally:
    _odb.close()
'''


def extract_kpis(odb_path: str, queries: list[dict]) -> KPILensReport:
    report = KPILensReport(odb_path=odb_path)
    try:
        if not os.path.isfile(odb_path):
            raise FileNotFoundError(f"ODB not found: {odb_path}")
        from odbAccess import openOdb
        odb = openOdb(path=odb_path, readOnly=True)
        try:
            for item in query_odb(odb, queries):
                report.add_result(KPIResult(**item))
        finally:
            odb.close()
    except Exception as exc:
        for q in queries:
            report.add_result(KPIResult(query_id=q.get("query_id", "?"), error=str(exc)))
    return report


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def format_kpi_lens_markdown(report: KPILensReport) -> str:
    """Render a KPILensReport as structured Markdown."""
    lines: list[str] = []
    lines.append(f"## ODB Lens: `{os.path.basename(report.odb_path)}`")
    lines.append("")
    lines.append(f"**ODB:** `{report.odb_path}`")
    lines.append("")

    if not report.results:
        lines.append("No queries executed.")
        return "\n".join(lines)

    # Summary
    ok_count = sum(1 for r in report.results if r.ok)
    err_count = report.error_count
    lines.append(f"**Results:** {ok_count} OK, {err_count} error(s)")
    lines.append("")

    # Table header
    lines.append("| Query ID | Field | Value | Unit | Metadata |")
    lines.append("|----------|-------|-------|------|----------|")

    for r in report.results:
        qid = r.query_id
        if r.error:
            lines.append(f"| {qid} | — | ERROR | — | {r.error} |")
        else:
            val_str = f"{r.value:.6g}" if isinstance(r.value, (int, float)) else str(r.value)
            meta_str = ", ".join(f"{k}={v}" for k, v in r.metadata.items())
            lines.append(f"| {qid} | — | {val_str} | {r.unit} | {meta_str} |")

    lines.append("")
    lines.append("---")
    lines.append("*Extracted by abaqus-mcp-pro ODB Lens.*")
    return "\n".join(lines)


def format_kpi_lens_compact(report: KPILensReport) -> str:
    """Compact single-line-per-result format."""
    lines: list[str] = []
    lines.append(f"ODB Lens: {report.odb_path}")
    for r in report.results:
        if r.error:
            lines.append(f"  [ERR] {r.query_id}: {r.error}")
        else:
            val_str = f"{r.value:.6g}" if isinstance(r.value, (int, float)) else str(r.value)
            lines.append(f"  [OK]  {r.query_id}: {val_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Query builder helpers
# ---------------------------------------------------------------------------

def make_stress_query(
    query_id: str = "max_stress",
    component: str = "Mises",
    step: str = "",
    frame: str = "last",
    region: str = "",
) -> dict:
    """Create a standard stress KPI query."""
    return {
        "query_id": query_id,
        "field": "S",
        "component": component,
        "invariant": "Mises",
        "step": step,
        "frame": frame,
        "aggregation": "max",
        "region": region,
    }


def make_displacement_query(
    query_id: str = "max_displacement",
    component: str = "Magnitude",
    step: str = "",
    frame: str = "last",
    region: str = "",
) -> dict:
    """Create a standard displacement KPI query."""
    return {
        "query_id": query_id,
        "field": "U",
        "component": component,
        "step": step,
        "frame": frame,
        "aggregation": "max",
        "region": region,
    }


def make_reaction_force_query(
    query_id: str = "reaction_force",
    component: str = "RF2",
    step: str = "",
    frame: str = "last",
    region: str = "",
) -> dict:
    """Create a standard reaction force KPI query."""
    return {
        "query_id": query_id,
        "field": "RF",
        "component": component,
        "step": step,
        "frame": frame,
        "aggregation": "sum",
        "region": region,
    }


def make_plastic_strain_query(
    query_id: str = "max_peeq",
    step: str = "",
    frame: str = "last",
    region: str = "",
) -> dict:
    """Create a standard equivalent plastic strain KPI query."""
    return {
        "query_id": query_id,
        "field": "PEEQ",
        "step": step,
        "frame": frame,
        "aggregation": "max",
        "region": region,
    }
