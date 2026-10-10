"""Portable ZIP export for a validated static website workspace."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .security import SecurityAuditReport, SecurityAuditor


EXPORT_SCHEMA = "hermes.export/v1"
_EXCLUDED_PARTS = {".bth-create", "build-runs", ".git", ".venv", "venv", "node_modules", "__pycache__"}


class ExportReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: str = Field(default=EXPORT_SCHEMA, alias="schema")
    archive_name: str
    entry: str = "index.html"
    files: list[str] = Field(default_factory=list)
    security: SecurityAuditReport


def export_static_website(workspace: Path, destination: Path, archive_name: str) -> ExportReport:
    """Create a ZIP with only deployable workspace files and an export manifest."""
    workspace = workspace.resolve()
    if not (workspace / "index.html").is_file():
        raise ValueError("Export ต้องมี index.html เป็นจุดเริ่มต้นของเว็บไซต์")
    security = SecurityAuditor().audit(workspace)
    if security.status != "passed":
        raise ValueError("Security audit ไม่ผ่านก่อน Export")
    files = [
        path for path in sorted(workspace.rglob("*"))
        if path.is_file() and not path.is_symlink() and not any(part in _EXCLUDED_PARTS for part in path.relative_to(workspace).parts)
    ]
    if not files:
        raise ValueError("ไม่พบไฟล์เว็บไซต์สำหรับ Export")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": EXPORT_SCHEMA,
        "entry": "index.html",
        "files": [path.relative_to(workspace).as_posix() for path in files],
        "security": security.model_dump(mode="json", by_alias=True),
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(workspace).as_posix())
        archive.writestr("hermes-export.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return ExportReport(archive_name=archive_name, files=manifest["files"], security=security)


def export_filename(project_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", project_name.strip()).strip(".-") or "hermes-site"
    return f"{safe[:80]}.zip"


__all__ = ["EXPORT_SCHEMA", "ExportReport", "export_filename", "export_static_website"]
