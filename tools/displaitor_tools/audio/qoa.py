"""Mono QOA encoding/decoding in Python, for offline firmware asset generation.

The interface accepts signed 16-bit PCM and returns a complete QOA file. Decode
validates the file before returning its sample rate and reconstructed PCM.
Algorithm adapted from phoboslab/qoa revision
bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e, copyright (c) 2023 Dominic Szablewski,
MIT licensed; see LICENSE-QOA.txt. No compiler or native library is used.
"""
from __future__ import annotations

from collections.abc import Sequence

import struct

_FRAME = 5120
_SLICE = 20
_SCALES = (1, 7, 21, 45, 84, 138, 211, 304, 421, 562, 731, 928, 1157, 1419, 1715, 2048)
_RECIPROCALS = tuple((65536 + scale - 1) // scale for scale in _SCALES)
_QUANT = (7, 7, 7, 5, 5, 3, 3, 1, 0, 0, 2, 2, 4, 4, 6, 6, 6)
# Exact round-to-nearest, ties away from zero, without floating-point tables.
_DEQUANT = tuple(tuple((1 if n > 0 else -1) * ((scale * abs(n) + 2) // 4)
                       for n in (3, -3, 10, -10, 18, -18, 28, -28)) for scale in _SCALES)


def _clamp(sample: int) -> int:
    return max(-32768, min(32767, sample))


def _predict(history: list[int], weights: list[int]) -> int:
    return (history[0] * weights[0] + history[1] * weights[1]
            + history[2] * weights[2] + history[3] * weights[3]) >> 13


def _update(history: list[int], weights: list[int], sample: int, residual: int) -> None:
    delta = residual >> 4
    for i in range(4):
        weights[i] += -delta if history[i] < 0 else delta
    history.pop(0)
    history.append(sample)


def _slice(samples: Sequence[int], history: list[int], weights: list[int], previous_scale: int) -> tuple[int, list[int], list[int], int]:
    best_rank = None
    best = None
    for candidate in range(16):
        scale = (previous_scale + candidate) & 15
        trial_history, trial_weights = history.copy(), weights.copy()
        rank, packed = 0, scale
        for sample in samples:
            prediction = _predict(trial_history, trial_weights)
            residual = sample - prediction
            scaled = (residual * _RECIPROCALS[scale] + 32768) >> 16
            scaled += ((residual > 0) - (residual < 0)) - ((scaled > 0) - (scaled < 0))
            quantized = _QUANT[max(-8, min(8, scaled)) + 8]
            dequantized = _DEQUANT[scale][quantized]
            reconstructed = _clamp(prediction + dequantized)
            penalty = max(0, (sum(w * w for w in trial_weights) >> 18) - 0x8ff)
            rank += (sample - reconstructed) ** 2 + penalty ** 2
            if best_rank is not None and rank > best_rank:
                break
            _update(trial_history, trial_weights, reconstructed, dequantized)
            packed = (packed << 3) | quantized
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best = (packed << ((_SLICE - len(samples)) * 3), trial_history, trial_weights, scale)
    assert best is not None
    return best


def encode(samples: Sequence[int], sample_rate: int) -> bytes:
    """Encode non-empty mono int16 PCM at 1..0xffffff Hz, deterministically."""
    samples = tuple(samples)
    if type(sample_rate) is not int or not 1 <= sample_rate <= 0xffffff:
        raise ValueError('QOA sample rate must be an integer in 1..0xffffff')
    if not 1 <= len(samples) <= 0xffffffff:
        raise ValueError('QOA requires 1..0xffffffff samples')
    if any(type(s) is not int or not -32768 <= s <= 32767 for s in samples):
        raise ValueError('QOA requires signed 16-bit integer samples')
    result = bytearray(b'qoaf' + struct.pack('>I', len(samples)))
    history, weights = [0] * 4, [0, 0, -8192, 16384]
    for start in range(0, len(samples), _FRAME):
        frame = samples[start:start + _FRAME]
        size = 24 + ((len(frame) + _SLICE - 1) // _SLICE) * 8
        header = (1 << 56) | (sample_rate << 32) | (len(frame) << 16) | size
        result.extend(struct.pack('>Q8H', header, *(n & 0xffff for n in history + weights)))
        scale = 0
        for offset in range(0, len(frame), _SLICE):
            packed, history, weights, scale = _slice(frame[offset:offset + _SLICE], history, weights, scale)
            result.extend(struct.pack('>Q', packed))
    return bytes(result)


def decode(data: bytes) -> tuple[int, tuple[int, ...]]:
    """Return (sample_rate, PCM tuple); reject invalid, non-mono or trailing data."""
    if len(data) < 8 or data[:4] != b'qoaf':
        raise ValueError('Invalid QOA header')
    declared = int.from_bytes(data[4:8], 'big')
    if not declared:
        raise ValueError('QOA must declare at least one sample')
    result: list[int] = []
    pos = 8
    rate: int | None = None
    while len(result) < declared:
        if len(data) - pos < 24:
            raise ValueError('Truncated QOA frame header')
        header = int.from_bytes(data[pos:pos + 8], 'big')
        channels, frame_rate = header >> 56, (header >> 32) & 0xffffff
        count, size = (header >> 16) & 0xffff, header & 0xffff
        expected = min(_FRAME, declared - len(result))
        if channels != 1 or not frame_rate or (rate is not None and frame_rate != rate):
            raise ValueError('QOA requires mono frames with a constant nonzero sample rate')
        if count != expected or size != 24 + ((count + 19) // 20) * 8:
            raise ValueError('Invalid QOA frame size or sample count')
        if pos + size > len(data):
            raise ValueError('Truncated QOA frame')
        rate = frame_rate
        state = struct.unpack('>8h', data[pos + 8:pos + 24])
        history, weights = list(state[:4]), list(state[4:])
        end = pos + size
        pos += 24
        left = count
        while pos < end:
            packed = int.from_bytes(data[pos:pos + 8], 'big')
            table = _DEQUANT[packed >> 60]
            for i in range(min(_SLICE, left)):
                residual = table[(packed >> (57 - i * 3)) & 7]
                sample = _clamp(_predict(history, weights) + residual)
                _update(history, weights, sample, residual)
                result.append(sample)
            left -= min(_SLICE, left)
            pos += 8
    if pos != len(data):
        raise ValueError('Trailing QOA data')
    assert rate is not None
    return rate, tuple(result)
