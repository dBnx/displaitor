#!/usr/bin/env python3
"""Two offline 40x32 casts: distinct creatures and Pokemon character studies.

Drawn as whole-pixel shapes, then quantized through the actual Canvas RGB565
converter. These previews do not select or replace any live companion.
"""
from __future__ import annotations

from ..models import Bounds, Color, Points, Pathish

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

from ..companions.designs import FRAMES, quantized

MOODS = ("idle", "busy", "hard")
CASTS = {
    "fresh-cast": {"clack": "#EEA27D", "lumen": "#A7B6F2", "cinder": "#DEAA74"},
    "pokemon": {"cubone": "#D6CFA6", "treecko": "#A8DA76", "torchic": "#F4BE65"},
}


def sprite(character: str, frame: int, activity: str="idle") -> Image.Image:
    if character not in {name for cast in CASTS.values() for name in cast} or activity not in MOODS:
        raise ValueError("unknown character or activity")
    image = Image.new("RGB", (64, 32), "black")
    d = ImageDraw.Draw(image)
    phase = frame % FRAMES
    angle = phase * math.tau / FRAMES
    q = (1 - math.cos(angle)) / 2
    working, hard = activity != "idle", activity == "hard"
    blink = phase in (13, 14)

    def poly(points: Points, color: Color, outline: Color | None=None) -> None:
        d.polygon(points, fill=color, outline=outline)

    def line(points: Points, color: Color, width: int=1) -> None:
        d.line(points, fill=color, width=width)

    def box(bounds: Bounds, color: Color) -> None:
        d.rectangle(bounds, fill=color)

    if character == "clack":
        # Horizontal crab, eye stalks and four pairs of articulated legs.
        bob = round(math.sin(angle) * (2 if hard else 1))
        top = 18 + bob
        d.ellipse((11, 29, 29, 30), fill="#211A24")
        for side in (-1, 1):
            for leg in range(4):
                spread = round(math.sin(angle + leg) * (3 if working else 1))
                root = 20 + side * 8
                elbow = 20 + side * (13 + leg % 2)
                foot = 20 + side * (15 + spread)
                line([(root, top + 3 + leg), (elbow, top + 2 + leg),
                      (foot, min(30, top + 7 + leg % 2))], "#A0634B")
        poly([(12, top), (16, top - 2), (24, top - 2), (28, top),
              (30, top + 5), (27, top + 8), (12, top + 8), (9, top + 5)], "#6F3A37", "#B16B50")
        line([(14, top), (18, top - 1), (24, top - 1)], "#CF9164")
        for x in (15, 24):
            line([(x, top), (x, top - 5)], "#B16B50", 2)
            box((x - 1, top - 6, x + 1, top - 4), "#E8BF8E")
            box((x, top - 5, x + 1, top - 5 if blink else top - 4), "#141925")
        line([(16, top + 5), (23, top + 5)], "#321F2A")
        claw_y = round(22 - 17 * q) if working else top - 2
        for x, side in ((6, -1), (34, 1)):
            line([(20 + side * 8, top + 2), (20 + side * 14, top), (x, claw_y + 2)], "#AE5F46", 2)
            poly([(x - 3, claw_y + 2), (x - 3, claw_y - 2), (x - 1, claw_y - 4),
                  (x - 1, claw_y), (x + 1, claw_y), (x + 1, claw_y - 4),
                  (x + 3, claw_y - 2), (x + 3, claw_y + 2)], "#97523D", "#DD9667")
        if working:
            line([(2, claw_y), (38, claw_y)], "#8F9FA9")
            for x in (3, 37):
                box((x - 1, claw_y - 3, x + 1, claw_y + 3), "#55577C")
                if hard:
                    box((x - 2, claw_y - 2, x + 2, claw_y + 2), "#767A9B")
        elif phase % 4 < 2:
            d.point((5, 29), fill="#483247")
    elif character == "lumen":
        # Umbrella and five trailing tentacles; deliberately no humanoid face.
        width = round(12 - q * (5 if hard else 3)) if working else 12
        top = 5 + round(math.sin(angle))
        root_y = top + 10
        sway = 5 if hard else 3 if working else 1.5
        for index, x in enumerate((12, 16, 20, 24, 28)):
            points = [(x, root_y)]
            for y in range(root_y + 1, 30):
                points.append((round(x + math.sin(angle + y / 4 + index) * sway), y))
            line(points, ("#57869F", "#8B71A6", "#6A9EAE")[index % 3])
            d.point(points[-1], fill="#A9E3EA")
        d.ellipse((20 - width, top, 20 + width, root_y + 2), fill="#263451", outline="#677EA0")
        box((20 - width, root_y, 20 + width, root_y + 3), "black")
        for x in range(20 - width + 1, 20 + width, 4):
            d.ellipse((x, root_y - 2, x + 3, root_y + 1), fill="#3D496E", outline="#8C82AC")
        d.arc((22 - width, top + 1, 18 + width, root_y), 190, 265, fill="#85AEC7")
        poly([(20, top + 4), (23, top + 7), (20, top + 9), (17, top + 7)], "#8674A5")
        if hard:
            for x, offset in ((4, 0), (35, 4)):
                y = 14 + (phase + offset) % 8
                line([(x, y), (x - 1, y + 2), (x + 2, y + 3), (x, y + 5)], "#7CB9D6")
                d.point((x + 2, y - 1), fill="#D3D3A1")
    elif character == "cinder":
        # Side-view winged dragon: snout, horns, curling tail and a fire jet.
        dy = -round(q * (3 if hard else 1)) if working else round(math.sin(angle))
        tail = round(math.sin(angle) * (3 if working else 1))
        poly([(17, 22 + dy), (10, 27 + dy), (4, 25 + tail), (2, 20 + tail),
              (5, 17 + tail), (4, 22 + tail), (10, 24 + dy), (15, 19 + dy)], "#633A3B", "#A6674E")
        wing_tip = round(3 + q * 9) if working else 11
        poly([(18, 20 + dy), (8, wing_tip), (3, wing_tip + 5), (9, wing_tip + 8),
              (10, 23 + dy), (18, 24 + dy)], "#453452", "#946785")
        line([(8, wing_tip), (14, 20 + dy), (5, wing_tip + 5)], "#674B6C")
        d.ellipse((13, 16 + dy, 24, 28 + dy), fill="#673E3B", outline="#AE704D")
        poly([(19, 20 + dy), (20, 12 + dy), (24, 8 + dy), (28, 10 + dy),
              (28, 13 + dy), (31, 14 + dy), (30, 18 + dy), (25, 18 + dy), (24, 25 + dy)], "#86503C", "#BD8559")
        poly([(22, 10 + dy), (21, 5 + dy), (25, 9 + dy)], "#A19B82")
        box((25, 11 + dy, 27, 12 + dy), "#171922")
        if not blink:
            d.point((26, 11 + dy), fill="#E5CB79")
        line([(28, 16 + dy), (30, 16 + dy)], "#241C26")
        for x in (16, 23):
            line([(x, 26 + dy), (x - 1, 29), (x + 2, 29)], "#A87954", 2)
        if hard:
            end_y = 12 + phase % 3 + dy
            poly([(30, 15 + dy), (34, 12 + dy), (35, 14 + dy), (38, end_y),
                  (36, 18 + dy), (32, 17 + dy)], "#A44B2D")
            line([(31, 15 + dy), (34, 15 + dy), (37, end_y + 1)], "#E49B43")
            d.point((38, end_y), fill="#F4D47E")
        elif working:
            d.point((33, 12 + (phase % 3)), fill="#8F684E")
    elif character == "cubone":
        # Skull mask with horns, left-facing muzzle, eye socket and a real bone.
        dy = -round(q * (2 if hard else 1)) if working else round(math.sin(angle))
        poly([(25, 25 + dy), (32, 25 + dy), (34, 21 + dy), (34, 27 + dy), (25, 28 + dy)], "#72533D")
        d.ellipse((14, 17 + dy, 28, 29 + dy), fill="#76583C", outline="#A6895A")
        d.ellipse((17, 20 + dy, 25, 27 + dy), fill="#AD9B69")
        for x in (15, 25):
            box((x - 1, 27 + dy, x + 3, 29 + dy), "#8C704D")
            d.point((x, 29 + dy), fill="#B4B4A3")
        poly([(12, 9 + dy), (11, 3 + dy), (17, 6 + dy), (23, 5 + dy),
              (28, 2 + dy), (27, 9 + dy), (29, 14 + dy), (24, 18 + dy),
              (16, 18 + dy), (12, 21 + dy), (7, 18 + dy), (8, 14 + dy)], "#969B8F", "#B8BAA5")
        poly([(13, 9 + dy), (17, 6 + dy), (23, 6 + dy), (19, 8 + dy)], "#C4C6AB")
        poly([(21, 9 + dy), (24, 8 + dy), (26, 10 + dy), (25, 15 + dy), (21, 16 + dy), (20, 13 + dy)], "#272A2D")
        if not blink:
            line([(23, 11 + dy), (23, 14 + dy)], "#B7A570")
            d.point((24, 11 + dy), fill="#DDD9BC")
        poly([(10, 15 + dy), (12, 17 + dy), (9, 18 + dy)], "#373B39")
        line([(26, 14 + dy), (28, 15 + dy)], "#5C6865")
        hand = (25 + round(7 * q), 22 + dy - round(6 * q)) if working else (25, 22 + dy)
        line([(25, 22 + dy), hand], "#A18455", 2)
        a = .3 - 1.9 * q if working else .65 + math.sin(angle) * .12
        length = 10 if working else 9
        end = (round(hand[0] + math.cos(a) * length), round(hand[1] + math.sin(a) * length))
        line([hand, end], "#B6B9A0", 3)
        for x, y in (hand, end):
            d.ellipse((x - 2, y - 1, x + 1, y + 2), fill="#BFC2A8")
        if hard and q > .8:
            for x, y in ((5, 6 + phase % 2), (34, 5 + phase % 3)):
                d.point((x, y), fill="#C9A46A")
    elif character == "treecko":
        # Tall gecko, yellow slit eyes, red belly and a thick twin-lobed tail.
        dx = round(math.sin(angle) * 2) if hard else 0
        dy = -round(q * (5 if hard else 3)) if working else round(math.sin(angle))

        def p(points: Points, color: Color, outline: Color | None=None) -> None:
            poly([(x + dx, y + dy) for x, y in points], color, outline)

        sway = round(math.sin(angle) * (3 if working else 1))
        p([(21, 22), (27, 18 + sway), (34, 19 + sway), (35, 22 + sway),
           (32, 24 + sway), (36, 25 + sway), (32, 28 + sway), (25, 28 + sway), (20, 25)], "#426A43", "#7EAA62")
        p([(15, 17), (23, 17), (25, 25), (21, 28), (14, 26)], "#598B43", "#91B964")
        p([(16, 19), (21, 19), (22, 25), (18, 26), (16, 24)], "#A55469")
        p([(11, 15), (10, 8), (12, 7), (16, 10), (18, 6), (21, 5),
           (25, 8), (26, 15), (22, 19), (15, 18)], "#78A950", "#A9CD71")
        line([(17 + dx, 9 + dy), (17 + dx, 14 + dy)], "#426B3C")
        p([(21, 10), (24, 9), (25, 11), (25, 14), (22, 16), (20, 13)], "#D3BC5C")
        if not blink:
            line([(23 + dx, 10 + dy), (23 + dx, 14 + dy)], "#171F26")
            d.point((24 + dx, 11 + dy), fill="#F4E4A8")
        p([(11, 10), (12, 9), (13, 11), (12, 14), (11, 13)], "#C7B659")
        line([(14 + dx, 16 + dy), (19 + dx, 17 + dy), (22 + dx, 16 + dy)], "#39633C")
        arm_y = 18 - round(q * (9 if working else 0))
        for shoulder, hand_x in ((15, 6), (23, 31)):
            line([(shoulder + dx, 20 + dy), (hand_x + dx, arm_y + dy)], "#8CB664", 2)
            for finger in (-1, 0, 1):
                x, y = hand_x + dx + finger * 2, arm_y + dy - abs(finger)
                d.ellipse((x, y, x + 1, y + 1), fill="#B1CF80")
        for x, direction in ((16, -1), (23, 1)):
            line([(x + dx, 25 + dy), (x + dx + direction * 2, 29 + dy)], "#80A85B", 2)
            for toe in range(3):
                xx = x + dx + direction * 2 + toe - 1
                d.point((xx, 30 + dy), fill="#B1CF80")
        if hard and q < .3:
            for x in (5, 9, 31, 35):
                d.point((x, 30 - phase % 3), fill="#638249")
    else:
        # Torchic: three-pronged yellow crest, orange head, neck feathers and toes.
        dy = -round(q * (5 if hard else 3)) if working else -round((math.sin(angle) + 1) / 2)
        top = 12 + dy
        d.ellipse((13, top + 7, 27, top + 16), fill="#A7662F", outline="#CD893C")
        flap = round(q * (7 if hard else 4)) if working else 0
        for side in (-1, 1):
            x = 20 + side * 6
            points = ([(x, top + 9), (20 + side * 14, top + 10 - flap),
                       (20 + side * 12, top + 14 - flap), (x, top + 14)] if working else
                      [(x, top + 9), (20 + side * 9, top + 11),
                       (20 + side * 8, top + 15), (x, top + 13)])
            poly(points, "#AD7E32", "#D8AD50")
        poly([(17, top + 2), (16, top - 3), (19, top - 1), (23, top - 7),
              (23, top - 2), (28, top - 4), (25, top + 3)], "#B89942", "#E3C567")
        d.ellipse((10, top, 29, top + 12), fill="#B87332", outline="#DF9E4B")
        d.arc((13, top + 1, 25, top + 9), 205, 270, fill="#E5B268")
        for x in (15, 24):
            d.ellipse((x - 1, top + 4, x + 1, top + 7), fill="#212131")
            if not blink:
                d.point((x, top + 4), fill="#F2E7C9")
                d.point((x, top + 7), fill="#5D5271")
        poly([(17, top + 7), (20, top + 6), (23, top + 8), (20, top + 9), (17, top + 8)], "#D5B45F")
        poly([(14, top + 10), (17, top + 11), (18, top + 10), (21, top + 11),
              (25, top + 10), (27, top + 14), (23, top + 13), (23, top + 15),
              (20, top + 13), (18, top + 15), (17, top + 13), (13, top + 14)], "#C6A34A")
        for x in (16, 23):
            foot_y = 30 + dy
            line([(x, top + 16), (x, foot_y)], "#BBA05B")
            line([(x - 2, foot_y + 1), (x, foot_y), (x + 2, foot_y + 1)], "#D7BF72")
        if hard:
            for x, offset in ((4, 0), (34, 5), (31, 2)):
                y = 19 - (phase + offset) % 12
                d.point((x, y), fill="#D98336")
                if phase % 3 == 0:
                    d.point((x, y + 1), fill="#F0C86E")
    return image


