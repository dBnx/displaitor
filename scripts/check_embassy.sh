#!/usr/bin/env bash
# Offline release/linker matrix. Does not invoke a runner or contact hardware.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

validation_python="${VALIDATION_PYTHON:-python3}"
if ! command -v -- "$validation_python" >/dev/null 2>&1; then
    echo "Validation Python not found: $validation_python" >&2
    echo 'Set VALIDATION_PYTHON to a Python interpreter with tools/requirements-validation.txt installed.' >&2
    exit 1
fi
"$validation_python" - <<'PY'
import importlib.util
import sys

missing = [name for name in ("elftools", "unicorn") if importlib.util.find_spec(name) is None]
if missing:
    print("Missing ELF validation dependencies: " + ", ".join(missing), file=sys.stderr)
    print("Install with this interpreter: python -m pip install -r tools/requirements-validation.txt",
          file=sys.stderr)
    raise SystemExit(1)
PY

archive="target/embassy-validation"
mkdir -p -- "$archive"
# Cargo metadata respects CARGO_TARGET_DIR and configuration overrides.
build_root="$(cargo metadata --locked --no-deps --format-version 1 |
    "$validation_python" -c 'import json,sys; print(json.load(sys.stdin)["target_directory"])')"
artifact="$build_root/thumbv6m-none-eabi/release/aitos"

build_and_check() {
    local name="$1" mode="$2" features="$3"
    local -a cargo_options=() elf_options=()
    if [[ "$mode" == xip ]]; then
        cargo_options+=(--no-default-features)
    else
        elf_options+=(--emulate)
    fi
    echo "Building and checking $name"
    cargo build --locked -p aitos --target thumbv6m-none-eabi --release \
        --features "$features" "${cargo_options[@]}" 2>&1 | tee "$archive/$name.build.log"
    cp -- "$artifact" "$archive/$name.elf"
    "$validation_python" scripts/check_elf.py "$archive/$name.elf" \
        --expect "$mode" "${elf_options[@]}" | tee "$archive/$name.check.log"
}

build_and_check ram-profiling ram profiling
build_and_check xip-profiling xip profiling
build_and_check xip-default xip firmware
# Leave the normal Cargo output as the standard, non-profiling RAM firmware.
build_and_check ram-default ram firmware
"$validation_python" scripts/test_elf_validation.py "$archive/ram-default.elf" \
    2>&1 | tee "$archive/negative-tests.log"
echo "All four release variants passed; archived ELFs and logs: $archive"
