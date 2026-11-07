#!/bin/bash
set -uo pipefail
rustc --version > /work/environment.log
cargo --version >> /work/environment.log
pkg-config --modversion glib-2.0 >> /work/environment.log
cargo test --manifest-path /work/before/Cargo.toml --release --lib > /work/before.log 2>&1
before_rc=$?
printf '%s\n' "$before_rc" > /work/before.rc
cargo test --manifest-path /work/after/Cargo.toml --release --lib > /work/after.log 2>&1
after_rc=$?
printf '%s\n' "$after_rc" > /work/after.rc
cat /work/environment.log
printf 'before_rc=%s after_rc=%s\n' "$before_rc" "$after_rc"
tail -15 /work/before.log
tail -15 /work/after.log
exit "$after_rc"
