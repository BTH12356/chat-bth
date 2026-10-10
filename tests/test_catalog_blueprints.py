"""End-to-end tests for the reusable catalog and library Blueprints."""

import tempfile
import unittest
from pathlib import Path

from bth_create.blueprint import BlueprintStore
from bth_create.build_engine import BuildEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver
from bth_create.task_dag import TaskDAGBuilder
from bth_create.verification import VerificationPipeline


CATALOG_BLUEPRINTS = [
    "catalog.library.v1",
    "catalog.documents.v1",
    "catalog.products.v1",
    "catalog.media.v1",
    "catalog.learning.v1",
]


class CatalogBlueprintTests(unittest.TestCase):
    def test_all_five_catalog_blueprints_build_and_verify(self):
        blueprints = BlueprintStore()
        generator = ProjectSpecGenerator()
        resolver = ProjectSpecResolver()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, blueprint_id in enumerate(CATALOG_BLUEPRINTS, start=1):
                with self.subTest(blueprint=blueprint_id):
                    blueprint = blueprints.get(blueprint_id)
                    spec = generator.from_website_form({
                        "project_name": blueprint.name,
                        "blueprint_id": blueprint_id,
                        "modules": blueprint.supported_modules,
                        "tabs": ["ทั้งหมด", "ธุรกิจ", "เทคโนโลยี"],
                        "color_tone": "orange",
                        "network_scope": "internet",
                        "auth_enabled": True,
                        "density": "comfortable",
                        "language": ["th", "en"],
                    })
                    resolved = resolver.resolve(spec)
                    frozen = FreezeStore(root / "specs").freeze(resolved, f"catalog-project-{index}")
                    gaps = GapAnalyzer().analyze(frozen)
                    self.assertEqual(gaps.status, "ready")
                    self.assertEqual(gaps.missing, [])
                    self.assertIn("catalog.navigation", {item.requirement_id for item in gaps.compose})
                    build = BuildEngine().build(frozen, gaps, TaskDAGBuilder().build(gaps), root / "builds")
                    verification = VerificationPipeline().verify(frozen, build)
                    self.assertEqual(verification.status, "passed")
                    workspace = Path(build.workspace)
                    source = (workspace / "index.html").read_text(encoding="utf-8")
                    styles = (workspace / "styles.css").read_text(encoding="utf-8")
                    script = (workspace / "app.js").read_text(encoding="utf-8")
                    self.assertIn('id="catalog-search"', source)
                    self.assertIn('id="catalog-sort"', source)
                    self.assertIn('accept="application/pdf,.pdf"', source)
                    self.assertIn('accept="image/*"', source)
                    self.assertIn('id="item-detail-dialog"', source)
                    self.assertIn("ธุรกิจ", source)
                    self.assertIn("#ea580c", styles)
                    self.assertIn("indexedDB", script)

    def test_catalog_components_are_reused_not_generated(self):
        blueprint = BlueprintStore().get("catalog.library.v1")
        spec = ProjectSpecGenerator().from_website_form({
            "project_name": "ห้องสมุดดิจิทัล",
            "blueprint_id": blueprint.id,
            "modules": blueprint.supported_modules,
            "tabs": ["หนังสือทั้งหมด", "วรรณกรรม"],
            "color_tone": "blue",
            "auth_enabled": True,
        })
        with tempfile.TemporaryDirectory() as directory:
            frozen = FreezeStore(Path(directory) / "specs").freeze(ProjectSpecResolver().resolve(spec), "library")
            report = GapAnalyzer().analyze(frozen)
        self.assertEqual(report.missing, [])
        reused = {item.component_id for item in report.reuse}
        self.assertIn("pdf_attachment", reused)
        self.assertIn("cover_selector", reused)
        self.assertIn("catalog_search_generic", reused)


if __name__ == "__main__":
    unittest.main()
