"""Project Spec v1: the deterministic source of truth for BTH Create.

This module intentionally contains no model calls and no filesystem/database
side effects. It validates a spec, produces a stable JSON representation, and
calculates a reproducible hash for a later Freeze Spec phase.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROJECT_SPEC_SCHEMA = "bth.project/v1"
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")


class StrictModel(BaseModel):
    """Reject accidental fields so misspelled requirements cannot be ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


Identifier = Annotated[str, Field(min_length=1, max_length=120)]
PageType = Literal[
    "home",
    "about",
    "policy",
    "document_library",
    "knowledge_library",
    "product_catalog",
    "service",
    "news",
    "contact",
    "standard",
]


class ProjectInfo(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["internal_dashboard", "website"]

    @field_validator("name")
    @classmethod
    def name_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project name must contain visible text")
        return value.strip()


class CatalogReference(StrictModel):
    id: Identifier

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("id must contain lowercase letters, numbers, dots, hyphens, or underscores")
        return value


class NetworkConfig(StrictModel):
    scope: Literal["local", "internet", "both"]


class AuthConfig(StrictModel):
    enabled: bool


class NavigationTab(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=60)
    slug: Identifier | None = None
    page_type: PageType = "standard"

    @field_validator("id")
    @classmethod
    def validate_tab_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("tab id must use lowercase letters, numbers, dots, hyphens, or underscores")
        return value

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is not None and not _ID_PATTERN.fullmatch(value):
            raise ValueError("page slug must use lowercase letters, numbers, dots, hyphens, or underscores")
        return value

    @field_validator("name")
    @classmethod
    def tab_name_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tab name must contain visible text")
        return value.strip()


class NavigationConfig(StrictModel):
    tabs: list[NavigationTab] = Field(min_length=1, max_length=12)

    @field_validator("tabs")
    @classmethod
    def tabs_must_be_unique(cls, values: list[NavigationTab]) -> list[NavigationTab]:
        if len({item.id for item in values}) != len(values) or len({item.name.casefold() for item in values}) != len(values):
            raise ValueError("tab ids and names must be unique")
        slugs = [item.slug for item in values if item.slug is not None]
        if len(slugs) != len(set(slugs)):
            raise ValueError("page slugs must be unique")
        return values


class AppearanceConfig(StrictModel):
    color_tone: Literal["blue", "green", "purple", "orange", "neutral"]


class AIConfig(StrictModel):
    enabled: bool
    capabilities: list[Identifier] = Field(min_length=0, max_length=20)
    autonomy: Literal["approval_required", "assisted", "autonomous"] = "approval_required"

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("ai capabilities must be unique")
        return values

    @model_validator(mode="after")
    def validate_enabled_state(self) -> "AIConfig":
        if not self.enabled and self.capabilities:
            raise ValueError("disabled AI cannot declare capabilities")
        if not self.enabled and self.autonomy != "approval_required":
            raise ValueError("disabled AI must use approval_required autonomy")
        if self.enabled and not self.capabilities:
            raise ValueError("enabled AI must declare at least one capability")
        return self


class ProjectSpec(StrictModel):
    schema_name: Literal[PROJECT_SPEC_SCHEMA] = Field(alias="schema")
    project: ProjectInfo
    blueprint: CatalogReference
    theme: CatalogReference
    modules: list[Identifier] = Field(min_length=1, max_length=50)
    network: NetworkConfig
    auth: AuthConfig
    ai: AIConfig
    density: Literal["compact", "comfortable"]
    language: list[str] = Field(min_length=1, max_length=5)
    navigation: NavigationConfig | None = None
    appearance: AppearanceConfig | None = None

    @field_validator("modules")
    @classmethod
    def modules_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("modules must be unique")
        for value in values:
            if not _ID_PATTERN.fullmatch(value):
                raise ValueError("module ids must contain lowercase letters, numbers, dots, hyphens, or underscores")
        return values

    @field_validator("language")
    @classmethod
    def languages_must_be_supported_format(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not _LANGUAGE_PATTERN.fullmatch(value) for value in normalized):
            raise ValueError("language must use a BCP-47-like value such as th or en")
        if len(normalized) != len(set(normalized)):
            raise ValueError("language values must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_security_policy(self) -> "ProjectSpec":
        if self.network.scope in ("internet", "both") and not self.auth.enabled:
            raise ValueError("internet-facing projects must enable authentication")
        if self.project.type == "website" and (self.navigation is None or self.appearance is None):
            raise ValueError("website projects require navigation tabs and appearance")
        return self


def validate_project_spec(value: ProjectSpec | dict) -> ProjectSpec:
    """Validate and return an immutable Project Spec v1 model."""

    if isinstance(value, ProjectSpec):
        return value
    return ProjectSpec.model_validate(value)


def canonical_project_spec(value: ProjectSpec | dict) -> str:
    """Serialize a spec deterministically for storage, comparison, or hashing."""

    spec = validate_project_spec(value)
    return json.dumps(
        spec.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def project_spec_hash(value: ProjectSpec | dict) -> str:
    """Return the SHA-256 hash of the canonical Project Spec JSON."""

    return hashlib.sha256(canonical_project_spec(value).encode("utf-8")).hexdigest()
