"""Full-panel art, seamless loops, controls and real Canvas snapshots; no board."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

from PIL import Image, ImageDraw

from displaitor_tools import canvas, scenes
from displaitor_tools.scenes import hunter, okami, witcher
from displaitor_tools.scenes.actions import layer as action_layer
from displaitor_tools.apps.cozy import Cozy, Settings
from displaitor_tools.paths import ROOT
from displaitor_tools.previews.cozy import previews, quantized


def press(*keys: str, active: bool = True, lost: bool = False) -> canvas.ButtonState:
    held = frozenset(keys)
    event = canvas.ButtonEvent(1, 1, held, held, frozenset(), active)
    return canvas.ButtonState(held, active, (event,), lost, False, 0, 1)


class ArtTests(unittest.TestCase):
    def test_native_rgb565_art_animates_full_panel_and_loops_exactly(self) -> None:
        for name in scenes.NAMES:
            with self.subTest(name=name):
                frames = [canvas.image_frame(scenes.render(name, index / 10)) for index in range(40)]
                self.assertGreater(len(set(frames)), 20)
                self.assertTrue(any(scenes.render(name, 0).crop((40, 0, 64, 32)).tobytes()))
                self.assertEqual(scenes.render(name, 0).size, (64, 32))
                self.assertTrue(all(len(frame) == 4096 for frame in frames))
                for elapsed in (0, .25, 1.5, 9.75):
                    self.assertEqual(scenes.render(name, elapsed).tobytes(),
                                     scenes.render(name, elapsed + scenes.PERIODS[name]).tobytes())
                self.assertEqual(canvas.image_frame(quantized(scenes.render(name, 1.5))), frames[15])

    def test_farm_camera_and_cottage_stay_fixed_while_smoke_and_water_move(self) -> None:
        still = scenes.render('farm', 0)
        frames = [scenes.render('farm', index / 4) for index in range(64)]
        for image in frames:
            self.assertEqual(image.crop((8, 10, 19, 17)).tobytes(), still.crop((8, 10, 19, 17)).tobytes())
            self.assertEqual(image.crop((19, 19, 23, 26)).tobytes(), still.crop((19, 19, 23, 26)).tobytes())
        self.assertGreater(len({image.crop((19, 0, 29, 9)).tobytes() for image in frames}), 8)
        self.assertGreater(len({image.crop((45, 24, 64, 31)).tobytes() for image in frames}), 4)

    def test_foreground_characters_are_large_animate_and_keep_ground_fixed(self) -> None:
        # Check the actors independently: moving petals/fire must not disguise
        # an absent or static character, including after RGB565 quantization.
        for actor in (okami.wolf, witcher.geralt, witcher.leshen):
            with self.subTest(actor=actor.__name__):
                frames: list[Image.Image] = []
                for tick in range(64):
                    layer = Image.new('RGBA', (64, 32))
                    actor(ImageDraw.Draw(layer), tick / 4)
                    bounds = layer.getbbox()
                    self.assertIsNotNone(bounds)
                    assert bounds is not None
                    self.assertGreaterEqual(bounds[2] - bounds[0], 10)
                    self.assertGreaterEqual(bounds[3] - bounds[1], 14)
                    self.assertGreater(sum(bool(alpha) for alpha in layer.getchannel('A').tobytes()), 100)
                    frames.append(quantized(layer.convert('RGB')))
                self.assertGreater(len({image.tobytes() for image in frames}), 2)
                # Ground anchors stay fixed while paws and upper bodies move.
                self.assertEqual(len({image.crop((0, 30, 64, 32)).tobytes() for image in frames}), 1)

    def test_fire_is_over_plain_stone_without_changing_the_backdrop(self) -> None:
        from displaitor_tools.scenes import fire
        stone = fire.background().tobytes()
        # A neutral stone-only backdrop, with no coloured furnishings or props.
        for red, green, blue in zip(stone[::3], stone[1::3], stone[2::3]):
            self.assertEqual(red, green)
            self.assertLessEqual(abs(red - blue), 10)
        frames = [scenes.render('fire', tick / 10) for tick in range(160)]
        self.assertEqual(fire.background().tobytes(), stone)
        self.assertGreater(len({frame.tobytes() for frame in frames}), 100)
        self.assertTrue(any(frame.crop((0, 20, 64, 32)).tobytes() != stone[20 * 64 * 3:]
                            for frame in frames))

    def test_hunter_reactions_keep_terrain_and_feet_fixed_and_do_not_edit_cached_art(self) -> None:
        for name in hunter.NAMES:
            before = hunter.background(name).tobytes()
            ground = scenes.render(name, 1.5).crop((0, 30, 64, 32)).tobytes()
            for tick in range(32):
                overlay = action_layer(name, tick / 10)
                self.assertLessEqual(set(overlay.getchannel('A').tobytes()), {0, 255})
                image = scenes.render(name, 1.5, action=tick / 10)
                self.assertEqual(image.crop((0, 30, 64, 32)).tobytes(), ground, (name, tick))
            self.assertEqual(hunter.background(name).tobytes(), before)
            self.assertIsNone(action_layer(name, 3.2).getbbox())

    def test_hunter_replacement_mask_covers_every_ambient_pose_without_ghosts(self) -> None:
        for name in hunter.NAMES:
            mask = hunter.actor_mask(name).tobytes()
            for tick in range(160):
                alpha = hunter.actor(name, tick).getchannel('A').tobytes()
                self.assertTrue(all(not pixel or mask[index] for index, pixel in enumerate(alpha)), (name, tick))

    def test_sparse_hunter_reactions_match_full_replacement_over_every_ambient_pose(self) -> None:
        for name in hunter.NAMES:
            for action in (.3, 1.1, 2.3, 3.1):
                full = Image.new('RGBA', (64, 32))
                full.paste(hunter.background(name), (0, 0), hunter.actor_mask(name))
                hunter._ACTORS[name](ImageDraw.Draw(full), action, reaction=action)
                sparse = hunter.reaction_layer(name, action)
                for tick in range(80):
                    ambient = hunter.render(name, tick / 10)
                    expected = ambient.copy()
                    expected.paste(full, (0, 0), full.getchannel('A'))
                    ambient.paste(sparse, (0, 0), sparse.getchannel('A'))
                    self.assertEqual(ambient.tobytes(), expected.tobytes(), (name, tick, action))

    def test_scene_time_and_name_validation(self) -> None:
        for elapsed in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                scenes.render('farm', elapsed)
        with self.assertRaises(ValueError):
            scenes.render('invalid', 0)
        for settings in ({'fps': 0}, {'fps': float('nan')}, {'timeout': 0}, {'frames': 0}, {'scene': 'invalid'}):
            with self.assertRaises(ValueError):
                Settings(**settings)

    def test_gallery_exports_every_scene_with_exact_loop_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previews(directory, scale=1)
            with Image.open(Path(directory) / 'scenes.png') as image:
                self.assertEqual(image.size, (64, len(scenes.NAMES) * 58))
            for name in scenes.NAMES:
                with Image.open(Path(directory) / (name + '-native.gif')) as gif:
                    self.assertEqual(gif.size, (64, 32))
                    self.assertEqual(gif.info['loop'], 0)
                    duration = 0
                    for index in range(gif.n_frames):
                        gif.seek(index)
                        duration += gif.info['duration']
                    self.assertEqual(duration, scenes.PERIODS[name] * 1000)
            for invalid in ((), ('missing',)):
                with self.assertRaises(ValueError):
                    previews(directory, names=invalid)


class SceneTests(unittest.TestCase):
    def test_all_python_scenes_cycle_while_paused_without_reopening_canvas(self) -> None:
        scene, client = Cozy(), MagicMock()
        scene.install(client)
        scene.buttons(press('up'))
        client.reset_mock()
        for expected in (*scenes.NAMES[1:], scenes.NAMES[0]):
            scene.buttons(press('right'))
            scene.update(client, 10)
            self.assertEqual(scene.name, expected)
            self.assertEqual(scene.elapsed, 0)
            self.assertTrue(scene.paused)
        self.assertEqual(client.frame.call_count, len(scenes.NAMES))
        client.layout.assert_not_called()
        client.show.assert_not_called()

    def test_fullscreen_install_removes_hud_and_updates_never_show_again(self) -> None:
        scene, client = Cozy(), MagicMock()
        scene.install(client)
        client.layout.assert_called_once_with({'text': {}})
        client.show.assert_called_once()
        client.reset_mock()
        scene.buttons(press('right'))
        scene.update(client, .25)
        self.assertEqual(scene.name, 'winter')
        client.frame.assert_called_once_with(canvas.image_frame(scenes.render('winter', .25)))
        client.show.assert_not_called()
        client.layout.assert_not_called()
        client.transaction.assert_not_called()  # One atomic full-frame command.

    def test_pause_freezes_time_and_uploads_but_still_allows_scene_switching(self) -> None:
        scene, client = Cozy(), MagicMock()
        scene.install(client)
        scene.buttons(press('up'))
        before = scene.elapsed
        client.reset_mock()
        scene.update(client, 10)
        self.assertEqual(scene.elapsed, before)
        client.frame.assert_not_called()
        scene.buttons(press('right'))
        scene.update(client, 10)
        self.assertEqual(scene.name, 'winter')
        self.assertEqual(scene.elapsed, 0)
        client.frame.assert_called_once()
        scene.buttons(press('down'))
        scene.update(client, .5)
        self.assertEqual(scene.elapsed, .5)
        scene.buttons(press('left'))
        self.assertEqual(scene.name, 'farm')

    def test_invalid_inactive_lost_and_held_only_buttons_do_not_change_scene(self) -> None:
        scene = Cozy()
        for invalid in (press('right', active=False), press('right', lost=True), press('left', 'right'), press(), press('up', 'down'), press('b')):
            scene.buttons(invalid)
        self.assertEqual(scene.name, 'farm')
        self.assertFalse(scene.paused)
        client = MagicMock()
        for elapsed in (-1.0, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                scene.update(client, elapsed)
        client.frame.assert_not_called()
        self.assertEqual(scene.elapsed, 0)

    def test_special_actions_finish_retrigger_and_cancel_without_resetting_ambient(self) -> None:
        for name in scenes.NAMES:
            scene, client = Cozy(name), MagicMock()
            scene.elapsed = 1.5
            scene.install(client)
            scene.buttons(press('up'))
            base = scene.last
            scene.buttons(press('a'))
            scene.update(client, .7)
            self.assertEqual(scene.elapsed, 1.5)
            self.assertNotEqual(scene.last, base, name)
            scene.buttons(press('a'))
            self.assertEqual(scene.action, 0)
            scene.update(client, 3.2)
            self.assertEqual(scene.last, base, name)
            self.assertIsNone(scene.action)
            scene.buttons(press('a'))
            scene.buttons(press('right'))
            self.assertIsNone(scene.action)

    def test_failed_frame_cannot_poison_the_upload_cache(self) -> None:
        scene, client = Cozy(), MagicMock()
        scene.install(client)
        client.frame.side_effect = TimeoutError('uncertain frame acknowledgement')
        with self.assertRaises(TimeoutError):
            scene.update(client, .5)
        self.assertIsNone(scene.last)
        client.reset_mock()
        client.frame.side_effect = None
        scene.update(client, 0)
        client.frame.assert_called_once()

    def test_each_scene_matches_the_real_canvas_framebuffer_and_clears_old_text(self) -> None:
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
        with tempfile.TemporaryDirectory() as directory:
            for name in scenes.NAMES:
                snapshot = Path(directory) / (name + '.ppm')
                process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                            '--frames', '130', '--snapshot', str(snapshot)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    assert process.stdout is not None
                    line = process.stdout.readline().strip()
                    self.assertTrue(line.startswith('Canvas listening on 127.0.0.1:'), line)
                    with canvas.Client('tcp://' + line.split()[-1]) as client:
                        client.layout({'text': {'old': {'x': 0, 'y': 0, 'width': 64, 'height': 10,
                                                       'font': 'medium', 'text': 'OLD HUD', 'color': '#FFFFFF'}}})
                        client.show()
                        scene = Cozy(name)
                        scene.elapsed = 1.5
                        scene.install(client)
                        assert client.info is not None
                        self.assertEqual(client.info['layout_id'], canvas.Layout({'text': {}}).id)
                    stdout, stderr = process.communicate(timeout=6)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    with Image.open(snapshot) as image:
                        self.assertEqual(canvas.image_frame(image), canvas.image_frame(scenes.render(name, 1.5)))
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=3)

    def test_live_launcher_streams_both_scenes_with_real_button_polling(self) -> None:
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
        for name in scenes.NAMES:
            # Keep the server alive through child-interpreter startup, including
            # loaded Windows CI machines. Its lifetime belongs to this test.
            process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0', '--frames', '10000'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                assert process.stdout is not None
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith('Canvas listening on 127.0.0.1:'), line)
                result = subprocess.run([sys.executable, str(ROOT / 'tools/cozy.py'), '--port', 'tcp://' + line.split()[-1],
                                         '--scene', name, '--frames', '3', '--fps', '20'],
                                        cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=6)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Cozy ' + name, result.stdout)
                self.assertIsNone(process.poll(), 'Canvas server exited before the sender finished')
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
