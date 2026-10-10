import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app
from bth_create.source_model import HermesPatch, HermesPatchOperation


class PreviewEditingTests(unittest.TestCase):
    def test_selected_node_is_precise_and_approved_patch_updates_only_it(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(web_app, "WORKSPACE_ROOT", Path(directory)), patch.object(web_app, "get_project", return_value={"id": "project-1", "name": "Demo"}):
            root = Path(directory) / "project-1"
            root.mkdir()
            selected = "node-0123456789abcdef"
            other = "node-fedcba9876543210"
            (root / "index.html").write_text(
                f'<html lang="th"><body><h1 data-node-id="{selected}">Before</h1><p data-node-id="{other}">Untouched</p></body></html>',
                encoding="utf-8",
            )
            node = web_app.inspect_preview_node("project-1", selected)
            self.assertEqual(node["text"], "Before")
            self.assertEqual(node["path"], "index.html")
            revision = web_app.workspace_history("project-1").checkpoint("initial").revision
            edit_patch = HermesPatch(
                patch_id="patch-1",
                base_revision=revision,
                summary="Change heading",
                operations=[HermesPatchOperation(op="set_text", target_node_id=selected, value="After")],
            )

            result = web_app.apply_edit_patch("project-1", edit_patch)

            self.assertEqual(result["status"], "applied")
            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn(">After</h1>", page)
            self.assertIn(">Untouched</p>", page)


if __name__ == "__main__":
    unittest.main()
