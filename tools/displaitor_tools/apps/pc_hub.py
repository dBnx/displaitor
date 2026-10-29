#!/usr/bin/env python3
"""PC stats on Displaitor: run this script to select Canvas and start the hub.

CPU/RAM use psutil. GPU load/VRAM use AMD Linux sysfs, NVIDIA nvidia-smi, or
Windows GPU counters. Unsupported counters stay unknown. No root,
probe, UART, background service, or remote network listener is required.
"""
from __future__ import annotations

from PIL import Image

import argparse
from datetime import datetime
import json
import math
import time

from ..output import add_gamma_argument
from ..canvas import Client, image_frame, resolve_port
from ..metrics import MIB, GIB, GPU, Sample, Sampler, byte_count, metric_color, percent

from ..paths import LAYOUTS

LAYOUT = LAYOUTS / "pc_hub.json"
COLORS = ("#28D7F7", "#AA8CFF", "#FFBA52")
METRICS = ("cpu", "ram", "gpu")
VRAM_COLOR = "#69EF8C"
METER_TRACK = "#1A2A39"


def vram_text(value: object) -> str:
    """Used dedicated memory with explicit binary units, within eight glyphs."""
    value = byte_count(value)
    if value is None:
        return "--"
    for divisor, suffix in ((MIB, "MiB"), (GIB, "GiB"), (GIB * 1024, "TiB")):
        scaled = value / divisor
        if scaled < 999.5:
            return f"{scaled:.1f} {suffix}" if suffix != "MiB" and scaled < 9.95 else f"{scaled:.0f} {suffix}"
    return "TOO BIG"


class DemoSampler:
    """Labelled synthetic data for preview/testing; never mistaken for live stats."""
    def __init__(self) -> None:
        self.index = 0
        self.gpu = GPU("none")
        self.gpu.name = "DEMO"

    def sample(self) -> Sample:
        phase = self.index
        self.index += 1
        return Sample(42 + 30 * math.sin(phase / 4), 67 + 8 * math.sin(phase / 9),
                      83 + 15 * math.sin(phase / 5), datetime.now(), vram_used=int(4.2 * GIB), demo=True)


def background(sample: Sample, pulse: bool) -> bytes:
    from PIL import Image, ImageDraw
    # Unlit LEDs behind every glyph: dark desktop colours still glow on a matrix.
    image = Image.new("RGB", (64, 32), "#000000")
    draw = ImageDraw.Draw(image)
    if pulse:
        draw.point((63, 28), fill=VRAM_COLOR)
    for row, (name, base) in enumerate(zip(METRICS, COLORS)):
        value = percent(getattr(sample, name))
        y = row * 8
        color = metric_color(value, base)
        draw.rectangle((42, y + 2, 61, y + 5), fill=METER_TRACK)
        if value is None:
            for x in range(42, 62, 3):
                draw.point((x, y + 3), fill=color)
        else:
            width = round(value / 5)
            if width:
                draw.rectangle((42, y + 2, 41 + width, y + 5), fill=color)
            for x in (45, 49, 53, 57):
                draw.line((x, y + 2, x, y + 5), fill="#000000")
    return image_frame(image)


class Dashboard:
    def __init__(self, demo: bool=False) -> None:
        self.layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
        if demo:
            self.layout["text"]["cpu_label"]["text"] = "CPU*"
        self.last: dict[str | tuple[str, str], str] = {}
        self.pulse = False

    def install(self, client: Client, sample: Sample) -> None:
        try:
            with client.transaction():
                self.last.clear()
                # Prepare the retained scene before explicitly selecting Canvas.
                client.layout(self.layout)
                self.update(client, sample)
                try:
                    client.show()
                except ValueError as error:
                    if "unknown command" in str(error):
                        raise RuntimeError("firmware update required: this board does not support Canvas show") from error
                    raise
        except BaseException:
            self.last.clear()
            raise

    def update(self, client: Client, sample: Sample) -> None:
        try:
            with client.transaction():
                self.pulse = not self.pulse
                client.frame(background(sample, self.pulse))
                for name, base in zip(METRICS, COLORS):
                    value = percent(getattr(sample, name))
                    text = " --%" if value is None else f"{value:3.0f}%"
                    color = metric_color(value, base)
                    if self.last.get((name, "color")) != color:
                        client.style(name, color, None)
                        client.style(name + "_label", color, None)
                        self.last[(name, "color")] = color
                    if self.last.get(name) != text:
                        client.text(name, text)
                        self.last[name] = text
                color = VRAM_COLOR if byte_count(sample.vram_used) is not None else "#FFFFFF"
                if self.last.get(("vram", "color")) != color:
                    client.style("vram", color, None)
                    client.style("vram_label", color, None)
                    self.last[("vram", "color")] = color
                vram = vram_text(sample.vram_used)
                if self.last.get("vram") != vram:
                    client.text("vram", vram)
                    self.last["vram"] = vram
        except BaseException:
            self.last.clear()
            raise


def run(args: argparse.Namespace) -> None:
    sampler = DemoSampler() if args.demo else Sampler(args.gpu)
    dashboard = Dashboard(demo=args.demo)
    limit = 1 if args.once else args.count
    sent = 0
    time.sleep(min(.25, args.interval)) # Give the first CPU delta a real sampling interval.
    while limit is None or sent < limit:
        try:
            target = resolve_port(args.port)
            with Client(target, timeout=args.timeout, gamma=getattr(args, "gamma", None)) as client:
                dashboard.install(client, sampler.sample())
                sent += 1
                print(f"PC hub -> {target}; GPU: {sampler.gpu.name}; every {args.interval:g}s. Ctrl+C stops.", flush=True)
                while limit is None or sent < limit:
                    time.sleep(args.interval)
                    dashboard.update(client, sampler.sample())
                    sent += 1
                    # No frame queue or catch-up burst; acknowledged I/O may lower the rate.
        except (OSError, ValueError) as error:
            if isinstance(error, ValueError) and "layout mismatch" not in str(error):
                raise
            if limit is not None:
                raise
            print(f"pc_hub: {error}; retrying in 2s", flush=True)
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="auto (native Displaitor USB only), serial path, or tcp://127.0.0.1:7777")
    parser.add_argument("--interval", type=float, default=2, help="seconds between updates, at least 0.2 (default: 2)")
    parser.add_argument("--timeout", type=float, default=3, help="acknowledgement timeout in seconds")
    parser.add_argument("--gpu", default="auto", help="auto, none, AMD cardN, nvidia:N, or Windows windows:N")
    parser.add_argument("--demo", action="store_true", help="synthetic metrics for preview (CPU* marks demo data)")
    finite = parser.add_mutually_exclusive_group()
    finite.add_argument("--once", action="store_true", help="send one snapshot and exit; connection errors fail immediately")
    finite.add_argument("--count", type=int, help="send N snapshots and exit; connection errors fail immediately")
    add_gamma_argument(parser)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < .2:
        parser.error("--interval must be finite and at least 0.2 seconds")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.count is not None and args.count <= 0:
        parser.error("--count must be positive")
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nPC hub stopped; the display retains the last sample.")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"pc_hub: {error}\n")


if __name__ == "__main__":
    main()
