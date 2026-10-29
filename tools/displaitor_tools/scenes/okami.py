"""An original ink-wash shrine and spirit wolf, inspired by Ōkami."""

from __future__ import annotations

from functools import lru_cache
import math
from PIL import Image, ImageDraw

PERIOD = 16.0
INK = '#444B40'
PAPER = '#ADA18A'


@lru_cache(maxsize=1)
def background() -> Image.Image:
    image = Image.new('RGB', (64, 32), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 8), fill='#A29681')
    draw.rectangle((0, 9, 63, 19), fill='#B5AA91')
    # Still paper grain, red sun, layered mountains and loose brush-stroke ridges.
    for index in range(32):
        x, y = index * 19 % 64, index * 11 % 32
        draw.point((x, y), fill='#A79A82')
    draw.ellipse((46, 3, 54, 11), fill='#B86B55')
    draw.point((48, 4), fill='#C48468')
    draw.polygon(((8, 18), (17, 11), (21, 12), (30, 4), (35, 12),
                  (40, 10), (48, 17), (57, 13), (63, 17), (63, 24), (8, 24)), fill='#7D8976')
    draw.line(((18, 15), (21, 13), (24, 13), (30, 5), (32, 10)), fill='#B8B49A')
    draw.polygon(((0, 23), (12, 18), (20, 21), (31, 15), (40, 18),
                  (48, 22), (59, 18), (63, 20), (63, 31), (0, 31)), fill='#5C735F')
    draw.polygon(((0, 27), (11, 25), (23, 27), (36, 25), (47, 27),
                  (59, 24), (63, 25), (63, 31), (0, 31)), fill='#758060')
    # A pale shrine path makes the red gate legible against the ink-green hill.
    draw.polygon(((49, 24), (58, 24), (63, 31), (41, 31)), fill='#B7AB8E')
    for x, y in ((48, 27), (56, 29), (47, 31)):
        draw.line((x, y, x + 3, y), fill='#8B8C73')
    # Slightly curved torii beams; posts are planted in small dark stone feet.
    draw.line(((45, 13), (48, 14), (59, 14), (62, 13)), fill=INK, width=3)
    draw.line(((45, 12), (48, 13), (59, 13), (62, 12)), fill='#B5654D')
    draw.line((47, 17, 60, 17), fill='#A35946', width=2)
    for x in (49, 58):
        draw.line((x, 16, x, 25), fill='#A75A48', width=2)
        draw.point((x - 1, 25), fill=INK)
        draw.point((x, 25), fill=INK)
    draw.line((53, 14, 53, 17), fill='#6D5141')
    # Blossom tree: irregular dark branches and washed-out petal clusters.
    draw.line(((4, 27), (6, 21), (5, 14), (7, 9)), fill=INK, width=2)
    draw.line(((5, 15), (0, 10), (0, 7)), fill=INK)
    draw.line(((6, 18), (11, 13), (17, 11)), fill=INK)
    draw.line(((7, 11), (14, 7), (19, 7)), fill=INK)
    for x, y, radius in ((1, 7, 3), (7, 8, 3), (13, 6, 4), (18, 8, 2), (14, 12, 3)):
        draw.ellipse((x - radius, y - 1, x + radius, y + 2), fill='#BC8D87')
        draw.line((x - radius + 1, y, x + 1, y), fill='#D1AAA0')
        draw.point((x + radius, y + 1), fill='#A87474')
    draw.line(((0, 29), (5, 28), (10, 29), (15, 28)), fill='#4F624B')
    draw.line((18, 30, 22, 30), fill='#89916C')
    return image


