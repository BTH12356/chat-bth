"""Tests for structured website Page Recipes and multi-page composition."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.blueprint import BlueprintStore
from bth_create.build_engine import BuildEngine
from bth_create.gap_analysis import GapAnalyzer
from bth_create.page_recipe import PageRecipe, PageRecipeStore
from bth_create.spec_lifecycle import FreezeStore, ProjectSpecGenerator, ProjectSpecResolver
from bth_create.task_dag import TaskDAGBuilder
from bth_create.verification import VerificationPipeline


BUSINESS_BLUEPRINTS = [
    "website.corporate.v1",
    "website.organization.v1",
    "website.retail.v1",
    "website.services.v1",
    "website.knowledge.v1",
]


class PageRecipeTests(unittest.TestCase):
    def test_recipe_store_contains_popular_page_types(self):
        store = PageRecipeStore()
        expected = {"home", "about", "policy", "document_library", "knowledge_library", "product_catalog", "service", "news", "contact", "standard"}
        self.assertEqual(set(store.list()), expected)
        self.assertIn("policy_article", store.get("policy").blocks)
        self.assertIn("knowledge_shelf", store.get("knowledge_library").blocks)
        with self.assertRaises(ValidationError):
            PageRecipe.model_validate({"id": "bad", "version": "1.0.0", "label": "Bad", "description": "Bad", "blocks": ["same", "same"]})

    def test_all_business_blueprints_build_distinct_linked_pages(self):
        blueprints = BlueprintStore()
        generator = ProjectSpecGenerator()
        resolver = ProjectSpecResolver()
        names = ["หน้าหลัก", "เกี่ยวกับ", "นโยบาย", "กฎระเบียบ", "คลังความรู้", "สินค้า", "บริการ", "ข่าวสาร", "ติดต่อ"]
        page_types = ["home", "about", "policy", "document_library", "knowledge_library", "product_catalog", "service", "news", "contact"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, blueprint_id in enumerate(BUSINESS_BLUEPRINTS, start=1):
                with self.subTest(blueprint=blueprint_id):
                    blueprint = blueprints.get(blueprint_id)
                    spec = generator.from_website_form({
                        "project_name": blueprint.name,
                        "blueprint_id": blueprint_id,
                        "modules": blueprint.supported_modules,
                        "tabs": names,
                        "page_types": page_types,
                        "color_tone": "blue",
                        "network_scope": "internet",
                        "auth_enabled": True,
                    })
                    frozen = FreezeStore(root / "specs").freeze(resolver.resolve(spec), f"business-site-{index}")
                    self.assertEqual(frozen.page_recipe_versions["policy"], "1.0.0")
                    gaps = GapAnalyzer().analyze(frozen)
                    self.assertEqual(gaps.status, "ready")
                    self.assertIn("website.pages", {item.requirement_id for item in gaps.compose})
                    build = BuildEngine().build(frozen, gaps, TaskDAGBuilder().build(gaps), root / "builds")
                    report = VerificationPipeline().verify(frozen, build)
                    self.assertEqual(report.status, "passed", report.model_dump())
                    workspace = Path(build.workspace)
                    expected_files = {"index.html", "about.html", "policy.html", "documents.html", "knowledge.html", "products.html", "services.html", "news.html", "contact.html"}
                    self.assertTrue(expected_files <= {path.name for path in workspace.glob("*.html")})
                    policy = (workspace / "policy.html").read_text(encoding="utf-8")
                    documents = (workspace / "documents.html").read_text(encoding="utf-8")
                    knowledge = (workspace / "knowledge.html").read_text(encoding="utf-8")
                    self.assertIn("page-image-input", policy)
                    self.assertIn("data-page-search", documents)
                    self.assertIn("accept=\"application/pdf,.pdf\"", documents)
                    self.assertIn("knowledge_shelf", PageRecipeStore().get("knowledge_library").blocks)
                    self.assertIn('href="contact.html"', knowledge)

    def test_page_type_count_must_match_page_names(self):
        with self.assertRaises(ValueError):
            ProjectSpecGenerator().from_website_form({
                "project_name": "Mismatch",
                "blueprint_id": "website.corporate.v1",
                "modules": ["site_shell", "navigation_tabs", "page_composer"],
                "tabs": ["หน้าแรก", "เกี่ยวกับ"],
                "page_types": ["home"],
                "auth_enabled": True,
            })


if __name__ == "__main__":
    unittest.main()
