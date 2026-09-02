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

KPI_LENS_CODE = r'''
import json as _json
import os as _os

_odb_path = __ODB_PATH__
_queries = _json.loads(__QUERIES_JSON__)

_results = []

try:
    from odbAccess import openOdb
    _odb = openOdb(path=_odb_path, readOnly=True)
except Exception as _exc:
    for _q in _queries:
        _results.append({
            "query_id": _q.get("query_id", "?"),
            "value": None,
            "unit": "",
            "error": "Cannot open ODB: " + str(_exc),
            "metadata": {},
        })
    result = {"odb_path": _odb_path, "error_count": len(_queries), "results": _results}
else:
    try:
        # Resolve step
        _step_names = list(_odb.steps.keys())
        if not _step_names:
            raise ValueError("ODB has no steps")

        for _q in _queries:
            _qid = _q.get("query_id", "?")
            _field_name = _q.get("field", "S")
            _component = _q.get("component", "")
            _step_name = _q.get("step", "")
            _frame_spec = _q.get("frame", "last")
            _aggregation = _q.get("aggregation", "max")
            _region = _q.get("region", "")
            _invariant = _q.get("invariant", "")

            _meta = {}

            try:
                # Resolve step
                if _step_name and _step_name in _odb.steps:
                    _step = _odb.steps[_step_name]
                else:
                    _step = _odb.steps[_step_names[0]]
                _meta["step"] = _step.name

                # Resolve frame
                _frames = _step.frames
                if not _frames:
                    raise ValueError("Step has no frames")
                if _frame_spec == "last":
                    _frame = _frames[-1]
                elif _frame_spec == "first":
                    _frame = _frames[0]
                else:
                    try:
                        _idx = int(_frame_spec)
                        _frame = _frames[_idx]
                    except (ValueError, IndexError):
                        _frame = _frames[-1]
                _meta["frame"] = _frame.frameId
                _meta["frameValue"] = _frame.frameValue

                # Get field output
                if _field_name not in _frame.fieldOutputs:
                    raise ValueError(
                        "Field '%s' not available. Available: %s"
                        % (_field_name, list(_frame.fieldOutputs.keys()))
                    )
                _fo = _frame.fieldOutputs[_field_name]

                # Get subfield (region)
                if _region:
                    _subfield = _fo.getSubset(region=_region)
                else:
                    _subfield = _fo

                # Determine what to extract
                _values = []
                if _invariant:
                    # Use invariant (e.g. Mises from S)
                    _inv_data = _subfield.getInvariant(_invariant)
                    _values = [v.data for v in _inv_data.values]
                elif _component:
                    # Use component label
                    _comp_data = _subfield.getSubset(componentLabel=_component)
                    _values = [v.data for v in _comp_data.values]
                else:
                    # Scalar field (e.g. PEEQ, NT) - get all values
                    _values = [v.data for v in _subfield.values]

                if not _values:
                    raise ValueError("No values extracted")

                # Aggregate
                if _aggregation == "max":
                    _value = max(_values)
                elif _aggregation == "min":
                    _value = min(_values)
                elif _aggregation == "sum":
                    _value = sum(_values)
                elif _aggregation == "avg":
                    _value = sum(_values) / len(_values)
                elif _aggregation == "range":
                    _value = max(_values) - min(_values)
                elif _aggregation == "abs_max":
                    _abs = [abs(v) for v in _values]
                    _value = max(_abs)
                else:
                    _value = _values[0]  # raw list

                _meta["value_count"] = len(_values)

                _results.append({
                    "query_id": _qid,
                    "value": _value,
                    "unit": "",
                    "error": "",
                    "metadata": _meta,
                })
            except Exception as _exc:
                _results.append({
                    "query_id": _qid,
                    "value": None,
                    "unit": "",
                    "error": str(_exc),
                    "metadata": _meta,
                })
    finally:
        _odb.close()

    result = {
        "odb_path": _odb_path,
        "error_count": sum(1 for r in _results if r["error"]),
        "results": _results,
    }
'''


# ---------------------------------------------------------------------------
# Standalone API (for use outside Abaqus)
# ---------------------------------------------------------------------------

def extract_kpis(odb_path: str, queries: list[dict]) -> KPILensReport:
    """Run KPI queries against an ODB file (standalone, uses Abaqus Python).

    **Note:** This function requires the Abaqus Python environment
    (``odbAccess`` module). For MCP usage, prefer the ``extract_kpis``
    tool which executes inside the Abaqus kernel.
    """
    report = KPILensReport(odb_path=odb_path)
    if not os.path.isfile(odb_path):
        for q in queries:
            report.add_result(KPIResult(
                query_id=q.get("query_id", "?"),
                error=f"ODB not found: {odb_path}",
            ))
        return report

    try:
        from odbAccess import openOdb
    except ImportError:
        for q in queries:
            report.add_result(KPIResult(
                query_id=q.get("query_id", "?"),
                error="odbAccess not available (not in Abaqus Python environment)",
            ))
        return report

    odb = None
    try:
        odb = openOdb(path=odb_path, readOnly=True)
        step_names = list(odb.steps.keys())
        if not step_names:
            for q in queries:
                report.add_result(KPIResult(query_id=q.get("query_id", "?"), error="ODB has no steps"))
            return report

        for q in queries:
            qid = q.get("query_id", "?")
            field_name = q.get("field", "S")
            component = q.get("component", "")
            step_name = q.get("step", "")
            frame_spec = q.get("frame", "last")
            aggregation = q.get("aggregation", "max")
            region = q.get("region", "")
            invariant = q.get("invariant", "")

            meta: dict[str, Any] = {}

            try:
                step = odb.steps[step_name] if step_name and step_name in odb.steps else odb.steps[step_names[0]]
                meta["step"] = step.name

                frames = step.frames
                if not frames:
                    raise ValueError("Step has no frames")
                if frame_spec == "last":
                    frame = frames[-1]
                elif frame_spec == "first":
                    frame = frames[0]
                else:
                    try:
                        frame = frames[int(frame_spec)]
                    except (ValueError, IndexError):
                        frame = frames[-1]
                meta["frame"] = frame.frameId
                meta["frameValue"] = frame.frameValue

                if field_name not in frame.fieldOutputs:
                    raise ValueError(f"Field '{field_name}' not available. Available: {list(frame.fieldOutputs.keys())}")
                fo = frame.fieldOutputs[field_name]

                subfield = fo.getSubset(region=region) if region else fo

                values = []
                if invariant:
                    values = [v.data for v in subfield.getInvariant(invariant).values]
                elif component:
                    values = [v.data for v in subfield.getSubset(componentLabel=component).values]
                else:
                    values = [v.data for v in subfield.values]

                if not values:
                    raise ValueError("No values extracted")

                if aggregation == "max":
                    value = max(values)
                elif aggregation == "min":
                    value = min(values)
                elif aggregation == "sum":
                    value = sum(values)
                elif aggregation == "avg":
                    value = sum(values) / len(values)
                elif aggregation == "range":
                    value = max(values) - min(values)
                elif aggregation == "abs_max":
                    value = max(abs(v) for v in values)
                else:
                    value = values

                meta["value_count"] = len(values)
                report.add_result(KPIResult(query_id=qid, value=value, metadata=meta))
            except Exception as exc:
                report.add_result(KPIResult(query_id=qid, error=str(exc), metadata=meta))

    except Exception as exc:
        for q in queries:
            report.add_result(KPIResult(query_id=q.get("query_id", "?"), error=str(exc)))
    finally:
        if odb is not None:
            odb.close()

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
