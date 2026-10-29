#!/usr/bin/env python3
"""Small Canvas client: named text layers over still/streamed RGB565 backgrounds.

Core protocol/TCP needs only Python's standard library. Images need Pillow;
serial ports need pyserial. Import Client for scripts, or run --help.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Protocol, Self, TypedDict, cast
from .models import Pathish
from .output import OutputGamma, USB_GAMMA, add_gamma_argument
if TYPE_CHECKING:
    from PIL import Image
    from serial import Serial

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import secrets
import socket
import struct
import sys
import threading
import time
import zlib


class PortInfo(Protocol):
    device: str
    vid: int | None
    pid: int | None
    serial_number: str | None
    product: str | None


class Reply(TypedDict, total=False):
    width: int
    height: int
    slots: int
    text_bytes: int
    layout_id: int
    state: int
    flags: int
    latest: int
    overwritten: int
    at_ms: int
    events: tuple[tuple[int, int, int], ...]

WIDTH, HEIGHT, MAX_SLOTS, MAX_TEXT = 64, 32, 8, 64
FONTS = {"small": (0, 6), "medium": (1, 10), "large": (2, 20)}
FONT_WIDTHS = {"small": 4, "medium": 6, "large": 10}
ERRORS = {1: "invalid packet", 2: "unsupported protocol version", 3: "unknown command",
          4: "invalid value or unconfigured text slot", 5: "layout mismatch: upload this layout first",
          6: "text must be printable Latin-1, at most 64 UTF-8 bytes",
          7: "Canvas transaction failed; abort before retrying"}
BUTTON_NAMES = ("a", "b", "select", "up", "down", "left", "right")
CRIES = {"stop": 0, "torchic": 1, "eevee": 2, "treecko": 3}
# Configure the short serial poll only when opening COM. Assigning pyserial's
# timeout on an open port reapplies Windows COM settings, even if unchanged.
# The overall ACK deadline can be exceeded by at most one fixed read interval.
SERIAL_READ_TIMEOUT = .05


def _held(state: int) -> frozenset[str]:
    return frozenset(name for bit, name in enumerate(BUTTON_NAMES) if state & (1 << bit))


@dataclass(frozen=True)
class ButtonEvent:
    sequence: int
    at_ms: int
    held: frozenset[str]
    pressed: frozenset[str]
    released: frozenset[str]
    active: bool


@dataclass(frozen=True)
class ButtonState:
    held: frozenset[str]
    active: bool
    events: tuple[ButtonEvent, ...]
    lost: bool
    more: bool
    overwritten: int
    at_ms: int


def color565(value: str) -> int:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise ValueError("colours must be #RRGGBB")
    try:
        color = int(value[1:], 16)
    except ValueError as error:
        raise ValueError("colours must be #RRGGBB") from error
    if any(c not in "0123456789abcdefABCDEF" for c in value[1:]):
        raise ValueError("colours must be #RRGGBB")
    return ((color >> 8) & 0xF800) | ((color >> 5) & 0x07E0) | ((color >> 3) & 0x001F)


def text_bytes(text: str) -> bytes:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    data = text.encode("utf-8")
    if len(data) > MAX_TEXT or any(not (32 <= ord(c) <= 126 or 160 <= ord(c) <= 255) for c in text):
        raise ValueError(ERRORS[6])
    return data


def cobs_encode(data: bytes | bytearray) -> bytes:
    output = bytearray([0])
    position, code = 0, 1
    for byte in data:
        if byte == 0:
            output[position] = code
            position = len(output)
            output.append(0)
            code = 1
        else:
            output.append(byte)
            code += 1
            if code == 255:
                output[position] = code
                position = len(output)
                output.append(0)
                code = 1
    output[position] = code
    return bytes(output) + b"\0"


def cobs_decode(data: bytes | bytearray) -> bytes:
    output = bytearray()
    position = 0
    while position < len(data):
        code = data[position]
        position += 1
        if code == 0 or position + code - 1 > len(data):
            raise ValueError("invalid COBS packet")
        output.extend(data[position:position + code - 1])
        position += code - 1
        if code != 255 and position < len(data):
            output.append(0)
    return bytes(output)


def packet(command: int, sequence: int, payload: bytes = b"") -> bytes:
    if len(payload) > WIDTH * HEIGHT * 2:
        raise ValueError("packet payload too large")
    body = struct.pack("<BBH", 1, command, sequence) + payload
    return cobs_encode(body + struct.pack("<I", zlib.crc32(body)))


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


class Layout:
    """Names remain on the host; insertion order defines slot IDs and z order."""
    def __init__(self, source: object, *, output: OutputGamma | None = None) -> None:
        output = output or OutputGamma(1.0)
        if isinstance(source, (str, Path)):
            source = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(source, dict) or set(source) != {"text"} or not isinstance(source["text"], dict):
            raise ValueError('layout must contain a single "text" object of named boxes')
        if len(source["text"]) > MAX_SLOTS:
            raise ValueError("at most eight text boxes are supported")
        self.slots = {}
        self._right_columns = {}
        names = json.dumps(list(source["text"]), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        records = bytearray(4)
        records.append(len(source["text"]))
        for index, (name, definition) in enumerate(source["text"].items()):
            if not isinstance(name, str) or not name or not isinstance(definition, dict):
                raise ValueError("text boxes require nonempty names and object definitions")
            if set(definition) - {"x", "y", "width", "height", "font", "color", "background", "text", "align"}:
                raise ValueError(f"unknown layout property for {name!r}")
            x = _integer(definition.get("x", 0), "x", 0, WIDTH - 1)
            y = _integer(definition.get("y", 0), "y", 0, HEIGHT - 1)
            width = _integer(definition.get("width", WIDTH - x), "width", 1, WIDTH - x)
            font = definition.get("font", "small")
            if not isinstance(font, str) or font not in FONTS:
                raise ValueError("font must be small, medium or large")
            font_id, font_height = FONTS[font]
            align = definition.get("align", "left")
            if align not in ("left", "right"):
                raise ValueError("align must be left or right")
            if align == "right":
                columns = width // FONT_WIDTHS[font]
                if columns < 1:
                    raise ValueError("right-aligned boxes must fit at least one complete character")
                self._right_columns[name] = columns
            height = _integer(definition.get("height", min(font_height, HEIGHT - y)), "height", 1, HEIGHT - y)
            foreground = output.color(color565(definition.get("color", "#FFFFFF")))
            background = definition.get("background")
            if background == "transparent":
                background = None
            background_color = 0 if background is None else output.color(color565(background))
            self.slots[name] = index
            text = self.encode_text(name, definition.get("text", ""))
            records.extend(struct.pack("<6BH B H B", index, x, y, width, height, font_id,
                                       foreground, background is not None, background_color, len(text)))
            records.extend(text)
        # Include host alignment policy even when an initial value fills its
        # box and would otherwise serialize identically. Keep old left-only IDs.
        if self._right_columns:
            names += b"\0right:" + json.dumps(list(self._right_columns), ensure_ascii=False,
                                              separators=(",", ":")).encode("utf-8")
        struct.pack_into("<I", records, 0, zlib.crc32(names))
        self.id = zlib.crc32(records)
        self.payload = struct.pack("<I", self.id) + records

    def reference(self, name: str) -> bytes:
        try:
            return struct.pack("<IB", self.id, self.slots[name])
        except KeyError as error:
            raise ValueError(f"unknown text name {name!r}; available: {', '.join(self.slots)}") from error

    def encode_text(self, name: str, text: str) -> bytes:
        """Keep numeric suffixes fixed using whole monospace cells on the host."""
        if name not in self.slots:
            raise ValueError(f"unknown text name {name!r}; available: {', '.join(self.slots)}")
        encoded = text_bytes(text)
        columns = self._right_columns.get(name)
        if columns is not None:
            if len(text) > columns:
                raise ValueError(f"{name!r} fits at most {columns} characters; value would be clipped")
            encoded = text_bytes(text.rjust(columns))
        return encoded


def resolve_port(target: str="auto", ports: Iterable[PortInfo] | None=None) -> str:
    if target != "auto":
        return target
    if ports is None:
        try:
            from serial.tools.list_ports import comports
        except ImportError as error:
            raise RuntimeError("install dependencies: python -m pip install displaitor-tools") from error
        ports = comports()
    matches = sorted({p.device for p in ports
                      if (p.vid, p.pid) == (0x16C0, 0x27DD)
                      and (p.serial_number == "canvas-1" or p.product == "Displaitor Canvas"
                           or (sys.platform == "win32" and not p.serial_number
                               and p.product in (None, "USB Serial Device")))})
    if not matches:
        raise ConnectionError("waiting for Displaitor native USB data connection (the probe's UART is not Canvas)")
    if len(matches) != 1:
        raise ValueError("multiple Displaitors found; choose --port " + " or ".join(matches))
    return matches[0]


class Client:
    def __init__(self, target: str, layout: object | None=None, *, baudrate: int = 115200, timeout: float = 3.0,
                 gamma: float | None = None) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self._socket = target.startswith("tcp://")
        self._output = OutputGamma(gamma if gamma is not None else 1.0 if self._socket else USB_GAMMA)
        self._layout = Layout(layout, output=self._output) if layout is not None else None
        self._sequence = secrets.randbits(16)
        self._lock = threading.RLock()
        self._transaction_depth = 0
        self._transaction_failed = False
        self._button_cursor: int | None = None
        self._button_state: int | None = None
        self._connection: socket.socket | Serial | None = None
        self.info: Reply | None = None
        self.timeout = timeout
        if self._socket:
            host, port = target[6:].rsplit(":", 1)
            self._connection = socket.create_connection((host.strip("[]"), int(port)), timeout)
            self._connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        else:
            try:
                import serial
            except ImportError as error:
                raise RuntimeError("serial support needs: python -m pip install displaitor-tools") from error
            self._connection = serial.Serial(target, baudrate=baudrate,
                                             timeout=min(timeout, SERIAL_READ_TIMEOUT), write_timeout=timeout)
        try:
            self._write(b"\0")  # discard any incomplete request from a previous session
            self.info = self._request(9)  # abort staging retained by an undetected serial reopen
        except BaseException:
            self.close()
            raise

    @property
    def gamma(self) -> float:
        return self._output.exponent

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self.info = None

    @contextmanager
    def transaction(self) -> Iterator[Client]:
        """Publish a complete scene once. Nested scopes join the outer transaction.

        Exceptions poison the entire transaction even when an inner exception is
        caught. A failed exchange closes the connection: Commit may have reached
        the device, so reconnect before choosing a new complete scene.
        """
        with self._lock:
            outer = self._transaction_depth == 0
            if outer:
                previous_layout, previous_info = self._layout, self.info
                self._request(7)
                self._transaction_failed = False
            self._transaction_depth += 1
            try:
                yield self
                if outer:
                    if self._transaction_failed:
                        raise RuntimeError("Canvas transaction aborted after an earlier operation failed")
                    self._request(8)
            except BaseException:
                self._transaction_failed = True
                if outer:
                    if self._connection is not None:
                        try:
                            self._request(9)
                        except BaseException:
                            self.close()
                    self._layout = previous_layout
                    self.info = previous_info if self._connection is not None else None
                raise
            finally:
                self._transaction_depth -= 1

    @contextmanager
    def _operation(self) -> Iterator[None]:
        # Validate and resolve names under the same lock as layout publication.
        with self._lock:
            try:
                yield
            except BaseException:
                if self._transaction_depth:
                    self._transaction_failed = True
                raise

    def _write(self, data: bytes) -> None:
        if self._socket:
            connection = cast(socket.socket, self._connection)
            connection.settimeout(self.timeout)
            connection.sendall(data)
        else:
            while data:
                written = cast("Serial", self._connection).write(data)
                if not written:
                    raise TimeoutError("serial write timed out")
                data = data[written:]

    def _request(self, command: int, payload: bytes = b"") -> Reply:
        # One shared Client may stream in a worker while another thread updates text.
        with self._lock:
            if self._connection is None:
                raise ConnectionError("Canvas connection is closed; reconnect before retrying")
            try:
                result = self._exchange(command, payload)
                if command != 10:
                    self.info = result
                return result
            except BaseException as error:
                if self._transaction_depth:
                    self._transaction_failed = True
                if isinstance(error, OSError):
                    self.close()
                raise

    def _exchange(self, command: int, payload: bytes) -> Reply:
        self._sequence = (self._sequence + 1) & 0xFFFF
        self._write(packet(command, self._sequence, payload))
        deadline = time.monotonic() + self.timeout
        encoded = bytearray()
        oversized = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Canvas did not acknowledge; reconnect before retrying")
            if self._socket:
                connection = cast(socket.socket, self._connection)
                connection.settimeout(remaining)
                byte = connection.recv(1)
                if not byte:
                    raise ConnectionError("Canvas disconnected")
            else:
                serial_port = cast("Serial", self._connection)
                byte = serial_port.read(1)
                if not byte:
                    # A COM read can time out between USB packets. Keep partial
                    # replies and wait until the shared deadline above expires.
                    continue
            if byte != b"\0":
                # Button reports contain at most four nine-byte events. Retain
                # a fixed bound even when a peer never sends a delimiter.
                if len(encoded) < (61 if command == 10 else 18):
                    encoded.extend(byte)
                else:
                    oversized = True
                continue
            if not encoded or oversized:
                encoded.clear()
                oversized = False
                continue
            try:
                reply = cobs_decode(encoded)
            except ValueError:
                encoded.clear()
                continue
            encoded.clear()
            if len(reply) < 8 or zlib.crc32(reply[:-4]) != struct.unpack("<I", reply[-4:])[0]:
                continue
            version, opcode, sequence = struct.unpack("<BBH", reply[:4])
            if version != 1 or sequence != self._sequence:
                continue
            if command == 10 and opcode == 0x81:
                if not 24 <= len(reply) <= 60:
                    continue
                _, _, _, status, state, flags, count, latest, overwritten, now_ms = struct.unpack(
                    "<BBHBBBBIII", reply[:20])
                if status != 0 or flags & ~3 or count > 4 or len(reply) != 24 + count * 9:
                    continue
                events = tuple(struct.unpack_from("<IIB", reply, 20 + index * 9)
                               for index in range(count))
                return {"state": state, "flags": flags, "latest": latest,
                        "overwritten": overwritten, "at_ms": now_ms, "events": events}
            if len(reply) != 17 or opcode != 0x80:
                continue
            version, opcode, sequence, status, width, height, slots, text_limit, layout_id = struct.unpack("<BBH5BI", reply[:-4])
            if status == 3 and command == 10:
                raise NotImplementedError("firmware update required: this board does not support Canvas buttons")
            if status == 3 and command == 11:
                raise NotImplementedError("firmware update required: this board does not support companion cries")
            if status == 3 and command in (7, 8, 9):
                raise RuntimeError("firmware update required: this board does not support Canvas transactions")
            if status:
                raise ValueError(ERRORS.get(status, f"device error {status}"))
            if command == 10:
                # A successful ordinary ACK cannot substitute for a report.
                continue
            if (width, height, slots, text_limit) != (WIDTH, HEIGHT, MAX_SLOTS, MAX_TEXT):
                raise ValueError("device has incompatible Canvas capabilities")
            return {"width": width, "height": height, "slots": slots, "text_bytes": text_limit, "layout_id": layout_id}

    def buttons(self) -> ButtonState:
        """Read button transitions since this client's previous poll.

        The first poll establishes a fresh baseline. A queue overrun similarly
        resets the baseline and returns no events, avoiding invented actions.
        Poll again promptly while ``more`` is true to drain a burst in order.
        Button reads share the connection lock with drawing and transactions.
        """
        with self._lock:
            initial = self._button_cursor is None
            payload = b"" if initial else struct.pack("<I", self._button_cursor)
            report = self._request(10, payload)
            state = report["state"]
            lost, more = bool(report["flags"] & 2), bool(report["flags"] & 1)
            events: list[ButtonEvent] = []
            if not initial and not lost:
                previous = self._button_state
                assert previous is not None
                for sequence, at_ms, raw_state in report["events"]:
                    held = _held(raw_state)
                    # Entering/leaving Canvas is navigation, not a pet action.
                    stable_mode = not ((previous ^ raw_state) & 0x80)
                    before = _held(previous)
                    events.append(ButtonEvent(sequence, at_ms, held,
                                              held - before if stable_mode else frozenset(),
                                              before - held if stable_mode else frozenset(),
                                              bool(raw_state & 0x80)))
                    previous = raw_state
                self._button_state = previous if more else state
                self._button_cursor = events[-1].sequence if more and events else report["latest"]
            else:
                self._button_state = state
                self._button_cursor = report["latest"]
            return ButtonState(_held(state), bool(state & 0x80), tuple(events),
                               lost, more, report["overwritten"], report["at_ms"])

    def layout(self, source: object) -> None:
        with self._operation():
            layout = Layout(source, output=self._output)
            self._request(2, layout.payload)
            self._layout = layout

    def text(self, name: str, text: str) -> None:
        with self._operation():
            if self._layout is None:
                raise ValueError("load a layout before updating named text")
            self._request(3, self._layout.reference(name) + self._layout.encode_text(name, text))

    def style(self, name: str, color: str, background: str | None = None) -> None:
        with self._operation():
            if self._layout is None:
                raise ValueError("load a layout before updating named text")
            if background == "transparent":
                background = None
            self._request(4, self._layout.reference(name) + struct.pack("<HBH", self._output.color(color565(color)),
                          background is not None, 0 if background is None else self._output.color(color565(background))))

    def fill(self, color: str) -> None:
        with self._operation():
            self._request(5, struct.pack("<H", self._output.color(color565(color))))

    def show(self) -> None:
        """Open Canvas once, after commit when called within a transaction."""
        with self._operation():
            self._request(6)

    def frame(self, rgb565: bytes) -> None:
        with self._operation():
            if len(rgb565) != WIDTH * HEIGHT * 2:
                raise ValueError("raw frames must contain exactly 4096 little-endian RGB565 bytes")
            self._request(1, self._output.frame(rgb565))

    def cry(self, name: str) -> None:
        """Play one bundled effect while Canvas is active; no retry on lost ACK."""
        if name not in CRIES:
            raise ValueError("cry must be stop, torchic, eevee or treecko")
        with self._operation():
            self._request(11, bytes([CRIES[name]]))

    def background(self, path: Pathish, *, fit: str = "contain") -> None:
        with self._operation():
            with _image(path) as image:
                self.frame(image_frame(image, fit=fit))

    def stream(self, paths: Iterable[Pathish], *, fps: float = 20, repeat: bool = False, fit: str = "contain", stop: threading.Event | None=None) -> None:
        """Stream stills/animated files; ACK backpressure limits speed without a frame queue."""
        try:
            if not math.isfinite(fps) or fps <= 0 or fps > 60:
                raise ValueError("fps must be in (0, 60]")
            paths = list(paths)
            if not paths:
                raise ValueError("stream requires at least one image")
            while True:
                for path in paths:
                    with _image(path) as image:
                        for index in range(getattr(image, "n_frames", 1)):
                            if stop is not None and stop.is_set():
                                return
                            image.seek(index)
                            started = time.monotonic()
                            self.frame(image_frame(image, fit=fit))
                            delay = max(0, 1 / fps - (time.monotonic() - started))
                            if stop is None:
                                time.sleep(delay)
                            elif stop.wait(delay):
                                return
                if not repeat:
                    return
        except BaseException:
            # Lock only on failure; streaming must allow concurrent text updates.
            with self._operation():
                raise

    @contextmanager
    def streaming(self, paths: Iterable[Pathish] | Pathish, *, fps: float = 20, fit: str = "contain") -> Iterator[Client]:
        """Keep a background playing while normal text/style calls remain available."""
        with self._operation():
            if self._transaction_depth:
                raise RuntimeError("Cannot start asynchronous streaming inside a Canvas transaction; "
                                   "start streaming outside the transaction or use frame/background")
            stream_paths: Iterable[Pathish] = [paths] if isinstance(paths, (str, Path)) else paths
        stop = threading.Event()
        errors: list[Exception] = []
        def run() -> None:
            try:
                self.stream(stream_paths, fps=fps, repeat=True, fit=fit, stop=stop)
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=run, name="canvas-background")
        worker.start()
        try:
            yield self
        finally:
            stop.set()
            worker.join()
        if errors:
            raise errors[0]


def _image(path: Pathish) -> Image.Image:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("image support needs: python -m pip install displaitor-tools") from error
    return Image.open(path)


def image_frame(image: Image.Image, *, fit: str="contain") -> bytes:
    from PIL import Image, ImageOps
    rgba = image.convert("RGBA")
    flattened = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    flattened.alpha_composite(rgba)
    rgb = flattened.convert("RGB")
    if fit == "contain":
        rgb = ImageOps.pad(rgb, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS, color="black")
    elif fit == "cover":
        rgb = ImageOps.fit(rgb, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    elif fit == "stretch":
        rgb = rgb.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    else:
        raise ValueError("fit must be contain, cover or stretch")
    pixels = rgb.tobytes()
    return b"".join(struct.pack("<H", ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
                    for r, g, b in zip(pixels[0::3], pixels[1::3], pixels[2::3]))


def quantized_image(image: Image.Image) -> Image.Image:
    """Expand exact panel RGB565 pixels for previews and baked firmware media."""
    from PIL import Image
    raw = image_frame(image)
    colors = []
    for offset in range(0, len(raw), 2):
        value = int.from_bytes(raw[offset:offset + 2], 'little')
        colors.append(((((value >> 11) & 31) * 255 + 15) // 31,
                       (((value >> 5) & 63) * 255 + 31) // 63, ((value & 31) * 255 + 15) // 31))
    result = Image.new('RGB', (WIDTH, HEIGHT))
    result.putdata(colors)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="explicit serial path or tcp://127.0.0.1:7777 for simulator")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud (USB CDC ignores it)")
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--layout", help="local JSON name mapping for text/style; does not upload")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("info")
    buttons = commands.add_parser("buttons", help="read physical button state and transitions")
    buttons.add_argument("--watch", action="store_true", help="poll every 50 ms and print changes")
    commands.add_parser("show", help="switch to Canvas once (requires current firmware)")
    cry = commands.add_parser("cry", help="play a bundled companion cry; Canvas must already be active")
    cry.add_argument("name", choices=CRIES)
    layout = commands.add_parser("layout", help="replace the layout and initial text")
    layout.add_argument("path")
    text = commands.add_parser("text", help="update one named text box; empty string clears it")
    text.add_argument("name")
    text.add_argument("value")
    style = commands.add_parser("style", help="set text foreground and transparent/solid box background")
    style.add_argument("name")
    style.add_argument("--color", required=True)
    style.add_argument("--background", default="transparent")
    fill = commands.add_parser("fill", help="replace only the background with a solid colour")
    fill.add_argument("color")
    background = commands.add_parser("background")
    background.add_argument("path")
    background.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain")
    stream = commands.add_parser("stream")
    stream.add_argument("paths", nargs="+")
    stream.add_argument("--fps", type=float, default=20)
    stream.add_argument("--repeat", action="store_true")
    stream.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain")
    add_gamma_argument(parser)
    args = parser.parse_args()
    try:
        with Client(args.port, args.layout, baudrate=args.baud, timeout=args.timeout, gamma=args.gamma) as client:
            match args.command:
                case "info": print(json.dumps(client.info, indent=2))
                case "buttons":
                    previous = None
                    while True:
                        state = client.buttons()
                        changed = (state.held, state.active, state.lost, state.overwritten)
                        if state.events or changed != previous:
                            print(json.dumps(asdict(state), default=lambda value: sorted(value)), flush=True)
                        previous = changed
                        if not args.watch:
                            break
                        time.sleep(.05)
                case "show": client.show()
                case "cry": client.cry(args.name)
                case "layout": client.layout(args.path)
                case "text": client.text(args.name, args.value)
                case "style": client.style(args.name, args.color, args.background)
                case "fill": client.fill(args.color)
                case "background": client.background(args.path, fit=args.fit)
                case "stream": client.stream(args.paths, fps=args.fps, repeat=args.repeat, fit=args.fit)
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"canvas: {error}\n")


if __name__ == "__main__":
    main()
