# Runtime architecture

The application remains a flat, allocation-free `Engine`. Firmware adapters own
hardware timing, input retention, display buffers and audio output. The GPIO
mapping, PWM5B output and logical RGB565 renderer remain compatible with the
existing board. These changes have offline evidence only; they are not installed
firmware or new physical timing measurements.

## Input and application time

Embassy's time driver owns TIMER_IRQ_0/alarm 0. A priority interrupt-executor
task owns all seven button input pins and samples on
an absolute 1 ms grid, applies the existing 8 ms debounce, and stores up to 32
timestamped full-state transitions. A delayed interrupt samples current inputs
once and skips missed grid slots; it does not manufacture historical samples.
Queue overflow drops the oldest transition, counts it and retains the latest
held state. The bound is explicit: arbitrary foreground stalls can still lose
edges after 32 transitions.

The foreground drains transitions and captures their time cutoff under one
local interrupt mask. This avoids admitting an older event after application
time has advanced past it. The queue is private to core 0; its entry points
check core identity, and it never takes the multicore audio/display spinlock.
Sampling can still be delayed by other interrupts or interrupt-masked code.
Only debounced changes notify the UI; the 1 ms sampler does not wake the UI
every millisecond. TIMER_IRQ_0 and USBCTRL_IRQ run at P0; the input/USB executor
uses SWI_IRQ_0 at P1. The UI uses the core-0 thread executor. Menus, Canvas and
finished Snake games await input or USB, while autonomous screens use absolute
deadlines from `Engine::next_update_after`, preserving fractional tick phase.

`aitos::runtime::Runtime` advances the engine up to each transition using the
previous held state, applies the transition at zero elapsed time, then advances
to the batch cutoff. New directions therefore do not apply retroactively. Each
retained Select release toggles mute once. Redraw requests combine with OR, and
the latest nonempty audio request wins, matching the existing audio mailbox.

`INPUT_DIAGNOSTICS` exposes missed sampling slots, dropped transitions and the
maximum observed sample interval in microseconds. These counters are present in
normal builds; optional profiling button injection follows the same IRQ path.

## Display ownership

The foreground owns either a released back buffer or a pending `Hub75Swap`.
It reclaims a buffer only after `is_done()`; the following `wait()` cannot block.
During a pending swap the loop continues servicing USB and updating the engine.
Redraw stays pending until a buffer is available, at which point the latest
application state is rendered. Intermediate application states can coalesce.

Drawing remains synchronous, but priority input sampling and the USB bus task
can preempt it. The Engine and protocol parser stay exclusively in the UI task;
owned 64-byte packets, bounded replies and generation-tagged completion messages
cross the executor boundary. No Engine mutex is required. Neither USB bus service
nor input sampling has a proven hard physical latency bound.
Profiling swap intervals now include foreground time until completion is observed.

## USB ownership

Device/CDC state is constructed and polled in one priority task: the class uses
non-Sync control cells, so its handles must not cross executors. `device.run()`
and data transport are joined within that task. Single-slot RX, reply and write
completion channels bound RAM. The UI retains packet suffixes and reply state
across canceled waits. RX backpressure still permits reply transmission, avoiding
a pipeline deadlock. Session generations invalidate software queues and abort
unpublished Canvas state independently of IN/OUT backpressure.

Closed CDC sessions drain OUT. The USB packet API cannot distinguish an old
hardware-buffered packet from a new first packet if close/reopen notifications
coalesce. Opening therefore preserves an immediate first client request; the
supported Python client sends Abort on connect. Native reconnect behavior still
needs board testing.

## Audio ownership

Core 1 owns the complete PWM5 slice, DMA data channels 2/3, fallback channel 4
and DMA pacing timer 0. HUB75 retains channels 0/1 and DMA_IRQ_1. The carrier
remains divider 1/TOP 255 on GPIO27; full-width CC words carry channel B duty in
their upper half, avoiding replicated narrow peripheral writes.

Audio is resampled with sample-and-hold to 32 kHz and prepared in fixed 64-sample
blocks. At the configured 125 MHz system clock, pacing timer X=4/Y=15625 requests
32,000 transfers per second. Hardware timing replaces per-sample software waits;
DMA_IRQ_0 wakes the core-1 executor on completion, and the worker checks its
command mailbox between blocks. Changed commands signal the sleeping worker;
unchanged UI state does not notify it. Idle/muted playback sleeps. Stop, mute and clip changes
drain already prepared blocks before applying the change: at most 4 ms of queued
sample time plus the final silence tick, decoding and scheduling latency. Muting
preserves the decoder and resampling phase after those samples have played.

Unprepared successors lead to a one-word midpoint fallback on the next 32 kHz
tick, preserving the final sample's hold time. Pacing stays enabled until that
fallback completes, including pending chain triggers that have not become busy
yet. Late production therefore reaches silence without the CPU writing individual
samples. Recovery uses a fresh pacing start and clears only owned audio-channel
request credits; it does not emit a backlog of late samples. DMA buffers remain static and cannot
be written while reachable by an active transfer. No DMA abort is used.

The private register adapter is kept separate from the host-testable decoder,
resampler and block-filling policies. Its hardware behavior, underrun recovery,
audio quality and physical jitter require a later board test. Building/linking
the firmware does not establish those properties.

Hardware semantics are based on the pinned HAL/PAC sources and the
[RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf),
particularly DMA chaining/pacing, narrow IO writes and PWM compare buffering.
The internal timer's transfer-speed contract is also documented in the
[Pico SDK timer interface](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#dma_timer_set_fraction).
Inactive-channel pacing and boundary behavior remain subject to physical
verification, including recovery under deliberate producer stalls.

## Startup and memory

The default `ram-code` option uses W25Q080 boot2 to establish XIP, then a
Flash-resident, stackless bootstrap copies executable code and runtime vectors
to SRAM and enters the copied normal Reset handler. Media and readonly assets
stay XIP. Embassy pre-init, data copy and BSS initialization are preserved.
The linker reserves 16 KiB for core 0; core 1 has an 8 KiB static stack.
See [port specification and validation](EMBASSY-PORT.md) for both build modes,
section checks, boot emulation and remaining hardware limits.
