"""Offline companion gallery and native sprite-sheet exports."""

from __future__ import annotations

from ..models import Pathish
import argparse
import math
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw

from ..canvas import Client, image_frame
from ..companions.designs import DESIGNS, FRAMES, layout, preview_frame, quantized, sprite
from ..paths import checkout_root


def sprite_sheets(directory: Pathish) -> None:
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


def previews(directory: Pathish) -> None:
    """Use the real Rust renderer for text, then animate the sprite region."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    binary = checkout_root() / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
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
            assert process.stdout is not None
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output-dir', '--preview-dir', dest='preview_dir', help='gallery and animated previews using the Rust simulator')
    mode.add_argument('--sprite-sheet-dir', help='sprite sheets only; no simulator required')
    args = parser.parse_args()
    if args.sprite_sheet_dir:
        sprite_sheets(args.sprite_sheet_dir)
    else:
        previews(args.preview_dir)
