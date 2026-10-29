"""Mystery Dungeon companions: native colours, whole pixels, little prop games.

All art is bundled locally. Pose sheets are decoded with their original colours, then kept
in a bounded cache; the live sender still uploads a single 64x32 RGB565 frame.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict, cast
from ..models import Point

from functools import lru_cache
import json
import math

from PIL import Image, ImageDraw
from . import IDLE_FRAMES


class PoseInfo(TypedDict):
    file: str
    frame_size: list[int]
    durations: list[int]

COLORS = {"torchic": "#E9AD69", "eevee": "#D5B08B", "treecko": "#86BD85",
          "cubone": "#D9CFA0", "ratzfatz": "#BE9BDF", "ratikarl": "#E0BA79"}
ACTION_SECONDS = 1.8
from ..paths import ART as ART_ROOT

ART = ART_ROOT / "rescue-pets"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, PoseInfo]]:
    return cast(dict[str, dict[str, PoseInfo]], json.loads((ART / "sources.json").read_text(encoding="utf-8"))["assets"])


@lru_cache(maxsize=30)
def _poses(name: str, mode: str, direction: int) -> tuple[Image.Image, ...]:
    """Keep a common crop across a sequence so tails/ears never recenter it."""
    info = _catalog()[name][mode]
    width, height = info["frame_size"]
    with (ART / info["file"]).open("rb") as stream, Image.open(stream) as source:
        cells = [source.crop((i * width, direction * height,
                              (i + 1) * width, (direction + 1) * height)).convert("RGBA")
                 for i in range(len(info["durations"]))]
    bounds = [bounds for cell in cells if (bounds := cell.getchannel("A").getbbox()) is not None]
    if not bounds:
        raise ValueError("Pose sheet has no visible pixels")
    common = (min(b[0] for b in bounds), min(b[1] for b in bounds),
              max(b[2] for b in bounds), max(b[3] for b in bounds))
    # Preserve source RGB and alpha. Output gamma belongs solely to Client;
    # attenuating these colours here would darken every pet and winter walker twice.
    return tuple(cell.crop(common) for cell in cells)


@lru_cache(maxsize=30)
def _render_poses(name: str, mode: str, direction: int) -> tuple[Image.Image, ...]:
    frames = _poses(name, mode, direction)
    if name not in ('torchic', 'eevee', 'treecko'):
        width, height = frames[0].size
        # Raticate remains the larger rat; retain the fixed floor below it.
        max_height = 27 if name == 'ratikarl' else 23
        scale = min(1.0, 24 / width, max_height / height)
        size = (round(width * scale), round(height * scale))
        frames = tuple(frame.resize(size, Image.Resampling.NEAREST) for frame in frames)
    if mode != 'idle' or name == 'eevee':
        return frames
    # Sheet cells contain vertical padding changes. Anchor idle feet instead
    # of turning those offsets into whole-body hops. Keep the common x anchor.
    aligned: list[Image.Image] = []
    for frame in frames:
        bounds = frame.getchannel('A').getbbox()
        pose = Image.new('RGBA', frame.size)
        pose.paste(frame, (0, frame.height - bounds[3] if bounds else 0))
        aligned.append(pose)
    return tuple(aligned)


def _pose(name: str, mode: str, frame: int, direction: int=1) -> Image.Image:
    frames = _render_poses(name, mode, direction)
    if mode == "walk":
        return frames[(frame * len(frames) // 8) % len(frames)]
    durations = _catalog()[name][mode]["durations"]
    tick = frame % 16 * sum(durations) / 16
    for index, duration in enumerate(durations):
        tick -= duration
        if tick < 0:
            return frames[index]
    return frames[-1]


@lru_cache(maxsize=3)
def walking_frames(name: str) -> tuple[Image.Image, ...]:
    """Small right-facing poses for full-panel scenes, with a shared anchor."""
    return tuple(frame.resize((round(frame.width / 2), round(frame.height / 2)), Image.Resampling.NEAREST)
                 for frame in _poses(name, 'walk', 2))


def _key(frame: float, keys: Sequence[tuple[int, int]]) -> int:
    """Hand-timed anticipation, contact and recovery, on whole pixels."""
    for (start, a), (end, b) in zip(keys, keys[1:]):
        if frame <= end:
            return round(a + (b - a) * max(0, (frame - start) / (end - start)))
    return keys[-1][1]


def _leaf(draw: ImageDraw.ImageDraw, x: int, y: int, tilt: int=0) -> None:
    draw.polygon(((x - 2, y), (x + tilt, y - 2), (x + 2, y), (x, y + 2)),
                 fill="#47754B", outline="#789359")
    draw.line(((x - 1, y + 1), (x + 2, y - 1)), fill="#A0AD72")


def _stick(draw: ImageDraw.ImageDraw, x: int, y: int, angle: float) -> None:
    dx, dy = round(4 * math.cos(angle)), round(4 * math.sin(angle))
    draw.line(((x - dx, y - dy), (x + dx, y + dy)), fill="#554030", width=2)
    draw.line(((x - dx, y - dy), (x + dx, y + dy)), fill="#B48A59")
    # A fork and one small leaf make this a twig, rather than a floating bar.
    draw.line(((x + dx, y + dy), (x + dx - 2, y + dy - 2)), fill="#B48A59")
    draw.point((x + dx - 2, y + dy - 3), fill="#71935B")


def _sparkle(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.line(((x - 1, y), (x + 1, y)), fill="#C7B888")
    draw.line(((x, y - 1), (x, y + 1)), fill="#C7B888")


def _treecko_arm(draw: ImageDraw.ImageDraw, shoulder: Point, elbow: Point, palm: Point, *, open_hand: bool=False) -> None:
    """Short bent forearm and three small gecko fingertips, around the grip."""
    draw.line((shoulder, elbow, palm), fill="#3F9F00", width=2)
    draw.line((shoulder, elbow, palm), fill="#8FB727")
    px, py = palm
    draw.rectangle((px, py, px + 1, py + 1), fill="#B7D767")
    # Closed fingers wrap over the stick, instead of the stick replacing a hand.
    for fx, fy in ((px + 2, py - 1), (px + 2, py + 1), (px, py + 2)):
        draw.point((fx + (1 if open_hand else 0), fy), fill="#D7EFA7")


def sprite(name: str, frame: int, activity: str, *, hop: int=0, action: float | None=None) -> Image.Image:
    """Draw in the 40x32 play area; action is a normalized, one-shot progress."""
    f = frame % 16
    playing = action is not None
    beat = min(15, max(0, round(action * 15))) if action is not None else f
    working = activity in ("busy", "hard")
    resting = not working and not playing
    idle_tick = frame % IDLE_FRAMES
    idle_angle = idle_tick * math.tau / IDLE_FRAMES
    hard = activity == "hard"
    image = Image.new("RGB", (64, 32), "black")
    draw = ImageDraw.Draw(image)
    for point in ((3, 4), (34, 7)):
        draw.point(point, fill="#17252D")
    # Ground stays put during all actions, including an externally requested hop.
    draw.ellipse((9, 29, 29, 30), fill="#101C24")
    center, lift, mode, direction = 18, 0, "walk" if working else "idle", 1
    pose_frame = f
    if resting:
        pose_frame = idle_tick // 2 % 16
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
        else:
            # Drift and glance only; approaching/pouncing belongs to A.
            if 43 <= idle_tick <= 48:
                direction = 0
    elif name in ('cubone', 'ratzfatz', 'ratikarl'):
        center = 15
        if playing:
            mode = 'walk' if 3 <= beat <= 11 else 'idle'
            if name == 'cubone':
                center += _key(beat, ((0, 0), (3, -1), (7, 2), (11, 0), (15, 0)))
                lift = _key(beat, ((0, 0), (3, 0), (6, 3), (9, 2), (12, 0), (15, 0)))
            else:
                reach = 7 if name == 'ratzfatz' else 5
                center += _key(beat, ((0, 0), (3, -1), (7, reach), (10, reach), (15, 0)))
                # The little rat bounces only after returning beneath its header.
                lift = 1 if name == 'ratzfatz' and beat in (12, 13) else 0
            pose_frame = beat
        elif working:
            center += _key(f, ((0, 0), (4, 2), (8, 0), (12, -1), (15, 0)))
            lift = 1 if hard and f in (3, 4, 11, 12) else 0
        else:
            mode = 'idle'
            if name == 'cubone' and 43 <= idle_tick <= 48:
                direction = 0  # Cubone looks up from its bone at a firefly.
    else:  # Treecko carries its twig in every state, not just during a trick.
        # A relaxed three-quarter stance, with planted feet. Moving the wrist
        # and elbow gives the twig weight without running or jumping in place.
        mode, pose_frame = "idle", 0

    actor = _pose(name, mode, pose_frame, direction)
    max_lift = min(3, max(0, 28 - actor.height)) if name == 'ratikarl' else 3
    lift = min(max_lift, max(0, lift + hop))
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
            if resting:
                lx = 32 + round(2 * math.sin(idle_angle * 2))
                ly = 18 + round(3 * math.sin(idle_angle))
            else:
                lx, ly = 33 + (1 if f in (5, 6, 7) else 0), 18 + round(math.sin(f * math.tau / 16) * 2)
        _leaf(draw, lx, ly, -1 if f % 8 < 4 else 1)
    elif name in ('cubone', 'ratzfatz', 'ratikarl'):
        if name == 'cubone':
            if resting:
                fx = 30 + round(3 * math.sin(idle_angle))
                fy = 15 + round(5 * math.sin(idle_angle * 2))
                draw.point((fx, fy), fill='#E2C98B')
                draw.point((fx - 1, fy + 1), fill='#776C50')
                if idle_tick % 8 < 4:
                    draw.line((fx - 1, fy - 1, fx + 1, fy - 1), fill='#A5A989')
            # The native pose keeps its bone; the hop kicks a small dust puff.
            if playing and 9 <= beat <= 12:
                for dx, dy in ((-3, 0), (1, -1), (4, 0)):
                    draw.point((15 + dx, 27 + dy), fill='#AD9E7F')
            if playing and beat >= 12:
                _sparkle(draw, 29, 15)
        else:
            # Nose to berry/acorn, bite, crumbs, then settle back at home.
            bite = playing and 7 <= beat <= 12
            color = '#BF7697' if name == 'ratzfatz' else '#BB8B52'
            sway = round(math.sin(idle_angle * 2)) if resting else 0
            draw.ellipse((27, 24, 31, 27), fill=color)
            draw.point((28, 24), fill='#D9C39A')
            draw.line((29, 23, 31 + sway, 22), fill='#8CAB6C')
            if name == 'ratikarl':
                draw.line((27, 24, 30, 24), fill='#806344')
            if bite:
                draw.point((27, 25), fill='black')
                draw.point((30, 27), fill='#E1C795')
                draw.point((32, 25), fill='#CEAE7B')
            if playing and beat >= 12:
                _sparkle(draw, 29, 17)
    else:
        airborne = playing and 5 <= beat <= 11
        palm_x, palm_y = center + 6, 22 - lift
        tilt = -.95 + math.sin(f * math.tau / 16) * (.32 if hard else .22 if working else .08)
        if resting:
            # Tiny wrist adjustments; tossing the twig is reserved for A.
            tilt = -.95 + .18 * math.sin(idle_angle * 2)
            palm_y -= round(math.sin(idle_angle * 2) * .6)
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
        draw.line(((center + 1, 22 - lift), (center, 24 - lift)), fill="#8FB727")
        draw.point((center - 1, 24 - lift), fill="#D7EFA7")
        draw.point((center, 25 - lift), fill="#D7EFA7")
        if playing and beat == 12:
            _sparkle(draw, 32, 20)
    return image
