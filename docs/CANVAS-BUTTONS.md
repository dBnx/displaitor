# Canvas host buttons

Host apps can read the board's seven debounced controls over the same native USB
or simulator connection used for drawing. No second serial connection or GPIO
ownership is needed. Normal Canvas commands and their replies remain compatible.

```python
from tools.canvas import Client
import time

with Client("/dev/serial/by-id/usb-Displaitor_Displaitor_Canvas_canvas-1-if00") as display:
    display.buttons()  # Establish the current state; do not replay old presses.
    while True:
        state = display.buttons()
        if state.active and not state.lost:
            for event in state.events:
                if event.active and "right" in event.pressed:
                    # Select the next scene without calling show() again.
                    pass
        # Draw/update your app here; drain bursts without an extra delay.
        if not state.more:
            time.sleep(.05)
```

`ButtonState` contains `held`, `active`, `events`, `lost`, `more`, `overwritten`
and `at_ms`. Names are `a`, `b`, `select`, `up`, `down`, `left`, `right`.
Each immutable `ButtonEvent` contains `sequence`, `at_ms`, `held`, `pressed`,
`released` and `active`. `active` means the local screen is Canvas. Both press
and release edges are retained, including taps shorter than the host polling
interval. Entering/leaving Canvas establishes a mode transition rather than a
host action, so the A press that opens Canvas cannot also trigger a pet action.

The device retains 32 changes, including screen-mode changes. Reads are
non-destructive and use a wrapping cursor; retrying the same cursor returns the
same retained events. Up to four are returned per response. `more` means another
poll is needed to catch up. `overwritten` counts all evicted history entries,
including ones a client already read; it is not a count of events lost by that
client. A stale/future cursor sets `lost`, resets the host's baseline and emits
no invented actions. A newly connected client always starts with a fresh baseline.
Device millisecond timestamps and event IDs wrap at 32 bits.

Readback observes local controls; it does not capture or consume them. Back still
returns to the local menu, and Select retains its mute toggle. Host apps should
respect `active` and avoid calling `show()` in response to a stale event. Scene
updates may continue in the background while the user is in another local app.

The live companion polls once per animation update. Left/Right cycle Orbit,
Ember, Sprout, Torchic, Eevee and Treecko. A triggers the selected pet's hop or
trick while its percentage remains a real CPU/GPU reading. Switching pets does not issue Show, preserving a Back
that arrives after the host's last button poll. `--no-buttons` disables these
actions. Older firmware is detected once per connection and continues displaying
live metrics without button actions, with a clear update message.

For a single-client diagnostic, stop any sender that owns the port, then run:

```sh
python tools/canvas.py --port YOUR-DEVICE buttons --watch
```

Without `--watch`, it prints the current baseline once. Polling and streaming
share the client's existing lock; do not open another reader on the same device.

## Wire extension

Command **10** accepts an empty payload to establish a baseline, or a little-endian
`after_id:u32`. Its successful response is:

```text
version:u8=1 | opcode:u8=0x81 | request_sequence:u16 | status:u8=0
state:u8 | flags:u8 | count:u8 | latest:u32 | overwritten:u32 | now_ms:u32
count × (event_id:u32 | event_ms:u32 | event_state:u8)
CRC32:u32
```

State bits 0–6 are A, B, Select, Up, Down, Left, Right; bit 7 means Canvas active.
Flags are bit 0 `more`, bit 1 `lost`. Count is at most four. CRC32, COBS encoding
and the zero delimiter are unchanged. The maximum decoded response is 60 bytes,
62 bytes on the wire, fitting a single short USB packet. Errors retain the
ordinary 17-byte decoded ACK format; unsupported older firmware returns status 3.
Buttons are separate from staged scene data and remain readable inside a scene
transaction. Transport resets abort staging without erasing the history.
