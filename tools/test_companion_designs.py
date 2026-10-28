"""Exercise the design launcher through the real loopback protocol and renderer."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

import canvas
import companion_designs

ROOT = Path(__file__).resolve().parents[1]


class CompanionSimulatorTests(unittest.TestCase):
    def test_legacy_sender_uses_live_activity_without_demo_fixture_labels(self):
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "companion.ppm"
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "600", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                result = subprocess.run([sys.executable, str(ROOT / "tools/companion_designs.py"),
                                         "--port", "tcp://" + line.split()[-1], "--design", "sprout",
                                         "--frames", "8", "--fps", "10", "--gpu", "none"],
                                        capture_output=True, text=True, timeout=9)
                self.assertEqual(result.returncode, 0, result.stderr)
                stdout, stderr = process.communicate(timeout=9)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                with Image.open(snapshot) as image:
                    self.assertEqual(image.size, (64, 32))
                    pixels = image.convert("RGB").tobytes()
                    actual = [canvas.color565("#%02X%02X%02X" % pixel)
                              for pixel in zip(pixels[0::3], pixels[1::3], pixels[2::3])]
                possible = []
                for mood in ("idle", "busy", "hard"):
                    for frame in range(16):
                        words = struct.unpack("<2048H", canvas.image_frame(
                            companion_designs.sprite("sprout", frame, mood)))
                        possible.append([words[y*64+x] for y in range(32) for x in range(40)])
                self.assertIn([actual[y*64+x] for y in range(32) for x in range(40)], possible)
                # The CPU label occupies three fixed glyphs above the status.
                self.assertTrue(any(actual[y*64+x] for y in range(20, 26) for x in range(48, 52)))
                self.assertFalse(any(actual[y*64+x] for y in range(20, 26) for x in range(52, 64)))
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
