#!/usr/bin/env bash
# Offline verification: no runner, flashing, probe, or attached hardware required.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
cargo fmt --all -- --check
cargo test --locked --workspace --all-targets
cargo clippy --locked --workspace --all-targets --all-features -- -D warnings
cargo run --locked -p simulaitor --no-default-features -- --smoke
python3 -m unittest discover -s tools -p 'test_*.py' -v
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy cargo run --locked -p simulaitor -- --frames 20
cargo clippy --locked -p aitos --all-features --target thumbv6m-none-eabi -- -D warnings
cargo build --locked -p aitos --features firmware --target thumbv6m-none-eabi --release
