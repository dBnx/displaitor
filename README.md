# Displaitor Next

A fresh, allocation-free Rust 2024 implementation of the latest complete
Displaitor application for the original RP2040 board. The original projects are
untouched. Source selection and exact connector signals are in
[docs/SOURCE.md](docs/SOURCE.md).

## Run and verify

The pinned Rust 1.99.0 toolchain installs its ARM target, rustfmt, and Clippy via
`rust-toolchain.toml`. Desktop simulation also needs SDL2 development libraries
and pkg-config (`libsdl2-dev pkg-config` on Debian/Ubuntu, `sdl2 pkgconf` on Arch).
The complete check script also needs Python 3.12+ and the development dependencies:
`python -m pip install -r tools/requirements-dev.txt`. Host tools use annotations
and strict mypy checks.

```sh
# From this project directory: no hardware, window or audio device required.
cargo run -p simulaitor --no-default-features -- --smoke

# Desktop UI with audio; close the window or press Escape to quit.
cargo run -p simulaitor

# All host tests, strict lint, headless smoke and linked ARM firmware build.
./scripts/check.sh

# Build only; this command does not flash or contact a device.
cargo build -p aitos --features firmware --target thumbv6m-none-eabi --release
```

Firmware ELF: `target/thumbv6m-none-eabi/release/aitos`.
No default build target or flash runner is configured. Normal `cargo test` tests
the application and decoder on the host; `--workspace` includes firmware policy
and simulator tests. Separate host/ARM output directories allow switching targets
without cleaning the workspace.

This branch ports the board to Embassy RP 0.10. Input sampling and native USB
run on a priority interrupt executor; UI/display and core-1 audio await events
and deadlines. Idle menus and Canvas have no periodic UI tick. Normal firmware
builds copy executable code and vectors into SRAM at boot; media stays in Flash.
See [Embassy port and RAM build options](docs/EMBASSY-PORT.md) and the
[authorized SWD hardware follow-up](docs/HARDWARE-EMBASSY.md). Native USB Canvas,
PC hub and companion clients also passed [Linux board tests](docs/HARDWARE-CANVAS-USB.md).

The UI has been redesigned around a flat, indexed menu catalog. Home contains
**Names**, **Watch**, **Play**, and **Canvas**; menus have a title strip, three fixed rows,
black row backgrounds, a small selection marker and folder/action icons.
The title uses pure black text on a dimmer coloured strip; the inactive
scrollbar track is the faintest neutral grey representable in RGB565. Menu depth adds no ancestor
updates or rendering. See [UI architecture and preview](docs/UI-ARCHITECTURE.md)
for the extension model and regression evidence.

Candidate next apps are in [app ideas](docs/APP-IDEAS.md), including a standalone
Hourglass timer and lander game, plus a Canvas build-status beacon and pixel pet.
The [Pixel Companion](docs/PIXEL-COMPANION.md) reacts to real CPU/GPU activity:
Orbit lifts weights as load rises. Cubone, Ratzfatz and Ratikarl add a bone
hop, berry nibble and acorn snack; Ember and Sprout are temporarily retired.
Torchic, Eevee and Treecko add an ember sneeze, a leaf pounce and a twig toss.
Run `.venv/bin/python tools/run.py companion --design torchic` to open it, or
`tools\run.cmd companion --design torchic` on Windows. It uses the existing Canvas connection.
Nudibranch and moray add sea-lettuce nibbling and bubble-hearts.
Left/Right switch all nine pets and A triggers a hop or trick; Back stays local. Other host
apps can use [button state and retained transitions](docs/CANVAS-BUTTONS.md) on
the same connection. Both live companion launchers default to actual CPU/GPU
readings; synthetic values require an explicit demo option.

The [installable Python library](tools/LIBRARY.md) can also be distributed as a
wheel: `python -m build`. Recipients can use `displaitor new-scene my_scene.py`
and implement `run_scene(render, on_buttons=...)` without a checkout.

Host apps and offline generators share [one launcher and a tools guide](tools/README.md):
`python tools/run.py companion --design torchic`.

