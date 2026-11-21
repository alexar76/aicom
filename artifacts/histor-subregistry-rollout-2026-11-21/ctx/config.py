"""Operator configuration. Secrets stay in env; nothing is baked into the image."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}, got {value}")
    return value


# Sandbox hosts: the first is HISTOR_SANDBOX_URL, then HISTOR_SANDBOX_2_* … _8_*. A host's own
# capacity is its HISTOR_SANDBOX_SLOTS (a 4-core machine runs 2-4); more than 8 per host is never useful.
SANDBOX_HOSTS = 8
SANDBOX_SLOTS_PER_HOST = 8


def _sandbox_extra() -> tuple[tuple[str, str, str, int], ...]:
    """HISTOR_SANDBOX_2_* … _8_*. A half-configured host, a host past the eighth, a host listed twice
    or extra hosts without the first one stop the start: a silently dropped host would look like
    a slow crawl, not like a typo."""
    get = lambda name: os.environ.get(name, "").strip()  # noqa: E731
    beyond = sorted(k for k in os.environ if (m := re.fullmatch(r"HISTOR_SANDBOX_(\d+)_URL", k))
                    and not 2 <= int(m.group(1)) <= SANDBOX_HOSTS and get(k))
    if beyond:
        raise RuntimeError(f"at most {SANDBOX_HOSTS} sandbox hosts (HISTOR_SANDBOX_URL, then _2_ … "
                           f"_{SANDBOX_HOSTS}_); remove {', '.join(beyond)}")
    out = []
    for n in range(2, SANDBOX_HOSTS + 1):
        url, token, pin = (get(f"HISTOR_SANDBOX_{n}_{k}") for k in ("URL", "TOKEN", "CERT_SHA256"))
        if not (url or token or pin):
            continue
        if not (url and token and pin):
            raise RuntimeError(f"HISTOR_SANDBOX_{n}_URL, _TOKEN and _CERT_SHA256 go together")
        out.append((url.rstrip("/"), token, pin,
                    min(_int(f"HISTOR_SANDBOX_{n}_CONCURRENCY", 2, minimum=1), SANDBOX_SLOTS_PER_HOST)))
    if out and not (get("HISTOR_SANDBOX_URL") and get("HISTOR_SANDBOX_TOKEN") and get("HISTOR_SANDBOX_CERT_SHA256")):
        raise RuntimeError("HISTOR_SANDBOX_2_* and later need the first host (HISTOR_SANDBOX_URL, _TOKEN, _CERT_SHA256)")
    urls = [get("HISTOR_SANDBOX_URL").rstrip("/")] + [u for u, *_ in out]
    if len(set(urls)) != len(urls):
        raise RuntimeError("a sandbox host is listed twice: each HISTOR_SANDBOX_*_URL must be a different host")
    return tuple(out)


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    public_base: str
    data_dir: Path
    database_url: str
    profile: str
    operator_token: str = field(repr=False)
    registry_url: str
    crawl_interval_s: int
    crawl_on_start: bool
    crawl_workers: int
    crawl_per_host: int
    crawl_timeout_s: int
    crawl_limit: int
    crawl_batch: int
    opt_out: str
    scanner_dir: Path
    node_bin: str
    landing_dir: Path
    pqc: bool
    trusted_proxies: tuple[str, ...]
    check_rate_per_min: int
    check_scan_rate_per_hour: int
    allow_private_targets: bool
    classifier_model: str
    classifier_api_key: str = field(repr=False)
    classifier_base_url: str
    classifier_timeout_s: int
    classifier_max_per_crawl: int
    classifier_max_tools: int
    # did:key issuers whose receipt anchors the receipts log accepts (histor.receipts). Empty =
    # the log is closed to submissions, which is the default: an open log is a free write.
    receipt_issuers: tuple[str, ...] = ()
    # The package sandbox (histor.packages, histor/sandbox/): HTTPS to the observer on the sandbox
    # host, pinned to its certificate. Off unless the URL, the token and the pin are all set.
    sandbox_url: str = ""
    sandbox_token: str = field(default="", repr=False)
    sandbox_cert_sha256: str = ""
    sandbox_max_per_crawl: int = 300
    # Observations in flight at once; match HISTOR_SANDBOX_SLOTS on the sandbox host.
    sandbox_concurrency: int = 2
    # Current sandbox generation (histor/sandbox/histor_observe.py VERSION): 5 adds modern MCP
    # discovery with legacy fallback. Failed older observations may now be readable and retry.
    sandbox_observer: str = "5"
    # Preserve dated, complete successful observations from older supported readers. Their
    # failures retry under the current observer; this is not a blanket re-observation campaign.
    sandbox_observers_valid: tuple[str, ...] = ("3", "4")
    # Seconds HISTOR waits for one observation: a free slot, install (360 s), install scripts
    # (120 s), start and calls (150 s).
    sandbox_timeout_s: int = 720
    # More sandbox hosts (HISTOR_SANDBOX_2_URL/_TOKEN/_CERT_SHA256/_CONCURRENCY, up to _8_): each is
    # (url, token, pin, concurrency 1..8). The crawl hands a package to whichever host has a free slot.
    sandbox_extra: tuple[tuple[str, str, str, int], ...] = field(default=(), repr=False)
    # Observations in flight across all hosts. Each holds a crawl thread (HISTOR_CRAWL_WORKERS, 12) for
    # up to sandbox_timeout_s and may buffer a 32 MiB answer in HISTOR's 768 MB container.
    sandbox_max_slots: int = 12
    # Seconds between reads of the declaration files publishers point at from their registry entry
    # (histor.declared); the crawl reads them too. 0 = only at the crawl.
    declaration_refresh_s: int = 3600
    # The subregistry (histor.subregistry): registry entries served in the MCP registry's v0.1 API with
    # what HISTOR observed. Off unless HISTOR_SUBREGISTRY=1. It reads HISTOR_SUBREGISTRY_UPSTREAM (default:
    # the registry the crawl reads) every HISTOR_SUBREGISTRY_SYNC_S seconds (0 = only by hand) and walks
    # every server again each HISTOR_SUBREGISTRY_FULL_S. HISTOR_SUBREGISTRY_ALLOW is a file of server names
    # or namespace/* lines: the copy then holds those servers only.
    subregistry: bool = False
    subregistry_sync_s: int = 3600
    subregistry_full_s: int = 604800
    subregistry_upstream: str = ""
    subregistry_allow_path: Path | None = None
    # histor-tlog/2 (histor.checkpoint): the log's checkpoint origin — a schema-less URL that
    # never changes once published (HISTOR_LOG_ORIGIN; default: the public host + "/log") — and
    # this instance's witness name (HISTOR_WITNESS_NAME; default: the public host + "/witness").
    # The witness co-signs only logs listed in HISTOR_WITNESS_LOGS, a JSON file of
    # [{"origin": ..., "vkey": ...}]; unset = it knows no log and answers 404 to every origin.
    log_origin: str = ""
    witness_name: str = ""
    witness_logs: str = ""
    # Pages the deployment serves beside the app that sitemap-site.xml should name too, e.g.
    # /datasets/ (nginx, from deploy/export_dataset.sh). Paths only, comma-separated.
    sitemap_extra: tuple[str, ...] = ()
    # After a successful cycle, at least this long before the next one starts. A cycle that outlasts the interval would
    # otherwise start the next at once, and the monthly snapshot (deploy/export_dataset.sh) never finds a moment
    # between two cycles to take a coherent copy.
    crawl_min_gap_s: int = 1800
    remote_interval_s: int = 21600
    remote_changed_interval_s: int = 1800
    remote_change_window_s: int = 604800
    # HISTOR Watch for teams (histor.watch_paid): push delivery sold by card through Stripe
    # Checkout. Closed unless both Stripe values are set; a test key opens only outside the prod
    # profile and a live key only in it.
    stripe_secret_key: str = field(default="", repr=False)
    stripe_webhook_secret: str = field(default="", repr=False)
    watch_price_cents: int = 2900
    watch_days: int = 30
    # Demo mode (HISTOR_WATCH_DEMO=1): the plan, the price and the page are shown, and checkout is
    # closed whatever keys are set — the way the desks run while sales are not open.
    watch_demo: bool = False
    # Publisher-signed revision indexes (histor.signed_revisions): ``server=https://…/index.json``
    # pairs, separated by ``;``. Empty = the pilot default (alexar76/histor). ``-`` = none.
    revision_sources: tuple[tuple[str, str], ...] = ()

    @property
    def sandbox_enabled(self) -> bool:
        return bool(self.sandbox_url and self.sandbox_token and self.sandbox_cert_sha256)

    @property
    def classifier_enabled(self) -> bool:
        # Off unless a model, a key and a per-crawl budget are all set — a paid API is never
        # called by accident, and a misconfigured instance runs exactly as it did before.
        return bool(self.classifier_model and self.classifier_api_key and self.classifier_max_per_crawl > 0)

    @property
    def is_prod(self) -> bool:
        return self.profile == "prod"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "histor.sqlite3"

    @property
    def issuer_key_path(self) -> Path:
        return self.data_dir / "issuer.key"

    @property
    def opt_out_path(self) -> Path:
        return self.data_dir / "opt-out.txt"

    @property
    def head_marker_path(self) -> Path:
        return self.data_dir / "sth-marker.json"

    @property
    def witness_key_path(self) -> Path:
        # A key of its own: the cosignature message is not bound to the cosigner name, and the
        # specification tells an operator of several Ed25519 cosigners to use distinct keys.
        return self.data_dir / "witness.key"

    @property
    def public_host(self) -> str:
        return self.public_base.split("://", 1)[-1].rstrip("/")

    @property
    def checkpoint_origin(self) -> str:
        return self.log_origin or f"{self.public_host}/log"

    @property
    def cosigner_name(self) -> str:
        return self.witness_name or f"{self.public_host}/witness"

    @property
    def provider_key_path(self) -> Path:
        return self.data_dir / "provider.key"


def load_settings() -> Settings:
    profile = os.environ.get("HISTOR_PROFILE", "dev").strip().lower() or "dev"
    if profile not in {"dev", "prod"}:
        raise RuntimeError(f"HISTOR_PROFILE must be dev or prod, got {profile!r}")
    public_base = os.environ.get("HISTOR_PUBLIC_BASE", "http://127.0.0.1:9490").strip().rstrip("/")
    settings = Settings(
        host=os.environ.get("HISTOR_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int("HISTOR_PORT", 9490, minimum=1),
        public_base=public_base,
        data_dir=Path(os.environ.get("HISTOR_DATA_DIR", "./data")).expanduser(),
        database_url=os.environ.get("HISTOR_DATABASE_URL", "").strip(),
        profile=profile,
        operator_token=os.environ.get("HISTOR_OPERATOR_TOKEN", "").strip(),
        registry_url=os.environ.get("HISTOR_REGISTRY_URL", "https://registry.modelcontextprotocol.io").strip().rstrip("/"),
        crawl_interval_s=_int("HISTOR_CRAWL_INTERVAL_S", 86400, minimum=0),
        crawl_min_gap_s=_int("HISTOR_CRAWL_MIN_GAP_S", 1800, minimum=0),
        remote_interval_s=_int("HISTOR_REMOTE_INTERVAL_S", 21600),
        remote_changed_interval_s=_int("HISTOR_REMOTE_CHANGED_INTERVAL_S", 1800, minimum=60),
        remote_change_window_s=_int("HISTOR_REMOTE_CHANGE_WINDOW_S", 604800, minimum=60),
        crawl_on_start=_truthy("HISTOR_CRAWL_ON_START", "1"),
        crawl_workers=_int("HISTOR_CRAWL_WORKERS", 12, minimum=1),
        crawl_per_host=_int("HISTOR_CRAWL_PER_HOST", 2, minimum=1),
        crawl_timeout_s=_int("HISTOR_CRAWL_TIMEOUT_S", 20, minimum=1),
        crawl_limit=_int("HISTOR_CRAWL_LIMIT", 0, minimum=0),
        crawl_batch=_int("HISTOR_CRAWL_BATCH", 400, minimum=1),
        opt_out=os.environ.get("HISTOR_OPT_OUT", ""),
        scanner_dir=Path(os.environ.get("HISTOR_SCANNER_DIR", str(PACKAGE_ROOT / "scanner"))),
        node_bin=os.environ.get("HISTOR_NODE_BIN", "node").strip() or "node",
        landing_dir=Path(os.environ.get("HISTOR_LANDING_DIR", str(PACKAGE_ROOT / "docs" / "landing"))),
        pqc=_truthy("HISTOR_PQC", "0"),
        trusted_proxies=tuple(
            p.strip() for p in os.environ.get("HISTOR_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if p.strip()
        ),
        check_rate_per_min=_int("HISTOR_CHECK_RATE_PER_MIN", 30, minimum=1),
        check_scan_rate_per_hour=_int("HISTOR_CHECK_SCAN_RATE_PER_HOUR", 20, minimum=0),
        allow_private_targets=_truthy("HISTOR_ALLOW_PRIVATE_TARGETS", "0"),
        # Optional meaning-based classifier (OpenRouter). Off by default; a Chinese model reads
        # the tool text in any language and says whether it instructs the model or exfiltrates.
        classifier_model=os.environ.get("HISTOR_CLASSIFIER_MODEL", "").strip(),
        # Provider-agnostic (all are OpenAI-compatible /chat/completions): DeepSeek's own key, an
        # OpenRouter key, or a generic one, whichever is set. The base URL picks the provider.
        classifier_api_key=(
            os.environ.get("HISTOR_CLASSIFIER_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("HISTOR_OPENROUTER_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        ).strip(),
        classifier_base_url=os.environ.get("HISTOR_CLASSIFIER_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        classifier_timeout_s=_int("HISTOR_CLASSIFIER_TIMEOUT_S", 30, minimum=1),
        classifier_max_per_crawl=_int("HISTOR_CLASSIFIER_MAX_PER_CRAWL", 0, minimum=0),
        classifier_max_tools=_int("HISTOR_CLASSIFIER_MAX_TOOLS", 60, minimum=1),
        receipt_issuers=tuple(
            d.strip() for d in os.environ.get("HISTOR_RECEIPT_ISSUERS", "").split(",") if d.strip()
        ),
        sandbox_url=os.environ.get("HISTOR_SANDBOX_URL", "").strip().rstrip("/"),
        sandbox_token=os.environ.get("HISTOR_SANDBOX_TOKEN", "").strip(),
        sandbox_cert_sha256=os.environ.get("HISTOR_SANDBOX_CERT_SHA256", "").strip(),
        sandbox_max_per_crawl=_int("HISTOR_SANDBOX_MAX_PER_CRAWL", 300, minimum=0),
        sandbox_concurrency=min(_int("HISTOR_SANDBOX_CONCURRENCY", 2, minimum=1), SANDBOX_SLOTS_PER_HOST),
        sandbox_max_slots=min(_int("HISTOR_SANDBOX_MAX_SLOTS", 12, minimum=1), 32),
        sandbox_observer=os.environ.get("HISTOR_SANDBOX_OBSERVER", "5").strip(),
        sandbox_observers_valid=tuple(v.strip() for v in os.environ.get("HISTOR_SANDBOX_OBSERVERS_VALID", "3,4").split(",") if v.strip()),
        sandbox_timeout_s=_int("HISTOR_SANDBOX_TIMEOUT_S", 720, minimum=30),
        sandbox_extra=_sandbox_extra(),
        declaration_refresh_s=_int("HISTOR_DECLARATION_REFRESH_S", 3600, minimum=0),
        subregistry=_truthy("HISTOR_SUBREGISTRY", "0"),
        subregistry_sync_s=_int("HISTOR_SUBREGISTRY_SYNC_S", 3600, minimum=0),
        subregistry_full_s=_int("HISTOR_SUBREGISTRY_FULL_S", 604800, minimum=0),
        subregistry_upstream=os.environ.get("HISTOR_SUBREGISTRY_UPSTREAM", "").strip().rstrip("/"),
        subregistry_allow_path=Path(os.environ["HISTOR_SUBREGISTRY_ALLOW"].strip()) if os.environ.get("HISTOR_SUBREGISTRY_ALLOW", "").strip() else None,
        log_origin=os.environ.get("HISTOR_LOG_ORIGIN", "").strip(),
        witness_name=os.environ.get("HISTOR_WITNESS_NAME", "").strip(),
        witness_logs=os.environ.get("HISTOR_WITNESS_LOGS", "").strip(),
        sitemap_extra=tuple(
            p.strip() for p in os.environ.get("HISTOR_SITEMAP_EXTRA", "").split(",") if p.strip().startswith("/")
        ),
        stripe_secret_key=os.environ.get("HISTOR_STRIPE_SECRET_KEY", "").strip(),
        stripe_webhook_secret=os.environ.get("HISTOR_STRIPE_WEBHOOK_SECRET", "").strip(),
        watch_price_cents=_int("HISTOR_WATCH_PRICE_CENTS", 2900, minimum=100),
        watch_days=_int("HISTOR_WATCH_DAYS", 30, minimum=1),
        watch_demo=_truthy("HISTOR_WATCH_DEMO", "0"),
        revision_sources=_revision_sources(),
    )
    if settings.is_prod:
        # Fail closed: a production instance with a guessable admin surface, a cleartext public
        # base or a crawler allowed onto private addresses is worse than one that does not start.
        if len(settings.operator_token) < 24:
            raise RuntimeError("HISTOR_PROFILE=prod needs HISTOR_OPERATOR_TOKEN of at least 24 characters")
        if not settings.public_base.startswith("https://"):
            raise RuntimeError("HISTOR_PROFILE=prod needs an https HISTOR_PUBLIC_BASE")
        if not settings.database_url.startswith(("postgresql://", "postgres://")):
            # SQLite is the development store. The production log publishes signed tree heads,
            # and a tree head over a file one volume mistake can replace is a promise we cannot keep.
            raise RuntimeError("HISTOR_PROFILE=prod needs a postgresql:// HISTOR_DATABASE_URL")
        if settings.allow_private_targets:
            raise RuntimeError("HISTOR_ALLOW_PRIVATE_TARGETS is refused under HISTOR_PROFILE=prod")
        if settings.subregistry and not (settings.subregistry_upstream or settings.registry_url).startswith("https://"):
            raise RuntimeError("HISTOR_SUBREGISTRY under HISTOR_PROFILE=prod needs an https upstream registry")
    return settings


def _revision_sources() -> tuple[tuple[str, str], ...]:
    from histor.signed_revisions import parse_sources

    return parse_sources(os.environ.get("HISTOR_REVISION_SOURCES"))
