"""Photo fitting, orientation, alpha, browsing and slideshow timing."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from displaitor_tools import ButtonEvent, ButtonState
from displaitor_tools.apps.pictures import Pictures, fit_image


def report(*pressed: str, active: bool = True, lost: bool = False) -> ButtonState:
    keys = frozenset(pressed)
    return ButtonState(keys, active, (ButtonEvent(1, 10, keys, keys, frozenset(), active),), lost, False, 0, 10)


class PictureTests(unittest.TestCase):
    def test_auto_only_stretches_near_panel_aspect(self) -> None:
        near = Image.new('RGB', (200, 105), 'red')
        self.assertEqual(fit_image(near).getbbox(), (0, 0, 64, 32))
        self.assertNotEqual(fit_image(near, 'contain').getbbox(), (0, 0, 64, 32))
        square = fit_image(Image.new('RGB', (100, 100), 'red'))
        self.assertEqual(square.size, (64, 32))
        self.assertEqual(square.getbbox(), (16, 0, 48, 32))
        self.assertEqual(fit_image(Image.new('RGB', (100, 300), 'red')).getbbox(), (26, 0, 37, 32))

    def test_cover_crops_centrally_and_never_exposes_outer_stripes(self) -> None:
        source = Image.new('RGB', (32, 64), 'blue')
        source.paste('red', (0, 24, 32, 40))
        frame = fit_image(source, 'cover')
        self.assertEqual(frame.getpixel((32, 16)), (255, 0, 0))
        self.assertEqual(frame.getbbox(), (0, 0, 64, 32))

    def test_exif_is_applied_before_fitting_and_alpha_goes_onto_black(self) -> None:
        source = Image.new('RGB', (32, 64), 'red')
        source.getexif()[274] = 6
        self.assertEqual(fit_image(source).getbbox(), (0, 0, 64, 32))
        translucent = Image.new('RGBA', (64, 32), (200, 100, 50, 128))
        frame = fit_image(translucent)
        self.assertEqual(frame.mode, 'RGB')
        self.assertEqual(frame.getpixel((0, 0)), (100, 50, 25))
        self.assertEqual(fit_image(Image.new('RGBA', (64, 32))).getpixel((0, 0)), (0, 0, 0))

    def test_manual_controls_wrap_and_do_not_reload_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{i}.png' for i in range(3)]
            for path, color in zip(paths, ('red', 'green', 'blue')):
                Image.new('RGB', (80, 40), color).save(path)
            pictures = Pictures(paths)
            for path in paths:
                path.unlink()
            with patch('PIL.Image.open', side_effect=AssertionError('decoded twice')):
                pictures.on_buttons(report('left'))
                self.assertEqual(pictures.render(0).getpixel((0, 0)), (0, 0, 255))
                pictures.on_buttons(report('right'))
                self.assertEqual(pictures.index, 0)
                pictures.on_buttons(report('a'))
                self.assertEqual(pictures.index, 1)
                for state in (report('right', lost=True), report('right', active=False), report('b', 'right'), report('left', 'right')):
                    pictures.on_buttons(state)
                    self.assertEqual(pictures.index, 1)

    def test_slideshow_skips_missed_intervals_pauses_and_resets_after_manual_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{i}.png' for i in range(3)]
            for path in paths:
                Image.new('RGB', (64, 32)).save(path)
            pictures = Pictures(paths, interval=5)
            pictures.render(0)
            pictures.render(4.9)
            self.assertEqual(pictures.index, 0)
            pictures.render(11)
            self.assertEqual(pictures.index, 2)
            pictures.on_buttons(report('a'))
            pictures.render(50)
            self.assertEqual(pictures.index, 2)
            pictures.on_buttons(report('a'))
            pictures.render(54.9)
            self.assertEqual(pictures.index, 2)
            pictures.render(55)
            self.assertEqual(pictures.index, 0)
            pictures.render(59)
            pictures.on_buttons(report('right'))
            pictures.render(60)
            self.assertEqual(pictures.index, 1)
            pictures.render(64)
            self.assertEqual(pictures.index, 2)

    def test_bad_input_fails_before_connecting(self) -> None:
        with self.assertRaisesRegex(ValueError, 'At least one'):
            Pictures([])
        for interval in (-1, float('inf'), float('nan')):
            with self.assertRaisesRegex(ValueError, 'interval'):
                Pictures([Path('unused.png')], interval=interval)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.jpg'
            path.write_text('not an image', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Cannot read picture'):
                Pictures([path])


if __name__ == '__main__':
    unittest.main()
