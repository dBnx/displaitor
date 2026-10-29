# QOA decoder reference fixture

`nonzero_lms_two_frames.qoa` was encoded and decoded by the upstream phoboslab
QOA C reference at commit
[`bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e`](https://github.com/phoboslab/qoa/commit/bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e).
The matching `nonzero_lms_two_frames.pcm16le` contains that reference decoder's
output as little-endian signed 16-bit PCM. The fixture has 5,257 mono samples at
22,050 Hz: one complete 5,120-sample frame followed by a 137-sample frame. Its
second frame carries nonzero LMS state from the first frame.

The input PCM is the fixed xorshift32 sequence (initial state `0x6d2b79f5`)
now implemented in `tools/displaitor_tools/audio/fixtures.py`. The original
reference-generated QOA and PCM files are retained unchanged as independent
compatibility evidence. The Python codec reproduces both files byte-for-byte.

Regenerate temporary copies from the workspace root using only Python:

```sh
python tools/run.py audio fixtures --output-dir target/qoa-reference
```

No compiler, downloaded header or shell script is required. Compare the results
with the checked-in reference files before replacing them.
