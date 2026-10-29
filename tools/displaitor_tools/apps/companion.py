#!/usr/bin/env python3
"""An idle companion that works harder as real CPU/GPU usage increases."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, Self
from ..output import add_gamma_argument
from ..canvas import ButtonState

import argparse
from dataclasses import dataclass
from datetime import datetime
import math
import sys
import threading
import time

from ..canvas import Client, CRIES, image_frame
from ..companions.designs import CUSTOM_ACTIONS, DESIGNS, IDLE_FRAMES, action_seconds, layout, sprite
from ..metrics import Sample, Sampler, metric_color, percent
from ..canvas import resolve_port
from ..companions.stats import PAGES, labels as stats_labels


@dataclass(frozen=True)
class Activity:
    value: float | None
    source: str
    mood: str
    demo: bool = False
    sample: Sample | None = None


class SampleSource(Protocol):
    def sample(self) -> Sample: ...


class Workload:
    """CPU/GPU activity, with hysteresis; RAM occupancy is not activity."""
    def __init__(self, source: str="auto") -> None:
        self.source = source
        self.mood = "unknown"

    def update(self, sample: Sample | None) -> Activity:
        values = [] if sample is None else [(name.upper(), percent(getattr(sample, name)))
                                            for name in ("cpu", "gpu")
                                            if self.source in ("auto", name)]
        valid = [(name, value) for name, value in values if value is not None]
        if not valid:
            self.mood = "unknown"
            return Activity(None, self.source.upper() if self.source != "auto" else "LOAD", self.mood,
                            sample.demo if sample else False, sample)
        source, value = max(valid, key=lambda pair: pair[1])
        if value >= 65 or (self.mood == "hard" and value >= 55):
            self.mood = "hard"
        elif value >= 20 or (self.mood in ("busy", "hard") and value >= 15):
            self.mood = "busy"
        else:
            self.mood = "idle"
        return Activity(value, source, self.mood, sample.demo if sample else False, sample)


class DemoSampler:
    def __init__(self, load: float | None=None) -> None:
        self.load = load
        self.started = time.monotonic()

    def sample(self) -> Sample:
        value = self.load if self.load is not None else (5, 45, 95)[int((time.monotonic() - self.started) / 4) % 3]
        return Sample(value, 64, value, datetime.now(), vram_used=round(3.2 * 1024**3), demo=True)


class Readings:
    """One latest sample, no queue. Slow OS GPU queries never block animation.

    Sampler construction and use stay on the same thread for psutil's per-thread
    CPU delta counter. Old readings expire instead of looking permanently live.
    """
    def __init__(self, factory: Callable[[], SampleSource], interval: float) -> None:
        self.factory, self.interval = factory, interval
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.latest: Sample | None = None
        self.received = 0.0
        self.error: str | None = None
        self.thread = threading.Thread(target=self._worker, daemon=True)

    def _worker(self) -> None:
        try:
            sampler = self.factory()
            if self.stop.wait(.25):
                return
            while not self.stop.is_set():
                sample = sampler.sample()
                with self.lock:
                    self.latest, self.received = sample, time.monotonic()
                self.ready.set()
                self.stop.wait(self.interval)
        except Exception as error:
            with self.lock:
                self.error = str(error)
            self.ready.set()

    def get(self) -> Sample | None:
        with self.lock:
            if self.error is not None:
                raise RuntimeError("metric sampler: " + self.error)
            if time.monotonic() - self.received > max(6, self.interval * 3):
                return None
            return self.latest

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        self.thread.join(timeout=4)


class Companion:
    def __init__(self, design: str, page: str="cpu", *, sound: bool=True) -> None:
        if design not in DESIGNS:
            raise ValueError("Unknown active companion design")
        self.design = design
        self.last: dict[str | tuple[str, str], str] = {}
        self.phase = 0.0
        self.action_remaining = 0.0
        self.action_pending = False
        self.page_index = PAGES.index(page)
        self.sound = sound
        self.cry_pending: str | None = None

    @property
    def page(self) -> str:
        return PAGES[self.page_index]

    def buttons(self, state: ButtonState) -> bool:
        """Apply host actions only while Canvas is active; local Back still wins."""
        changed = False
        if state.lost or not state.active:
            return changed
        designs = tuple(DESIGNS)
        for event in state.events:
            if not event.active:
                continue
            left, right = 'left' in event.pressed, 'right' in event.pressed
            if left != right:
                step = 1 if right else -1
                self.design = designs[(designs.index(self.design) + step) % len(designs)]
                self.phase = 0.0
                self.action_remaining = 0.0
                self.action_pending = False
                self.cry_pending = None
                changed = True
            up, down = 'up' in event.pressed, 'down' in event.pressed
            if up != down:
                self.page_index = (self.page_index + (1 if down else -1)) % len(PAGES)
                changed = True
            if 'a' in event.pressed:
                self.action_remaining = action_seconds(self.design)
                self.action_pending = True
                self.cry_pending = self.design if self.design in CRIES and self.sound else None
        return changed

    def install(self, client: Client, activity: Activity, *, activate: bool=True, elapsed: float=0) -> None:
        if activate:
            # Reconnect must not replay a sound queued for an earlier session.
            self.cry_pending = None
        try:
            with client.transaction():
                self.last.clear()
                scene = layout(self.design, self.page)
                client.layout(scene)
                self.last["name"] = scene["text"]["name"]["text"]
                self.update(client, activity, elapsed)
                if activate:
                    client.show()
        except BaseException:
            self.last.clear()
            raise

    def update(self, client: Client, activity: Activity, elapsed: float) -> None:
        try:
            with client.transaction():
                speed = {"unknown": 4, "idle": 6, "busy": 8, "hard": 12}[activity.mood]
                self.phase = (self.phase + elapsed * speed) % IDLE_FRAMES
                # A newly polled press happened after the preceding frame
                # interval; do not subtract that old interval from its action.
                if self.action_pending:
                    self.action_pending = False
                else:
                    self.action_remaining = max(0.0, self.action_remaining - elapsed)
                hop = 0
                action = None
                if self.action_remaining:
                    # A short hop is an explicit action, independent of CPU/GPU
                    # load. Move the actor while its floor and backdrop stay put.
                    if self.design in CUSTOM_ACTIONS:
                        action = 1 - self.action_remaining / action_seconds(self.design)
                    else:
                        hop = round(abs(math.sin((1.3 - self.action_remaining) * math.tau / .4)) * 3)
                image = sprite(self.design, int(self.phase), activity.mood, hop=hop, action=action)
                client.frame(image_frame(image))
                # Overview has no footer: label synthetic data in its header.
                title = "DEMO" if activity.demo and self.page == "all" else self.design.upper()
                if self.last.get("name") != title:
                    client.text("name", title)
                    self.last["name"] = title
                for name, (text, value) in stats_labels(activity, self.page, bool(self.action_remaining)).items():
                    color = metric_color(value, DESIGNS[self.design]) if value is not None else DESIGNS[self.design]
                    if self.last.get((name, "color")) != color:
                        client.style(name, color, None)
                        self.last[(name, "color")] = color
                    if self.last.get(name) != text:
                        client.text(name, text)
                        self.last[name] = text
        except BaseException:
            self.last.clear()
            raise

    def play_pending_cry(self, client: Client) -> None:
        """Send a one-shot effect only after the scene transaction has committed."""
        name, self.cry_pending = self.cry_pending, None
        if name is None or not self.sound:
            return
        try:
            client.cry(name)
        except NotImplementedError:
            self.sound = False
            print("Pokémon cries need updated firmware; animations and stats remain available.", file=sys.stderr)


def run(args: argparse.Namespace) -> None:
    factory = (lambda: DemoSampler(args.demo_load)) if args.demo or args.demo_load is not None else lambda: Sampler(args.gpu)
    workload = Workload(args.load)
    companion = Companion(args.design, getattr(args, "view", "cpu"), sound=not getattr(args, "no_sound", False))
    sent = 0
    with Readings(factory, args.interval) as readings:
        while args.frames is None or sent < args.frames:
            try:
                target = resolve_port(args.port)
                with Client(target, timeout=args.timeout, gamma=getattr(args, "gamma", None)) as client:
                    companion.install(client, workload.update(readings.get()))
                    controls = not args.no_buttons
                    if controls:
                        try:
                            client.buttons()  # Establish a fresh held-state baseline.
                        except NotImplementedError:
                            print("Button controls need updated firmware; continuing with live display only.", file=sys.stderr)
                            controls = False
                    sent += 1
                    print(f"Pixel Companion ({companion.design}) -> {target}; {args.load} load. Ctrl+C stops.", flush=True)
                    if controls:
                        print(f"Left/Right: {', '.join(DESIGNS)}; Up/Down: stats; A: play; B: menu.", flush=True)
                    previous = time.monotonic()
                    while args.frames is None or sent < args.frames:
                        time.sleep(max(0, 1 / args.fps - (time.monotonic() - previous)))
                        now = time.monotonic()
                        changed = companion.buttons(client.buttons()) if controls else False
                        activity = workload.update(readings.get())
                        if changed:
                            # Changing a pet must never pull the user back into
                            # Canvas if Back arrived after the button read.
                            companion.install(client, activity, activate=False, elapsed=now - previous)
                        else:
                            companion.update(client, activity, now - previous)
                        companion.play_pending_cry(client)
                        previous = now
                        sent += 1
            except (OSError, ValueError) as error:
                if isinstance(error, ValueError) and "layout mismatch" not in str(error):
                    raise
                if args.frames is not None:
                    raise
                print(f"pixel_companion: {error}; retrying in 2s", flush=True)
                time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="native USB auto, serial path, or tcp://127.0.0.1:7777")
    parser.add_argument("--design", choices=DESIGNS, default="orbit")
    parser.add_argument("--load", choices=("auto", "cpu", "gpu"), default="auto", help="activity source (auto: busier of CPU/GPU)")
    parser.add_argument("--gpu", default="auto", help="same GPU backends as pc_hub.py; none disables GPU sampling")
    parser.add_argument("--interval", type=float, default=1, help="seconds between metric samples (default 1)")
    parser.add_argument("--fps", type=float, default=8, help="animation upload rate, at most 20 (default 8)")
    parser.add_argument("--timeout", type=float, default=3, help="Canvas acknowledgement timeout")
    parser.add_argument("--frames", type=int, help="send N frames and exit; connection errors fail immediately")
    parser.add_argument("--no-buttons", action="store_true", help="disable host pet controls")
    parser.add_argument("--view", choices=PAGES, default="cpu", help="initial stats page; Up/Down cycles pages")
    parser.add_argument("--no-sound", action="store_true", help="disable A-button cries")
    parser.add_argument("--preview-dir", help="export all activity GIFs locally with the Rust simulator; no device")
    demo = parser.add_mutually_exclusive_group()
    demo.add_argument("--demo", action="store_true", help="labelled idle/work/hard cycle, four seconds per state")
    demo.add_argument("--demo-load", type=float, help="labelled fixed demo usage (0..100)")
    add_gamma_argument(parser)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < .2:
        parser.error("--interval must be finite and at least 0.2")
    if not math.isfinite(args.fps) or not 0 < args.fps <= 20:
        parser.error("--fps must be in (0, 20]")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive")
    if args.demo_load is not None and percent(args.demo_load) is None:
        parser.error("--demo-load must be in [0, 100]")
    try:
        if args.preview_dir:
            from ..previews.activity import previews
            previews(args.preview_dir)
        else:
            run(args)
    except KeyboardInterrupt:
        print("\nCompanion stopped; the display retains the last frame.")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"pixel_companion: {error}\n")


if __name__ == "__main__":
    main()
