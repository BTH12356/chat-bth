import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bth_create.exporter import export_filename, export_static_website


class ExporterTests(unittest.TestCase):
    def test_exports_deployable_files_and_preserves_asset_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "site"
            root.mkdir()
            (root / "assets").mkdir()
            (root / "index.html").write_text('<html lang="th"><head><link href="assets/site.css" rel="stylesheet"></head><body>สวัสดี</body></html>', encoding="utf-8")
            (root / "assets" / "site.css").write_text("body { color: #123456; }", encoding="utf-8")
            (root / ".bth-create").mkdir()
            (root / ".bth-create" / "private.txt").write_text("not exported", encoding="utf-8")
            archive = Path(directory) / "website.zip"

            report = export_static_website(root, archive, "website.zip")

            self.assertEqual(report.security.status, "passed")
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()), {"index.html", "assets/site.css", "hermes-export.json"})
                manifest = json.loads(bundle.read("hermes-export.json"))
                self.assertEqual(manifest["entry"], "index.html")
                self.assertIn("assets/site.css", manifest["files"])

    def test_refuses_export_when_security_audit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text('<html lang="th"><body><a href="javascript:alert(1)">unsafe</a></body></html>', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Security audit"):
                export_static_website(root, root / "unsafe.zip", "unsafe.zip")

    def test_filename_is_portable(self):
        self.assertEqual(export_filename("ร้านค้า / Summer 2026"), "Summer-2026.zip")


if __name__ == "__main__":
    unittest.main()
