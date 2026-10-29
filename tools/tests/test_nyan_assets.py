"""Nyan keeps logical source colours and its original twelve animation frames."""

from __future__ import annotations

import hashlib
import unittest

from PIL import Image

from displaitor_tools.paths import ROOT


class NyanAssetsTests(unittest.TestCase):
    def test_source_palette_and_original_pixel_geometry(self) -> None:
        # Semantic order: sky, body, pastry, icing, sprinkles, cheeks,
        # rainbow red/orange/yellow/green/blue/purple, outline, stars.
        palette = (
            (0, 51, 102), (153, 153, 153), (255, 204, 153),
            (255, 153, 255), (255, 51, 153), (255, 153, 153),
            (255, 0, 0), (255, 153, 0), (255, 255, 0),
            (51, 255, 0), (0, 153, 255), (102, 51, 255),
            (0, 0, 0), (255, 255, 255),
        )
        # Captured from the original frames before recolouring, indexed by
        # semantic role. Every pixel must retain its role in every pose.
        geometry = (
            'fef5f9b829650fd933acf334378148b9ebde115af5df81370413f0f29143e7a7',
            '16cd46b6e269feb040248ac606fa73b80d439e895511995f2a3a6419708f18ab',
            '9eb496e4d44d641a3f3b156a45319b1bb028d1d4ffeeabdff68f162426684373',
            '78c12b6e4fbeabb21d058d4472830d70f9ddc33f1abc21e7ed07bf33aa44293e',
            'ebe8750e71e192123d97597ac3f50ec4a865bc8c24e9112f28b3e981853847db',
            'e0d0de81780e84c253f8505bc0d8cc821759bddcb92fbf3dd3ecd82ecd573062',
            '5649f548fc843bc9755594d25aac294082a6e53772997afc10fc2ff97a6cc9c2',
            '5301261a241cfbe1b8d0f78cf033d82f8c4796bd5ce0ad9289acd52801c2151b',
            'e3b9adedf4e1ba68519c397bc405e8fa7f819431d1c60e1cfbb89bdd38e84cb9',
            'e479a995e816c34c0c3ee928b2c51ec8ba1f62a801de1b52cc641b3b290a31b2',
            '8f59bd8cf83135bd39699461ce2851f774786accc414e6e8190e38bcbcf7ab1b',
            'a6c7a24b5e41b3719b868a0e1fbe20b7b06197bb02537be1f95d6434f11de5a7',
        )
        directory = ROOT / 'displaitor/assets/nyan'
        self.assertEqual(sorted(p.name for p in directory.glob('*.qoi')),
                         [f'{index:02d}.qoi' for index in range(1, 13)])
        for index, expected in enumerate(geometry, 1):
            with self.subTest(frame=index), Image.open(directory / f'{index:02d}.qoi') as image:
                self.assertEqual(image.size, (64, 32))
                raw = image.convert('RGB').tobytes()
                pixels = [tuple(raw[offset:offset + 3]) for offset in range(0, len(raw), 3)]
                self.assertEqual(set(pixels), set(palette))
                roles = bytes(palette.index(pixel) for pixel in pixels)
                self.assertEqual(hashlib.sha256(roles).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
