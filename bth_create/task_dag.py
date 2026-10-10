"""Deterministic Task DAG generation for BTH Create."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .gap_analysis import GapAnalysisReport


ResourceClass = Literal["CPU", "P4", "LOCAL_LLM", "LARGE_LLM"]
TaskStatus = Literal["pending", "running", "passed", "failed", "blocked", "skipped"]


class TaskModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetryPolicy(TaskModel):
    max_attempts: int = Field(ge=1, le=10)
    backoff_seconds: int = Field(ge=0, le=3600)
    retry_on: list[str] = Field(default_factory=list, max_length=20)


class BuildTask(TaskModel):
    task_id: str = Field(min_length=1, max_length=160)
    task_type: str = Field(min_length=1, max_length=120)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    required_capability: str = Field(min_length=1, max_length=120)
    resource_class: ResourceClass
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list, max_length=100)
    status: TaskStatus = "pending"
    retry_policy: RetryPolicy
    verification_method: str = Field(min_length=1, max_length=300)


class TaskDAG(TaskModel):
    frozen_spec_id: str = Field(min_length=1, max_length=160)
    spec_hash: str = Field(min_length=64, max_length=64)
    tasks: list[BuildTask] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_graph(self) -> "TaskDAG":
        ids = [task.task_id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task ids must be unique")
        known = set(ids)
        for task in self.tasks:
            if task.task_id in task.dependencies:
                raise ValueError("a task cannot depend on itself")
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(f"task {task.task_id} has unknown dependencies: {sorted(missing)}")
        self.topological_order()
        return self

    def topological_order(self) -> list[str]:
        remaining = {task.task_id: set(task.dependencies) for task in self.tasks}
        ordered: list[str] = []
        while remaining:
            ready = [task.task_id for task in self.tasks if task.task_id in remaining and not remaining[task.task_id]]
            if not ready:
                raise ValueError("task DAG contains a dependency cycle")
            for task_id in ready:
                ordered.append(task_id)
                del remaining[task_id]
                for dependencies in remaining.values():
                    dependencies.discard(task_id)
        return ordered


def _retry(max_attempts: int = 1, backoff_seconds: int = 0, retry_on: list[str] | None = None) -> RetryPolicy:
    return RetryPolicy(max_attempts=max_attempts, backoff_seconds=backoff_seconds, retry_on=retry_on or [])


class TaskDAGBuilder:
    """Convert a structured Gap Analysis report into a scheduler-ready DAG."""

    def build(self, report: GapAnalysisReport) -> TaskDAG:
        tasks = [
            BuildTask(
                task_id="validate_spec", task_type="validation", dependencies=[],
                required_capability="schema_validation", resource_class="CPU",
                inputs={"spec_hash": report.spec_hash}, outputs=["validated_spec"],
                retry_policy=_retry(), verification_method="Project Spec validator returns success and hash matches.",
            ),
            BuildTask(
                task_id="load_blueprint", task_type="catalog_load", dependencies=["validate_spec"],
                required_capability="blueprint_store", resource_class="CPU",
                inputs={"frozen_spec_id": report.frozen_spec_id}, outputs=["resolved_blueprint"],
                retry_policy=_retry(), verification_method="Blueprint exists and version can be resolved.",
            ),
            BuildTask(
                task_id="resolve_components", task_type="component_resolution", dependencies=["load_blueprint"],
                required_capability="component_registry", resource_class="CPU",
                inputs={"reuse": [item.requirement_id for item in report.reuse]}, outputs=["resolved_components"],
                retry_policy=_retry(), verification_method="All reusable components match frozen versions.",
            ),
            BuildTask(
                task_id="configure_components", task_type="configuration", dependencies=["resolve_components"],
                required_capability="component_configuration", resource_class="CPU",
                inputs={"configure": [item.requirement_id for item in report.configure]}, outputs=["configured_components"],
                retry_policy=_retry(), verification_method="Configuration validates against Project Spec.",
            ),
            BuildTask(
                task_id="compose_layout", task_type="composition", dependencies=["configure_components"],
                required_capability="component_composition", resource_class="CPU",
                inputs={"compose": [item.requirement_id for item in report.compose]}, outputs=["composed_workspace"],
                retry_policy=_retry(), verification_method="Composition manifest contains every requested module.",
            ),
        ]
        generation_ids: list[str] = []
        for index, item in enumerate(report.missing, start=1):
            task_id = f"generate_missing_{index:03d}"
            generation_ids.append(task_id)
            tasks.append(
                BuildTask(
                    task_id=task_id, task_type="generate_missing_component", dependencies=["compose_layout"],
                    required_capability="scoped_code_generation", resource_class="LOCAL_LLM",
                    inputs={"requirement_id": item.requirement_id, "reason": item.reason, "component_id": item.component_id},
                    outputs=[f"generated.{item.requirement_id}"],
                    retry_policy=_retry(2, 2, ["transient_model_error", "verification_failed"]),
                    verification_method="Run task-scoped contract tests for the generated gap only.",
                )
            )
        test_dependencies = generation_ids or ["compose_layout"]
        tasks.extend(
            [
                BuildTask(
                    task_id="run_tests", task_type="test", dependencies=test_dependencies,
                    required_capability="unit_testing", resource_class="CPU",
                    inputs={}, outputs=["unit_test_results"], retry_policy=_retry(2, 1, ["flaky_test"]),
                    verification_method="All required unit tests return structured passed results.",
                ),
                BuildTask(
                    task_id="integration_test", task_type="test", dependencies=["run_tests"],
                    required_capability="integration_testing", resource_class="CPU",
                    inputs={}, outputs=["integration_test_results"], retry_policy=_retry(),
                    verification_method="Integration test suite returns structured passed results.",
                ),
                BuildTask(
                    task_id="build_product", task_type="build", dependencies=["integration_test"],
                    required_capability="product_build", resource_class="CPU",
                    inputs={"frozen_spec_id": report.frozen_spec_id}, outputs=["product_artifact"],
                    retry_policy=_retry(), verification_method="Build output exists and matches the frozen spec identity.",
                ),
            ]
        )
        return TaskDAG(frozen_spec_id=report.frozen_spec_id, spec_hash=report.spec_hash, tasks=tasks)
