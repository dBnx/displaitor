"""Bake the Python cozy scenes into indexed, deduplicated QOI clips for Flash."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import struct

from PIL import Image

from ..canvas import image_frame, quantized_image
from ..models import Pathish
from ..paths import ROOT
from ..scenes import BUILTIN_NAMES, PERIODS, render
from ..scenes.actions import DURATION, layer

FPS = 10
DEFAULT_OUTPUT = (ROOT / 'displaitor' / 'assets' / 'cozy'
                  if (ROOT / 'Cargo.toml').is_file() and (ROOT / 'displaitor').is_dir()
                  else Path.cwd() / 'cozy-assets')


def checksum(raw: bytes) -> int:
    value = 0xCBF29CE484222325
    for byte in raw:
        value = ((value ^ byte) * 0x100000001B3) & 0xffffffffffffffff
    return value


def encode(name: str) -> tuple[bytes, bytes]:
    """Return the CZY1 clip and test-only RGB565 checksums, one per timeline tick."""
    if name not in BUILTIN_NAMES:
        raise ValueError('Unknown built-in scene')
    timeline: list[int] = []
    offsets = [0]
    atlas = bytearray()
    hashes = bytearray()
    seen: dict[bytes, int] = {}
    for tick in range(round(PERIODS[name] * FPS)):
        frame = quantized_image(render(name, tick / FPS))
        raw = image_frame(frame)
        hashes.extend(struct.pack('<Q', checksum(raw)))
        index = seen.get(raw)
        if index is None:
            index = len(seen)
            seen[raw] = index
            stream = io.BytesIO()
            frame.save(stream, format='QOI')
            atlas.extend(stream.getvalue())
            offsets.append(len(atlas))
        timeline.append(index)
    header = struct.pack('<4sHHI', b'CZY1', len(timeline), len(seen), 1_000_000 // FPS)
    return (header + struct.pack(f'<{len(timeline)}H', *timeline)
            + struct.pack(f'<{len(offsets)}I', *offsets) + atlas, bytes(hashes))


def encode_action(name: str) -> bytes:
    """ACT1: offsets into sparse, opaque RGB565 runs; no framebuffer in firmware."""
    offsets = [0]
    payload = bytearray()
    for tick in range(round(DURATION * FPS)):
        overlay = layer(name, tick / FPS)
        alpha = overlay.getchannel('A').tobytes()
        if any(value not in (0, 255) for value in alpha):
            raise ValueError('Action overlays need binary alpha')
        raw = image_frame(overlay.convert('RGB'))
        index = 0
        while index < 2048:
            if not alpha[index]:
                index += 1
                continue
            start = index
            while index < 2048 and alpha[index]:
                index += 1
            payload.extend(struct.pack('<HH', start, index - start))
            payload.extend(raw[start * 2:index * 2])
        offsets.append(len(payload))
    return (struct.pack('<4sHH', b'ACT1', len(offsets) - 1, 1_000 // FPS)
            + struct.pack(f'<{len(offsets)}I', *offsets) + payload)


def decode(data: bytes, tick: int) -> Image.Image:
    """Inspect a generated clip without Rust; reject inconsistent index bounds."""
    if len(data) < 12:
        raise ValueError('Truncated cozy clip')
    magic, ticks, unique, period_us = struct.unpack_from('<4sHHI', data)
    if magic != b'CZY1' or not 0 < unique <= ticks or not 0 <= tick < ticks or period_us != 1_000_000 // FPS:
        raise ValueError('Invalid cozy clip header or tick')
    table = 12 + ticks * 2
    payload = table + (unique + 1) * 4
    if payload > len(data):
        raise ValueError('Truncated cozy clip index')
    index = struct.unpack_from('<H', data, 12 + tick * 2)[0]
    if index >= unique:
        raise ValueError('Invalid cozy frame index')
    start, end = struct.unpack_from('<II', data, table + index * 4)
    if not 0 <= start < end <= len(data) - payload:
        raise ValueError('Invalid cozy frame offset')
    with Image.open(io.BytesIO(data[payload + start:payload + end])) as image:
        if image.size != (64, 32):
            raise ValueError('Invalid cozy frame dimensions')
        return image.convert('RGB')


def generate(directory: Pathish = DEFAULT_OUTPUT, *, check: bool = False) -> None:
    directory = Path(directory)
    if not check:
        directory.mkdir(parents=True, exist_ok=True)
    for name in BUILTIN_NAMES:
        clip, hashes = encode(name)
        action_hashes = b''.join(struct.pack('<Q', checksum(image_frame(
            render(name, 1.5, action=tick / FPS)))) for tick in range(round(DURATION * FPS)))
        for suffix, data in (('.cqoi', clip), ('.hashes', hashes),
                             ('.action', encode_action(name)), ('.action-hashes', action_hashes)):
            path = directory / (name + suffix)
            if check:
                if path.read_bytes() != data:
                    raise ValueError(f'Stale cozy asset: {path}; regenerate with tools/run.py assets cozy')
            else:
                path.write_bytes(data)
        _, ticks, unique = struct.unpack_from('<4sHH', clip)
        print(f'{name}: {ticks} ticks, {unique} unique frames, {len(clip):,} Flash bytes', flush=True)

    for name in ('nyan', 'hyper'):
        path = directory / (name + '.action')
        data = encode_action(name)
        if check:
            if path.read_bytes() != data:
                raise ValueError(f'Stale action asset: {path}')
        else:
            path.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--check', action='store_true', help='verify assets are reproducible without writing')
    args = parser.parse_args()
    generate(args.output_dir, check=args.check)
