# Pixel Companion

An idle character that exercises harder as PC usage rises. Run the Python sender
to open Canvas and stream the character; it uses real CPU/GPU readings by default.
Choose Orbit, Ember or Sprout. It is a host-driven Canvas scene, so it appears
while this script runs and does not automatically replace another app on idle.

![Idle, working and hard-work states, rendered at 64×32](ui/companions/activity/workload-designs.png)

| Design | Idle | Working | Hard work |
| --- | --- | --- | --- |
| **Orbit** | [Floating robot](ui/companions/activity/orbit-idle.gif) | [Lifting dumbbells](ui/companions/activity/orbit-busy.gif) | [Faster barbell lifts](ui/companions/activity/orbit-hard.gif) |
| **Ember** | [Resting fox](ui/companions/activity/ember-idle.gif) | [Running fox](ui/companions/activity/ember-busy.gif) | [Faster running and sweat](ui/companions/activity/ember-hard.gif) |
| **Sprout** | [Bobbing sprout](ui/companions/activity/sprout-idle.gif) | [Leaf exercises](ui/companions/activity/sprout-busy.gif) | [Faster jumping jacks and sweat](ui/companions/activity/sprout-hard.gif) |

Every design uses whole-pixel shapes, a black background and a small palette.
Bodies and shadows are dim; eyes and small accents carry the bright highlights.
Labels sit on black. Text is rendered by the actual Rust Canvas implementation.
Ember's fur and Sprout's body/leaves use a darker palette for panel contrast;
their eyes, cheeks, ear/tail-tip details and other small accents retain their
brightness. The same palette applies while exercising and hopping.

## Combined sprite sheet

[Native sprite sheet](ui/companions/activity/sprite-sheet.png) contains all 144
character frames at their original pixel resolution. Each cell is 40×32 pixels,
cropped to the character region; the separate 24-column Canvas HUD is omitted.
There are 16 columns (frames 0–15) and nine rows: Orbit idle/work/hard, then Ember
idle/work/hard, then Sprout idle/work/hard. The full sheet is 640×288 pixels.

![All character poses, enlarged without smoothing and labelled](ui/companions/activity/sprite-sheet-labelled.png)

Regenerate both native and labelled sheets without a simulator or device:

```sh
.venv/bin/python tools/companion_designs.py --sprite-sheet-dir docs/ui/companions/activity
```

## New casts and Pokémon studies

The latest [play iteration and Monster Hunter-inspired creatures](COMPANION-PLAY.md)
give Cubone bowling pins, Treecko juggling berries and Torchic a toy ball. A
separate creature-only set features a rock-gobbler, winged night-cat and thunder-pup
playing with a pebble, feather and glowbugs. These use 24-frame play sequences.

[Fresh creatures and Pokémon](COMPANION-COLLECTIONS.md) provide two more complete
sets for choosing: Clack the crab, Lumen the jellyfish and Cinder the dragon;
plus Cubone, Treecko and Torchic. Their actions include claw presses, tentacle
pulses, wingbeats, fire, bone swings, leaps and hops. Each set has an animated
gallery and a 144-frame sprite sheet. These remain separate selection previews.

## Alternative characters: set B

These are an alternative set for choosing, separate from the current sender.
The comparison pairs are suggestions; characters can be mixed freely.

| Current A | Alternative B | Alternative exercise |
| --- | --- | --- |
| Orbit robot | **Pebble**, a stone golem | Waist-to-overhead barbell presses, heavier plates and a deeper squat under load. |
| Ember fox | **Tux**, a penguin | Kettlebell swings with broad flippers; the bell moves up and out as effort increases. |
| Sprout plant | **Axel**, an axolotl | Large overhead dumbbell presses and deep squats, with visible gills and a wide smile. |

![A current versus B alternative, with idle/work/hard columns](ui/companions/alternatives/comparison.gif)

This comparison plays both sets at the same rate to compare poses. The individual
alternative GIFs use 3/8/12 animation steps per second for idle/work/hard. All art
uses the existing 40×32 character region, RGB565 colours and black behind the HUD.
Axel's weights travel 17 pixels vertically and its hard-work squat moves its body
six pixels, giving a much clearer silhouette change than Sprout's small leaves.

- [Static comparison, frame 8](ui/companions/alternatives/comparison.png)
- [Labelled alternative sprite sheet: all 144 frames](ui/companions/alternatives/sprite-sheet-labelled.png)
- [Native alternative sheet: 640×288, 40×32 cells](ui/companions/alternatives/sprite-sheet.png)
- Individual hard-work loops: [Pebble](ui/companions/alternatives/pebble-hard.gif),
  [Tux](ui/companions/alternatives/tux-hard.gif), [Axel](ui/companions/alternatives/axel-hard.gif).

