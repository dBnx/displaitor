"""Render changing numeric widths through the real Canvas stack."""

from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from displaitor_tools import canvas as canvas
from displaitor_tools.companions import designs as companion_designs
from displaitor_tools.apps import pc_hub as pc_hub
from displaitor_tools.apps import weather as weather

ROOT = Path(__file__).resolve().parents[2]


class AlignmentTests(unittest.TestCase):
    def test_all_live_numeric_fields_declare_right_alignment(self) -> None:
        hub = canvas.Layout(pc_hub.LAYOUT)
        for name in pc_hub.METRICS:
            for text in ("1%", "10%", "100%", "--%"):
                self.assertEqual(len(hub.encode_text(name, text)), 4)
        for text in ("0 MiB", "4.2 GiB", "512 MiB", "24 GiB", "--"):
            self.assertEqual(len(hub.encode_text("vram", text)), 10)
        for design in companion_designs.DESIGNS:
            pet = canvas.Layout(companion_designs.layout(design))
            self.assertEqual(pet.encode_text("metric", "1%"), b"  1%")
            self.assertEqual(pet.encode_text("metric", "100%"), b"100%")

    def test_rendered_units_and_temperature_digits_stay_fixed_and_shrinking_clears_old_glyphs(self) -> None:
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        scene = {"text": {
            "metric": copy.deepcopy(companion_designs.layout("orbit")["text"]["metric"]),
            "temperature": json.loads(weather.LAYOUT.read_text())["text"]["temperature"],
        }}

        def render(directory: str | Path, name: str, metric: str, temperature: str, *, shrink: bool=False) -> Image.Image:
            snapshot = Path(directory) / (name + ".ppm")
            source = copy.deepcopy(scene)
            source["text"]["metric"]["text"] = metric
            source["text"]["temperature"]["text"] = temperature
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "75", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                with canvas.Client("tcp://" + line.split()[-1]) as client:
                    client.layout(source)
                    client.fill("#000000")
                    client.show()
                    if shrink:
                        with client.transaction():
                            client.text("metric", "1%")
                            client.text("temperature", "18°C")
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                with Image.open(snapshot) as image:
                    return image.convert("RGB")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)

        with tempfile.TemporaryDirectory() as directory:
            wide = render(directory, "wide", "100%", "-18°C")
            shrunk = render(directory, "shrunk", "100%", "-18°C", shrink=True)
            fresh = render(directory, "fresh", "1%", "18°C")
            self.assertEqual(shrunk.tobytes(), fresh.tobytes())
            # Last medium cell is always %, regardless of numeric digit count.
            self.assertEqual(wide.crop((58, 8, 64, 18)).tobytes(), shrunk.crop((58, 8, 64, 18)).tobytes())
            self.assertIsNotNone(shrunk.crop((58, 8, 64, 18)).getbbox())
            # A negative sign uses reserved space; 18°C itself does not move.
            self.assertEqual(wide.crop((14, 9, 38, 19)).tobytes(), shrunk.crop((14, 9, 38, 19)).tobytes())
            self.assertIsNotNone(wide.crop((8, 9, 14, 19)).getbbox())
            self.assertIsNone(shrunk.crop((8, 9, 14, 19)).getbbox())


if __name__ == "__main__":
    unittest.main()
