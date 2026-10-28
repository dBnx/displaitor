# Companion cries

`cry_torchic.qoa`, `cry_eevee.qoa` and `cry_treecko.qoa` are original, synthesized
handheld-style approximations. They do not contain ROM samples or recordings of
the games. The short pitch sweeps, pulse/wavetable colour, noise and 8-bit
quantization take inspiration from the GBA's tone/noise and sampled audio
capabilities ([GBATEK](https://mgba-emu.github.io/gbatek/),
[Direct Sound documentation](https://gbadev.net/gbadoc/audio/directsound.html)).

The deterministic source is `tools/synth_cries.py`: mono, 16,384 Hz, less than
0.7 seconds each. QOA occupies about 12 KiB altogether in flash. Playback uses
the existing decoder/resampler and PWM/DMA path; synthesis runs only on the PC.
Cries play once on A, restart on another A press, and stop on Back or mute.
Unmuting does not replay an old cry. Existing music mute behaviour is unchanged.

To regenerate WAV auditions without extra tools:

```sh
python3 tools/synth_cries.py --output-dir target/cry-auditions
```

To reproduce the firmware assets, obtain the upstream MIT-licensed `qoa.h` from
[revision bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e](https://github.com/phoboslab/qoa/blob/bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e/qoa.h).
Its SHA-256 is
`7b2396063eb960b10001db7db28ba25e284d4e772191968012e612dc8834952c`.
Keep the header outside the source tree; it is only an offline encoder input.
The generator verifies its hash and needs a C99 compiler (`CC`, default `cc`).

```sh
python3 tools/synth_cries.py --output-dir target/cry-auditions --qoa-header /path/to/qoa.h
# Review the generated files before replacing assets/audio/cry_*.qoa.
```

With `--qoa-header`, the WAVs contain the decoded QOA output so that auditions
match the compressed firmware assets. Offline tests decode the shipped assets,
check sample counts and one-shot behaviour, and exercise the Canvas command
through the simulator. Speaker loudness and physical sound quality still need
checking on the connected board.
