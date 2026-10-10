"""Tests for the deterministic BTH Project Spec v1 boundary."""

import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from bth_create.project_spec import (
    PROJECT_SPEC_SCHEMA,
    canonical_project_spec,
    project_spec_hash,
    validate_project_spec,
)


VALID_SPEC = {
    "schema": "bth.project/v1",
    "project": {"name": "BTH Control Center", "type": "internal_dashboard"},
    "blueprint": {"id": "dashboard.internal.v1"},
    "theme": {"id": "windows_xp.v1"},
    "modules": ["worker_monitor", "gpu_monitor", "job_queue", "model_manager", "ai_assistant"],
    "network": {"scope": "local"},
    "auth": {"enabled": True},
    "ai": {
        "enabled": True,
        "capabilities": ["log_analysis", "error_assistance", "system_summary"],
        "autonomy": "approval_required",
    },
    "density": "compact",
    "language": ["th", "en"],
}


class ProjectSpecTests(unittest.TestCase):
    def test_valid_internal_dashboard_spec(self):
        spec = validate_project_spec(VALID_SPEC)
        self.assertEqual(spec.schema_name, PROJECT_SPEC_SCHEMA)
        self.assertEqual(spec.project.name, "BTH Control Center")
        self.assertTrue(spec.model_config["frozen"])

    def test_canonical_json_is_stable_and_uses_schema_alias(self):
        reordered = {key: VALID_SPEC[key] for key in reversed(list(VALID_SPEC))}
        self.assertEqual(canonical_project_spec(VALID_SPEC), canonical_project_spec(reordered))
        self.assertEqual(len(project_spec_hash(VALID_SPEC)), 64)
        self.assertIn('"schema":"bth.project/v1"', canonical_project_spec(VALID_SPEC))

    def test_unknown_fields_are_rejected(self):
        invalid = {**VALID_SPEC, "prompt": "generate everything"}
        with self.assertRaises(ValidationError):
            validate_project_spec(invalid)

    def test_duplicate_modules_and_languages_are_rejected(self):
        duplicate_modules = {**VALID_SPEC, "modules": ["worker_monitor", "worker_monitor"]}
        duplicate_languages = {**VALID_SPEC, "language": ["th", "th"]}
        with self.assertRaises(ValidationError):
            validate_project_spec(duplicate_modules)
        with self.assertRaises(ValidationError):
            validate_project_spec(duplicate_languages)

    def test_internet_scope_requires_authentication(self):
        invalid = {**VALID_SPEC, "network": {"scope": "internet"}, "auth": {"enabled": False}}
        with self.assertRaises(ValidationError):
            validate_project_spec(invalid)

    def test_disabled_ai_cannot_have_capabilities(self):
        invalid = {**VALID_SPEC, "ai": {"enabled": False, "capabilities": []}}
        validate_project_spec(invalid)
        invalid["ai"] = {"enabled": False, "capabilities": ["log_analysis"]}
        with self.assertRaises(ValidationError):
            validate_project_spec(invalid)

    def test_json_schema_artifact_is_present_and_declares_contract(self):
        path = Path(__file__).parents[1] / "bth_create" / "schemas" / "bth.project.v1.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["$id"], PROJECT_SPEC_SCHEMA)
        self.assertEqual(document["properties"]["schema"]["const"], PROJECT_SPEC_SCHEMA)
        self.assertIn("modules", document["required"])


if __name__ == "__main__":
    unittest.main()
