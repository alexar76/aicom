# Sandbox trust model

Generated products run in an **iframe preview** and optional **isolated Python venv** for FastAPI sandboxes. This is **not** a full multi-tenant hypervisor.

## What we enforce

| Layer | Mechanism |
|-------|-----------|
| Browser | CSP on factory pages; sandbox iframe `sandbox` attribute where applicable |
| API | Authenticated `/api/sandbox/*` routes; path traversal checks on file reads |
| Preview Python | Per-sandbox venv under `data/sandbox_previews/<id>/venv` — **does not** mutate the main app `venv` |
| Network | Preview uvicorn binds locally; exposure is via factory reverse proxy only |

## What we do **not** guarantee

- **gVisor / Firecracker / Kata** — not deployed; untrusted code is not kernel-isolated.
- **CPU/memory quotas** — rely on OS cgroup limits in Compose (`deploy.resources`) where configured.
- **Outbound network** — preview apps may call external APIs if the generated code does so; block at egress firewall for strict deployments.

## Threat assumptions

- **Trusted operators** configure factory secrets and admin access.
- **Untrusted content** = generated product code executed in preview; treat as **soft isolation** suitable for demos and internal QA, not arbitrary public multi-tenant hosting without additional hardening.

## Hardening checklist (production)

1. Run preview workers on a separate host or VM from payment/admin DB.
2. Set `AIFACTORY_SANDBOX_PREVIEW_ENABLED=0` if previews are not required.
3. Cap upload sizes and disable arbitrary `pip install` in preview unless needed.
4. Scan artifacts with the security agent gate before `COMPLETED`.
5. Use read-only root filesystem + tmpfs for preview roots where possible.

Related: `web/backend/services/sandbox_preview_env.py`, `security/sandbox_isolation.py`.