def wolf(draw: ImageDraw.ImageDraw, elapsed: float) -> None:
    phase = int(elapsed * 4) % 4
    fur, shade, red = '#E5DFC6', '#B5B69C', '#AE503F'
    # Foreground Amaterasu: a long canine silhouette, pointed ears and brush tail.
    draw.ellipse((18, 28, 44, 30), fill='#586C4E')
    tail = (0, 1, 1, 0)[phase]
    draw.line(((23, 23), (18, 21), (16, 17 - tail), (18, 15 - tail),
               (20, 16 - tail), (19, 18 - tail)), fill=INK, width=4)
    draw.line(((23, 22), (18, 20), (17, 17 - tail), (18, 16 - tail),
               (19, 17 - tail)), fill=fur, width=2)
    draw.point((17, 17 - tail), fill=red)
    # Far paws first; all feet land on the same fixed ground line.
    for index, x in enumerate((25, 36)):
        stride = (-1, 0, 1, 0)[(phase + index * 2) % 4]
        draw.line(((x, 24), (x + stride, 28), (x + stride + 1, 28)), fill=INK, width=2)
        draw.point((x + stride, 27), fill=shade)
    draw.polygon(((22, 21), (26, 19), (34, 19), (38, 21), (38, 25),
                  (32, 26), (24, 25), (22, 23)), fill=fur, outline=INK)
    draw.line((26, 24, 34, 24), fill=shade)
    for index, x in enumerate((23, 35)):
        stride = (1, 0, -1, 0)[(phase + index * 2) % 4]
        draw.line(((x, 24), (x + stride, 28)), fill=INK, width=3)
        draw.line((x, 25, x + stride, 27), fill=fur)
        draw.line((x + stride, 28, x + stride + 2, 28), fill=fur)
    # Upright neck, triangular ears, long muzzle and unmistakable red eye stripe.
    draw.polygon(((34, 23), (35, 18), (35, 13), (38, 16), (40, 13),
                  (41, 18), (46, 20), (45, 22), (40, 23), (38, 25)),
                 fill=fur, outline=INK)
    draw.line((36, 15, 37, 17), fill=red)
    draw.point((40, 16), fill=red)
    draw.line(((37, 18), (38, 20), (40, 21)), fill=red, width=2)
    blink = 7.5 <= elapsed % 8 < 7.75
    if blink:
        draw.line((40, 18, 41, 18), fill=INK)
    else:
        draw.point((41, 19), fill=INK)

    draw.point((45, 20), fill='#2F3934')
    draw.line((42, 22, 44, 22), fill=shade)
    draw.line(((27, 20), (25, 21), (27, 23), (29, 22)), fill=red)
    draw.line((33, 21, 32, 23), fill=red)
    # Flaming Divine Reflector floats over the shoulders, without covering the face.
    draw.ellipse((24, 10, 33, 19), fill=INK)
    draw.ellipse((25, 11, 32, 18), fill='#527865')
    draw.arc((26, 12, 31, 17), 15, 305, fill='#C1CA9D')
    draw.point((28, 14), fill='#E1D6A5')
    for index, x in enumerate((24, 28, 32)):
        lift = (0, 1, 2, 1)[(phase + index) % 4]
        draw.line(((x, 12), (x - 1, 9 - lift), (x + 1, 10)), fill='#B76742', width=2)
        draw.point((x, 10), fill='#DFAB61')


def render(elapsed: float) -> Image.Image:
    image = background().copy()
    draw = ImageDraw.Draw(image)
    # Two curling wind ribbons slide slowly over the distant mountain wash.
    wind = round(math.sin(elapsed * math.tau / 8) * 2)
    for x, y in ((28 + wind, 11), (39 - wind, 8)):
        draw.line(((x - 3, y), (x + 3, y), (x + 4, y - 1), (x + 3, y - 2)), fill='#BEB69C')
    # A few flowers answer the spirit's steps, then return to leaf-green.
    for index, x in enumerate((18, 21, 39)):
        y = 27 + index % 2
        draw.point((x, y), fill='#C2958A' if (int(elapsed * 2) + index) % 8 < 4 else '#9A9D75')
    for index in range(7):
        phase = elapsed * math.tau / 8 + index
        x = (index * 13 + math.floor(elapsed * 4) + round(math.sin(phase))) % 64
        y = (index * 7 + math.floor(elapsed * 2)) % 32
        draw.point((x, y), fill='#CE9E95')
        if index in (1, 5):
            draw.point((x + 1, y), fill='#B5807C')
    wolf(draw, elapsed)
    return image
