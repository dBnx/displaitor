"""Baked firmware frames stay pixel-identical to the Python scene definitions."""

from __future__ import annotations

import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from displaitor_tools.assets.cozy import DEFAULT_OUTPUT, FPS, checksum, decode, encode, encode_action
from displaitor_tools.canvas import image_frame
from displaitor_tools.scenes import BUILTIN_NAMES, NAMES, PERIODS, render
from displaitor_tools.paths import ROOT


class CozyAssetsTests(unittest.TestCase):
    def test_every_firmware_tick_matches_source_art_and_reference_checksum(self) -> None:
        for name in BUILTIN_NAMES:
            clip = (DEFAULT_OUTPUT / (name + '.cqoi')).read_bytes()
            hashes = (DEFAULT_OUTPUT / (name + '.hashes')).read_bytes()
            magic, ticks, unique = struct.unpack_from('<4sHH', clip)
            self.assertEqual(magic, b'CZY1')
            self.assertEqual(ticks, PERIODS[name] * FPS)
            self.assertLessEqual(unique, ticks)
            self.assertEqual(len(hashes), ticks * 8)
            for tick in range(ticks):
                raw = image_frame(decode(clip, tick))
                self.assertEqual(raw, image_frame(render(name, tick / FPS)), (name, tick))
                self.assertEqual(checksum(raw), struct.unpack_from('<Q', hashes, tick * 8)[0])

    def test_generator_preserves_the_checked_in_clips(self) -> None:
        for name in BUILTIN_NAMES:
            clip, hashes = encode(name)
            self.assertEqual(clip, (DEFAULT_OUTPUT / (name + '.cqoi')).read_bytes())
            self.assertEqual(hashes, (DEFAULT_OUTPUT / (name + '.hashes')).read_bytes())
            self.assertEqual(encode_action(name), (DEFAULT_OUTPUT / (name + '.action')).read_bytes())

    def test_bad_indexes_are_rejected(self) -> None:
        clip = (DEFAULT_OUTPUT / 'farm.cqoi').read_bytes()
        for invalid, tick in ((b'', 0), (b'BAD!' + clip[4:], 0), (clip[:10], 0), (clip, -1), (clip, 65535)):
            with self.assertRaises(ValueError):
                decode(invalid, tick)
        bad = bytearray(clip)
        bad[12:14] = b'\xff\xff'
        with self.assertRaises(ValueError):
            decode(bytes(bad), 0)

    def test_built_in_scenes_match_source_without_canvas_or_a_host_sender(self) -> None:
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
        with tempfile.TemporaryDirectory() as directory:
            for name in BUILTIN_NAMES:
                snapshot = Path(directory) / (name + '.ppm')
                result = subprocess.run([str(binary), '--headless', '--cozy', name, '--frames', '150',
                                         '--snapshot', str(snapshot)], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('App(', result.stdout)
                with Image.open(snapshot) as image:
                    self.assertEqual(image_frame(image), image_frame(render(name, 1.5)))

    def test_every_scene_is_baked_into_firmware(self) -> None:
        self.assertEqual(BUILTIN_NAMES, NAMES)
        with self.assertRaisesRegex(ValueError, 'Unknown built-in scene'):
            encode('missing')


if __name__ == '__main__':
    unittest.main()
