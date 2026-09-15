# React SPA + Express API (reference stub)

Intended direction for **`full_software`** products that need a split browser client and Node API.

Shipped in this folder:

- `server.js` — health + sample `/api/items`
- `Dockerfile`, `docker-compose.yml` — local and Railway-style container runs
- `nixpacks.toml`, `Procfile`, `railway.json` — Railway (Nixpacks or Dockerfile builder)

Add a Vite React app, Prisma, and root `docker-compose.yml` in generated repos per Architect charter.

This folder is a **placeholder**: add a minimal reference layout here when you want the Developer agent to mirror file naming and routing conventions (e.g. `client/` Vite + React, `server/` Express + TypeScript).

Until then, the factory ships **`packaging/templates/full_stack_fastapi/`** as the primary full-stack reference.
