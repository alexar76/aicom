# Sandbox trust model

Generated products are untrusted code. Host execution is refused by default, including QA pytest/plugins, property checks, npm/pip build hooks, migrations, seeds and FastAPI previews. A subprocess, working directory, scrubbed environment and Python venv do not isolate host privileges.

Use an isolated worker or the hardened Docker/Compose execution paths. A host-backed gate reports `generated_code_isolation_required` when it cannot run safely; it must not count that check as a pass. Static syntax/source inspection and already-built static previews remain available.

## What we enforce

| Layer | Mechanism |
|-------|-----------|
| Browser | CSP on factory pages; sandbox iframe `sandbox` attribute where applicable |
| API | Authenticated `/api/sandbox/*` routes; path traversal checks on file reads |
| Host execution | Refused unless explicitly enabled for disposable private development; always refused in production, public demo or container-required mode |
| Child processes | On the private local opt-in path, factory credentials, database URLs, publish tokens and Docker client credentials are still removed |
| Preview Python | The optional private development venv separates packages only; it is never treated as a security boundary |
| Preview proxy | Factory cookies, CSRF and factory-signed admin/customer Bearer tokens are never forwarded to generated applications; independent product Bearer tokens are preserved |
| Generated Compose | Rejects privileged mode, host namespaces, device/capability grants, host bind mounts, external resources, unsafe build paths/options, and secret-bearing interpolation before Docker sees the file |
| Network | Preview uvicorn binds locally; exposure is via factory reverse proxy. Generated Compose startup fails closed if the configured isolation network cannot be prepared |

## What we do **not** guarantee

- **gVisor / Firecracker / Kata** — not deployed; Docker alone is not a separate kernel.
- **A complete container adapter for every QA gate** — host-backed tests/builds fail closed until an isolated worker runs them.
- **Universal outbound blocking** — the Compose preview path can enforce its isolation network; private local host execution has no network sandbox.

## Threat assumptions

- **Trusted operators** configure factory secrets and admin access.
- **Untrusted content** = generated code, dependency installation/build hooks and project-local test/lint plugins. Public input never authorizes host execution.

## Disposable private development

Only a private development host may explicitly set `AIFACTORY_UNSAFE_ALLOW_HOST_GENERATED_CODE=1`. This permits generated code to read/write files and access processes/sockets with the developer's privileges; environment scrubbing does not prevent that. The flag is refused whenever `AIFACTORY_PROD`, `AIFACTORY_PRODUCTION`, `AIFACTORY_ENV=production|prod|live`, `AIFACTORY_DEMO_READONLY` or `AIFACTORY_SANDBOX_REQUIRE_CONTAINER` identifies a protected deployment. Customer pipeline creation is refused while this unsafe host flag is active, even if a deployment omitted its production marker.

## Hardening checklist (production)

1. Run preview workers on a separate host or VM from payment/admin DB.
2. Do not mount `/var/run/docker.sock` into the public API; keep Compose execution on a dedicated worker with a narrowly scoped Docker daemon.
3. Set `AIFACTORY_SANDBOX_PREVIEW_ENABLED=0` if previews are not required.
4. Cap upload sizes and disable arbitrary `pip install` in preview unless needed.
5. Scan artifacts with the security agent gate before `COMPLETED`.
6. Use read-only root filesystem + tmpfs for preview roots where possible.

Related: `core/child_env.py`, `web/backend/services/sandbox_preview_env.py`,
`core/generated_code_execution.py`, `web/backend/services/sandbox_compose_preview.py`, `security/sandbox_isolation.py`.
