"""Sea-pet readability, genuine workload poses, prop actions and button lifetime."""

from __future__ import annotations

import unittest
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock

from PIL import Image, ImageColor

from displaitor_tools.apps.companion import Activity, Companion
from displaitor_tools.canvas import ButtonEvent, ButtonState, image_frame
from displaitor_tools.companions import designs, marine
from displaitor_tools.paths import ROOT
from displaitor_tools.scenes import render


def pixels(image: Image.Image, color: str) -> set[tuple[int, int]]:
    rgb = ImageColor.getrgb(color)
    return {(x, y) for y in range(image.height) for x in range(image.width)
            if image.getpixel((x, y)) == rgb}


class MarineTests(unittest.TestCase):
    def test_all_activity_and_play_frames_preserve_header_hud_and_ground(self) -> None:
        for name in marine.COLORS:
            header = designs.layout(name)['text']['name']
            ground = designs.sprite(name, 0).crop((0, 31, 64, 32)).tobytes()
            poses: dict[str, set[bytes]] = {}
            for mood in ('idle', 'busy', 'hard', 'unknown'):
                poses[mood] = set()
                for frame in range(16):
                    for action in (None, 0, .25, .5, .75, 1):
                        image = designs.sprite(name, frame, mood, action=action)
                        self.assertEqual(image.size, (64, 32))
                        self.assertFalse(any(image.crop((40, 0, 64, 32)).tobytes()))
                        self.assertFalse(any(image.crop((header['x'], 0, 64, 6)).tobytes()))
                        self.assertEqual(image.crop((0, 31, 64, 32)).tobytes(), ground)
                        if action is None:
                            poses[mood].add(image_frame(image))
                self.assertGreater(len(poses[mood]), 3)
            # Hard work must have new anatomy/poses, not only a faster clock.
            self.assertNotEqual(poses['idle'], poses['busy'])
            self.assertNotEqual(poses['busy'], poses['hard'])
            self.assertEqual(poses['unknown'], poses['idle'])

    def test_nudibranch_reaches_lettuce_then_recovers_with_a_heart(self) -> None:
        still = designs.sprite('nudibranch', 0)
        reaching = designs.sprite('nudibranch', 0, action=.4)
        content = designs.sprite('nudibranch', 0, action=.8)
        self.assertGreater(max(x for x, _ in pixels(reaching, '#A997B5')),
                           max(x for x, _ in pixels(still, '#A997B5')))
        self.assertTrue(pixels(reaching, '#62926A'))
        self.assertFalse(pixels(content, '#62926A'))
        self.assertTrue(pixels(content, '#C3879C'))
        self.assertEqual(designs.sprite('nudibranch', 0, action=1).tobytes(), still.tobytes())

    def test_moray_bubble_leaves_mouth_rises_and_disappears(self) -> None:
        early = pixels(designs.sprite('moray', 0, action=.25), '#8ABCC1')
        late = pixels(designs.sprite('moray', 0, action=.8), '#8ABCC1')
        self.assertTrue(early)
        self.assertTrue(late)
        self.assertLess(min(y for _, y in late), min(y for _, y in early) - 4)
        self.assertEqual(designs.sprite('moray', 0, action=1).tobytes(),
                         designs.sprite('moray', 0).tobytes())
        self.assertFalse(pixels(designs.sprite('moray', 0, action=1), '#C3879C'))

    def test_a_runs_full_custom_action_without_sound_or_moving_the_floor(self) -> None:
        event = ButtonEvent(1, 1, frozenset({'a'}), frozenset({'a'}), frozenset(), True)
        state = ButtonState(frozenset({'a'}), True, (event,), False, False, 0, 1)
        for name in marine.COLORS:
            pet, client = Companion(name), MagicMock()
            activity = Activity(5, 'CPU', 'idle')
            pet.buttons(state)
            pet.update(client, activity, 10)  # A slow preceding interval cannot swallow a press.
            self.assertEqual(pet.action_remaining, marine.ACTION_SECONDS)
            pet.update(client, activity, marine.ACTION_SECONDS * .4)
            pet.play_pending_cry(client)
            client.cry.assert_not_called()
            self.assertEqual(pet.action_remaining, marine.ACTION_SECONDS * .6)
            pet.update(client, activity, marine.ACTION_SECONDS)
            self.assertEqual(pet.action_remaining, 0)

    def test_reef_keeps_both_actors_visible_and_the_sand_fixed(self) -> None:
        frames = [render('reef', index / 10) for index in range(160)]
        sand = frames[0].crop((8, 31, 44, 32)).tobytes()
        for image in frames:
            self.assertTrue(pixels(image, '#A997B5'))  # Slug face.
            self.assertTrue(pixels(image, '#C1D5AC'))  # Eel eye.
            self.assertEqual(image.crop((8, 31, 44, 32)).tobytes(), sand)
        self.assertGreater(len({image.crop((0, 8, 35, 31)).tobytes() for image in frames}), 20)
        self.assertGreater(len({image.crop((35, 8, 64, 31)).tobytes() for image in frames}), 20)

    def test_both_live_cli_pets_match_actual_canvas_pixels_under_high_load(self) -> None:
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')

        def actor_pixels(image: Image.Image) -> tuple[int, ...]:
            words = struct.unpack('<2048H', image_frame(image))
            return tuple(words[y * 64 + x] for y in range(7, 32) for x in range(40))

        with tempfile.TemporaryDirectory() as directory:
            for name in marine.COLORS:
                snapshot = Path(directory) / (name + '.ppm')
                process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                            '--frames', '400', '--snapshot', str(snapshot)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    assert process.stdout is not None
                    line = process.stdout.readline().strip()
                    self.assertTrue(line.startswith('Canvas listening on 127.0.0.1:'), line)
                    result = subprocess.run([sys.executable, str(ROOT / 'tools/pixel_companion.py'),
                                             '--port', 'tcp://' + line.split()[-1], '--design', name,
                                             '--demo-load', '95', '--frames', '3', '--fps', '20'],
                                            cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=6)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    stdout, stderr = process.communicate(timeout=6)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    with Image.open(snapshot) as image:
                        self.assertIn(actor_pixels(image),
                                      [actor_pixels(designs.sprite(name, frame, 'hard')) for frame in range(16)])
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
