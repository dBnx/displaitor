"""Muted, whole-pixel weather characters with stationary text regions."""

from __future__ import annotations
import math
import re

from PIL import Image, ImageDraw

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

    def face(x: int, y: int) -> None:
        for eye in (x, x + 6):
            if blink:
                draw.line((eye, y + 1, eye + 1, y + 1), fill="#17282D")
            else:
                draw.point((eye, y), fill="#101D22")
                draw.point((eye, y + 1), fill="#101D22")
        draw.line(((x + 2, y + 3), (x + 3, y + 4), (x + 4, y + 3)), fill="#20353B")

    def cloud() -> None:
        # Chunky lobes keep the silhouette readable on the physical matrix.
        draw.polygon([(42, 10 + bob), (45, 10 + bob), (45, 7 + bob),
                      (48, 5 + bob), (52, 5 + bob), (55, 8 + bob),
                      (58, 8 + bob), (61, 11 + bob), (61, 15 + bob),
                      (43, 15 + bob), (42, 13 + bob)], fill="#4B6268")
        draw.line(((45, 9 + bob), (47, 9 + bob), (47, 7 + bob), (51, 7 + bob)), fill="#7D9498")
        face(48, 10 + bob)

    def sun(x: int=52, y: int=11, radius: int=5, *, smiling: bool=True) -> None:
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
