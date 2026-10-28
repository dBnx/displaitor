"""Mystery Dungeon companions: native pixels, restrained light, little prop games.

All art is bundled locally. Pose sheets are decoded and dimmed once, then kept
in a bounded cache; the live sender still uploads a single 64x32 RGB565 frame.
"""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

COLORS = {"torchic": "#E9AD69", "eevee": "#D5B08B", "treecko": "#86BD85"}
ACTION_SECONDS = 1.8
ART = Path(__file__).resolve().parent / "art" / "rescue-pets"


@lru_cache(maxsize=1)
def _catalog():
    return json.loads((ART / "sources.json").read_text(encoding="utf-8"))["assets"]


@lru_cache(maxsize=15)
def _poses(name, mode, direction):
    """Keep a common crop across a sequence so tails/ears never recenter it."""
    info = _catalog()[name][mode]
    width, height = info["frame_size"]
    with Image.open(ART / info["file"]) as source:
        cells = [source.crop((i * width, direction * height,
                              (i + 1) * width, (direction + 1) * height)).convert("RGBA")
                 for i in range(len(info["durations"]))]
    bounds = [cell.getchannel("A").getbbox() for cell in cells]
    common = (min(b[0] for b in bounds), min(b[1] for b in bounds),
              max(b[2] for b in bounds), max(b[3] for b in bounds))
    result = []
    for cell in cells:
        cell = cell.crop(common)
        # Broad fur/leaf/feather areas stay subdued on the emissive matrix.
        # Preserve the tiny pale eye glints against dark pupils and outlines.
        data = cell.tobytes()
        pixels = []
        for r, g, b, a in zip(data[::4], data[1::4], data[2::4], data[3::4]):
            intensity = .74 if min(r, g, b) >= 224 else .43
            pixels.append((round(r * intensity), round(g * intensity), round(b * intensity), a))
        cell.putdata(pixels)
        result.append(cell)
    return tuple(result)


