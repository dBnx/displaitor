#!/usr/bin/env python3
"""Pixel Companion design studies: actual 64x32 sprites and Canvas text.

Preview all designs locally, or stream live activity through the Canvas interface.
Exported previews use labelled fixtures; device operation defaults to real readings.
"""
from __future__ import annotations

from ..models import Bounds, Color, Points, Scene

import math

from PIL import Image, ImageDraw

from ..canvas import image_frame
from .pokemon import COLORS as POKEMON, ACTION_SECONDS, sprite as pokemon_sprite
from .stats import fields as stats_fields
from . import knight, marine
from . import FRAMES, IDLE_FRAMES

__all__ = ["POKEMON", "CUSTOM_ACTIONS", "ACTION_SECONDS", "action_seconds", "DESIGNS", "FRAMES", "IDLE_FRAMES", "layout", "sprite", "quantized", "preview_frame"]

PALETTE = {"orbit": "#79ECF0", "ember": "#FFAC72", "sprout": "#96E8A0", **POKEMON, **marine.COLORS, **knight.COLORS}
CUSTOM_ACTIONS = frozenset((*POKEMON, *marine.COLORS, *knight.COLORS))
# Keep the archived artwork for offline comparisons, outside the live rotation.
DESIGNS = {name: color for name, color in PALETTE.items() if name not in ("ember", "sprout")}


def action_seconds(design: str) -> float:
    if design in POKEMON:
        return ACTION_SECONDS
    if design in knight.COLORS:
        return knight.ACTION_SECONDS
    return marine.ACTION_SECONDS if design in marine.COLORS else 1.2


def layout(design: str, page: str="cpu") -> Scene:
    color = PALETTE[design]
    # Long names reserve a blank cell, clear of the panel's edge.
    # Numeric/status slots retain exactly the same positions and widths.
    name_width = max(24, (len(design) + 1) * 4)
    return {"text": {
        "name": dict(x=64 - name_width, y=0, width=name_width, height=6, font="small", color=color, text=design.upper()),
        **stats_fields(color, page),
    }}


