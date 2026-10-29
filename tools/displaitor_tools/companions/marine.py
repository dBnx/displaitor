"""Sea pets with detailed standalone art and compact actors for the baked reef."""

from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw
from . import FRAMES, IDLE_FRAMES

COLORS = {'nudibranch': '#D6A5E3', 'moray': '#9BC5AA'}
ACTION_SECONDS = 2.4


@lru_cache(maxsize=1)
def rock() -> Image.Image:
    """A stationary cave; moving an eel must never move its home."""
    image = Image.new('RGBA', (36, 28))
    draw = ImageDraw.Draw(image)
    draw.polygon(((21, 27), (20, 21), (23, 17), (31, 16), (35, 20), (35, 27)),
                 fill='#293F48', outline='#45616A')
    draw.ellipse((23, 20, 32, 29), fill='#101F2A')
    draw.line(((22, 20), (25, 18), (30, 18)), fill='#5E7677')
    draw.line((33, 23, 34, 26), fill='#36555C')
    draw.point((32, 19), fill='#719486')
    return image


def _heart(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.line(((x - 2, y), (x - 1, y - 1), (x, y), (x + 1, y - 1),
               (x + 2, y), (x, y + 2), (x - 2, y)), fill='#C3879C')


def nudibranch(elapsed: float, *, activity: str = 'idle', action: float | None = None,
               detailed: bool = False) -> Image.Image:
    """Purple sea slug: rippling skirt, feathery cerata and orange rhinophores."""
    image = Image.new('RGBA', (36, 28))
    draw = ImageDraw.Draw(image)
    phase = elapsed * math.tau / 4
    effort = {'idle': 0, 'unknown': 0, 'busy': 1, 'hard': 2}[activity]
    nibble = action is not None and .2 <= action < .7
    reach = 2 if nibble else 0
    resting = detailed and effort == 0 and action is None
    idle_angle = elapsed * math.tau / 16
    if resting:
        reach = 1 if math.sin(idle_angle) > .4 else 0
    # Feathered back appendages ripple in succession, rather than bobbing the floor.
    for index, x in enumerate((7, 11, 15, 19, 23) if detailed else (9, 13, 17, 21)):
        lean = round(math.sin(phase + index) * (1 + effort / 2))
        top = (9 - index % 3 if detailed else 12 - index % 2) - effort
        draw.polygon(((x - 2, 20), (x - 3 + lean, top + 1), (x + lean, top - 2),
                      (x + 2 + lean, top + 2), (x + 2, 20)),
                     fill='#67436F', outline='#AA799D')
        draw.line((x + lean, top, x, 17), fill='#C49DB7')
        draw.point((x + lean, top - 1), fill='#DEAF86')
        if detailed:
            # Alternating single-pixel barbs give each plume a feathery edge.
            for row in range(top + 2, 17, 3):
                stem = x + round(lean * (17 - row) / max(1, 17 - top))
                draw.line((stem - 2, row - 1, stem, row + 1), fill='#E3BAD0')
                draw.line((stem, row + 1, stem + 2, row - 1), fill='#B28DBB')
            draw.point((x + lean, top - 2), fill='#F4C590')
    # A broad dark lavender mantle and a pale rippling skirt preserve contrast.
    skirt = [(4, 23), (7, 20), (13, 19), (20, 19), (25 + reach, 18),
             (30 + reach, 20), (31 + reach, 23)]
    skirt += [(x, 25 + round(math.sin(phase + x) * .6)) for x in range(29, 5, -3)]
    draw.polygon(skirt, fill='#9C7B9D', outline='#D5B4CC')
    draw.ellipse((8, 18, 28 + reach, 23), fill='#654F78')
    draw.line(((5, 23), (12, 23), (18, 24), (25 + reach, 23)), fill='#A98FAF')
    if detailed:
        # A shaded mantle, iridescent seam and orange freckles use the pixels
        # between the big shapes, rather than enlarging a coarse silhouette.
        draw.line(((7, 22), (11, 20), (17, 20), (22, 21), (26 + reach, 20)), fill='#B3A4CE')
        draw.line(((8, 23), (14, 22), (20, 23), (25 + reach, 22)), fill='#846697')
        draw.line(((5, 24), (10, 24), (16, 25), (22, 24), (28 + reach, 24)), fill='#D7BCD9')
        for index, px in enumerate(range(7, 29, 4)):
            py = 25 + round(math.sin(phase + px) * .6)
            draw.point((px, py), fill='#97BED3')
            draw.point((px + 1, py - 1), fill='#E8C5DA')
        for px, py in ((9, 21), (13, 20), (17, 22), (21, 21)):
            draw.point((px, py), fill='#F0BF7D')
            draw.point((px + 1, py), fill='#B97B88')
    # Two sensory horns, a rounded face, tiny cheeks and a friendly smile.
    for x, lean in ((24, -1), (28, 1)):
        wave = round(math.sin(phase + x) * .7)
        if resting:
            wave += round(math.sin(idle_angle + x) * .7)
        draw.line(((x + reach, 18), (x + reach + lean, 13),
                   (x + reach + lean + wave, 10)), fill='#A9788F', width=2)
        draw.line((x + reach + lean + wave, 9, x + reach + lean + wave, 11), fill='#E0AE7B')
        if detailed:
            tip = x + reach + lean + wave
            draw.point((tip, 9), fill='#F6D2A4')
            draw.line((tip - 1, 12, tip, 12), fill='#754E70')
            draw.point((x + reach + lean, 14), fill='#E1B7AC')
    face = (21 + reach, 15, 32 + reach, 24) if detailed else (22 + reach, 16, 31 + reach, 23)
    draw.ellipse(face, fill='#A997B5', outline='#D4BDCE')
    if detailed:
        draw.line(((24 + reach, 16), (28 + reach, 16), (30 + reach, 17)), fill='#E5CFE2')
        draw.line(((24 + reach, 23), (28 + reach, 24), (31 + reach, 22)), fill='#80698C')
    blink = 3.5 <= elapsed % 4 < 3.8
    for x in (25 + reach, 29 + reach):
        x += round(math.sin(idle_angle)) if resting else 0
        draw.line((x, 19, x, 19 if blink else 20), fill='#242A40')
        if detailed and not blink:
            draw.point((x, 18), fill='#F3E5EE')
    draw.point((24 + reach, 21), fill='#D9899F')
    draw.point((30 + reach, 21), fill='#D9899F')
    draw.line(((26 + reach, 21), (27 + reach, 22), (28 + reach, 21)), fill='#59445E')
    for x, y in ((11, 20), (16, 21), (20, 19)):
        draw.point((x, y), fill='#C5A26B')
    if resting:
        # A tiny passing plankton draws the feelers and eyes forward.
        px = 32 + round(2 * math.sin(idle_angle))
        py = 12 + round(2 * math.sin(idle_angle * 2))
        draw.point((px, py), fill='#E1C795')
        draw.point((px - 1, py - 1), fill='#8FA6B2')
    # A-button: lean towards the sea lettuce, nibble, then a contented heart.
    if action is not None:
        if action < .7:
            draw.line(((34, 26), (33, 22), (35, 20)), fill='#62926A')
            draw.line((33, 22, 31, 21), fill='#8EB987')
        if .7 <= action < .95:
            _heart(draw, 28, 7 - round((action - .7) * 12))
    return image


def moray(elapsed: float, *, activity: str = 'idle', action: float | None = None,
          detailed: bool = False) -> Image.Image:
    """A spotted green moray peeking from its cave and breathing gently."""
    image = Image.new('RGBA', (36, 28))
    draw = ImageDraw.Draw(image)
    phase = elapsed * math.tau / 4
    effort = {'idle': 0, 'unknown': 0, 'busy': 1, 'hard': 2}[activity]
    stretch = round(math.sin(phase) * (1 + effort))
    x, y = 10 - effort, 12 + stretch
    resting = detailed and effort == 0 and action is None
    if resting:
        idle_angle = elapsed * math.tau / 16
        x -= round(math.sin(idle_angle))
        y += round(math.sin(idle_angle * 2) * .7)
    blowing = action is not None and .2 <= action < .8
    # The tail stays inside the cave while the neck makes a relaxed S curve.
    body: tuple[tuple[int, int], ...] = ((27, 25), (28, 21), (25, 18), (22, 18), (20, y + 3), (x + 6, y + 2))
    if detailed:
        # Sample a smooth S-shaped neck directly in panel pixels. The tail
        # anchor stays in the same cave, including during high-load breathing.
        body = tuple((round((1-t)**3 * 27 + 3*(1-t)**2*t * 30
                            + 3*(1-t)*t*t * 20 + t**3 * (x + 6)),
                      round((1-t)**3 * 25 + 3*(1-t)**2*t * 15
                            + 3*(1-t)*t*t * 23 + t**3 * (y + 2)))
                     for step in range(25) for t in (step / 24,))
        draw.polygon(((28, 25), (29, 20), (26, 16), (23, 17),
                      (20, y - 1), (16, y - 3), (17, y + 2), (25, 22)),
                     fill='#526E62', outline='#91AA83')
        draw.line(((27, 21), (25, 18), (22, 19)), fill='#BDD0A0')
    draw.line(body, fill='#1E3839', width=9)
    draw.line(body, fill='#567B65', width=7)
    draw.line(((27, 24), (26, 20), (22, 20), (19, y + 5)), fill='#92A577', width=2)
    draw.line(((27, 20), (24, 17), (20, y), (x + 6, y - 2)), fill='#80A38A')
    if detailed:
        draw.line(body, fill='#7E9B70', width=5)
        for index in range(3, len(body) - 3, 4):
            sx, sy = body[index]
            draw.line((sx - 1, sy - 1, sx, sy), fill='#3F5D4A')
            draw.point((sx + 1, sy + 1), fill='#B0C48B')
    head = (x - 4, y - 5, x + 12, y + 6) if detailed else (x - 3, y - 4, x + 11, y + 5)
    draw.ellipse(head, fill='#71967B', outline='#A3B89B')
    if detailed:
        draw.arc((x - 2, y - 4, x + 10, y + 4), 195, 310, fill='#C1D0A0')
        draw.line(((x - 2, y + 4), (x + 3, y + 5), (x + 8, y + 4)), fill='#506F54')
        for sx, sy in ((x + 7, y - 3), (x + 9, y - 1), (x + 7, y + 1), (x + 3, y + 4)):
            draw.line((sx, sy, sx + 1, sy), fill='#3F5D4A')
            draw.point((sx, sy + 1), fill='#A7BC8C')
    # Facing left towards the nudibranch in the shared scene.
    draw.line(((x - 3, y + 1), (x + 1, y + 2), (x + 6, y + 1)), fill='#233B39')
    if blowing or math.sin(phase) > .5:
        draw.line((x - 2, y + 3, x + 3, y + 3), fill='#213339')
        draw.point((x + 1, y + 2), fill='#C9C4A4')
        if detailed:
            draw.point((x - 1, y + 2), fill='#E1D9B7')
    draw.ellipse((x + 1, y - 3, x + 4, y), fill='#C1D5AC')
    blink = 3.5 <= elapsed % 4 < 3.8
    draw.line((x + 2, y - 1, x + 3, y - 1 if blink else y - 2), fill='#1C3035')
    if detailed and not blink:
        draw.point((x + 1, y - 3), fill='#E2E9CE')
    draw.point((x - 1, y - 1), fill='#344E4B')
    draw.point((x + 5, y + 2), fill='#BC9290')
    draw.line((x + 9, y + 1, x + 9, y + 3), fill='#3D6256')
    if detailed:
        draw.line(((x + 10, y), (x + 11, y + 2), (x + 10, y + 4)), fill='#4C715A')
        draw.point((x + 11, y + 3), fill='#ABC197')
    for spot_x, spot_y in ((x + 7, y - 2), (x + 6, y + 4), (22, 17), (25, 20), (28, 23)):
        draw.point((spot_x, spot_y), fill='#354F46')
        draw.point((spot_x + 1, spot_y), fill='#405E4C')
    if resting:
        # Little breath bubbles continue between explicit bubble-heart tricks.
        # Offset the two bubbles so something drifts while the head is still.
        tick = round(elapsed * 4)
        for offset in (0, 16):
            idle_age = (tick + offset) % 32
            if idle_age < 26:
                bx = max(2, x - 4 - idle_age // 10)
                by = y + 1 - idle_age // 2
                draw.ellipse((bx - 1, by - 1, bx + 1, by + 1), outline='#8ABCC1')
                draw.point((bx, by - 1), fill='#C4DCD4')
    # A-button: a pursed mouth, a growing bubble, then a drifting bubble-heart.
    if action is not None and .15 <= action < .95:
        age = (action - .15) / .8
        bx = x - 4 - round(age * 3)
        if detailed:
            bx = max(2, bx)
        by = y - round(age * 10)
        radius = 1 if age < .3 else 2
        draw.ellipse((bx - radius, by - radius, bx + radius, by + radius), outline='#8ABCC1')
        draw.point((bx - 1, by - 1), fill='#C4DCD4')
        if age > .7:
            _heart(draw, bx, by)
    return image


def sprite(design: str, frame: int, activity: str, *, hop: int = 0,
           action: float | None = None) -> Image.Image:
    """Pet composition: fixed sand/cave, animated actor, black 24-column HUD."""
    image = Image.new('RGB', (64, 32))
    if action is not None and action >= 1:
        action = None
    draw = ImageDraw.Draw(image)
    draw.line((1, 31, 38, 31), fill='#253D42')
    for x, y in ((4, 29), (14, 30), (32, 30), (37, 28)):
        draw.point((x, y), fill='#466163')
    if design == 'moray':
        image.paste(rock(), (2, 4), rock())
    # The pet has a whole play area to itself. The shared reef keeps its compact
    # actor composition; existing baked clips remain identical to their source.
    count = IDLE_FRAMES if activity in ('idle', 'unknown') and action is None else FRAMES
    actor = (nudibranch if design == 'nudibranch' else moray)(
        frame % count / 4, activity=activity, action=action, detailed=True)
    image.paste(actor, (2, 4 - hop), actor)
    return image
