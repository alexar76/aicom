# Screenshot gallery (README hero)

This folder backs the **three-to-five hero screenshots** in the root [README.md](../../README.md).

## How to refresh

1. With the app reachable at **`http://127.0.0.1:9080`** (default), from repo root:

   ```bash
   .venv/bin/python scripts/capture_gallery_landings.py
   ```

   Writes **`landing-01.webp` … `landing-06.webp`** by opening **`/api/sandbox/file/{sandbox_id}/index.html`** (generated page only — not the sandbox viewer shell). Override paths with **`GALLERY_PRODUCT_IDS`** and optional **`GALLERY_INDEX_RELPATH`** (default `index.html`).

2. Or manually: run products through the pipeline, then capture desktop **1440×900** WebP/PNG into this folder and update the root README table if filenames differ.

3. Optional: from `web/frontend` with the UI running, see `npm run capture-docs-screenshots` ([screenshots README](../assets/screenshots/README.md)) for **admin UI** shots under `docs/assets/screenshots/`.

The README hero table references **`landing-01.webp` … `landing-06.webp`** in this folder (3×2 grid).

## Full_software gallery (dashboard · login · CRUD · settings)

### A) Packaging template (fastest, no LLM)

From repo root, with Docker and Playwright installed:

```bash
.venv/bin/python scripts/capture_gallery_fullstack_packaging_demo.py
```

Uses **`packaging/templates/full_stack_fastapi`** (`docker compose up` → screenshots → `down -v`).

### B) Real pipeline product (compose sandbox)

Use **compose sandbox preview** so the iframe hits a real API + DB stack (not only static `index.html`).

1. Complete a **full_software** product with **`docker-compose.yml`** at repo root and UI routes (e.g. `/`, `/login`, `/tasks`, `/settings`).
2. Stack on **`http://127.0.0.1:9080`**, **`AIFACTORY_SANDBOX_COMPOSE_PREVIEW=1`** on the app container.
3. Run:

   ```bash
   GALLERY_FS_PRODUCT_ID=prod-xxxxxxxxxxxx \
     .venv/bin/python scripts/capture_gallery_full_software.py
   ```

   Override routes: **`GALLERY_FS_ROUTES=/,/login,/tasks,/settings`**

Writes **`fullstack-01.webp` … `fullstack-04.webp`** (one per route). Update the root README “full_software gallery” section if filenames change.

## Automated screen recording (Playwright `.webm`)

From repo root (stack running, default **http://127.0.0.1:9080**):

```bash
.venv/bin/python -m playwright install chromium   # once
DEMO_VIDEO_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD=admin123 \
  .venv/bin/python scripts/record_pipeline_demo_video.py
```

**Full_software narrative:** set **`DEMO_VIDEO_PROFILE=full_software`** and optionally **`DEMO_VIDEO_IDEA="…dashboard, auth, API…"`** so the scripted enqueue matches the Habr/LinkedIn story (idea → pipeline → working dashboard). See `scripts/record_pipeline_demo_video.py` header.

Writes under **`docs/gallery/recordings/`** and copies the newest take to **`pipeline-demo-latest.webm`**. Upload that file in Admin → **Live Monitor** or **Settings** → **Demo replay** if you want it inside the operator UI (or run **`scripts/sync_demo_replay_from_recording.py`** — see root README).

### Prune old pipeline rows (keep storefront-listed only)

Inside the running app container:

```bash
docker compose exec -T app /app/venv/bin/python3 /app/scripts/prune_pipeline_keep_storefront.py --dry-run
docker compose exec -T app /app/venv/bin/python3 /app/scripts/prune_pipeline_keep_storefront.py
```

Deletes SQLite products/tasks + matching `code/` / `specs/` / … dirs for anything **not** eligible for the public marketplace (same gates as the storefront API).
