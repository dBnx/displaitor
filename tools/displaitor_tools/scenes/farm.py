"""A small, original farm at dusk, inspired by Stardew Valley's warm evenings."""

from __future__ import annotations

from functools import lru_cache
import math
from PIL import Image, ImageDraw

PERIOD = 16.0


@lru_cache(maxsize=1)
def background() -> Image.Image:
    image = Image.new('RGB', (64, 32))
    draw = ImageDraw.Draw(image)
    # Narrow dusk bands leave the amber windows as the scene's warmest light.
    for start, end, color in ((0, 5, '#172032'), (6, 9, '#2B2D42'),
                              (10, 12, '#514252'), (13, 15, '#745359')):
        draw.rectangle((0, start, 63, end), fill=color)
    draw.ellipse((52, 2, 57, 7), fill='#B7A58A')
    draw.ellipse((50, 1, 55, 6), fill='#172032')
    draw.polygon(((0, 14), (5, 11), (12, 14), (18, 12), (24, 15),
                  (32, 12), (40, 13), (47, 10), (55, 12), (63, 11), (63, 19), (0, 19)), fill='#2C4143')
    draw.polygon(((0, 17), (9, 15), (19, 18), (28, 15), (39, 17),
                  (50, 14), (63, 16), (63, 31), (0, 31)), fill='#384A38')
    draw.rectangle((0, 22, 63, 31), fill='#3C4B34')
    # Cottage, chimney, timber walls and a broad shingled roof.
    draw.rectangle((8, 15, 24, 25), fill='#8B6B49')
    draw.rectangle((9, 17, 23, 24), fill='#74563D')
    for y in (18, 21, 24):
        draw.line((9, y, 23, y), fill='#5B4938')
    draw.rectangle((20, 9, 22, 15), fill='#6C6260')
    draw.line((19, 9, 23, 9), fill='#90817A')
    draw.polygon(((5, 16), (13, 9), (20, 10), (27, 16)), fill='#49373D')
    draw.polygon(((7, 14), (13, 9), (20, 10), (25, 14)), fill='#9C6150')
    draw.line((9, 13, 23, 13), fill='#784C43')
    draw.line((12, 11, 20, 11), fill='#B17A5B')
    draw.line((6, 16, 26, 16), fill='#332E31')
    draw.rectangle((19, 19, 22, 25), fill='#3E3430')
    draw.line((20, 19, 21, 19), fill='#BA8852')
    draw.point((21, 23), fill='#C69B60')
    draw.line((18, 26, 23, 26), fill='#9F8B65')
    # Winding path from the porch, leaving room for the little vegetable patch.
    draw.polygon(((19, 27), (23, 27), (26, 31), (16, 31)), fill='#7A6B4E')
    draw.line((18, 30, 20, 30), fill='#96805A')
    draw.point((23, 29), fill='#5B573E')
    draw.rectangle((29, 23, 40, 31), fill='#4A3930')
    for y in (25, 28, 31):
        draw.line((29, y, 40, y), fill='#6C4B37')
    # Pond with a grassy, irregular bank.
    draw.polygon(((46, 22), (56, 21), (63, 23), (63, 31), (43, 31), (42, 27)), fill='#68745A')
    draw.polygon(((47, 23), (56, 22), (63, 24), (63, 31), (45, 31), (44, 27)), fill='#274850')
    draw.line((49, 23, 56, 23), fill='#426667')
    draw.line((46, 30, 48, 30), fill='#52746B')
    # Fence and flowers give the far field scale without a moving background.
    draw.line((29, 19, 63, 19), fill='#8D7955')
    for x in (30, 38, 46, 54, 62):
        draw.line((x, 17, x, 21), fill='#A18D63')
        draw.point((x, 17), fill='#BAA377')
    for x, y in ((3, 28), (6, 30), (27, 22), (42, 22), (59, 20)):
        draw.point((x, y), fill='#927658')
        draw.point((x, y + 1), fill='#56704B')
    # Orchard tree at the left edge.
    draw.rectangle((2, 17, 3, 25), fill='#5D4B38')
    draw.polygon(((0, 13), (3, 10), (7, 12), (9, 17), (6, 21), (0, 20)), fill='#263C32')
    draw.polygon(((0, 13), (3, 11), (7, 13), (6, 16), (1, 16)), fill='#41593B')
    draw.line((1, 18, 5, 18), fill='#354C35')
    for x, y in ((2, 15), (6, 17)):
        draw.point((x, y), fill='#9F6250')
    return image


def render(elapsed: float) -> Image.Image:
    image = background().copy()
    draw = ImageDraw.Draw(image)
    # Window light changes by a few levels, never flashing across the panel.
    light = ('#C19A60', '#C8A266', '#CEAA70', '#C8A266')[int(elapsed * .5) % 4]
    draw.rectangle((11, 18, 16, 22), fill='#4D3E33')
    draw.rectangle((12, 19, 15, 21), fill=light)
    draw.line((14, 19, 14, 21), fill='#7C603E')
    draw.line((11, 23, 16, 23), fill='#A08356')
    draw.point((17, 25), fill='#77613E')
    # Three puffs rise and thin out as they drift from the chimney.
    for index in range(3):
        age = (elapsed / 8 + index / 3) % 1
        x = 21 + round(age * 6 + math.sin(age * math.tau) * .8)
        y = 8 - round(age * 8)
        color = '#716A70' if age < .35 else '#534D5A' if age < .7 else '#383A4C'
        if age < .72:
            draw.line((x, y, x + 1, y), fill=color)
            draw.point((x - 1, y - 1), fill=color)
        else:
            draw.point((x, y), fill=color)
    # Short pond ripples catch the last of the evening light.
    for index, (x, y) in enumerate(((49, 25), (56, 28), (48, 30))):
        phase = int(elapsed * 2 + index) % 8
        draw.line((x + phase // 3, y, x + phase // 3 + 2, y), fill='#557B7D')
        if phase in (2, 3, 4):
            draw.point((x + phase // 3 + 3, y), fill='#71908A')
    # Whole-pixel leaves sway, while their roots and soil stay fixed.
    for index, (x, y) in enumerate(((31, 24), (36, 24), (32, 28), (38, 28))):
        lean = round(math.sin(elapsed * math.tau / 8 + index * .7))
        draw.line((x, y + 2, x, y), fill='#75804D')
        draw.line((x - 1 + lean, y, x, y + 1), fill='#8C9A5C')
        draw.point((x + 1 + lean, y - 1), fill='#5B7746')
    # A curled-up cat by the porch, with a slow tail tip and occasional blink.
    draw.line((8, 26, 13, 26), fill='#A58160')
    draw.rectangle((9, 24, 12, 25), fill='#B18A62')
    draw.point((9, 23), fill='#B18A62')
    draw.point((11, 23), fill='#B18A62')
    draw.point((10, 25), fill='#443B32' if elapsed % 8 < 7.5 else '#B18A62')
    draw.point((14, 25 if elapsed % 8 < 4 else 26), fill='#8A684D')
    for index, (x, y) in enumerate(((28, 15), (41, 16), (58, 13))):
        glow_phase = elapsed * math.tau / 8 + index * 2.1
        color = '#AFA46D' if math.sin(glow_phase) > .5 else '#6B7252'
        draw.point((x + round(math.sin(glow_phase) * 2), y + round(math.cos(glow_phase))), fill=color)
    for index, (x, y) in enumerate(((6, 3), (15, 5), (34, 3), (44, 6), (60, 2))):
        draw.point((x, y), fill='#8C8B8C' if math.sin(elapsed * math.tau / 8 + index) > .6 else '#525B70')
    return image
