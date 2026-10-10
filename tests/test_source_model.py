"""Tests for the Phase 1 shared source model boundary."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.source_model import (
    HermesPatch,
    HermesResponse,
    PageModel,
    ProjectSourceModel,
    ProjectStore,
    SourceNode,
    ThemeModel,
    stable_node_id,
)


def source_model() -> ProjectSourceModel:
    return ProjectSourceModel(
        schema="hermes.source-model/v1",
        project_id="demo",
        name="Demo",
        pages=[PageModel(
            id="home",
            path="index.html",
            title="Home",
            root=SourceNode(
                id=stable_node_id("demo", "home", "page/root"),
                kind="section",
                tag="main",
                path="page/root",
            ),
        )],
        theme=ThemeModel(id="website-standard", tokens={"accent": "#2563eb"}),
    )


class SourceModelTests(unittest.TestCase):
    def test_node_ids_are_stable_and_content_independent(self):
        self.assertEqual(stable_node_id("demo", "home", "page/root"), stable_node_id("demo", "home", "page/root"))
        self.assertNotEqual(stable_node_id("demo", "home", "page/root"), stable_node_id("demo", "home", "section/1"))

    def test_duplicate_node_ids_are_rejected(self):
        model = source_model()
        duplicate = model.pages[0].root.model_copy(update={"path": "another"})
        with self.assertRaises(ValidationError):
            ProjectSourceModel(
                schema="hermes.source-model/v1",
                project_id="demo",
                name="Demo",
                pages=[PageModel(id="home", path="index.html", title="Home", root=SourceNode(
                    id=model.pages[0].root.id, kind="element", tag="div", path="root", children=[duplicate]
                ))],
                theme=ThemeModel(id="theme"),
            )

    def test_store_writes_current_and_append_only_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            first = store.save(source_model())
            second = store.save(first.model_copy(update={"name": "Updated"}), expected_revision=first.revision)
            self.assertEqual(store.list_versions(), [1, 2])
            self.assertEqual(store.load().name, "Updated")
            self.assertEqual(store.load_version(1).name, "Demo")
            with self.assertRaises(ValueError):
                store.save(second, expected_revision=1)

    def test_proposal_requires_structured_approved_patch(self):
        patch = HermesPatch(patch_id="p1", base_revision=1, summary="Change heading", operations=[{
            "op": "set_text", "target_node_id": stable_node_id("demo", "home", "page/root"), "value": "ใหม่"
        }])
        response = HermesResponse(schema="hermes.edit-contract/v1", kind="proposal", message="ตรวจ diff ก่อนใช้", patch=patch)
        self.assertTrue(response.requires_approval)
        with self.assertRaises(ValidationError):
            HermesResponse(schema="hermes.edit-contract/v1", kind="proposal", message="bad", requires_approval=False, patch=patch)


if __name__ == "__main__":
    unittest.main()
