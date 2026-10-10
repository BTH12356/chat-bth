"""Tests for Project Spec generation, resolution, and freezing."""

from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.form_engine import FormStore, RuleEngine
from bth_create.spec_lifecycle import FreezeStore, FrozenProjectSpec, ProjectSpecGenerator, ProjectSpecResolver


class SpecLifecycleTests(unittest.TestCase):
    def setUp(self):
        form = FormStore().get("internal_dashboard.v1")
        self.values = RuleEngine().evaluate(
            form,
            {
                "project_name": "BTH Control Center",
                "modules": ["worker_monitor", "gpu_monitor", "job_queue", "model_manager", "ai_assistant"],
                "ai_assistant": True,
                "ai_capabilities": ["log_analysis", "error_assistance", "system_summary"],
            },
        ).values
        self.generator = ProjectSpecGenerator()
        self.resolver = ProjectSpecResolver()

    def test_form_values_generate_valid_project_spec(self):
        spec = self.generator.from_internal_dashboard_form(self.values)
        self.assertEqual(spec.project.name, "BTH Control Center")
        self.assertEqual(spec.blueprint.id, "dashboard.internal.v1")
        self.assertTrue(spec.ai.enabled)

    def test_resolver_pins_catalog_versions_and_components(self):
        resolved = self.resolver.resolve(self.generator.from_internal_dashboard_form(self.values))
        self.assertEqual(resolved.blueprint_version, "1.0.0")
        self.assertEqual(resolved.theme_version, "1.0.0")
        self.assertEqual(resolved.component_versions["gpu_monitor"], "1.0.0")
        self.assertEqual(resolved.component_versions["auth"], "1.0.0")
        self.assertEqual(resolved.component_versions["api_client"], "1.0.0")

    def test_resolver_rejects_missing_required_blueprint_module(self):
        values = {**self.values, "modules": ["worker_monitor", "gpu_monitor"]}
        with self.assertRaises(ValueError):
            self.resolver.resolve(self.generator.from_internal_dashboard_form(values))

    def test_resolver_rejects_unsupported_ai_capability(self):
        values = {**self.values, "ai_capabilities": ["automatic_system_modification"]}
        with self.assertRaises(ValueError):
            self.resolver.resolve(self.generator.from_internal_dashboard_form(values))

    def test_freeze_creates_append_only_revision_with_provenance(self):
        resolved = self.resolver.resolve(self.generator.from_internal_dashboard_form(self.values))
        with tempfile.TemporaryDirectory() as directory:
            store = FreezeStore(Path(directory))
            frozen_at = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
            first = store.freeze(resolved, "bth-project-0001", frozen_at)
            second = store.freeze(resolved, "bth-project-0001", frozen_at)
            self.assertEqual(first.frozen_id, "bth-project-0001-r1")
            self.assertEqual(second.frozen_id, "bth-project-0001-r2")
            self.assertEqual(first.status, "frozen")
            self.assertEqual(store.get(first.frozen_id).spec_hash, first.spec_hash)
            self.assertEqual(first.component_versions["worker_monitor"], "1.0.0")

    def test_frozen_spec_is_strict_and_immutable(self):
        resolved = self.resolver.resolve(self.generator.from_internal_dashboard_form(self.values))
        with tempfile.TemporaryDirectory() as directory:
            frozen = FreezeStore(Path(directory)).freeze(resolved, "bth-project-0001")
            with self.assertRaises(ValidationError):
                FrozenProjectSpec.model_validate({**frozen.model_dump(), "prompt": "change build"})
            with self.assertRaises((TypeError, ValidationError)):
                frozen.status = "draft"


if __name__ == "__main__":
    unittest.main()
