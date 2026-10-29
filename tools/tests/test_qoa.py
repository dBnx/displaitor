"""Codec checks use shipped reference-encoded files and independent PCM vectors."""

from __future__ import annotations
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from displaitor_tools.audio import fixtures, qoa, synth
from displaitor_tools.paths import ROOT


class QoaTests(unittest.TestCase):
    def test_python_generation_reproduces_reference_qoa_and_decoded_wav_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            synth.generate(directory)
            for name in synth.VOICES:
                with self.subTest(pet=name):
                    filename = 'cry_' + name
                    encoded = (Path(directory) / (filename + '.qoa')).read_bytes()
                    self.assertEqual(encoded, (ROOT / 'assets/audio' / (filename + '.qoa')).read_bytes())
                    self.assertEqual((Path(directory) / (filename + '.wav')).read_bytes(),
                                     (ROOT / 'docs/ui/companions/stats-cries' / (filename + '.wav')).read_bytes())
                    rate, samples = qoa.decode(encoded)
                    self.assertEqual(rate, synth.RATE)
                    self.assertEqual(len(samples), len(synth.synthesize(name)))
                    with wave.open(str(Path(directory) / (filename + '.wav')), 'rb') as sound:
                        self.assertEqual(sound.readframes(len(samples)), struct.pack(f'<{len(samples)}h', *samples))

    def test_reproduces_the_independent_nonzero_lms_multiframe_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixtures.generate(directory)
            for name in ('nonzero_lms_two_frames.qoa', 'nonzero_lms_two_frames.pcm16le'):
                self.assertEqual((Path(directory) / name).read_bytes(),
                                 (ROOT / 'qoa_decoder/tests/fixtures' / name).read_bytes())

    def test_decode_known_reference_vector_without_using_the_encoder(self) -> None:
        # Same independently reference-decoded vector as qoa_decoder's Rust tests.
        packed = 0
        for index in range(20):
            packed = (packed << 3) | (index % 8)
        data = b'qoaf' + struct.pack('>I', 20) + struct.pack('>Q', (1 << 56) | (44100 << 32) | (20 << 16) | 32)
        data += bytes(16) + struct.pack('>Q', packed)
        self.assertEqual(qoa.decode(data), (44100, (1, -1, 3, -4, 5, -6, 7, -8, 1, -2, 3, -4, 5, -6, 7, -8, 1, -2, 3, -4)))

    def test_partial_slices_frames_and_input_extremes(self) -> None:
        for length in (1, 19, 20, 21, 5119, 5120, 5121):
            with self.subTest(length=length):
                samples = tuple((0, 32767, -32768, 0)[n % 4] for n in range(length))
                encoded = qoa.encode(samples, 16384)
                rate, decoded = qoa.decode(encoded)
                self.assertEqual((rate, len(decoded)), (16384, length))
                self.assertTrue(all(-32768 <= x <= 32767 for x in decoded))
                self.assertEqual(encoded, qoa.encode(samples, 16384))

    def test_invalid_inputs_and_corrupt_framing_are_rejected(self) -> None:
        for samples, rate in (((), 1), ((0,), 0), ((0,), 0x1000000), ((0,), True),
                              ((32768,), 1), ((-32769,), 1), ((.5,), 1)):
            with self.assertRaises(ValueError):
                qoa.encode(samples, rate)
        encoded = qoa.encode([0] * 21, 16384)
        for end in range(len(encoded)):
            with self.assertRaises(ValueError):
                qoa.decode(encoded[:end])
        for offset, value in ((0, 0), (7, 0), (8, 2), (10, 0), (13, 22), (15, 1)):
            damaged = bytearray(encoded)
            if offset == 10:
                damaged[9:12] = bytes(3)
            else:
                damaged[offset] = value
            with self.assertRaises(ValueError):
                qoa.decode(damaged)
        with self.assertRaises(ValueError):
            qoa.decode(encoded + b'x')


if __name__ == '__main__':
    unittest.main()
