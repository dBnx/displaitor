# Panel colour output

All Python apps using the Canvas SDK apply **gamma 2.8 automatically on USB/serial**.
This includes Companion, Dashboard, Weather, Cozy and the low-level Canvas CLI.
Background images, initial text foreground/background colours, subsequent style
changes and solid fills use the same transform. Restart a running sender to pick
up the new default. Existing board firmware works without reflashing.

```sh
python tools/cozy.py --scene reef                   # USB: gamma 2.8
python tools/run.py companion --design nudibranch  # Same correction for pet and HUD
python tools/cozy.py --scene reef --gamma 2.2       # Gentler correction
python tools/cozy.py --scene reef --gamma 1         # Uncorrected comparison
```

The HUB75 driver sends RGB values directly to binary PWM bitplanes. This makes middle values look brighter
than artwork viewed on a conventional display. Applying a power curve reduces
those middle intensities while preserving black, full white and full primaries.
[Adafruit's LED gamma explanation](https://learn.adafruit.com/led-tricks-gamma-correction?view=all)
describes the same LED brightness issue. This is a brightness-response correction,
not a measured per-channel white-balance calibration.

Physical feedback on 2026-10-28 reported that the Reef scene's gamma 2.2 trial
looked much better but still a little washed out. Stronger correction was then
requested, including a 2.6 trial. The user confirmed the controls and preferred
3.0 after comparing the curves. After the sprite colours were restored, the
user confirmed they looked good and selected **2.8 as the final default**.
The exponent remains adjustable: gamma 1 is
identity, larger values dim middle intensities more. The final appearance depends
on the panel and room lighting.

## One shared output boundary

Artwork, retained layout definitions, `color565()` and `image_frame()` stay in
logical RGB565. `Client` transforms output once, immediately before encoding its
frame/fill commands or serializing layout/style colours. Each channel uses:

```text
round((input / channel_max) ** gamma * channel_max)
channel_max = 31 for red/blue, 63 for green
```

The lookup is computed once per exponent, with one indexed lookup per output
pixel and no floating-point work in the frame loop. Each table occupies 128 KiB
on the host; at most eight tables are cached. The framebuffer payload remains
4096 little-endian RGB565 bytes. The host correction adds no board buffers or protocol commands. The board's physical channel
mapping remains in its existing display adapter.

Direct SDK users can set `Client(port, gamma=2.2)` or `gamma=1.0` and read
`client.gamma` for the effective exponent. The SDK applies the same profile when
loading the local name mapping supplied to the constructor. Changing the profile
requires reloading a retained layout; live apps do this when they start.

## Previews and firmware apps

TCP connections default to **gamma 1.0** because the simulator is viewed on a
conventional display. Offline GIFs and sprite sheets likewise retain their logical
colours; saving darkened LED drive values into artwork would correct it twice.
Use `--gamma 2.8` explicitly when a TCP endpoint forwards to a physical LED panel,
or to inspect the exact calibrated wire values in a simulator.

All native firmware screens now use the same gamma 2.8 curve in
`aitos/src/display.rs`, after scene rendering and before physical channel mapping.
Two small channel tables occupy 96 bytes. Canvas bypasses these tables: its
pixels, fills and text already contain the Python sender's selected gamma.
This keeps `--gamma` comparisons working and avoids double correction. Native
simulator output and all baked media remain logical RGB565; source art is never
rewritten. Custom Canvas hosts should send panel drive values or apply their own
output profile, as the Python SDK does.

## Sprite colours and earlier panel compensation

The old sprite loader multiplied broad Pokémon colours by 0.43 and pale details
by 0.74. Applying output gamma afterwards made Torchic and Eevee too dark.
That loader attenuation is removed for Torchic, Eevee and Treecko, including the
small companions in the Python winter scene. Original PNG inputs, alpha,
geometry, eyes, cheeks and animations are retained. Treecko's custom hand colours
now match the unattenuated source palette.

Ember and Sprout's earlier manual palette darkening was also reversed using the
original edit, preserving all facial accents. Their original body bases still
looked too dark after output correction, so those midtones were raised separately
without changing eyes, cheeks, ears or leaf details. The user confirmed both
look good at gamma 2.8. Offline Pokémon icon studies no
longer multiply source colours by 0.82. Orbit, sea pets and scene scenery had no
extra loader attenuation and retain their palettes. Intentional black text
backgrounds, shadows and dim empty meter tracks remain part of the artwork.

All six baked clips and reference checksums use logical source colours.
Gamma remains an output operation and is never baked into scene media.

Nyan Cat's legacy QOI palette also had very dark midtones. Its twelve frames
now use a brighter grey body, pastel icing and clean rainbow colours, preserving
all pixel positions. See the [palette notes](../displaitor/assets/nyan/README.md).
It still uses the same single gamma 2.8 output correction as the other native apps.

## Verification

Host checks cover all 65,536 RGB565 words at identity and multiple gamma values,
channel endpoints, byte order, every colour-bearing Canvas command, layout IDs,
serial defaults and overrides, and unchanged Windows COM read settings. Actual
Rust Canvas snapshots verify that text, its background and uploaded pixels are
corrected exactly once. Native USB exercised the corrected Reef scene; physical
feedback is recorded above separately from protocol and simulator evidence.

The final gamma-2.8 native USB check exercised all eight pets in idle, work,
high-load and scripted-action states, followed by the updated winter scene:
432 frames acknowledged without protocol errors. Restored winter sprites and
the final Ember/Sprout body colours were confirmed on the panel by the user.
