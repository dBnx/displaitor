#!/usr/bin/env python3
"""Pixel Companion design studies: actual 64x32 sprites and Canvas text.

Preview all designs locally, or stream live activity through the Canvas interface.
Exported previews use labelled fixtures; device operation defaults to real readings.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw

try:
    from .canvas import Client, image_frame
    from .companion_pokemon import COLORS as POKEMON, ACTION_SECONDS, sprite as pokemon_sprite
except ImportError:
    from canvas import Client, image_frame
    from companion_pokemon import COLORS as POKEMON, ACTION_SECONDS, sprite as pokemon_sprite

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = {"orbit": "#79ECF0", "ember": "#FFAC72", "sprout": "#96E8A0", **POKEMON}
FRAMES = 16


def layout(design):
    color = DESIGNS[design]
    # Long names reserve a blank cell, clear of the panel's edge.
    # Numeric/status slots retain exactly the same positions and widths.
    name_width = (len(design) + 1) * 4 if len(design) > 6 else 24
    return {"text": {
        "name": dict(x=64 - name_width, y=0, width=name_width, height=6, font="small", color=color, text=design.upper()),
        "metric": dict(x=40, y=8, width=24, height=10, font="medium", align="right", color="#FFFFFF", text="42%"),
        "mood": dict(x=40, y=20, width=24, height=6, font="small", color=color, text="IDLE"),
        "demo": dict(x=40, y=26, width=24, height=6, font="small", color="#505860", text="DEMO"),
    }}


def sprite(design, frame, activity="idle", *, hop=0, action=None):
    """Whole-pixel art; the right 24 columns stay black for retained text."""
    if design not in DESIGNS:
        raise ValueError("unknown companion design")
    if activity not in ("idle", "busy", "hard", "unknown"):
        raise ValueError("unknown companion activity")
    if design in POKEMON:
        return pokemon_sprite(design, frame, activity, hop=hop, action=action)
    image = Image.new("RGB", (64, 32), "black")
    draw = ImageDraw.Draw(image)
    phase = frame % FRAMES
    bob = round(math.sin(phase * math.tau / FRAMES) * (2 if activity == "hard" else 1))
    actor_y = bob - hop
    blink = phase in (6, 7)

    def polygon(points, fill, outline=None):
        draw.polygon([(x, y + actor_y) for x, y in points], fill=fill, outline=outline)

    def line(points, fill):
        draw.line([(x, y + actor_y) for x, y in points], fill=fill)

    def box(bounds, fill):
        x0, y0, x1, y1 = bounds
        draw.rectangle((x0, y0 + actor_y, x1, y1 + actor_y), fill=fill)

    # Sparse stars and a dim shadow provide depth without a lit panel behind text.
    for x, y in ((3, 4), (34, 7), (5, 23), (35, 25)):
        draw.point((x, y), fill="#17252D")
    draw.ellipse((11 - bob, 29, 29 + bob, 30), fill="#101C24")

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
                box((x + 1, 13, x + 2, 13), "#E8FFFF")
        line([(18, 18), (20, 19), (22, 18)], "#3B8BA3")
        box((18, 23, 22, 23), "#58BDDC")
        box((13, 26, 16, 27), "#365477")
        box((25, 26, 28, 27), "#365477")
    elif design == "ember":
        # Keep the small facial/ear/tail-tip accents bright against dim fur.
        polygon([(13, 25), (7, 27), (3, 23), (4, 17), (7, 14), (8, 21), (14, 22)],
                "#42211C", "#79432F")
        polygon([(4, 17), (7, 14), (8, 19), (6, 20)], "#DDAF75")
        polygon([(10, 12), (10, 5), (16, 9), (24, 9), (30, 4), (30, 14),
                 (29, 22), (24, 26), (15, 26), (11, 22)], "#25161B", "#59312A")
        polygon([(11, 7), (14, 9), (11, 11)], "#F8A369")
        polygon([(28, 7), (28, 12), (25, 10)], "#F8A369")
        polygon([(13, 20), (17, 18), (20, 20), (24, 18), (28, 20), (24, 24), (17, 24)], "#452F2A")
        for x in (14, 24):
            box((x, 15 if blink else 13, x + 2, 15), "#FFCB88")
            if not blink:
                box((x + 1, 14, x + 1, 15), "#FFECC0")
        box((19, 18, 21, 18), "#F29C83")
        line([(20, 19), (20, 21), (18, 21)], "#140D13")
        box((15, 27, 17, 27), "#C47A55")
        box((24, 27, 26, 27), "#C47A55")
        for offset in range(3):
            draw.point((3 + offset * 3, 11 - (phase + offset * 4) % 10),
                       fill=("#7D3F37", "#C87548", "#F4BF75")[offset])
    else:
        # Dim the broad leaves/body; retain eyes, pink cheeks and fine accents.
        line([(20, 12), (20, 6)], "#4A9C6F")
        polygon([(20, 8), (14, 7), (11, 3), (16, 3), (20, 6)], "#1C4033", "#4D7D59")
        polygon([(20, 7), (22, 2), (28, 1), (26, 5), (22, 8)], "#2B4B33", "#708F61")
        polygon([(11, 16), (15, 12), (25, 12), (30, 16), (31, 22), (27, 26),
                 (14, 26), (10, 22)], "#101F1A", "#2F5746")
        line([(13, 16), (16, 13), (24, 13)], "#7BB78A")
        polygon([(28, 18), (29, 22), (26, 24), (15, 24), (13, 23), (15, 25), (27, 25), (30, 22)], "#192E23")
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
            line([(12, 21), (9, 21 - effort)], "#79432F")
            line([(28, 21), (32, 21 + effort)], "#79432F")
        else:
            # Leaves open and close like arms doing jumping jacks.
            box((10, 0, 29, 11), "black")
            line([(20, 12), (20, 6)], "#4A9C6F")
            leaf_y = 5 + effort
            polygon([(20, 8), (14, leaf_y + 2), (10, leaf_y), (15, leaf_y - 1)],
                    "#1C4033", "#4D7D59")
            polygon([(20, 8), (25, leaf_y - 1), (30, leaf_y), (26, leaf_y + 2)],
                    "#2B4B33", "#708F61")
            box((13, 26, 30, 28), "black")
            for x, direction in ((16, -1), (26, 1)):
                line([(x, 25), (x + direction * abs(effort), 28)], "#67AC7E")
        for x in (3, 7, 32):
            draw.point(((x + phase) % 37 + 1, 31), fill="#20303B")
        if activity == "hard":
            drop_y = 7 + phase % 6
            draw.line((33, drop_y, 33, drop_y + 1), fill="#55B7DE")
    return image


def quantized(image):
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


def preview_frame(image, rendered, design):
    """Retain each real text box, including names wider than the right HUD."""
    image = quantized(image)
    for slot in layout(design)["text"].values():
        x, y = slot["x"], slot["y"]
        area = (x, y, x + slot["width"], y + slot["height"])
        image.paste(rendered.crop(area), (x, y))
    return image


def sprite_sheets(directory):
    """All native 40x32 character frames: 16 columns, three rows per pet."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    raw = Image.new("RGB", (40 * FRAMES, 32 * len(DESIGNS) * 3), "black")
    labelled = Image.new("RGB", (1416, 24 + len(DESIGNS) * 3 * 80), "#0C0C0C")
    labels = ImageDraw.Draw(labelled)
    for frame in range(FRAMES):
        labels.text((128 + frame * 80, 5), str(frame), fill="#B4B4B4")
    row = 0
    for design in DESIGNS:
        for activity in ("idle", "busy", "hard"):
            y = 24 + row * 80
            labels.text((8, y + 12), design.upper(), fill=DESIGNS[design])
            labels.text((8, y + 28), activity.upper(), fill="#B4B4B4")
            for frame in range(FRAMES):
                image = quantized(sprite(design, frame, activity)).crop((0, 0, 40, 32))
                raw.paste(image, (frame * 40, row * 32))
                labelled.paste(image.resize((80, 64), Image.Resampling.NEAREST),
                               (128 + frame * 80, y))
            row += 1
    raw.save(directory / "sprite-sheet.png")
    labelled.save(directory / "sprite-sheet-labelled.png")


