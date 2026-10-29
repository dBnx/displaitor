"""Public command paths stay usable from outside the checkout, without a board."""

from __future__ import annotations
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from displaitor_tools.paths import ROOT


class LauncherTests(unittest.TestCase):
    def run_cli(self, *args: str, bare: bool=False) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run([sys.executable, *(['-S'] if bare else []), str(ROOT / 'tools/run.py'), *args],
                                  cwd=directory, capture_output=True, text=True, timeout=15)

    def test_help_for_live_apps_exports_audio_and_explicit_diagnostics(self) -> None:
        for args in ((), ('companion', '--help'), ('dashboard', '--help'), ('weather', '--help'), ('cozy', '--help'), ('pictures', '--help'),
                     ('canvas', '--help'), ('new-scene', '--help'), ('audio', 'synth', '--help'), ('audio', 'fixtures', '--help'), ('preview', '--help'),
                     ('assets', 'cozy', '--help'),
                     ('preview', 'stats', '--help'), ('preview', 'designs', '--help'),
                     ('preview', 'activity', '--help'), ('preview', 'play', '--help'),
                     ('preview', 'weather', '--help'),
                     ('preview', 'cozy', '--help'),
                     ('preview', 'alternatives', '--help'), ('preview', 'collections', '--help'),
                     ('hardware', 'audio', '--help')):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_audio_generation_needs_no_compiler_header_or_third_party_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli('audio', 'synth', '--output-dir', directory, bare=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for pet in ('torchic', 'eevee', 'treecko'):
                name = 'cry_' + pet + '.qoa'
                self.assertEqual((Path(directory) / name).read_bytes(), (ROOT / 'assets/audio' / name).read_bytes())

    def test_old_user_facing_launchers_still_accept_the_same_options(self) -> None:
        for name in ('pixel_companion', 'weather', 'pc_hub', 'canvas', 'cozy', 'pictures'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable, str(ROOT / 'tools' / (name + '.py')), '--help'],
                                        cwd=directory, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--port', result.stdout)

    def test_documented_sdk_import_remains_available_from_the_checkout_root(self) -> None:
        result = subprocess.run([sys.executable, '-c',
                                 'from tools.canvas import Client, Layout, ButtonState; assert callable(Client)'],
                                cwd=ROOT, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_command_or_pet_is_rejected_without_connecting(self) -> None:
        self.assertEqual(self.run_cli('nonexistent').returncode, 2)
        result = self.run_cli('companion', '--design', 'nonexistent')
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid choice', result.stderr)


if __name__ == '__main__':
    unittest.main()
