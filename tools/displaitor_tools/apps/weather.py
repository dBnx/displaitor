#!/usr/bin/env python3
"""Live wttr.in weather: cached readings, quiet animation and D-pad views."""

from __future__ import annotations
from contextlib import ExitStack
import argparse
import math
from pathlib import Path
import sys
import time

from ..output import add_gamma_argument
from ..canvas import Client, resolve_port
from ..paths import LAYOUTS
from ..weather.data import Feed, REFRESH, MIN_REFRESH, State, parse
from ..weather.examples import payload as example_payload
from ..weather.icons import ANIMATION_FPS, EXAMPLES, FRAMES, condition, sprite
from ..weather.manual import Weather as Weather
from ..weather.views import Display, PAGES

# Retain the documented manual scene interface and old preview option.
LAYOUT = LAYOUTS / 'weather.json'
__all__ = ['Weather', 'main', 'condition', 'sprite', 'EXAMPLES', 'FRAMES', 'ANIMATION_FPS']


def run(args: argparse.Namespace) -> None:
    manual = args.temperature is not None or args.status is not None
    scene = Weather(temperature=args.temperature, status=args.status) if manual else Display(getattr(args, 'view', 'now'))
    if isinstance(scene, Weather):
        scene.scene['text']['title']['text'] = 'MANUAL'
    demo = getattr(args, 'demo', False)
    feed = None
    sent = 0
    with ExitStack() as resources:
        while args.frames is None or sent < args.frames:
            try:
                target = resolve_port(args.port)
                with Client(target, timeout=args.timeout, gamma=getattr(args, "gamma", None)) as client:
                    if isinstance(scene, Display):
                        if demo:
                            scene.receive(State(parse(example_payload()), 'DEMO'))
                        else:
                            if feed is None:
                                feed = resources.enter_context(Feed(getattr(args, 'location', ''),
                                                                   directory=getattr(args, 'cache_dir', None),
                                                                   refresh=getattr(args, 'refresh', REFRESH)))
                            scene.receive(feed.get())
                    scene.install(client)
                    controls = not manual and not getattr(args, 'no_buttons', False)
                    if controls and isinstance(scene, Display):
                        try:
                            client.buttons()  # Fresh baseline, never replay old presses.
                        except NotImplementedError:
                            print('Weather views need updated button firmware; continuing without controls.', file=sys.stderr)
                            controls = False
                    sent += 1
                    print(f'Weather -> {target}; ' + ('manual values' if manual else 'demo' if demo else 'wttr.in, cached'), flush=True)
                    previous = time.monotonic()
                    while args.frames is None or sent < args.frames:
                        time.sleep(max(0, 1 / args.fps - (time.monotonic() - previous)))
                        now = time.monotonic()
                        if controls and isinstance(scene, Display):
                            scene.buttons(client.buttons())
                        if isinstance(scene, Display) and not demo:
                            assert feed is not None
                            scene.receive(feed.get())
                        # Page changes update the retained scene, never Show:
                        # Back arriving after the last poll keeps the local menu.
                        scene.update(client, now - previous)
                        previous = now
                        sent += 1
            except (OSError, ValueError) as error:
                if args.frames is not None or isinstance(error, ValueError) and 'layout mismatch' not in str(error):
                    raise
                print(f'weather: {error}; retrying in 2s', file=sys.stderr, flush=True)
                time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='auto', help='native USB auto, COM port or tcp://127.0.0.1:7777')
    parser.add_argument('--location', default='', help='city or coordinates; omitted: wttr.in IP-based location')
    parser.add_argument('--refresh', type=float, default=REFRESH, help='seconds between requests, at least 900; default 1800')
    parser.add_argument('--cache-dir', type=Path, help='override the OS user weather cache directory')
    parser.add_argument('--view', choices=PAGES, default='now', help='initial view; Up/Down switches pages')
    parser.add_argument('--no-buttons', action='store_true', help='disable host D-pad actions')
    parser.add_argument('--demo', action='store_true', help='explicit sample data and all views; no network')
    parser.add_argument('--temperature', help='supplied temperature: explicit manual mode, no network')
    parser.add_argument('--status', help='supplied condition: explicit manual mode, no network')
    parser.add_argument('--fps', type=float, default=8, help='animation upload rate in (0, 20], default 8')
    parser.add_argument('--timeout', type=float, default=3, help='Canvas acknowledgement timeout')
    parser.add_argument('--frames', type=int, help='send N frames and exit; device connection errors fail immediately')
    parser.add_argument('--preview-dir', help='export offline sample condition GIFs with the Rust simulator')
    add_gamma_argument(parser)
    args = parser.parse_args()
    for value, valid, message in ((args.fps, 0 < args.fps <= 20, '--fps must be in (0, 20]'),
                                  (args.timeout, args.timeout > 0, '--timeout must be positive'),
                                  (args.refresh, args.refresh >= MIN_REFRESH, '--refresh must be at least 900 seconds')):
        if not math.isfinite(value) or not valid:
            parser.error(message)
    if args.frames is not None and args.frames < 1:
        parser.error('--frames must be positive')
    if args.demo and (args.temperature is not None or args.status is not None):
        parser.error('--demo cannot be combined with manual values')
    try:
        if args.preview_dir:
            from ..previews.weather import previews
            previews(args.preview_dir)
        else:
            run(args)
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'weather: {error}\n')


if __name__ == '__main__':
    main()
