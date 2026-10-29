"""Short, opaque pixel-art overlays; the ambient scene clock never resets."""

from __future__ import annotations

import math
from PIL import Image, ImageColor, ImageDraw

from . import hunter

DURATION = 3.2


def heart(draw: ImageDraw.ImageDraw, x: int, y: int, color: str) -> None:
    draw.polygon(((x - 2, y), (x - 1, y - 1), (x, y), (x + 1, y - 1),
                  (x + 2, y), (x + 2, y + 1), (x, y + 3), (x - 2, y + 1)), fill=color)


def spark(draw: ImageDraw.ImageDraw, x: int, y: int, color: str) -> None:
    draw.line((x - 1, y, x + 1, y), fill=color)
    draw.line((x, y - 1, x, y + 1), fill=color)


def flame_spirit(elapsed: float) -> Image.Image:
    """A shaded, expressive little hearth spirit with drifting flame tongues."""
    image = Image.new('RGBA', (64, 32))
    envelope = min(1.0, (elapsed + .08) / .65, (DURATION - elapsed) / .7)
    height = max(2, round(20 * envelope))
    x, bottom = 32, 31 - round(5 * envelope) + round(math.sin(elapsed * 5) * .6)
    top = bottom - height
    sway = round(math.sin(elapsed * 9) * 2)
    mask = Image.new('1', (64, 32))
    shape = ImageDraw.Draw(mask)
    shape.polygon(((x - 10, bottom - 4), (x - 9, top + height // 2),
                   (x - 7 + sway, top + 2), (x - 5, top + 6), (x - 2, top + 4),
                   (x + sway, top - 1), (x + 3, top + 4), (x + 4, top + 7),
                   (x + 8 - sway, top + 3), (x + 9, top + height // 2),
                   (x + 10, bottom - 4), (x + 8, bottom - 1), (x + 4, bottom + 1),
                   (x - 5, bottom + 1), (x - 8, bottom - 1)), fill=1)
    palette = ('#BB462B', '#D25B2D', '#E47731', '#EE9236', '#F4AE42', '#F8C655', '#FBD76A')
    for yy in range(max(0, top - 1), min(32, bottom + 2)):
        for xx in range(21, 44):
            if mask.getpixel((xx, yy)):
                warmth = (yy - top) / max(1, height) - abs(xx - x) / 45
                color = palette[max(0, min(6, round(warmth * 6)))]
                image.putpixel((xx, yy), ImageColor.getrgb(color) + (255,))
    draw = ImageDraw.Draw(image)
    # Thin hot strands follow the outer flames; no flat yellow oval face.
    if height > 8:
        draw.line(((x - 7, bottom - 4), (x - 8, bottom - 7), (x - 6, top + 5)), fill='#F8B64B')
        draw.line(((x + 7, bottom - 4), (x + 8, bottom - 7)), fill='#F9CF65')
    if height < 12:
        return image
    eye_y = bottom - 10
    glance = 1 if .8 < elapsed < 1.5 else 0
    wink = 1.75 < elapsed < 1.95
    for side in (-1, 1):
        eye_x = x + side * 4
        if wink and side == -1:
            draw.line(((eye_x - 2, eye_y + 2), (eye_x, eye_y + 1), (eye_x + 2, eye_y + 2)), fill='#684530')
        else:
            draw.ellipse((eye_x - 2, eye_y - 1, eye_x + 2, eye_y + 4), fill='#E9D9A7')
            draw.ellipse((eye_x - 2, eye_y - 1, eye_x + 1, eye_y + 3), fill='#FFF2CE')
            draw.line((eye_x + glance, eye_y + 1, eye_x + glance, eye_y + 2), fill='#493D30')
        # Unequal brows add a curious expression without moving the whole face.
        draw.line((eye_x - 1, eye_y - 3 + (side == 1), eye_x + 1, eye_y - 3), fill='#B56936')
        wave = round(math.sin(elapsed * 8 + side) * 2)
        hand_y = bottom - 6 - (3 + wave if side == -1 else 0)
        draw.line(((x + side * 8, bottom - 5), (x + side * 12, hand_y),
                   (x + side * 13, hand_y - 2)), fill='#D57B35', width=2)
        draw.line(((x + side * 9, bottom - 5), (x + side * 12, hand_y)), fill='#F9C85C')
        draw.point((x + side * 12, hand_y - 2), fill='#FFE49A')
    draw.line(((x - 3, bottom - 4), (x - 2, bottom - 2), (x + 1, bottom - 1),
               (x + 3, bottom - 3)), fill='#864D32')
    draw.point((x - 1, bottom - 2), fill='#F7E1A0')
    if elapsed > 2:
        age = (elapsed - 2) / 1.2
        for side in (-1, 1):
            draw.point((round(32 + side * (10 + age * 5)), round(16 - age * 10)), fill='#F5CB7F')
    return image


def layer(name: str, elapsed: float) -> Image.Image:
    """Return a binary-alpha 64x32 layer; no background or gamma correction."""
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('Action time must be finite and nonnegative')
    image = Image.new('RGBA', (64, 32))
    if elapsed >= DURATION:
        return image
    if name in hunter.NAMES:
        image = hunter.reaction_layer(name, elapsed)
    draw = ImageDraw.Draw(image)
    p = elapsed / DURATION
    if name == 'fire':
        return flame_spirit(elapsed)
    elif name == 'nyan':
        # A rainbow of star trails follows a full-panel celebratory orbit.
        colors = ('#F2B3C0', '#F1C890', '#EFE5A6', '#B7D9AB', '#AED8E6', '#CABBE4')
        for i, color in enumerate(colors):
            x = round(31 + 27 * math.cos(p * math.tau + i * .22))
            y = round(15 + 13 * math.sin(p * math.tau + i * .22))
            spark(draw, x, y, color)
    elif name == 'hyper':
        # Extra shooting stars stretch radially for a brief warp burst.
        for i in range(12):
            angle = i * math.tau / 12
            travel = (p * 3 + i * .13) % 1
            distance = 4 + travel * 31
            hx, hy = 32 + distance * math.cos(angle), 16 + distance * math.sin(angle) * .55
            draw.line((round(hx), round(hy), round(hx + 6 * math.cos(angle)),
                       round(hy + 3 * math.sin(angle))), fill='#D0E5ED')
    elif name == 'farm':
        # A fish leaps from the pond while a shooting star crosses above it.
        x = 45 + round(15 * p)
        y = 26 - round(14 * math.sin(math.pi * p))
        draw.ellipse((x - 2, y - 1, x + 2, y + 1), fill='#EBC190', outline='#936F63')
        draw.polygon(((x - 3, y), (x - 5, y - 2), (x - 5, y + 2)), fill='#C8AD88')
        draw.point((x + 1, y - 1), fill='#343C4A')
        if p < .65:
            sx, sy = round(6 + 65 * p), round(1 + 8 * p)
            draw.line((sx - 5, sy - 1, sx, sy), fill='#A8B9B9')
            spark(draw, sx, sy, '#F5DFC0')
        if p > .7:
            radius = round((p - .7) * 15)
            draw.arc((60 - radius, 26 - radius // 2, 60 + radius, 26 + radius // 2 + 1),
                     0, 360, fill='#A6DBD6')
    elif name == 'winter':
        # One snowball arcs between the walkers, then bursts into soft flakes.
        if p < .7:
            q = p / .7
            x, y = round(23 + 21 * q), round(21 - 12 * math.sin(math.pi * q))
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill='#EDF4ED')
            draw.point((x - 1, y + 1), fill='#A8CCD1')
        else:
            for i in range(9):
                angle = i * math.tau / 9
                spread = (p - .7) * 28
                spark(draw, round(44 + spread * math.cos(angle)),
                      round(21 + spread * math.sin(angle)), '#DFEEE7')
    elif name == 'okami':
        # A brush circle paints itself, followed by a bloom of cherry blossoms.
        draw.arc((12, 2, 47, 30), -90, -90 + min(360, round(p * 600)), fill='#343D3C', width=2)
        for i in range(8):
            angle = i * math.tau / 8 + p
            x, y = round(30 + 22 * math.cos(angle)), round(15 + 12 * math.sin(angle))
            if p * 12 >= i:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    draw.point((x + dx, y + dy), fill='#EDB8B2')
                draw.point((x, y), fill='#FFE3B6')
    elif name == 'witcher':
        # A restrained Quen shield shimmers around Geralt, then sheds sparks.
        radius = min(13, 4 + round(p * 28))
        draw.arc((22 - radius, 20 - radius, 22 + radius, 20 + radius),
                 round(p * 180), round(p * 180) + 300, fill='#E3BE71')
        for i in range(7):
            angle = i * math.tau / 7 - p * 3
            spark(draw, round(22 + radius * math.cos(angle)),
                  round(20 + radius * math.sin(angle)), '#F4D995')
    elif name == 'reef':
        # A rising trail of heart-shaped bubbles shared by both friends.
        for i in range(4):
            q = (p + i * .19) % 1
            x = round(21 + i * 8 + math.sin(q * math.tau + i) * 2)
            y = round(29 - q * 28)
            heart(draw, x, y, '#F0BACC' if i % 2 else '#AEE4DF')
            draw.point((x - 1, y), fill='#F5E9DC')
    elif name == 'palico':
        # A real serving pose: the paw, dish and happy eyes share the same clock.
        lift = round(math.sin(math.pi * p) * 6)
        if lift > 2:
            y = 15 - lift
            draw.line((41, y, 42, y - 1), fill='#D6D8BB')
            if .7 < elapsed < 1.3 or 2 < elapsed < 2.4:
                spark(draw, 48, 17 - lift, '#F4DA9A')
    elif name == 'rathalos':
        # A tapered, curling breath emerges from the muzzle, with a bright core.
        reach = max(0, round(math.sin(math.pi * p) * 8))
        if .4 < elapsed < 2.7:
            draw.polygon(((57, 25), (59, 23), (59 + reach, 20), (58 + reach, 23),
                          (60 + reach, 23), (59 + reach, 26), (59, 26)), fill='#E79653')
            draw.line(((58, 25), (61, 24), (61 + reach, 22)), fill='#F9D891')
            draw.point((61 + reach, 20), fill='#EAC28B')
    elif name == 'zinogre':
        # Blue charge crawls along the layered fur; little thunderbugs gather.
        for i in range(4):
            angle = i * math.tau / 4 + p * 3
            x, y = round(32 + 24 * math.cos(angle)), round(14 + 10 * math.sin(angle))
            draw.point((x, y), fill='#E1F3CF')
            draw.line((x - 1, y + 1, x + 1, y + 1), fill='#8DC6CA')
        if .5 < elapsed < 2.7:
            shift = int(elapsed * 8) % 3
            for x, y in ((13, 16), (29, 16), (36, 13)):
                draw.line(((x, y), (x + 1, y - 3 - shift), (x + 3, y - 2), (x + 4, y - 5)), fill='#C5ECE2')
                draw.point((x + 1, y - 2), fill='#7BC0D1')
    elif name == 'poogie':
        # Folded ears perk and the eye smiles while two small hearts float away.
        for i in range(2):
            q = min(1.0, max(0.0, p * 1.6 - i * .3))
            if 0 < q < 1:
                heart(draw, 28 + i * 25, round(17 - q * 12), '#E6A6A4')
                draw.point((27 + i * 25, round(17 - q * 12)), fill='#F8D4BC')
    else:
        raise ValueError('Unknown scene action')
    return image
