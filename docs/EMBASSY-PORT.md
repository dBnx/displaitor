# Embassy port specification

The RP2040 firmware uses Embassy RP, with a RAM-code boot option and the
original connector GPIO contract.

## Required behavior

- Use Embassy RP HAL and its multicore-aware executors, with no second HAL
  independently owning the same hardware. Remove the old polled USB stack.
- Preserve every connector GPIO, active-low button interpretation, 8 ms debounce,
  panel rotation/colour calibration, power sequencing and PWM5B carrier settings.
- Preserve the allocation-free, directly dispatched Engine and all applications,
  flat menus, Canvas protocol/transactions, setup hint, local Back priority,
  explicit Show, and simulator/client compatibility.
- Keep button sampling and USB bus progress independent of synchronous rendering.
  Retain timestamped input transitions with bounded storage and explicit overflow
  counters. Do not invent historical samples after delayed interrupts.
- Await real events or deadlines instead of spinning on clocks, display swaps,
  DMA completion or idle command mailboxes. Idle menu/Canvas state must not wake
  the UI task every millisecond merely to discover that nothing changed.
- Keep the two-core audio architecture, owned DMA buffers, 32 kHz pacing, looping
  music, mute/pause source continuity, EOF padding and hardware silence fallback.
  Process commands between blocks and notify only when commands actually change.
- Retain bounded USB packet/response buffers, backpressure and packet suffixes.
  Abort unpublished Canvas state on reset/disconnect or CDC session changes.
  Do not hold an engine or cross-core mutex across asynchronous waits.

## Implemented ownership

| Owner | Resources and wakeups |
| --- | --- |
| Core 0 thread executor | Engine, Canvas parser and rendering; input transitions, USB bridge, animation deadlines and completed swaps |
| Core 0 interrupt executor, SWI_IRQ_0/P1 | 1 ms timestamped button sampler and joined USB device/CDC transport |
| Embassy time driver, TIMER_IRQ_0/P0 | Timer alarm 0; does not conflict with the DMA pacing timer |
| USBCTRL_IRQ/P0 | Native USB bus progress; all CDC internal state remains in one task |
| HUB75 DMA_IRQ_1 | PIO0, DMA channels 0/1, retained front/back buffers |
| Core 1 thread executor, DMA_IRQ_0 | PWM5B/GPIO27, DMA channels 2/3/4, DMA pacing timer 0, decoder and two 64-word audio buffers |

The UI does not poll at 1 kHz. Menus, Canvas and finished Snake games have no
periodic UI deadline. Animated screens retain their fractional phase across
input/USB/display wakeups. Both thread executors use Embassy RP's multicore
wake routing and sleep while idle. Audio completions wake at block boundaries;
unchanged UI commands do not wake the audio worker. These are source/scheduling
properties; CPU duty, power, physical signal timing and stack high-water use
remain unmeasured. The later hardware follow-up records software timing and DMA
completion windows separately.

The pinned `rp-hub75` package is vendored with a narrow RP2040 Embassy fix:
IRQ1 must acknowledge the shared raw DMA INTR register at offset `0x400`,
rather than reserved offset `0x410`. Only the selected channel bit is cleared.
See [patch reference](../vendor/rp-hub75/PATCHES.md). RTT uses
`disable-blocking-mode`, so a full diagnostics buffer cannot wait indefinitely
inside the multicore critical section.

## RAM boot option

- Normal firmware builds default to the `ram-code` option; disabling default
  features retains a standard XIP build for comparison and rollback.
- Standard W25Q080 boot2 establishes XIP. A Flash-resident bootstrap copies
  executable code and runtime vectors from Flash load addresses into their SRAM
  execution addresses, switches VTOR and enters the normal copied Reset handler.
- Keep large media and read-only assets in Flash; the complete image is too large
  for RP2040 SRAM. Preserve Embassy's normal pre-init, data initialization and BSS
  clearing. Do not claim the whole application is independent of XIP.
- Do not enable `boot2-ram-memcpy`, `run-from-ram`, or `zero-init-ram`: their
  semantics conflict with retained XIP assets or the relocated executable code.
- Enforce section placement, copy bounds and an explicit stack reserve with
  linker assertions. Validate both runtime vector tables and Flash bootstrap
  vectors, load addresses, Thumb entries, data/BSS separation and memory budget.

## Verification and limits

Run the existing full offline suite and add directed tests for scheduling
deadlines, retained input, USB staging/session behavior, mailbox notification and
audio wake/recovery policies. Link both RAM/XIP modes and profiling variants;
check vectors, dependency selection, static memory and stack reservations. Where
possible execute the actual boot-copy instructions in an offline Thumb emulator.
Perform independent standards and specification reviews against the fixed
baseline and fix confirmed findings.

Install `tools/requirements-validation.txt` into a Python virtual environment,
then run `VALIDATION_PYTHON=/path/to/venv/bin/python scripts/check_embassy.sh`
after the ordinary `scripts/check.sh` suite. The validation script builds the
four RAM/XIP and normal/profiling release combinations, checks each archived ELF,
and executes the actual RAM startup instructions through `main` in Unicorn.
Only PSM force-register readback is modeled; reset hardware is not simulated.
ELFs and logs are retained in `target/embassy-validation/`, and the final normal
Cargo output is the default RAM build. `VALIDATION_PYTHON` defaults to `python3`.

