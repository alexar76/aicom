"""Hub API — FastAPI application exposing federation endpoints.

Core routes: .well-known, manifest (v2), federated search, routing proxy,
federation announce, peers list, stats, plugin catalog.

Plugins extend the hub via entry points — they register their own routes
and hook into the invoke pipeline (pre/post checks). See plugin.py.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from aimarket_hub.metrics import (
    metrics_payload,
    record_invoke,
    set_federation_peer_health,
)

# Pydantic models imported from api_models
from aimarket_hub.api_models import (
    AnnounceRequest,
    AppealRequest,
    AuditClaimRequest,
    AuditSyncRequest,
    ChannelCloseRequest,
    ChannelOpenRequest,
    PermissionViolationRequest,
    LotteryEntitlementRequest,
    ReceiptVerifyRequest,
    InvokeRequest,
    IpoRequest,
    ReputationEventsRequest,
    StudioRunRequest,
)
from aimarket_hub.channels import (
    channel_escrow_binding,
    _is_production_mode,
    capture_hold,
    channel_balance,
    channel_stats,
    close_channel,
    debit_channel,
    hold_channel,
    open_channel,
    payment_readiness,
    release_hold,
)
from aimarket_hub import consumer_labels
from aimarket_hub import deposit_watch
from aimarket_hub import ecosystem
from aimarket_hub import openapi_merge
from aimarket_hub import security_posture
from aimarket_hub import terminal_ssr
from aimarket_hub import credits
from aimarket_hub import topup
from aimarket_hub import mandates
from aimarket_hub import subcontract
from aimarket_hub import chain_net
from aimarket_hub import realm
from aimarket_hub import theme
from aimarket_hub import settle
from aimarket_hub import deliveries
from aimarket_hub import x402
from aimarket_hub import contracts_declaration
from aimarket_hub import verified_settlement
from aimarket_hub.access_policy import capability_access_mode
from aimarket_hub.invoke_outcome import (
    OUTCOME_INCOMPLETE,
    classify_invoke_outcome,
    missing_required_inputs,
)
from aimarket_hub.verified_settlement import VerifiedSettlementService

# Reserved consumer_hub for operator/admin smoke tests. Public sandbox visitors
# and paying channels must NOT use this — otherwise /stats/live collapses all
# real traffic into "operator_self" and hides external demand.
OPERATOR_SELF_CONSUMER = "operator_self"

#: The deposit-claim registry's name for an operator crediting an on-chain payment by hand.
OPERATOR_CREDIT_STACK = "aimarket-hub-operator-credit"

from aimarket_hub.config import HubConfig
from aimarket_hub.catalog import catalogue_display_name
from aimarket_hub.database import HubDatabase
from aimarket_hub.demo_seeder import seed_capabilities
from aimarket_hub.models import InvocationStat, Peer
from aimarket_hub.plugin import PluginRegistry
from aimarket_hub.safety_gate import default_safety_gate
from aimarket_hub.sandbox_trials import (
    consume_sandbox_trial,
    ensure_trial_ledger,
    release_sandbox_trial,
    free_tier_covers,
    model_budget_refusal,
    sandbox_demo_result,
    sandbox_enabled,
    sandbox_quota,
    sandbox_stub_invoke_enabled,
    trial_policy,
)
from aimarket_hub.semantic_search import interpret_intent
from aimarket_hub.signing import Signer, pqc_required, receipt_signature_version
from aimarket_hub.trust import TrustScorer

from aimarket_hub.hub_routes import wellknown as _wellknown_routes
from aimarket_hub.hub_routes import catalog as _catalog_routes
from aimarket_hub.hub_routes import supply as _supply_routes
from aimarket_hub.hub_routes import verification as _verification_routes
from aimarket_hub.hub_routes import mandates as _mandates_routes
from aimarket_hub.hub_routes import invoke as _invoke_routes
from aimarket_hub.hub_routes import federation as _federation_routes
from aimarket_hub.hub_routes import reputation as _reputation_routes
from aimarket_hub.hub_routes import accounts as _accounts_routes
from aimarket_hub.hub_routes import market_stats as _market_stats_routes
from aimarket_hub.hub_routes import capital as _capital_routes
from aimarket_hub.hub_routes import channels as _channels_routes
from aimarket_hub.hub_routes import plugins as _plugins_routes
from aimarket_hub.hub_routes import agents as _agents_routes
from aimarket_hub.hub_routes import pages as _pages_routes
from aimarket_hub.hub_routes import middleware as _middleware_routes
from aimarket_hub.hub_routes import payments as _payments_routes
from aimarket_hub.hub_routes import credentials as _credentials_routes
from aimarket_hub.hub_routes import rate_limits as _rate_limits_routes

# Moved out of this module; re-exported because hub_routes/* and tests import them from here.
from aimarket_hub.request_guards import (  # noqa: F401
    _SAFE_ID_CHARS,
    _money_arg,
    _trim_rate_buckets,
    _env_positive_int,
    _parse_subject_tokens,
    _parse_trusted_proxies,
    _INTERNAL_NETS,
    _client_address,
    _announced_relay,
    _is_safe_path,
)
from aimarket_hub.peer_routing import (  # noqa: F401
    _MAX_REPORTED_PRICE_USD,
    _MAX_REPORTED_LATENCY_MS,
    _as_float,
    _PEER_PAYMENT_HEADERS,
    _peer_payment_headers,
    _PEER_ENDPOINT_TTL_S,
    _peer_endpoint_cache,
    _peer_seller_direct,
    _peer_is_aimarket_hub,
    _BUYER_SALT,
    _opaque_buyer,
    _provider_channel_ref,
    _peer_invoke_endpoint,
    _peer_sells_direct,
)
from aimarket_hub.catalogue_view import (  # noqa: F401
    _INPUT_HINT_KEYS,
    _input_requirements,
    _observe_answer,
    _catalogue_route,
    _catalogue_snapshot,
)
from aimarket_hub import peer_routing
from aimarket_hub.hub_lifespan import make_lifespan

logger = logging.getLogger(__name__)

# One worker for the whole process, created on first use. Inbound federation discovery is a
# courtesy: it must never compete with request handling, and it must never grow without
# bound. Deliberately NOT per-app — create_app() runs once in production but hundreds of
# times in a test suite, and a pool per app leaked a thread each time (measured: the suite
# went from 2.5 to 17 minutes before this was a singleton).
_INBOUND_POOL = None
_INBOUND_POOL_LOCK = threading.Lock()


def _inbound_pool():
    global _INBOUND_POOL
    if _INBOUND_POOL is None:
        with _INBOUND_POOL_LOCK:
            if _INBOUND_POOL is None:
                from concurrent.futures import ThreadPoolExecutor

                _INBOUND_POOL = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="aimarket-inbound"
                )
    return _INBOUND_POOL

_HUB_STARTED_AT = time.time()


def _ceil_to_cents(usd: float) -> float:
    """Round a price UP to a whole cent — the granularity both money paths already use.

    `channels._dollars_to_cents_bill` bills `max(1, ceil(usd*100))` cents and
    `escrow_bridge.escrow_verify.usd_to_base_units` converts a signed amount the same way,
    so any quote finer than a cent is a number the buyer cannot sign and the hub would not
    honour: the verifier demands the cent it ceils to, the client re-signs the quote it was
    given, and the purchase deadlocks with the deposit already on chain.
    """
    if usd <= 0:
        return 0.0
    return math.ceil(round(usd * 100, 6)) / 100.0


# ── Router factory ─────────────────────────────────────────────


def _authorization_too_short(authorization: Any) -> bool:
    """True when an escrow DebitAuthorization dies before a verified call could be collected."""
    try:
        deadline = int((authorization or {}).get("deadline") or 0)
    except (TypeError, ValueError, AttributeError):
        return False  # malformed: the bridge's own verification refuses it with a precise reason
    return deadline < time.time() + verified_settlement.min_authorization_deadline_s()


def create_app(
    config: HubConfig | None = None,
    db: HubDatabase | None = None,
    signer: Signer | None = None,
    trust_scorer: TrustScorer | None = None,
    plugins: PluginRegistry | None = None,
) -> FastAPI:
    """Create the hub FastAPI app.

    Args:
        config: Hub configuration
        db: Hub database
        signer: Ed25519 signer
        trust_scorer: Trust score computer
        plugins: Plugin registry (auto-discovers from entry_points if None)
    """
    config = config or HubConfig()
    if db is None:
        # Production must never silently fall back to a local SQLite file when an env file
        # is missing or malformed. That creates a fresh, apparently healthy empty market
        # beside the real PostgreSQL ledger — the worst failure mode for balances and trials.
        # Injected databases remain available to isolated tests; the standalone production
        # entry point is fail-closed.
        database_url = (config.database_url or "").strip()
        if _is_production_mode() and not database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError(
                "production Hub requires DATABASE_URL=postgresql://...; "
                "SQLite fallback is disabled when AIFACTORY_PROD=1"
            )
        db = HubDatabase(config.db_path, database_url=database_url)
    # The free tier is part of this hub's contract with strangers, so its ledger is built
    # here rather than on the first call that needs it. Lazily, a hub that cannot keep trial
    # counters starts clean, reports healthy, and 500s at the visitor.
    if sandbox_enabled():
        ensure_trial_ledger()
    if signer is None:
        from aimarket_hub.signing import hub_signs_hybrid, pqc_signing_setting

        hybrid = hub_signs_hybrid(config.signing_key_path)
        signer = Signer(config.signing_key_path, pqc=hybrid)
        if hybrid and pqc_signing_setting() is None:
            logger.info("Signing hybrid (Ed25519 + ML-DSA-65) by default, as every AIMarket hub "
                        "does; AIMARKET_PQC=0 signs Ed25519 only.")
        if pqc_signing_setting() is False and os.path.exists(f"{config.signing_key_path}_mldsa"):
            logger.warning(
                "AIMARKET_PQC=0 on a hub that holds an ML-DSA-65 key: peers that pinned it will "
                "refuse this hub's Ed25519-only documents (ratchet). Unset it to keep signing hybrid.")
    # Bind the credits rail to THIS app's database. A new app may be a new database
    # (every test builds one), and a rail still pointed at the previous file would debit
    # accounts that no longer describe this hub.
    # Bound to THIS app, not to a module global. A process can hold more than one hub —
    # every test builds several, and the cross-hub settlement suite runs two real hubs that
    # pay each other — and a shared global meant the second app's ledger silently answered
    # the first app's requests: a valid key on hub B was looked up in hub A's database and
    # came back 401. `configure` still sets the module handle for single-app entry points
    # (the CLI, quickstart), but nothing inside a request path reads it.
    hub_credits = credits.configure(db._conn)
    # Mandates and subcontracting (aimarket-protocol/mandates.md) live beside the credits
    # ledger they constrain, on the same backend, bound to this app for the same reason.
    hub_mandates = mandates.MandateStore(db._conn, config.hub_url)
    hub_jobs = subcontract.JobStore(db._conn, signer, config.hub_url)
    hub_x402 = x402.PaymentStore(db._conn)
    hub_settle = settle.PaymentStore(db._conn)
    hub_invoices = settle.InvoiceStore(db._conn)
    hub_topups = topup.TopupStore(db._conn)
    hub_deposits = deposit_watch.DepositStore(db._conn)
    settle.refuse_unbound_setting()
    # Which realm is this? Logged, never published: the bubble must be indistinguishable
    # from inside, so the only reader told about it is the operator, who is outside.
    if realm.is_uni():
        logger.warning(
            "[realm=uni] SEALED BUBBLE — chain id %s, simulated economy. Every amount this "
            "hub reports is virtual and must never be quoted as revenue.",
            realm.uni_chain_id(),
        )
        # Peers admitted through a door the seal did not watch (see realm.peer_inside).
        try:
            realm.evict_outside_peers(db)
        except Exception as exc:  # noqa: BLE001 - logged loudly; the doors still hold
            logger.error("realm: could not evict outside peers: %s", exc)
    if config.crypto_enabled:
        # Fail closed at boot rather than at the first payment offer: a hub that has already
        # advertised a mainnet asset inside a bubble cannot take it back.
        try:
            spec = chain_net.active_network()
            realm.assert_sealed(
                chain_id=spec.chain_id, rpc_urls=spec.rpc_urls, addresses=spec.addresses,
            )
        except realm.RealmBreach:
            raise
        except Exception as exc:  # noqa: BLE001 - a resolver problem is not a breach
            logger.warning("realm: could not verify the chain configuration: %s", exc)
    # Whose hub is this? Every page the hub serves used to be branded, linked and
    # escrow-stamped for one specific deployment, so rebranding meant editing source.
    theme.configure(
        name=config.hub_name,
        hub_url=config.hub_url,
        source_url=config.source_url,
        escrow_url=(
            f"https://basescan.org/address/{config.escrow_evm_address.strip()}"
            if config.escrow_evm_address.strip() else ""
        ),
        ecosystem_links=config.ecosystem_links,
    )

    # A new app is a new hub: different config, possibly a different peer set. Carrying
    # a cached transport decision in from a previous instance in the same process is
    # wrong, and it is observable — running the federated-invoke suite in one process
    # made a peer resolved by an earlier test keep its endpoint for a later test that
    # had configured its well-known to fail, so the legacy-fallback assertion saw the
    # cached endpoint instead. Found by building the image and running the suite where
    # it can actually execute; both local interpreters skip these tests at fixture setup.
    peer_routing._peer_endpoint_cache.clear()
    peer_routing._peer_seller_direct.clear()
    trust_scorer = trust_scorer or TrustScorer(db)
    builtin_safety = default_safety_gate()  # Built-in fallback
    # Pay-on-Verified settlement worker (buyer-opt-in escrow holds; env-gated per invoke).
    verify_svc = VerifiedSettlementService(db=db, signer=signer, consumer_hub=OPERATOR_SELF_CONSUMER)

    # Seed marketplace with initial capability catalog on first start.
    #
    # Never in production. The seeded showcase exists so a fresh hub is not empty, and
    # every one of its twelve rows is unexecutable — no invoke_url, no static pack — so on
    # a real deployment they are stock that cannot be delivered. `seed_capabilities`
    # re-creates them whenever the local count reaches zero, which makes deleting them a
    # temporary act: they came back on the next restart. Cleaning the catalogue and then
    # having the next deploy undo it is worse than never seeding, so production opts out
    # here rather than relying on AIMARKET_SKIP_SEED being remembered in a deploy capture.
    _prod = os.environ.get("AIFACTORY_PROD", "").strip().lower() in ("1", "true", "yes")
    _skip = os.environ.get("AIMARKET_SKIP_SEED", "").strip().lower() in ("1", "true", "yes")
    if not _skip and not _prod:
        seeded = seed_capabilities(db)
        if seeded:
            import logging
            logging.getLogger(__name__).info("Seeded %d marketplace capabilities", seeded)

    # Import real products from AI-Factory if bridge is available
    try:
        from aimarket_hub.factory_bridge import import_factory_products
        real = import_factory_products(db)
        if real:
            import logging
            logging.getLogger(__name__).info("Imported %d real factory products", real)
    except Exception:
        pass

    # Build multilingual document profiles before the first visitor types. The profile
    # cache is only worthwhile for a real catalogue; tiny unit-test/demo databases stay
    # instant. Ranking itself is local and read-only.
    if db.count_capabilities() > 20:
        with contextlib.suppress(Exception):
            db.search_capabilities_detailed("weather wildfire navigation proof", limit=1)

    # Plugin discovery
    if plugins is None:
        plugins = PluginRegistry()
        plugins.discover(db)
        plugins.startup_all(db)

    if not config.crypto_enabled:
        access = (
            "prepaid credits can still enforce 402 via X-API-Key"
            if credits.enabled()
            else "free/sandbox tier active; no payment rail can enforce 402"
        )
        logger.warning(
            "[crypto-disabled] AIFACTORY_CRYPTO_ENABLED=0 — payment channels offline; "
            "%s; no on-chain verification/escrow; NFT minting "
            "blocked. Manifest/receipt signing and federation are unaffected. "
            "Set AIFACTORY_CRYPTO_ENABLED=1 to enable the on-chain economy.",
            access,
        )

    # Background work for the app's lifetime (crawl, sweeps, deposit watch, …): hub_lifespan.py.
    # slash_registry and the deposit watcher are bound further down and reach it through here.
    lifespan_late = SimpleNamespace()
    _lifespan = make_lifespan(
        config=config, signer=signer, verify_svc=verify_svc, plugins=plugins,
        hub_credits=hub_credits, hub_mandates=hub_mandates, hub_jobs=hub_jobs,
        late=lifespan_late, db=db,
    )

    app = FastAPI(
        title=f"{config.hub_name} — AIMarket Hub v3",
        version=config.hub_version,
        description="Lean federation hub for AI capability discovery and routing. Plugins extend functionality.",
        lifespan=_lifespan,
    )
    _own_openapi = app.openapi
    app.openapi = lambda: openapi_merge.merged(_own_openapi())  # type: ignore[method-assign]
    # CORS: default to empty allowlist (require AIMARKET_CORS_ORIGINS to enable cross-origin).
    # Previous default of ["*"] enabled drive-by CSRF on state-changing endpoints.
    # Idempotency-Key on paid invokes, innermost so every other layer sees a replay as an answer.
    from aimarket_hub.idempotency import InvokeIdempotency

    app.add_middleware(InvokeIdempotency, conn=db._conn)
    _cors_env = os.environ.get("AIMARKET_CORS_ORIGINS", "").strip()
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Content-Type", "Authorization", "X-Payment-Channel", "X-Payment-Channel-Secret",
            "X-AIMarket-Affiliate", "X-API-Key", "X-AIMarket-Mandate",
            "X-AIMarket-Mandate-Proof", "X-AIMarket-A2A-Proof",
            "X-Payment", "PAYMENT-SIGNATURE", "X-Payment-Nonce", "X-Payment-Secret",
            "X-AIMarket-Sandbox-Visitor", "X-Market-Signature", "X-AIMarket-Routing-Hub",
            "X-AIMarket-Routing-Fee", "X-AIMarket-Buyer", "X-AIMarket-Crawler", "X-Provider-Signature",
            "A2A-Version", "A2A-Extensions", "Idempotency-Key",
        ],
    )

    # Middleware and /metrics.
    _middleware_routes.register(
        app=app,
        config=config,
        db=db,
        hub_invoices=hub_invoices,
        signer=signer,
    )

    # Admin token for federation/crawl-control endpoints.
    # If unset, those endpoints are disabled (fail-closed).
    _ADMIN_TOKEN = os.environ.get("AIMARKET_ADMIN_TOKEN", "").strip()
    if not _ADMIN_TOKEN:
        logger.warning(
            "AIMARKET_ADMIN_TOKEN not set — public Hub observations still land "
            "in quarantine, but federation approval and crawl-control requests "
            "will be rejected. Set this env var to enable operator actions."
        )

    def _require_admin(authorization: str) -> None:
        """Reject if Bearer token doesn't match AIMARKET_ADMIN_TOKEN. Fail-closed."""
        import hmac
        if not _ADMIN_TOKEN:
            raise HTTPException(
                status_code=503,
                detail="Admin endpoints disabled: AIMARKET_ADMIN_TOKEN not configured",
            )
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization[7:]
        if not hmac.compare_digest(token, _ADMIN_TOKEN):
            raise HTTPException(status_code=403, detail="Invalid admin token")

    def _is_admin_bearer(authorization: str) -> bool:
        """True when Authorization is a valid admin Bearer (no raise)."""
        import hmac
        if not _ADMIN_TOKEN or not authorization.startswith("Bearer "):
            return False
        return hmac.compare_digest(authorization[7:], _ADMIN_TOKEN)

    # Payment helpers for invoke.
    payments_scope = _payments_routes.register(
        _is_admin_bearer=_is_admin_bearer,
        config=config,
        hub_credits=hub_credits,
        hub_invoices=hub_invoices,
        hub_settle=hub_settle,
    )
    _bind_hub_fee_payee = payments_scope._bind_hub_fee_payee
    _bind_listing_payee = payments_scope._bind_listing_payee
    _credit_hearth_owner = payments_scope._credit_hearth_owner
    _pay_publisher_share = payments_scope._pay_publisher_share
    _payment_hint = payments_scope._payment_hint
    _payment_ways = payments_scope._payment_ways
    _pays_a_third_party = payments_scope._pays_a_third_party
    _release_market_payment = payments_scope._release_market_payment
    _resolve_invoke_consumer_hub = payments_scope._resolve_invoke_consumer_hub
    _settle_market_payment = payments_scope._settle_market_payment
    _unbind_payee = payments_scope._unbind_payee

    # Credential checks.
    credentials_scope = _credentials_routes.register(
        _ADMIN_TOKEN=_ADMIN_TOKEN,
        config=config,
        hub_credits=hub_credits,
    )
    _AGENT_TOKENS = credentials_scope._AGENT_TOKENS
    _NS_AGENT = credentials_scope._NS_AGENT
    _NS_PUBLISHER = credentials_scope._NS_PUBLISHER
    _credits_publisher = credentials_scope._credits_publisher
    _ecosystem_policy = credentials_scope._ecosystem_policy
    _require_stake_subject = credentials_scope._require_stake_subject
    _require_subject_credential = credentials_scope._require_subject_credential

    # Reverse-proxy trust for the per-IP rate limits below. See _client_address: without
    # a declared proxy the hub keys on the raw peer, which behind deploy/nginx/*.conf is
    # the proxy itself — one bucket for the whole internet.
    _TRUSTED_PROXIES = _parse_trusted_proxies(
        os.environ.get("AIMARKET_TRUSTED_PROXIES", "")
    )
    if not _TRUSTED_PROXIES and _is_production_mode():
        logger.warning(
            "AIMARKET_TRUSTED_PROXIES not set — per-IP rate limits key on the immediate "
            "peer. Behind a reverse proxy that is the PROXY's address, so every caller "
            "shares one bucket; set it to the proxy address(es) (e.g. 127.0.0.1)."
        )

    def _mcp_caller(request: Any) -> str:
        return _client_address(request, _TRUSTED_PROXIES)

    # Rate limits.
    rate_limits_scope = _rate_limits_routes.register(
    )
    _INVOKE_RATE_WORKERS = rate_limits_scope._INVOKE_RATE_WORKERS
    _check_invoke_rate = rate_limits_scope._check_invoke_rate
    _signup_allowed = rate_limits_scope._signup_allowed

    # Attach plugin registry to app state
    app.state.plugins = plugins

    # Federated slash registry (F2 transport): this hub's signed slash log + ingested peers.
    # DB-backed so the authored log (and its monotonic seq) survives restarts.
    from aimarket_hub.slash_sync import SlashRegistry

    slash_registry = SlashRegistry(config.hub_url, db=db)
    lifespan_late.slash_registry = slash_registry
    app.state.slash_registry = slash_registry

    from aimarket_hub.oracle_quorum import RulingQuorum
    from aimarket_hub.reputation_oracle import ReputationOracle

    reputation_oracle = ReputationOracle(
        signer=signer,
        hub_url=config.hub_url,
        slash_registry=slash_registry,
        quorum=RulingQuorum.from_env(),
    )
    app.state.reputation_oracle = reputation_oracle

    from aimarket_hub.supply_security import SupplySecurity, TrustOracleUnavailable

    supply_security = SupplySecurity(
        db, config, signer=signer, slash_registry=slash_registry,
    )
    app.state.supply_security = supply_security
    from aimarket_hub.supply_chain_admission import SupplyChainAdmission

    supply_chain_admission = SupplyChainAdmission(db)
    app.state.supply_chain_admission = supply_chain_admission
    # Verify-first: repeat Metis verdict failures escalate to a calibrated slash.
    verify_svc.attach_supply_security(supply_security)
    app.state.verify_svc = verify_svc  # exposed so the escalation wiring is testable

    router = APIRouter(prefix="/ai-market/v2", tags=["hub-v2"])
    wellknown_router = APIRouter(tags=["wellknown"])
    # Names a route reads at request time but create_app binds further down (the
    # federation helpers, the pipeline provider). Route groups are registered in route
    # order, so these reach them through here instead of as register() arguments.
    late = SimpleNamespace()

    # Discovery: /.well-known/*, bazaar resources, protocol schemas.
    _wellknown_routes.register(
        _AGENT_TOKENS=_AGENT_TOKENS,
        config=config,
        db=db,
        hub_deposits=hub_deposits,
        late=late,
        plugins=plugins,
        signer=signer,
        wellknown_router=wellknown_router,
    )

    # Catalogue: signed manifest, prices, search.
    catalog_scope = _catalog_routes.register(
        _pays_a_third_party=_pays_a_third_party,
        config=config,
        db=db,
        router=router,
        signer=signer,
        supply_security=supply_security,
    )
    search = catalog_scope.search

    # Supply: stake policy, staking, registration, self-bonds.
    _supply_routes.register(
        _NS_AGENT=_NS_AGENT,
        _credits_publisher=_credits_publisher,
        _require_admin=_require_admin,
        _require_stake_subject=_require_stake_subject,
        _require_subject_credential=_require_subject_credential,
        config=config,
        db=db,
        hub_credits=hub_credits,
        hub_mandates=hub_mandates,
        router=router,
        supply_chain_admission=supply_chain_admission,
        supply_security=supply_security,
    )

    # Trial quota, verification and appeals, receipts, lottery entitlement.
    _verification_routes.register(
        _ADMIN_TOKEN=_ADMIN_TOKEN,
        _AGENT_TOKENS=_AGENT_TOKENS,
        _NS_AGENT=_NS_AGENT,
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _check_invoke_rate=_check_invoke_rate,
        _require_subject_credential=_require_subject_credential,
        config=config,
        router=router,
        signer=signer,
        verify_svc=verify_svc,
    )

    # Mandates and subcontract job trees.
    mandates_scope = _mandates_routes.register(
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _check_invoke_rate=_check_invoke_rate,
        _is_admin_bearer=_is_admin_bearer,
        hub_credits=hub_credits,
        hub_jobs=hub_jobs,
        hub_mandates=hub_mandates,
        router=router,
    )
    _api_key_account = mandates_scope._api_key_account

    # POST /invoke.
    _invoke_routes.register(
        TrustOracleUnavailable=TrustOracleUnavailable,
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _bind_hub_fee_payee=_bind_hub_fee_payee,
        _bind_listing_payee=_bind_listing_payee,
        _check_invoke_rate=_check_invoke_rate,
        _credit_hearth_owner=_credit_hearth_owner,
        _ecosystem_policy=_ecosystem_policy,
        _mcp_caller=_mcp_caller,
        _pay_publisher_share=_pay_publisher_share,
        _payment_hint=_payment_hint,
        _payment_ways=_payment_ways,
        _pays_a_third_party=_pays_a_third_party,
        _release_market_payment=_release_market_payment,
        _resolve_invoke_consumer_hub=_resolve_invoke_consumer_hub,
        _settle_market_payment=_settle_market_payment,
        _unbind_payee=_unbind_payee,
        builtin_safety=builtin_safety,
        config=config,
        db=db,
        hub_credits=hub_credits,
        hub_jobs=hub_jobs,
        hub_mandates=hub_mandates,
        late=late,
        plugins=plugins,
        router=router,
        signer=signer,
        supply_security=supply_security,
        verify_svc=verify_svc,
    )

    # Federation: knock, peers, assay, crawl, admission.
    federation_scope = _federation_routes.register(
        _is_admin_bearer=_is_admin_bearer,
        _require_admin=_require_admin,
        config=config,
        db=db,
        late=late,
        router=router,
        signer=signer,
        slash_registry=slash_registry,
        trust_scorer=trust_scorer,
    )
    _publishable_pending_peers = federation_scope._publishable_pending_peers

    # Reputation: slashes, events, deliveries, disputes.
    _reputation_routes.register(
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _require_admin=_require_admin,
        config=config,
        db=db,
        reputation_oracle=reputation_oracle,
        router=router,
        signer=signer,
        slash_registry=slash_registry,
        supply_security=supply_security,
        trust_scorer=trust_scorer,
    )

    # Health, credit accounts, top-ups, payer wallets, deposits.
    accounts_scope = _accounts_routes.register(
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _is_admin_bearer=_is_admin_bearer,
        _require_admin=_require_admin,
        _signup_allowed=_signup_allowed,
        config=config,
        db=db,
        hub_credits=hub_credits,
        hub_deposits=hub_deposits,
        hub_settle=hub_settle,
        hub_topups=hub_topups,
        router=router,
        signer=signer,
    )
    _deposit_watcher = accounts_scope._deposit_watcher
    lifespan_late.deposit_watcher = _deposit_watcher

    # Live stats, permission violations, supply audits.
    _market_stats_routes.register(
        _NS_AGENT=_NS_AGENT,
        _NS_PUBLISHER=_NS_PUBLISHER,
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _ecosystem_policy=_ecosystem_policy,
        _require_subject_credential=_require_subject_credential,
        config=config,
        db=db,
        hub_credits=hub_credits,
        hub_x402=hub_x402,
        router=router,
        supply_chain_admission=supply_chain_admission,
        supply_security=supply_security,
    )

    # ACEX capital: pricing, IPO, audits.
    capital_scope = _capital_routes.register(
        _require_admin=_require_admin,
        db=db,
        router=router,
    )
    capital_alias = capital_scope.capital_alias

    # Payment channels and the escrow bridge.
    _channels_routes.register(
        _INVOKE_RATE_WORKERS=_INVOKE_RATE_WORKERS,
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _require_admin=_require_admin,
        config=config,
        router=router,
    )

    # Plugins.
    _plugins_routes.register(
        config=config,
        plugins=plugins,
        router=router,
    )

    # Agent doors: MCP and A2A.
    _agents_routes.register(
        _api_key_account=_api_key_account,
        _check_invoke_rate=_check_invoke_rate,
        _mcp_caller=_mcp_caller,
        app=app,
        config=config,
        db=db,
        hub_invoices=hub_invoices,
        hub_mandates=hub_mandates,
        search=search,
        wellknown_router=wellknown_router,
    )
    app.include_router(wellknown_router)
    app.include_router(router)
    app.include_router(capital_alias)

    # Pages, studio, seller operations, pipeline provider.
    _pages_routes.register(
        _TRUSTED_PROXIES=_TRUSTED_PROXIES,
        _check_invoke_rate=_check_invoke_rate,
        _ecosystem_policy=_ecosystem_policy,
        _mcp_caller=_mcp_caller,
        _publishable_pending_peers=_publishable_pending_peers,
        app=app,
        config=config,
        db=db,
        hub_jobs=hub_jobs,
        late=late,
        signer=signer,
    )

    return app
