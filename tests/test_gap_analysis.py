"""Tests for deterministic Project Spec Gap Analysis."""

import tempfile
import unittest
from pathlib import Path

from bth_create.form_engine import FormStore, RuleEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver


class GapAnalysisTests(unittest.TestCase):
    def setUp(self):
        values = RuleEngine().evaluate(
            FormStore().get("internal_dashboard.v1"),
            {
                "project_name": "BTH Control Center",
                "modules": ["worker_monitor", "gpu_monitor", "job_queue", "model_manager", "ai_assistant"],
                "ai_assistant": True,
                "ai_capabilities": ["log_analysis", "error_assistance", "system_summary"],
            },
        ).values
        resolved = ProjectSpecResolver().resolve(ProjectSpecGenerator().from_internal_dashboard_form(values))
        self.tempdir = tempfile.TemporaryDirectory()
        self.frozen = FreezeStore(Path(self.tempdir.name)).freeze(resolved, "bth-project-0001")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_existing_components_are_classified_as_reuse(self):
        report = GapAnalyzer().analyze(self.frozen)
        self.assertEqual(report.status, "ready")
        self.assertEqual({item.category for item in report.reuse}, {"REUSE"})
        self.assertIn("module.gpu_monitor", {item.requirement_id for item in report.reuse})
        self.assertIn("auth", {item.requirement_id for item in report.reuse})

    def test_configuration_and_composition_are_not_generation_work(self):
        report = GapAnalyzer().analyze(self.frozen)
        self.assertIn("project.name", {item.requirement_id for item in report.configure})
        self.assertIn("dashboard.layout", {item.requirement_id for item in report.compose})
        self.assertFalse(report.missing)

    def test_custom_unknown_requirement_is_missing(self):
        report = GapAnalyzer().analyze(self.frozen, ["custom_gpu_alert_rule"])
        self.assertEqual(report.status, "gaps_found")
        self.assertEqual(report.missing[0].requirement_id, "custom.1")
        self.assertEqual(report.missing[0].category, "MISSING")

    def test_tampered_frozen_spec_is_rejected(self):
        altered = self.frozen.model_copy(update={"spec_hash": "0" * 64})
        with self.assertRaises(ValueError):
            GapAnalyzer().analyze(altered)


if __name__ == "__main__":
    unittest.main()
