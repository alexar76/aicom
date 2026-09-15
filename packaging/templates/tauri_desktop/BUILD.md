# Release build matrix

| OS | Command | Output |
|----|---------|--------|
| macOS | `cargo tauri build` | `.dmg` / `.app` in `target/release/bundle/` |
| Windows | `cargo tauri build` | `.msi` / `.exe` |
| Linux | `cargo tauri build` | `.deb` / `.AppImage` |

CI: extend with GitHub Actions `tauri-action` when product ships.
