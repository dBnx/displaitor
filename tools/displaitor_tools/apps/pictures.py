"""Display pictures. Left/Right browses; A advances or pauses a timed slideshow; B exits."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import math
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps

from ..canvas import ButtonState, HEIGHT, WIDTH
from ..output import add_gamma_argument
from ..runner import run_scene

type Fit = Literal['auto', 'contain', 'cover']


def fit_image(image: Image.Image, fit: Fit = 'auto') -> Image.Image:
    """Orient a photo, flatten transparency onto black and fit logical RGB pixels.

    Auto preserves the entire image, allowing at most 10% aspect distortion
    for pictures already close to the panel's 2:1 shape. Others get black bars.
    Cover fills the panel by cropping centrally; contain never stretches.
    Gamma is applied later by the shared Canvas client, exactly once.
    """
    if fit not in ('auto', 'contain', 'cover'):
        raise ValueError('Unknown image fit')
    source = ImageOps.exif_transpose(image).convert('RGBA')
    size = (WIDTH, HEIGHT)
    aspect = (source.width / source.height) / (WIDTH / HEIGHT)
    if fit == 'cover':
        scaled = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    elif fit == 'auto' and 1 / 1.1 <= aspect <= 1.1:
        scaled = source.resize(size, Image.Resampling.LANCZOS)
    else:
        scaled = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
    frame = Image.new('RGBA', size, 'black')
    frame.alpha_composite(scaled, ((WIDTH - scaled.width) // 2, (HEIGHT - scaled.height) // 2))
    return frame.convert('RGB')


class Pictures:
    """Decode once before connecting; retain only small, panel-sized frames."""

    def __init__(self, paths: Sequence[Path], *, fit: Fit = 'auto', interval: float = 0) -> None:
        if not paths:
            raise ValueError('At least one picture is required')
        if not math.isfinite(interval) or interval < 0:
            raise ValueError('--interval must be finite and nonnegative')
        frames: list[Image.Image] = []
        for path in paths:
            try:
                with Image.open(path) as image:
                    frames.append(fit_image(image, fit))
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                raise ValueError(f'Cannot read picture {path}: {error}') from error
        self.frames = tuple(frames)
        self.index = 0
        self.interval = interval
        self.paused = False
        self.elapsed = 0.0
        self.next_change = interval

    def render(self, elapsed: float) -> Image.Image:
        self.elapsed = elapsed
        if self.interval and not self.paused and elapsed >= self.next_change:
            steps = int((elapsed - self.next_change) // self.interval) + 1
            self.index = (self.index + steps) % len(self.frames)
            self.next_change += steps * self.interval
        return self.frames[self.index]

    def on_buttons(self, state: ButtonState) -> None:
        if not state.active or state.lost:
            return
        for event in state.events:
            if not event.active or 'b' in event.pressed:
                return
            left, right = 'left' in event.pressed, 'right' in event.pressed
            if left != right:
                self.index = (self.index + (1 if right else -1)) % len(self.frames)
                self.next_change = self.elapsed + self.interval
            elif 'a' in event.pressed:
                if self.interval:
                    self.paused = not self.paused
                else:
                    self.index = (self.index + 1) % len(self.frames)
                self.next_change = self.elapsed + self.interval


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pictures', type=Path, nargs='+', help='image paths, in display order; animated files use their first frame')
    parser.add_argument('--port', default='auto', help='native USB auto, COM port or tcp://127.0.0.1:7777')
    parser.add_argument('--fit', choices=('auto', 'contain', 'cover'), default='auto',
                        help='auto: at most 10%% stretch, otherwise black bars; contain: no stretch; cover: crop to fill')
    parser.add_argument('--interval', type=float, default=0, help='slideshow seconds per picture; default 0 for manual browsing')
    parser.add_argument('--timeout', type=float, default=3)
    parser.add_argument('--frames', type=int, help='limit rendered updates for offline checks')
    parser.add_argument('--no-buttons', action='store_true')
    add_gamma_argument(parser)
    args = parser.parse_args()
    try:
        pictures = Pictures(args.pictures, fit=args.fit, interval=args.interval)
    except ValueError as error:
        parser.error(str(error))
    try:
        run_scene(pictures.render, on_buttons=None if args.no_buttons else pictures.on_buttons,
                  port=args.port, gamma=args.gamma, timeout=args.timeout, fps=10,
                  frames=args.frames, buttons=not args.no_buttons)
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'pictures: {error}\n')


if __name__ == '__main__':
    main()
