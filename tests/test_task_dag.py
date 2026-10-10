"""Tests for deterministic Task DAG generation."""

import unittest

from pydantic import ValidationError

from bth_create.gap_analysis import GapAnalysisReport, GapItem
from bth_create.task_dag import BuildTask, RetryPolicy, TaskDAG, TaskDAGBuilder


def report_with(missing: list[GapItem] | None = None) -> GapAnalysisReport:
    return GapAnalysisReport(
        frozen_spec_id="bth-project-0001-r1",
        spec_hash="a" * 64,
        reuse=[GapItem(requirement_id="module.worker_monitor", category="REUSE", component_id="worker_monitor", reason="verified")],
        configure=[GapItem(requirement_id="project.name", category="CONFIGURE", reason="from spec")],
        compose=[GapItem(requirement_id="dashboard.layout", category="COMPOSE", reason="compose")],
        missing=missing or [],
    )


class TaskDAGTests(unittest.TestCase):
    def test_ready_report_produces_deterministic_cpu_pipeline(self):
        dag = TaskDAGBuilder().build(report_with())
        self.assertEqual(dag.topological_order()[0], "validate_spec")
        self.assertEqual(dag.topological_order()[-1], "build_product")
        self.assertNotIn("generate_missing_001", dag.topological_order())
        self.assertEqual(next(task for task in dag.tasks if task.task_id == "run_tests").dependencies, ["compose_layout"])

    def test_missing_gap_creates_scoped_generation_task(self):
        gap = GapItem(requirement_id="custom.1", category="MISSING", reason="No matching component")
        dag = TaskDAGBuilder().build(report_with([gap]))
        generation = next(task for task in dag.tasks if task.task_id == "generate_missing_001")
        self.assertEqual(generation.resource_class, "LOCAL_LLM")
        self.assertEqual(generation.inputs["requirement_id"], "custom.1")
        self.assertEqual(next(task for task in dag.tasks if task.task_id == "run_tests").dependencies, [generation.task_id])

    def test_task_schema_contains_scheduler_fields(self):
        task = TaskDAGBuilder().build(report_with()).tasks[0]
        self.assertEqual(task.status, "pending")
        self.assertTrue(task.required_capability)
        self.assertTrue(task.verification_method)
        self.assertGreaterEqual(task.retry_policy.max_attempts, 1)

    def test_unknown_dependency_is_rejected(self):
        task = BuildTask(
            task_id="one", task_type="test", dependencies=["missing"],
            required_capability="test", resource_class="CPU", retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0),
            verification_method="verify",
        )
        with self.assertRaises(ValidationError):
            TaskDAG(frozen_spec_id="spec-r1", spec_hash="a" * 64, tasks=[task])

    def test_dependency_cycle_is_rejected(self):
        retry = RetryPolicy(max_attempts=1, backoff_seconds=0)
        first = BuildTask(task_id="one", task_type="test", dependencies=["two"], required_capability="test", resource_class="CPU", retry_policy=retry, verification_method="verify")
        second = BuildTask(task_id="two", task_type="test", dependencies=["one"], required_capability="test", resource_class="CPU", retry_policy=retry, verification_method="verify")
        with self.assertRaises(ValidationError):
            TaskDAG(frozen_spec_id="spec-r1", spec_hash="a" * 64, tasks=[first, second])


if __name__ == "__main__":
    unittest.main()