Display your own images with `python tools/run.py pictures photo.jpg second.png`.
Left/Right browses; add `--interval 5` for a slideshow. The viewer fits images to
64×32 with at most 10% stretching, otherwise preserving proportions with black
bars. `--fit cover` crops to fill instead. The shared gamma correction applies.

**Cozy scenes:** all ten are built into **Watch** and run without a PC: Farm dusk,
Snow walk, Blossoms (Ōkami), Valley camp (Witcher), Tidepool, Fireplace, Palico,
Rathalos, Zinogre and Poogie.
Left/Right cycles them, A triggers a special moment, Up/Down pauses/resumes,
and Back returns to Watch. The fireplace is a
full-panel stone background with flowing fire in front. The Python sender has the same scenes:
`python tools/cozy.py --scene fire`. See [usage and previews](docs/COZY.md).
[Game proposals and control maps](docs/GAME-IDEAS.md) cover richer d-pad-and-A games.

Python USB tools automatically apply [output gamma correction](docs/COLOR-OUTPUT.md)
to images, text and fills. `--gamma 1` disables it; `--gamma 2.2` tunes the curve.

**Weather:** `.venv/bin/python tools/run.py weather --location London` fetches
wttr.in weather with a persistent 30-minute cache. Up/Down selects current,
forecast or overview; Left/Right selects days or additional readings. Rain,
snow and other animations follow the displayed condition, with a muted palette
and stationary text. See [weather usage and previews](docs/WEATHER.md).

**PC stats hub:** with the board's own USB data port connected, run
`.venv/bin/python tools/run.py dashboard` to automatically select a dashboard with CPU,
RAM and GPU usage with coloured meters, plus a green VRAM row below GPU. It updates every two
seconds and reconnects automatically. Bright labels sit on a pure black background
for LED matrix contrast. See [setup, preview and options](docs/PC-HUB.md).
Windows setup and the `tools\run.cmd dashboard` launcher are documented there too.

**Canvas** accepts still/streamed backgrounds and eight named text boxes over a
serial connection. Before its first upload, it displays a USB-to-PC setup hint
with a provided script to run. Upload a user-defined JSON layout once, then update
text by name, set its colour, or choose a transparent/solid box background.
Transactions publish background, text and styles together; interrupted updates
retain the previous complete scene. Current helpers require the corresponding
transaction-capable firmware. The small
Python helper handles image conversion and the wire protocol. Try the complete
path without hardware:

```sh
# Image/helper test dependencies (use a virtual environment).
python3 -m venv .venv
. .venv/bin/activate
pip install -r tools/requirements.txt
cargo run -p simulaitor -- --canvas-listen 127.0.0.1:7777
# In another terminal:
python3 tools/run.py canvas --port tcp://127.0.0.1:7777 layout tools/displaitor_tools/resources/layouts/weather.json
python3 tools/run.py canvas --port tcp://127.0.0.1:7777 --layout tools/displaitor_tools/resources/layouts/weather.json text temperature '21°C'
```

