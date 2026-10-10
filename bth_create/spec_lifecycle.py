"""Generate, validate, and freeze BTH Create Project Specs.

This Phase 6 boundary turns completed form values into the structured source
of truth.  It does not run a build or reinterpret user conversation.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .blueprint import BlueprintStore
from .component import ComponentRegistry
from .page_recipe import PageRecipeStore
from .project_spec import ProjectSpec, project_spec_hash, validate_project_spec
from .theme import ThemeStore


_FREEZE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class LifecycleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResolvedProjectSpec(LifecycleModel):
    """A valid spec pinned to the catalog versions used to resolve it."""

    spec: ProjectSpec
    blueprint_version: str
    theme_version: str
    component_versions: dict[str, str]
    page_recipe_versions: dict[str, str] = Field(default_factory=dict)


class FrozenProjectSpec(LifecycleModel):
    project_spec_id: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=1)
    status: Literal["frozen"] = "frozen"
    frozen_at: datetime
    spec_hash: str = Field(min_length=64, max_length=64)
    project_spec: ProjectSpec
    blueprint_version: str
    theme_version: str
    component_versions: dict[str, str]
    page_recipe_versions: dict[str, str] = Field(default_factory=dict)

    @field_validator("project_spec_id")
    @classmethod
    def project_spec_id_must_be_safe(cls, value: str) -> str:
        if not _FREEZE_ID_PATTERN.fullmatch(value):
            raise ValueError("project spec id must use lowercase letters, numbers, dots, hyphens, or underscores")
        return value

    @property
    def frozen_id(self) -> str:
        return f"{self.project_spec_id}-r{self.revision}"


class ProjectSpecGenerator:
    """Deterministically map the v0.1 Internal Dashboard form to Project Spec v1."""

    def from_internal_dashboard_form(self, values: dict[str, Any]) -> ProjectSpec:
        return validate_project_spec(
            {
                "schema": "bth.project/v1",
                "project": {
                    "name": values.get("project_name", ""),
                    "type": values.get("project_type", "internal_dashboard"),
                },
                "blueprint": {"id": "dashboard.internal.v1"},
                "theme": {"id": values.get("theme", "windows_xp.v1")},
                "modules": values.get("modules", []),
                "network": {"scope": values.get("network_scope", "local")},
                "auth": {"enabled": values.get("auth_enabled", True)},
                "ai": {
                    "enabled": values.get("ai_assistant", False),
                    "capabilities": values.get("ai_capabilities", []),
                    "autonomy": values.get("ai_autonomy", "approval_required"),
                },
                "density": values.get("density", "compact"),
                "language": values.get("language", ["th", "en"]),
            }
        )

    def from_website_form(self, values: dict[str, Any]) -> ProjectSpec:
        tab_names = [str(name).strip() for name in values.get("tabs", []) if str(name).strip()]
        requested_types = [str(value) for value in values.get("page_types", [])]
        if requested_types and len(requested_types) != len(tab_names):
            raise ValueError("page types must match the number of navigation tabs")
        page_types = requested_types or [self._infer_page_type(name, index) for index, name in enumerate(tab_names)]
        slug_counts: dict[str, int] = {}
        tabs = []
        for index, (name, page_type) in enumerate(zip(tab_names, page_types), start=1):
            base_slug = {
                "home": "home", "about": "about", "policy": "policy", "document_library": "documents",
                "knowledge_library": "knowledge", "product_catalog": "products", "service": "services",
                "news": "news", "contact": "contact", "standard": "page",
            }.get(page_type, "page")
            slug_counts[base_slug] = slug_counts.get(base_slug, 0) + 1
            slug = base_slug if slug_counts[base_slug] == 1 else f"{base_slug}-{slug_counts[base_slug]}"
            tabs.append({"id": f"tab-{index}", "name": name, "slug": slug, "page_type": page_type})
        return validate_project_spec(
            {
                "schema": "bth.project/v1",
                "project": {"name": values.get("project_name", ""), "type": "website"},
                "blueprint": {"id": values.get("blueprint_id", "")},
                "theme": {"id": "website_standard.v1"},
                "modules": values.get("modules", []),
                "network": {"scope": values.get("network_scope", "internet")},
                "auth": {"enabled": values.get("auth_enabled", True)},
                "ai": {"enabled": False, "capabilities": [], "autonomy": "approval_required"},
                "density": values.get("density", "comfortable"),
                "language": values.get("language", ["th", "en"]),
                "navigation": {"tabs": tabs},
                "appearance": {"color_tone": values.get("color_tone", "blue")},
            }
        )

    @staticmethod
    def _infer_page_type(name: str, index: int) -> str:
        text = name.casefold()
        matches = (
            (("เกี่ยว", "about", "องค์กร", "company"), "about"),
            (("นโยบาย", "policy"), "policy"),
            (("กฎ", "ระเบียบ", "เอกสาร", "document", "download"), "document_library"),
            (("ความรู้", "หนังสือ", "library", "knowledge", "บทเรียน"), "knowledge_library"),
            (("สินค้า", "product", "ร้าน", "shop"), "product_catalog"),
            (("บริการ", "service"), "service"),
            (("ข่าว", "กิจกรรม", "news", "blog", "บทความ"), "news"),
            (("ติดต่อ", "contact", "แผนที่"), "contact"),
        )
        for keywords, page_type in matches:
            if any(keyword in text for keyword in keywords):
                return page_type
        return "home" if index == 0 else "standard"


class ProjectSpecResolver:
    """Validate a Project Spec against BTH's deterministic catalogs."""

    def __init__(
        self,
        blueprints: BlueprintStore | None = None,
        themes: ThemeStore | None = None,
        components: ComponentRegistry | None = None,
    ):
        self.blueprints = blueprints or BlueprintStore()
        self.themes = themes or ThemeStore()
        self.components = components or ComponentRegistry()

    def resolve(self, value: ProjectSpec | dict) -> ResolvedProjectSpec:
        spec = validate_project_spec(value)
        blueprint = self.blueprints.get(spec.blueprint.id)
        theme = self.themes.get(spec.theme.id)
        if spec.project.type != blueprint.type:
            raise ValueError("project type does not match blueprint type")
        selected = set(spec.modules)
        supported = set(blueprint.supported_modules)
        if not selected <= supported:
            raise ValueError("project spec contains modules unsupported by its blueprint")
        missing_required = set(blueprint.required_modules) - selected
        if missing_required:
            raise ValueError(f"project spec is missing required modules: {sorted(missing_required)}")
        for dependency in blueprint.dependencies:
            if dependency.module in selected and not set(dependency.requires) <= selected:
                raise ValueError(f"module {dependency.module} is missing blueprint dependencies")
        for incompatible in blueprint.incompatible_combinations:
            if set(incompatible) <= selected:
                raise ValueError(f"project spec contains incompatible modules: {incompatible}")
        if spec.network.scope not in blueprint.supported_network_modes:
            raise ValueError("network scope is unsupported by the blueprint")
        if spec.ai.enabled and not set(spec.ai.capabilities) <= set(blueprint.supported_ai_capabilities):
            raise ValueError("AI capability is unsupported by the blueprint")
        page_recipe_versions: dict[str, str] = {}
        if spec.project.type == "website" and spec.navigation:
            recipe_store = PageRecipeStore()
            selected_page_types = {page.page_type for page in spec.navigation.tabs}
            for page_type in selected_page_types:
                recipe = recipe_store.get(page_type)
                page_recipe_versions[recipe.id] = recipe.version
            if blueprint.supported_page_types and not selected_page_types <= set(blueprint.supported_page_types):
                raise ValueError("page type is unsupported by the blueprint")

        component_ids = [blueprint.default_component_mapping[module].id for module in spec.modules]
        if spec.auth.enabled:
            component_ids.append("auth")
        versions: dict[str, str] = {}
        pending = list(component_ids)
        while pending:
            component_id = pending.pop(0)
            if component_id in versions:
                continue
            component = self.components.get(component_id)
            if not self.components.compatible_with(component_id, blueprint.id):
                raise ValueError(f"component {component_id} is incompatible with blueprint {blueprint.id}")
            versions[component.id] = component.version
            pending.extend(component.dependencies)
        return ResolvedProjectSpec(
            spec=spec,
            blueprint_version=blueprint.version,
            theme_version=theme.version,
            component_versions=dict(sorted(versions.items())),
            page_recipe_versions=dict(sorted(page_recipe_versions.items())),
        )


