# Built-in cozy animation clips

Generated from the typed Python [scene renderers](../../../tools/displaitor_tools/scenes/)
with `python tools/run.py assets cozy`. No C tools or external downloads are used.
`--check` verifies byte-for-byte reproducibility without writing. Farm scenery is
original, inspired by Stardew Valley. Winter scenery is original, inspired by the
Red Rescue Team journey; the small walking companions reuse the already attributed
[Mystery Dungeon inputs](../../../tools/displaitor_tools/resources/art/rescue-pets/README.md).

| Clip | Loop | Timeline ticks | Unique frames | Flash bytes |
| --- | --- | --- | --- | --- |
| farm.cqoi | 16 s | 160 | 67 | 58,600 |
| winter.cqoi | 32 s | 320 | 312 | 370,973 |
| okami.cqoi | 16 s | 160 | 99 | 107,542 |
| witcher.cqoi | 16 s | 160 | 126 | 186,428 |
| reef.cqoi | 16 s | 160 | 145 | 158,138 |
| fire.cqoi | 16 s | 160 | 160 | 613,757 |
| palico.cqoi | 16 s | 160 | 72 | 90,858 |
| rathalos.cqoi | 16 s | 160 | 70 | 100,331 |
| zinogre.cqoi | 16 s | 160 | 80 | 122,377 |
| poogie.cqoi | 16 s | 160 | 70 | 91,332 |

Each clip is a `CZY1` container. All integer metadata is little endian:

1. Four magic bytes `CZY1`, then u16 timeline length, u16 unique frame count,
   and u32 tick duration in microseconds (100,000).
2. One u16 atlas frame ID per timeline tick.
3. One u32 byte offset per unique frame plus a final end offset, relative to the
   payload. Offsets begin at zero and strictly increase.
4. Complete, opaque 64×32 RGB QOI images concatenated as the payload.

Firmware validates metadata at compile time. Rendering borrows the selected QOI
slice directly from Flash and uses the existing tinyqoi decoder. Identical images
share an atlas entry. The clip metadata drives both animation ticks and deadlines;
the runtime carries only its existing frame/timer fields and a pause flag.

The `.hashes` sidecars contain one little-endian u64 FNV-1a checksum per tick,
computed from the exact 4096-byte RGB565 panel frame. They are used by host tests,
including an independent full decode through tinyqoi, and are not linked into
firmware. Python tests compare every baked tick with the original scene rendering.

Winter companions retain their native source colours. Earlier host-side RGB
attenuation was removed. Media stays in logical RGB565; gamma 2.8 is applied
once at output by the physical firmware adapter or by the Python sender. All ten
clips run autonomously under Watch; Left/Right follows the Python scene order.


Actions use a separate sparse `ACT1` format. All integer fields are little endian:
magic `ACT1`, u16 frame count (32), u16 frame duration in milliseconds (100), then
u32 offsets for every frame plus its end offset, relative to the payload. Each
frame contains sorted, non-overlapping runs: u16 first linear pixel index,
u16 pixel count, and that many RGB565 u16 colours. Missing pixels are transparent.
The generator requires binary alpha; firmware validates all offsets, lengths,
ordering and 64×32 bounds at compile time. A reaction costs one optional elapsed-time clock
in the existing engine, no framebuffer or heap. The 3.2-second action clock runs
independently of the ambient clock and its pause state. `.action-hashes` are
host-only FNV-1a checksums of each overlay composited over ambient time 1.5 seconds.
Tests compare every firmware action tick with the Python source composite.
Nyankatz and Hyperspace have small `.action` clips too.


Monster Hunter reactions replace the changing actor pixels as well as adding
particles. The Python generator restores background pixels beneath possible old
limb positions and omits pixels matching every ambient pose. This gives expressive
faces and carried props without ghost limbs or a second full-frame animation set.
The sparse ACT1 wire format and allocation-free firmware decoder are unchanged.
