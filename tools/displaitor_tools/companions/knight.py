"""A quiet horned wanderer whose A-button action casts Descending Dark."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

from . import FRAMES, IDLE_FRAMES

COLORS = {'knight': '#D2DEE2'}
ACTION_SECONDS = 2.4


def _knight(frame: int, activity: str, *, hop: int, casting: bool, crouch: int = 0) -> Image.Image:
    """The Knight's mask, cloak and nail, with a small casting brace."""
    actor = Image.new('RGBA', (40, 29))
    draw = ImageDraw.Draw(actor)
    angle = frame % IDLE_FRAMES * math.tau / IDLE_FRAMES
    stride = frame % FRAMES
    working = activity in ('busy', 'hard') and not casting
    bob = (1 if stride % 8 in (2, 3) else 0) if working else 0 if casting else round(math.sin(angle * 2) * .6)
    center, top = 16, 13 + bob + crouch - min(2, max(0, hop))
    hem = round(math.sin(angle * 3))
    draw.line((13, 26, 12, 28), fill='#7C8A9D')
    draw.line((19, 26, 20, 28), fill='#7C8A9D')
    draw.polygon(((center - 3, 20), (center + 3, 20), (center + 6 + hem, 25),
                  (center + 3, 25), (center + 2, 27), (center - 1, 26),
                  (center - 4, 27), (center - 6 + hem, 25)), fill='#69798F', outline='#374359')
    draw.line(((center - 1, 21), (center - 3, 25)), fill='#98A4B5')
    draw.line(((center + 1, 21), (center + 3 + hem, 25)), fill='#48566D')
    draw.line((center, 22, center, 25), fill='#8390A4')
    draw.polygon(((center - 4, top + 2), (center - 7, top - 3),
                  (center - 7, top - 6), (center - 5, top - 3),
                  (center - 3, top), (center - 1, top + 2)), fill='#DBE4E0', outline='#96A9AE')
    draw.polygon(((center + 2, top + 2), (center + 5, top - 2),
                  (center + 7, top - 7), (center + 8, top - 4),
                  (center + 6, top + 1), (center + 4, top + 3)), fill='#DBE4E0', outline='#96A9AE')
    draw.polygon(((center - 5, top), (center - 3, top - 1), (center + 3, top - 1),
                  (center + 5, top + 1), (center + 5, top + 6),
                  (center + 2, top + 9), (center - 2, top + 8), (center - 5, top + 5)),
                 fill='#DBE4E0', outline='#96A9AE')
    draw.line((center - 2, top, center + 2, top), fill='#F0F1DF')
    gaze = 1 if casting else round(math.sin(angle))
    blink = frame % IDLE_FRAMES in (22, 23, 57) and not casting
    for eye in (center - 3, center + 2):
        draw.ellipse((eye + gaze, top + 2, eye + gaze + 1,
                      top + (2 if blink else 5)), fill='#171E2A')
    lift = (2 if activity == 'hard' else 1) * round(math.sin(stride * math.tau / 8)) if working else 0
    if casting:
        # Tuck the nail down for the plunge rather than aiming a projectile.
        draw.line(((center + 3, 22), (center + 5, 24)), fill='#98A4B5')
        draw.line((center + 5, 22, center + 5, 27), fill='#C5D3D4', width=2)
        draw.point((center + 5, 27), fill='#EDF0DB')
    else:
        draw.line(((center + 4, 23), (center + 6, 22 - lift)), fill='#98A4B5')
        draw.line((center + 6, 22 - lift, center + 10, 25 - lift), fill='#C5D3D4', width=2)
        draw.point((center + 10, 25 - lift), fill='#EDF0DB')
    return actor


def _dive(progress: float) -> tuple[int, int]:
    """Crouch, rise, hang briefly, accelerate down and settle into the landing."""
    if progress < .08:
        return 0, 0
    if progress < .16:
        return 0, 2
    if progress < .3:
        t = (progress - .16) / .14
        return round(6 * (1 - (1-t)**2)), 0
    if progress < .37:
        return 6, 0
    if progress < .48:
        t = (progress - .37) / .11
        return round(6 * (1 - t*t)), 0
    if progress < .56:
        return 0, 2
    if progress < .68:
        return 0, 1
    return 0, 0


def _spell(progress: float) -> Image.Image:
    """A short plunge trail and two ground-level bursts, below the fixed HUD."""
    image = Image.new('RGBA', (40, 29))
    draw = ImageDraw.Draw(image)
    if .08 <= progress < .3:
        charge = (progress - .08) / .22
        for index in range(3):
            x = 16 + round((index - 1) * 6 * (1 - charge))
            y = 25 - round(charge * 4) - index
            draw.point((x, y), fill='#CFD8EC')
    if .37 <= progress < .48:
        draw.polygon(((8, 15), (11, 6), (12, 20), (16, 28),
                      (20, 20), (22, 6), (25, 15), (23, 24),
                      (16, 28), (9, 24)), fill='#151A2D', outline='#A5B3D8')
        draw.line((8, 8, 8, 16), fill='#788DB6')
        draw.line((25, 10, 25, 19), fill='#BAC6DC')
    # Two expanding pulses give the landing weight without moving the floor.
    for start in (.48, .6):
        age = (progress - start) / .22
        if 0 <= age < 1:
            radius = round(6 + 12 * age)
            height = round(5 * (1 - age)) + 1
            edge = '#D8DCEC' if age < .4 else '#9BA6CB'
            draw.line(((16-radius, 27), (18-radius, 25), (11, 25-height), (14, 24)), fill=edge)
            draw.line(((18, 24), (21, 25-height), (14+radius, 25), (16+radius, 27)), fill=edge)
            draw.line((16-radius, 27, 18-radius, 26), fill='#BAC7DD')
            draw.line((14+radius, 26, 16+radius, 27), fill='#BAC7DD')
            for side in (-1, 1):
                x = 16 + side * round(7 + age * 11)
                y = 26 - round(6 * math.sin(age * math.pi))
                draw.line((x, y, x + side, y - 1), fill='#A1ADBE')
                draw.point((x + side * 3, y + 1), fill='#7183A8')
    return image


def sprite(frame: int, activity: str, *, hop: int = 0, action: float | None = None) -> Image.Image:
    """Native pet composition with an explicit, short A-button spell."""
    image = Image.new('RGB', (64, 32))
    draw = ImageDraw.Draw(image)
    draw.ellipse((9, 29, 28, 30), fill='#101C24')
    draw.point((3, 4), fill='#17252D')
    draw.point((34, 7), fill='#17252D')
    tick = frame % IDLE_FRAMES
    playing = action is not None and 0 < action < 1
    elevation, crouch = _dive(action) if playing and action is not None else (0, 0)
    if playing and action is not None:
        effect = _spell(action)
        image.paste(effect, (0, 0), effect)
    actor = _knight(frame, activity, hop=hop, casting=playing, crouch=crouch)
    image.paste(actor, (0, -elevation), actor)
    for index in range(3):
        phase = (tick + index * 21) % IDLE_FRAMES
        mx = (4, 32, 7)[index] + round(math.sin(phase * math.tau / IDLE_FRAMES))
        draw.point((mx, 26 - phase // 3), fill=('#859DAE', '#ADBFC4', '#526B83')[index])
    return image
