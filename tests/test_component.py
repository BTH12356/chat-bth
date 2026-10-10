"""Tests for the deterministic BTH Component Registry boundary."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.component import ComponentRegistry, validate_component


class ComponentRegistryTests(unittest.TestCase):
    def test_registry_contains_core_verified_components(self):
        registry = ComponentRegistry()
        self.assertIn("worker_monitor", registry.list())
        self.assertTrue(registry.has("gpu_monitor"))
        self.assertTrue(registry.is_verified("worker_monitor"))
        self.assertEqual(registry.get("gpu_monitor").version, "1.0.0")

    def test_registry_exposes_dependencies_and_compatibility(self):
        registry = ComponentRegistry()
        self.assertEqual(registry.dependencies("gpu_monitor"), ["api_client"])
        self.assertTrue(registry.compatible_with("worker_monitor", "dashboard.internal.v1"))
        self.assertFalse(registry.compatible_with("worker_monitor", "other.v1"))

    def test_component_metadata_is_strict_and_immutable(self):
        component = ComponentRegistry().get("worker_monitor")
        with self.assertRaises(ValidationError):
            validate_component({**component.model_dump(), "prompt": "generate implementation"})
        with self.assertRaises((TypeError, ValidationError)):
            component.status = "deprecated"

    def test_invalid_version_and_duplicate_metadata_are_rejected(self):
        base = ComponentRegistry().get("worker_monitor").model_dump()
        base["version"] = "v1"
        with self.assertRaises(ValidationError):
            validate_component(base)
        base = ComponentRegistry().get("worker_monitor").model_dump()
        base["capabilities"] = ["worker_status", "worker_status"]
        with self.assertRaises(ValidationError):
            validate_component(base)

    def test_missing_component_is_explicit(self):
        registry = ComponentRegistry()
        self.assertFalse(registry.has("unknown_component"))
        with self.assertRaises(KeyError):
            registry.get("unknown_component")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyError):
                ComponentRegistry(Path(directory)).get("unknown.v1")


if __name__ == "__main__":
    unittest.main()
