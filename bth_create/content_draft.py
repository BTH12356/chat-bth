"""Create safe Thai starter copy from Guided Build answers."""

from __future__ import annotations

import html
from pathlib import Path

from pydantic import BaseModel, Field


class WebsiteContentDraft(BaseModel):
    hero: str = Field(min_length=1, max_length=1200)
    overview: str = Field(min_length=1, max_length=1600)
    contact: str = Field(min_length=1, max_length=800)


def draft_website_content(values: dict) -> WebsiteContentDraft | None:
    about = str(values.get("content_about", "")).strip()
    offer = str(values.get("content_offer", "")).strip()
    if not about or not offer:
        return None
    project = str(values.get("project_name", "เว็บไซต์ของเรา")).strip() or "เว็บไซต์ของเรา"
    audience = str(values.get("content_audience", "")).strip()
    contact = str(values.get("content_contact", "")).strip()
    hero = f"{about} {offer}".strip()
    overview = f"{project} {about} เรานำเสนอ {offer}"
    if audience and audience not in {"ไม่มี", "-"}:
        overview += f" เพื่อช่วยให้ {audience} เข้าถึงข้อมูลและตัดสินใจได้อย่างมั่นใจ"
    overview += "."
    contact_copy = contact if contact and contact not in {"ไม่มี", "-"} else f"สอบถามข้อมูลเพิ่มเติมเกี่ยวกับ {project} ได้ผ่านช่องทางติดต่อของเรา"
    return WebsiteContentDraft(hero=hero, overview=overview, contact=contact_copy)


def personalize_website_workspace(workspace: Path, values: dict) -> WebsiteContentDraft | None:
    """Replace deterministic template copy only; user text is always HTML-escaped."""
    draft = draft_website_content(values)
    if draft is None:
        return None
    hero = html.escape(draft.hero)
    overview = html.escape(draft.overview)
    contact = html.escape(draft.contact)
    for path in workspace.glob("*.html"):
        source = path.read_text(encoding="utf-8")
        source = source.replace("พื้นที่ดิจิทัลที่รวบรวมข้อมูล บริการ และเรื่องสำคัญขององค์กรไว้ในที่เดียว", hero)
        source = source.replace("เนื้อหาส่วนนี้พร้อมสำหรับใส่รายละเอียดจริงขององค์กร", overview)
        source = source.replace("กรอกข้อมูลเพื่อให้ทีมงานติดต่อกลับ", contact)
        path.write_text(source, encoding="utf-8")
    return draft


__all__ = ["WebsiteContentDraft", "draft_website_content", "personalize_website_workspace"]
