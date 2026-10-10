import json
import re
import tempfile
import unittest
from pathlib import Path

from bth_create.form_engine import FormStore, RuleEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.generation_engine import WebsiteGenerationEngine
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver
from bth_create.task_dag import TaskDAGBuilder


class GenerationEngineTests(unittest.TestCase):
    def test_generates_typed_artifacts_and_validates_resources(self):
        values = RuleEngine().evaluate(FormStore().get("website_standard.v1"), {
            "project_name": "Hermes Site", "blueprint_id": "website.landing.v1",
            "tabs": ["หน้าหลัก", "ติดต่อ"], "color_tone": "blue",
            "network_scope": "internet", "auth_enabled": True,
            "density": "comfortable", "language": ["th", "en"],
        }).values
        values["modules"] = ["site_shell", "navigation_tabs", "hero", "feature_sections", "testimonials", "contact_form"]
        spec = ProjectSpecGenerator().from_website_form(values)
        resolved = ProjectSpecResolver().resolve(spec)
        with tempfile.TemporaryDirectory() as directory:
            frozen = FreezeStore(Path(directory) / "specs").freeze(resolved, "site")
            report = GapAnalyzer().analyze(frozen)
            build, generation = WebsiteGenerationEngine().generate(frozen, report, TaskDAGBuilder().build(report), Path(directory) / "builds")
            self.assertEqual(generation.status, "generated")
            self.assertTrue(generation.node_ids)
            self.assertIn("index.html", generation.page_paths)
            self.assertTrue(any(item.kind == "css" for item in generation.artifacts))
            self.assertTrue(generation.checked_references)
            self.assertTrue((Path(build.workspace) / "index.html").is_file())
            source = (Path(build.workspace) / "index.html").read_text(encoding="utf-8")
            ids = re.findall(r'data-node-id="(node-[0-9a-f]{16})"', source)
            self.assertGreaterEqual(len(ids), 4)
            self.assertEqual(len(ids), len(set(ids)))

    def test_generation_report_schema_artifact_is_valid(self):
        path = Path(__file__).parents[1] / "bth_create" / "schemas" / "hermes.generation-report.v1.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["$id"], "hermes.generation-report/v1")


if __name__ == "__main__":
    unittest.main()
