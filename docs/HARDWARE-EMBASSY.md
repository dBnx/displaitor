# Embassy hardware validation scope

An RP2040 board was programmed and readback-verified over SWD. Normal RAM
firmware copied executable text and vectors into SRAM; text matched its ELF,
and VTOR pointed to `0x20000000`. The runtime preserves connector GPIOs, active-low
buttons, display orientation/colour compensation, power outputs and PWM audio.

Hardware testing found a DMA reload/completion issue that offline checks did not
expose. The repair uses actual completion tracking and a firmware-timed capture
window; hardware audio checks then passed. This establishes the measured digital
stream behavior, not subjective audible quality or long-run power robustness.

The public source substitutes neutral scroller messages and has separate offline
build/test evidence. No binaries, RAM/flash dumps, probe serials or local session
logs are published. See [validation](VALIDATION.md) and the
[Embassy design](EMBASSY-PORT.md) for scope and build options.
