"""Tests for the deterministic BTH Blueprint Store boundary."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.blueprint import BlueprintStore, validate_blueprint


class BlueprintTests(unittest.TestCase):
    def test_internal_dashboard_blueprint_is_loadable(self):
        store = BlueprintStore()
        blueprint = store.get("dashboard.internal.v1")
        self.assertIn("dashboard.internal.v1", store.list())
        self.assertEqual(blueprint.type, "internal_dashboard")
        self.assertIn("worker_monitor", blueprint.required_modules)
        self.assertEqual(blueprint.default_component_mapping["ai_assistant"].id, "ai_assistant_panel")

    def test_blueprint_is_immutable_and_rejects_unknown_fields(self):
        blueprint = BlueprintStore().get("dashboard.internal.v1")
        with self.assertRaises(ValidationError):
            validate_blueprint({**blueprint.model_dump(), "prompt": "generate a dashboard"})
        with self.assertRaises((TypeError, ValidationError)):
            blueprint.name = "changed"

    def test_required_and_optional_modules_must_be_supported_and_disjoint(self):
        base = BlueprintStore().get("dashboard.internal.v1").model_dump()
        base["required_modules"] = ["unknown_module"]
        with self.assertRaises(ValidationError):
            validate_blueprint(base)
        base = BlueprintStore().get("dashboard.internal.v1").model_dump()
        base["optional_modules"] = ["worker_monitor"]
        with self.assertRaises(ValidationError):
            validate_blueprint(base)

    def test_dependencies_and_mapping_must_reference_supported_modules(self):
        base = BlueprintStore().get("dashboard.internal.v1").model_dump()
        base["dependencies"] = [{"module": "worker_monitor", "requires": ["missing"]}]
        with self.assertRaises(ValidationError):
            validate_blueprint(base)
        base = BlueprintStore().get("dashboard.internal.v1").model_dump()
        base["default_component_mapping"] = {"missing": {"id": "missing"}}
        with self.assertRaises(ValidationError):
            validate_blueprint(base)

    def test_store_missing_blueprint_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyError):
                BlueprintStore(Path(directory)).get("unknown.v1")


if __name__ == "__main__":
    unittest.main()
