"""Deterministic Theme Store for BTH Create."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ThemeIdentifier = Annotated[str, Field(min_length=1, max_length=120)]
TokenMap = dict[str, str]


class ThemeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ComponentRecipe(ThemeModel):
    component: ThemeIdentifier
    base: TokenMap = Field(min_length=1)
    states: dict[str, TokenMap] = Field(default_factory=dict)

    @field_validator("states")
    @classmethod
    def states_must_not_be_empty(cls, values: dict[str, TokenMap]) -> dict[str, TokenMap]:
        if any(not state.strip() for state in values):
            raise ValueError("recipe state names must contain visible text")
        return values


class WindowsXPTheme(ThemeModel):
    id: ThemeIdentifier
    version: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    typography: TokenMap = Field(min_length=1)
    colors: TokenMap = Field(min_length=1)
    borders: TokenMap = Field(min_length=1)
    window_chrome: TokenMap = Field(min_length=1)
    title_bars: TokenMap = Field(min_length=1)
    buttons: TokenMap = Field(min_length=1)
    inputs: TokenMap = Field(min_length=1)
    menus: TokenMap = Field(min_length=1)
    taskbar: TokenMap = Field(min_length=1)
    spacing: TokenMap = Field(min_length=1)
    icons: TokenMap = Field(min_length=1)
    hover_states: TokenMap = Field(min_length=1)
    active_states: TokenMap = Field(min_length=1)
    disabled_states: TokenMap = Field(min_length=1)
    panel_styles: TokenMap = Field(min_length=1)
    dialog_styles: TokenMap = Field(min_length=1)
    component_recipes: dict[str, ComponentRecipe] = Field(min_length=1)

    @field_validator("component_recipes")
    @classmethod
    def recipe_names_must_be_nonempty(cls, values: dict[str, ComponentRecipe]) -> dict[str, ComponentRecipe]:
        if any(not name.strip() for name in values):
            raise ValueError("component recipe names must contain visible text")
        return values

    @model_validator(mode="after")
    def validate_required_recipes(self) -> "WindowsXPTheme":
        required = {
            "window", "button", "checkbox", "radio", "select", "input",
            "panel", "dialog", "toolbar", "statusbar", "taskbar", "table", "card",
        }
        missing = required - set(self.component_recipes)
        if missing:
            raise ValueError(f"theme is missing component recipes: {sorted(missing)}")
        return self


Theme = WindowsXPTheme


def validate_theme(value: Theme | dict) -> Theme:
    """Validate and return an immutable Theme model."""

    if isinstance(value, Theme):
        return value
    return Theme.model_validate(value)


class ThemeStore:
    """Read-only filesystem-backed store for versioned theme JSON files."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent / "themes"

    def list(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))

    def get(self, theme_id: str) -> Theme:
        path = self.root / f"{theme_id}.json"
        if path.parent != self.root or not path.is_file():
            raise KeyError(f"theme not found: {theme_id}")
        return validate_theme(json.loads(path.read_text(encoding="utf-8")))

