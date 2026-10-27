#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REV=bc0589710ff6aa2f50e08fb4d0a815d567bc0f3e
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

curl -fsSL "https://raw.githubusercontent.com/phoboslab/qoa/$REV/qoa.h" -o "$TMP/qoa.h"
${CC:-cc} -std=c99 -O2 -I"$TMP" "$ROOT/generate.c" -o "$TMP/generate"
"$TMP/generate" "$ROOT/nonzero_lms_two_frames.qoa" "$ROOT/nonzero_lms_two_frames.pcm16le"
