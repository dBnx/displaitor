"""Shared host-side drawing and layout types (Python 3.12+)."""

from __future__ import annotations
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

type Pathish = str | Path
type Point = tuple[float, float]
type Bounds = tuple[float, float, float, float]
type Points = Sequence[Point]
type Color = str | int | tuple[int, int, int]


class TextSlot(TypedDict, total=False):
    x: int
    y: int
    width: int
    height: int
    font: str
    color: str
    background: str | None
    align: str
    text: str


class Scene(TypedDict):
    text: dict[str, TextSlot]
