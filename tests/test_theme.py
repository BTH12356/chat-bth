"""Tests for the deterministic BTH Theme Store boundary."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bth_create.theme import ThemeStore, validate_theme


class ThemeTests(unittest.TestCase):
    def test_windows_xp_theme_is_loadable(self):
        store = ThemeStore()
        theme = store.get("windows_xp.v1")
        self.assertIn("windows_xp.v1", store.list())
        self.assertEqual(theme.name, "Windows XP")
        self.assertEqual(theme.typography["font_family"], "Tahoma, sans-serif")
        self.assertIn("window", theme.component_recipes)
        self.assertIn("disabled", theme.component_recipes["button"].states)

    def test_theme_is_immutable_and_rejects_unknown_fields(self):
        theme = ThemeStore().get("windows_xp.v1")
        with self.assertRaises(ValidationError):
            validate_theme({**theme.model_dump(), "prompt": "invent a style"})
        with self.assertRaises((TypeError, ValidationError)):
            theme.name = "changed"

    def test_all_required_component_recipes_are_present(self):
        base = ThemeStore().get("windows_xp.v1").model_dump()
        del base["component_recipes"]["dialog"]
        with self.assertRaises(ValidationError):
            validate_theme(base)

    def test_recipe_state_names_must_be_nonempty(self):
        base = ThemeStore().get("windows_xp.v1").model_dump()
        base["component_recipes"]["button"]["states"] = {" ": {"style": "hover_states"}}
        with self.assertRaises(ValidationError):
            validate_theme(base)

    def test_store_missing_theme_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyError):
                ThemeStore(Path(directory)).get("unknown.v1")


if __name__ == "__main__":
    unittest.main()
