"""Unit tests for capsule module."""

from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.capsule import (
    CapsuleEntry,
    CapsuleStore,
    format_capsule_markdown,
    format_capsule_list_markdown,
    diff_capsules,
    CAPSULE_CAPTURE_CODE,
)


class TestCapsuleEntry:
    def test_defaults(self):
        c = CapsuleEntry(capsule_id="test")
        assert c.capsule_id == "test"
        assert c.timestamp == ""
        assert c.notes == ""
        assert c.model_info == {}
        assert c.job_name == ""
        assert c.job_status == ""

    def test_full(self):
        c = CapsuleEntry(
            capsule_id="run_001",
            timestamp="2025-01-01T00:00:00Z",
            workdir="/tmp",
            notes="baseline",
            model_info={"Model-1": {"parts": ["Part-1"]}},
            job_name="Job-1",
            job_status="COMPLETED",
            abaqus_version="2024",
        )
        assert c.capsule_id == "run_001"
        assert c.model_info["Model-1"]["parts"] == ["Part-1"]

    def test_to_dict(self):
        c = CapsuleEntry(capsule_id="test", notes="hello")
        d = c.to_dict()
        assert d["capsule_id"] == "test"
        assert d["notes"] == "hello"

    def test_from_dict(self):
        d = {"capsule_id": "test", "notes": "hello", "extra_field": "ignored"}
        c = CapsuleEntry.from_dict(d)
        assert c.capsule_id == "test"
        assert c.notes == "hello"
        # extra_field should not be in the dataclass
        assert not hasattr(c, "extra_field")


