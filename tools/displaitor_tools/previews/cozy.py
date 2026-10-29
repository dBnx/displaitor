"""Offline, RGB565-faithful seamless loops of full-panel cozy scenes."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw

from ..canvas import quantized_image as quantized
from ..models import Pathish
from ..scenes import LABELS, NAMES, PERIODS, render
from ..scenes.actions import DURATION

FPS = 10  # GIF supports centiseconds; this preserves exact loop durations.


def previews(directory: Pathish, *, scale: int = 8, names: Sequence[str] = NAMES) -> None:
    if not names or any(name not in NAMES for name in names):
        raise ValueError('Choose at least one known cozy scene')
    if not 1 <= scale <= 12:
        raise ValueError('Preview scale must be in 1..12')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (64 * scale, len(names) * (32 * scale + 26)), '#11151A')
    labels = ImageDraw.Draw(sheet)
    for index, name in enumerate(names):
        frames = [quantized(render(name, frame / FPS)) for frame in range(round(PERIODS[name] * FPS))]
        frames[0].save(directory / (name + '.png'))
        frames[0].save(directory / (name + '-native.gif'), save_all=True, append_images=frames[1:],
                       duration=1000 // FPS, loop=0, disposal=2, optimize=False)
        enlarged = [frame.resize((64 * scale, 32 * scale), Image.Resampling.NEAREST) for frame in frames]
        enlarged[0].save(directory / (name + '.gif'), save_all=True, append_images=enlarged[1:],
                         duration=1000 // FPS, loop=0, disposal=2, optimize=False)
        y = index * (32 * scale + 26)
        labels.text((8, y + 6), LABELS[name], fill='#B8C8C0')
        sheet.paste(enlarged[0], (0, y + 26))
    sheet.save(directory / 'scenes.png')


def action_previews(directory: Pathish, *, scale: int = 8, names: Sequence[str] = NAMES) -> None:
    """Show A reactions and clean return to ambient, using source RGB565 colours."""
    if not names or any(name not in NAMES for name in names) or not 1 <= scale <= 12:
        raise ValueError('Choose known scenes and a preview scale in 1..12')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (128 * scale, len(names) * (32 * scale + 26)), '#18212B')
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(names):
        for column, action in enumerate((None, 1.1)):
            image = quantized(render(name, 1.5, action=action)).resize((64 * scale, 32 * scale), Image.Resampling.NEAREST)
            y = index * (32 * scale + 26)
            sheet.paste(image, (column * 64 * scale, y + 26))
            draw.text((column * 64 * scale + 6, y + 6), LABELS[name] + (' / A' if column else ' / AMBIENT'), fill='#DFE5DE')
        frames = [quantized(render(name, 1.5 + tick / FPS,
                                  action=tick / FPS if tick / FPS < DURATION else None))
                  .resize((64 * scale, 32 * scale), Image.Resampling.NEAREST)
                  for tick in range(round((DURATION + 1.6) * FPS))]
        frames[0].save(directory / (name + '-action.gif'), save_all=True, append_images=frames[1:],
                       duration=1000 // FPS, loop=0, disposal=2, optimize=False)
    sheet.save(directory / 'actions.png')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--scale', type=int, default=8, choices=range(1, 13))
    parser.add_argument('--actions', action='store_true', help='preview A-button reactions instead of ambient loops')
    parser.add_argument('--scene', action='append', choices=NAMES, help='export selected scenes; repeat for multiple scenes')
    args = parser.parse_args()
    exporter = action_previews if args.actions else previews
    exporter(args.output_dir, scale=args.scale, names=args.scene or NAMES)
