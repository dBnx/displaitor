# Host tools and Python library

For wheel installation, custom scenes, button callbacks and manual distribution,
see the [Python library guide](LIBRARY.md). Once installed, use `displaitor`
or `python -m displaitor_tools` from any directory. Create a starting script with
`displaitor new-scene my_scene.py`.

Build locally with `python -m build`; share the `.whl` in `dist/`. No publishing
step is required. `python scripts/check_wheel.py --simulator target/debug/simulaitor`
checks clean installation, bundled resources, typing and real simulator output.


Use **Python 3.12 or newer** and run commands from the repository root. On Windows, use `py` in place of `python`,
or `tools\run.cmd` to use the checkout's virtual environment automatically.

```sh
python -m pip install -r tools/requirements.txt
python tools/run.py companion --port COM6 --design torchic
python tools/run.py dashboard --port COM6
python tools/run.py weather --port COM6 --location London
python tools/run.py cozy --port COM6 --scene farm
python tools/run.py pictures photo.jpg second.png --port COM6
python tools/run.py pictures photo.jpg second.png --interval 5
python tools/run.py canvas --help
```

The picture viewer also runs directly as `python tools/pictures.py photo.jpg`.
Left/Right browses, A advances, and B exits. With `--interval 5`, pictures advance
every five seconds and A pauses/resumes. Auto fit stretches by at most 10% when
the aspect ratio is close to 2:1; otherwise it preserves the image with black
bars. `--fit contain` disables stretching; `--fit cover` crops centrally to fill
the panel. EXIF orientation, transparency and the shared gamma profile apply.

Use one live app per display. Stop the current app with Ctrl+C before starting
another. Port `auto` is the default; COM6 above is an explicit Windows example.
USB apps automatically apply gamma 2.8 to image, text and fill colours. Use
`--gamma 1` for uncorrected output, or e.g. `--gamma 2.2` to tune it. TCP simulator
connections default to 1.0 so desktop previews retain their intended colours.
See [colour output and calibration](../docs/COLOR-OUTPUT.md).

The companion supports `--design torchic`, `eevee`, `treecko`, `cubone`, `ratzfatz` and `ratikarl`, Left/Right pet
selection, Up/Down stats and A for a trick/cry. `--design nudibranch` and
`--design moray` select the two sea pets and their silent prop actions. See [the companion guide](../docs/PIXEL-COMPANION.md).
Weather uses wttr.in with a persistent 30-minute cache. Up/Down switches current,
forecast and overview; Left/Right selects forecast days or overview details.
See [weather setup and previews](../docs/WEATHER.md).
`--design knight` adds the Hollow Knight pet: A jumps and plunges into a
Descending Dark spell with two spreading shockwaves. All ten pets have longer, lively idle
loops, with fixed text and scenery. The preview command also exports an
enlarged `idle-gallery.gif` with all selected pets together.
For a text-free animated panel, run `python tools/cozy.py --scene farm` or
`--scene winter`. `--scene okami` and `--scene witcher` add a blossom
shrine with Amaterasu and a moonlit camp with Geralt and a leshen. `--scene reef`
shows a nudibranch and moray together in a cozy tidepool. Left/Right
cycles all ten scenes, A triggers a special moment, and Up/Down pauses/resumes. See [cozy scenes](../docs/COZY.md).
All ten scenes, including `--scene fire` (an indoor stone fireplace), are built
into **Watch** after updating the firmware and run without a host connection.

Offline tasks have their own command groups:

```sh
python tools/run.py audio synth --output-dir target/cry-auditions
python tools/run.py audio fixtures --output-dir target/qoa-reference
python tools/run.py assets cozy --check
python tools/run.py preview stats --audio-dir target/cry-auditions --output-dir target/stats-previews
python tools/run.py preview activity --output-dir target/activity-previews
python tools/run.py preview activity --design nudibranch --design moray --output-dir target/sea-pets
python tools/run.py preview weather --output-dir target/weather-previews
python tools/run.py preview cozy --output-dir target/cozy-previews
python tools/run.py preview cozy --scene okami --scene witcher --output-dir target/themed-previews
python tools/run.py preview designs --sprite-sheet-dir target/sprite-sheets
python tools/run.py preview play --help
```

Audio synthesis and mono QOA encoding/decoding use only the Python standard
library. No C compiler, native audio library or downloaded header is needed.
QOA and decoded WAV outputs reproduce the shipped assets byte-for-byte.
Previews use Pillow; some capture real Canvas text with a native `simulaitor`
build, and the stats video exporter also needs ffmpeg. Art studies are separate
from the live pet selection.

```text
tools/
  run.py, run.cmd         command launcher
  displaitor_tools/
    apps/                live companion, dashboard, weather and cozy scenes
    canvas.py            shared transport, drawing, buttons and discovery
    metrics.py           shared CPU/RAM/GPU/VRAM sampling
    weather/             typed provider data, persistent cache, views and artwork
    scenes/              deterministic fullscreen artwork, including fire
    companions/          pet sprites, actions, layout and stats formatting
    audio/               synthesis and Python QOA codec
    assets/              offline firmware media generators
    previews/            offline galleries, GIFs, sprite sheets and videos
    hardware/            opt-in SWD audio checks and game-profiling GDB script
    runner.py            public render/button loop with bounded uploads
    resources/           bundled art, JSON layouts and typed scene starter
    paths.py             read-only resources and checked development paths
  tests/                 host tests, including simulator integration
  requirements*.txt      app and optional validation dependencies
```

The four old live-app scripts (`pixel_companion.py`, `pc_hub.py`, `weather.py`,
`canvas.py`) and the existing Windows launchers remain small compatibility entry
points. `from tools.canvas import Client` still works from the repository root.
Implementations and new development belong in `displaitor_tools`, which uses
normal package imports rather than script-import fallback chains.

Run host checks with:

```sh
python -m pip install -r tools/requirements-dev.txt
cargo build --locked -p simulaitor --no-default-features
python -m mypy
python -m unittest discover -s tools/tests -t tools -v
```

All implementation functions have type annotations, checked with strict mypy
against Python 3.12. New Python code uses that baseline and typed interfaces;
weather readings use immutable dataclasses and layouts use `TypedDict` models.
CI checks the host tools on Python 3.12 and 3.14.

Hardware commands are explicit and excluded from host tests:
`python tools/run.py hardware audio --help`. Running an actual SWD check requires
a matching profiling ELF, an explicit probe selector, validation dependencies and
a connected board. See [game profiling](../docs/GAME-PROFILING.md).
