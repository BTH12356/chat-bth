"""Deterministic Blueprint Store for BTH Create.

Blueprints describe product capabilities and constraints. They do not contain
presentation/theme decisions and they do not invoke an AI model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .project_spec import CatalogReference


BlueprintIdentifier = Annotated[str, Field(min_length=1, max_length=120)]


class BlueprintModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BlueprintDependency(BlueprintModel):
    module: BlueprintIdentifier
    requires: list[BlueprintIdentifier] = Field(default_factory=list, max_length=50)

    @field_validator("requires")
    @classmethod
    def requires_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("dependency requirements must be unique")
        return values


class Blueprint(BlueprintModel):
    id: BlueprintIdentifier
    version: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    supported_modules: list[BlueprintIdentifier] = Field(min_length=1, max_length=100)
    required_modules: list[BlueprintIdentifier] = Field(default_factory=list, max_length=100)
    optional_modules: list[BlueprintIdentifier] = Field(default_factory=list, max_length=100)
    dependencies: list[BlueprintDependency] = Field(default_factory=list, max_length=100)
    incompatible_combinations: list[list[BlueprintIdentifier]] = Field(default_factory=list, max_length=100)
    required_configuration: list[BlueprintIdentifier] = Field(default_factory=list, max_length=100)
    required_permissions: list[BlueprintIdentifier] = Field(default_factory=list, max_length=100)
    supported_network_modes: list[str] = Field(min_length=1, max_length=3)
    supported_ai_capabilities: list[BlueprintIdentifier] = Field(default_factory=list, max_length=50)
    supported_page_types: list[BlueprintIdentifier] = Field(default_factory=list, max_length=30)
    default_component_mapping: dict[BlueprintIdentifier, CatalogReference] = Field(default_factory=dict)

    @field_validator(
        "supported_modules",
        "required_modules",
        "optional_modules",
        "required_configuration",
        "required_permissions",
        "supported_ai_capabilities",
        "supported_page_types",
    )
    @classmethod
    def identifiers_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("blueprint identifiers must be unique")
        return values

    @field_validator("supported_network_modes")
    @classmethod
    def network_modes_must_be_supported(cls, values: list[str]) -> list[str]:
        allowed = {"local", "internet", "both"}
        if len(values) != len(set(values)) or any(value not in allowed for value in values):
            raise ValueError("supported network modes must be unique values from local, internet, both")
        return values

    @field_validator("incompatible_combinations")
    @classmethod
    def incompatible_pairs_must_be_valid(cls, values: list[list[str]]) -> list[list[str]]:
        for combination in values:
            if len(combination) != 2 or combination[0] == combination[1] or len(set(combination)) != 2:
                raise ValueError("incompatible combinations must contain two distinct modules")
        return values

    @model_validator(mode="after")
    def validate_module_contract(self) -> "Blueprint":
        supported = set(self.supported_modules)
        required = set(self.required_modules)
        optional = set(self.optional_modules)
        if not required <= supported or not optional <= supported:
            raise ValueError("required and optional modules must be supported modules")
        if required & optional:
            raise ValueError("a module cannot be both required and optional")
        dependency_modules = {item.module for item in self.dependencies}
        if not dependency_modules <= supported:
            raise ValueError("dependency entries must reference supported modules")
        for item in self.dependencies:
            if not set(item.requires) <= supported:
                raise ValueError("dependency requirements must reference supported modules")
            if item.module in item.requires:
                raise ValueError("a module cannot depend on itself")
        for combination in self.incompatible_combinations:
            if not set(combination) <= supported:
                raise ValueError("incompatible combinations must reference supported modules")
        mapped = set(self.default_component_mapping)
        if not mapped <= supported:
            raise ValueError("default component mapping must reference supported modules")
        return self


def validate_blueprint(value: Blueprint | dict) -> Blueprint:
    """Validate and return an immutable Blueprint model."""

    if isinstance(value, Blueprint):
        return value
    return Blueprint.model_validate(value)


class BlueprintStore:
    """Read-only filesystem-backed store for versioned Blueprint JSON files."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent / "blueprints"

    def list(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))

    def get(self, blueprint_id: str) -> Blueprint:
        path = self.root / f"{blueprint_id}.json"
        if path.parent != self.root or not path.is_file():
            raise KeyError(f"blueprint not found: {blueprint_id}")
        return validate_blueprint(json.loads(path.read_text(encoding="utf-8")))