The initial port was verified offline. The user subsequently authorized board
programming and SWD tests; see [hardware follow-up](HARDWARE-EMBASSY.md). Offline
checks alone do not prove cold boot, physical DMA timing, native USB behavior,
stack high-water use, power consumption or audio/panel quality.

## Build options

```sh
# Default: copy executable code and runtime vectors into SRAM before Reset.
cargo build --locked -p aitos --features firmware --target thumbv6m-none-eabi --release

# Standard XIP alternative; same application and Embassy runtime.
cargo build --locked -p aitos --no-default-features --features firmware --target thumbv6m-none-eabi --release
```

For timing counters, substitute `profiling` for `firmware`. Both commands write
`target/thumbv6m-none-eabi/release/aitos`; use the matrix script to retain all
four images. `ram-code` is independent of `profiling`. The whole media image
cannot fit in SRAM: approximately 1.6 MiB of readonly media remains in Flash in
both modes. The code-copy mode continues to require functioning XIP.

## Verified results — 2026-10-21

Rust/Cargo 1.99.0, host x86_64 Linux, target `thumbv6m-none-eabi`:

- `scripts/check.sh` passed: **99 Rust tests**, **37 Python tests**, workspace
  formatting, strict host/ARM Clippy, deterministic smoke, SDL dummy video/audio,
  and an actual linked release firmware image. After the final shared-period
  cleanup, all Rust tests, host/ARM Clippy and the four-image matrix passed again.
- The smoke result is unchanged: 600 frames, 67 redraws, 13 audio requests,
  checksum `cd95dad574a7203a`, ending in Canvas.
- Directed tests cover scheduler phase/deadlines and sleeping static screens;
  command-mailbox notification; retained USB packet suffixes; and the actual
  bridge futures with real channels under cancellation, full queues, reset,
  transaction abort, coalesced reconnect and stale RX/write acknowledgments.
- Effective ARM dependencies contain one RP HAL (`embassy-rp`), Embassy USB,
  nonblocking RTT, and none of the conflicting RAM startup features above.
- Both RAM images executed their actual Thumb bootstrap and normal Reset through
  `main` in Unicorn. Code/vector contents, write bounds, VTOR, MSP, Embassy pre-init,
  initialized data and cleared BSS passed. PSM register readback is modeled.
- Five negative tests reject corrupted boot2 CRC, a Thumb IRQ pointer into BSS,
  a non-Thumb Reset entry, incorrect data-load metadata and an actual missing
  SRAM-store instruction. The last image passes layout checks but fails execution.
- All images pass runtime IRQ/vector ownership, executable section placement,
  Flash load-address/separation, allocator absence and stack/memory budget checks.

| Release image | Executable code | Readonly Flash | Static SRAM | Core 0 stack reserved | SRAM left below stack |
| --- | ---: | ---: | ---: | ---: | ---: |
| RAM, normal | 98,668 B | 1,652,856 B | 152,104 B | 16,384 B | 93,656 B |
| XIP, normal | 98,668 B | 1,652,856 B | 53,224 B | 16,384 B | 192,536 B |
| RAM, profiling | 100,100 B | 1,653,024 B | 154,088 B | 16,384 B | 91,672 B |
| XIP, profiling | 100,100 B | 1,653,024 B | 53,800 B | 16,384 B | 191,960 B |

Static SRAM includes copied code/vectors in RAM mode, all task/buffer state and
core 1's 8 KiB stack. Core 0's reserve is additional. These are linker budgets;
stack high-water use and physical execution time remain unmeasured.

Normal RAM ELF SHA-256:
`ba35161fc5ab426259bd2c8372ff8ee97567f254123d3b569af9f66d4cde2992`.
The matrix retains all four ELFs and build/check logs in
`target/embassy-validation/`; the ordinary Cargo artifact is normal RAM firmware.

Independent subagents reviewed Standards and Spec against baseline `9a01561`.
Confirmed review fixes include the IRQ1 raw-register address, bounded RTT
logging, stricter executable-vector validation, and actual USB bridge cancellation
coverage. A final maintenance finding unified scheduler/update period constants.
Final reviews found no remaining blocking source defects. Review and offline tests
are not physical correctness proof.

The original checkout remains at `3fd03c6`; all 221 captured source files match
the pre-worktree checksum manifest. Its unrelated dirty state is preserved.
The new worktree's `9a01561` checkpoint includes that source state before the port.

USB software queues are session-tagged. One native USB limitation remains: if
close/reopen notifications coalesce, an old packet already in the hardware OUT
bank has no generation/timestamp in the driver API. Opening does not discard a
genuine first request; the supported Python client sends Abort at connect. Reset
and deconfiguration disable/clear endpoint banks, and closed CDC sessions drain
OUT. Native enumeration, reconnects, cold boot, DMA trigger/EN/DREQ edge timing,
input latency, physical power/CPU use and audio/panel quality require board tests.
At this initial offline checkpoint no board, probe or native serial port was
contacted and nothing was flashed. The later authorized hardware follow-up
found and repaired a DMA RELOAD/LIVE assumption; the historical counts and image
hashes above describe the initial checkpoint, before that repair.
