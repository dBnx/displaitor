"""Offline exports of actual live-companion activity and actions."""

from __future__ import annotations

from ..models import Pathish
from collections.abc import Sequence
import argparse
import math
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw

from ..apps.companion import Activity, Companion
from ..canvas import Client
from ..companions.designs import CUSTOM_ACTIONS, DESIGNS, FRAMES, IDLE_FRAMES, action_seconds, preview_frame, sprite
from ..paths import checkout_root


def previews(directory: Pathish, *, names: Sequence[str] | None = None) -> None:
    """Capture actual Canvas HUDs, then export activity and A-button animations."""
    selected = tuple(DESIGNS) if names is None else tuple(names)
    if not selected or any(name not in DESIGNS for name in selected):
        raise ValueError("Select at least one known pet")
    root = checkout_root()
    binary = root / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (8 + len(selected) * 392, 896), "#0C0C0C")
    labels = ImageDraw.Draw(sheet)
    idle_clips: dict[str, list[Image.Image]] = {}
    for row, (mood, load) in enumerate((("idle", 5), ("busy", 45), ("hard", 95), ("play", 5))):
        for col, design in enumerate(selected):
            snapshot = directory / (design + "-" + mood + ".ppm")
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "100", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                assert process.stdout is not None
                line = process.stdout.readline().strip()
                if not line.startswith("Canvas listening on 127.0.0.1:"):
                    raise RuntimeError("simulator did not open Canvas: " + line)
                with Client("tcp://" + line.split()[-1]) as client:
                    companion = Companion(design)
                    if mood == "play":
                        companion.action_remaining = action_seconds(design)
                        companion.action_pending = True
                    companion.install(client, Activity(load, "CPU", "idle" if mood == "play" else mood, True))
                stdout, stderr = process.communicate(timeout=8)
                if process.returncode:
                    raise RuntimeError(stdout + stderr)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)
            with Image.open(snapshot) as image:
                still = image.convert("RGB")
            snapshot.unlink()
            animation = []
            count = (IDLE_FRAMES if mood == 'idle' else
                     max(FRAMES, round(action_seconds(design) * 8) + 1) if mood == 'play' else FRAMES)
            for frame in range(count):
                progress = frame / (count - 1)
                action = progress if mood == "play" and design in CUSTOM_ACTIONS else None
                hop = round(abs(math.sin((.1 + progress * 1.2) * math.tau / .4)) * 3) if mood == "play" and design not in CUSTOM_ACTIONS else 0
                animation.append(preview_frame(
                    sprite(design, frame, "idle" if mood == "play" else mood,
                           hop=hop, action=action), still, design))
            speed = {"idle": 6, "busy": 8, "hard": 12,
                     "play": (count - 1) / (action_seconds(design))}[mood]
            animation[0].save(directory / (design + "-" + mood + ".gif"), save_all=True,
                              append_images=animation[1:], duration=round(1000 / speed),
                              loop=0, disposal=2, optimize=False)
            if mood == 'idle':
                idle_clips[design] = animation
            x, y = 8 + col * 392, row * 224
            labels.text((x, y + 3), design.upper() + " / " + mood.upper(), fill="#B4B4B4")
            sheet.paste(still.resize((384, 192), Image.Resampling.NEAREST), (x, y + 24))
    sheet.save(directory / "workload-designs.png")
    _idle_gallery(idle_clips, directory)


def _idle_gallery(clips: dict[str, list[Image.Image]], directory: Path) -> None:
    """Keep every idle gesture visible in one labelled, enlarged animation."""
    columns = 3 if len(clips) % 3 == 0 else min(2, len(clips))
    rows = math.ceil(len(clips) / columns)
    frames: list[Image.Image] = []
    for tick in range(IDLE_FRAMES):
        gallery = Image.new('RGB', (columns * 256, rows * 148), '#101010')
        labels = ImageDraw.Draw(gallery)
        for index, (name, animation) in enumerate(clips.items()):
            x, y = index % columns * 256, index // columns * 148
            gallery.paste(animation[tick].resize((256, 128), Image.Resampling.NEAREST), (x, y + 16))
            labels.text((x + 5, y + 3), name.upper() + ' / IDLE', fill='#CDCDCD')
        frames.append(gallery)
    frames[0].save(directory / 'idle-gallery.gif', save_all=True, append_images=frames[1:],
                   duration=170, loop=0, disposal=2, optimize=False)
    frames[24].save(directory / 'idle-gallery.png')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--design', action='append', choices=tuple(DESIGNS), help='repeat to export selected pets')
    args = parser.parse_args()
    previews(args.output_dir, names=args.design)
