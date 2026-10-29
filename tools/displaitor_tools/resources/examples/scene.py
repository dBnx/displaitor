"""My display scene. Arrows move the light; A changes its colour; B exits."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from PIL import Image, ImageDraw
from displaitor_tools import ButtonState, HEIGHT, WIDTH, run_scene


@dataclass
class Scene:
    x: int = WIDTH // 2
    y: int = HEIGHT // 2
    color: int = 0

    def render(self, elapsed: float) -> Image.Image:
        image = Image.new('RGB', (WIDTH, HEIGHT), 'black')
        draw = ImageDraw.Draw(image)
        for x, y in ((3, 5), (13, 24), (44, 7), (58, 23)):
            draw.point((x, y), fill='#526373')
        radius = 2 + round((math.sin(elapsed * 2) + 1) / 2)
        color = ('#90D5CF', '#F7C782', '#D3B6E3')[self.color]
        draw.ellipse((self.x - radius, self.y - radius, self.x + radius, self.y + radius), fill=color)
        return image

    def on_buttons(self, state: ButtonState) -> None:
        for event in state.events:
            if not event.active:
                continue
            self.x = min(WIDTH - 4, max(3, self.x + 2 * (('right' in event.pressed) - ('left' in event.pressed))))
            self.y = min(HEIGHT - 4, max(3, self.y + 2 * (('down' in event.pressed) - ('up' in event.pressed))))
            if 'a' in event.pressed:
                self.color = (self.color + 1) % 3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='auto')
    parser.add_argument('--gamma', type=float)
    parser.add_argument('--fps', type=float, default=12)
    parser.add_argument('--frames', type=int)
    args = parser.parse_args()
    scene = Scene()
    try:
        run_scene(scene.render, on_buttons=scene.on_buttons, port=args.port,
                  gamma=args.gamma, fps=args.fps, frames=args.frames)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
