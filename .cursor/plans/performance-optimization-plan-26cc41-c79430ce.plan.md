<!-- c79430ce-cc15-4445-b016-8621c1447c7f 6530f646-2616-4e5d-89d5-63d3055949f9 -->
# Performance Optimization Plan

## Overview

This plan optimizes the firmware (aitos) and UI library (displaitor) for the RP2040 microcontroller. Optimizations will be split into separate branches/PRs for each major area.

## Section 1: Firmware Main Loop Optimizations (aitos)

**Branch**: `perf/firmware-main-loop`

### Files to modify:

- `aitos/src/main.rs`

### Optimizations:

1. Remove unnecessary `Timer` clone (line 251) - use reference instead
2. Optimize GPIO pin reads - batch read or use direct port register access for control inputs
3. Remove debug logging in main loop (warn! on button S de-press)
4. Optimize button history logic - use bit manipulation more efficiently
5. Reduce fixed delay overhead - investigate if 400 cycle delay can be reduced or eliminated
6. Inline critical functions like `audio_set`, `audio_reset`

## Section 2: UI Library Rendering Optimizations (displaitor)

**Branch**: `perf/ui-rendering`

### Files to modify:

- `displaitor/src/apps/app_animation.rs`
- `displaitor/src/apps/app_image.rs`
- `displaitor/src/apps/app_menu.rs`
- `displaitor/src/games/app_pong.rs`

### Optimizations:

1. Cache decoded QOI frames in Animation app - decode once, reuse
2. Optimize color conversion - avoid ColorConverted wrapper where possible, use direct Rgb565
3. Reduce string buffer allocations - reuse buffers or use const strings where possible
4. Optimize menu rendering - only redraw changed text elements
5. Optimize Pong rendering - avoid clearing entire screen, use dirty rectangles
6. Remove unnecessary allocations in render paths

## Section 3: Audio Decoder Optimizations (qoa_decoder)

**Branch**: `perf/audio-decoder`

### Files to modify:

- `qoa_decoder/src/lib.rs`
- `qoa_decoder/src/lms.rs`

### Optimizations:

1. Optimize LMS predict() - unroll loop, use SIMD-friendly operations
2. Optimize LMS update() - unroll loop, optimize history shift
3. Optimize slice decoding loop - reduce bounds checks, better register usage
4. Inline critical decoding functions
5. Optimize bit manipulation in slice decoding

## Section 4: Microcontroller-Specific Optimizations (aitos)

**Branch**: `perf/microcontroller-optimizations`

### Files to modify:

- `aitos/src/main.rs`
- `aitos/Cargo.toml`

### Optimizations:

1. Use direct GPIO port register access for control inputs (bypass HAL overhead)
2. Add `#[inline]` attributes to hot-path functions
3. Configure compiler optimizations for embedded targets
4. Optimize memory access patterns
5. Use RP2040-specific optimizations (cache hints, instruction ordering)

## Section 5: String Buffer and Memory Optimizations (displaitor)

**Branch**: `perf/memory-optimizations`

### Files to modify:

- `displaitor/src/string_buffer.rs`
- `displaitor/src/apps/app_menu.rs`
- `displaitor/src/games/app_pong.rs`

### Optimizations:

1. Optimize FixedBuffer - avoid unnecessary bounds checks
2. Use const strings where possible instead of formatting
3. Reduce temporary allocations in text rendering
4. Optimize write_str implementation

## Implementation Order

1. Section 1 (Firmware Main Loop) - Quick wins, visible impact
2. Section 3 (Audio Decoder) - Critical for audio performance
3. Section 2 (UI Rendering) - Major visual impact
4. Section 4 (Microcontroller-Specific) - Platform-specific gains
5. Section 5 (Memory Optimizations) - Final polish

## Testing Strategy

- Use existing monitor to measure FPS improvements
- Verify audio quality remains unchanged
- Test all apps for visual correctness
- Run `cargo check` and `cargo clippy` after each section