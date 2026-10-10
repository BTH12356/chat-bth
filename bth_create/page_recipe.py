"""Structured page recipes used by the deterministic website composer."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PageRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=300)
    blocks: list[str] = Field(min_length=1, max_length=20)

    @field_validator("blocks")
    @classmethod
    def blocks_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("page recipe blocks must be unique")
        return values


class PageRecipeStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent / "page_recipes"

    def list(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))

    def get(self, recipe_id: str) -> PageRecipe:
        path = self.root / f"{recipe_id}.json"
        if path.parent != self.root or not path.is_file():
            raise KeyError(f"page recipe not found: {recipe_id}")
        return PageRecipe.model_validate(json.loads(path.read_text(encoding="utf-8")))
