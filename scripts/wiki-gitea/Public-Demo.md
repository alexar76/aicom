# Public demo mode (`AIFACTORY_DEMO_READONLY=1`)

> **Disclaimer:** The live site [magic-ai-factory.com](https://magic-ai-factory.com) is a **shared demonstration**. Login `admin` / `demo123` is public. Do **not** treat it as a private factory. Self-host for full owner controls.

---

## What it does

When **`AIFACTORY_DEMO_READONLY=1`** is set in `.env` (read by `docker compose`), the backend blocks operations that would let casual visitors corrupt the shared demo:

| Blocked | Why |
|---------|-----|
| Factory backup download | Prevents exfiltrating all demo products/secrets |
| Factory restore | Prevents wiping or replacing the shared catalog |
| **Settings → Save** | Keeps Director/autopilot/URLs stable for everyone (includes **GA / head snippet** — use `NEXT_PUBLIC_GA_MEASUREMENT_ID` in `.env` on demo) |
| **Admin password change** | Keeps shared `demo123` working |
| **Admin user CRUD** | No add/delete/edit; super-admin accounts are never deletable |

**Still allowed on demo:** browse Pipeline, LLM logs (read), **sandbox preview** (admin + storefront), git push from sandbox, create products (within normal pipeline), most read-only admin tabs.

There is **no** “delete product” button in the UI on any instance.

---

## Required on the public demo host

In project root **`.env`** (not in git — survives `docker compose build` / `up`):

```bash
AIFACTORY_DEMO_READONLY=1
```

`docker-compose.yml` passes it through:

```yaml
AIFACTORY_DEMO_READONLY: ${AIFACTORY_DEMO_READONLY:-0}
```

After changing `.env`:

```bash
docker compose build app
docker compose up -d app
```

`fill_production_env.py` appends `AIFACTORY_DEMO_READONLY=1` when you pass `--public-url` pointing at **magic-ai-factory.com** (see [[Deployment]]).

---

## Self-hosted instances

Leave **`AIFACTORY_DEMO_READONLY=0`** (default) or omit the variable. Use a **private** bootstrap password, enable backup/restore in **Settings**, and rotate credentials.

---

## How the UI shows it

- **Settings:** blue banner — backup/restore and platform saves disabled.
- **`GET /api/admin/auth/me`:** `public_demo: true`, `blocks_*` flags for the SPA.

Full detail: [`docs/security.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/security.md) · backup/restore: [[Owner-Guide]] §7
