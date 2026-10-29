"""Read-only package resources and explicit source-checkout development paths."""

from __future__ import annotations
from importlib.resources import files
from pathlib import Path

# Wheel installs are unpacked by pip. Traversables also support zip resources.
RESOURCES = files("displaitor_tools").joinpath("resources")
ART = RESOURCES / "art"
LAYOUTS = RESOURCES / "layouts"
# Retained for checkout tests; live apps never derive their resources from ROOT.
ROOT = Path(__file__).resolve().parents[2]


def checkout_root() -> Path:
    if not (ROOT / "Cargo.toml").is_file() or not (ROOT / "displaitor").is_dir():
        raise RuntimeError("This development command needs a Displaitor source checkout and native simulator build.")
    return ROOT