See [Canvas usage and protocol](docs/CANVAS.md) for backgrounds, streaming,
text colour/transparency, scripting and the native USB CDC firmware adapter.
Probe UART is not used. The firmware has been flashed and readback-verified on
the RP2040; SWD checks exercised navigation and Canvas rendering with RAM test
data. On earlier firmware, The user visually confirmed the corrected panel colours
and text backgrounds; that visual check has not been repeated for the port.
Native USB uploads and rendered output now pass
[hardware tests](docs/HARDWARE-CANVAS-USB.md); the older visual evidence retains
its original scope in [validation](docs/VALIDATION.md#connected-board-checks).

W/S/A/D map to directions, Space to A, Q to B/back, and R to Select. B skips the
splash or returns to a menu. Select toggles audio on release. On the board all
seven pull-up buttons are active low. Physical left/right use GPIO18/GPIO23;
the legacy reversed labels were corrected after the user's Snake report. Both adapters normalize to `true = pressed`
and apply the same 8 ms debounce. Hold directions to move the Pong paddle; menus
advance once per press. Pong and Snake are available under Play.
Earlier firmware's connected-board profiling measured about 50 redraws/s for
Pong and 16.6 for Snake; its review also caught and fixed an unbeatable Pong opponent. See
[game checks and timing](docs/VALIDATION.md#game-tests-and-on-board-timing) for
measurements and their limits.

## Structure

- `displaitor`: `no_std` application. `Engine::update(Duration, Controls)` advances
  a bounded state machine and returns redraw/audio requests. `Engine<N>` accepts
  a validated static menu tree, retains one cursor per menu, and dispatches to the
  active `AppId` directly; adding menu levels does not wrap application updates.
  `render` draws a complete RGB565 frame through `embedded-graphics` and propagates target errors.
  Splash, scroller, menus, animations, Pong, Snake and Canvas share this engine.
- `qoa_decoder`: checked, streaming mono QOA decoder with fixed storage. Errors
  remain visible through `try_next_sample`; multichannel files are rejected.
- `aitos`: native USB CDC Canvas adapter, shared input debounce and buffered audio
  playback, plus the RP2040 binary. Core 0 owns the UI/display and a timer-driven
  button transition queue; core 1
  owns buffered DMA/PWM audio and the decoder in a separate Embassy executor. A short multicore critical section
  transfers the latest audio command and mute state between blocks. No shared
  mutable statics or heap allocator.
- `simulaitor`: optional SDL window/audio adapter and deterministic headless
  rendering. Uses the same application, debounce and playback code as firmware.

The maintained `rp-hub75` driver replaces the old nightly-only Git dependency.
It owns display DMA and frame swaps; application drawing touches only the released
back buffer. The panel adapter preserves the old 180° orientation, expands
RGB565 to RGB888, and compensates for this panel's green/blue channel reversal.
Applications and serial uploads retain logical RGB colours. Six bitplanes retain
every distinct source intensity; the old
driver used ten linear bitplanes. Scan timing and DMA assignments consequently
change, while every connector GPIO remains the same. GPIO10/E stays low with
16 row pairs. Display power is enabled only after a black scan buffer is ready.

The board still uses the original 12 MHz crystal, 125 MHz system clock, 16 MiB
flash layout and W25Q080 boot routine. The default `ram-code` feature relocates
code and vectors before normal runtime startup, reserving 16 KiB for the core-0
stack and 8 KiB for core 1. Use `--no-default-features --features firmware` for
standard XIP execution. GPIO20/21 remain reserved
floating inputs. The activity LED and power/level-shifter outputs are retained.

Audio keeps PWM5B on GPIO27 at divider1/TOP255. A DMA pacing timer feeds
32 kHz resampled audio in 64-sample blocks; completion interrupts wake decoding and command checks
between blocks. Idle and muted audio await changed commands. A fallback DMA write selects the midpoint if the producer falls
behind. Stop/mute/clip changes drain prepared samples before taking effect; mute
then pauses playback and unmute resumes it. Music loops at EOF; sound effects
stop. Repeated clip requests restart playback. IDs with no original audio asset
produce silence. A new sound replaces the current sound; there is no mixing or
command FIFO. Board testing found and repaired a DMA reload/completion defect. See
[runtime ownership and timing limits](docs/RUNTIME-ARCHITECTURE.md).

Only referenced image and QOA assets are included. The public build uses neutral
sample messages from `displaitor/assets/names.example.txt`. Personal name lists,
local hardware logs, debug dumps and compiled firmware are not published.
To use a private list, keep it outside the repository or in the ignored
`.private/` directory and set `DISPLAITOR_NAMES_FILE` to its absolute path
when building (for example `DISPLAITOR_NAMES_FILE="$PWD/.private/names.txt" cargo build ...`). Do not
commit that file or distribute a firmware binary containing it.
Source and embedded assets retain their original licensing; repository license
files are included.

## Verification limits

See [docs/VALIDATION.md](docs/VALIDATION.md) for the checks and review results.
Offline checks and connected-board SWD checks are reported separately. Flash
programming/readback, application progress and Canvas framebuffer swaps have been
checked on the RP2040. Linux native USB app uploads, streaming and session
recovery have also passed. Physical panel timing/ghosting, audible quality,
cold power-on behavior and physical button operation still need their own checks.