def _pose(name, mode, frame, direction=1):
    frames = _poses(name, mode, direction)
    if mode == "walk":
        return frames[(frame * len(frames) // 8) % len(frames)]
    durations = _catalog()[name][mode]["durations"]
    tick = frame % 16 * sum(durations) / 16
    for index, duration in enumerate(durations):
        tick -= duration
        if tick < 0:
            return frames[index]
    return frames[-1]


def _key(frame, keys):
    """Hand-timed anticipation, contact and recovery, on whole pixels."""
    for (start, a), (end, b) in zip(keys, keys[1:]):
        if frame <= end:
            return round(a + (b - a) * max(0, (frame - start) / (end - start)))
    return keys[-1][1]


def _leaf(draw, x, y, tilt=0):
    draw.polygon(((x - 2, y), (x + tilt, y - 2), (x + 2, y), (x, y + 2)),
                 fill="#47754B", outline="#789359")
    draw.line(((x - 1, y + 1), (x + 2, y - 1)), fill="#A0AD72")


def _stick(draw, x, y, angle):
    dx, dy = round(4 * math.cos(angle)), round(4 * math.sin(angle))
    draw.line(((x - dx, y - dy), (x + dx, y + dy)), fill="#554030", width=2)
    draw.line(((x - dx, y - dy), (x + dx, y + dy)), fill="#B48A59")
    # A fork and one small leaf make this a twig, rather than a floating bar.
    draw.line(((x + dx, y + dy), (x + dx - 2, y + dy - 2)), fill="#B48A59")
    draw.point((x + dx - 2, y + dy - 3), fill="#71935B")


def _sparkle(draw, x, y):
    draw.line(((x - 1, y), (x + 1, y)), fill="#C7B888")
    draw.line(((x, y - 1), (x, y + 1)), fill="#C7B888")


def _treecko_arm(draw, shoulder, elbow, palm, *, open_hand=False):
    """Short bent forearm and three small gecko fingertips, around the grip."""
    draw.line((shoulder, elbow, palm), fill="#1B4400", width=2)
    draw.line((shoulder, elbow, palm), fill="#3D4F11")
    px, py = palm
    draw.rectangle((px, py, px + 1, py + 1), fill="#4F5C2C")
    # Closed fingers wrap over the stick, instead of the stick replacing a hand.
    for fx, fy in ((px + 2, py - 1), (px + 2, py + 1), (px, py + 2)):
        draw.point((fx + (1 if open_hand else 0), fy), fill="#5C6748")


def sprite(name, frame, activity, *, hop=0, action=None):
    """Draw in the 40x32 play area; action is a normalized, one-shot progress."""
    f = frame % 16
    playing = action is not None
    beat = min(15, max(0, round(action * 15))) if playing else f
    working = activity in ("busy", "hard")
    hard = activity == "hard"
    image = Image.new("RGB", (64, 32), "black")
    draw = ImageDraw.Draw(image)
    for point in ((3, 4), (34, 7)):
        draw.point(point, fill="#17252D")
    # Ground stays put during all actions, including an externally requested hop.
    draw.ellipse((9, 29, 29, 30), fill="#101C24")
    center, lift, mode, direction = 18, 0, "walk" if working else "idle", 1
    pose_frame = f
    if playing:
        mode, pose_frame = "idle", 0

    if name == "torchic":
        if playing:
            # Wind-up, a startled backwards hop, then a proud little recovery.
            center += _key(beat, ((0, 0), (3, -1), (6, -2), (10, 0), (15, 0)))
            lift = _key(beat, ((0, 0), (3, 0), (6, 3), (10, 0), (15, 0)))
            pose_frame = 15 if beat <= 3 else 12 if beat < 10 else 0
        elif working:
            center += _key(f, ((0, 0), (4, 3), (8, 0), (12, -2), (15, 0)))
            lift = 1 if hard and f % 8 in (2, 3) else 0
        # A little seed is something to inspect, even when the PC is idle.
        draw.line(((30, 27), (31, 27)), fill="#807255")
        draw.point((31, 26), fill="#A79465")
    elif name == "eevee":
        if playing:
            # Crouch, pounce towards a falling leaf, touch it, settle back down.
            center += _key(beat, ((0, 0), (3, -2), (7, 5), (10, 5), (15, 0)))
            lift = _key(beat, ((0, 0), (3, 0), (6, 3), (9, 1), (11, 0), (15, 0)))
            mode = "walk" if 4 <= beat <= 12 else "idle"
            pose_frame = _key(beat, ((4, 0), (5, 4), (9, 4), (12, 6))) if mode == "walk" else 0
        elif working:
            center += _key(f, ((0, 0), (4, 3), (8, 0), (12, -2), (15, 0)))
            lift = 1 if hard and f % 8 in (2, 3) else 0
        elif f in (12, 13, 14):
            direction = 0  # A small glance at the person watching.
    else:  # Treecko carries its twig in every state, not just during a trick.
        # A relaxed three-quarter stance, with planted feet. Moving the wrist
        # and elbow gives the twig weight without running or jumping in place.
        mode, pose_frame = "idle", 0

    actor = _pose(name, mode, pose_frame, direction)
    lift = min(3, max(0, lift + hop))
    y = 29 - actor.height - lift
    # A slight squash sells the wind-up without resampling any other pose.
    if playing and 1 <= beat <= 3:
        actor = actor.resize((actor.width, actor.height - 1), Image.Resampling.NEAREST)
        y += 1
    x = center - actor.width // 2
    image.paste(actor, (x, y), actor)

    if name == "torchic":
        if playing and 4 <= beat <= 11:
            # Three small embers leave the beak and drift upwards; no full-panel
            # flashes. The last one fizzles into a tiny smoke curl.
            for index in range(3):
                age = beat - 4 - index
                if 0 <= age <= 5:
                    ex, ey = center + 9 + age * 2, 19 - lift - age - index
                    draw.polygon(((ex - 1, ey), (ex, ey - 2), (ex + 1, ey), (ex, ey + 1)),
                                 fill="#BB703D")
                    draw.point((ex, ey), fill="#F0B775")
            if beat >= 9:
                draw.line(((32, 10), (33, 9), (32, 8)), fill="#55606C")
        elif hard and f in (5, 6, 7):
            draw.point((29 + f - 5, 20 - (f - 5)), fill="#C58B50")
        if playing and beat >= 12:
            _sparkle(draw, 29, 13)
    elif name == "eevee":
        if playing:
            lx = _key(beat, ((0, 33), (3, 34), (7, 35), (10, 31), (15, 33)))
            ly = _key(beat, ((0, 17), (3, 15), (7, 18), (10, 21), (15, 17)))
            if 8 <= beat <= 10:
                _sparkle(draw, 32, 22)
        else:
            lx, ly = 33 + (1 if f in (5, 6, 7) else 0), 18 + round(math.sin(f * math.tau / 16) * 2)
        _leaf(draw, lx, ly, -1 if f % 8 < 4 else 1)
    else:
        airborne = playing and 5 <= beat <= 11
        palm_x, palm_y = center + 6, 22 - lift
        tilt = -.95 + math.sin(f * math.tau / 16) * (.32 if hard else .22 if working else .08)
        if playing:
            palm_x += _key(beat, ((0, 0), (3, -1), (4, 1), (8, 1), (12, 0), (15, 0)))
            palm_y += _key(beat, ((0, 0), (3, 1), (4, -2), (8, -3), (12, -1), (15, 0)))
            tilt = -.95 + _key(beat, ((0, 0), (3, 5), (4, -2), (12, -2), (15, 0))) / 10
        elif working:
            palm_y -= round(math.sin(f * math.tau / 16))
        # The lower third of the twig sits in the palm while it is held.
        sx = palm_x + round(2 * math.cos(tilt))
        sy = palm_y + round(2 * math.sin(tilt))
        if airborne:
            # One turn along a gentle arc, with the open hand waiting below it.
            t = (beat - 4) / 8
            sx = 26 + round(math.sin(math.pi * t))
            sy = round(18 - 8 * 4 * t * (1 - t)) - lift
            tilt = -1.15 + t * math.tau
        _stick(draw, sx, sy, tilt)
        _treecko_arm(draw, (center + 2, 20 - lift), (center + 3, 23 - lift),
                     (palm_x, palm_y), open_hand=airborne)
        # The other hand rests beside the belly, with its own tiny fingertips.
        draw.line(((center + 1, 22 - lift), (center, 24 - lift)), fill="#3D4F11")
        draw.point((center - 1, 24 - lift), fill="#5C6748")
        draw.point((center, 25 - lift), fill="#5C6748")
        if playing and beat == 12:
            _sparkle(draw, 32, 20)
    return image
