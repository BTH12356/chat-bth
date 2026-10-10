"""End-to-end tests for the five standard website Blueprints."""

import tempfile
import unittest
from pathlib import Path

from bth_create.blueprint import BlueprintStore
from bth_create.build_engine import BuildEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver
from bth_create.task_dag import TaskDAGBuilder
from bth_create.verification import VerificationPipeline


WEBSITE_BLUEPRINTS = [
    "website.landing.v1",
    "website.company.v1",
    "website.portfolio.v1",
    "website.catalog.v1",
    "website.content.v1",
]


class WebsiteBlueprintTests(unittest.TestCase):
    def test_all_five_blueprints_build_and_verify(self):
        blueprints = BlueprintStore()
        generator = ProjectSpecGenerator()
        resolver = ProjectSpecResolver()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, blueprint_id in enumerate(WEBSITE_BLUEPRINTS, start=1):
                with self.subTest(blueprint=blueprint_id):
                    blueprint = blueprints.get(blueprint_id)
                    spec = generator.from_website_form({
                        "project_name": blueprint.name,
                        "blueprint_id": blueprint_id,
                        "modules": blueprint.supported_modules,
                        "tabs": ["หน้าหลัก", "ผลงาน", "ติดต่อ"],
                        "color_tone": "purple",
                        "network_scope": "internet",
                        "auth_enabled": True,
                        "density": "comfortable",
                        "language": ["th", "en"],
                    })
                    resolved = resolver.resolve(spec)
                    frozen = FreezeStore(root / "specs").freeze(resolved, f"website-project-{index}")
                    gaps = GapAnalyzer().analyze(frozen)
                    self.assertEqual(gaps.status, "ready")
                    build = BuildEngine().build(frozen, gaps, TaskDAGBuilder().build(gaps), root / "builds")
                    verification = VerificationPipeline().verify(frozen, build)
                    self.assertEqual(verification.status, "passed")
                    source = (Path(build.workspace) / "index.html").read_text(encoding="utf-8")
                    styles = (Path(build.workspace) / "styles.css").read_text(encoding="utf-8")
                    self.assertIn("หน้าหลัก", source)
                    self.assertIn("ติดต่อ", source)
                    self.assertIn("#7c3aed", styles)

    def test_tab_names_must_be_unique_and_limited(self):
        blueprint = BlueprintStore().get("website.landing.v1")
        base = {
            "project_name": "Website",
            "blueprint_id": blueprint.id,
            "modules": blueprint.supported_modules,
            "color_tone": "blue",
            "network_scope": "internet",
            "auth_enabled": True,
        }
        with self.assertRaises(ValueError):
            ProjectSpecGenerator().from_website_form({**base, "tabs": ["Home", "home"]})
        with self.assertRaises(ValueError):
            ProjectSpecGenerator().from_website_form({**base, "tabs": [f"Tab {index}" for index in range(13)]})


if __name__ == "__main__":
    unittest.main()
