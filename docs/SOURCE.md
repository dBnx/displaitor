# Source and board interface

This implementation updates the original Displaitor RP2040 firmware, preserving
its connector GPIOs and media formats. Personal name lists are replaced with
neutral sample messages in public builds.

## Original board IO contract

| Function | RP2040 GPIO or configuration |
| --- | --- |
| HUB75 R1, G1, B1, R2, G2, B2 | 0, 1, 2, 3, 4, 5 |
| HUB75 A, B, C, D | 6, 7, 8, 9 |
| HUB75 E | 10, output low |
| HUB75 clock, latch, output enable | 11, 12, 13 |
| Button A, B, Select | 14, 15, 29; pull-up inputs, pressed low |
| D-pad up, down, left, right | 16, 17, 18, 23; pull-up inputs, pressed low (legacy left/right names corrected after the user's physical Snake test) |
| Level shifter enable | 19, output low |
| Reserved SDA, SCL | 20, 21; floating inputs, no I2C transaction in source |
| Display power enable | 22, output high |
| Audio | 27, PWM slice 5 channel B; divider 1, top 255 |
| Activity LED | 28, high during update, low during rendering |
| Clock | 12 MHz external crystal; original HAL default 125 MHz system clock |
| Flash layout | 16 MiB external flash configured in original `memory.x` |
| Display | 64 × 32 RGB565 input, original driver used 10 PWM bitplanes and rotated pixel addressing by 180 degrees |

Original HUB75 resource assignments were PIO0 state machines 0–2 and DMA channels
0–3. These are internal implementation details rather than connector signals.

The colour-signal names above preserve the original source's GPIO assignments.
The 2026-10-19 Canvas test-card photo showed the connected panel exchanging green
and blue relative to the new driver's RGB stream. The physical display adapter
compensates by exchanging pixel G/B channels, without changing connector GPIOs,
logical RGB565 images, simulator colours or the serial protocol.

## Application behavior used as reference

Two splash images last two seconds each; B skips the splash. Boot enters the names
scroller directly. The root menu contains `<3`, `Imageine`, and `Pong`.
`Imageine` contains Nyan (12 frames with music), hyperspace (14 frames), and fire
(4 frames), with 50 ms animation frames. Scrolling advances every 30 ms. Pong's
simulation step is 20 ms. Snake existed in source but its menu was commented out;
Game Boy and Space Invader were unfinished placeholders.

The simulator retains W/S/A/D for the D-pad, Space for A, Q for B, and R for Select.
It normalizes keys and GPIO to `true = pressed`; the old simulator had opposite
polarity from the board. Select mutes on release. Headless mode runs the same
application and renderer without creating a window or opening an audio device.

The original firmware used unsynchronized mutable globals across cores, a broken
mute toggle, imprecise audio sample scheduling, and incomplete application resets.
Those defects are not compatibility requirements. The source selection does not
constitute connected-board, display timing, audio quality, or electrical validation.
