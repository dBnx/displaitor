"""Explicit supplied-value weather scene, retained for scripts and offline art."""

from __future__ import annotations

from ..canvas import Client
import json
import math

from ..canvas import Layout, image_frame
from ..paths import LAYOUTS
from .icons import ANIMATION_FPS, FRAMES, sprite

LAYOUT = LAYOUTS / 'weather.json'


class Weather:
    """One condition string drives both the named status box and animation.

    Feed new readings through update(); one Canvas transaction publishes text
    and art together. show() is only used at installation, preserving local Back.
    """
    def __init__(self, *, temperature: str | None=None, status: str | None=None) -> None:
        self.scene = json.loads(LAYOUT.read_text(encoding="utf-8"))
        self._text_layout = Layout(self.scene)
        self.temperature = self.scene["text"]["temperature"]["text"] if temperature is None else temperature
        self.status = self.scene["text"]["status"]["text"] if status is None else status
        self._text_layout.encode_text("temperature", self.temperature)
        self._text_layout.encode_text("status", self.status)
        self.phase = 0.0
        self.last: dict[str, str | bytes] = {}

    def install(self, client: Client) -> None:
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

    def update(self, client: Client, elapsed: float, *, temperature: str | None=None, status: str | None=None) -> None:
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
