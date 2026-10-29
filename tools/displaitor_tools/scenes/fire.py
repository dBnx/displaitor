"""Flowing fire against full-bleed stone, without a frame or surrounding objects."""

from __future__ import annotations

from functools import lru_cache
import math
import random
from typing import cast

from PIL import Image, ImageDraw

PERIOD = 16.0
_WIDTH = 64
_TILE_HEIGHT = 320


@lru_cache(maxsize=1)
def background() -> Image.Image:
    image = Image.new('RGB', (64, 32), '#55554E')
    draw = ImageDraw.Draw(image)
    rng = random.Random(72)
    # Irregular, full-bleed stonework: no border, opening, mantel or hearth.
    for row in range(5):
        y = row * 8 - 3
        x = -7 if row % 2 else -2
        while x < 64:
            width = rng.randrange(11, 19)
            shade = rng.randrange(102, 132)
            draw.polygon(((x + 1, y + 1), (x + width - 2, y), (x + width, y + 3),
                          (x + width - 1, y + 7), (x + 2, y + 7), (x, y + 5)),
                         fill=(shade, shade, shade - 10))
            x += width + 1
    # Fine grain belongs to the stone itself and stays fixed.
    pixels = image.load()
    assert pixels is not None
    for y in range(32):
        for x in range(64):
            red, green, blue = cast(tuple[int, int, int], image.getpixel((x, y)))
            grain = rng.randrange(-4, 5)
            pixels[x, y] = (red + grain, green + grain, blue + grain)
    return image


def _noise(columns: int, rows: int, seed: int) -> bytes:
    """Smooth tileable turbulence, prepared once using Pillow's native resampler."""
    rng = random.Random(seed)
    cell = Image.new('L', (columns, rows))
    cell.putdata([rng.randrange(256) for _ in range(columns * rows)])
    tiled = Image.new('L', (columns * 3, rows * 3))
    for y in range(3):
        for x in range(3):
            tiled.paste(cell, (x * columns, y * rows))
    smooth = tiled.resize((_WIDTH * 3, _TILE_HEIGHT * 3), Image.Resampling.BICUBIC)
    return smooth.crop((_WIDTH, _TILE_HEIGHT, _WIDTH * 2, _TILE_HEIGHT * 2)).tobytes()


@lru_cache(maxsize=1)
def _turbulence() -> tuple[bytes, bytes]:
    return _noise(10, 20, 29), _noise(23, 64, 137)


@lru_cache(maxsize=1)
def _palette() -> tuple[tuple[int, int, int], ...]:
    stops = ((0, (99, 30, 8)), (50, (202, 62, 8)), (105, (244, 128, 14)),
             (165, (255, 195, 55)), (220, (255, 235, 153)), (255, (255, 252, 218)))
    result: list[tuple[int, int, int]] = []
    for value in range(256):
        for (start, a), (end, b) in zip(stops, stops[1:]):
            if value <= end:
                ratio = (value - start) / (end - start)
                result.append((round(a[0] + (b[0] - a[0]) * ratio),
                               round(a[1] + (b[1] - a[1]) * ratio),
                               round(a[2] + (b[2] - a[2]) * ratio)))
                break
    return tuple(result)


@lru_cache(maxsize=1)
def _heat_curves() -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    # Spatial edge falloff and both turbulence contributions are invariant.
    return (tuple((abs(x - 31.5) / 31.5) ** 4 * .48 for x in range(_WIDTH)),
            tuple((value / 255 - .5) * 1.05 for value in range(256)),
            tuple((value / 255 - .5) * .22 for value in range(256)))


def render(elapsed: float) -> Image.Image:
    image = background().copy()
    stone = image.tobytes()
    broad, fine = _turbulence()
    palette = _palette()
    edges, large_heat, small_heat = _heat_curves()
    # Both noise fields advect upwards. Their different scales/speeds break up
    # the flame front into curling, merging tongues rather than fixed triangles.
    offset = round(elapsed * 20) % _TILE_HEIGHT
    phase = elapsed * math.tau / PERIOD
    result = bytearray(stone)
    for y in range(32):
        altitude = (31 - y) / 31
        sway = round(math.sin(phase * 4 - altitude * 5) * altitude * 4)
        base_heat = .88 - altitude * 1.00
        row_a = (y + offset) % _TILE_HEIGHT * _WIDTH
        row_b = (y + offset * 2) % _TILE_HEIGHT * _WIDTH
        for x in range(_WIDTH):
            large = large_heat[broad[row_a + (x + sway) % _WIDTH]]
            small = small_heat[fine[row_b + x]]
            heat = base_heat + large + small - edges[x]
            if heat <= .18:
                continue
            color = palette[min(255, max(0, round((heat - .18) * 310)))]
            alpha = min(1.0, (heat - .18) * 10)
            index = (y * _WIDTH + x) * 3
            if alpha == 1:
                result[index], result[index + 1], result[index + 2] = color
            else:
                for channel in range(3):
                    result[index + channel] = round(stone[index + channel] * (1 - alpha) + color[channel] * alpha)
    return Image.frombytes('RGB', (64, 32), bytes(result))
