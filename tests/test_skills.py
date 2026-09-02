"""Unit tests for abaqus_mcp_pro.skills."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from abaqus_mcp_pro.skills import SKILLS


class TestSkills:
    """Verify the built-in skills knowledge base."""

    def test_skills_count(self):
        assert len(SKILLS) == 26, f"Expected 26 skills, got {len(SKILLS)}"

    def test_all_skills_non_empty(self):
        for key, content in SKILLS.items():
            assert content.strip(), f"Skill '{key}' has empty content"

    def test_skills_index_exists(self):
        assert "skills/index" in SKILLS
        assert "Abaqus Skills Index" in SKILLS["skills/index"]

    def test_required_skills_present(self):
        required = [
            "skills/geometry",
            "skills/material",
            "skills/mesh",
            "skills/interaction",
            "skills/step",
            "skills/boundary-condition",
            "skills/load",
            "skills/output",
            "skills/job",
            "skills/odb",
            "skills/static-analysis",
            "skills/modal-analysis",
            "skills/contact-analysis",
            "skills/dynamic-analysis",
            "skills/thermal-analysis",
            "skills/fatigue-analysis",
            "skills/coupled-analysis",
            "skills/optimization",
            "skills/topology-optimization",
            "skills/shape-optimization",
            "skills/amplitude",
            "skills/field",
            "skills/export",
            "skills/units",
            "skills/docs",
        ]
        for key in required:
            assert key in SKILLS, f"Required skill '{key}' is missing"
            assert SKILLS[key].strip(), f"Required skill '{key}' is empty"

    def test_skill_keys_follow_pattern(self):
        for key in SKILLS:
            assert key.startswith("skills/"), f"Key '{key}' does not start with 'skills/'"
            assert " " not in key, f"Key '{key}' contains spaces"

    def test_index_references_skills(self):
        """The index should reference at least some of the actual skills."""
        index = SKILLS["skills/index"]
        for key in ["skills/geometry", "skills/material", "skills/static-analysis"]:
            assert key in index, f"Index does not reference {key}"

    def test_units_skill_content(self):
        assert "mm" in SKILLS["skills/units"].lower()
        assert "MPa" in SKILLS["skills/units"]
