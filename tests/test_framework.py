#!/usr/bin/env python3
"""Comprehensive test suite for Simulacra framework and tooling."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "Framework"))

from scripts.validate_state import validate, load_json, DEFAULT_SCHEMA, EXAMPLE
from Framework.linter import audit_file, SYSTEM_LEAKS_PATTERNS, BANNED_PHRASES_PATTERNS
import deploy_framework


class TestPsychosomaticStateValidation(unittest.TestCase):
    """Test psychosomatic state JSON schema validation."""

    def setUp(self):
        self.schema = load_json(DEFAULT_SCHEMA)
        self.valid_state = load_json(EXAMPLE)

    def test_example_state_is_valid(self):
        errors = validate(self.valid_state, self.schema)
        self.assertEqual(errors, [], f"Example state should have 0 errors, got: {errors}")

    def test_distress_fields_and_legacy_pain(self):
        auto = self.valid_state["autonomic_state"]
        auto["emotional_distress_tolerance"] = 101
        errors = validate(self.valid_state, self.schema)
        self.assertTrue(any("emotional_distress_tolerance" in error for error in errors))

        for key in (
            "physical_pain",
            "emotional_distress",
            "physical_pain_tolerance",
            "emotional_distress_tolerance",
        ):
            del auto[key]
        self.assertTrue(validate(self.valid_state, self.schema))
        auto["pain"] = 20
        self.assertEqual(validate(self.valid_state, self.schema), [])

    def test_missing_required_top_level_key(self):
        state = dict(self.valid_state)
        del state["autonomic_state"]
        errors = validate(state, self.schema)
        self.assertTrue(any("missing required key 'autonomic_state'" in e for e in errors))

    def test_scale_bounds(self):
        state = json.loads(json.dumps(self.valid_state))
        state["autonomic_state"]["stress"] = 105
        errors = validate(state, self.schema)
        self.assertTrue(any("105 out of range 0–100" in e for e in errors))

        state["autonomic_state"]["stress"] = -5
        errors = validate(state, self.schema)
        self.assertTrue(any("-5 out of range 0–100" in e for e in errors))

    def test_polyvagal_and_cognitive_regime_enums(self):
        state = json.loads(json.dumps(self.valid_state))
        state["autonomic_state"]["polyvagal_mode"] = "invalid_mode"
        state["autonomic_state"]["cognitive_regime"] = "hyper_mode"
        errors = validate(state, self.schema)
        self.assertTrue(any("polyvagal_mode: invalid value 'invalid_mode'" in e for e in errors))
        self.assertTrue(any("cognitive_regime: invalid value 'hyper_mode'" in e for e in errors))

    def test_primary_somatic_zones_multi_zone_rule(self):
        state = json.loads(json.dumps(self.valid_state))
        state["autonomic_state"]["primary_somatic_zones"] = ["Z1_Cranial_Ocular"]
        errors = validate(state, self.schema)
        self.assertTrue(any("requires at least 2 body zones" in e for e in errors))

        state["autonomic_state"]["primary_somatic_zones"] = ["Z1_Cranial_Ocular", "Unknown_Zone"]
        errors = validate(state, self.schema)
        self.assertTrue(any("unknown zone 'Unknown_Zone'" in e for e in errors))

    def test_defense_posture_and_bias_state(self):
        state = json.loads(json.dumps(self.valid_state))
        state["subconscious_bias"]["bias_state"] = "INVALID_STATE"
        state["subconscious_bias"]["defense_posture"] = "rage_quit"
        errors = validate(state, self.schema)
        self.assertTrue(any("bias_state: invalid value 'INVALID_STATE'" in e for e in errors))
        self.assertTrue(any("defense_posture: invalid value 'rage_quit'" in e for e in errors))

    def test_relational_vectors_and_reciprocity(self):
        state = json.loads(json.dumps(self.valid_state))
        vec = state["relational_vectors"]["interlocutor_slug"]
        vec["status_dynamic"] = "invalid_dynamic"
        vec["relational_momentum"] = "invalid_momentum"
        vec["perceived_reciprocity"]["perceived_threat"] = 150
        errors = validate(state, self.schema)
        self.assertTrue(any("status_dynamic: invalid value 'invalid_dynamic'" in e for e in errors))
        self.assertTrue(any("relational_momentum: invalid value 'invalid_momentum'" in e for e in errors))
        self.assertTrue(any("150 out of range 0–100" in e for e in errors))


class TestLinterProseAuditing(unittest.TestCase):
    """Test prose linter pattern matching and leak detection."""

    def audit_text(self, text: str) -> list[dict]:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(text)
            tmp_path = f.name
        try:
            return audit_file(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_clean_prose_passes(self):
        clean_text = """---
