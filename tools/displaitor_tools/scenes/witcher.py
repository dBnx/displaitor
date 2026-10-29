"""An original quiet valley camp, inspired by The Witcher 3: Wild Hunt."""

from __future__ import annotations

from functools import lru_cache
import math
from PIL import Image, ImageDraw

PERIOD = 16.0


@lru_cache(maxsize=1)
def background() -> Image.Image:
    image = Image.new('RGB', (64, 32), '#17242F')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 7, 63, 14), fill='#2D3B43')
    draw.rectangle((0, 15, 63, 31), fill='#394A48')
    draw.ellipse((17, 2, 22, 7), fill='#A8ADA0')
    draw.ellipse((15, 1, 20, 6), fill='#17242F')
    draw.polygon(((0, 15), (6, 9), (11, 12), (19, 5), (24, 12),
                  (30, 8), (37, 14), (46, 10), (55, 14), (63, 10), (63, 23), (0, 23)), fill='#4F5E5B')
    draw.line(((12, 11), (19, 6), (22, 10)), fill='#7B8580')
    draw.polygon(((0, 20), (13, 15), (22, 18), (32, 13), (44, 17),
                  (55, 14), (63, 18), (63, 31), (0, 31)), fill='#2A403B')
    # Distant Kaer Morhen-inspired keep: rough stone, uneven towers, warm windows.
    draw.rectangle((39, 10, 53, 17), fill='#66706A')
    draw.rectangle((39, 7, 41, 15), fill='#71796F')
    draw.rectangle((49, 5, 52, 15), fill='#788076')
    draw.polygon(((48, 5), (50, 2), (53, 5)), fill='#3F514F')
    draw.polygon(((38, 7), (40, 4), (42, 7)), fill='#3F514F')
    for x in (42, 45, 47, 53):
        draw.point((x, 9), fill='#879080')
    draw.rectangle((45, 13, 47, 17), fill='#34463F')
    draw.point((50, 8), fill='#A69462')
    draw.point((40, 10), fill='#A69462')
    draw.line((39, 17, 55, 17), fill='#3F5348')
    # A winding cold river lies below the keep and beside the warm campsite.
    draw.polygon(((49, 18), (52, 19), (47, 22), (54, 25), (63, 27),
                  (63, 31), (54, 30), (43, 24), (42, 22)), fill='#476365')
    draw.line(((50, 19), (45, 22), (49, 24)), fill='#5B7673')
    draw.polygon(((0, 25), (12, 22), (23, 25), (34, 22), (43, 25),
                  (48, 31), (0, 31)), fill='#293C31')
    draw.ellipse((24, 26, 39, 31), fill='#4C4934')
    # A dark spruce frames the camp without hiding the valley.
    draw.line((3, 10, 4, 28), fill='#202C29', width=2)
    for y, width in ((7, 4), (11, 6), (15, 8), (19, 9)):
        draw.polygon(((3, y - 4), (3 - width, y + 3), (4, y + 1),
                      (3 + width, y + 3)), fill='#20362F')
        draw.line((3, y - 2, 3 + width - 1, y + 2), fill='#30493B')
    return image


def horse(draw: ImageDraw.ImageDraw, elapsed: float) -> None:
    # Roach grazes slowly: only the head, ear and tail change position.
    phase = int(elapsed) % 8
    drop = (0, 0, 1, 2, 2, 1, 0, 0)[phase]
    draw.ellipse((7, 23, 15, 26), fill='#6F5840', outline='#26332D')
    draw.line((8, 26, 7, 29), fill='#384133')
    draw.line((13, 26, 14, 29), fill='#384133')
    draw.line((15, 25, 15, 29), fill='#26332D')
    draw.line((14, 24, 16, 21 + drop), fill='#786144', width=2)
    draw.line((16, 21 + drop, 18, 22 + drop), fill='#91734C', width=2)
    draw.point((16, 19 + drop), fill='#5E513B')
    draw.point((17, 21 + drop), fill='#29372F')
    draw.rectangle((9, 23, 12, 24), fill='#343C31')
    draw.point((9, 25), fill='#97815A')
    tail = -1 if phase in (2, 3, 4) else 0
    draw.line(((7, 24), (5, 25), (5 + tail, 27)), fill='#3B3E2E')


def geralt(draw: ImageDraw.ImageDraw, elapsed: float) -> None:
    # White ponytail, twin sword hilts and dark leather armour read at panel scale.
    ink, steel, hair = '#18252A', '#8B9691', '#C2C5B8'
    draw.ellipse((17, 29, 28, 31), fill='#1E302A')
    draw.line((22, 24, 27, 11), fill=ink, width=3)
    draw.line((23, 22, 27, 12), fill=steel)
    draw.line((20, 24, 18, 12), fill=ink, width=3)
    draw.line((20, 22, 18, 12), fill='#697B7A')
    draw.line((24, 14, 28, 15), fill='#B3A074')
    draw.line((16, 15, 20, 14), fill='#A59A74')
    draw.polygon(((19, 21), (24, 20), (26, 24), (25, 27), (18, 27),
                  (17, 24)), fill='#445559', outline=ink)
    draw.line((19, 23, 23, 26), fill='#9A8C65')
    draw.line((18, 27, 25, 27), fill='#907B54')
    draw.rectangle((18, 28, 20, 30), fill=ink)
    draw.rectangle((23, 28, 25, 30), fill=ink)
    draw.point((23, 23), fill='#C0B993')  # Wolf medallion.
    draw.rectangle((20, 16, 24, 20), fill='#A39981')
    draw.line((20, 20, 23, 21), fill='#535B53')
    draw.line(((19, 18), (19, 15), (22, 14), (24, 15), (24, 16), (21, 16)), fill=hair, width=2)
    draw.line((18, 17, 17, 20), fill='#8E9E9A')
    draw.point((24, 18), fill='#DFC07D')
    draw.point((24, 19), fill='#795B4D')
    # Warm hands over the fire, then sip from a small travel cup and lower it.
    sip = (0, 0, 0, 1, 2, 2, 1, 0)[int(elapsed) % 8]
    hand_x, hand_y = 28 - sip, 24 - sip * 2
    draw.line(((24, 22), (26, 24), (hand_x, hand_y)), fill='#748079', width=2)
    draw.point((hand_x, hand_y), fill='#C0A27B')
    draw.rectangle((hand_x, hand_y - 2, hand_x + 2, hand_y), fill='#A9A78A')
    draw.line((hand_x, hand_y - 2, hand_x + 2, hand_y - 2), fill=ink)


