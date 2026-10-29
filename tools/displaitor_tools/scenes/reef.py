"""A quiet tidepool: a sea slug and a friendly moray share a bubble garden."""

from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw

from ..companions import marine

PERIOD = 16.0


@lru_cache(maxsize=1)
def background() -> Image.Image:
    image = Image.new('RGB', (64, 32), '#122C3B')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 12, 63, 24), fill='#183B48')
    draw.polygon(((0, 28), (10, 26), (22, 28), (33, 25), (44, 27),
                  (54, 25), (63, 27), (63, 31), (0, 31)), fill='#56635C')
    draw.line(((0, 29), (14, 28), (25, 30), (37, 28), (47, 29), (63, 28)), fill='#718174')
    # Distant reef silhouettes stay dim, leaving the animals as the focal point.
    for x, y in ((4, 20), (27, 18), (59, 17)):
        draw.line(((x, 27), (x, y), (x - 2, y - 3)), fill='#28535A', width=2)
        draw.line(((x, y + 3), (x + 3, y), (x + 3, y - 2)), fill='#28535A')
    for index in range(18):
        draw.point((index * 17 % 64, 28 + index % 4), fill='#869080' if index % 3 == 0 else '#3E5758')
    cave = marine.rock()
    image.paste(cave, (29, 4), cave)
    # A tiny resting starfish at the lower left.
    draw.line(((1, 30), (3, 29), (5, 30)), fill='#AF796D')
    draw.line((3, 28, 3, 31), fill='#AF796D')
    return image


def render(elapsed: float) -> Image.Image:
    image = background().copy()
    draw = ImageDraw.Draw(image)
    # Slow caustics live high in the water, never flashing across the animals.
    shift = round(math.sin(elapsed * math.tau / PERIOD) * 3)
    for x, y in ((9, 4), (29, 7), (46, 3)):
        draw.line(((x + shift, y), (x + shift + 4, y + 1), (x + shift + 9, y)), fill='#28505C')
    for index, x in enumerate((1, 6, 61)):
        lean = round(math.sin(elapsed * math.tau / 8 + index) * 2)
        draw.line(((x, 28), (x - 1, 23), (x + lean, 18 - index)), fill='#467E71')
        draw.point((x + lean, 18 - index), fill='#79A283')
    # A shared quiet moment: the eel blows a bubble while the slug has a snack.
    action = (elapsed - 4) / marine.ACTION_SECONDS if 4 <= elapsed < 6.4 else None
    eel = marine.moray(elapsed, action=action)
    slug = marine.nudibranch(elapsed, action=action)
    image.paste(eel, (29, 4), eel)
    image.paste(slug, (0, 4), slug)
    for index in range(3):
        age = (elapsed / 8 + index / 3) % 1
        x = 35 + index * 6 + round(math.sin(age * math.tau))
        y = 25 - round(age * 26)
        if y < 9:  # Floating particles do not obscure the faces.
            draw.ellipse((x, y, x + 2, y + 2), outline='#5C8A95')
    return image
