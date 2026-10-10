"""Deterministic Gap Analysis for a frozen BTH Create Project Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .blueprint import BlueprintStore
from .component import ComponentRegistry
from .project_spec import project_spec_hash
from .spec_lifecycle import FrozenProjectSpec
from .theme import ThemeStore


GapCategory = Literal["REUSE", "CONFIGURE", "COMPOSE", "MISSING"]


class GapModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GapItem(GapModel):
    requirement_id: str = Field(min_length=1, max_length=160)
    category: GapCategory
    reason: str = Field(min_length=1, max_length=500)
    component_id: str | None = None


class GapAnalysisReport(GapModel):
    frozen_spec_id: str = Field(min_length=1)
    spec_hash: str = Field(min_length=64, max_length=64)
    reuse: list[GapItem] = Field(default_factory=list)
    configure: list[GapItem] = Field(default_factory=list)
    compose: list[GapItem] = Field(default_factory=list)
    missing: list[GapItem] = Field(default_factory=list)

    @property
    def status(self) -> Literal["ready", "gaps_found"]:
        return "gaps_found" if self.missing else "ready"

    @property
    def all_items(self) -> list[GapItem]:
        return self.reuse + self.configure + self.compose + self.missing


class GapAnalyzer:
    """Classify frozen requirements without model calls or code generation."""

    def __init__(
        self,
        blueprints: BlueprintStore | None = None,
        themes: ThemeStore | None = None,
        components: ComponentRegistry | None = None,
    ):
        self.blueprints = blueprints or BlueprintStore()
        self.themes = themes or ThemeStore()
        self.components = components or ComponentRegistry()

    def analyze(
        self,
        frozen: FrozenProjectSpec,
        additional_requirements: list[str] | None = None,
    ) -> GapAnalysisReport:
        if project_spec_hash(frozen.project_spec) != frozen.spec_hash:
            raise ValueError("frozen spec hash does not match its project spec")
        blueprint = self.blueprints.get(frozen.project_spec.blueprint.id)
        self.themes.get(frozen.project_spec.theme.id)
        report = GapAnalysisReport(frozen_spec_id=frozen.frozen_id, spec_hash=frozen.spec_hash)
        reuse: list[GapItem] = []
        missing: list[GapItem] = []

        for module in frozen.project_spec.modules:
            component_id = blueprint.default_component_mapping[module].id
            component = self.components.get(component_id)
            frozen_version = frozen.component_versions.get(component_id)
            if component.status == "verified" and component.version == frozen_version:
                reuse.append(
                    GapItem(
                        requirement_id=f"module.{module}",
                        category="REUSE",
                        component_id=component_id,
                        reason="A verified component matches the frozen component version.",
                    )
                )
            else:
                missing.append(
                    GapItem(
                        requirement_id=f"module.{module}",
                        category="MISSING",
                        component_id=component_id,
                        reason="No verified component matches the frozen component version.",
                    )
                )

        if frozen.project_spec.auth.enabled:
            auth = self.components.get("auth")
            if auth.status == "verified" and frozen.component_versions.get("auth") == auth.version:
                reuse.append(GapItem(requirement_id="auth", category="REUSE", component_id="auth", reason="Verified authentication component is pinned by the frozen spec."))
            else:
                missing.append(GapItem(requirement_id="auth", category="MISSING", component_id="auth", reason="Authentication component is unavailable or differs from the frozen version."))

        configure = [
            GapItem(requirement_id="project.name", category="CONFIGURE", reason="Project name is supplied by the frozen spec."),
            GapItem(requirement_id="network.scope", category="CONFIGURE", reason="Network scope is supplied by the frozen spec."),
            GapItem(requirement_id="theme", category="CONFIGURE", reason="The frozen theme ID and version provide visual configuration."),
            GapItem(requirement_id="density", category="CONFIGURE", reason="Density is supplied by the frozen spec."),
            GapItem(requirement_id="language", category="CONFIGURE", reason="Languages are supplied by the frozen spec."),
        ]
        if frozen.project_spec.project.type == "website":
            configure.extend([
                GapItem(requirement_id="navigation.tabs", category="CONFIGURE", reason="Tab names and order are supplied by the frozen spec."),
                GapItem(requirement_id="navigation.page_types", category="CONFIGURE", reason="Each page type and URL slug is supplied by the frozen spec."),
                GapItem(requirement_id="appearance.color_tone", category="CONFIGURE", reason="Color tone is supplied by the frozen spec."),
            ])
            if frozen.project_spec.blueprint.id.startswith("catalog."):
                compose = [
                    GapItem(requirement_id="catalog.layout", category="COMPOSE", component_id="site_shell", reason="Compose the selected reusable catalog Blueprint."),
                    GapItem(requirement_id="catalog.navigation", category="COMPOSE", component_id="topic_navigation", reason="Compose configured tabs as catalog topics and searchable sections."),
                ]
            else:
                compose = [
                    GapItem(requirement_id="website.layout", category="COMPOSE", component_id="site_shell", reason="Compose the selected standard website Blueprint."),
                    GapItem(requirement_id="website.navigation", category="COMPOSE", component_id="navigation_tabs", reason="Compose configured tabs into responsive navigation and sections."),
                ]
                if "page_composer" in frozen.project_spec.modules:
                    compose.append(GapItem(requirement_id="website.pages", category="COMPOSE", component_id="page_composer", reason="Compose each configured page from its deterministic Page Recipe and content blocks."))
        else:
            compose = [
                GapItem(requirement_id="dashboard.layout", category="COMPOSE", reason="Compose dashboard shell and selected module components using Blueprint layout rules."),
                GapItem(requirement_id="dashboard.navigation", category="COMPOSE", component_id="sidebar", reason="Compose navigation with the selected dashboard modules."),
            ]
        for index, requirement in enumerate(additional_requirements or [], start=1):
            text = requirement.strip()
            if text:
                missing.append(GapItem(requirement_id=f"custom.{index}", category="MISSING", reason=f"No catalog component or deterministic rule resolves: {text}"))
        return GapAnalysisReport(reuse=reuse, configure=configure, compose=compose, missing=missing, frozen_spec_id=frozen.frozen_id, spec_hash=frozen.spec_hash)
