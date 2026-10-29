"""Reproduce the pinned, independently reference-decoded two-frame QOA fixture."""

from __future__ import annotations

from ..models import Pathish
import argparse
from pathlib import Path
import struct

from . import qoa


def generate(directory: Pathish) -> None:
    state, samples = 0x6d2b79f5, []
    for _ in range(5257):
        state = (state ^ (state << 13)) & 0xffffffff
        state ^= state >> 17
        state = (state ^ (state << 5)) & 0xffffffff
        sample = state >> 16
        samples.append(sample - 65536 if sample >= 32768 else sample)
    encoded = qoa.encode(samples, 22050)
    _, decoded = qoa.decode(encoded)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'nonzero_lms_two_frames.qoa').write_bytes(encoded)
    (directory / 'nonzero_lms_two_frames.pcm16le').write_bytes(struct.pack(f'<{len(decoded)}h', *decoded))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    generate(args.output_dir)
