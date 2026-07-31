# Full-stack FastAPI template

Minimal runnable layout aligned with factory **full_software** expectations:

- `GET /health` for probes and runtime checks
- `GET|POST|PATCH|DELETE /api/items` as a CRUD-shaped surface (in-memory; swap for SQLAlchemy/etc.)

Included for **Docker / Railway**:

- `Dockerfile` (multi-stage), `docker-compose.yml`
- `nixpacks.toml`, `Procfile`, `railway.json`

Copy into a generated product repo, add migrations, authentication, and deployment manifests (Docker/K8s) as needed.

For SPA/login QA beyond crawl limits, copy **`e2e-scenarios.json.example`** → **`e2e-scenarios.json`** and set **`AIFACTORY_E2E_*`** credentials (see factory `.env.example`).
