# Validation

The public source uses neutral sample scroller messages. Personal input files,
local session records, debug dumps and compiled images are not included.

## Offline checks

Run `./scripts/check.sh` with the dependencies from the README. The publication
copy was checked independently of the hardware working directory:

- Rust workspace tests, all targets: 108 tests passed.
- Python helper/protocol/renderer tests: 65 tests passed.
- Strict host and ARM Clippy, formatting, headless smoke and SDL dummy drivers.
- Linked normal RAM ARM release build.

The public sample changes the scroller checksum while retaining its behavior.
Its 600-frame smoke run produced 67 redraws and 13 audio requests, with checksum
`50711b51acd4e628`.

`./scripts/check_embassy.sh` separately checks normal/profiling RAM and XIP
builds, ELF layout and RAM startup. It needs the Python validation dependencies
in `tools/requirements-validation.txt`; use `VALIDATION_PYTHON` to choose that
Python environment. These commands do not flash or contact a board.

## Connected board checks

The same runtime was tested on an RP2040 board through SWD and native USB.
Those hardware builds used local scroller content. The public sample build is
qualified offline; it has not been separately flashed.

- Normal firmware programming/readback and RAM text/vector relocation passed.
- Hardware audio checks found and repaired DMA completion/reload tracking.
- Native USB passed Canvas uploads, transactions, streaming and reconnect tests.
- Physical Left/Right pet selection, A action and local Back navigation worked.
- Rain weather appearance was visually confirmed on the panel.

See [Embassy hardware scope](HARDWARE-EMBASSY.md),
[native USB scope](HARDWARE-CANVAS-USB.md) and
[button scope](HARDWARE-CANVAS-BUTTONS.md). Register readback and USB ACKs do not
establish optical quality, audible quality, cold-boot robustness or power margin.

## Game tests and on-board timing

Pong and Snake have deterministic host tests for collision, growth, scoring,
reset, input and update timing. Earlier connected-board profiling measured
about 50 redraws/s for Pong and 16.6 for Snake. These are earlier qualification
results rather than new measurements of the public sample build. See
[game profiling](GAME-PROFILING.md) for the bounded profiling interface.

## Canvas and host apps

Tests use the actual Rust renderer and loopback protocol, plus malformed-frame,
CRC, transaction poisoning, disconnect and recovery cases. Button tests cover
cursor wrapping, overflow, held/pressed/released semantics and local Back priority.

Metrics and temperature use reserved monospace cells. Renderer snapshots verify
fixed `%` and `°C` anchors and removal of old digits/minus signs. Weather tests
cover condition priority, rain and snow motion, text clearance and reading
updates. Companion checks cover all exercise/hop poses and text clearance.

The final Ember/Sprout palette change passed all 15 companion tests. Comparisons
across 256 Orbit variants and 512 Ember/Sprout variants confirmed unchanged
Orbit output, silhouettes and accent-pixel locations. Remaining changed pixels
are darker. Its final physical contrast still awaits visual confirmation.
