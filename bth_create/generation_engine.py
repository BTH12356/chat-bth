"""Phase 3 website generation boundary.

BuildEngine performs the template composition.  This module is the product
boundary around it: it validates generated HTML/resource references and
returns a structured report that Preview and the Editor can consume.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .build_engine import BuildEngine, BuildResult, MissingPartGenerator
from .gap_analysis import GapAnalysisReport
from .spec_lifecycle import FrozenProjectSpec
from .task_dag import TaskDAG
from .source_model import stable_node_id


GENERATION_REPORT_SCHEMA = "hermes.generation-report/v1"


class GenerationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GeneratedArtifact(GenerationModel):
    path: str
    kind: Literal["html", "css", "javascript", "json", "asset"]
    bytes: int = Field(ge=0)


class GenerationReport(GenerationModel):
    status: Literal["generated"] = "generated"
    frozen_spec_id: str
    source_of_truth: Literal["html-css-js"] = "html-css-js"
    artifacts: list[GeneratedArtifact]
    page_paths: list[str]
    node_ids: list[str]
    checked_references: list[str]
    content: dict[str, dict[str, str]]
    structure: dict[str, list[str]]
    theme: dict[str, str]


class _GeneratedHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.node_ids: list[str] = []
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("data-node-id"):
            self.node_ids.append(values["data-node-id"] or "")
        for key in ("href", "src"):
            reference = values.get(key)
            if reference and not reference.startswith(("#", "/", "//", "http:", "https:", "mailto:", "data:", "javascript:")):
                self.references.append(reference.split("?", 1)[0].split("#", 1)[0])


class WebsiteGenerationEngine:
    """Generate from a frozen, already-resolved spec only."""

    def __init__(self, build_engine: BuildEngine | None = None):
        self.build_engine = build_engine or BuildEngine()

    def generate(
        self,
        frozen: FrozenProjectSpec,
        report: GapAnalysisReport,
        dag: TaskDAG,
        workspace_root: Path,
        missing_generator: MissingPartGenerator | None = None,
    ) -> tuple[BuildResult, GenerationReport]:
        build = self.build_engine.build(frozen, report, dag, workspace_root, missing_generator=missing_generator)
        workspace = Path(build.workspace)
        self._annotate_editable_nodes(workspace, frozen, build.artifacts)
        parser = _GeneratedHTMLParser()
        page_paths: list[str] = []
        artifacts: list[GeneratedArtifact] = []
        references: list[str] = []
        for relative in build.artifacts:
            path = workspace / relative
            suffix = path.suffix.lower()
            kind = {".html": "html", ".css": "css", ".js": "javascript", ".json": "json"}.get(suffix, "asset")
            artifacts.append(GeneratedArtifact(path=relative, kind=kind, bytes=path.stat().st_size))
            if suffix == ".html":
                page_paths.append(relative)
                parser.feed(path.read_text(encoding="utf-8"))
        if len(parser.node_ids) != len(set(parser.node_ids)):
            raise ValueError("generated website contains duplicate data-node-id values")
        if not parser.node_ids:
            raise ValueError("generated website contains no editable data-node-id values")
        for html_path in page_paths:
            source = (workspace / html_path).read_text(encoding="utf-8")
            local = _GeneratedHTMLParser()
            local.feed(source)
            for reference in local.references:
                target = (workspace / html_path).parent / reference
                if not target.is_file():
                    raise ValueError(f"generated resource reference is missing: {html_path} -> {reference}")
                references.append(f"{html_path}:{reference}")
        return build, GenerationReport(
            frozen_spec_id=frozen.frozen_id,
            artifacts=artifacts,
            page_paths=sorted(page_paths),
            node_ids=sorted(parser.node_ids),
            checked_references=sorted(set(references)),
            content={page.id: {"title": page.name, "path": ("index.html" if index == 0 else f"{page.slug or page.id}.html")} for index, page in enumerate(frozen.project_spec.navigation.tabs if frozen.project_spec.navigation else [])},
            structure={page.id: list(self.build_engine.page_recipes.get(page.page_type).blocks) for page in (frozen.project_spec.navigation.tabs if frozen.project_spec.navigation else [])},
            theme={"id": frozen.project_spec.theme.id, "version": frozen.theme_version},
        )

    @staticmethod
    def _annotate_editable_nodes(workspace: Path, frozen: FrozenProjectSpec, artifacts: list[str]) -> None:
        editable = re.compile(r"<(main|header|footer|section|article|h[1-6]|p|a|button|label|input|textarea|select|img|li)(\s[^>]*?)?>", re.IGNORECASE)
        for relative in artifacts:
            path = workspace / relative
            if path.suffix.lower() != ".html":
                continue
            source = path.read_text(encoding="utf-8")
            counter = 0

            def add_id(match: re.Match[str]) -> str:
                nonlocal counter
                opening = match.group(0)
                if "data-node-id=" in opening:
                    return opening
                counter += 1
                node_id = stable_node_id(frozen.project_spec.project.name.casefold().strip(), path.stem, f"dom/{match.group(1).lower()}/{counter}")
                return opening[:-1] + f' data-node-id="{node_id}">'

            updated = editable.sub(add_id, source)
            if updated != source:
                path.write_text(updated, encoding="utf-8")
