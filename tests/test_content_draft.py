import tempfile
import unittest
from pathlib import Path

from bth_create.content_draft import draft_website_content, personalize_website_workspace


class ContentDraftTests(unittest.TestCase):
    def test_creates_thai_starter_copy_and_replaces_template_text(self):
        values = {
            "project_name": "บ้านสุขภาพ",
            "content_about": "ร้านสินค้าเพื่อสุขภาพจากชุมชน",
            "content_offer": "สินค้าออร์แกนิกและชุดของขวัญ",
            "content_audience": "คนรักสุขภาพ",
            "content_contact": "โทร 02-123-4567",
        }
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "index.html"
            page.write_text("พื้นที่ดิจิทัลที่รวบรวมข้อมูล บริการ และเรื่องสำคัญขององค์กรไว้ในที่เดียว เนื้อหาส่วนนี้พร้อมสำหรับใส่รายละเอียดจริงขององค์กร กรอกข้อมูลเพื่อให้ทีมงานติดต่อกลับ", encoding="utf-8")
            draft = personalize_website_workspace(Path(directory), values)
            source = page.read_text(encoding="utf-8")
        self.assertIsNotNone(draft)
        self.assertIn("สินค้าออร์แกนิก", draft.hero)
        self.assertIn("บ้านสุขภาพ", draft.overview)
        self.assertIn("โทร 02-123-4567", source)
        self.assertNotIn("ข้อความตัวอย่าง", source)

    def test_skips_draft_when_required_content_is_missing(self):
        self.assertIsNone(draft_website_content({"content_about": "ข้อมูลเดียว"}))


if __name__ == "__main__":
    unittest.main()
