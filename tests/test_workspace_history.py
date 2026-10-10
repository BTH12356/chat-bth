import tempfile
import unittest
from pathlib import Path

from bth_create.workspace_history import WorkspaceHistory


class WorkspaceHistoryTests(unittest.TestCase):
    def test_undo_redo_and_restore_share_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "index.html"
            file.write_text("one", encoding="utf-8")
            history = WorkspaceHistory(root)
            first = history.checkpoint("initial")
            file.write_text("two", encoding="utf-8")
            second = history.checkpoint("changed")
            file.write_text("three", encoding="utf-8")
            history.undo()
            self.assertEqual(file.read_text(encoding="utf-8"), "one")
            history.redo()
            self.assertEqual(file.read_text(encoding="utf-8"), "two")
            history.restore(first.revision)
            self.assertEqual(file.read_text(encoding="utf-8"), "one")
            self.assertEqual(history.current_revision(), first.revision)
            self.assertEqual(second.revision, 2)


if __name__ == "__main__":
    unittest.main()