class TestCapsuleStore:
    def test_init(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        assert os.path.isdir(store.store_dir)

    def test_save_and_load(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        c = CapsuleEntry(capsule_id="test", notes="my notes", job_name="Job-1")
        path = store.save(c)
        assert os.path.isfile(path)

        loaded = store.load("test")
        assert loaded is not None
        assert loaded.capsule_id == "test"
        assert loaded.notes == "my notes"
        assert loaded.job_name == "Job-1"

    def test_load_nonexistent(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        assert store.load("nonexistent") is None

    def test_list_ids(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        store.save(CapsuleEntry(capsule_id="c1"))
        store.save(CapsuleEntry(capsule_id="c2"))
        ids = store.list_ids()
        assert "c1" in ids
        assert "c2" in ids
        assert len(ids) == 2

    def test_list_all(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        store.save(CapsuleEntry(capsule_id="c1", notes="first"))
        store.save(CapsuleEntry(capsule_id="c2", notes="second"))
        all_caps = store.list_all()
        assert len(all_caps) == 2
        notes = {c.notes for c in all_caps}
        assert notes == {"first", "second"}

    def test_delete(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        store.save(CapsuleEntry(capsule_id="to_delete"))
        assert store.delete("to_delete")
        assert store.load("to_delete") is None
        assert not store.delete("nonexistent")

    def test_sanitize_id(self, tmp_path):
        store = CapsuleStore(store_dir=str(tmp_path / "capsules"))
        c = CapsuleEntry(capsule_id="test/with:bad*chars")
        path = store.save(c)
        assert "testwithbadchars" in os.path.basename(path)


class TestFormatCapsuleMarkdown:
    def test_basic(self):
        c = CapsuleEntry(
            capsule_id="run_001",
            timestamp="2025-01-01T00:00:00Z",
            workdir="/tmp",
            notes="test run",
            abaqus_version="2024",
            job_name="Job-1",
            job_status="COMPLETED",
        )
        md = format_capsule_markdown(c)
        assert "run_001" in md
        assert "test run" in md
        assert "Job-1" in md
        assert "COMPLETED" in md

    def test_with_model_info(self):
        c = CapsuleEntry(
            capsule_id="test",
            model_info={"Model-1": {"parts": ["Part-1", "Part-2"], "materials": ["Steel"]}},
        )
        md = format_capsule_markdown(c)
        assert "Part-1" in md
        assert "Steel" in md

    def test_with_kpis(self):
        c = CapsuleEntry(
            capsule_id="test",
            kpis={"max_stress": 345.6, "max_disp": 0.012},
        )
        md = format_capsule_markdown(c)
        assert "max_stress" in md
        assert "345.6" in md

    def test_with_diagnosis(self):
        c = CapsuleEntry(
            capsule_id="test",
            diagnosis={"error_count": 2, "warning_count": 1},
        )
        md = format_capsule_markdown(c)
        assert "Errors: 2" in md
        assert "Warnings: 1" in md

    def test_with_files(self):
        c = CapsuleEntry(
            capsule_id="test",
            files=[
                {"name": "job.odb", "size": 1024000},
                {"name": "job.msg", "size": 2048},
            ],
        )
        md = format_capsule_markdown(c)
        assert "job.odb" in md
        assert "1000.0 KB" in md


class TestFormatCapsuleListMarkdown:
    def test_empty(self):
        md = format_capsule_list_markdown([])
        assert "No capsules found" in md

    def test_with_capsules(self):
        capsules = [
            CapsuleEntry(capsule_id="c1", timestamp="2025-01-01T00:00:00Z", job_name="Job-1", job_status="COMPLETED"),
            CapsuleEntry(capsule_id="c2", timestamp="2025-01-02T00:00:00Z", notes="second run"),
        ]
        md = format_capsule_list_markdown(capsules)
        assert "c1" in md
        assert "c2" in md
        assert "Job-1" in md
        assert "COMPLETED" in md
        assert "second run" in md


class TestDiffCapsules:
    def test_diff_same(self):
        c1 = CapsuleEntry(capsule_id="c1", job_name="Job-1", job_status="COMPLETED")
        c2 = CapsuleEntry(capsule_id="c2", job_name="Job-1", job_status="COMPLETED")
        md = diff_capsules(c1, c2)
        assert "c1" in md
        assert "c2" in md

    def test_diff_status_change(self):
        c1 = CapsuleEntry(capsule_id="c1", job_status="RUNNING")
        c2 = CapsuleEntry(capsule_id="c2", job_status="COMPLETED")
        md = diff_capsules(c1, c2)
        assert "RUNNING" in md
        assert "COMPLETED" in md

    def test_diff_model_changes(self):
        c1 = CapsuleEntry(
            capsule_id="c1",
            model_info={"Model-1": {"parts": ["Part-1", "Part-2"]}},
        )
        c2 = CapsuleEntry(
            capsule_id="c2",
            model_info={"Model-1": {"parts": ["Part-1", "Part-3"]}},
        )
        md = diff_capsules(c1, c2)
        assert "Part-2" in md  # removed
        assert "Part-3" in md  # added

    def test_diff_kpi_changes(self):
        c1 = CapsuleEntry(capsule_id="c1", kpis={"max_stress": 100.0})
        c2 = CapsuleEntry(capsule_id="c2", kpis={"max_stress": 120.0})
        md = diff_capsules(c1, c2)
        assert "100.0" in md
        assert "120.0" in md

    def test_diff_file_size_changes(self):
        c1 = CapsuleEntry(
            capsule_id="c1",
            files=[{"name": "job.odb", "size": 1000000}],
        )
        c2 = CapsuleEntry(
            capsule_id="c2",
            files=[{"name": "job.odb", "size": 1500000}],
        )
        md = diff_capsules(c1, c2)
        assert "job.odb" in md


class TestCapsuleCaptureCode:
    def test_placeholders(self):
        assert "__CAPSULE_ID__" in CAPSULE_CAPTURE_CODE
        assert "__NOTES__" in CAPSULE_CAPTURE_CODE

    def test_valid_python_syntax(self):
        import ast
        code = CAPSULE_CAPTURE_CODE.replace("__CAPSULE_ID__", "'test'")
        code = code.replace("__NOTES__", "'notes'")
        ast.parse(code)
