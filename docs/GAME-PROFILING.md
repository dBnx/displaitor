# Game profiling through SWD

The optional `profiling` feature adds fixed RAM timing counters and synthetic
buttons to the firmware. Normal `--features firmware` builds contain neither.
It preserves connector GPIOs and routes synthetic input through the same debounce
and engine path as physical buttons. This is a manual hardware diagnostic; ordinary
builds and `scripts/check.sh` never contact a board.

The runtime revision described in [runtime architecture](RUNTIME-ARCHITECTURE.md)
samples physical/synthetic buttons in a priority Embassy task, woken by its
time driver. Idle screens no longer poll profiling capture requests until a UI
event; generate a button event to begin an idle capture. Swap timing now records the
time until the foreground observes completion, including application/USB work
performed while the swap is pending. Older archived captures used a blocking
swap wait and are not fresh measurements of this revision. Normal builds also
expose separate `INPUT_DIAGNOSTICS` counters for sampling gaps and queue overflow.

Build the diagnostic ELF:

```sh
cargo build --locked -p aitos --features profiling --target thumbv6m-none-eabi --release
```

Keep a copy of the matching ELF before building another configuration. After
programming and verifying that ELF, reset to the normal startup state and start
a probe-rs GDB server for the authorized board. With the server at port 1337:

```sh
probe-rs gdb --chip RP2040 --probe VID:PID:SERIAL --speed 5000 \
  --gdb-connection-string 127.0.0.1:1337
# In another terminal:
GAME_PROFILE_OUTPUT=target/game-profile.json gdb -batch \
  target/thumbv6m-none-eabi/release/aitos -x tools/profile_games.gdb
```

The script resolves the engine from stack or suspended Embassy task DWARF and
framebuffer addresses from the matching ELF, including RAM-code builds. It
navigates to Play, captures Pong with
released/held directions, steers Snake, waits for a collision, verifies retry,
and clears synthetic inputs in its cleanup path. It reads framebuffer hashes
and GPIO control state. All writes are to RAM; it does not use GDB's byte-oriented
memory writes on peripheral registers. No UART or native USB serial port is opened.

`GAME_CAPTURE` contains a requested duration in microseconds, actual start timer
low word and actual finish low word. A request clears counters at the next UI
loop. Capture ends at a later UI-loop boundary and counters then freeze. Calculate
duration with wrapping subtraction. The first iteration is excluded to avoid
debugger-related catch-up. Resume both cores without breakpoints until capture
finishes; read and report `TIMER.DBGPAUSE`. A nonzero request or zero finish means
the capture is incomplete and must not be reported as finished.

`GAME_TIMINGS` has 12 words per screen, ordered Splash, Home, Watch, Play, then
the `AppId` values in declaration order. Firmware storage uses `AppId::COUNT`;
the GDB reader obtains application names/count from the matching ELF's enum
debug information instead of maintaining a separate app list or word count.
The built-in menu labels and navigation script still need updating if menus change.
Each group of three words is count, total and maximum
microseconds for update, render, swap and poll interval respectively. Totals
saturate at `u32::MAX`. `GAME_INPUT` bits 0–6 mean A, B, Select, Up, Down, Left,
Right; zero releases synthetic inputs while preserving physical input.

Update/render/swap measurements exclude counter bookkeeping. Poll intervals
include instrumentation, USB service, the audio mailbox and display work. These
are instrumented firmware measurements; code layout and timing differ from normal
firmware. Redraws per second measure completed software render/swap work during
the capture window, rather than the panel's electrical scan refresh. Neither
framebuffer hashes nor these counters measure flicker, visible quality or audio
quality. Native USB traffic was not exercised by the SWD input path.

Profiling firmware also exposes `AUDIO_DIAGNOSTICS`: cumulative saturating data
completion count (DMA 2/3), fallback completion count (DMA 4), last pacing-timer
word observed inside the IRQ, and underrun recovery count. The last IRQ word is
historical: it does not prove that the timer is still enabled after mute/stop.
Normal builds omit these counters. `AUDIO_CAPTURE` accepts a duration request,
settles for 100 ms, then records actual firmware timestamps and baseline/final
counters from the existing button sampler. Its eleven words are request, start,
finish, four baseline counters, and four final counters; finish is published last.
This excludes probe attachment pauses from the measurement window. After
selecting Nyan, detaching and stopping the GDB server, test DMA pacing:

```sh
python tools/check_audio_hw.py --elf /path/to/matching-profiling.elf \
  --probe VID:PID:SERIAL --output target/audio-hardware
```

This manual script expects approximately 500 completed 64-sample blocks per
second, then checks zero completions while muted/stopped and resumed pacing.
It writes only capture requests and synthetic input in RAM and retains raw reads
and JSON evidence. Fresh probe-rs sessions pause cores while clearing hardware
breakpoints; differences between separate live reads include these disruptions
and must not be reported as uninterrupted playback measurements.
Game-over captures use Up/release events at the boundaries because the idle UI
has no periodic deadline. Those events do not restart Snake.

After testing, clear synthetic inputs, detach the debugger, stop the GDB server,
and explicitly resume both cores. Restore and verify the normal firmware build
when the diagnostic session is complete. See [validation results](VALIDATION.md)
for the actual observed checks and remaining limits.
