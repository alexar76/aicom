# Sandbox trust model

Generated products run in an **iframe preview** and optional **isolated Python venv** for FastAPI sandboxes. This is **not** a full multi-tenant hypervisor.

## What we enforce

| Layer | Mechanism |
|-------|-----------|
| Browser | CSP on factory pages; sandbox iframe `sandbox` attribute where applicable |
| API | Authenticated `/api/sandbox/*` routes; path traversal checks on file reads |
| Child processes | Factory credentials, database URLs, publish tokens, and Docker client credentials are removed before generated test/build/runtime code starts |
| Preview Python | Per-sandbox venv under `data/sandbox_previews/<id>/venv` — **does not** mutate the main app `venv`; generated pytest runs have a bounded timeout |
| Generated Compose | Rejects privileged mode, host namespaces, device/capability grants, host bind mounts, external resources, unsafe build paths/options, and secret-bearing interpolation before Docker sees the file |
| Network | Preview uvicorn binds locally; exposure is via factory reverse proxy. Generated Compose startup fails closed if the configured isolation network cannot be prepared |

## What we do **not** guarantee

- **gVisor / Firecracker / Kata** — not deployed; untrusted code is not kernel-isolated.
- **Complete CPU/memory isolation** — generated tests and previews remain host processes unless the deployment places workers inside constrained containers/VMs.
- **Universal outbound blocking** — the Compose preview path can enforce its isolation network, but direct Python previews may call external APIs; block at the host/VM egress firewall for strict deployments.

## Threat assumptions

- **Trusted operators** configure factory secrets and admin access.
- **Untrusted content** = generated product code executed in preview; treat as **soft isolation** suitable for demos and internal QA, not arbitrary public multi-tenant hosting without additional hardening.

## Hardening checklist (production)

1. Run preview workers on a separate host or VM from payment/admin DB.
2. Do not mount `/var/run/docker.sock` into the public API; keep Compose execution on a dedicated worker with a narrowly scoped Docker daemon.
3. Set `AIFACTORY_SANDBOX_PREVIEW_ENABLED=0` if previews are not required.
4. Cap upload sizes and disable arbitrary `pip install` in preview unless needed.
5. Scan artifacts with the security agent gate before `COMPLETED`.
6. Use read-only root filesystem + tmpfs for preview roots where possible.

Related: `core/child_env.py`, `web/backend/services/sandbox_preview_env.py`,
`web/backend/services/sandbox_compose_preview.py`, `security/sandbox_isolation.py`.
