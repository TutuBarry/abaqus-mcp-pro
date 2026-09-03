"""Simulation Report: generate comprehensive Markdown reports combining
multiple analysis results into a single structured document.

Combines:
- Capsule snapshot (model, job, files)
- KPI Lens results (ODB extraction)
- Physics Contracts validation
- Solver Doctor diagnosis
- Silent Failure Detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .capsule import CapsuleEntry
from .contracts import ContractReport
from .solver_diagnosis import DiagnosisReport
from .odb_lens import KPILensReport
from .silent_failures import SilentFailureReport


# ---------------------------------------------------------------------------
# Report data model
# ---------------------------------------------------------------------------

@dataclass
class SimulationReport:
    """Aggregated simulation report combining all analysis results."""

    title: str = "Abaqus Simulation Report"
    generated_at: str = ""

    # Sections (all optional - only populated sections appear in the report)
    capsule: CapsuleEntry | None = None
    kpi_lens: KPILensReport | None = None
    contracts: ContractReport | None = None
    diagnosis: DiagnosisReport | None = None
    silent_failures: SilentFailureReport | None = None
    screenshots: list[str] = field(default_factory=list)  # file paths
    extra_sections: dict[str, str] = field(default_factory=dict)  # custom sections

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def format_report_markdown(report: SimulationReport) -> str:
    """Render a full simulation report as structured Markdown.

    Only sections with data are rendered. Empty sections are skipped.
    """
    lines: list[str] = []

    # ── Header ──
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Table of Contents ──
    lines.append("## Contents")
    lines.append("")
    toc: list[str] = []
    if report.capsule:
        toc.append("1. [Model & Job Summary](#model--job-summary)")
    if report.kpi_lens:
        toc.append("2. [KPI Lens Results](#kpi-lens-results)")
    if report.contracts:
        toc.append("3. [Physics Contracts](#physics-contracts)")
    if report.diagnosis:
        toc.append("4. [Solver Diagnosis](#solver-diagnosis)")
    if report.silent_failures:
        toc.append("5. [Silent Failure Detection](#silent-failure-detection)")
    if report.screenshots:
        toc.append("6. [Screenshots](#screenshots)")
    for key in report.extra_sections:
        toc.append(f"- [{key}](#{key.lower().replace(' ', '-')})")
    for item in toc:
        lines.append(item)
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 1: Model & Job Summary ──
    if report.capsule:
        lines.append("## Model & Job Summary")
        lines.append("")
        capsule = report.capsule

        # Basic info
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        if capsule.abaqus_version:
            lines.append(f"| Abaqus Version | {capsule.abaqus_version} |")
        if capsule.job_name:
            lines.append(f"| Job Name | {capsule.job_name} |")
        if capsule.job_status:
            lines.append(f"| Job Status | {capsule.job_status} |")
        if capsule.workdir:
            lines.append(f"| Working Directory | {capsule.workdir} |")
        if capsule.notes:
            lines.append(f"| Notes | {capsule.notes} |")
        lines.append("")

        # Model info
        if capsule.model_info:
            for model_name, info in capsule.model_info.items():
                lines.append(f"### Model: `{model_name}`")
                lines.append("")
                if isinstance(info, dict):
                    for key, val in info.items():
                        if isinstance(val, list) and val:
                            lines.append(f"- **{key}:** {', '.join(str(v) for v in val)}")
                        elif val:
                            lines.append(f"- **{key}:** {val}")
                    lines.append("")

        # Output files
        if capsule.files:
            lines.append("### Output Files")
            lines.append("")
            lines.append("| File | Size |")
            lines.append("|------|------|")
            for f in capsule.files:
                name = f.get("name", "?")
                size = f.get("size", 0)
                if isinstance(size, (int, float)):
                    if size > 1_000_000:
                        size_str = f"{size / 1_000_000:.1f} MB"
                    elif size > 1_000:
                        size_str = f"{size / 1_000:.1f} KB"
                    else:
                        size_str = f"{size} B"
                else:
                    size_str = str(size)
                lines.append(f"| {name} | {size_str} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── Section 2: KPI Lens Results ──
    if report.kpi_lens:
        lines.append("## KPI Lens Results")
        lines.append("")
        kpi = report.kpi_lens
        lines.append(f"**ODB:** `{kpi.odb_path}`")
        lines.append("")
        if kpi.error_count > 0:
            lines.append(f"**Errors:** {kpi.error_count}")
            lines.append("")

        if kpi.results:
            lines.append("| Query | Field | Value | Aggregation | Frame |")
            lines.append("|-------|-------|-------|-------------|-------|")
            for r in kpi.results:
                if r.error:
                    lines.append(f"| {r.query_id} | - | ERROR: {r.error} | - | - |")
                else:
                    val_str = f"{r.value:.6g}" if isinstance(r.value, (int, float)) else str(r.value)
                    meta = r.metadata or {}
                    frame = meta.get("frame", "-")
                    aggregation = meta.get("aggregation", "-")
                    lines.append(f"| {r.query_id} | {meta.get('field', '-')} | {val_str} | {aggregation} | {frame} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── Section 3: Physics Contracts ──
    if report.contracts:
        lines.append("## Physics Contracts")
        lines.append("")
        ct = report.contracts
        total = ct.passed_count + ct.failed_count
        pass_rate = (ct.passed_count / total * 100) if total > 0 else 0
        lines.append(f"**Results:** {ct.passed_count} passed, {ct.failed_count} failed ({pass_rate:.0f}% pass rate)")
        lines.append("")

        if ct.results:
            lines.append("| Contract | KPI | Status | Actual | Expected | Message |")
            lines.append("|----------|-----|--------|--------|----------|---------|")
            for r in ct.results:
                status = "PASS" if r.passed else "FAIL"
                actual_str = f"{r.actual:.6g}" if isinstance(r.actual, (int, float)) else str(r.actual)
                lines.append(f"| {r.contract_id} | {r.kpi_name} | {status} | {actual_str} | {r.expected_display} | {r.message} |")
            lines.append("")

        # Overall verdict
        if ct.failed_count == 0 and total > 0:
            lines.append("**Verdict: ALL CONTRACTS PASSED**")
        elif ct.failed_count > 0:
            lines.append(f"**Verdict: {ct.failed_count} CONTRACT(S) FAILED**")
        lines.append("")

        lines.append("---")
        lines.append("")

    # ── Section 4: Solver Diagnosis ──
    if report.diagnosis:
        lines.append("## Solver Diagnosis")
        lines.append("")
        diag = report.diagnosis
        lines.append(f"**Job:** `{diag.job_name}`")
        lines.append(f"**Files scanned:** {', '.join(diag.files_scanned) if diag.files_scanned else 'none'}")
        lines.append("")

        # Summary counts
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| Error | {diag.error_count} |")
        lines.append(f"| Warning | {diag.warning_count} |")
        lines.append(f"| Info | {diag.info_count} |")
        lines.append("")

        if diag.events:
            # Group by severity
            errors = [e for e in diag.events if e.severity == "error"]
            warnings = [e for e in diag.events if e.severity == "warning"]
            infos = [e for e in diag.events if e.severity == "info"]

            if errors:
                lines.append("### Errors")
                lines.append("")
                for e in errors:
                    lines.append(f"- **{e.pattern_id}** (line {e.line} in `{e.file}`): {e.suggestion}")
                lines.append("")

            if warnings:
                lines.append("### Warnings")
                lines.append("")
                for e in warnings:
                    lines.append(f"- **{e.pattern_id}** (line {e.line} in `{e.file}`): {e.suggestion}")
                lines.append("")

            if infos:
                lines.append("### Info")
                lines.append("")
                for e in infos:
                    lines.append(f"- **{e.pattern_id}**: {e.suggestion}")
                lines.append("")

        lines.append("---")
        lines.append("")

    # ── Section 5: Silent Failure Detection ──
    if report.silent_failures:
        lines.append("## Silent Failure Detection")
        lines.append("")
        sf = report.silent_failures
        lines.append(f"**Model:** `{sf.model_name}`")
        lines.append(f"**Checks:** {sf.failed_count} failed, {sf.warning_count} warnings, {sf.passed_count} passed (of {len(sf.findings)})")
        lines.append("")

        if sf.findings:
            # Group by category
            from collections import defaultdict
            grouped: dict[str, list] = defaultdict(list)
            for f in sf.findings:
                grouped[f.category].append(f)

            for cat_name, cat_findings in sorted(grouped.items()):
                lines.append(f"### {cat_name.replace('_', ' ').title()}")
                lines.append("")
                for f in cat_findings:
                    marker = "[FAIL]" if not f.passed else "[PASS]"
                    lines.append(f"**{marker} {f.check_id}**")
                    lines.append(f"> {f.detail}")
                    if f.suggestion:
                        lines.append(f"> Suggestion: {f.suggestion}")
                    if f.evidence:
                        ev = ", ".join(f"{k}={v}" for k, v in f.evidence.items())
                        lines.append(f"> Evidence: {ev}")
                    lines.append("")
                lines.append("")

        lines.append("---")
        lines.append("")

    # ── Section 6: Screenshots ──
    if report.screenshots:
        lines.append("## Screenshots")
        lines.append("")
        for i, path in enumerate(report.screenshots, 1):
            lines.append(f"{i}. `{path}`")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Custom sections ──
    for title, content in report.extra_sections.items():
        lines.append(f"## {title}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by abaqus-mcp-pro Simulation Report.*")
    lines.append(f"*Generated at: {report.generated_at}*")

    return "\n".join(lines)


def format_report_compact(report: SimulationReport) -> str:
    """Compact one-line-per-section summary of the report."""
    lines: list[str] = []
    lines.append(f"Report: {report.title}")

    if report.capsule:
        c = report.capsule
        lines.append(f"  Capsule: {c.capsule_id} | Job: {c.job_name} | Status: {c.job_status}")

    if report.kpi_lens:
        k = report.kpi_lens
        ok = len([r for r in k.results if not r.error])
        errors = k.error_count
        lines.append(f"  KPI Lens: {ok} OK, {errors} errors | ODB: {k.odb_path}")

    if report.contracts:
        ct = report.contracts
        lines.append(f"  Contracts: {ct.passed_count} passed, {ct.failed_count} failed")

    if report.diagnosis:
        d = report.diagnosis
        lines.append(f"  Diagnosis: {d.error_count} errors, {d.warning_count} warnings, {d.info_count} info")

    if report.silent_failures:
        sf = report.silent_failures
        lines.append(f"  Silent Failures: {sf.failed_count} failed, {sf.warning_count} warnings, {sf.passed_count} passed")

    if report.screenshots:
        lines.append(f"  Screenshots: {len(report.screenshots)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(
    title: str = "Abaqus Simulation Report",
    capsule: CapsuleEntry | None = None,
    kpi_lens: KPILensReport | None = None,
    contracts: ContractReport | None = None,
    diagnosis: DiagnosisReport | None = None,
    silent_failures: SilentFailureReport | None = None,
    screenshots: list[str] | None = None,
    extra_sections: dict[str, str] | None = None,
) -> SimulationReport:
    """Build a SimulationReport from individual analysis results.

    All arguments except title are optional. Only provided sections
    will appear in the rendered report.

    Args:
        title: Report title.
        capsule: Capsule snapshot from create_capsule.
        kpi_lens: KPI Lens results from extract_kpis.
        contracts: Contract validation results from check_contracts.
        diagnosis: Solver diagnosis from diagnose_logs.
        screenshots: List of screenshot file paths.
        extra_sections: Additional custom sections as {title: content} dict.

    Returns:
        SimulationReport ready for rendering.
    """
    return SimulationReport(
        title=title,
        capsule=capsule,
        kpi_lens=kpi_lens,
        contracts=contracts,
        diagnosis=diagnosis,
        silent_failures=silent_failures,
        screenshots=screenshots or [],
        extra_sections=extra_sections or {},
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def save_report(report: SimulationReport, path: str) -> str:
    """Save a SimulationReport as a Markdown file.

    Args:
        report: The report to save.
        path: Output file path (.md extension recommended).

    Returns:
        The absolute path where the report was saved.
    """
    import os
    md = format_report_markdown(report)
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    return abs_path
