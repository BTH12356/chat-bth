"""Structured Verification Pipeline and Build Manifest for BTH Create."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from time import perf_counter
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .blueprint import BlueprintStore
from .build_engine import BuildResult
from .component import ComponentRegistry
from .page_recipe import PageRecipeStore
from .project_spec import project_spec_hash, validate_project_spec
from .spec_lifecycle import FrozenProjectSpec
from .theme import ThemeStore


class VerificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerificationResult(VerificationModel):
    test: str
    status: Literal["passed", "failed", "skipped"]
    details: list[str] = Field(default_factory=list)
    duration_ms: float = Field(ge=0)


class VerificationReport(VerificationModel):
    frozen_spec_id: str
    status: Literal["passed", "failed"]
    results: list[VerificationResult]


class ManifestReference(VerificationModel):
    id: str
    version: str


class ManifestVerification(VerificationModel):
    status: Literal["passed"]
    tests: int


class BuildManifest(VerificationModel):
    schema_name: Literal["bth.build/v1"] = Field(default="bth.build/v1", alias="schema")
    product: str
    project_spec: str
    spec_hash: str
    blueprint: ManifestReference
    theme: ManifestReference
    components: dict[str, str]
    page_recipes: dict[str, str] = Field(default_factory=dict)
    generated_components: list[str]
    artifacts: dict[str, str]
    verification: ManifestVerification


class _UIParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.classes: list[str] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"] or "")
        if attributes.get("class"):
            self.classes.extend((attributes["class"] or "").split())
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"] or "")
        if tag == "link" and attributes.get("rel") == "stylesheet" and attributes.get("href"):
            self.stylesheets.append(attributes["href"] or "")
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"] or "")


class VerificationPipeline:
    REQUIRED_FILES = ("index.html", "styles.css", "app.js", "project-config.json")

    def __init__(
        self,
        blueprints: BlueprintStore | None = None,
        themes: ThemeStore | None = None,
        components: ComponentRegistry | None = None,
    ):
        self.blueprints = blueprints or BlueprintStore()
        self.themes = themes or ThemeStore()
        self.components = components or ComponentRegistry()

    def verify(self, frozen: FrozenProjectSpec, build: BuildResult) -> VerificationReport:
        workspace = Path(build.workspace)
        checks: list[tuple[str, Callable[[], list[str]]]] = [
            ("schema_validation", lambda: self._schema_validation(frozen, build)),
            ("component_validation", lambda: self._component_validation(frozen)),
            ("component_dependency_validation", lambda: self._dependency_validation(frozen)),
            ("build_validation", lambda: self._build_validation(workspace, build)),
            ("static_checks", lambda: self._static_checks(workspace)),
            ("unit_tests", lambda: self._unit_tests(frozen, workspace)),
            ("integration_tests", lambda: self._integration_tests(frozen, workspace)),
            ("basic_ui_test", lambda: self._basic_ui_test(frozen, workspace)),
            ("output_verification", lambda: self._output_verification(workspace, build)),
        ]
        results = [self._run_check(name, check) for name, check in checks]
        status = "passed" if all(result.status in ("passed", "skipped") for result in results) else "failed"
        return VerificationReport(frozen_spec_id=frozen.frozen_id, status=status, results=results)

    def create_manifest(self, frozen: FrozenProjectSpec, build: BuildResult, report: VerificationReport) -> BuildManifest:
        if report.status != "passed":
            raise ValueError("build manifest cannot be created from failed verification")
        workspace = Path(build.workspace)
        artifact_hashes = {
            relative: hashlib.sha256((workspace / relative).read_bytes()).hexdigest()
            for relative in build.artifacts
        }
        return BuildManifest(
            product=frozen.project_spec.project.name,
            project_spec=frozen.frozen_id,
            spec_hash=frozen.spec_hash,
            blueprint=ManifestReference(id=frozen.project_spec.blueprint.id, version=frozen.blueprint_version),
            theme=ManifestReference(id=frozen.project_spec.theme.id, version=frozen.theme_version),
            components=frozen.component_versions,
            page_recipes=frozen.page_recipe_versions,
            generated_components=build.generated_components,
            artifacts=dict(sorted(artifact_hashes.items())),
            verification=ManifestVerification(status="passed", tests=len(report.results)),
        )

    def write_manifest(self, frozen: FrozenProjectSpec, build: BuildResult, report: VerificationReport) -> Path:
        manifest = self.create_manifest(frozen, build, report)
        path = Path(build.workspace) / "build_manifest.json"
        if path.exists():
            raise FileExistsError(f"build manifest already exists: {path}")
        path.write_text(json.dumps(manifest.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _run_check(self, name: str, check: Callable[[], list[str]]) -> VerificationResult:
        started = perf_counter()
        try:
            details = check()
            status: Literal["passed", "failed", "skipped"] = "passed"
        except Exception as exc:
            details = [str(exc)]
            status = "failed"
        return VerificationResult(test=name, status=status, details=details, duration_ms=(perf_counter() - started) * 1000)

    def _schema_validation(self, frozen: FrozenProjectSpec, build: BuildResult) -> list[str]:
        validate_project_spec(frozen.project_spec)
        if project_spec_hash(frozen.project_spec) != frozen.spec_hash:
            raise ValueError("Frozen Project Spec hash mismatch.")
        if build.frozen_spec_id != frozen.frozen_id or build.spec_hash != frozen.spec_hash:
            raise ValueError("Build identity does not match Frozen Project Spec.")
        recipe_store = PageRecipeStore()
        for recipe_id, version in frozen.page_recipe_versions.items():
            if recipe_store.get(recipe_id).version != version:
                raise ValueError(f"Page Recipe version mismatch: {recipe_id}@{version}")
        return ["Project Spec schema and identity are valid."]

    def _component_validation(self, frozen: FrozenProjectSpec) -> list[str]:
        blueprint = self.blueprints.get(frozen.project_spec.blueprint.id)
        self.themes.get(frozen.project_spec.theme.id)
        for component_id, version in frozen.component_versions.items():
            component = self.components.get(component_id)
            if component.version != version:
                raise ValueError(f"Component version mismatch: {component_id}@{version}")
            if blueprint.id not in component.compatible_blueprints:
                raise ValueError(f"Component is incompatible with blueprint: {component_id}")
        return [f"Validated {len(frozen.component_versions)} pinned components."]

    def _dependency_validation(self, frozen: FrozenProjectSpec) -> list[str]:
        pinned = set(frozen.component_versions)
        for component_id in pinned:
            missing = set(self.components.get(component_id).dependencies) - pinned
            if missing:
                raise ValueError(f"Component {component_id} has unpinned dependencies: {sorted(missing)}")
        return ["All component dependencies are pinned."]

    def _build_validation(self, workspace: Path, build: BuildResult) -> list[str]:
        if build.status != "built" or not workspace.is_dir():
            raise ValueError("Build workspace is unavailable.")
        missing = [name for name in self.REQUIRED_FILES if not (workspace / name).is_file()]
        if missing:
            raise ValueError(f"Required build files are missing: {missing}")
        return ["Required build artifacts are present."]

    def _static_checks(self, workspace: Path) -> list[str]:
        for name in ("styles.css", *[path.name for path in workspace.glob("*.html")]):
            if "{{" in (workspace / name).read_text(encoding="utf-8"):
                raise ValueError(f"Unresolved template token in {name}")
        json.loads((workspace / "project-config.json").read_text(encoding="utf-8"))
        node = shutil.which("node")
        if node:
            result = subprocess.run([node, "--check", str(workspace / "app.js")], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise ValueError(result.stderr.strip() or "JavaScript syntax check failed.")
            return ["Template, JSON, and JavaScript static checks passed."]
        return ["Template and JSON checks passed; Node.js syntax check unavailable."]

    def _unit_tests(self, frozen: FrozenProjectSpec, workspace: Path) -> list[str]:
        source = (workspace / "index.html").read_text(encoding="utf-8")
        if frozen.project_spec.project.type == "website":
            config = json.loads((workspace / "project-config.json").read_text(encoding="utf-8"))
            if config["project"].get("modules") != frozen.project_spec.modules:
                raise ValueError("Configured website modules do not match Project Spec.")
            if frozen.project_spec.blueprint.id.startswith("catalog."):
                for tab in frozen.project_spec.navigation.tabs:
                    if f'id="{tab.id}"' not in source or tab.name not in source:
                        raise ValueError(f"Rendered catalog topic is missing: {tab.name}")
                return [f"Rendered {len(frozen.project_spec.navigation.tabs)} configured catalog topics."]
            pages = frozen.project_spec.navigation.tabs
            for index, page in enumerate(pages):
                filename = "index.html" if index == 0 else f"{page.slug or page.id}.html"
                page_source = (workspace / filename).read_text(encoding="utf-8")
                if f'id="{page.id}"' not in page_source or page.name not in page_source:
                    raise ValueError(f"Rendered website page is missing: {page.name}")
                if f'data-page-recipe="{page.page_type}"' not in page_source:
                    raise ValueError(f"Page recipe is missing: {page.name}")
            return [f"Rendered {len(pages)} configured website pages with individual recipes."]
        for module in frozen.project_spec.modules:
            if f'data-component="' not in source or module.replace("_", " ").title() not in source:
                raise ValueError(f"Rendered module card is missing: {module}")
        return [f"Rendered {len(frozen.project_spec.modules)} requested module cards."]

    def _integration_tests(self, frozen: FrozenProjectSpec, workspace: Path) -> list[str]:
        config = json.loads((workspace / "project-config.json").read_text(encoding="utf-8"))
        if config.get("frozen_spec_id") != frozen.frozen_id or config.get("spec_hash") != frozen.spec_hash:
            raise ValueError("Runtime configuration is not bound to the Frozen Project Spec.")
        page_files = list(workspace.glob("*.html"))
        for page_file in page_files:
            source = page_file.read_text(encoding="utf-8")
            if 'href="styles.css"' not in source or 'src="app.js"' not in source:
                raise ValueError(f"Application assets are not integrated into {page_file.name}.")
            parser = _UIParser()
            parser.feed(source)
            for link in parser.links:
                if link.endswith(".html") and not (workspace / link).is_file():
                    raise ValueError(f"Broken internal page link in {page_file.name}: {link}")
        return [f"Runtime configuration, assets, and links are integrated across {len(page_files)} pages."]

    def _basic_ui_test(self, frozen: FrozenProjectSpec, workspace: Path) -> list[str]:
        if frozen.project_spec.project.type == "website":
            if frozen.project_spec.blueprint.id.startswith("catalog."):
                parser = _UIParser()
                parser.feed((workspace / "index.html").read_text(encoding="utf-8"))
                if "site-shell" not in parser.classes or "site-nav" not in parser.classes:
                    raise ValueError("Required catalog website shell elements are missing.")
                if parser.classes.count("site-section") != len(frozen.project_spec.navigation.tabs):
                    raise ValueError("Visible catalog section count does not match configured topics.")
                required_ids = {"catalog-search", "catalog-sort", "add-item-dialog", "item-detail-dialog"}
                missing_ids = required_ids - parser.ids
                if missing_ids:
                    raise ValueError(f"Required catalog controls are missing: {sorted(missing_ids)}")
                if "build-status" not in parser.ids:
                    raise ValueError("Build status element is missing.")
                return ["Basic catalog UI structure matches the configured topics."]
            expected_pages = frozen.project_spec.navigation.tabs
            for index, page in enumerate(expected_pages):
                filename = "index.html" if index == 0 else f"{page.slug or page.id}.html"
                parser = _UIParser()
                parser.feed((workspace / filename).read_text(encoding="utf-8"))
                if "site-shell" not in parser.classes or "site-nav" not in parser.classes or parser.classes.count("site-section") != 1:
                    raise ValueError(f"Required multi-page shell elements are missing from {filename}.")
                if "build-status" not in parser.ids:
                    raise ValueError(f"Build status element is missing from {filename}.")
            return [f"Basic UI structure is valid across {len(expected_pages)} website pages."]
        else:
            parser = _UIParser()
            parser.feed((workspace / "index.html").read_text(encoding="utf-8"))
            if "window" not in parser.classes or "statusbar" not in parser.classes:
                raise ValueError("Required Windows XP shell elements are missing.")
            if parser.classes.count("module-card") != len(frozen.project_spec.modules):
                raise ValueError("Visible module card count does not match Project Spec.")
        if "build-status" not in parser.ids:
            raise ValueError("Build status element is missing.")
        return ["Basic UI structure matches the selected modules and theme shell."]

    def _output_verification(self, workspace: Path, build: BuildResult) -> list[str]:
        for relative in build.artifacts:
            path = workspace / relative
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Build artifact is missing or empty: {relative}")
            if workspace.resolve() not in path.resolve().parents:
                raise ValueError(f"Build artifact escapes workspace: {relative}")
        return [f"Verified {len(build.artifacts)} non-empty build artifacts."]
