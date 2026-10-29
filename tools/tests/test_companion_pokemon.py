"""Raster-level prop interactions, bundled art integrity and live A-button use."""

from __future__ import annotations
from collections.abc import Iterable
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image, ImageColor

from displaitor_tools import canvas as canvas
from displaitor_tools.companions import designs as designs
from displaitor_tools.companions import pokemon as pets
from displaitor_tools.apps import companion as pixel_companion


def points(image: Image.Image, colors: Iterable[str]) -> set[tuple[int, int]]:
    palette = {ImageColor.getrgb(c) for c in colors}
    data = image.tobytes()
    return {(i % 64, i // 64) for i, pixel in enumerate(zip(data[::3], data[1::3], data[2::3]))
            if pixel in palette}


class RescuePetTests(unittest.TestCase):
    def test_idle_never_uses_the_walk_or_interaction_poses(self) -> None:
        for name in pets.COLORS:
            with patch.object(pets, '_pose', wraps=pets._pose) as pose:
                for tick in range(designs.IDLE_FRAMES):
                    designs.sprite(name, tick, 'idle')
                self.assertTrue(pose.called)
                self.assertTrue(all(call.args[1] == 'idle' for call in pose.call_args_list), name)

    def test_native_pose_rgb_and_alpha_are_preserved_before_output_gamma(self) -> None:
        # Guard against reintroducing source attenuation now that the transport
        # handles the panel's response. Include side-walk poses used by winter.
        for name, modes in pets._catalog().items():
            for mode, info in modes.items():
                width, height = info['frame_size']
                for direction in ((0, 1) if mode == 'idle' else (1, 2)):
                    with Image.open(pets.ART / info['file']) as source:
                        cells = [source.crop((index * width, direction * height,
                                              (index + 1) * width, (direction + 1) * height)).convert('RGBA')
                                 for index in range(len(info['durations']))]
                    bounds = [box for cell in cells if (box := cell.getchannel('A').getbbox()) is not None]
                    common = (min(box[0] for box in bounds), min(box[1] for box in bounds),
                              max(box[2] for box in bounds), max(box[3] for box in bounds))
                    actual = pets._poses(name, mode, direction)
                    self.assertEqual(len(actual), len(cells))
                    for original, pose in zip(cells, actual):
                        self.assertEqual(pose.tobytes(), original.crop(common).tobytes(),
                                         (name, mode, direction))

    def test_pinned_native_art_is_complete_and_unchanged(self) -> None:
        manifest = json.loads((pets.ART / "sources.json").read_text())
        for name in pets.COLORS:
            for mode, info in manifest["assets"][name].items():
                data = (pets.ART / info["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"])
                self.assertIn(manifest["revision"], info["url"])
                for direction in ((0, 1) if mode == "idle" else (1,)):
                    for image in pets._poses(name, mode, direction):
                        self.assertLessEqual(image.width, info["frame_size"][0])
                        self.assertLessEqual(image.height, info["frame_size"][1])

    def test_all_actions_leave_the_floor_header_and_hud_untouched(self) -> None:
        for name in pets.COLORS:
            for mood in ("unknown", "idle", "busy", "hard"):
                still = designs.sprite(name, 0, mood)
                for f in range(16):
                    image = designs.sprite(name, f, mood, action=f / 15)
                    self.assertEqual(image.size, (64, 32))
                    self.assertEqual(image.crop((0, 29, 64, 32)).tobytes(),
                                     still.crop((0, 29, 64, 32)).tobytes(), (name, mood, f))
                    self.assertFalse(any(image.crop((40, 0, 64, 32)).tobytes()))
                    self.assertFalse(any(image.crop((32, 0, 40, 6)).tobytes()))
                    self.assertFalse(any(image.crop((0, 0, 40, 1)).tobytes()))
                scene = designs.layout(name)["text"]
                self.assertGreaterEqual(scene["name"]["width"], (len(name) + 1) * 4)
                self.assertEqual(scene["metric"]["align"], "right")
                self.assertEqual((scene["metric"]["x"], scene["metric"]["width"]), (40, 24))

    def test_new_pets_are_selectable_with_work_and_play_and_archived_pets_are_hidden(self) -> None:
        self.assertNotIn('ember', designs.DESIGNS)
        self.assertNotIn('sprout', designs.DESIGNS)
        for name in ('cubone', 'ratzfatz', 'ratikarl'):
            self.assertIn(name, designs.DESIGNS)
            idle = [designs.sprite(name, f, 'idle').tobytes() for f in range(16)]
            work = [designs.sprite(name, f, 'hard').tobytes() for f in range(16)]
            play = [designs.sprite(name, f, 'idle', action=f / 15).tobytes() for f in range(16)]
            self.assertGreater(len(set(idle)), 1)
            self.assertGreater(len(set(work)), 3)
            self.assertGreater(len(set(play)), 3)
            self.assertNotEqual(idle, work)
            self.assertNotEqual(idle, play)
            header = designs.layout(name)['text']['name']
            self.assertLessEqual(header['x'] + header['width'], 64)
            for mood in ('idle', 'busy', 'hard'):
                for frame in range(16):
                    for action in (None, frame / 15):
                        image = designs.sprite(name, frame, mood, action=action)
                        self.assertFalse(any(image.crop((header['x'], 0, 64, 6)).tobytes()), (name, mood, frame, action))

    def test_torchic_embers_leave_the_beak_then_disappear(self) -> None:
        palette = ("#BB703D", "#F0B775")
        images = [designs.sprite("torchic", 0, action=f / 15) for f in range(16)]
        self.assertFalse(points(images[0], palette))
        first, later = points(images[4], palette), points(images[8], palette)
        self.assertTrue(first)
        self.assertTrue(later)
        self.assertGreater(max(x for x, _ in later), max(x for x, _ in first) + 3)
        self.assertLess(min(y for _, y in later), min(y for _, y in first))
        self.assertFalse(points(images[15], palette))

    def test_eevee_reaches_its_leaf_and_returns_home(self) -> None:
        leaf = ("#47754B", "#789359", "#A0AD72")
        # Separate the actor from its prop using the actor's original pixels.
        actor_colors = set()
        for mode in ("idle", "walk"):
            for pose in pets._poses("eevee", mode, 1):
                data = pose.tobytes()
                for r, g, b, a in zip(data[::4], data[1::4], data[2::4], data[3::4]):
                    if a and max(r, g, b) > 10:
                        actor_colors.add('#%02X%02X%02X' % (r, g, b))
        distances = []
        centers = []
        for f in (0, 9, 15):
            image = designs.sprite("eevee", 0, action=f / 15)
            actor = points(image, actor_colors)
            prop = points(image, leaf)
            self.assertTrue(actor)
            self.assertTrue(prop)
            distances.append(min((x - a)**2 + (y - b)**2 for x, y in actor for a, b in prop))
            centers.append(min(x for x, _ in actor))
        self.assertLessEqual(distances[1], 2)
        self.assertGreater(distances[0], distances[1])
        self.assertEqual(centers[0], centers[2])

    def test_treecko_tosses_its_stick_above_its_hand_and_catches_it(self) -> None:
        twig = ("#554030", "#B48A59")
        masks = [points(designs.sprite("treecko", 0, action=f / 15), twig)
                 for f in (0, 8, 12, 15)]
        self.assertTrue(all(masks))
        self.assertLess(max(y for _, y in masks[1]), min(y for _, y in masks[0]))
        # The catching wrist yields slightly, then settles back to its grip.
        self.assertLessEqual(abs(max(y for _, y in masks[0]) - max(y for _, y in masks[2])), 2)
        self.assertEqual(masks[0], masks[3])
        for mood in ("unknown", "idle", "busy", "hard"):
            for f in range(16):
                self.assertTrue(points(designs.sprite("treecko", f, mood), twig))

    def test_treecko_keeps_its_feet_planted_while_moving_its_hand_and_stick(self) -> None:
        still = designs.sprite("treecko", 0)
        feet = still.crop((9, 26, 28, 29)).tobytes()
        for mood in ("idle", "busy", "hard"):
            frames = [designs.sprite("treecko", f, mood) for f in range(16)]
            for image in frames:
                self.assertEqual(image.crop((9, 26, 28, 29)).tobytes(), feet)
            self.assertGreater(len({image.tobytes() for image in frames}), 1)

    def test_a_runs_a_complete_trick_with_real_metrics_and_resets_on_switch(self) -> None:
        press = canvas.ButtonEvent(1, 10, frozenset({'a'}), frozenset({'a'}), frozenset(), True)
        state = canvas.ButtonState(frozenset({'a'}), True, (press,), False, False, 0, 10)
        activity = pixel_companion.Activity(7, "CPU", "idle")
        for name in pets.COLORS:
            companion = pixel_companion.Companion(name)
            companion.buttons(state)
            client = MagicMock()
            # A newly received press must survive a slow previous host interval.
            companion.update(client, activity, 2)
            frames = []
            for _ in range(16):
                companion.update(client, activity, pets.ACTION_SECONDS / 16)
                frames.append(client.frame.call_args.args[0])
            self.assertGreater(len(set(frames)), 8)
            self.assertIn(("metric", "7%"), [call.args for call in client.text.call_args_list])
            self.assertIn(("mood", "CPU"), [call.args for call in client.text.call_args_list])
            self.assertIn(("demo", "PLAY"), [call.args for call in client.text.call_args_list])
            companion.update(client, activity, 1)
            self.assertEqual(companion.action_remaining, 0)
            self.assertEqual(companion.last["demo"], "IDLE")
            companion.buttons(state)
            right = canvas.ButtonEvent(2, 20, frozenset({'right'}), frozenset({'right'}), frozenset(), True)
            companion.buttons(canvas.ButtonState(frozenset(), True, (right,), False, False, 0, 20))
            self.assertEqual(companion.action_remaining, 0)
            self.assertFalse(companion.action_pending)


class RescuePetSimulatorTests(unittest.TestCase):
    def test_each_pet_action_reaches_the_real_canvas_renderer(self) -> None:
        root = Path(__file__).resolve().parents[2]
        binary = root / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        for name in pets.COLORS:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                snapshot = Path(directory) / "pet.ppm"
                process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                            "--frames", "100", "--snapshot", str(snapshot)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    line = process.stdout.readline().strip()
                    self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                    with canvas.Client("tcp://" + line.split()[-1]) as client:
                        companion = pixel_companion.Companion(name)
                        activity = pixel_companion.Activity(7, "CPU", "idle")
                        companion.install(client, activity)
                        companion.action_remaining = pets.ACTION_SECONDS
                        companion.action_pending = True
                        companion.update(client, activity, 0)
                        companion.update(client, activity, pets.ACTION_SECONDS * .6)
                        expected = canvas.image_frame(designs.sprite(
                            name, int(companion.phase), "idle", action=.6))
                    stdout, stderr = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    with Image.open(snapshot) as image:
                        rendered = image.convert("RGB")
                    raw = rendered.tobytes()
                    actual = [canvas.color565('#%02X%02X%02X' % pixel)
                              for pixel in zip(raw[::3], raw[1::3], raw[2::3])]
                    wanted = struct.unpack('<2048H', expected)
                    # Actor/prop pixels survive the real wire codec and render.
                    self.assertEqual([actual[y*64+x] for y in range(32) for x in range(28)],
                                     [wanted[y*64+x] for y in range(32) for x in range(28)])
                    # Full-width names, the fixed right-aligned percentage and
                    # PLAY status really appear, rather than an offline mock HUD.
                    last_glyph = 56
                    self.assertTrue(any(actual[y*64+x] for y in range(6)
                                        for x in range(last_glyph, last_glyph + 4)))
                    self.assertFalse(any(actual[y*64+x] for y in range(6) for x in range(60, 64)))
                    # Animation exports must preserve the first letters of the
                    # wider title as well as the usual right-hand HUD columns.
                    preview = designs.preview_frame(designs.sprite(name, 0), rendered, name)
                    self.assertEqual(preview.crop((32, 0, 64, 6)).tobytes(),
                                     rendered.crop((32, 0, 64, 6)).tobytes())
                    self.assertFalse(any(actual[y*64+x] for y in range(8, 18) for x in range(40, 52)))
                    self.assertTrue(any(actual[y*64+x] for y in range(8, 18) for x in range(58, 64)))
                    self.assertTrue(any(actual[y*64+x] for y in range(26, 32) for x in range(52, 56)))
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
