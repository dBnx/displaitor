"""Exercise the public custom-scene runner, including Back and slow-frame timing."""
from __future__ import annotations
from threading import Event
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from displaitor_tools import ButtonEvent, ButtonState, run_scene


def report(*pressed: str, active: bool = True, lost: bool = False) -> ButtonState:
    keys = frozenset(pressed)
    events = (ButtonEvent(1, 10, keys, keys, frozenset(), active),) if keys else ()
    return ButtonState(keys, active, events, lost, False, 0, 10)


class Clock(Event):
    def __init__(self) -> None:
        super().__init__()
        self.now = 0.0

    def wait(self, timeout: float | None = None) -> bool:
        self.now += timeout or 0
        return self.is_set()


class RunnerTests(unittest.TestCase):
    def test_clears_old_hud_opens_once_deduplicates_and_passes_options(self) -> None:
        clock = Clock()
        seen: list[float] = []
        def render(elapsed: float) -> Image.Image:
            seen.append(elapsed)
            return Image.new('RGB', (64, 32), '#88CCAA')
        with patch('displaitor_tools.runner.Client') as cls, \
             patch('displaitor_tools.runner.resolve_port', return_value='COM6'), \
             patch('displaitor_tools.runner.time.monotonic', side_effect=lambda: clock.now):
            client = cls.return_value.__enter__.return_value
            client.buttons.return_value = report()
            self.assertEqual(run_scene(render, frames=4, fps=10, gamma=2.2, stop=clock), 4)
            cls.assert_called_once_with('COM6', timeout=3, gamma=2.2)
            client.layout.assert_called_once_with({'text': {}})
            client.show.assert_called_once()
            self.assertEqual(client.frame.call_count, 1)
            self.assertGreaterEqual(client.buttons.call_count, 5)
            self.assertEqual(len(seen), 4)
            self.assertAlmostEqual(seen[-1], .3)
            cls.return_value.__exit__.assert_called_once()

    def test_baseline_and_lost_events_are_ignored_and_back_ends_even_at_low_fps(self) -> None:
        clock, callback = Clock(), MagicMock()
        with patch('displaitor_tools.runner.Client') as cls, \
             patch('displaitor_tools.runner.resolve_port', return_value='unused'), \
             patch('displaitor_tools.runner.time.monotonic', side_effect=lambda: clock.now):
            client = cls.return_value.__enter__.return_value
            client.buttons.side_effect = [report('a'), report('a', lost=True), report('right'), report(active=False)]
            self.assertEqual(run_scene(lambda t: Image.new('RGB', (64, 32)), on_buttons=callback,
                                       fps=1, stop=clock), 1)
            callback.assert_called_once()
            self.assertIn('right', callback.call_args.args[0].events[0].pressed)
            self.assertLess(clock.now, 1)
            client.show.assert_called_once()
            self.assertEqual(client.frame.call_count, 1)

    def test_slow_rendering_never_replays_missed_frames(self) -> None:
        clock, seen = Clock(), []
        def render(elapsed: float) -> Image.Image:
            seen.append(elapsed)
            clock.now += .4
            return Image.new('RGB', (64, 32), (len(seen), 0, 0))
        with patch('displaitor_tools.runner.Client'), \
             patch('displaitor_tools.runner.resolve_port', return_value='unused'), \
             patch('displaitor_tools.runner.time.monotonic', side_effect=lambda: clock.now):
            self.assertEqual(run_scene(render, frames=4, buttons=False, fps=20, stop=clock), 4)
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(b - a >= .399999 for a, b in zip(seen, seen[1:])))

    def test_renderer_errors_close_the_connection_and_invalid_images_are_not_shown(self) -> None:
        with patch('displaitor_tools.runner.Client') as cls, \
             patch('displaitor_tools.runner.resolve_port', return_value='unused'):
            with self.assertRaisesRegex(ValueError, '64x32'):
                run_scene(lambda t: Image.new('RGB', (32, 32)))
            cls.return_value.__enter__.return_value.show.assert_not_called()
            cls.return_value.__exit__.assert_called_once()

    def test_stopped_and_invalid_arguments_do_not_open_hardware(self) -> None:
        with patch('displaitor_tools.runner.Client') as cls:
            for arguments in ({'fps': 0}, {'fps': 21}, {'fps': float('nan')}, {'gamma': -1},
                              {'frames': 0}, {'frames': True}, {'timeout': 0},
                              {'buttons': False, 'on_buttons': lambda s: None}):
                with self.assertRaises(ValueError):
                    run_scene(lambda t: Image.new('RGB', (64, 32)), **arguments)
            stop = Event()
            stop.set()
            self.assertEqual(run_scene(lambda t: Image.new('RGB', (64, 32)), stop=stop), 0)
            cls.assert_not_called()


if __name__ == '__main__':
    unittest.main()
