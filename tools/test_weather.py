"""Condition-driven weather art, scene publication, and real Rust rendering."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import canvas
import weather

ROOT = Path(__file__).resolve().parents[1]


class WeatherTests(unittest.TestCase):
    def test_condition_text_and_precedence(self):
        for text, expected in (
            ("Rain soon", "rain"), ("LIGHT SHOWERS", "rain"),
            ("Cloudy with rain", "rain"), ("Snow showers", "snow"),
            ("Thunderstorm with rain", "storm"), ("Partly cloudy", "partly"),
            ("Overcast", "cloudy"), ("Foggy", "fog"), ("Sunny", "sunny"),
            ("Clear night", "night"), ("Cloudy night", "cloudy"),
            ("No rain", "unknown"), ("No rain or snow", "unknown"),
            ("No chance of rain", "unknown"), ("No thunderstorms", "unknown"),
            ("Rain-free, sunny", "sunny"),
            ("Waiting for data", "unknown"), ("", "unknown"),
        ):
            with self.subTest(text=text):
                self.assertEqual(weather.condition(text), expected)

    def test_animation_stays_clear_of_every_text_box_and_is_periodic(self):
        kinds = set()
        for status in (*weather.EXAMPLES, "Waiting"):
            kinds.add(weather.condition(status))
            frames = []
            for phase in range(weather.FRAMES):
                image = weather.sprite(status, phase)
                self.assertEqual(image.size, (64, 32))
                self.assertIsNone(image.crop((0, 0, 40, 32)).getbbox())
                self.assertIsNone(image.crop((0, 24, 64, 32)).getbbox())
                frames.append(image.tobytes())
            self.assertGreater(len(set(frames)), 1, status)
            self.assertEqual(frames[0], weather.sprite(status, weather.FRAMES).tobytes())
        self.assertEqual(len(kinds), 9)

    def test_rain_falls_down_while_cloud_and_text_stay_in_place(self):
        first = weather.sprite("Rain soon", 0)
        second = weather.sprite("Rain soon", 1)
        # Only the falling drops move on these consecutive frames.
        self.assertEqual(first.crop((40, 0, 64, 17)).tobytes(),
                         second.crop((40, 0, 64, 17)).tobytes())
        rain = (88, 147, 160)
        self.assertEqual(first.getpixel((45, 18)), rain)
        self.assertEqual(second.getpixel((45, 18)), (0, 0, 0))
        self.assertEqual(second.getpixel((45, 20)), rain)
        self.assertNotEqual(first.tobytes(), weather.sprite("Sunny", 0).tobytes())

    def test_snow_has_falling_flakes_instead_of_rain(self):
        first = weather.sprite("Snow showers", 0)
        later = weather.sprite("Snow showers", 2)
        snow = (145, 178, 172)
        self.assertEqual(first.getpixel((45, 18)), snow)
        self.assertEqual(later.getpixel((45, 19)), snow)
        self.assertEqual(later.getpixel((45, 18)), (0, 0, 0))
        self.assertNotEqual(first.tobytes(), weather.sprite("Rain soon", 0).tobytes())

    def test_update_changes_text_and_matching_art_together_without_show(self):
        app, client = weather.Weather(), MagicMock()
        app.install(client)
        client.show.assert_called_once()
        client.reset_mock()
        app.update(client, 0, temperature="21°C", status="Snow")
        self.assertEqual(client.frame.call_args.args[0], canvas.image_frame(weather.sprite("Snow", 0)))
        self.assertEqual([call.args for call in client.text.call_args_list],
                         [("temperature", "21°C"), ("status", "Snow")])
        client.transaction.assert_called_once()
        client.show.assert_not_called()
        client.layout.assert_not_called()
        client.reset_mock()
        app.update(client, 0)  # Do not resend identical text/background.
        client.frame.assert_not_called()
        client.text.assert_not_called()

    def test_invalid_reading_never_mutates_scene_and_commit_failure_clears_cache(self):
        app, client = weather.Weather(), MagicMock()
        original = (app.temperature, app.status)
        with self.assertRaises(ValueError):
            app.update(client, 1, status="bad\ntext")
        with self.assertRaisesRegex(ValueError, "fits at most 6"):
            app.update(client, 1, temperature="-1234°C")
        self.assertEqual((app.temperature, app.status), original)
        client.transaction.assert_not_called()
        client.transaction.return_value.__exit__.side_effect = TimeoutError("commit outcome unknown")
        with self.assertRaises(TimeoutError):
            app.update(client, 0, status="Sunny")
        self.assertEqual(app.last, {})
        client.transaction.return_value.__exit__.side_effect = None
        client.reset_mock()
        app.install(client)  # Reconnect must install the latest complete scene.
        self.assertEqual(client.layout.call_args.args[0]["text"]["status"]["text"], "Sunny")
        self.assertEqual(client.frame.call_args.args[0], canvas.image_frame(weather.sprite("Sunny", 0)))

    def test_permanent_setup_errors_fail_instead_of_retrying(self):
        args = SimpleNamespace(temperature=None, status=None, port="unused-test-device", timeout=3, frames=None)
        for message in ("serial support needs: pip install -r tools/requirements.txt",
                        "firmware update required: this board does not support Canvas transactions"):
            with patch("weather.resolve_port", return_value="unused-test-device"), \
                 patch("weather.Client", side_effect=RuntimeError(message)) as client_type, \
                 patch("weather.time.sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError, message):
                    weather.run(args)
                client_type.assert_called_once()
                sleep.assert_not_called()

    def test_rain_icon_survives_actual_firmware_text_backgrounds(self):
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "weather.ppm"
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "75", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                with canvas.Client("tcp://" + line.split()[-1]) as client:
                    weather.Weather().install(client)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                with Image.open(snapshot) as rendered:
                    # Opaque title/temperature boxes must leave the art visible.
                    raw = canvas.image_frame(weather.sprite("Rain soon", 0))
                    actual = canvas.image_frame(rendered)
                    for y in range(24):
                        start, end = 2 * (y * 64 + 40), 2 * (y * 64 + 64)
                        self.assertEqual(actual[start:end], raw[start:end])
                    self.assertIsNotNone(rendered.crop((0, 25, 64, 31)).getbbox())
                    self.assertIsNotNone(rendered.crop((0, 9, 38, 19)).getbbox())
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
