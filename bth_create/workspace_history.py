"""Phase 8 file-level checkpoints shared by visual, code, and Hermes edits."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class HistoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HistoryRevision(HistoryModel):
    revision: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=200)
    created_at: datetime
    files: dict[str, str]


class WorkspaceHistory:
    """Append-only snapshots with a movable current pointer for undo/redo."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.root = self.workspace / ".bth-create" / "history"
        self.revisions = self.root / "revisions"
        self.state_path = self.root / "state.json"

    def current_revision(self) -> int:
        state = self._read_state()
        return int(state.get("current", 0))

    def checkpoint(self, label: str) -> HistoryRevision:
        self.root.mkdir(parents=True, exist_ok=True)
        self.revisions.mkdir(parents=True, exist_ok=True)
        current = self.current_revision()
        revision = max([current, *self.list_revisions()], default=0) + 1
        snapshot = self.revisions / f"r{revision:06d}"
        snapshot.mkdir(parents=True, exist_ok=False)
        files: dict[str, str] = {}
        for path in self._tracked_files():
            relative = path.relative_to(self.workspace).as_posix()
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        record = HistoryRevision(revision=revision, label=label.strip() or "Workspace checkpoint", created_at=datetime.now(timezone.utc), files=dict(sorted(files.items())))
        (snapshot / "metadata.json").write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        self._write_state({"current": revision, "redo": []})
        return record

    def list_revisions(self) -> list[int]:
        if not self.revisions.exists():
            return []
        return sorted(int(path.name[1:]) for path in self.revisions.glob("r*") if path.is_dir() and path.name[1:].isdigit())

    def list(self) -> list[HistoryRevision]:
        result = []
        for revision in self.list_revisions():
            metadata = self.revisions / f"r{revision:06d}" / "metadata.json"
            if metadata.is_file(): result.append(HistoryRevision.model_validate_json(metadata.read_text(encoding="utf-8")))
        return result

    def undo(self) -> HistoryRevision:
        revisions = self.list_revisions()
        current = self.current_revision()
        previous = [item for item in revisions if item < current]
        if not previous: raise ValueError("ไม่มี revision ก่อนหน้าให้ Undo")
        target = max(previous)
        self._restore(target)
        self._write_state({"current": target, "redo": [current, *self._read_state().get("redo", [])]})
        return self.get(target)

    def redo(self) -> HistoryRevision:
        state = self._read_state()
        redo = list(state.get("redo", []))
        if not redo: raise ValueError("ไม่มี revision ถัดไปให้ Redo")
        target = redo.pop(0)
        self._restore(target)
        self._write_state({"current": target, "redo": redo})
        return self.get(target)

    def restore(self, revision: int) -> HistoryRevision:
        self.get(revision)
        current = self.current_revision()
        self._restore(revision)
        self._write_state({"current": revision, "redo": [current] if current and current != revision else []})
        return self.get(revision)

    def get(self, revision: int) -> HistoryRevision:
        metadata = self.revisions / f"r{revision:06d}" / "metadata.json"
        if not metadata.is_file(): raise KeyError(f"history revision not found: {revision}")
        return HistoryRevision.model_validate_json(metadata.read_text(encoding="utf-8"))

    def compare(self, from_revision: int, to_revision: int) -> list[dict[str, str]]:
        before = self.get(from_revision).files
        after = self.get(to_revision).files
        changes = []
        for path in sorted(set(before) | set(after)):
            if path not in before: status = "added"
            elif path not in after: status = "removed"
            elif before[path] != after[path]: status = "modified"
            else: continue
            changes.append({"path": path, "status": status})
        return changes

    def _restore(self, revision: int) -> None:
        record = self.get(revision)
        snapshot = self.revisions / f"r{revision:06d}"
        current = {path.relative_to(self.workspace).as_posix() for path in self._tracked_files()}
        for relative in current - set(record.files):
            (self.workspace / relative).unlink(missing_ok=True)
        for relative in record.files:
            source = snapshot / relative
            target = self.workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _tracked_files(self) -> list[Path]:
        ignored = {".bth-create", ".git", ".venv", "venv", "node_modules", "__pycache__"}
        return [path for path in sorted(self.workspace.rglob("*")) if path.is_file() and not any(part in ignored for part in path.relative_to(self.workspace).parts)]

    def _read_state(self) -> dict:
        if not self.state_path.is_file(): return {"current": 0, "redo": []}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