chapter: 1
movement: 2
---
Julian gripped the edge of the cedar table. The grain was rough under his calloused palm.
He set the ledger down and looked past the open window into the rain.
"We move before sunrise," he said.
"""
        findings = self.audit_text(clean_text)
        self.assertEqual(findings, [])

    def test_detects_system_leaks(self):
        leak_text = """
She entered Realm IV as her cognitive_regime shifted to bypassed_reactive.
Her polyvagal_mode was sympathetic_mobilized and her defense_posture took over.
"""
        findings = self.audit_text(leak_text)
        types = [f["type"] for f in findings]
        matches = [f["match"] for f in findings]
        self.assertTrue(all(t == "System Leak" for t in types))
        self.assertIn("Realm IV", matches)
        self.assertIn("cognitive_regime", matches)
        self.assertIn("bypassed_reactive", matches)
        self.assertIn("polyvagal_mode", matches)
        self.assertIn("defense_posture", matches)

    def test_detects_therapy_labels(self):
        therapy_text = """
He explained that his trauma was an active wound triggering his coping mechanism.
"""
        findings = self.audit_text(therapy_text)
        matches = [f["match"] for f in findings]
        self.assertTrue(any(f["type"] == "System Leak" for f in findings))
        self.assertIn("trauma", matches)
        self.assertIn("active wound", matches)
        self.assertIn("coping mechanism", matches)

    def test_detects_banned_dialogue_and_beats(self):
        banned_text = """
"Are you okay?" she whispered.
Beat.
"I feel like we shouldn't be here," he said gently.
[jaw tightens]
"""
        findings = self.audit_text(banned_text)
        matches = [f["match"].strip() for f in findings]
        self.assertTrue(any("Are you okay?" in m for m in matches))
        self.assertTrue(any("whispered" in m for m in matches))
        self.assertTrue(any("Beat." in m for m in matches))
        self.assertTrue(any("I feel like" in m for m in matches))
        self.assertTrue(any("said gently" in m for m in matches))
        self.assertTrue(any("[jaw tightens]" in m for m in matches))


class TestDeploymentDecoupling(unittest.TestCase):
    """Test deploy_framework source files and decoupling."""

    def test_framework_source_files_exist(self):
        missing_files, missing_dirs = deploy_framework.validate_source_files(deploy_framework.get_source_dir())
        self.assertEqual(missing_files, [])
        self.assertEqual(missing_dirs, [])

    def test_simulator_and_images_not_in_framework_dirs(self):
        self.assertNotIn("Simulator", deploy_framework.FRAMEWORK_DIRS)
        self.assertNotIn("Images", deploy_framework.FRAMEWORK_DIRS)

    def test_blocked_target_detects_framework(self):
        self.assertTrue(deploy_framework.is_blocked_target("/some/path/Simulacra"))
        self.assertTrue(deploy_framework.is_blocked_target("/some/path/Authors_Framework"))

    def test_framework_files_include_psyche_framework(self):
        self.assertIn("Framework/psyche_framework.md", deploy_framework.FRAMEWORK_FILES)


if __name__ == "__main__":
    unittest.main()
