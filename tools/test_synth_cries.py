"""The shipped cries stay short, distinct, deterministic and within headroom."""
from pathlib import Path
import struct
import unittest

import synth_cries

ROOT = Path(__file__).resolve().parents[1]


class CrySynthesisTests(unittest.TestCase):
    def test_cries_have_silent_edges_headroom_and_distinct_reproducible_waveforms(self):
        waveforms = []
        for name in synth_cries.VOICES:
            with self.subTest(name=name):
                samples = synth_cries.synthesize(name)
                self.assertEqual(samples, synth_cries.synthesize(name))
                self.assertLess(len(samples), synth_cries.RATE)
                self.assertTrue(all(value == 0 for value in samples[:300] + samples[-300:]))
                self.assertTrue(all(value % 256 == 0 for value in samples))
                self.assertTrue(3000 < max(abs(value) for value in samples) < 18000)
                self.assertLess(abs(sum(samples) / len(samples)), 20)
                raw = (ROOT / 'assets/audio' / ('cry_' + name + '.qoa')).read_bytes()
                self.assertEqual(raw[:4], b'qoaf')
                self.assertEqual(struct.unpack('>I', raw[4:8])[0], len(samples))
                self.assertLess(len(raw), 5000)
                waveforms.append(samples)
        self.assertEqual(len(set(waveforms)), 3)


if __name__ == '__main__':
    unittest.main()