def sprite(design: str, frame: int, activity: str="idle", *, hop: int=0, action: float | None=None) -> Image.Image:
    """Whole-pixel art; the right 24 columns stay black for retained text."""
    if design not in PALETTE:
        raise ValueError("unknown companion design")
    if activity not in ("idle", "busy", "hard", "unknown"):
        raise ValueError("unknown companion activity")
    if design in knight.COLORS:
        return knight.sprite(frame, activity, hop=hop, action=action)
    if design in marine.COLORS:
        return marine.sprite(design, frame, activity, hop=hop, action=action)
    if design in POKEMON:
        return pokemon_sprite(design, frame, activity, hop=hop, action=action)
    image = Image.new("RGB", (64, 32), "black")
    draw = ImageDraw.Draw(image)
    phase = frame % FRAMES
    idle_tick = frame % IDLE_FRAMES
    resting = activity in ('idle', 'unknown')
    bob = round(math.sin(phase * math.tau / FRAMES) * (2 if activity == "hard" else 1))
    actor_y = bob - hop
    blink = phase in (6, 7)

    def polygon(points: Points, fill: Color, outline: Color | None=None) -> None:
        draw.polygon([(x, y + actor_y) for x, y in points], fill=fill, outline=outline)

    def line(points: Points, fill: Color) -> None:
        draw.line([(x, y + actor_y) for x, y in points], fill=fill)

    def box(bounds: Bounds, fill: Color) -> None:
        x0, y0, x1, y1 = bounds
        draw.rectangle((x0, y0 + actor_y, x1, y1 + actor_y), fill=fill)

    # Sparse stars and a dim shadow provide depth without a lit panel behind text.
    for x, y in ((3, 4), (34, 7), (5, 23), (35, 25)):
        draw.point((x, y), fill="#17252D")
    draw.ellipse((11, 29, 29, 30), fill="#101C24")

    if design == "orbit":
        for offset in range(5):
            angle = (phase / FRAMES + offset / 24) * math.tau
            draw.point((round(20 + 17 * math.cos(angle)), round(15 + 11 * math.sin(angle))),
                       fill=("#79ECF0", "#447D93", "#2A485C", "#1A2A3E", "#101922")[offset])
        polygon([(11, 9), (14, 6), (26, 6), (30, 10), (30, 21), (27, 25), (13, 25), (10, 21)],
                "#26354E", "#48668A")
        polygon([(14, 7), (24, 7), (28, 10), (12, 10)], "#3A6581")
        line([(19, 5), (19, 2)], "#4A9DAD")
        box((18, 1, 20, 2), "#A7F6F3")
        polygon([(12, 12), (14, 10), (26, 10), (28, 12), (28, 19), (26, 21), (14, 21), (12, 19)], "black")
        for x in (15, 23):
            box((x, 14 if blink else 12, x + 2, 14), "#85F5EF")
            if not blink:
                gaze = round(math.sin(idle_tick * math.tau / IDLE_FRAMES)) if resting else 0
                box((x + 1 + gaze, 13, x + 1 + gaze, 13), "#E8FFFF")
        line([(18, 18), (20, 19), (22, 18)], "#3B8BA3")
        box((18, 23, 22, 23), "#58BDDC")
        box((13, 26, 16, 27), "#365477")
        box((25, 26, 28, 27), "#365477")
        if resting:
            # Gentle tracking is ambient motion; the A-button hop stays special.
            hx = 34 + round(math.sin(idle_tick * math.tau / 32))
            hy = 14 + round(3 * math.sin(idle_tick * math.tau / IDLE_FRAMES))
            draw.rectangle((hx - 1, hy - 1, hx + 1, hy + 1), outline='#58BDDC')
            draw.point((hx, hy), fill='#A7F6F3')
    elif design == "ember":
        # Midtone fur stays visible with the calibrated output curve; keep accents.
        polygon([(13, 25), (7, 27), (3, 23), (4, 17), (7, 14), (8, 21), (14, 22)],
                "#B57554", "#7F5040")
        polygon([(4, 17), (7, 14), (8, 19), (6, 20)], "#DDAF75")
        polygon([(10, 12), (10, 5), (16, 9), (24, 9), (30, 4), (30, 14),
                 (29, 22), (24, 26), (15, 26), (11, 22)], "#A26856", "#6F453C")
        polygon([(11, 7), (14, 9), (11, 11)], "#F8A369")
        polygon([(28, 7), (28, 12), (25, 10)], "#F8A369")
        polygon([(13, 20), (17, 18), (20, 20), (24, 18), (28, 20), (24, 24), (17, 24)], "#C18C70")
        for x in (14, 24):
            box((x, 15 if blink else 13, x + 2, 15), "#FFCB88")
            if not blink:
                box((x + 1, 14, x + 1, 15), "#FFECC0")
        box((19, 18, 21, 18), "#F29C83")
        line([(20, 19), (20, 21), (18, 21)], "#301C27")
        box((15, 27, 17, 27), "#C47A55")
        box((24, 27, 26, 27), "#C47A55")
        for offset in range(3):
            draw.point((3 + offset * 3, 11 - (phase + offset * 4) % 10),
                       fill=("#7D3F37", "#C87548", "#F4BF75")[offset])
    else:
        # Lift the broad body midtones; preserve leaf, eye and cheek detail colours.
        line([(20, 12), (20, 6)], "#4A9C6F")
        polygon([(20, 8), (14, 7), (11, 3), (16, 3), (20, 6)], "#377E65", "#7AC58C")
        polygon([(20, 7), (22, 2), (28, 1), (26, 5), (22, 8)], "#599C69", "#B0E49A")
        polygon([(11, 16), (15, 12), (25, 12), (30, 16), (31, 22), (27, 26),
                 (14, 26), (10, 22)], "#548B6B", "#356B50")
        line([(13, 16), (16, 13), (24, 13)], "#7BB78A")
        polygon([(28, 18), (29, 22), (26, 24), (15, 24), (13, 23), (15, 25), (27, 25), (30, 22)], "#457A59")
        for x in (15, 24):
            box((x, 18 if blink else 16, x + 1, 18), "#C6F4AD")
        box((12, 20, 13, 20), "#966B6A")
        box((28, 20, 29, 20), "#966B6A")
        line([(19, 21), (20, 22), (22, 21)], "#6AB88C")
        box((14, 27, 17, 27), "#67AC7E")
        box((25, 27, 28, 27), "#67AC7E")
        angle = phase / FRAMES * math.tau
        draw.point((round(5 + 2 * math.cos(angle)), round(13 + 5 * math.sin(angle))), fill="#A9E99B")
        draw.point((34, 15 - phase % 8), fill="#376B59")
    if activity in ("busy", "hard"):
        effort = round(math.sin(phase * math.tau / 8) * 3)
        if design == "orbit":
            # Two arms lift a real dumbbell; hard work uses a heavier barbell.
            lift = 20 + effort
            line([(11, 19), (7, lift), (5, lift)], "#48668A")
            line([(29, 19), (33, lift), (35, lift)], "#48668A")
            for x in (5, 35):
                box((x - 2, lift - 2, x + 2, lift), "#5488AD")
                box((x, lift - 3, x, lift + 1), "#A7EAF0")
            if activity == "hard":
                line([(5, lift), (35, lift)], "#AACAD8")
        elif design == "ember":
            # Alternating paws and sparse ground streaks suggest a running stride.
            box((13, 26, 29, 28), "black")
            line([(16, 25), (16 + effort, 28)], "#DDAF75")
            line([(25, 25), (25 - effort, 28)], "#DDAF75")
            line([(12, 21), (9, 21 - effort)], "#7F5040")
            line([(28, 21), (32, 21 + effort)], "#7F5040")
        else:
            # Leaves open and close like arms doing jumping jacks.
            box((10, 0, 29, 11), "black")
            line([(20, 12), (20, 6)], "#4A9C6F")
            leaf_y = 5 + effort
            polygon([(20, 8), (14, leaf_y + 2), (10, leaf_y), (15, leaf_y - 1)],
                    "#377E65", "#7AC58C")
            polygon([(20, 8), (25, leaf_y - 1), (30, leaf_y), (26, leaf_y + 2)],
                    "#599C69", "#B0E49A")
            box((13, 26, 30, 28), "black")
            for x, direction in ((16, -1), (26, 1)):
                line([(x, 25), (x + direction * abs(effort), 28)], "#67AC7E")
        for x in (3, 7, 32):
            draw.point(((x + phase) % 37 + 1, 31), fill="#20303B")
        if activity == "hard":
            drop_y = 7 + phase % 6
            draw.line((33, drop_y, 33, drop_y + 1), fill="#55B7DE")
    return image


def quantized(image: Image.Image) -> Image.Image:
    """Expand the exact uploaded RGB565 pixels for a faithful preview."""
    raw = image_frame(image)
    colors = []
    for offset in range(0, len(raw), 2):
        value = int.from_bytes(raw[offset:offset + 2], "little")
        colors.append((((value >> 11) & 31) * 255 // 31,
                       ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31))
    result = Image.new("RGB", (64, 32))
    result.putdata(colors)
    return result


def preview_frame(image: Image.Image, rendered: Image.Image, design: str, page: str="cpu") -> Image.Image:
    """Retain each real text box, including names wider than the right HUD."""
    image = quantized(image)
    for slot in layout(design, page)["text"].values():
        x, y = slot["x"], slot["y"]
        area = (x, y, x + slot["width"], y + slot["height"])
        image.paste(rendered.crop(area), (x, y))
    return image
