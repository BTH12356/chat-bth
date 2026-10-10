"""Tests for the structured Verification Pipeline and Build Manifest."""

import json
import tempfile
import unittest
from pathlib import Path

from bth_create.build_engine import BuildEngine
from bth_create.form_engine import FormStore, RuleEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver
from bth_create.task_dag import TaskDAGBuilder
from bth_create.verification import VerificationPipeline


class VerificationTests(unittest.TestCase):
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
        self.freeze_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = tempfile.TemporaryDirectory()
        self.frozen = FreezeStore(Path(self.freeze_dir.name)).freeze(resolved, "bth-project-0001")
        report = GapAnalyzer().analyze(self.frozen)
        self.build = BuildEngine().build(self.frozen, report, TaskDAGBuilder().build(report), Path(self.workspace_dir.name))
        self.pipeline = VerificationPipeline()

    def tearDown(self):
        self.freeze_dir.cleanup()
        self.workspace_dir.cleanup()

    def test_full_verification_pipeline_passes(self):
        report = self.pipeline.verify(self.frozen, self.build)
        self.assertEqual(report.status, "passed")
        self.assertEqual(len(report.results), 9)
        self.assertTrue(all(result.status == "passed" for result in report.results))
        self.assertIn("component_dependency_validation", {result.test for result in report.results})

    def test_manifest_records_complete_provenance(self):
        report = self.pipeline.verify(self.frozen, self.build)
        path = self.pipeline.write_manifest(self.frozen, self.build, report)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "bth.build/v1")
        self.assertEqual(manifest["project_spec"], self.frozen.frozen_id)
        self.assertEqual(manifest["blueprint"]["id"], "dashboard.internal.v1")
        self.assertEqual(manifest["theme"]["id"], "windows_xp.v1")
        self.assertEqual(manifest["components"]["api_client"], "1.0.0")
        self.assertEqual(manifest["verification"]["status"], "passed")
        self.assertEqual(len(manifest["artifacts"]["index.html"]), 64)

    def test_static_failure_is_structured_and_blocks_manifest(self):
        path = Path(self.build.workspace) / "styles.css"
        path.write_text(path.read_text(encoding="utf-8") + "\n{{UNRESOLVED}}\n", encoding="utf-8")
        report = self.pipeline.verify(self.frozen, self.build)
        self.assertEqual(report.status, "failed")
        static = next(result for result in report.results if result.test == "static_checks")
        self.assertEqual(static.status, "failed")
        self.assertTrue(static.details)
        with self.assertRaises(ValueError):
            self.pipeline.write_manifest(self.frozen, self.build, report)

    def test_missing_output_is_reported_without_aborting_other_checks(self):
        (Path(self.build.workspace) / "app.js").unlink()
        report = self.pipeline.verify(self.frozen, self.build)
        self.assertEqual(report.status, "failed")
        self.assertEqual(len(report.results), 9)
        self.assertEqual(next(result for result in report.results if result.test == "build_validation").status, "failed")


if __name__ == "__main__":
    unittest.main()