Regenerate this set and its A/B comparisons offline:

```sh
.venv/bin/python tools/companion_alternatives.py
```

No alternative is selected in the live sender yet. Its original characters and
the firmware remain unchanged while the user picks the preferred set.

## Run it

Install the existing [Canvas dependencies](CANVAS.md). With the board's **native
USB data connection** available, run from the repository root:

```sh
.venv/bin/python tools/pixel_companion.py --design orbit
```

On Windows:

```bat
tools\pixel_companion.cmd --design ember
```

The launcher uses the repository's Windows virtual environment if present, or
`py -3` otherwise. It needs the same Python dependencies. Native-board discovery
excludes the probe UART. All three characters in idle/work/hard states now pass
[Linux native USB uploads and hardware framebuffer comparisons](HARDWARE-CANVAS-USB.md).
Windows execution remains unverified; a debug probe alone does not provide a
Canvas serial connection. Earlier SWD-only checks are retained in
[connected rendering evidence](VALIDATION.md#canvas-and-host-apps).

To try it locally, first start the simulator in another terminal:

```sh
cargo run -p simulaitor -- --canvas-listen 127.0.0.1:7777
.venv/bin/python tools/pixel_companion.py --port tcp://127.0.0.1:7777 --design sprout
```

Canvas is selected once when connected, after preparing the scene. B returns to
the menu while the sender continues updating the retained scene. Reconnection
reinstalls the whole scene and opens Canvas again. Ctrl+C stops and retains the
last frame. A stopped sender leaves a still image, not a firmware screensaver.
Running only `pc_hub.py` continues to show its dashboard; run `pixel_companion.py`
instead to show the companion. Use one sender per device.

## How usage drives the character

By default the larger available CPU or GPU utilization drives its effort. The
footer says CPU or GPU to identify that reading. `--load cpu` or `--load gpu`
chooses one explicitly; `--gpu` supports the same backends as the PC hub.
High RAM occupancy alone is not work and does not make the character exercise.

| Activity | Enters at | Animation |
| --- | --- | --- |
| IDLE | Below 20% on initial reading | Gentle bob and blink; 3 animation steps/s |
| WORK | At least 20% | Exercise poses; 8 animation steps/s |
| HARD | At least 65% | Faster exercise, larger bob and sweat; 12 animation steps/s |

WORK returns to idle below 15%; HARD leaves below 55%. These small gaps prevent
jitter around the thresholds. The value and source label share the same colour,
with amber at 85% and red at 95%. The percentage reserves four medium-font cells
and aligns right, keeping `%` anchored from `1%` to `100%`. Missing counters show `--% / WAIT`, rather than
pretending the PC is idle. Auto can use CPU when GPU is unavailable; explicit
GPU mode waits for GPU data.

Metrics are sampled once per second (`--interval`, at least 0.2s). A single
background worker owns the CPU/GPU sampler and publishes only its latest sample;
slow OS/GPU queries do not block animation. Samples expire after the greater of
six seconds and three sampling intervals. Animation uploads default to 8fps
(`--fps`, at most 20); acknowledged transfer speed can lower the actual rate.
No frame queue or catch-up burst accumulates. `--frames N` sends a finite run.

## Preview and demo modes

For a visibly labelled synthetic idle → work → hard cycle, four seconds per state:

```sh
.venv/bin/python tools/pixel_companion.py --port tcp://127.0.0.1:7777 --demo
```

`--demo-load 95` holds a fixed labelled demo reading. DEMO replaces the CPU/GPU
footer, so synthetic values cannot be mistaken for actual telemetry. Live mode
is the default. `companion_designs.py --port ...` now shares the live application,
including actual CPU/GPU readings and button controls. Offline preview exports
retain explicitly labelled fixture values.

With updated firmware, Left/Right switch pets and A triggers a short hop. Back
still returns to the local menu and Select retains mute. Use `--no-buttons` to
disable pet controls; see [the host button interface](CANVAS-BUTTONS.md) to add
your own scene/action handling through the same connection.

To regenerate the activity sheet and all nine native-size GIFs locally:

```sh
cargo build -p simulaitor --no-default-features
.venv/bin/python tools/pixel_companion.py --preview-dir docs/ui/companions/activity
```

The exporter uploads each scene over simulator TCP, captures its real-rendered
HUD, and combines it with the exact RGB565 sprite frames. GIFs retain the 64×32
grid; the sheet uses nearest-neighbour enlargement. This does not contact hardware.
