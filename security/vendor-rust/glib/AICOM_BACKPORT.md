# GLib 0.18.5 compatible backport

This is the official MIT-licensed `glib` 0.18.5 crate with the two-line upstream
fix for RUSTSEC-2024-0429 / GHSA-wrw7-89jp-8q8g. `VariantStrIter::impl_get`
now provides a mutable out-pointer to the variadic C call. All other upstream
files, package version, public API, LICENSE and COPYRIGHT are preserved.

The compatible GTK 0.18 / Tauri 2 branch still requires GLib 0.18; changing only
GLib to 0.20 would create incompatible Rust types. A local Cargo path patch
selects this copy without changing the upstream version or hiding scan results.

See `AICOM_BACKPORT.json` for the verified crate SHA-256 and upstream commit.
The template carries an identical portable copy under `src-tauri/vendor/glib`.
Local optimized regression evidence is in
`artifacts/security-audit-2026-11-07/rust-unlocked/` in the canonical workspace.
