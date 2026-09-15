# Module boundaries

The repo is a monolith (~100k+ LOC). Boundaries are enforced by **domain registry** and **facades**, not separate deployables (yet).

## Service domains

Canonical list: `web/backend/services/registry.py` (`SERVICE_DOMAINS`).

| Domain | Facade | Responsibility |
|--------|--------|----------------|
| `pipeline` | — | Catalog, director, replay, methodology |
| `sandbox` | `sandbox_runtime` | Preview + hardened Docker entry |
| `storefront` | — | Listing, pricing, showcase clips |
| `economics` | `product_economics` | LLM cost per product |
| `platform` | `public_demo_guard` | Demo read-only, backup, users |
| `observability` | — | E2E artifacts, release cockpit |

**Rule:** New code in `web/backend/services/` must be listed under one domain in `registry.py`. Cross-domain imports should go through a facade module documented in the registry.

## Sandbox stack (two lifecycles)

| Layer | Module | Use |
|-------|--------|-----|
| Hardened `docker run` | `security/docker_sandbox.py` | Flags for isolation |
| Pipeline workspaces | `security/sandbox_isolation.py` | Long-lived sandboxes (tests / future pipeline) |
| HTTP preview | `web/backend/services/sandbox_runtime.py` | **Import here** for API + E2E |

Do not duplicate `hardened_docker_run_args` outside `docker_sandbox.py`.

## Orchestrator

- FSM: `orchestrator/state_machine.py` + `orchestrator/pipeline_transitions.py`
- Worker: single process today — see [scaling.md](./scaling.md)

## Admin API introspection

`GET /api/admin/platform/service-domains` returns the registry JSON for tooling and docs.
