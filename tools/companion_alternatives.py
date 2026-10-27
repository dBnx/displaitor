#!/usr/bin/env python3
"""Offline alternative set B. Export pixel-exact art for choosing against set A.

These studies do not change the live companion sender. Each character occupies
the same left 40x32 region of a 64x32 Canvas background as the current set.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

try:
    from .companion_designs import FRAMES, quantized, sprite as original
except ImportError:
    from companion_designs import FRAMES, quantized, sprite as original

MOODS = ("idle", "busy", "hard")
DESIGNS = {"pebble": "#E4C18C", "tux": "#8CD6F2", "axel": "#E9A0CD"}
PAIRS = {"pebble": "orbit", "tux": "ember", "axel": "sprout"}


def sprite(design, frame, activity="idle"):
    if design not in DESIGNS or activity not in MOODS:
        raise ValueError("unknown alternative character or activity")
    image = Image.new("RGB", (64, 32), "black")
    draw = ImageDraw.Draw(image)
    phase = frame % FRAMES
    lift = (1 - math.cos(phase * math.tau / FRAMES)) / 2
    working, hard = activity != "idle", activity == "hard"
    blink = phase in (13, 14)
    # Shadows are dim and small; all unused matrix pixels stay unlit.
    draw.ellipse((10, 29, 29, 30), fill="#111D23")

    def line(points, color, width=1):
        draw.line(points, fill=color, width=width)

    def polygon(points, color, outline=None):
        draw.polygon(points, fill=color, outline=outline)

    def box(bounds, color):
        draw.rectangle(bounds, fill=color)

    def eyes(y, left=16, right=23, color="#D5F5ED"):
        for x in (left, right):
            box((x, y + (1 if blink else 0), x + 2, y + 1), color)

    def plates(x, y, color, heavy=False):
        box((x - 2, y - 3, x + 2, y + 3), color)
        box((x - 1, y - 4, x + 1, y + 4), "#7F869F" if design == "pebble" else "#7B8DC0")
        if heavy:
            box((x - 4, y - 2, x - 3, y + 2), color)
            box((x + 3, y - 2, x + 4, y + 2), color)

    if design == "pebble":
        # Broad stone golem with glowing cracks and rock fists. The bar travels
        # from its waist to overhead, so effort changes the whole silhouette.
        squat = round((1 - lift) * (3 if hard else 1)) if working else round(lift)
        top = 11 + squat
        polygon([(14, top), (25, top - 1), (29, top + 3), (28, top + 12),
                 (24, top + 15), (15, top + 15), (10, top + 11), (10, top + 3)],
                "#45464B", "#74787B")
        polygon([(14, top), (24, top - 1), (27, top + 2), (13, top + 2)], "#626268")
        box((13, top + 4, 18, top + 7), "#181A23")
        box((22, top + 4, 26, top + 7), "#181A23")
        eyes(top + 5, 15, 23, "#F1D28C")
        line([(13, top + 3), (18, top + 4)], "#949086")
        line([(22, top + 4), (26, top + 3)], "#949086")
        line([(17, top + 10), (22, top + 10)], "#22242C")
        line([(20, top), (19, top + 3), (21, top + 4)], "#C3945E")
        line([(24, top + 12), (21, top + 13), (20, top + 15)], "#C3945E")
        line([(15, top + 14), (13, 28)], "#6C6B70", 3)
        line([(25, top + 14), (27, 28)], "#6C6B70", 3)
        polygon([(10, 27), (15, 27), (16, 29), (9, 29)], "#52525B", "#777780")
        polygon([(25, 27), (30, 27), (31, 29), (24, 29)], "#52525B", "#777780")
        bar_y = round(23 - 18 * lift) if working else 24
        line([(12, top + 8), (8, top + 7 if lift < .5 else bar_y + 5), (8, bar_y)], "#7B7878", 3)
        line([(28, top + 8), (32, top + 7 if lift < .5 else bar_y + 5), (32, bar_y)], "#7B7878", 3)
        line([(3, bar_y), (37, bar_y)], "#9ABCC6")
        plates(6, bar_y, "#3E476F", heavy=hard)
        plates(34, bar_y, "#3E476F", heavy=hard)
        box((7, bar_y - 1, 10, bar_y + 2), "#888582")
        box((30, bar_y - 1, 33, bar_y + 2), "#888582")
        if hard and lift > .7:
            draw.point((3, 2 + phase % 2), fill="#F7CA74")
            draw.point((37, 2 + phase % 2), fill="#F7CA74")
    elif design == "tux":
        # Round penguin with a pale bib, small beak and broad flippers.
        squat = round(2 * (1 - lift)) if working else round(lift)
        top = 4 + squat
        draw.ellipse((10, top, 29, top + 22), fill="#203443", outline="#547284")
        draw.ellipse((14, top + 10, 25, top + 21), fill="#607985")
        polygon([(13, top + 6), (16, top + 4), (19, top + 6), (20, top + 8),
                 (22, top + 4), (26, top + 6), (26, top + 13), (13, top + 13)], "#526C79")
        eyes(top + 7, 14, 23, "#D8F2FA")
        polygon([(18, top + 11), (22, top + 11), (20, top + 14)], "#DAA35E")
        polygon([(13, 26), (17, 26), (17, 29), (10, 29)], "#B7834B")
        polygon([(23, 26), (27, 26), (30, 29), (23, 29)], "#B7834B")
        if working:
            bell_x = round(18 + (17 if hard else 15) * lift)
            bell_y = round(26 - (17 if hard else 14) * lift)
            polygon([(11, top + 11), (14, top + 14), (bell_x - 2, bell_y - 2),
                     (bell_x - 4, bell_y), (10, top + 17)], "#315264", "#7198AA")
            line([(27, top + 12), (bell_x, bell_y - 2)], "#7198AA", 2)
        else:
            bell_x, bell_y = 33, 26
            polygon([(11, top + 11), (8, top + 16), (11, top + 20), (14, top + 15)], "#315264", "#7198AA")
            polygon([(28, top + 11), (31, top + 16), (28, top + 20), (25, top + 15)], "#315264", "#7198AA")
        draw.ellipse((bell_x - 2, bell_y - 4, bell_x + 2, bell_y), outline="#B99775")
        draw.ellipse((bell_x - 3, bell_y - 1, bell_x + 3, bell_y + 3), fill="#546D80", outline="#8EAAB5")
        box((bell_x - 1, bell_y, bell_x, bell_y + 1), "#A5BFC0")
    else:
        # Coral axolotl: feathered gills, wide smile, real arms and large presses.
        # The whole body squats; the weights travel ~17 pixels into the air.
        squat = round((1 - lift) * (6 if hard else 4)) if working else round(lift)
        top = 9 + squat if working else 13 + squat
        for points in (
            [(10, top + 3), (4, top), (5, top + 5), (1, top + 6), (6, top + 8), (3, top + 11), (10, top + 9)],
            [(29, top + 3), (35, top), (34, top + 5), (38, top + 6), (33, top + 8), (36, top + 11), (29, top + 9)]):
            polygon(points, "#713C68", "#C47DA6")
        polygon([(12, top + 1), (26, top + 1), (30, top + 4), (30, top + 9),
                 (26, top + 12), (12, top + 12), (8, top + 9), (8, top + 4)], "#70465D", "#AE7894")
        line([(12, top + 3), (16, top + 2), (24, top + 2)], "#BB819A")
        eyes(top + 5, 14, 23, "#F4D8E9")
        line([(16, top + 8), (18, top + 10), (22, top + 10), (24, top + 8)], "#D893AF")
        box((11, top + 8, 12, top + 8), "#B880AA")
        box((27, top + 8, 28, top + 8), "#B880AA")
        feet = 3 + round(3 * (1 - lift)) if working else 3
        line([(16, top + 12), (20 - feet, 28), (17 - feet, 29)], "#B47F9B", 2)
        line([(24, top + 12), (20 + feet, 28), (23 + feet, 29)], "#B47F9B", 2)
        if working:
            hand_y = round(24 - 17 * lift)
            for shoulder, hand_x, side in ((12, 5, -1), (28, 34, 1)):
                # Wide limbs change direction visibly between squat and press.
                polygon([(shoulder, top + 7), (hand_x - side * 2, hand_y - 3),
                         (hand_x, hand_y - 1), (hand_x, hand_y + 1),
                         (hand_x - side * 3, hand_y + 3), (shoulder, top + 10)],
                        "#945B7B", "#CE95AF")
                line([(shoulder, top + 8), (hand_x, hand_y)], "#B77C9A")
                box((hand_x - 3, hand_y - 1, hand_x + 3, hand_y), "#B8869D")
                plates(hand_x, hand_y, "#3E507B", heavy=hard)
                box((hand_x - 1, hand_y - 1, hand_x, hand_y), "#A8B7E7")
        else:
            line([(12, top + 10), (8, 27)], "#C58EA7", 2)
            line([(28, top + 10), (32, 27)], "#C58EA7", 2)
            for x in (4, 35):
                draw.ellipse((x - 2, 26, x + 2, 29), fill="#3E507B", outline="#7B8DC0")
    if hard:
        y = 4 + phase % 7
        line([(36, y), (36, y + 1)], "#62BBDD")
    # A dim, moving speck makes the idle loop feel alive without a bright field.
    draw.point((1 + phase % 7, 1), fill="#183038")
    return image


def export(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    native = Image.new("RGB", (640, 288), "black")
    labelled = Image.new("RGB", (1416, 744), "#0C0C0C")
    labels = ImageDraw.Draw(labelled)
    for phase in range(FRAMES):
        labels.text((128 + phase * 80, 5), str(phase), fill="#B4B4B4")
    # Original/alternative paired columns for each activity, one character per row.
    comparisons = []
    for phase in range(FRAMES):
        sheet = Image.new("RGB", (1104, 520), "#0C0C0C")
        caption = ImageDraw.Draw(sheet)
        caption.text((8, 5), "A = CURRENT     B = ALTERNATIVE     SAME PLAYBACK RATE FOR POSE COMPARISON", fill="#B4B4B4")
        for col, mood in enumerate(MOODS):
            for variant in range(2):
                caption.text((96 + (col * 2 + variant) * 168, 27),
                             mood.upper() + (" / A" if variant == 0 else " / B"), fill="#B4B4B4")
        for row, design in enumerate(DESIGNS):
            y = 50 + row * 156
            caption.text((8, y + 40), PAIRS[design].upper() + " A", fill="#B4B4B4")
            caption.text((8, y + 58), design.upper() + " B", fill=DESIGNS[design])
            for col, mood in enumerate(MOODS):
                for variant, draw_sprite in enumerate((original, sprite)):
                    character = PAIRS[design] if variant == 0 else design
                    image = quantized(draw_sprite(character, phase, mood)).crop((0, 0, 40, 32))
                    sheet.paste(image.resize((160, 128), Image.Resampling.NEAREST),
                                (96 + (col * 2 + variant) * 168, y))
        comparisons.append(sheet)
    comparisons[8].save(directory / "comparison.png")
    comparisons[0].save(directory / "comparison.gif", save_all=True,
                        append_images=comparisons[1:], duration=125, loop=0, disposal=2, optimize=False)
    row = 0
    for design in DESIGNS:
        for mood in MOODS:
            animation = []
            for phase in range(FRAMES):
                image = quantized(sprite(design, phase, mood)).crop((0, 0, 40, 32))
                native.paste(image, (phase * 40, row * 32))
                labelled.paste(image.resize((80, 64), Image.Resampling.NEAREST),
                               (128 + phase * 80, 24 + row * 80))
                animation.append(image)
            speed = {"idle": 3, "busy": 8, "hard": 12}[mood]
            animation[0].save(directory / (design + "-" + mood + ".gif"), save_all=True,
                              append_images=animation[1:], duration=round(1000 / speed),
                              loop=0, disposal=2, optimize=False)
            labels.text((8, 36 + row * 80), design.upper() + " B", fill=DESIGNS[design])
            labels.text((8, 52 + row * 80), mood.upper(), fill="#B4B4B4")
            row += 1
    native.save(directory / "sprite-sheet.png")
    labelled.save(directory / "sprite-sheet-labelled.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/ui/companions/alternatives"))
    args = parser.parse_args()
    export(args.output_dir)


if __name__ == "__main__":
    main()
