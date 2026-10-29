#!/usr/bin/env python3
"""Original GBA-inspired pet cries: swept voices, 8-bit colour, mono 16384 Hz.

Export firmware QOA assets and their exact decoded WAV previews with only Python.
See assets/audio/CRIES.md for the synthesis and codec sources.
No ROM samples, sound downloads or synthesis work are needed during playback.
"""
from __future__ import annotations

from collections.abc import Sequence
from ..models import Pathish

import argparse
import math
from pathlib import Path
import struct
import wave

from . import qoa

RATE = 16_384
# (start, length, starting pitch, ending pitch, strength, vibrato depth)
VOICES = {
    "torchic": (.52, ((.025, .135, 1450, 2150, .82, 24),
                       (.185, .255, 1650, 850, 1.0, 65))),
    "eevee": (.69, ((.025, .205, 720, 1180, .82, 30),
                     (.25, .355, 1260, 590, 1.0, 75))),
    "treecko": (.62, ((.025, .21, 420, 780, .85, 32),
                       (.26, .285, 740, 250, 1.0, 45))),
}


def synthesize(name: str) -> tuple[int, ...]:
    """Deterministic PCM; smooth note edges and silence at both ends prevent pops."""
    duration, notes = VOICES[name]
    signal = [0.0] * round(duration * RATE)
    seed = 0x4A83
    for start, length, low, high, strength, vibrato in notes:
        phase = 0.0
        for i in range(round(length * RATE)):
            t = i / RATE
            u = t / length
            pitch = low + (high - low) * (u * u * (3 - 2 * u))
            pitch += vibrato * math.sin(t * math.tau * (15 if name == "treecko" else 8))
            phase = (phase + pitch / RATE) % 1
            # A short wavetable and pulse colour evoke handheld sampled cries.
            p = round(phase * 32) % 32 / 32
            pulse = (1 if p < .25 else -1) + .5
            triangle = 1 - 4 * abs(p - .5)
            sine = math.sin(math.tau * p)
            seed = ((seed >> 1) ^ (0xB400 if seed & 1 else 0)) & 0xFFFF
            noise = (seed / 32767.5 - 1)
            if name == "torchic":
                voice = .50 * triangle + .24 * pulse + .20 * math.sin(3 * math.tau * p) + .025 * noise
            elif name == "eevee":
                voice = .55 * sine + .18 * math.sin(2 * math.tau * p) + .18 * pulse + .02 * noise
            else:
                voice = .40 * (2 * p - 1) + .30 * pulse + .26 * sine + .075 * noise
                voice *= .80 + .20 * math.sin(t * math.tau * 24)
            envelope = min(1, t / .006, (length - t) / .028)
            signal[round(start * RATE) + i] += voice * envelope * strength
    # Gentle low-pass, DC rejection, then 8-bit sample quantization. Leave ample
    # headroom for the QOA reconstruction and the board's existing PWM output.
    previous = filtered = dc = 0.0
    result = []
    for value in signal:
        filtered += .68 * (value - filtered)
        dc = filtered - previous + .995 * dc
        previous = filtered
        sample = max(-127, min(127, round(dc * 48))) * 256
        result.append(sample)
    return tuple(result)


def write_wav(path: Pathish, samples: Sequence[int]) -> None:
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def generate(directory: Pathish) -> None:
    """Write QOA plus WAV decoded from that same asset, using Python alone."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in VOICES:
        encoded = qoa.encode(synthesize(name), RATE)
        (directory / ("cry_" + name + ".qoa")).write_bytes(encoded)
        rate, samples = qoa.decode(encoded)
        assert rate == RATE
        write_wav(directory / ("cry_" + name + ".wav"), samples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    generate(args.output_dir)


if __name__ == "__main__":
    main()
