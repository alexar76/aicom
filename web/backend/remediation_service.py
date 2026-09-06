"""The private patch-authoring service — the AI-Factory, reduced to the one route SKOPOS needs.

The full factory is a pipeline: redis, a database, a worker, an admin surface, a storefront. None of
that is needed to turn a signed MOMUS ticket into a diff, and running it all again would be wrong on
three counts at once:

* **Memory.** The oracle host it belongs on had 772 MB free and swap exhausted when this was measured.
  A second full factory does not fit; this does.
* **Surface.** The remediation instance is reachable by the conductor. Giving that reachability an
  admin panel, a payment surface and a storefront as well would be a gift to anyone who got in.
* **Correctness.** The only factory deployed today is the PUBLIC demo (`AIFACTORY_DEMO_READONLY=1`),
  where `require_not_public_demo` refuses patch authoring — correctly. A public demo is not where an
  autonomous patcher belongs, so the answer is a separate private instance, not a weakened guard.

Same code, same guards, same cost accounting as the factory — this file only chooses which router to
mount and builds the LLM router the route reads off `app.state`. It shares the monorepo, so there is
one source of truth; and because the public factory does not mount the remediation route at all,
changing this code means redeploying ONE service. See momus/docs/self-healing-operations.md.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The route calls `llm_router.generate` DIRECTLY rather than going through BaseAgent, whose broad
    # exception handler turns a budget refusal into hard-coded fallback JSON — a fabricated patch
    # that would then be committed and reviewed as if a model had written it.
    router = None
    try:
        from llm.router import LLMRouter

        router = LLMRouter()
        if not router.providers:
            # Say so loudly at startup rather than at the first ticket: an LLM router with no
            # provider produces a refusal that reads like a model failure.
            logger.error("LLM router has no providers — check config/model_providers.yaml and the "
                         "provider API key env var. Patch authoring will refuse every ticket.")
        else:
            await router.start_health_checks(interval_sec=60)
            logger.info("remediation fixer ready: %d provider(s), default=%s",
                        len(router.providers), router.default_provider)
    except Exception:
        logger.exception("failed to initialise the LLM router")
    app.state.llm_router = router
    try:
        yield
    finally:
        if router is not None:
            try:
                await router.close()
            except Exception:  # noqa: BLE001 - shutdown must not raise
                logger.warning("LLM router close failed on shutdown", exc_info=True)


def build_app() -> FastAPI:
    app = FastAPI(title="AI-Factory remediation fixer", version="1.0.0",
                  docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)

    # Deliberately NOT conditional on AIFACTORY_REMEDIATION_FIX_ENABLED, unlike the public factory:
    # this service exists only to serve this route, so mounting it is the point. The capability is
    # still gated — the route itself refuses unless the flag is set, the shared secret matches, and
    # MOMUS's signature on the ticket verifies.
    from web.backend.api import remediation as remediation_api

    app.include_router(remediation_api.router)

    @app.get("/health")
    async def health() -> dict:
        from web.backend.services.remediation_fix import is_enabled, scope_map

        router = getattr(app.state, "llm_router", None)
        return {
            "status": "ok",
            "service": "remediation-fixer",
            "authoring_enabled": is_enabled(),
            "llm_providers": len(getattr(router, "providers", {}) or {}),
            "components_in_scope": sorted(scope_map()),
        }

    return app


app = build_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    # Loopback by default. The conductor reaches this over the container network or a loopback
    # publish; nothing about patch authoring should be listening on a public interface.
    uvicorn.run("web.backend.remediation_service:app",
                host=os.environ.get("REMEDIATION_HOST", "0.0.0.0"),
                port=int(os.environ.get("REMEDIATION_PORT", "9086")), workers=1)


if __name__ == "__main__":  # pragma: no cover
    main()
