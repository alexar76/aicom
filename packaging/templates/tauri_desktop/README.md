# Tauri desktop template (AI-Factory)

## Prerequisites

- Rust toolchain (`rustup`)
- [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for your OS

## Development

```bash
cd src-tauri
cargo tauri dev
```

## Release build

```bash
cd src-tauri
cargo tauri build
```

Artifacts appear under `src-tauri/target/release/bundle/`.

## Hub SKU

Listed on AI Market as `desktop_app` with capability `{slug}.desktop@v1` (source ZIP download).
