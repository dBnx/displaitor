# Companion cries

`cry_torchic.qoa`, `cry_eevee.qoa` and `cry_treecko.qoa` are original, synthesized
handheld-style approximations. They do not contain ROM samples or recordings of
the games. The short pitch sweeps, pulse/wavetable colour, noise and 8-bit
quantization take inspiration from the GBA's tone/noise and sampled audio
capabilities ([GBATEK](https://mgba-emu.github.io/gbatek/),
[Direct Sound documentation](https://gbadev.net/gbadoc/audio/directsound.html)).

The deterministic source is `tools/displaitor_tools/audio/synth.py`: mono,
16,384 Hz, less than 0.7 seconds each. QOA occupies about 12 KiB altogether in
flash. Playback uses the existing decoder/resampler and PWM/DMA path; synthesis
and encoding run only on the PC. Cries play once on A, restart on another A
press, and stop on Back or mute. Unmuting does not replay an old cry.

Regenerate firmware QOA assets and exact decoded WAV auditions with Python:

```sh
python tools/run.py audio synth --output-dir target/cry-auditions
```

No compiler, extra Python packages, downloaded headers or native library is
needed. The mono QOA codec in `tools/displaitor_tools/audio/qoa.py` uses integer
LMS prediction and the reference scalefactor search. It reproduces the existing
three QOA files and WAV auditions byte-for-byte, so the sounds do not change.
Its upstream algorithm attribution and MIT license are included alongside the
module; the reference revision is
[bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e](https://github.com/phoboslab/qoa/tree/bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e).
Review generated files before replacing `assets/audio/cry_*.qoa`.

Offline tests cover reference sample vectors, slice/frame boundaries, malformed
files, deterministic encoding and exact asset reproduction. Firmware tests decode
the shipped assets and check sample counts, mute, restart and one-shot behaviour.
Speaker loudness and physical sound quality still need checking on the board.
