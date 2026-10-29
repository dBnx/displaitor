"""The explicit Descending Dark cast, jump, impact and fixed scenery."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from PIL import Image

from displaitor_tools.apps.companion import Activity, Companion
from displaitor_tools.canvas import ButtonEvent, ButtonState
from displaitor_tools.companions import designs, knight


def colored(image: Image.Image, rgb: tuple[int, int, int]) -> set[tuple[int, int]]:
    return {(x, y) for y in range(32) for x in range(40) if image.getpixel((x, y)) == rgb}


class KnightTests(unittest.TestCase):
    def test_jump_plunge_and_ground_burst_are_distinct_from_idle(self) -> None:
        idle = designs.sprite('knight', 0)
        mask = (219, 228, 224)
        wave = (186, 199, 221)
        airborne = designs.sprite('knight', 0, action=.34)
        descending = designs.sprite('knight', 0, action=.45)
        landed = designs.sprite('knight', 0, action=.52)
        self.assertLessEqual(max(y for _, y in colored(airborne, mask)),
                             max(y for _, y in colored(idle, mask)) - 5)
        self.assertGreater(max(y for _, y in colored(descending, mask)),
                           max(y for _, y in colored(airborne, mask)))
        self.assertGreater(max(y for _, y in colored(landed, mask)),
                           max(y for _, y in colored(airborne, mask)) + 5)
        early = colored(designs.sprite('knight', 0, action=.5), wave)
        spreading = colored(designs.sprite('knight', 0, action=.65), wave)
        self.assertTrue(early)
        self.assertTrue(spreading)
        self.assertLess(min(x for x, _ in spreading), min(x for x, _ in early) - 4)
        self.assertGreater(max(x for x, _ in spreading), max(x for x, _ in early) + 4)
        self.assertFalse(colored(designs.sprite('knight', 0, action=.9), wave))
        for progress in (0., 1.):
            self.assertEqual(designs.sprite('knight', 0, action=progress).tobytes(), idle.tobytes())
        for mood in ('idle', 'unknown', 'busy', 'hard'):
            for tick in range(designs.IDLE_FRAMES):
                self.assertFalse(colored(designs.sprite('knight', tick, mood), wave))
            for tick in range(129):
                image = designs.sprite('knight', tick, mood, action=tick / 128)
                self.assertFalse(any(image.crop((36, 0, 64, 6)).tobytes()), (mood, tick))
                self.assertFalse(any(image.crop((40, 0, 64, 32)).tobytes()), (mood, tick))
                self.assertEqual(image.crop((0, 29, 64, 32)).tobytes(),
                                 idle.crop((0, 29, 64, 32)).tobytes())

    def test_a_runs_the_full_spell_once_and_switching_cancels_it(self) -> None:
        pet, client = Companion('knight'), MagicMock()
        event = ButtonEvent(1, 1, frozenset({'a'}), frozenset({'a'}), frozenset(), True)
        pet.buttons(ButtonState(frozenset({'a'}), True, (event,), False, False, 0, 1))
        activity = Activity(5, 'CPU', 'idle')
        pet.update(client, activity, 10)
        self.assertEqual(pet.action_remaining, knight.ACTION_SECONDS)
        pet.play_pending_cry(client)
        client.cry.assert_not_called()
        pet.update(client, activity, knight.ACTION_SECONDS)
        self.assertEqual(pet.action_remaining, 0)
        pet.buttons(ButtonState(frozenset({'a'}), True, (event,), False, False, 0, 1))
        right = ButtonEvent(2, 2, frozenset({'right'}), frozenset({'right'}), frozenset(), True)
        pet.buttons(ButtonState(frozenset({'right'}), True, (right,), False, False, 0, 2))
        self.assertEqual(pet.design, 'orbit')
        self.assertEqual(pet.action_remaining, 0)


if __name__ == '__main__':
    unittest.main()
