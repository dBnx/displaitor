"""A quiet snowy forest walk, inspired by Red Rescue Team's winter journey."""

from __future__ import annotations

from functools import lru_cache
import math
from PIL import Image, ImageDraw

from ..companions.pokemon import walking_frames

PERIOD = 32.0


def pine(draw: ImageDraw.ImageDraw, x: int, y: int, height: int, *, distant: bool = False) -> None:
    width = height // 3
    branches = '#2C4252' if distant else '#304C53'
    snow = '#536D7D' if distant else '#9EAFAE'
    shade = '#3F596B' if distant else '#6F8B98'
    draw.rectangle((x, y + height - 4, x + 1, y + height), fill='#35434C')
    for top, bottom, radius in ((0, height // 2, max(2, width - 2)),
                                (height // 4, height * 3 // 4, max(3, width - 1)),
                                (height // 2, height - 2, width)):
        draw.polygon(((x, y + top), (x - radius, y + bottom),
                      (x + radius, y + bottom)), fill=branches)
        draw.line((x, y + top, x - radius + 1, y + bottom - 1), fill=snow)
        draw.line((x - radius + 1, y + bottom - 1, x + radius - 1, y + bottom - 1), fill=shade)
        draw.line((x - radius + 2, y + bottom - 2, x, y + bottom - 2), fill=snow)


@lru_cache(maxsize=2)
def trees(distant: bool) -> Image.Image:
    width = 32 if distant else 64
    image = Image.new('RGBA', (width, 32))
    draw = ImageDraw.Draw(image)
    shapes = ((3, 10, 11), (15, 8, 13), (27, 11, 10)) if distant else (
        (4, 4, 19), (22, 3, 20), (46, 2, 21), (61, 7, 16))
    # Repeat across both tile edges so parallax never exposes a cut-off trunk.
    for shift in (-width, 0, width):
        for x, y, height in shapes:
            pine(draw, x + shift, y, height, distant=distant)
    return image


def tile(image: Image.Image, layer: Image.Image, offset: int) -> None:
    start = -(offset % layer.width)
    for x in range(start, image.width, layer.width):
        image.paste(layer, (x, 0), layer)


@lru_cache(maxsize=1)
def sky() -> Image.Image:
    image = Image.new('RGB', (64, 32), '#202F48')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 8, 63, 16), fill='#344A60')
    draw.rectangle((0, 17, 63, 31), fill='#485F71')
    draw.ellipse((52, 2, 56, 6), fill='#A1AFB0')
    draw.ellipse((50, 1, 54, 5), fill='#202F48')
    for point in ((11, 2), (30, 5), (40, 1), (61, 9)):
        draw.point(point, fill='#7C8F9C')
    return image


def render(elapsed: float) -> Image.Image:
    image = sky().copy()
    tile(image, trees(True), math.floor(elapsed))
    tile(image, trees(False), math.floor(elapsed * 2))
    draw = ImageDraw.Draw(image)
    # Snowbanks flank a clear, slightly darker trail. Only the texture scrolls.
    draw.rectangle((0, 23, 63, 31), fill='#809499')
    draw.line((0, 23, 63, 23), fill='#A4B2AF')
    draw.rectangle((0, 26, 63, 29), fill='#687F8B')
    draw.line((0, 30, 63, 30), fill='#9CABA8')
    for seed in (1, 13, 27, 44, 58):
        x = (seed - math.floor(elapsed * 4)) % 64
        draw.line((x, 24, x + 2, 24), fill='#AFBAB4')
    for index in range(10):
        x = (index * 7 - math.floor(elapsed * 4)) % 64
        if x < 17:
            draw.point((x, 27 + index % 2), fill='#4B6478')
    # Far flakes sit behind the walkers; their drift is periodic and seeded.
    for index in range(12):
        x = (index * 19 + round(math.sin(elapsed * math.tau / 8 + index) * 2)) % 64
        y = (index * 11 + math.floor(elapsed)) % 32
        draw.point((x, y), fill='#7E949F')
    # Two companions keep their spacing, with native walk poses and planted feet.
    for name, center, phase in (('eevee', 25, .25), ('torchic', 43, 0.0)):
        frames = walking_frames(name)
        actor = frames[int((elapsed + phase) % 1 * len(frames))]
        draw.ellipse((center - 4, 28, center + 4, 29), fill='#506978')
        image.paste(actor, (center - actor.width // 2, 28 - actor.height), actor)
    # A tiny lantern lends warmth to the cold path without a screen-wide glow.
    draw.line((47, 21, 49, 21), fill='#73604E')
    draw.rectangle((48, 22, 50, 24), fill='#645644')
    draw.point((49, 23), fill='#D4AE72')
    draw.line((48, 28, 51, 28), fill='#8A8C79')
    # Faster foreground flakes and low bushes give the camera a little depth.
    for index in range(7):
        x = (index * 23 + 7 + round(math.sin(elapsed * math.tau / 8 + index) * 2)) % 64
        y = (index * 13 + math.floor(elapsed * 2)) % 32
        draw.point((x, y), fill='#B3C0BA')
        if index == 2:
            draw.line((x - 1, y, x + 1, y), fill='#96AEB0')
            draw.line((x, y - 1, x, y + 1), fill='#96AEB0')
    for seed in (7, 39):
        x = (seed - math.floor(elapsed * 4)) % 64
        draw.line((x - 2, 31, x + 2, 31), fill='#415C62')
        draw.line((x - 1, 30, x + 1, 30), fill='#B1BBB4')
    return image
