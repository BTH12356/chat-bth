"""Phase 1 source model and persistence boundary for Hermes websites.

The source model is deliberately independent from the renderer and from model
calls.  It gives Preview, future editors, and Hermes one validated contract to
refer to.  A node id is derived from the project/page and semantic path, so it
does not change when text or styling changes.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SOURCE_MODEL_SCHEMA = "hermes.source-model/v1"
HERMES_CONTRACT_SCHEMA = "hermes.edit-contract/v1"
_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


def stable_node_id(project_id: str, page_id: str, semantic_path: str) -> str:
    """Return a compact, deterministic id for an editable element."""

    for value, label in ((project_id, "project_id"), (page_id, "page_id"), (semantic_path, "semantic_path")):
        if not value or "\x00" in value or value.strip() != value:
            raise ValueError(f"{label} must be a non-empty clean string")
    digest = hashlib.sha256(f"{project_id}\n{page_id}\n{semantic_path}".encode("utf-8")).hexdigest()[:16]
    return f"node-{digest}"


class SourceNode(SourceModel):
    id: str = Field(pattern=r"^node-[0-9a-f]{16}$")
    kind: Literal["element", "text", "image", "link", "section", "component"] = "element"
    tag: str = Field(min_length=1, max_length=32)
    path: str = Field(min_length=1, max_length=240)
    attributes: dict[str, str] = Field(default_factory=dict)
    styles: dict[str, str] = Field(default_factory=dict)
    content: str | None = Field(default=None, max_length=100_000)
    children: list["SourceNode"] = Field(default_factory=list)


SourceNode.model_rebuild()


class PageModel(SourceModel):
    id: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=240)
    root: SourceNode


class ThemeModel(SourceModel):
    id: str = Field(min_length=1, max_length=120)
    tokens: dict[str, str] = Field(default_factory=dict)


class ProjectSourceModel(SourceModel):
    schema_name: Literal[SOURCE_MODEL_SCHEMA] = Field(alias="schema")
    project_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    source_of_truth: Literal["html-css-js", "component-model"] = "html-css-js"
    revision: int = Field(default=1, ge=1)
    pages: list[PageModel] = Field(min_length=1, max_length=200)
    theme: ThemeModel
    assets: list[str] = Field(default_factory=list, max_length=10_000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_graph(self) -> "ProjectSourceModel":
        page_ids = [page.id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("page ids must be unique")
        node_ids: list[str] = []

        def visit(node: SourceNode) -> None:
            node_ids.append(node.id)
            for child in node.children:
                visit(child)

        for page in self.pages:
            visit(page.root)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node ids must be unique across the project")
        if len(self.assets) != len(set(self.assets)):
            raise ValueError("assets must be unique")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json", by_alias=True), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class HermesPatchOperation(SourceModel):
    op: Literal["set_text", "set_attribute", "set_style", "insert_node", "remove_node", "move_node"]
    target_node_id: str = Field(pattern=r"^node-[0-9a-f]{16}$")
    value: Any = None


class HermesPatch(SourceModel):
    patch_id: str = Field(min_length=1, max_length=120)
    base_revision: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=500)
    operations: list[HermesPatchOperation] = Field(min_length=1, max_length=100)


class HermesResponse(SourceModel):
    schema_name: Literal[HERMES_CONTRACT_SCHEMA] = Field(alias="schema")
    kind: Literal["answer", "clarification", "proposal"]
    message: str = Field(min_length=1, max_length=10_000)
    patch: HermesPatch | None = None
    requires_approval: Literal[True] = True

    @model_validator(mode="after")
    def proposal_requires_patch(self) -> "HermesResponse":
        if self.kind == "proposal" and self.patch is None:
            raise ValueError("proposal responses must include a structured patch")
        if self.kind != "proposal" and self.patch is not None:
            raise ValueError("only proposal responses may include a patch")
        return self


class ProjectStore:
    """Atomic current-state storage with append-only JSON revision snapshots."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.versions = self.root / "versions"

    def load(self) -> ProjectSourceModel:
        path = self.root / "project.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return ProjectSourceModel.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, model: ProjectSourceModel, *, expected_revision: int | None = None) -> ProjectSourceModel:
        current = None
        try:
            current = self.load()
        except FileNotFoundError:
            pass
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            raise ValueError("source model revision conflict")
        revision = (current.revision + 1) if current else model.revision
        saved = model.model_copy(update={"revision": revision, "updated_at": datetime.now(timezone.utc)})
        payload = saved.model_dump_json(by_alias=True, indent=2) + "\n"
        self.root.mkdir(parents=True, exist_ok=True)
        self.versions.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.versions / f"r{revision:06d}.json", payload)
        self._atomic_write(self.root / "project.json", payload)
        return saved

    def list_versions(self) -> list[int]:
        if not self.versions.exists():
            return []
        return sorted(int(path.stem[1:]) for path in self.versions.glob("r*.json") if path.stem[1:].isdigit())

    def load_version(self, revision: int) -> ProjectSourceModel:
        path = self.versions / f"r{revision:06d}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return ProjectSourceModel.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
