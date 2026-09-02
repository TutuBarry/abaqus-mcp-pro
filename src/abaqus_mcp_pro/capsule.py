"""Experiment Capsule: capture and store simulation run snapshots.

A capsule records the full context of a simulation run — model, jobs,
KPIs, diagnostics, scripts, and files — so it can be reproduced,
audited, and compared later.

Storage: JSON files in ``.capsules/`` under the workdir (or MCP home).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CapsuleEntry:
    """A single simulation run snapshot."""

    capsule_id: str
    timestamp: str = ""  # ISO 8601
    workdir: str = ""
    notes: str = ""

    # Model state
    model_info: dict[str, Any] = field(default_factory=dict)

    # Job state
    job_name: str = ""
    job_status: str = ""

    # Diagnostics
    diagnosis: dict[str, Any] = field(default_factory=dict)

    # KPIs
    kpis: dict[str, Any] = field(default_factory=dict)

    # Files (inventory)
    files: list[dict[str, str]] = field(default_factory=list)

    # Scripts executed
    scripts: list[str] = field(default_factory=list)

    # Abaqus version info
    abaqus_version: str = ""
    python_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CapsuleEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Capsule Store
# ---------------------------------------------------------------------------


class CapsuleStore:
    """Manages persistent storage of capsules on disk."""

    def __init__(self, store_dir: str | None = None):
        if store_dir is None:
            store_dir = os.environ.get(
                "ABAQUS_MCP_CAPSULE_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".capsules"),
            )
        self.store_dir = os.path.abspath(store_dir)
        os.makedirs(self.store_dir, exist_ok=True)

    def _capsule_path(self, capsule_id: str) -> str:
        # Sanitize capsule_id for filesystem
        safe_id = "".join(c for c in capsule_id if c.isalnum() or c in "._-")
        return os.path.join(self.store_dir, f"{safe_id}.json")

    def save(self, capsule: CapsuleEntry) -> str:
        """Save a capsule to disk. Returns the file path."""
        path = self._capsule_path(capsule.capsule_id)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(capsule.to_dict(), fh, indent=2, ensure_ascii=False, default=str)
        return path

    def load(self, capsule_id: str) -> CapsuleEntry | None:
        """Load a capsule from disk. Returns None if not found."""
        path = self._capsule_path(capsule_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return CapsuleEntry.from_dict(data)

    def list_ids(self) -> list[str]:
        """List all capsule IDs in the store."""
        ids = []
        if not os.path.isdir(self.store_dir):
            return ids
        for fname in os.listdir(self.store_dir):
            if fname.endswith(".json"):
                ids.append(fname[:-5])  # strip .json
        return sorted(ids)

    def list_all(self) -> list[CapsuleEntry]:
        """List all capsules with full data."""
        capsules = []
        for cid in self.list_ids():
            entry = self.load(cid)
            if entry is not None:
                capsules.append(entry)
        return capsules

    def delete(self, capsule_id: str) -> bool:
        """Delete a capsule. Returns True if deleted."""
        path = self._capsule_path(capsule_id)
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False


# ---------------------------------------------------------------------------
# Capsule creation (Abaqus-side code)
# ---------------------------------------------------------------------------

# This code runs inside the Abaqus kernel to capture the current state.
# Placeholders: __CAPSULE_ID__, __NOTES__

CAPSULE_CAPTURE_CODE = r'''
import json as _json
import os as _os
import sys as _sys
import time as _time
from datetime import datetime, timezone as _timezone

_capsule_id = __CAPSULE_ID__
_notes = __NOTES__

_capsule = {
    "capsule_id": _capsule_id,
    "timestamp": datetime.now(_timezone.utc).isoformat(),
    "workdir": _os.getcwd(),
    "notes": _notes,
    "abaqus_version": "",
    "python_version": _sys.version,
    "model_info": {},
    "job_name": "",
    "job_status": "",
    "diagnosis": {},
    "kpis": {},
    "files": [],
    "scripts": [],
}

try:
    from abaqus import mdb, session

    # Abaqus version
    try:
        import abaqus
        _capsule["abaqus_version"] = getattr(abaqus, "version", "")
    except Exception:
        pass

    # Model info
    _models = {}
    for _mn in mdb.models.keys():
        _m = mdb.models[_mn]
        _models[_mn] = {
            "parts": list(_m.parts.keys()),
            "materials": list(_m.materials.keys()),
            "sections": list(_m.sections.keys()),
            "steps": list(_m.steps.keys()),
            "loads": list(_m.loads.keys()),
            "boundary_conditions": list(_m.boundaryConditions.keys()),
            "interactions": list(_m.interactions.keys()),
            "constraints": list(_m.constraints.keys()),
        }
    _capsule["model_info"] = _models

    # Job info
    _jobs = []
    for _jn in mdb.jobs.keys():
        _j = mdb.jobs[_jn]
        _jobs.append({
            "name": _jn,
            "status": str(getattr(_j, "status", "")),
            "type": str(getattr(_j, "type", "")),
            "model": str(getattr(_j, "model", "")),
        })
    if _jobs:
        _capsule["job_name"] = _jobs[-1]["name"]
        _capsule["job_status"] = _jobs[-1]["status"]

    # File inventory (output files for the last job)
    if _jobs:
        _jn = _jobs[-1]["name"]
        for _ext in [".odb", ".sta", ".msg", ".dat", ".log", ".inp", ".prt", ".com"]:
            _fp = _os.path.join(_os.getcwd(), _jn + _ext)
            if _os.path.isfile(_fp):
                _st = _os.stat(_fp)
                _capsule["files"].append({
                    "name": _jn + _ext,
                    "path": _fp,
                    "size": _st.st_size,
                    "mtime": _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(_st.st_mtime)),
                })

except Exception as _exc:
    _capsule["error"] = str(_exc)

result = _capsule
'''


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def format_capsule_markdown(capsule: CapsuleEntry) -> str:
    """Render a capsule as structured Markdown."""
    lines: list[str] = []
    lines.append(f"## Capsule: `{capsule.capsule_id}`")
    lines.append("")
    lines.append(f"**Timestamp:** {capsule.timestamp}")
    lines.append(f"**Workdir:** `{capsule.workdir}`")
    if capsule.notes:
        lines.append(f"**Notes:** {capsule.notes}")
    if capsule.abaqus_version:
        lines.append(f"**Abaqus:** {capsule.abaqus_version}")
    lines.append("")

    # Model summary
    if capsule.model_info:
        lines.append("### Model")
        for model_name, info in capsule.model_info.items():
            lines.append(f"**{model_name}:**")
            for key, val in info.items():
                if isinstance(val, list):
                    lines.append(f"- {key}: {', '.join(val) if val else '(none)'}")
                else:
                    lines.append(f"- {key}: {val}")
            lines.append("")

    # Job info
    if capsule.job_name:
        lines.append("### Job")
        lines.append(f"- Name: {capsule.job_name}")
        lines.append(f"- Status: {capsule.job_status}")
        lines.append("")

    # KPIs
    if capsule.kpis:
        lines.append("### KPIs")
        for k, v in capsule.kpis.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    # Diagnosis
    if capsule.diagnosis:
        lines.append("### Diagnosis")
        err_count = capsule.diagnosis.get("error_count", 0)
        warn_count = capsule.diagnosis.get("warning_count", 0)
        lines.append(f"- Errors: {err_count}, Warnings: {warn_count}")
        lines.append("")

    # Files
    if capsule.files:
        lines.append("### Output Files")
        for f in capsule.files:
            size_kb = f.get("size", 0) / 1024
            lines.append(f"- `{f.get('name', '?')}` ({size_kb:.1f} KB)")
        lines.append("")

    lines.append("---")
    lines.append("*Captured by abaqus-mcp-pro Experiment Capsule.*")
    return "\n".join(lines)


def format_capsule_list_markdown(capsules: list[CapsuleEntry]) -> str:
    """Render a list of capsules as a compact Markdown table."""
    lines: list[str] = []
    lines.append("## Capsule Inventory")
    lines.append("")

    if not capsules:
        lines.append("No capsules found.")
        return "\n".join(lines)

    lines.append(f"**Total:** {len(capsules)} capsule(s)")
    lines.append("")
    lines.append("| ID | Timestamp | Job | Status | Notes |")
    lines.append("|----|-----------|-----|--------|-------|")
    for c in capsules:
        ts = c.timestamp[:19] if c.timestamp else "—"
        job = c.job_name or "—"
        status = c.job_status or "—"
        notes = c.notes[:40] if c.notes else "—"
        lines.append(f"| {c.capsule_id} | {ts} | {job} | {status} | {notes} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diff helper
# ---------------------------------------------------------------------------

def diff_capsules(c1: CapsuleEntry, c2: CapsuleEntry) -> str:
    """Compare two capsules and return a Markdown diff report."""
    lines: list[str] = []
    lines.append(f"## Capsule Diff: `{c1.capsule_id}` vs `{c2.capsule_id}`")
    lines.append("")

    # Compare timestamps
    lines.append(f"**Baseline:** {c1.timestamp}")
    lines.append(f"**Current:**  {c2.timestamp}")
    lines.append("")

    # Compare model info
    if c1.model_info and c2.model_info:
        lines.append("### Model Changes")
        m1 = c1.model_info
        m2 = c2.model_info
        all_models = set(m1.keys()) | set(m2.keys())
        for mn in sorted(all_models):
            if mn not in m1:
                lines.append(f"- **+ {mn}** (new model)")
            elif mn not in m2:
                lines.append(f"- **- {mn}** (removed)")
            else:
                for key in sorted(set(m1[mn].keys()) | set(m2[mn].keys())):
                    v1 = set(m1[mn].get(key, []))
                    v2 = set(m2[mn].get(key, []))
                    added = v2 - v1
                    removed = v1 - v2
                    if added or removed:
                        lines.append(f"- {mn}.{key}:")
                        for a in sorted(added):
                            lines.append(f"  + {a}")
                        for r in sorted(removed):
                            lines.append(f"  - {r}")
        lines.append("")

    # Compare jobs
    if c1.job_name != c2.job_name:
        lines.append(f"**Job:** {c1.job_name} → {c2.job_name}")
    if c1.job_status != c2.job_status:
        lines.append(f"**Status:** {c1.job_status} → {c2.job_status}")
    lines.append("")

    # Compare KPIs
    if c1.kpis or c2.kpis:
        lines.append("### KPI Changes")
        all_kpis = set(c1.kpis.keys()) | set(c2.kpis.keys())
        for k in sorted(all_kpis):
            v1 = c1.kpis.get(k)
            v2 = c2.kpis.get(k)
            if v1 != v2:
                lines.append(f"- {k}: {v1} → {v2}")
        lines.append("")

    # Compare file sizes
    if c1.files and c2.files:
        lines.append("### File Size Changes")
        f1 = {f["name"]: f.get("size", 0) for f in c1.files}
        f2 = {f["name"]: f.get("size", 0) for f in c2.files}
        all_files = set(f1.keys()) | set(f2.keys())
        for fn in sorted(all_files):
            s1 = f1.get(fn, 0)
            s2 = f2.get(fn, 0)
            if s1 != s2:
                delta = s2 - s1
                sign = "+" if delta > 0 else ""
                lines.append(f"- {fn}: {s1/1024:.1f} KB → {s2/1024:.1f} KB ({sign}{delta/1024:.1f} KB)")
        lines.append("")

    lines.append("---")
    lines.append("*Diff generated by abaqus-mcp-pro Capsule.*")
    return "\n".join(lines)
