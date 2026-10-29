# Displaitor Python library

A typed Python 3.12+ library for custom 64×32 display scenes, button input,
retained text and the included companion, weather and cozy apps. Install a local
wheel; no Rust toolchain, source checkout or firmware rebuild is needed to use it.

## Install and run

```sh
python -m pip install displaitor_tools-0.1.0-py3-none-any.whl
displaitor cozy --scene fire
displaitor companion --design cubone
displaitor weather --location London
displaitor pictures photo.jpg second.png --port COM6
displaitor pictures photo.jpg second.png --interval 5
# Equivalent when the scripts directory is not on PATH:
python -m displaitor_tools cozy --scene reef
```

The wheel works on Windows, Linux and macOS. Pip installs Pillow, pyserial and
psutil as dependencies. USB uses automatic port discovery; `--port COM6` or
`--port /dev/ttyACM1` chooses a particular device. Use one running app per board.
The board needs Canvas-capable firmware. The probe's UART is not the display port.

The picture viewer accepts one or more image paths. Left/Right browses with
wraparound; A advances. Add `--interval 5` for a slideshow (A pauses/resumes).
Back returns to the menu and exits. EXIF orientation and transparency are handled
automatically. The default fit permits up to 10% aspect distortion when that
fills the 64×32 screen; other images retain their proportions with black bars.
Use `--fit contain` for no stretching or `--fit cover` to crop centrally and fill
the panel. Animated image files show their first frame. Images load once before
connecting, and unchanged pictures are not uploaded repeatedly. Gamma 2.8 is
applied by the common serial output path.

## Your first scene

```sh
displaitor new-scene my_scene.py
python my_scene.py --port auto
# Windows examples:
py -m displaitor_tools new-scene my_scene.py
py my_scene.py --port COM6
```

The starter has an animated light, arrow-key movement and an A-button colour
change. Existing files are never overwritten. Edit the generated script freely.
A minimal scene needs only a render function returning a 64×32 Pillow image:

```python
from PIL import Image, ImageDraw
from displaitor_tools import run_scene


def render(elapsed: float) -> Image.Image:
    image = Image.new("RGB", (64, 32), "black")
    x = 4 + round(elapsed * 8) % 56
    ImageDraw.Draw(image).ellipse((x - 2, 14, x + 2, 18), fill="#B4E0C8")
    return image


if __name__ == "__main__":
    try:
        run_scene(render)
    except KeyboardInterrupt:
        pass
```

`run_scene(render, *, on_buttons=None, port="auto", fps=12, gamma=None,
timeout=3, buttons=True, frames=None, stop=None)` owns the connection, clears any
old text HUD and opens Canvas once. Render and button callbacks share one thread.
It polls input at up to 20 Hz even at a lower render rate. It skips identical
uploads and missed render deadlines, with one acknowledged frame in flight.
`elapsed` is monotonic seconds since launch, not a frame counter.

Back (B) returns to the board menu and ends the runner without reopening Canvas.
Select/mute remains local. A and the d-pad are available to your callback. The
runner ignores lost reports and establishes a fresh baseline before callbacks:

```python
from displaitor_tools import ButtonState


def on_buttons(state: ButtonState) -> None:
    for event in state.events:
        if event.active and "a" in event.pressed:
            print("A pressed")
```

Pass `on_buttons=on_buttons` to the runner. Reports also contain held buttons,
release edges and device timestamps. Use press edges for actions that should
happen once; held state is useful for continuous movement. Handle callbacks
quickly to keep display updates responsive. Use `buttons=False` with older
firmware lacking button reports. `frames=60` limits rendered updates, including
identical frames; the return value is the number rendered. A `threading.Event`
passed as `stop` ends the loop cleanly. Exceptions close the connection and
propagate; reconnection is explicit. Ctrl+C also closes it.

Keep artwork in its intended colours. USB/serial automatically applies gamma
2.8 once to images and text. TCP simulator previews default to gamma 1.0.
`gamma=1` disables correction; `gamma=2.2` changes it. Preserve a fixed layout
for changing numbers and keep sprite motion separate from the background.

## Retained text and lower-level access

```python
from displaitor_tools import Client, TextLayout, resolve_port

layout: TextLayout = {"text": {"temperature": {
    "x": 24, "y": 8, "width": 40, "height": 10,
    "font": "medium", "align": "right", "color": "#C8E4DC", "text": "-12°C",
}}}
with Client(resolve_port("auto")) as display:
    with display.transaction():
        display.layout(layout)
        display.fill("#000000")
        display.show()
    display.text("temperature", "21°C")
```

The root package exports `Client`, `Layout`, `TextLayout`, `TextSlot`,
`ButtonState`, `ButtonEvent`, `Renderer`, `ButtonHandler`, `WIDTH`, `HEIGHT`,
`color565`, `image_frame`, `resolve_port` and `run_scene`. Existing imports from
`displaitor_tools.canvas` remain supported. The wheel includes `py.typed` for
static type checkers. Your app can use `run_scene` for animated backgrounds or
`Client` directly for named text, atomic updates and its own event loop.

Included artwork/layouts are package resources, so apps work from any directory.
Firmware media generation and most simulator-based development previews remain
checkout-oriented; they fail clearly when a native simulator is needed. Plain
cozy GIF export and audio generation also work in an installed wheel. No app
writes to its installed package directory. Weather stores its cache in the
user's normal cache directory.

## Build and share manually

From the source checkout:

```sh
python -m pip install build
python -m build
# Share dist/displaitor_tools-0.1.0-py3-none-any.whl
```

The build produces a universal Python wheel and a source archive. It does not
publish or upload either. The package includes only its Python code, typing
marker, curated artwork, layouts, starter and attribution notices. Firmware,
personal name lists, captures, credentials and checkout state are excluded.
Artwork retains the separately documented rights in its bundled source notes.

For a completely offline installation, collect dependency wheels on a connected
machine with the recipient's OS, architecture and Python version:

```sh
python -m pip download --dest wheelhouse dist/displaitor_tools-0.1.0-py3-none-any.whl
# Copy wheelhouse to the recipient, then:
python -m pip install --no-index --find-links wheelhouse displaitor-tools
```

An individual Displaitor wheel is portable; Pillow's dependency wheels are
specific to the recipient's platform. The separate firmware/simulator remains
available in the project checkout and is not bundled into the Python wheel.


CI also builds and verifies the wheel on Linux and Windows (Python 3.12/3.14).
After a successful **Offline checks → verify** job, download the
**displaitor-python** artifact from the GitHub Actions run. It contains the
universal `.whl` and source `.tar.gz`, retained for 30 days. A manual
`workflow_dispatch` run is available too. This creates build artifacts; it does
not publish a package to PyPI. The installed wheel is checked outside the source
checkout, including its resources, public typing and a real simulator connection.
