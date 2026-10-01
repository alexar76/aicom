# Packaging templates

## Web (`full_software`)

Reference layouts the Architect/Developer stages may mirror for deployable web products.

### `full_stack_fastapi/`

| File | Role |
|------|------|
| `Dockerfile` | Multi-stage Python image (`uvicorn` on `$PORT`) |
| `docker-compose.yml` | Local / sandbox preview |
| `nixpacks.toml` | Railway Nixpacks build |
| `app/main.py` | FastAPI app + sample HTML routes |

### `full_stack_react_express/`

| File | Role |
|------|------|
| `server.js` | Minimal Express API |
| `package.json` | Node 20+ |
| `Dockerfile` | Alpine Node runtime |

## Desktop (`desktop_app`)

### `tauri_desktop/`

Tauri v2 shell: `src-tauri/` + `ui/` WebView. Storefront lists as **download-first** desktop SKU (no browser sandbox).

See `tauri_desktop/README.md` for `cargo tauri dev` / `cargo tauri build`.

Optional: Flutter desktop when admin/spec requests it (`pubspec.yaml` + `lib/main.dart`).
