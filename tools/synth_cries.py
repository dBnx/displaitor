#!/usr/bin/env python3
"""Original GBA-inspired pet cries: swept voices, 8-bit colour, mono 16384 Hz.

Export WAV previews with no dependencies. To rebuild the firmware QOA assets,
provide the pinned upstream qoa.h with --qoa-header (see assets/audio/CRIES.md).
No ROM samples, sound downloads or synthesis work are needed during playback.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
import wave

RATE = 16_384
QOA_REVISION = "bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e"
QOA_SHA256 = "7b2396063eb960b10001db7db28ba25e284d4e772191968012e612dc8834952c"
# (start, length, starting pitch, ending pitch, strength, vibrato depth)
VOICES = {
    "torchic": (.52, ((.025, .135, 1450, 2150, .82, 24),
                       (.185, .255, 1650, 850, 1.0, 65))),
    "eevee": (.69, ((.025, .205, 720, 1180, .82, 30),
                     (.25, .355, 1260, 590, 1.0, 75))),
    "treecko": (.62, ((.025, .21, 420, 780, .85, 32),
                       (.26, .285, 740, 250, 1.0, 45))),
}


def synthesize(name):
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


def write_wav(path, samples):
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def generate(directory, qoa_header=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        encoder = None
        if qoa_header:
            header = Path(qoa_header).read_bytes()
            if hashlib.sha256(header).hexdigest() != QOA_SHA256:
                raise ValueError("qoa.h does not match the pinned encoder revision")
            (temporary / "qoa.h").write_bytes(header)
            encoder = temporary / ("encode.exe" if os.name == "nt" else "encode")
            compiler = shlex.split(os.environ.get("CC", "cc"))
            subprocess.run([*compiler, "-std=c99", "-O2", "-I", str(temporary),
                            str(Path(__file__).with_name("encode_cry.c")), "-o", str(encoder)], check=True)
            print("QOA header SHA-256:", hashlib.sha256(header).hexdigest())
        for name in VOICES:
            samples = synthesize(name)
            if encoder:
                pcm, decoded = temporary / "input.pcm", temporary / "decoded.pcm"
                pcm.write_bytes(struct.pack(f"<{len(samples)}h", *samples))
                subprocess.run([str(encoder), str(RATE), str(pcm),
                                str(directory / ("cry_" + name + ".qoa")), str(decoded)], check=True)
                # Audition the exact compressed-and-decoded firmware asset.
                raw = decoded.read_bytes()
                samples = struct.unpack(f"<{len(raw)//2}h", raw)
            write_wav(directory / ("cry_" + name + ".wav"), samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--qoa-header", help="local upstream qoa.h; enables QOA export")
    args = parser.parse_args()
    generate(args.output_dir, args.qoa_header)


if __name__ == "__main__":
    main()
