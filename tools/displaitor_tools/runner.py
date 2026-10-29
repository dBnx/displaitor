"""A renderer and optional button callback, with one bounded, acknowledged frame."""
from __future__ import annotations

from collections.abc import Callable
import math
from threading import Event
import time
from typing import TYPE_CHECKING

from .canvas import ButtonState, Client, HEIGHT, WIDTH, image_frame, resolve_port
from .output import OutputGamma

if TYPE_CHECKING:
    from PIL import Image

type Renderer = Callable[[float], Image.Image]
type ButtonHandler = Callable[[ButtonState], None]
_POLL_PERIOD = .05


def run_scene(
    render: Renderer,
    *,
    on_buttons: ButtonHandler | None = None,
    port: str = 'auto',
    fps: float = 12,
    gamma: float | None = None,
    timeout: float = 3,
    buttons: bool = True,
    frames: int | None = None,
    stop: Event | None = None,
) -> int:
    """Show a 64x32 Pillow renderer until Back, stop, Ctrl+C, or a frame limit.

    ``render(elapsed_seconds)`` receives monotonic time since launch. Button
    callbacks run on the same thread, at most 20 Hz, with active, complete reports.
    Duplicate frames are not sent. Acknowledgements provide backpressure and
    missed render deadlines are skipped, without a frame queue or catch-up burst.
    Serial output defaults to gamma 2.8; TCP defaults to identity.

    Returns the number of rendered updates, including the initial frame and
    duplicates. Exceptions propagate after closing the connection. Reconnection
    is explicit, so a disconnected app never reopens Canvas over a local menu.
    ``buttons=False`` supports firmware without button reporting.
    """
    if not math.isfinite(fps) or not 0 < fps <= 20:
        raise ValueError('fps must be in (0, 20]')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    if frames is not None and (type(frames) is not int or frames < 1):
        raise ValueError('frames must be a positive integer')
    if gamma is not None:
        OutputGamma(gamma)
    if not buttons and on_buttons is not None:
        raise ValueError('on_buttons requires buttons=True')
    stopped = stop if stop is not None else Event()
    if stopped.is_set():
        return 0

    def frame(elapsed: float) -> bytes:
        image = render(elapsed)
        if image.size != (WIDTH, HEIGHT):
            raise ValueError(f'Scene renderer must return a {WIDTH}x{HEIGHT} image')
        return image_frame(image)

    with Client(resolve_port(port), timeout=timeout, gamma=gamma) as client:
        started = time.monotonic()
        with client.transaction():
            client.layout({'text': {}})
            last = frame(0)
            client.frame(last)
            client.show()
        count = 1
        if buttons:
            client.buttons()  # Establish a fresh baseline, ignoring old presses.
        next_frame = time.monotonic() + 1 / fps
        next_poll = time.monotonic() + _POLL_PERIOD
        while not stopped.is_set() and (frames is None or count < frames):
            deadline = min(next_frame, next_poll) if buttons else next_frame
            if stopped.wait(max(0.0, deadline - time.monotonic())):
                break
            now = time.monotonic()
            if buttons and now >= next_poll:
                state = client.buttons()
                if not state.active:
                    break  # Local Back wins; never issue another Show command.
                if on_buttons is not None and not state.lost:
                    on_buttons(state)
                next_poll = time.monotonic() + _POLL_PERIOD
            if stopped.is_set():
                break
            now = time.monotonic()
            if now >= next_frame:
                current = frame(now - started)
                if current != last:
                    client.frame(current)
                    last = current
                count += 1
                # Schedule from this render, rather than replaying missed ticks.
                next_frame = now + 1 / fps
        return count
