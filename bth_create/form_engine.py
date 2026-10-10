"""Hybrid Form and deterministic Rule Engine for BTH Create."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FormModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FormField(FormModel):
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "select", "multi_select", "checkbox", "radio"]
    options: list[str] = Field(default_factory=list, max_length=100)
    default: Any = None
    visible_by_default: bool = True
    required: bool = False

    @field_validator("options")
    @classmethod
    def options_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("form field options must be unique")
        return values


class RuleCondition(FormModel):
    field: str = Field(min_length=1, max_length=120)
    operator: Literal["equals", "not_equals", "in", "not_in", "is_true", "is_false"]
    value: Any = None


class RuleAction(FormModel):
    type: Literal["show", "hide", "require", "unrequire"]
    field: str = Field(min_length=1, max_length=120)


class FormRule(FormModel):
    id: str = Field(min_length=1, max_length=120)
    when: list[RuleCondition] = Field(min_length=1, max_length=20)
    then: list[RuleAction] = Field(min_length=1, max_length=20)


class FormDefinition(FormModel):
    id: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=30)
    fields: list[FormField] = Field(min_length=1, max_length=200)
    rules: list[FormRule] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_references(self) -> "FormDefinition":
        field_ids = [field.id for field in self.fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("form field ids must be unique")
        known = set(field_ids)
        for rule in self.rules:
            for condition in rule.when:
                if condition.field not in known:
                    raise ValueError(f"rule condition references unknown field: {condition.field}")
            for action in rule.then:
                if action.field not in known:
                    raise ValueError(f"rule action references unknown field: {action.field}")
        return self


class FormView(FormModel):
    visible_fields: list[str]
    required_fields: list[str]
    values: dict[str, Any]
    fired_rules: list[str]


def _condition_matches(condition: RuleCondition, values: dict[str, Any]) -> bool:
    actual = values.get(condition.field)
    if condition.operator == "equals":
        return actual == condition.value
    if condition.operator == "not_equals":
        return actual != condition.value
    if condition.operator == "in":
        return actual in condition.value
    if condition.operator == "not_in":
        return actual not in condition.value
    if condition.operator == "is_true":
        return actual is True
    return actual is False


class RuleEngine:
    """Evaluate rules without model calls or side effects."""

    def evaluate(self, definition: FormDefinition, values: dict[str, Any]) -> FormView:
        known = {field.id for field in definition.fields}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"form values contain unknown fields: {sorted(unknown)}")
        normalized = {field.id: values.get(field.id, field.default) for field in definition.fields}
        visible = {field.id for field in definition.fields if field.visible_by_default}
        required: set[str] = {field.id for field in definition.fields if field.required}
        fired: list[str] = []
        for rule in definition.rules:
            if all(_condition_matches(condition, normalized) for condition in rule.when):
                fired.append(rule.id)
                for action in rule.then:
                    if action.type == "show":
                        visible.add(action.field)
                    elif action.type == "hide":
                        visible.discard(action.field)
                    elif action.type == "require":
                        required.add(action.field)
                    else:
                        required.discard(action.field)
        return FormView(
            visible_fields=[field.id for field in definition.fields if field.id in visible],
            required_fields=[field.id for field in definition.fields if field.id in required],
            values=normalized,
            fired_rules=fired,
        )


class UnknownRequirement(FormModel):
    text: str = Field(min_length=1, max_length=2000)
    context_fields: dict[str, Any] = Field(default_factory=dict, max_length=30)


class InterviewQuestion(FormModel):
    id: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=500)
    kind: Literal["text", "select", "multi_select", "boolean"] = "text"
    options: list[str] = Field(default_factory=list, max_length=50)


class AIInterview:
    """Interface for clarification only; implementations must not generate code."""

    def questions_for(self, requirement: UnknownRequirement) -> list[InterviewQuestion]:
        raise NotImplementedError


class MockAIInterview(AIInterview):
    """Deterministic placeholder for Phase 5; no network or model call."""

    def questions_for(self, requirement: UnknownRequirement) -> list[InterviewQuestion]:
        return [
            InterviewQuestion(id="goal", question="What outcome should this requirement produce?"),
            InterviewQuestion(id="inputs", question="What data or inputs should it use?"),
            InterviewQuestion(id="constraints", question="What constraints or approval rules apply?"),
        ]


class FormStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent / "forms"

    def get(self, form_id: str) -> FormDefinition:
        path = self.root / f"{form_id}.json"
        if path.parent != self.root or not path.is_file():
            raise KeyError(f"form not found: {form_id}")
        return FormDefinition.model_validate(json.loads(path.read_text(encoding="utf-8")))
