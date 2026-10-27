#!/usr/bin/env python3
"""An idle companion that works harder as real CPU/GPU usage increases."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import subprocess
import sys
import threading
import time

try:
    from .canvas import Client, image_frame
    from .companion_designs import DESIGNS, layout, sprite
    from .pc_hub import Sample, Sampler, metric_color, percent, resolve_port
except ImportError:
    from canvas import Client, image_frame
    from companion_designs import DESIGNS, layout, sprite
    from pc_hub import Sample, Sampler, metric_color, percent, resolve_port


@dataclass(frozen=True)
class Activity:
    value: float | None
    source: str
    mood: str
    demo: bool = False


class Workload:
    """CPU/GPU activity, with hysteresis; RAM occupancy is not activity."""
    def __init__(self, source="auto"):
        self.source = source
        self.mood = "unknown"

    def update(self, sample):
        values = [] if sample is None else [(name.upper(), percent(getattr(sample, name)))
                                            for name in ("cpu", "gpu")
                                            if self.source in ("auto", name)]
        values = [(name, value) for name, value in values if value is not None]
        if not values:
            self.mood = "unknown"
            return Activity(None, self.source.upper() if self.source != "auto" else "LOAD", self.mood)
        source, value = max(values, key=lambda pair: pair[1])
        if value >= 65 or (self.mood == "hard" and value >= 55):
            self.mood = "hard"
        elif value >= 20 or (self.mood in ("busy", "hard") and value >= 15):
            self.mood = "busy"
        else:
            self.mood = "idle"
        return Activity(value, source, self.mood, sample.demo)


class DemoSampler:
    def __init__(self, load=None):
        self.load = load
        self.started = time.monotonic()

    def sample(self):
        value = self.load if self.load is not None else (5, 45, 95)[int((time.monotonic() - self.started) / 4) % 3]
        return Sample(value, None, value, datetime.now(), demo=True)


class Readings:
    """One latest sample, no queue. Slow OS GPU queries never block animation.

    Sampler construction and use stay on the same thread for psutil's per-thread
    CPU delta counter. Old readings expire instead of looking permanently live.
    """
    def __init__(self, factory, interval):
        self.factory, self.interval = factory, interval
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.latest = None
        self.received = 0
        self.error = None
        self.thread = threading.Thread(target=self._worker, daemon=True)

    def _worker(self):
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

    def get(self):
        with self.lock:
            if self.error is not None:
                raise RuntimeError("metric sampler: " + self.error)
            if time.monotonic() - self.received > max(6, self.interval * 3):
                return None
            return self.latest

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=4)


class Companion:
    def __init__(self, design):
        self.design = design
        self.last = {}
        self.phase = 0.0
        self.action_remaining = 0.0
        self.action_pending = False

    def buttons(self, state):
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
                changed = True
            if 'a' in event.pressed:
                self.action_remaining = 1.2
                self.action_pending = True
        return changed

    def install(self, client, activity, *, activate=True):
        try:
            with client.transaction():
                self.last.clear()
                scene = layout(self.design)
                for name, text in (("metric", "--%"), ("mood", "WAIT"), ("demo", "LOAD")):
                    scene["text"][name]["text"] = text
                client.layout(scene)
                self.update(client, activity, 0)
                if activate:
                    client.show()
        except BaseException:
            self.last.clear()
            raise

    def update(self, client, activity, elapsed):
        try:
            with client.transaction():
                speed = {"unknown": 2, "idle": 3, "busy": 8, "hard": 12}[activity.mood]
                self.phase = (self.phase + elapsed * speed) % 16
                # A newly polled press happened after the preceding frame
                # interval; do not subtract that old interval from its action.
                if self.action_pending:
                    self.action_pending = False
                else:
                    self.action_remaining = max(0.0, self.action_remaining - elapsed)
                hop = 0
                if self.action_remaining:
                    # A short hop is an explicit action, independent of CPU/GPU
                    # load. Move the actor while its floor and backdrop stay put.
                    hop = round(abs(math.sin((1.3 - self.action_remaining) * math.tau / .4)) * 3)
                image = sprite(self.design, int(self.phase), activity.mood, hop=hop)
                client.frame(image_frame(image))
                color = metric_color(activity.value, DESIGNS[self.design])
                labels = {"metric": "--%" if activity.value is None else f"{activity.value:.0f}%",
                          "mood": "PLAY" if self.action_remaining else
                                  {"unknown": "WAIT", "idle": "IDLE", "busy": "WORK", "hard": "HARD"}[activity.mood],
                          "demo": "DEMO" if activity.demo else activity.source}
                for name, text in labels.items():
                    if self.last.get((name, "color")) != color:
                        client.style(name, color, None)
                        self.last[(name, "color")] = color
                    if self.last.get(name) != text:
                        client.text(name, text)
                        self.last[name] = text
        except BaseException:
            self.last.clear()
            raise


def run(args):
    factory = (lambda: DemoSampler(args.demo_load)) if args.demo or args.demo_load is not None else lambda: Sampler(args.gpu)
    workload, companion = Workload(args.load), Companion(args.design)
    sent = 0
    with Readings(factory, args.interval) as readings:
        while args.frames is None or sent < args.frames:
            try:
                target = resolve_port(args.port)
                with Client(target, timeout=args.timeout) as client:
                    companion.install(client, workload.update(readings.get()))
                    controls = not args.no_buttons
                    if controls:
                        try:
                            client.buttons()  # Establish a fresh held-state baseline.
                        except NotImplementedError:
                            print("Button controls need updated firmware; continuing with live display only.", file=sys.stderr)
                            controls = False
                    sent += 1
                    print(f"Pixel Companion ({args.design}) -> {target}; {args.load} load. Ctrl+C stops.", flush=True)
                    previous = time.monotonic()
                    while args.frames is None or sent < args.frames:
                        time.sleep(max(0, 1 / args.fps - (time.monotonic() - previous)))
                        now = time.monotonic()
                        changed = companion.buttons(client.buttons()) if controls else False
                        activity = workload.update(readings.get())
                        if changed:
                            # Changing a pet must never pull the user back into
                            # Canvas if Back arrived after the button read.
                            companion.install(client, activity, activate=False)
                        else:
                            companion.update(client, activity, now - previous)
                        previous = now
                        sent += 1
            except (OSError, ValueError) as error:
                if isinstance(error, ValueError) and "layout mismatch" not in str(error):
                    raise
                if args.frames is not None:
                    raise
                print(f"pixel_companion: {error}; retrying in 2s", flush=True)
                time.sleep(2)


def previews(directory):
    """Capture actual Canvas HUDs, then export idle/work/hard animated studies."""
    from PIL import Image, ImageDraw
    try:
        from .companion_designs import quantized
    except ImportError:
        from companion_designs import quantized
    root = Path(__file__).resolve().parents[1]
    binary = root / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (1184, 672), "#0C0C0C")
    labels = ImageDraw.Draw(sheet)
    for row, (mood, load) in enumerate((("idle", 5), ("busy", 45), ("hard", 95))):
        for col, design in enumerate(DESIGNS):
            snapshot = directory / (design + "-" + mood + ".ppm")
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "100", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                if not line.startswith("Canvas listening on 127.0.0.1:"):
                    raise RuntimeError("simulator did not open Canvas: " + line)
                with Client("tcp://" + line.split()[-1]) as client:
                    Companion(design).install(client, Activity(load, "CPU", mood, True))
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
            hud = still.crop((40, 0, 64, 32))
            animation = []
            for frame in range(16):
                image = quantized(sprite(design, frame, mood))
                image.paste(hud, (40, 0))
                animation.append(image)
            speed = {"idle": 3, "busy": 8, "hard": 12}[mood]
            animation[0].save(directory / (design + "-" + mood + ".gif"), save_all=True,
                              append_images=animation[1:], duration=round(1000 / speed),
                              loop=0, disposal=2, optimize=False)
            x, y = 8 + col * 392, row * 224
            labels.text((x, y + 3), design.upper() + " / " + mood.upper(), fill="#B4B4B4")
            sheet.paste(still.resize((384, 192), Image.Resampling.NEAREST), (x, y + 24))
    sheet.save(directory / "workload-designs.png")


def main():
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
    parser.add_argument("--preview-dir", help="export all activity GIFs locally with the Rust simulator; no device")
    demo = parser.add_mutually_exclusive_group()
    demo.add_argument("--demo", action="store_true", help="labelled idle/work/hard cycle, four seconds per state")
    demo.add_argument("--demo-load", type=float, help="labelled fixed demo usage (0..100)")
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
            previews(args.preview_dir)
        else:
            run(args)
    except KeyboardInterrupt:
        print("\nCompanion stopped; the display retains the last frame.")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"pixel_companion: {error}\n")


if __name__ == "__main__":
    main()
