"""Transport output calibration; artwork and the Canvas protocol stay RGB565."""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
from functools import lru_cache
import math
import sys

USB_GAMMA = 2.8


def add_gamma_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--gamma', type=float,
                        help=f'output gamma (default: USB {USB_GAMMA:g}, TCP 1.0); 1 disables correction')


@lru_cache(maxsize=8)
def _table(gamma: float) -> array[int]:
    # Build once per exponent, then one lookup per pixel. 128 KiB/table on the
    # host, no Pillow dependency, float operations or allocations per channel.
    red = tuple(round((value / 31) ** gamma * 31) << 11 for value in range(32))
    green = tuple(round((value / 63) ** gamma * 63) << 5 for value in range(64))
    blue = tuple(value >> 11 for value in red)
    return array('H', (red[value >> 11] | green[(value >> 5) & 63] | blue[value & 31]
                       for value in range(65536)))


@dataclass(frozen=True)
class OutputGamma:
    exponent: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.exponent) or self.exponent <= 0:
            raise ValueError('gamma must be positive and finite')

    def color(self, rgb565: int) -> int:
        return rgb565 if self.exponent == 1 else _table(self.exponent)[rgb565]

    def frame(self, rgb565: bytes) -> bytes:
        if self.exponent == 1:
            return rgb565
        words = array('H')
        words.frombytes(rgb565)
        if sys.byteorder != 'little':
            words.byteswap()
        table = _table(self.exponent)
        corrected = array('H', (table[word] for word in words))
        if sys.byteorder != 'little':
            corrected.byteswap()
        return corrected.tobytes()
