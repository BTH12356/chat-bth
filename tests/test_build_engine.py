"""Tests for the frozen-spec-only Build Engine."""

import json
import tempfile
import unittest
from pathlib import Path

from bth_create.build_engine import BuildBlocked, BuildEngine
from bth_create.form_engine import FormStore, RuleEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver
from bth_create.task_dag import TaskDAGBuilder


class FakeMissingGenerator:
    def generate(self, item, workspace):
        path = workspace / "custom_gpu_alert_rule.js"
        path.write_text('export const threshold = 90;\n', encoding="utf-8")
        return [path]


class BuildEngineTests(unittest.TestCase):
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

    def tearDown(self):
        self.freeze_dir.cleanup()
        self.workspace_dir.cleanup()

    def test_build_composes_static_application_from_frozen_spec(self):
        report = GapAnalyzer().analyze(self.frozen)
        result = BuildEngine().build(self.frozen, report, TaskDAGBuilder().build(report), Path(self.workspace_dir.name))
        workspace = Path(result.workspace)
        self.assertEqual(result.status, "built")
        self.assertEqual(result.generated_components, [])
        self.assertEqual(set(result.artifacts), {"app.js", "index.html", "project-config.json", "styles.css"})
        self.assertIn("BTH Control Center", (workspace / "index.html").read_text(encoding="utf-8"))
        config = json.loads((workspace / "project-config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["frozen_spec_id"], self.frozen.frozen_id)

    def test_build_refuses_to_overwrite_existing_workspace(self):
        report = GapAnalyzer().analyze(self.frozen)
        dag = TaskDAGBuilder().build(report)
        engine = BuildEngine()
        engine.build(self.frozen, report, dag, Path(self.workspace_dir.name))
        with self.assertRaises(FileExistsError):
            engine.build(self.frozen, report, dag, Path(self.workspace_dir.name))

    def test_missing_requirement_blocks_without_scoped_generator(self):
        report = GapAnalyzer().analyze(self.frozen, ["custom_gpu_alert_rule"])
        dag = TaskDAGBuilder().build(report)
        with self.assertRaises(BuildBlocked) as captured:
            BuildEngine().build(self.frozen, report, dag, Path(self.workspace_dir.name))
        self.assertEqual(captured.exception.failure.status, "blocked")
        self.assertEqual(captured.exception.failure.task, "generate_missing_001")
        self.assertTrue(captured.exception.failure.needs_human)
        resumed = BuildEngine().build(
            self.frozen,
            report,
            dag,
            Path(self.workspace_dir.name),
            missing_generator=FakeMissingGenerator(),
            resume=True,
        )
        self.assertEqual(resumed.status, "built")
        self.assertIn("custom.1", resumed.generated_components)
        self.assertIn("custom_gpu_alert_rule.js", resumed.artifacts)

    def test_mismatched_build_inputs_are_rejected(self):
        report = GapAnalyzer().analyze(self.frozen)
        dag = TaskDAGBuilder().build(report).model_copy(update={"spec_hash": "0" * 64})
        with self.assertRaises(ValueError):
            BuildEngine().build(self.frozen, report, dag, Path(self.workspace_dir.name))


if __name__ == "__main__":
    unittest.main()
