"""Offline sample weather art, captured with real Rust Canvas text."""

from __future__ import annotations

from ..models import Pathish
import argparse
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw

from ..canvas import Client, image_frame
from ..paths import checkout_root
from ..weather.icons import ANIMATION_FPS, EXAMPLES, FRAMES, condition, sprite
from ..weather.manual import Weather
from ..weather.data import State, parse
from ..weather.examples import payload
from ..weather.views import Display


def animated_frames(still: Image.Image, status: str) -> list[Image.Image]:
    """Keep Rust-rendered text fixed while the RGB565 artwork animates."""
    frames = []
    for phase in range(FRAMES):
        raw = image_frame(sprite(status, phase))
        quantized = Image.new('RGB', (64, 32))
        colors = []
        for offset in range(0, len(raw), 2):
            value = int.from_bytes(raw[offset:offset + 2], 'little')
            colors.append(((((value >> 11) & 31) * 255 + 15) // 31,
                           (((value >> 5) & 63) * 255 + 31) // 63, ((value & 31) * 255 + 15) // 31))
        quantized.putdata(colors)
        image = still.copy()
        image.paste(quantized.crop((40, 0, 64, 24)), (40, 0))
        frames.append(image)
    return frames


def previews(directory: Pathish) -> None:
    """Export sample GIFs with text from the actual Rust Canvas renderer."""
    root = checkout_root()
    binary = root / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (1024, 304), "#0C0C0C")
    labels = ImageDraw.Draw(sheet)
    for index, status in enumerate(EXAMPLES):
        kind = condition(status)
        snapshot = directory / (kind + ".ppm")
        process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                    "--frames", "75", "--snapshot", str(snapshot)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout is not None
            line = process.stdout.readline().strip()
            if not line.startswith("Canvas listening on 127.0.0.1:"):
                raise RuntimeError("simulator did not open Canvas: " + line)
            with Client("tcp://" + line.split()[-1]) as client:
                Weather(status=status).install(client)
            stdout, stderr = process.communicate(timeout=6)
            if process.returncode:
                raise RuntimeError(stdout + stderr)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=3)
        with Image.open(snapshot) as source:
            still = source.convert("RGB")
        snapshot.unlink()
        frames = animated_frames(still, status)
        frames[0].save(directory / (kind + ".png"))
        frames[0].save(directory / (kind + ".gif"), save_all=True, append_images=frames[1:],
                       duration=1000 // ANIMATION_FPS, loop=0, disposal=2, optimize=False)
        x, y = index % 4 * 256, index // 4 * 152
        labels.text((x + 8, y + 4), status, fill="#B8C8C0")
        sheet.paste(still.resize((256, 128), Image.Resampling.NEAREST), (x, y + 24))
    sheet.save(directory / "conditions.png")


def view_previews(directory: Pathish) -> None:
    """Capture all pages with explicit sample data, without HTTP or hardware."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    binary = checkout_root() / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
    if not binary.exists():
        raise RuntimeError('build the simulator first: cargo build -p simulaitor --no-default-features')
    galleries = [Image.new('RGB', (1184, 448), '#0C0C0C') for _ in range(FRAMES)]
    for index, (page, day, details, label) in enumerate((
        ('now', 0, 0, 'CURRENT - SAMPLE'), ('forecast', 0, 0, 'FORECAST - RAIN'),
        ('forecast', 1, 0, 'FORECAST - SNOW'), ('forecast', 2, 0, 'FORECAST - SUN'),
        ('info', 0, 0, 'OVERVIEW - RAIN / UV / HUMIDITY'), ('info', 0, 1, 'OVERVIEW - FEELS LIKE / WIND'),
    )):
        name = f'{page}-{day if page == "forecast" else details}'
        snapshot = directory / (name + '.ppm')
        scene = Display(page)
        scene.receive(State(parse(payload()), 'DEMO'))
        scene.day_index, scene.details = day, details
        process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                    '--frames', '130', '--snapshot', str(snapshot)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout is not None
            line = process.stdout.readline().strip()
            if not line.startswith('Canvas listening on 127.0.0.1:'):
                raise RuntimeError('simulator did not open Canvas: ' + line)
            with Client('tcp://' + line.split()[-1]) as client:
                scene.install(client)
            stdout, stderr = process.communicate(timeout=8)
            if process.returncode:
                raise RuntimeError(stdout + stderr)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=3)
        with Image.open(snapshot) as source:
            still = source.convert('RGB')
        snapshot.unlink()
        frames = animated_frames(still, scene.content()[1])
        still.save(directory / (name + '.png'))
        enlarged = [frame.resize((384, 192), Image.Resampling.NEAREST) for frame in frames]
        enlarged[0].save(directory / (name + '.gif'), save_all=True, append_images=enlarged[1:],
                         duration=1000 // ANIMATION_FPS, loop=0, disposal=2, optimize=False)
        x, y = 8 + index % 3 * 392, index // 3 * 224
        for gallery, frame in zip(galleries, enlarged, strict=True):
            ImageDraw.Draw(gallery).text((x, y + 4), label, fill='#B8C8C0')
            gallery.paste(frame, (x, y + 24))
    galleries[0].save(directory / 'views.png')
    galleries[0].save(directory / 'views.gif', save_all=True, append_images=galleries[1:],
                      duration=1000 // ANIMATION_FPS, loop=0, disposal=2, optimize=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    view_previews(args.output_dir)