class FreezeStore:
    """Append-only storage for frozen Project Spec revisions."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path.cwd() / ".bth_create" / "frozen_specs"

    def freeze(
        self,
        resolved: ResolvedProjectSpec,
        project_spec_id: str,
        frozen_at: datetime | None = None,
    ) -> FrozenProjectSpec:
        if not _FREEZE_ID_PATTERN.fullmatch(project_spec_id):
            raise ValueError("project spec id must use lowercase letters, numbers, dots, hyphens, or underscores")
        revision = self.next_revision(project_spec_id)
        frozen = FrozenProjectSpec(
            project_spec_id=project_spec_id,
            revision=revision,
            frozen_at=frozen_at or datetime.now(timezone.utc),
            spec_hash=project_spec_hash(resolved.spec),
            project_spec=resolved.spec,
            blueprint_version=resolved.blueprint_version,
            theme_version=resolved.theme_version,
            component_versions=resolved.component_versions,
            page_recipe_versions=resolved.page_recipe_versions,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(frozen.frozen_id)
        if path.exists():
            raise FileExistsError(f"frozen spec already exists: {frozen.frozen_id}")
        path.write_text(json.dumps(frozen.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return frozen

    def get(self, frozen_id: str) -> FrozenProjectSpec:
        path = self._path_for(frozen_id)
        if not path.is_file():
            raise KeyError(f"frozen spec not found: {frozen_id}")
        return FrozenProjectSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def next_revision(self, project_spec_id: str) -> int:
        if not self.root.exists():
            return 1
        prefix = f"{project_spec_id}-r"
        revisions = [
            int(path.stem.removeprefix(prefix))
            for path in self.root.glob(f"{project_spec_id}-r*.json")
            if path.stem.removeprefix(prefix).isdigit()
        ]
        return max(revisions, default=0) + 1

    def _path_for(self, frozen_id: str) -> Path:
        if not _FREEZE_ID_PATTERN.fullmatch(frozen_id.rsplit("-r", 1)[0]):
            raise KeyError(f"invalid frozen spec id: {frozen_id}")
        return self.root / f"{frozen_id}.json"