def leshen(draw: ImageDraw.ImageDraw, elapsed: float) -> None:
    # A small woodland leshen: branching antlers, pale skull and bark-clad limbs.
    # Sway only the upper body; planted root feet keep the clearing still.
    sway = round(math.sin(elapsed * math.tau / 8))
    bark, edge, light = '#6D7866', '#1B2D2C', '#A2AA89'
    draw.ellipse((45, 29, 59, 31), fill='#26372F')
    draw.line(((49, 24), (48, 28), (46, 30)), fill=edge, width=3)
    draw.line(((55, 24), (56, 28), (58, 30)), fill=edge, width=3)
    draw.line(((49, 24), (48, 28), (46, 30)), fill=bark)
    draw.line(((55, 24), (56, 28), (58, 30)), fill=bark)
    x = 52 + sway
    for side in (-1, 1):
        draw.line(((x + side, 16), (x + side * 4, 12), (x + side * 7, 11),
                   (x + side * 8, 8)), fill=edge, width=3)
        draw.line(((x + side, 16), (x + side * 4, 12), (x + side * 7, 11),
                   (x + side * 8, 8)), fill=light)
        draw.line((x + side * 4, 12, x + side * 4, 8), fill=light)
        draw.line((x + side * 7, 11, x + side * 9, 11), fill=light)
    draw.polygon(((x - 3, 21), (x, 19), (x + 3, 21), (55, 26), (52, 28), (48, 26)),
                 fill=bark, outline=edge)
    draw.line((x, 22, 52, 26), fill=light)
    draw.line((x - 1, 24, x + 2, 24), fill='#4A5C50')
    # Long branch fingers curl lazily, leaving the skull silhouette unobscured.
    for side in (-1, 1):
        tip = x + side * 7
        draw.line(((x + side * 2, 21), (x + side * 5, 24), (tip, 27)), fill=edge, width=3)
        draw.line(((x + side * 2, 21), (x + side * 5, 24), (tip, 27)), fill=bark)
        draw.line((tip, 26, tip + side, 28), fill=light)
    draw.polygon(((x - 3, 15), (x + 3, 15), (x + 2, 19), (x, 22),
                  (x - 2, 19)), fill='#C0BE9D', outline=edge)
    draw.point((x - 1, 17), fill='#243A37')
    draw.point((x + 1, 17), fill='#243A37')
    draw.line((x, 19, x, 20), fill='#586352')


def render(elapsed: float) -> Image.Image:
    image = background().copy()
    draw = ImageDraw.Draw(image)
    # Thin mist lifts through the distant valley; the campsite camera stays put.
    drift = round(math.sin(elapsed * math.tau / 16) * 3)
    for x, y, width in ((25, 16, 9), (48, 19, 11)):
        draw.line((x + drift, y, x + width + drift, y), fill='#526763')
        draw.line((x + 2 + drift, y + 1, x + width - 2 + drift, y + 1), fill='#455B55')
    horse(draw, elapsed)
    # A small fire uses a hand-timed flame sequence, not a whole-scene flicker.
    phase = int(elapsed * 6) % 4
    height = (3, 4, 5, 4)[phase]
    draw.line(((28, 30), (34, 29)), fill='#9A7049')
    draw.line(((28, 29), (34, 30)), fill='#685238')
    draw.polygon(((28, 28), (29, 25), (30, 26), (32, 28 - height),
                  (32, 26), (34, 28), (33, 29), (29, 29)), fill='#B87542')
    draw.line((30, 28, 31, 25 + phase % 2), fill='#D9A85E', width=2)
    draw.point((31, 28), fill='#E1BD7A')
    for index in range(2):
        age = (elapsed / 4 + index * .5) % 1
        x = 32 + round(age * 4 + math.sin(age * math.tau))
        y = 24 - round(age * 7)
        draw.point((x, y), fill='#B68D54' if age < .5 else '#776B4D')
    for index, (x, y) in enumerate(((48, 23), (56, 28), (59, 30))):
        phase = int(elapsed * 2 + index) % 8
        draw.line((x + phase // 3, y, x + 2 + phase // 3, y), fill='#68807B')
    for index, x in enumerate((2, 7, 39, 44)):
        lean = round(math.sin(elapsed * math.tau / 8 + index))
        draw.line(((x - 1, 31), (x, 28), (x + 1 + lean, 30)), fill='#65704A')
    for index, (x, y) in enumerate(((9, 3), (30, 2), (58, 6))):
        draw.point((x, y), fill='#87948D' if math.sin(elapsed * math.tau / 8 + index) > .7 else '#53666C')
    geralt(draw, elapsed)
    leshen(draw, elapsed)
    return image
