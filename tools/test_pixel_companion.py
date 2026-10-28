"""Workload semantics, stale data, and real Python-to-Rust companion rendering."""
from datetime import datetime
import io
from pathlib import Path
from types import SimpleNamespace
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

import canvas
import companion_designs
import pc_hub
import pixel_companion

ROOT = Path(__file__).resolve().parents[1]


def sample(cpu=None, gpu=None, ram=99):
    return pc_hub.Sample(cpu, ram, gpu, datetime.now())


class WorkloadTests(unittest.TestCase):
    def test_old_firmware_disables_button_polling_once_but_keeps_live_frames(self):
        args = SimpleNamespace(demo=False, demo_load=None, gpu="none", interval=.2,
                               load="auto", design="orbit", frames=3, fps=20,
                               port="unused-test-device", timeout=3, no_buttons=False)
        with patch("pixel_companion.Client") as client_type, \
             patch("pixel_companion.Readings") as readings_type, \
             patch("pixel_companion.resolve_port", return_value="unused-test-device"), \
             patch("pixel_companion.time.sleep"), \
             patch("pixel_companion.sys.stderr", new_callable=io.StringIO) as errors:
            client = client_type.return_value.__enter__.return_value
            client.buttons.side_effect = NotImplementedError("old firmware")
            readings_type.return_value.__enter__.return_value.get.return_value = sample(5)
            pixel_companion.run(args)
            self.assertEqual(client.buttons.call_count, 1)
            self.assertEqual(client.frame.call_count, 3)
            self.assertEqual(errors.getvalue().count("updated firmware"), 1)
            self.assertIn(('demo', 'CPU'), [call.args for call in client.text.call_args_list])

    def test_retained_presses_cycle_pets_once_and_keep_local_back_priority(self):
        def event(sequence, *pressed, active=True):
            return canvas.ButtonEvent(sequence, sequence * 10, frozenset(pressed),
                                      frozenset(pressed), frozenset(), active)

        def state(*events, active=True, lost=False):
            return canvas.ButtonState(frozenset(), active, events, lost, False, 0, 100)

        companion = pixel_companion.Companion("orbit")
        self.assertTrue(companion.buttons(state(event(1, 'right'), event(2), event(3, 'right'))))
        self.assertEqual(companion.design, "sprout")
        self.assertFalse(companion.buttons(state(event(4))))  # Held, without a new press.
        self.assertTrue(companion.buttons(state(event(5, 'right'))))
        self.assertEqual(companion.design, "torchic")
        for sequence, design in enumerate(("eevee", "treecko", "orbit"), 20):
            self.assertTrue(companion.buttons(state(event(sequence, 'right'))))
            self.assertEqual(companion.design, design)
        self.assertTrue(companion.buttons(state(event(24, 'left'))))
        self.assertEqual(companion.design, "treecko")
        self.assertTrue(companion.buttons(state(event(25, 'right'))))
        self.assertEqual(companion.design, "orbit")
        for report in (state(event(6, 'left'), active=False),
                       state(event(7, 'right'), lost=True),
                       state(event(8, 'left', 'right')),
                       state(event(9, 'left', active=False))):
            self.assertFalse(companion.buttons(report))
            self.assertEqual(companion.design, "orbit")
        client = MagicMock()
        companion.install(client, pixel_companion.Activity(5, 'CPU', 'idle'), activate=False)
        client.show.assert_not_called()  # A late Back can never be undone by switching pets.

    def test_a_action_animates_without_faking_activity_and_expires(self):
        companion = pixel_companion.Companion("orbit")
        event = canvas.ButtonEvent(1, 10, frozenset({'a'}), frozenset({'a'}), frozenset(), True)
        state = canvas.ButtonState(frozenset({'a'}), True, (event,), False, False, 0, 10)
        self.assertFalse(companion.buttons(state))  # Same layout; action needs only an update.
        self.assertGreater(companion.action_remaining, 0)
        client = MagicMock()
        activity = pixel_companion.Activity(5, 'CPU', 'idle')
        # Even a slow host interval before this press cannot expire the new
        # action before its first visible frame.
        companion.update(client, activity, 2)
        calls = [call.args for call in client.text.call_args_list]
        self.assertIn(('metric', '5%'), calls)
        self.assertIn(('demo', 'CPU'), calls)
        self.assertIn(('mood', 'PLAY'), calls)
        normal = pixel_companion.Companion("orbit")
        other = MagicMock()
        normal.update(other, activity, 2)
        self.assertNotEqual(client.frame.call_args.args[0], other.frame.call_args.args[0])
        actual = client.frame.call_args.args[0]
        expected = other.frame.call_args.args[0]
        self.assertEqual(actual[31*64*2:], expected[31*64*2:])
        shadow = canvas.color565('#101C24')
        shadow_rows = {i // 64 for i, value in enumerate(struct.unpack('<2048H', actual)) if value == shadow}
        self.assertTrue(shadow_rows)
        self.assertLessEqual(shadow_rows, {29, 30})
        client.reset_mock()
        companion.update(client, activity, 2)
        self.assertEqual(companion.action_remaining, 0)
        self.assertIn(('mood', 'IDLE'), [call.args for call in client.text.call_args_list])

    def test_commit_failure_invalidates_companion_cache(self):
        client = MagicMock()
        client.transaction.return_value.__exit__.side_effect = TimeoutError("commit outcome unknown")
        companion = pixel_companion.Companion("ember")
        activity = pixel_companion.Activity(45, "CPU", "busy", True)
        with self.assertRaisesRegex(TimeoutError, "commit outcome unknown"):
            companion.update(client, activity, 0)
        self.assertEqual(companion.last, {})
        client.transaction.return_value.__exit__.side_effect = None
        client.reset_mock()
        companion.update(client, activity, 0)
        self.assertEqual(client.text.call_count, 3)
        self.assertEqual(client.style.call_count, 3)

    def test_real_activity_uses_busiest_counter_and_hysteresis_not_ram(self):
        activity = pixel_companion.Workload()
        self.assertEqual(activity.update(sample(5, 10)).mood, "idle")
        busy = activity.update(sample(10, 45))
        self.assertEqual((busy.source, busy.value, busy.mood), ("GPU", 45, "busy"))
        self.assertEqual(activity.update(sample(18)).mood, "busy")
        self.assertEqual(activity.update(sample(14)).mood, "idle")
        self.assertEqual(activity.update(sample(65)).mood, "hard")
        self.assertEqual(activity.update(sample(56)).mood, "hard")
        self.assertEqual(activity.update(sample(54)).mood, "busy")
        self.assertEqual(activity.update(sample(3, 99)).source, "GPU")
        self.assertEqual(pixel_companion.Workload("cpu").update(sample(3, 99)).mood, "idle")
        self.assertEqual(pixel_companion.Workload("gpu").update(sample(99, 3)).value, 3)

    def test_unknown_or_expired_readings_do_not_mean_idle(self):
        activity = pixel_companion.Workload()
        activity.update(sample(99))
        for reading in (None, sample(), sample(float("nan"), 101)):
            result = activity.update(reading)
            self.assertEqual((result.value, result.mood), (None, "unknown"))
        self.assertEqual(activity.update(sample(None, 0)).value, 0)
        readings = pixel_companion.Readings(lambda: None, 1)
        readings.latest, readings.received = sample(99), 10
        with patch("pixel_companion.time.monotonic", return_value=15):
            self.assertEqual(readings.get().cpu, 99)
        with patch("pixel_companion.time.monotonic", return_value=17):
            self.assertIsNone(readings.get())
        readings.error = ""
        with self.assertRaises(RuntimeError):
            readings.get()

    def test_every_exercise_frame_keeps_the_text_region_black(self):
        for design in companion_designs.DESIGNS:
            for mood in ("idle", "busy", "hard", "unknown"):
                for frame in range(16):
                    image = companion_designs.sprite(design, frame, mood)
                    self.assertEqual(image.size, (64, 32))
                    self.assertFalse(any(image.crop((40, 0, 64, 32)).tobytes()),
                                     (design, mood, frame))

    def test_hopping_moves_only_actor_geometry_and_keeps_ground_and_stars_fixed(self):
        for design in companion_designs.DESIGNS:
            for mood in ('idle', 'busy', 'hard'):
                for frame in range(16):
                    normal = companion_designs.sprite(design, frame, mood)
                    for hop in (1, 2, 3):
                        action = companion_designs.sprite(design, frame, mood, hop=hop)
                        self.assertEqual(action.crop((0, 31, 64, 32)).tobytes(),
                                         normal.crop((0, 31, 64, 32)).tobytes())
                        for point in ((3, 4), (34, 7)):
                            self.assertEqual(action.getpixel(point), normal.getpixel(point))
                        self.assertFalse(any(action.crop((40, 0, 64, 32)).tobytes()))

    def test_sampler_is_primed_and_used_on_same_background_thread(self):
        initialized = []
        sampled = threading.Event()
        caller = threading.get_ident()

        class Sampler:
            def __init__(self):
                initialized.append(threading.get_ident())

            def sample(self):
                self_test.assertEqual(initialized, [threading.get_ident()])
                sampled.set()
                return sample(42)

        self_test = self
        with pixel_companion.Readings(Sampler, .2) as readings:
            self.assertTrue(readings.ready.wait(2))
            self.assertTrue(sampled.is_set())
            self.assertEqual(readings.get().cpu, 42)
            self.assertNotEqual(initialized[0], caller)


class CompanionSimulatorTests(unittest.TestCase):
    def footer_mask(self, binary, text, directory):
        snapshot = Path(directory) / "expected.ppm"
        process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                    "--frames", "60", "--snapshot", str(snapshot)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stdout.readline().strip()
            self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
            with canvas.Client("tcp://" + line.split()[-1]) as client:
                client.layout({"text": {"footer": dict(x=40, y=26, width=24, height=6,
                                                       font="small", color="#FFFFFF", text=text)}})
                client.fill("#000000")
                client.show()
            stdout, stderr = process.communicate(timeout=4)
            self.assertEqual(process.returncode, 0, stdout + stderr)
            with Image.open(snapshot) as image:
                return [image.getpixel((x, y)) != (0, 0, 0) for y in range(26, 32) for x in range(40, 64)]
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=3)

    def test_live_and_demo_cli_render_their_actual_activity_without_fixture_leakage(self):
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        for mode in ("live", "demo"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                snapshot = Path(directory) / "companion.ppm"
                process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                            "--frames", "600", "--snapshot", str(snapshot)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    line = process.stdout.readline().strip()
                    self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                    command = [sys.executable, str(ROOT / "tools/pixel_companion.py"), "--port", "tcp://" + line.split()[-1],
                               "--design", "ember", "--frames", "8", "--fps", "10", "--gpu", "none"]
                    if mode == "demo":
                        command += ["--demo-load", "95"]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=7)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    stdout, stderr = process.communicate(timeout=7)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    with Image.open(snapshot) as image:
                        pixels = image.convert("RGB").tobytes()
                    actual = [canvas.color565("#%02X%02X%02X" % rgb)
                              for rgb in zip(pixels[0::3], pixels[1::3], pixels[2::3])]
                    left = [actual[y*64+x] for y in range(32) for x in range(40)]
                    possible = []
                    for mood in (("hard",) if mode == "demo" else ("idle", "busy", "hard")):
                        for frame in range(16):
                            raw = canvas.image_frame(companion_designs.sprite("ember", frame, mood))
                            words = struct.unpack("<2048H", raw)
                            possible.append([words[y*64+x] for y in range(32) for x in range(40)])
                    self.assertIn(left, possible)
                    footer = [actual[y*64+x] for y in range(26, 32) for x in range(40, 64)]
                    expected_text = "DEMO" if mode == "demo" else "CPU"
                    color = "#FF665E" if mode == "demo" else None
                    self.assertGreater(sum(pixel != 0 for pixel in footer), 10)
                    if color:
                        self.assertEqual({pixel for pixel in footer if pixel}, {canvas.color565(color)})
                    self.assertEqual([pixel != 0 for pixel in footer],
                                     self.footer_mask(binary, expected_text, directory))
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
