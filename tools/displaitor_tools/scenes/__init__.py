"""Deterministic full-panel scenes; no transport, telemetry or network access."""

from __future__ import annotations

import math
from functools import partial
from collections.abc import Callable
from PIL import Image

from . import farm, fire, hunter, okami, reef, winter, witcher
from .actions import layer as action_layer

_RENDERERS: dict[str, Callable[[float], Image.Image]] = {
    'palico': partial(hunter.render, 'palico'), 'rathalos': partial(hunter.render, 'rathalos'),
    'zinogre': partial(hunter.render, 'zinogre'), 'poogie': partial(hunter.render, 'poogie'),
    'farm': farm.render, 'winter': winter.render, 'okami': okami.render, 'witcher': witcher.render, 'reef': reef.render, 'fire': fire.render,
}
NAMES = ('farm', 'winter', 'okami', 'witcher', 'reef', 'fire', 'palico', 'rathalos', 'zinogre', 'poogie')
BUILTIN_NAMES = NAMES
PERIODS = {'palico': hunter.PERIOD, 'rathalos': hunter.PERIOD, 'zinogre': hunter.PERIOD, 'poogie': hunter.PERIOD, 'farm': farm.PERIOD, 'winter': winter.PERIOD, 'okami': okami.PERIOD, 'witcher': witcher.PERIOD, 'reef': reef.PERIOD, 'fire': fire.PERIOD}
LABELS = {'palico': 'PALICO - CAMP KITCHEN', 'rathalos': 'RATHALOS - SLEEPY CLEARING',
          'zinogre': 'ZINOGRE - THUNDERBUG GROVE', 'poogie': 'POOGIE - VILLAGE STROLL', 'farm': 'FARM AT DUSK', 'winter': 'SNOWY FOREST WALK',
          'okami': 'OKAMI - BLOSSOM SHRINE', 'witcher': 'WITCHER 3 - VALLEY CAMP', 'reef': 'TINY TIDEPOOL FRIENDS', 'fire': 'FIREPLACE - STONE HEARTH'}


def render(name: str, elapsed: float, *, action: float | None = None) -> Image.Image:
    """Render native 64x32 pixels at a nonnegative scene time in seconds."""
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('Scene time must be finite and nonnegative')
    if name not in NAMES:
        raise ValueError('Unknown cozy scene')
    image = _RENDERERS[name](elapsed % PERIODS[name])
    if action is not None:
        overlay = action_layer(name, action)
        image.paste(overlay, (0, 0), overlay.getchannel('A'))
    return image
