"""Static security, accessibility, and resource checks for generated workspaces."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


SECURITY_AUDIT_SCHEMA = "hermes.security-audit/v1"
_UNSAFE_URL = re.compile(r"^(?:javascript|vbscript|file):", re.IGNORECASE)
_DATA_HTML = re.compile(r"^data:text/html", re.IGNORECASE)
_DANGEROUS_CODE = re.compile(r"\b(?:eval|Function|document\.write)\s*\(", re.IGNORECASE)


class SecurityIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    path: str
    line: int = Field(default=1, ge=1)
    message: str


class SecurityAuditReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: str = Field(default=SECURITY_AUDIT_SCHEMA, alias="schema")
    status: Literal["passed", "failed"]
    checks: dict[str, str]
    issues: list[SecurityIssue] = Field(default_factory=list)


def _local_reference(value: str) -> str | None:
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    return parsed.path.lstrip("/") or None


class _HTMLSecurityParser(HTMLParser):
    def __init__(self, path: Path, add_issue):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.add_issue = add_issue
        self.stack: list[tuple[str, int]] = []
        self.script_chunks: list[str] = []
        self.in_script = False
        self.has_lang = False

    def handle_starttag(self, tag: str, attrs_list):
        attrs = {key.lower(): value or "" for key, value in attrs_list}
        line = self.getpos()[0]
        tag = tag.lower()
        if tag == "html":
            self.has_lang = bool(attrs.get("lang"))
        for attr in ("href", "src", "action"):
            value = attrs.get(attr)
            if not value:
                continue
            if _UNSAFE_URL.match(value) or _DATA_HTML.match(value):
                self.add_issue("error", "unsafe-url", self.path, line, f"Unsafe {attr} URL is not allowed")
            elif value.startswith("data:") and attr != "src":
                self.add_issue("error", "unsafe-url", self.path, line, f"Data URL is not allowed in {attr}")
        if tag == "img" and "alt" not in attrs:
            self.add_issue("error", "missing-alt", self.path, line, "Images must define alt text")
        if tag == "a" and "href" not in attrs:
            self.add_issue("warning", "missing-href", self.path, line, "Links should define href")
        if attrs.get("target") == "_blank" and "noopener" not in attrs.get("rel", "").lower():
            self.add_issue("warning", "unsafe-target", self.path, line, "target=_blank should include rel=noopener")
        if tag == "script":
            self.in_script = True
            self.script_chunks = []
        if tag not in {"meta", "link", "img", "input", "br", "hr", "source", "area", "base", "embed", "param", "track", "wbr"}:
            self.stack.append((tag, line))

    def handle_endtag(self, tag: str):
        if tag.lower() == "script":
            code = "".join(self.script_chunks)
            if _DANGEROUS_CODE.search(code):
                self.add_issue("warning", "dangerous-script-api", self.path, self.getpos()[0], "Script uses a dynamically evaluated or document-writing API")
            self.in_script = False
            self.script_chunks = []
        if self.stack and self.stack[-1][0] == tag.lower():
            self.stack.pop()

    def handle_data(self, data: str):
        if self.in_script:
            self.script_chunks.append(data)


class SecurityAuditor:
    """Run deterministic checks without executing project code."""

    def audit(self, workspace: Path) -> SecurityAuditReport:
        workspace = workspace.resolve()
        issues: list[SecurityIssue] = []

        def add(severity: str, code: str, path: Path, line: int, message: str):
            issues.append(SecurityIssue(severity=severity, code=code, path=path.relative_to(workspace).as_posix(), line=max(1, line), message=message))

        allowed = {".html", ".css", ".js", ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".woff", ".woff2", ".ttf"}
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or ".bth-create" in path.parts or "build-runs" in path.parts:
                continue
            if path.suffix.lower() not in allowed:
                add("error", "unsupported-file", path, 1, f"File type {path.suffix or '(none)'} is outside the web workspace policy")
                continue
            try:
                text = path.read_text(encoding="utf-8") if path.suffix.lower() in {".html", ".css", ".js", ".json", ".svg"} else ""
            except UnicodeDecodeError:
                add("error", "invalid-text", path, 1, "Text resource is not valid UTF-8")
                continue
            if path.suffix.lower() == ".html":
                parser = _HTMLSecurityParser(path, add)
                try:
                    parser.feed(text)
                except Exception as error:  # HTMLParser is intentionally non-fatal.
                    add("error", "invalid-html", path, 1, f"HTML could not be inspected: {error}")
                if not parser.has_lang:
                    add("warning", "missing-lang", path, 1, "HTML should declare a document language")
                for match in re.finditer(r"\b(?:href|src)\s*=\s*[\"']([^\"']+)", text, re.IGNORECASE):
                    reference = _local_reference(match.group(1))
                    if reference and not (path.parent / reference).is_file() and not (workspace / reference).is_file():
                        add("error", "broken-reference", path, text[:match.start()].count("\n") + 1, f"Local resource does not exist: {match.group(1)}")
            elif path.suffix.lower() in {".js", ".svg"} and _DANGEROUS_CODE.search(text):
                add("warning", "dangerous-script-api", path, 1, "File contains a dynamically evaluated or document-writing API")
            elif path.suffix.lower() == ".css":
                if re.search(r"url\s*\(\s*(?:javascript:|data:text/html)", text, re.IGNORECASE):
                    add("error", "unsafe-css-url", path, 1, "CSS contains an unsafe resource URL")
                if re.search(r"@import\s+https?://", text, re.IGNORECASE):
                    add("warning", "remote-css", path, 1, "Remote CSS imports are discouraged by the workspace policy")
        status = "failed" if any(issue.severity == "error" for issue in issues) else "passed"
        return SecurityAuditReport(
            status=status,
            checks={
                "file_scope": "passed",
                "url_policy": "passed" if not any(i.code in {"unsafe-url", "unsafe-css-url"} for i in issues) else "failed",
                "accessibility": "passed" if not any(i.code.startswith("missing-") for i in issues) else "warning",
                "static_code": "passed",
            },
            issues=issues,
        )


__all__ = ["SECURITY_AUDIT_SCHEMA", "SecurityAuditReport", "SecurityAuditor", "SecurityIssue"]
