"""Deterministic Component Registry for BTH Create."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ComponentIdentifier = Annotated[str, Field(min_length=1, max_length=120)]
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class ComponentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Component(ComponentModel):
    id: ComponentIdentifier
    version: str = Field(min_length=1, max_length=30)
    type: Literal["feature", "ui", "infrastructure"]
    capabilities: list[ComponentIdentifier] = Field(default_factory=list, max_length=100)
    dependencies: list[ComponentIdentifier] = Field(default_factory=list, max_length=100)
    compatible_blueprints: list[ComponentIdentifier] = Field(default_factory=list, max_length=50)
    status: Literal["verified", "experimental", "deprecated"]

    @field_validator("version")
    @classmethod
    def version_must_be_semver(cls, value: str) -> str:
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError("component version must use MAJOR.MINOR.PATCH format")
        return value

    @field_validator("capabilities", "dependencies", "compatible_blueprints")
    @classmethod
    def identifiers_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("component metadata identifiers must be unique")
        return values


def validate_component(value: Component | dict) -> Component:
    """Validate and return an immutable Component model."""

    if isinstance(value, Component):
        return value
    return Component.model_validate(value)


class ComponentRegistry:
    """Read-only registry for versioned component metadata."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent / "components"

    def list(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))

    def get(self, component_id: str) -> Component:
        path = self.root / f"{component_id}.json"
        if path.parent != self.root or not path.is_file():
            raise KeyError(f"component not found: {component_id}")
        return validate_component(json.loads(path.read_text(encoding="utf-8")))

    def has(self, component_id: str) -> bool:
        try:
            self.get(component_id)
        except KeyError:
            return False
        return True

    def is_verified(self, component_id: str) -> bool:
        return self.get(component_id).status == "verified"

    def dependencies(self, component_id: str) -> list[str]:
        return list(self.get(component_id).dependencies)

    def compatible_with(self, component_id: str, blueprint_id: str) -> bool:
        component = self.get(component_id)
        return blueprint_id in component.compatible_blueprints

