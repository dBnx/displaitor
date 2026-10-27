#!/usr/bin/env python3
"""Quiet pixel weather animations, selected by the bottom condition text.

Values come from the example layout or the caller, not a built-in weather feed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import time

from PIL import Image, ImageDraw

try:
    from .canvas import Client, Layout, image_frame
    from .pc_hub import resolve_port
except ImportError:
    from canvas import Client, Layout, image_frame
    from pc_hub import resolve_port

LAYOUT = Path(__file__).with_name("layouts") / "weather.json"
FRAMES = 16
ANIMATION_FPS = 8
EXAMPLES = ("Rain soon", "Sunny", "Partly cloudy", "Overcast", "Snow", "Fog", "Thunderstorm", "Clear night")


def condition(status: str) -> str:
    """Prefer precipitation over cloud/clear words in an English condition."""
    normalized = status.casefold()
    # Do not infer weather from negated English clauses we cannot interpret.
    if re.search(r"\b(?:no|not|without)\b", normalized):
        return "unknown"
    normalized = re.sub(r"\b(?:rain|snow)-free\b", "", normalized)
    words = set(re.findall(r"[a-z]+", normalized))
    if words & {"thunder", "thunderstorm", "thunderstorms", "storm", "stormy", "lightning"}:
        return "storm"
    if words & {"snow", "snowy", "snowing", "sleet", "flurries", "blizzard"}:
        return "snow"
    if words & {"rain", "rainy", "raining", "drizzle", "drizzling", "shower", "showers"}:
        return "rain"
    if words & {"fog", "foggy", "mist", "misty", "haze", "hazy"}:
        return "fog"
    if words & {"partly", "partial"} and words & {"cloud", "clouds", "cloudy", "sunny"}:
        return "partly"
    if words & {"cloud", "clouds", "cloudy", "overcast"}:
        return "cloudy"
    if words & {"night", "moon", "moonlit"}:
        return "night"
    if words & {"sun", "sunny", "sunshine", "clear"}:
        return "sunny"
    return "unknown"


def sprite(status: str, frame: int) -> Image.Image:
    """64x32 RGB background; all animated pixels stay in x=40..63, y=0..23."""
    image = Image.new("RGB", (64, 32), "black")
    draw = ImageDraw.Draw(image)
    phase = frame % FRAMES
    kind = condition(status)
    bob = 1 if 4 <= phase < 12 else 0
    blink = phase in (12, 13)

    def face(x, y):
        for eye in (x, x + 6):
            if blink:
                draw.line((eye, y + 1, eye + 1, y + 1), fill="#17282D")
            else:
                draw.point((eye, y), fill="#101D22")
                draw.point((eye, y + 1), fill="#101D22")
        draw.line(((x + 2, y + 3), (x + 3, y + 4), (x + 4, y + 3)), fill="#20353B")

    def cloud():
        # Chunky lobes keep the silhouette readable on the physical matrix.
        draw.polygon([(42, 10 + bob), (45, 10 + bob), (45, 7 + bob),
                      (48, 5 + bob), (52, 5 + bob), (55, 8 + bob),
                      (58, 8 + bob), (61, 11 + bob), (61, 15 + bob),
                      (43, 15 + bob), (42, 13 + bob)], fill="#4B6268")
        draw.line(((45, 9 + bob), (47, 9 + bob), (47, 7 + bob), (51, 7 + bob)), fill="#7D9498")
        face(48, 10 + bob)

    def sun(x=52, y=11, radius=5, *, smiling=True):
        for ray in range(8):
            angle = ray * math.tau / 8
            length = radius + 3 + ((phase // 4 + ray) % 2)
            start = (round(x + (radius + 2) * math.cos(angle)), round(y + (radius + 2) * math.sin(angle)))
            end = (round(x + length * math.cos(angle)), round(y + length * math.sin(angle)))
            draw.line((start, end), fill="#706337")
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#A69A60")
        if smiling:
            face(x - 3, y - 2)

    if kind == "sunny":
        sun(y=11 + bob)
    elif kind == "night":
        draw.ellipse((46, 4 + bob, 59, 18 + bob), fill="#84998E")
        draw.ellipse((52, 2 + bob, 63, 13 + bob), fill="black")
        draw.point((49, 11 + bob), fill="#17282D")
        draw.line(((49, 14 + bob), (50, 15 + bob), (52, 15 + bob)), fill="#354A49")
        for x, y, offset in ((43, 4, 0), (61, 19, 4), (44, 20, 8)):
            draw.point((x, y), fill="#607078" if (phase + offset) % 16 < 8 else "#283C42")
    elif kind in ("rain", "cloudy", "partly", "snow", "storm"):
        if kind == "partly":
            sun(47, 6, 3, smiling=False)
        cloud()
        if kind in ("rain", "storm"):
            for x, offset in ((45, 0), (51, 3), (57, 6)):
                y = 18 + (phase + offset) % 5
                draw.line((x, y, x, min(23, y + 1)), fill="#5893A0")
        if kind == "snow":
            for x, offset in ((45, 0), (51, 3), (58, 6)):
                y = 18 + (phase // 2 + offset) % 6
                x += 1 if (phase // 4 + offset) % 2 else 0
                draw.point((x, y), fill="#91B2AC")
                if y <= 21:
                    draw.line((x - 1, y + 1, x + 1, y + 1), fill="#607D79")
                    draw.point((x, y + 2), fill="#91B2AC")
        if kind == "storm":
            # A steady muted bolt avoids a bright whole-panel lightning flash.
            draw.polygon([(53, 17), (50, 20), (53, 20), (51, 23), (57, 18), (54, 18)], fill="#A09358")
    elif kind == "fog":
        cloud()
        for row, width in ((18, 16), (21, 13), (23, 17)):
            offset = 1 if (phase // 4 + row) % 2 else 0
            draw.line((43 + offset, row, 43 + offset + width, row), fill="#40595E")
    else:
        for index, x in enumerate((47, 52, 57)):
            draw.point((x, 12), fill="#607078" if phase // 4 % 3 == index else "#283C42")
    return image


class Weather:
    """One condition string drives both the named status box and animation.

    Feed new readings through update(); one Canvas transaction publishes text
    and art together. show() is only used at installation, preserving local Back.
    """
    def __init__(self, *, temperature=None, status=None):
        self.scene = json.loads(LAYOUT.read_text(encoding="utf-8"))
        self._text_layout = Layout(self.scene)
        self.temperature = self.scene["text"]["temperature"]["text"] if temperature is None else temperature
        self.status = self.scene["text"]["status"]["text"] if status is None else status
        self._text_layout.encode_text("temperature", self.temperature)
        self._text_layout.encode_text("status", self.status)
        self.phase = 0.0
        self.last = {}

    def install(self, client):
        try:
            with client.transaction():
                self.last.clear()
                self.scene["text"]["temperature"]["text"] = self.temperature
                self.scene["text"]["status"]["text"] = self.status
                client.layout(self.scene)
                self.update(client, 0)
                client.show()
        except BaseException:
            self.last.clear()
            raise

    def update(self, client, elapsed, *, temperature=None, status=None):
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("elapsed must be finite and nonnegative")
        temperature = self.temperature if temperature is None else temperature
        status = self.status if status is None else status
        self._text_layout.encode_text("temperature", temperature)
        self._text_layout.encode_text("status", status)
        self.temperature, self.status = temperature, status
        self.phase = (self.phase + elapsed * ANIMATION_FPS) % FRAMES
        background = image_frame(sprite(status, int(self.phase)))
        try:
            with client.transaction():
                if self.last.get("frame") != background:
                    client.frame(background)
                    self.last["frame"] = background
                for name, text in (("temperature", temperature), ("status", status)):
                    if self.last.get(name) != text:
                        client.text(name, text)
                        self.last[name] = text
        except BaseException:
            self.last.clear()
            raise


def run(args):
    weather = Weather(temperature=args.temperature, status=args.status)
    sent = 0
    while args.frames is None or sent < args.frames:
        try:
            target = resolve_port(args.port)
            with Client(target, timeout=args.timeout) as client:
                weather.install(client)
                sent += 1
                print(f"Weather -> {target}: {weather.temperature}, {weather.status} (supplied values)", flush=True)
                previous = time.monotonic()
                while args.frames is None or sent < args.frames:
                    time.sleep(max(0, 1 / args.fps - (time.monotonic() - previous)))
                    now = time.monotonic()
                    weather.update(client, now - previous)
                    previous = now
                    sent += 1
        except (OSError, TimeoutError, ValueError) as error:
            if args.frames is not None or isinstance(error, ValueError) and "layout mismatch" not in str(error):
                raise
            print(f"weather: {error}; retrying in 2s", file=sys.stderr, flush=True)
            time.sleep(2)


def previews(directory):
    """Export sample GIFs with text from the actual Rust Canvas renderer."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
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
        with Image.open(snapshot) as image:
            still = image.convert("RGB")
        snapshot.unlink()
        frames = []
        for phase in range(FRAMES):
            raw = image_frame(sprite(status, phase))
            quantized = Image.new("RGB", (64, 32))
            colors = []
            for offset in range(0, len(raw), 2):
                value = int.from_bytes(raw[offset:offset + 2], "little")
                colors.append(((((value >> 11) & 31) * 255 + 15) // 31,
                               (((value >> 5) & 63) * 255 + 31) // 63, ((value & 31) * 255 + 15) // 31))
            quantized.putdata(colors)
            image = still.copy()
            image.paste(quantized.crop((40, 0, 64, 24)), (40, 0))
            frames.append(image)
        frames[0].save(directory / (kind + ".png"))
        frames[0].save(directory / (kind + ".gif"), save_all=True, append_images=frames[1:],
                       duration=1000 // ANIMATION_FPS, loop=0, disposal=2, optimize=False)
        x, y = index % 4 * 256, index // 4 * 152
        labels.text((x + 8, y + 4), status, fill="#B8C8C0")
        sheet.paste(still.resize((256, 128), Image.Resampling.NEAREST), (x, y + 24))
    sheet.save(directory / "conditions.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="native USB auto, serial path, or tcp://127.0.0.1:7777")
    parser.add_argument("--temperature", help="temperature text; defaults to the example layout")
    parser.add_argument("--status", help="bottom condition text, e.g. 'Rain soon'; selects the animation")
    parser.add_argument("--fps", type=float, default=8, help="upload rate in (0, 20], default 8")
    parser.add_argument("--timeout", type=float, default=3, help="Canvas acknowledgement timeout")
    parser.add_argument("--frames", type=int, help="send N frames and exit; connection errors fail immediately")
    parser.add_argument("--preview-dir", help="export all sample animations with the Rust simulator; no device")
    args = parser.parse_args()
    if not math.isfinite(args.fps) or not 0 < args.fps <= 20:
        parser.error("--fps must be in (0, 20]")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive")
    try:
        if args.preview_dir:
            previews(args.preview_dir)
        else:
            run(args)
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        parser.exit(1, f"weather: {error}\n")


if __name__ == "__main__":
    main()
