#!/usr/bin/env python3
"""Export stats/pet GIFs and a sound video, using real Rust-rendered text boxes.

Offline only: connects to temporary loopback simulators, never to a board.
Provide WAVs exported with tools/run.py audio synth to audition the exact
compressed firmware assets. ffmpeg is required for the MP4.
"""
from __future__ import annotations

from collections.abc import Sequence
from ..models import Pathish

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

from PIL import Image, ImageDraw

from ..canvas import Client
from ..companions.designs import ACTION_SECONDS, preview_frame, sprite
from ..companions.stats import PAGES
from ..metrics import GIB, Sample
from ..apps.companion import Companion, Workload

PETS = ('torchic', 'eevee', 'treecko')
FPS = 20


def capture(binary: Path, directory: Path, pet: str, page: str) -> tuple[tuple[str, str], Image.Image]:
    snapshot = directory / (pet + '-' + page + '.ppm')
    process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                '--frames', '150', '--snapshot', str(snapshot)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        if not line.startswith('Canvas listening on 127.0.0.1:'):
            raise RuntimeError('Simulator did not open Canvas: ' + line)
        with Client('tcp://' + line.split()[-1]) as client:
            reading = Sample(7, 64, 35, datetime.now(), vram_used=round(3.2 * GIB), demo=True)
            Companion(pet, page).install(client, Workload().update(reading))
        stdout, stderr = process.communicate(timeout=8)
        if process.returncode:
            raise RuntimeError(stdout + stderr)
        with Image.open(snapshot) as image:
            return (pet, page), image.convert('RGB')
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=3)


def actor(pet: str, page: str, hud: Image.Image, t: float, action_start: float | None=None) -> Image.Image:
    progress = None
    if action_start is not None and action_start <= t < action_start + ACTION_SECONDS:
        progress = (t - action_start) / ACTION_SECONDS
    return preview_frame(sprite(pet, int(t * 8) % 16, 'busy', action=progress), hud, pet, page)


def gif(path: Pathish, frames: Sequence[Image.Image], duration: int) -> None:
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=duration,
                   loop=0, disposal=2, optimize=False)


def export(output: Path, audio_dir: Path, binary: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='displaitor-previews-') as temporary_name:
        temporary = Path(temporary_name)
        jobs = [(pet, page) for pet in PETS for page in PAGES]
        with ThreadPoolExecutor(max_workers=3) as pool:
            captured = dict(pool.map(lambda job: capture(binary, temporary, *job), jobs))
        gallery = Image.new('RGB', (1360, 510), '#0C0C0C')
        draw = ImageDraw.Draw(gallery)
        draw.text((16, 10), 'UP / DOWN: CPU > RAM > GPU > VRAM > ALL     |     OFFLINE PREVIEW - SAMPLE VALUES', fill='#B4B4B4')
        for row, pet in enumerate(PETS):
            for col, page in enumerate(PAGES):
                x, y = 16 + col * 268, 36 + row * 156
                draw.text((x, y), pet.upper() + ' / ' + page.upper(), fill='#B4B4B4')
                gallery.paste(captured[pet, page].resize((256, 128), Image.Resampling.NEAREST), (x, y + 18))
        gallery.save(output / 'stats-gallery.png')
        cycle = []
        for page in PAGES:
            for step in range(20):
                t = step / 8
                image = Image.new('RGB', (408, 240), '#0C0C0C')
                draw = ImageDraw.Draw(image)
                draw.text((12, 8), 'TORCHIC / ' + page.upper() + '     UP / DOWN', fill='#B4B4B4')
                draw.text((12, 225), 'Offline preview - sample readings', fill='#909090')
                image.paste(actor('torchic', page, captured['torchic', page], t).resize(
                    (384, 192), Image.Resampling.NEAREST), (12, 26))
                cycle.append(image)
        gif(output / 'stats-cycle.gif', cycle, 125)
        actions = []
        for step in range(76):
            t = step / FPS
            image = Image.new('RGB', (1192, 240), '#0C0C0C')
            draw = ImageDraw.Draw(image)
            for col, pet in enumerate(PETS):
                x = 12 + col * 392
                draw.text((x, 8), pet.upper() + (' / A: PLAY + CRY' if .55 <= t < 2.35 else ' / READY'), fill='#B4B4B4')
                image.paste(actor(pet, 'cpu', captured[pet, 'cpu'], t, .55).resize(
                    (384, 192), Image.Resampling.NEAREST), (x, 26))
            draw.text((12, 225), 'Offline preview - sample readings. GIF is silent; MP4 includes the three cries separately.', fill='#909090')
            actions.append(image)
        gif(output / 'pet-actions.gif', actions, round(1000 / FPS))
        # Three separate four-second scenes keep the cries clearly audible.
        combined = [0] * (12 * 16384)
        for index, pet in enumerate(PETS):
            source = audio_dir / ('cry_' + pet + '.wav')
            with wave.open(str(source), 'rb') as input_wave:
                if (input_wave.getnchannels(), input_wave.getsampwidth(), input_wave.getframerate()) != (1, 2, 16384):
                    raise ValueError('Expected mono 16-bit 16384-Hz WAV: ' + str(source))
                raw = input_wave.readframes(input_wave.getnframes())
            samples = struct.unpack(f'<{len(raw)//2}h', raw)
            offset = round((index * 4 + .55) * 16384)
            combined[offset:offset + len(samples)] = samples
            shutil.copyfile(source, output / source.name)
            page = ('cpu', 'all', 'vram')[index]
            for step in range(4 * FPS):
                t = step / FPS
                image = Image.new('RGB', (800, 448), '#0C0C0C')
                draw = ImageDraw.Draw(image)
                draw.text((16, 10), pet.upper() + ' / ' + page.upper() + ' / ORIGINAL GBA-INSPIRED CRY', fill='#B4B4B4')
                image.paste(actor(pet, page, captured[pet, page], t, .55).resize(
                    (768, 384), Image.Resampling.NEAREST), (16, 30))
                draw.text((16, 429), 'A: PLAY + CRY' if .55 <= t < 2.35 else 'Offline preview - sample readings', fill='#909090')
                image.save(temporary / f'frame-{index * 80 + step:04}.png')
        with wave.open(str(temporary / 'sound.wav'), 'wb') as output_wave:
            output_wave.setparams((1, 2, 16384, 0, 'NONE', 'not compressed'))
            output_wave.writeframes(struct.pack(f'<{len(combined)}h', *combined))
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-framerate', str(FPS),
                        '-i', str(temporary / 'frame-%04d.png'), '-i', str(temporary / 'sound.wav'),
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                        str(output / 'pet-cries.mp4')], check=True)


def main() -> None:
    from ..paths import checkout_root
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--audio-dir', type=Path, required=True)
    parser.add_argument('--simulator', type=Path, default=None)
    args = parser.parse_args()
    binary = args.simulator or checkout_root() / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
    export(args.output_dir, args.audio_dir, binary)


if __name__ == '__main__':
    main()