def export_collection(collection: str, directory: Pathish) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cast = CASTS[collection]
    native = Image.new("RGB", (640, 288), "black")
    labelled = Image.new("RGB", (1416, 744), "#0C0C0C")
    labels = ImageDraw.Draw(labelled)
    for frame in range(FRAMES):
        labels.text((128 + frame * 80, 5), str(frame), fill="#B4B4B4")
    previews = []
    for frame in range(FRAMES):
        sheet = Image.new("RGB", (744, 616), "#0C0C0C")
        caption = ImageDraw.Draw(sheet)
        caption.text((8, 6), collection.upper() + " / POSE COMPARISON AT 8 FPS", fill="#B4B4B4")
        for col, mood in enumerate(MOODS):
            caption.text((112 + col * 208, 28), mood.upper(), fill="#B4B4B4")
        for row, character in enumerate(cast):
            y = 48 + row * 188
            caption.text((8, y + 70), character.upper(), fill=cast[character])
            for col, mood in enumerate(MOODS):
                image = quantized(sprite(character, frame, mood)).crop((0, 0, 40, 32))
                sheet.paste(image.resize((200, 160), Image.Resampling.NEAREST), (112 + col * 208, y))
        previews.append(sheet)
    previews[8].save(directory / "preview.png")
    previews[0].save(directory / "preview.gif", save_all=True, append_images=previews[1:],
                     duration=125, loop=0, disposal=2, optimize=False)
    row = 0
    for character in cast:
        for mood in MOODS:
            frames = []
            for frame in range(FRAMES):
                image = quantized(sprite(character, frame, mood)).crop((0, 0, 40, 32))
                native.paste(image, (frame * 40, row * 32))
                labelled.paste(image.resize((80, 64), Image.Resampling.NEAREST), (128 + frame * 80, 24 + row * 80))
                frames.append(image)
            duration = round(1000 / {"idle": 3, "busy": 8, "hard": 12}[mood])
            frames[0].save(directory / f"{character}-{mood}.gif", save_all=True,
                           append_images=frames[1:], duration=duration, loop=0, disposal=2, optimize=False)
            labels.text((8, 36 + row * 80), character.upper(), fill=cast[character])
            labels.text((8, 52 + row * 80), mood.upper(), fill="#B4B4B4")
            row += 1
    native.save(directory / "sprite-sheet.png")
    labelled.save(directory / "sprite-sheet-labelled.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", choices=(*CASTS, "all"), default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/ui/companions"))
    args = parser.parse_args()
    for name in CASTS if args.collection == "all" else (args.collection,):
        export_collection(name, args.output_dir / name)


if __name__ == "__main__":
    main()