def previews(directory):
    """Use the real Rust renderer for text, then animate the sprite region."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
    if not binary.exists():
        raise RuntimeError("build the simulator first: cargo build -p simulaitor --no-default-features")
    sheet = Image.new("RGB", (1184, math.ceil(len(DESIGNS) / 3) * 224), "#0C0C0C")
    labels = ImageDraw.Draw(sheet)
    for index, design in enumerate(DESIGNS):
        snapshot = directory / (design + ".ppm")
        process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                    "--frames", "130", "--snapshot", str(snapshot)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stdout.readline().strip()
            if not line.startswith("Canvas listening on 127.0.0.1:"):
                raise RuntimeError("simulator did not open its Canvas endpoint: " + line)
            with Client("tcp://" + line.split()[-1]) as client:
                client.layout(layout(design))
                client.frame(image_frame(sprite(design, 0)))
                client.show()
            stdout, stderr = process.communicate(timeout=8)
            if process.returncode:
                raise RuntimeError(stdout + stderr)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=3)
        with Image.open(snapshot) as image:
            still = image.convert("RGB")
        still.save(directory / (design + ".png"))
        animation = []
        for frame in range(FRAMES):
            animation.append(preview_frame(sprite(design, frame), still, design))
        animation[0].save(directory / (design + ".gif"), save_all=True, append_images=animation[1:],
                          duration=125, loop=0, disposal=2, optimize=False)
        x, y = 8 + index % 3 * 392, index // 3 * 224
        labels.text((x, y + 3), design.upper(), fill="#B4B4B4")
        sheet.paste(still.resize((384, 192), Image.Resampling.NEAREST), (x, y + 24))
        snapshot.unlink()
    sheet.save(directory / "designs.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=
        "Port mode also accepts pixel_companion.py options, including --gpu, --load and --demo-load.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview-dir", help="export all designs locally using the Rust simulator")
    mode.add_argument("--sprite-sheet-dir", help="export all character frames locally; no simulator or device")
    mode.add_argument("--port", help="auto (native USB only), serial device, or tcp://127.0.0.1:7777")
    parser.add_argument("--design", choices=DESIGNS, default="orbit")
    parser.add_argument("--fps", type=float, default=8)
    parser.add_argument("--frames", type=int, help="send a finite number of frames")
    args, extra = parser.parse_known_args()
    if args.port is None and extra:
        parser.error("unrecognized arguments: " + " ".join(extra))
    if not math.isfinite(args.fps) or not 0 < args.fps <= 20:
        parser.error("--fps must be in (0, 20]")
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive")
    try:
        if args.sprite_sheet_dir:
            sprite_sheets(args.sprite_sheet_dir)
            return
        if args.preview_dir:
            previews(args.preview_dir)
            return
        # Keep the legacy entry point, sharing the real sampler, transactions,
        # reconnect handling and labels with the normal live application.
        try:
            from .pixel_companion import main as live_main
        except ImportError:
            from pixel_companion import main as live_main
        live_main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"companion_designs: {error}\n")


if __name__ == "__main__":
    main()
