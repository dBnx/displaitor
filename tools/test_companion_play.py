"""Check the actual rasterized play events, independent of timeline internals."""
import math
import unittest

from PIL import ImageColor

import companion_play as art


def pixels(image, colors):
    palette = {ImageColor.getrgb(color) for color in colors}
    raw = image.tobytes()
    return {(i % 64, i // 64) for i, rgb in enumerate(zip(raw[::3], raw[1::3], raw[2::3])) if rgb in palette}


def box(points):
    return min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)


class PlayTests(unittest.TestCase):
    def test_cubone_rolls_the_bone_knocks_pins_and_recovers_it(self):
        bone = ("#B8B99E", "#CBC9AC")
        flight = [box(pixels(art.sprite("cubone", f, "hard"), bone)) for f in (5, 6, 7)]
        self.assertLess(flight[0][0], flight[1][0])
        self.assertLess(flight[1][0], flight[2][0])
        pins = ("#815E3F", "#CAA371", "#C2A58A")
        for frame, standing in ((0, True), (8, False), (23, True)):
            tall = [(x, y) for x, y in pixels(art.sprite("cubone", frame, "hard"), pins)
                    if 30 <= x <= 37 and 24 <= y <= 27]
            self.assertEqual(bool(tall), standing, frame)
        # The recovered prop returns beside Cubone, far from the target lane.
        returned = box(pixels(art.sprite("cubone", 23, "hard"), bone))
        self.assertLess(returned[2], 25)

    def test_treecko_really_has_two_or_three_separate_berries(self):
        for mood, count in (("busy", 2), ("hard", 3)):
            image = art.sprite("treecko", 9, mood)
            for index, color in enumerate(("#C5738D", "#8873B7", "#C6A35D")):
                self.assertEqual(len(pixels(image, (color,))) >= 5, index < count)
        # An airborne berry clears the head and a low pass reaches the hands.
        image = art.sprite("treecko", 9, "hard")
        heights = [box(pixels(image, (color,)))[1] for color in ("#C5738D", "#8873B7", "#C6A35D")]
        self.assertLess(min(heights), 8)
        self.assertGreater(max(heights), 15)

    def test_torchic_ball_rolls_out_returns_and_the_bird_hops(self):
        ball = ("#416D8B", "#8EBAC8", "#B8CBAD", "#D2D8B5")
        bounds = [box(pixels(art.sprite("torchic", f, "hard"), ball)) for f in (0, 9, 23)]
        self.assertGreater(bounds[1][0], bounds[0][0] + 10)
        self.assertEqual(bounds[0], bounds[2])
        base = art.pokemon_base("torchic")
        raw = base.tobytes()
        actor_colors = {'#%02X%02X%02X' % (r, g, b)
                        for r, g, b, a in zip(raw[::4], raw[1::4], raw[2::4], raw[3::4])
                        if a and max(r, g, b) > 16}
        before = box(pixels(art.sprite("torchic", 9, "hard"), actor_colors))
        jumping = box(pixels(art.sprite("torchic", 11, "hard"), actor_colors))
        self.assertLess(jumping[3], before[3] - 2)

    def test_nox_paw_reaches_the_feather_after_the_crouch(self):
        distances = []
        for frame in (5, 11):
            image = art.sprite("nox", frame, "hard")
            paw = pixels(image, ("#756780",))
            toy = pixels(image, ("#A99FBF", "#7F719B"))
            distances.append(min(math.hypot(x-a, y-b) for x, y in paw for a, b in toy))
        self.assertGreater(distances[0], 3)
        self.assertLessEqual(distances[1], math.sqrt(2))


if __name__ == "__main__":
    unittest.main()
