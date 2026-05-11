# Packaging templates (`full_software`)

These folders are **reference layouts** the Architect/Developer stages may mirror. Each ships **Railway-oriented** files so generated repos are deployable without inventing config from scratch.

## `full_stack_fastapi/`

| File | Role |
|------|------|
| `Dockerfile` | Multi-stage Python image (`uvicorn` on `$PORT`) |
| `docker-compose.yml` | Local / sandbox preview (`WEB_HOST_PORT`) |
| `nixpacks.toml` | Railway **Nixpacks** build when not using Dockerfile builder |
| `Procfile` | Process type `web` for Procfile-based hosts |
| `railway.json` | Railway **`$schema`** deploy hints (Dockerfile builder by default) |
| `app/main.py` | FastAPI app + sample HTML routes (`/`, `/login`, `/tasks`, `/settings`) + REST |

Gallery screenshots for the root README are produced from this template via **`scripts/capture_gallery_fullstack_packaging_demo.py`**.

## `full_stack_react_express/`

| File | Role |
|------|------|
| `server.js` | Minimal Express (`/health`, `/api/items`) |
| `package.json` | Node 20+ |
| `Dockerfile` | Alpine Node runtime |
| `docker-compose.yml` | Single-service compose |
| `nixpacks.toml` | Node Nixpacks |
| `Procfile` | `web` |
| `railway.json` | Same schema pattern as FastAPI template |

Extend with a Vite/React client and DB per product charter.
