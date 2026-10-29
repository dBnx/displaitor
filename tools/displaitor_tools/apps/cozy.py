"""Ten fullscreen cozy scenes. Left/Right: scene; A: special; Up/Down: pause/resume."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import sys
import time

from ..canvas import ButtonState, Client, image_frame, resolve_port
from ..scenes import NAMES, render
from ..scenes.actions import DURATION
from ..output import OutputGamma, add_gamma_argument


@dataclass(frozen=True)
class Settings:
    port: str = 'auto'
    scene: str = 'farm'
    fps: float = 12
    timeout: float = 3
    frames: int | None = None
    buttons: bool = True
    gamma: float | None = None

    def __post_init__(self) -> None:
        if self.gamma is not None:
            OutputGamma(self.gamma)
        if self.scene not in NAMES:
            raise ValueError('Unknown cozy scene')
        if not math.isfinite(self.fps) or not 0 < self.fps <= 20:
            raise ValueError('--fps must be in (0, 20]')
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('--timeout must be positive')
        if self.frames is not None and self.frames < 1:
            raise ValueError('--frames must be positive')


class Cozy:
    """Own a scene clock and one acknowledged frame; no animation queue."""

    def __init__(self, name: str = 'farm') -> None:
        self.index = NAMES.index(name)
        self.elapsed = 0.0
        self.paused = False
        self.action: float | None = None
        self.last: bytes | None = None

    @property
    def name(self) -> str:
        return NAMES[self.index]

    def buttons(self, state: ButtonState) -> None:
        if state.lost or not state.active:
            return
        for event in state.events:
            if not event.active:
                continue
            if 'b' in event.pressed:
                return
            left, right = 'left' in event.pressed, 'right' in event.pressed
            if left != right:
                self.index = (self.index + (1 if right else -1)) % len(NAMES)
                self.elapsed = 0
                self.action = None
                self.last = None
                continue
            up, down = 'up' in event.pressed, 'down' in event.pressed
            if up != down:
                self.paused = up
            if 'a' in event.pressed:
                self.action = 0.0
                self.last = None

    def install(self, client: Client) -> None:
        self.last = None
        try:
            with client.transaction():
                client.layout({'text': {}})  # Remove all retained HUD text.
                self.update(client, 0)
                client.show()
        except BaseException:
            self.last = None
            raise

    def update(self, client: Client, elapsed: float) -> None:
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Elapsed time must be finite and nonnegative')
        if self.paused and self.action is None and self.last is not None:
            return
        if not self.paused:
            self.elapsed += elapsed
        if self.action is not None:
            self.action += elapsed
            if self.action >= DURATION:
                self.action = None
        frame = image_frame(render(self.name, self.elapsed, action=self.action))
        if frame != self.last:
            try:
                # A complete background command publishes atomically. No text
                # changes, extra scene transactions or Show commands per frame.
                client.frame(frame)
            except BaseException:
                self.last = None
                raise
            self.last = frame


def run(settings: Settings) -> None:
    scene = Cozy(settings.scene)
    sent = 0
    while settings.frames is None or sent < settings.frames:
        try:
            target = resolve_port(settings.port)
            with Client(target, timeout=settings.timeout, gamma=settings.gamma) as client:
                scene.install(client)
                controls = settings.buttons
                if controls:
                    try:
                        client.buttons()  # Baseline: ignore presses before launch.
                    except NotImplementedError:
                        print('Cozy scene controls need newer button firmware; continuing without controls.', file=sys.stderr)
                        controls = False
                sent += 1
                print(f'Cozy {scene.name} -> {target}; Left/Right: scene, A: special, Up/Down: pause/resume, B: local menu', flush=True)
                previous = time.monotonic()
                while settings.frames is None or sent < settings.frames:
                    time.sleep(max(0, 1 / settings.fps - (time.monotonic() - previous)))
                    now = time.monotonic()
                    if controls:
                        scene.buttons(client.buttons())
                    scene.update(client, now - previous)
                    previous = now
                    sent += 1
        except (OSError, ValueError) as error:
            if settings.frames is not None or isinstance(error, ValueError) and 'layout mismatch' not in str(error):
                raise
            print(f'cozy: {error}; retrying in 2s', file=sys.stderr, flush=True)
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='auto', help='native USB auto, COM port or tcp://127.0.0.1:7777')
    parser.add_argument('--scene', choices=NAMES, default='farm')
    parser.add_argument('--fps', type=float, default=12, help='upload rate in (0, 20], default 12')
    parser.add_argument('--timeout', type=float, default=3, help='Canvas acknowledgement timeout')
    parser.add_argument('--frames', type=int, help='send N updates and exit; connection failures fail immediately')
    parser.add_argument('--no-buttons', action='store_true', help='disable host controls; local Back stays available')
    add_gamma_argument(parser)
    args = parser.parse_args()
    try:
        settings = Settings(args.port, args.scene, args.fps, args.timeout, args.frames, not args.no_buttons, args.gamma)
    except ValueError as error:
        parser.error(str(error))
    try:
        run(settings)
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'cozy: {error}\n')


if __name__ == '__main__':
    main()
