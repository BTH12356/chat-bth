"""Compatibility smoke tests for optional voice/data dependencies."""

from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import io
import unittest


PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None


@unittest.skipUnless(PANDAS_AVAILABLE, "optional pandas dependency is not installed")
class OptionalVoiceStackTests(unittest.TestCase):
    def test_pandas_preserves_thai_csv_and_modern_string_dtype(self):
        import pandas as pd

        source = "ข้อความ,คะแนน\nสวัสดี,10\nทดสอบระบบ,8\n"
        frame = pd.read_csv(io.StringIO(source), dtype={"ข้อความ": "string"})
        self.assertEqual(frame["ข้อความ"].tolist(), ["สวัสดี", "ทดสอบระบบ"])
        self.assertEqual(str(frame["ข้อความ"].dtype), "string")

        output = io.StringIO()
        frame.to_csv(output, index=False, quoting=csv.QUOTE_MINIMAL)
        self.assertIn("สวัสดี", output.getvalue())
        self.assertIn("ทดสอบระบบ", output.getvalue())

    def test_optional_dependency_versions_are_the_reviewed_versions(self):
        self.assertEqual(importlib.metadata.version("pandas"), "3.0.6")
        self.assertEqual(importlib.metadata.version("tltk"), "1.10")


if __name__ == "__main__":
    unittest.main()
