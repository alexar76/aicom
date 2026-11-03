"""Widget sandbox trials — free invoke quota per visitor (escrow-free preview).

Used by embed widgets and demos: visitors get N complimentary invocations without
opening a payment channel. Production invocations still debit channels normally.

Env:
  AIMARKET_SANDBOX_ENABLED — "0" disables sandbox (default: enabled)
  AIMARKET_SANDBOX_MAX_PER_VISITOR — trials per visitor id (default 3)
  AIMARKET_SANDBOX_QUOTA_WINDOW — "lifetime" (default) or "daily"/"hourly"/"weekly".
      lifetime is the revenue setting: three invokes ever, then pay. A repeating window
      is the engagement setting: the allowance comes back, so a returning agent keeps
      using the hub between purchases. Switch it without touching the ledger — counters
      are keyed by window, so changing the value starts a fresh period rather than
      forgiving or double-charging what was already spent.
  AIMARKET_SANDBOX_MAX_PER_IP_HOUR — rate cap per client IP (default 30)
  AIMARKET_SANDBOX_STUB_INVOKE — "1" returns deterministic demo output when factory is down

Runtime overrides: the same three dials can be set in ``data/sandbox_trial_policy.json``
so the free tier can be retuned without recreating the container. A dial you can only
turn by redeploying is not much of a dial, and this one is a revenue/engagement setting
someone will want to move while watching traffic. Environment always wins over the file,
so an explicit ops decision cannot be overridden by a stray config.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_ENABLED = os.getenv("AIMARKET_SANDBOX_ENABLED", "1").strip().lower() not in ("0", "false", "no")
_MAX_PER_VISITOR = int(os.getenv("AIMARKET_SANDBOX_MAX_PER_VISITOR", "3"))
_MAX_PER_IP_HOUR = int(os.getenv("AIMARKET_SANDBOX_MAX_PER_IP_HOUR", "30"))
_QUOTA_WINDOW = (os.getenv("AIMARKET_SANDBOX_QUOTA_WINDOW", "lifetime").strip().lower() or "lifetime")


def _runtime_policy() -> dict[str, Any]:
    """Operator overrides from disk, re-read at most every few seconds."""
    global _policy_cache
    now = time.time()
    cached_at, cached = _policy_cache
    if now - cached_at < _POLICY_TTL_S:
        return cached
    data: dict[str, Any] = {}
    try:
        raw = Path(_POLICY_PATH).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, ValueError):
        data = {}
    _policy_cache = (now, data)
    return data


def _int_setting(env_name: str, env_value: int, key: str, floor: int = 1) -> int:
    # An explicitly set environment variable is an ops decision and wins.
    if os.getenv(env_name) is not None:
        return env_value
    raw = _runtime_policy().get(key)
    try:
        return max(floor, int(raw))
    except (TypeError, ValueError):
        return env_value


def max_per_visitor() -> int:
    return _int_setting("AIMARKET_SANDBOX_MAX_PER_VISITOR", _MAX_PER_VISITOR, "max_per_visitor")


def max_per_ip_hour() -> int:
    return _int_setting("AIMARKET_SANDBOX_MAX_PER_IP_HOUR", _MAX_PER_IP_HOUR, "max_per_ip_hour")

# How the allowance repeats. "lifetime" keeps the original behaviour exactly.
_WINDOW_FORMATS = {
    "lifetime": "",
    "hourly": "%Y-%m-%dT%H",
    "daily": "%Y-%m-%d",
    "weekly": "%G-W%V",
}


def quota_window() -> str:
    """The configured window, falling back to lifetime for an unknown value.

    An unrecognised setting must not silently grant an unlimited allowance, so the
    safe direction is the strictest one.
    """
    if os.getenv("AIMARKET_SANDBOX_QUOTA_WINDOW") is not None:
        candidate = _QUOTA_WINDOW
    else:
        candidate = str(_runtime_policy().get("quota_window") or _QUOTA_WINDOW).strip().lower()
    return candidate if candidate in _WINDOW_FORMATS else "lifetime"


def current_window_key(now: float | None = None) -> str:
    """Ledger key for the period a visitor's allowance belongs to."""
    fmt = _WINDOW_FORMATS.get(quota_window(), "")
    if not fmt:
        return ""
    return time.strftime(fmt, time.gmtime(now if now is not None else time.time()))
_DB_PATH = os.getenv("AIMARKET_SANDBOX_DB_PATH", "data/sandbox_trials.db")
_POLICY_PATH = os.getenv(
    "AIMARKET_SANDBOX_POLICY_PATH",
    str(Path(_DB_PATH).parent / "sandbox_trial_policy.json"),
)
_POLICY_TTL_S = 15.0
_policy_cache: tuple[float, dict[str, Any]] = (0.0, {})
def sandbox_stub_invoke_enabled() -> bool:
    return os.getenv("AIMARKET_SANDBOX_STUB_INVOKE", "0").strip().lower() in ("1", "true", "yes")


def sandbox_enabled() -> bool:
    return _ENABLED


# Capabilities whose handler spends real model budget downstream. The free tier's entire
# justification is that the servers run regardless, so a stranger's call costs noise — and
# that is simply FALSE here: every call composes an answer with a paid model.
#
# Found live on production. `platon.ask@v1` ($0.003), `platon.oracle@v1` ($0.02, "LLM
# mathematical witness") and `platon.steer@v1` ($0.005, natural language to parameters) were
# all reachable on the free tier through hub federation, and a direct call returned a genuinely
# composed answer — order parameter, Lyapunov exponent, prose reasoning — so the tokens were
# real. Worse than merely free: the visitor id is self-chosen, so the per-caller allowance is
# bypassable by rotating it, which makes the exposure unbounded rather than five calls an hour.
#
# Discovery is unaffected: the capability stays in the manifest with its price, and the refusal
# says why and what to do. What changes is that someone else's model bill is no longer the
# free sample.
_MODEL_BACKED_DEFAULT = (
    "platon.ask@v1",
    "platon.oracle@v1",
    "platon.steer@v1",
)


def model_backed_capabilities() -> frozenset[str]:
    """Capability ids excluded from the free tier because each call costs model budget.

    ``AIMARKET_SANDBOX_MODEL_BACKED`` (comma-separated) replaces the default list, and
    ``model_backed_capabilities`` in the policy file does the same without a redeploy — a new
    LLM-backed SKU appears on a peer, not here, so this must be changeable from the outside.
    """
    raw = os.getenv("AIMARKET_SANDBOX_MODEL_BACKED")
    if raw is None:
        from_policy = _runtime_policy().get("model_backed_capabilities")
        if isinstance(from_policy, (list, tuple)):
            return frozenset(str(c).strip() for c in from_policy if str(c).strip())
        if isinstance(from_policy, str):
            raw = from_policy
    if raw is None:
        return frozenset(_MODEL_BACKED_DEFAULT)
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def free_tier_covers(capability_id: str) -> bool:
    return str(capability_id or "").strip() not in model_backed_capabilities()


def model_budget_refusal(capability_id: str) -> dict[str, Any]:
    """Why this one is not free, and how to use it anyway.

    The wording says "real budget", not "a paid model", because the list is not only about
    models. It was when it held three Platon capabilities; then ATLAS's `situation.brief`
    joined it — a multi-layer sensor brief that fans out to metered upstreams and takes ten
    seconds a call, with no model anywhere in it. Telling that buyer their call "composes its
    answer with a paid model" is a false explanation for a true refusal, and a buyer who
    checks would be right to distrust the rest of the message.

    The `error` CODE stays `model_budget_not_free`: agents branch on it, and renaming a
    published contract to improve prose is a bad trade.
    """
    return {
        "error": "model_budget_not_free",
        "capability_id": capability_id,
        "detail": (
            f"{capability_id} spends real budget on every call — a paid model, or metered "
            "upstream data — so it is not free to serve. The free tier covers capabilities "
            "whose marginal cost is noise; this is not one of them."
        ),
        "how_to_continue": [
            "Open a payment channel at the hub and invoke through it: "
            "https://modelmarket.dev/.well-known/ai-market.json",
            "Free alternatives with no model cost are listed in the manifest at "
            "price_per_call_usd and marked free_tier: true.",
        ],
    }


def trial_policy() -> dict[str, Any]:
    """The free-trial terms, for publication in `.well-known/ai-market.json`.

    The tier existed and worked but was advertised nowhere, so a discovering agent read
    `payment_configured: true` next to a price list and concluded it needed a funded
    wallet to evaluate anything. Naming the header and the allowance here is the
    difference between "found the hub" and "tried a capability".

    Deliberately omits the per-IP cap: that is an abuse control, and publishing it just
    tells an abuser the shape of the limit.
    """
    if not _ENABLED:
        return {"enabled": False}
    window = quota_window()
    return {
        "enabled": True,
        "max_invokes_per_visitor": max_per_visitor(),
        # A repeating allowance is worth advertising: it is the difference between
        # "evaluate once" and "keep using this between purchases".
        "quota_window": window,
        "renews": window != "lifetime",
        "visitor_header": "X-AIMarket-Sandbox-Visitor",
        # Published, because discovering this by being refused wastes a round trip and reads
        # as the tier being broken.
        "excluded_capabilities": sorted(model_backed_capabilities()),
        "excluded_reason": (
            "each call spends real budget — a paid model, or metered upstream data — "
            "so it is not free to serve"
        ),
        # The status code is stated because a discovering agent branches on it, and the
        # published text said 402 while the hub answers 429 trial_quota_exhausted — written
        # when the tier was lifetime, never corrected when it became a renewing window. An
        # agent that trusted the contract would treat a temporary refusal as "must pay",
        # abandon the free tier it still had, and never come back. 429 is the right code for
        # a limit that clears on its own, so the text moves to match the behaviour rather
        # than the reverse.
        "exhausted_status": 429 if window != "lifetime" else 402,
        "exhausted_error": "trial_quota_exhausted",
        "how": (
            "Send X-AIMarket-Sandbox-Visitor with a stable id you choose and no payment "
            "channel; the invoke runs for free and returns a signed receipt. Results are "
            "marked sandbox=true. A refused call costs nothing — the allowance is spent "
            "only when data is delivered. When it is spent the hub answers "
            + (
                "429 trial_quota_exhausted until the window renews."
                if window != "lifetime"
                else "402; open a payment channel to continue."
            )
        ),
        "clients": {
            "mcp": "pip install aimarket-mcp — market_search / market_invoke",
            "python": "pip install aimarket-agent — AIMarketAgent(..., sandbox_visitor=\"<id>\") "
                      "or AIMARKET_SANDBOX_VISITOR; CLI: --sandbox-visitor (2.6.1+)",
            "http": "POST /ai-market/v2/invoke with the visitor header and no payment channel",
        },
    }


def _require_durable_sqlite(named_path: str) -> None:
    """In production the trial ledger must survive a restart. Prove it, do not assume it.

    The free tier is an anti-abuse counter: a ledger that is wiped when the container is
    recreated hands every visitor a fresh allowance on each deploy, which is the same as
    having no limit. That is what the original rule was defending, and it defended it by
    demanding PostgreSQL.

    But "not PostgreSQL" is not the same as "not durable". modelmarket.dev runs entirely on
    SQLite with `/app/data` on a Docker volume, has no PostgreSQL to point at, and was
    therefore refused — not at boot, where an operator would see it, but inside the first
    free invoke, which answered 500 to the caller. Measured on production 2026-09-16: every
    sandbox-tier call to the apex hub failed that way, and because the ledger is built
    lazily the deploy that introduced it passed every check.

    What is actually required is that the operator has NAMED a durable location. An absolute
    `AIMARKET_SANDBOX_DB_PATH` is a decision; the relative default `data/sandbox_trials.db`
    is whatever the working directory happens to be, which is exactly the accident this
    should keep out of production.
    """
    named = (named_path or "").strip()
    if named and Path(named).is_absolute():
        return
    raise RuntimeError(
        "production sandbox trial ledger must be durable: set "
        "AIMARKET_SANDBOX_DATABASE_URL=postgresql://... (or DATABASE_URL), or "
        "AIMARKET_SANDBOX_DB_PATH=/absolute/path on a volume. A relative path resolves "
        "against the working directory and is lost when the container is recreated, which "
        "resets every visitor's free allowance."
    )


class SandboxTrialLedger:
    """Trial counters backed by SQLite locally or PostgreSQL in production.

    ``DATABASE_URL`` selects PostgreSQL through the same backend abstraction used by
    the Hub index and payment channels.  The public ``db_path`` argument remains for
    backward-compatible local/test SQLite databases.
    """

    def __init__(self, db_path: str = "", database_url: str = "") -> None:
        from aimarket_hub.db_backend import create_backend

        self._path = Path(db_path or _DB_PATH)
        # The per-service URL first, the shared one second — the order every other ledger
        # in this hub uses. Reading only DATABASE_URL meant a hub told to put its trial
        # counters in a particular database was judged on a variable it had not been given.
        configured_url = (
            database_url
            or os.getenv("AIMARKET_SANDBOX_DATABASE_URL", "")
            or os.getenv("DATABASE_URL", "")
        ).strip()
        if os.getenv("AIFACTORY_PROD", "").strip() == "1" and not configured_url.startswith(
            ("postgresql://", "postgres://")
        ):
            _require_durable_sqlite(db_path or os.getenv("AIMARKET_SANDBOX_DB_PATH", ""))
        self._backend = create_backend(database_url=configured_url, db_path=self._path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._backend.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS visitor_trials (
                    visitor_id TEXT PRIMARY KEY,
                    used INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ip_hits (
                    ip TEXT NOT NULL,
                    ts REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ip_hits_ts ON ip_hits(ts)")
            # Windowed counters live beside the lifetime table rather than replacing it:
            # an existing deployment keeps its spent allowances when the window changes,
            # and switching back to lifetime does not forgive them.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS visitor_trials_windowed (
                    visitor_id TEXT NOT NULL,
                    window_key TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (visitor_id, window_key)
                )
            """)
            conn.commit()

    def quota(self, visitor_id: str) -> dict[str, Any]:
        if not _ENABLED:
            return {"enabled": False, "max_trials": 0, "used": 0, "remaining": 0}
        vid = _normalize_visitor(visitor_id)
        used = self._get_used(vid)
        remaining = max(0, max_per_visitor() - used)
        return {
            "enabled": True,
            "max_trials": max_per_visitor(),
            "used": used,
            "remaining": remaining,
            "visitor_id": vid,
            "quota_window": quota_window(),
        }

    def consume(self, visitor_id: str, client_ip: str = "") -> dict[str, Any]:
        """Reserve one trial. Returns ok/error dict."""
        if not _ENABLED:
            return {"error": "sandbox_disabled", "enabled": False}

        vid = _normalize_visitor(visitor_id)
        if not vid:
            # "missing" only when it really is. A present-but-rejected id (`keys-3` is six
            # characters) reported missing_visitor_id, sending the caller to look for a
            # header they had already sent — so say what the rule is instead.
            if (visitor_id or "").strip():
                return {
                    "error": "invalid_visitor_id",
                    "detail": (
                        "X-AIMarket-Sandbox-Visitor must be 8-64 characters of letters, "
                        "digits, '_' or '-'"
                    ),
                }
            return {"error": "missing_visitor_id"}

        if client_ip and not self._ip_within_limit(client_ip):
            return {"error": "rate_limit_exceeded", "detail": "too many sandbox tries from this network"}

        window = current_window_key()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        maximum = max_per_visitor()
        with self._lock, self._backend.get_connection() as conn:
            if window:
                # Ensure the counter exists, then let the database atomically claim one
                # allowance.  A SELECT followed by UPDATE is unsafe with multiple workers:
                # two requests can both observe used=N and both write N+1.
                conn.execute(
                    "INSERT INTO visitor_trials_windowed "
                    "(visitor_id, window_key, used, updated_at) VALUES (?, ?, 0, ?) "
                    "ON CONFLICT(visitor_id, window_key) DO NOTHING",
                    (vid, window, now),
                )
                row = conn.execute(
                    "UPDATE visitor_trials_windowed SET used = used + 1, updated_at = ? "
                    "WHERE visitor_id = ? AND window_key = ? AND used < ? RETURNING used",
                    (now, vid, window, maximum),
                ).fetchone()
            else:
                conn.execute(
                    "INSERT INTO visitor_trials (visitor_id, used, updated_at) "
                    "VALUES (?, 0, ?) ON CONFLICT(visitor_id) DO NOTHING",
                    (vid, now),
                )
                row = conn.execute(
                    "UPDATE visitor_trials SET used = used + 1, updated_at = ? "
                    "WHERE visitor_id = ? AND used < ? RETURNING used",
                    (now, vid, maximum),
                ).fetchone()
            if row is None:
                if window:
                    current = conn.execute(
                        "SELECT used FROM visitor_trials_windowed "
                        "WHERE visitor_id = ? AND window_key = ?",
                        (vid, window),
                    ).fetchone()
                else:
                    current = conn.execute(
                        "SELECT used FROM visitor_trials WHERE visitor_id = ?", (vid,)
                    ).fetchone()
                used = int(current[0]) if current else maximum
                conn.commit()
                return {
                    "error": "trial_quota_exhausted",
                    "used": used,
                    "max_trials": maximum,
                    "remaining": 0,
                }
            new_used = int(row[0])
            conn.commit()

        if client_ip:
            self._record_ip(client_ip)

        return {
            "ok": True,
            "used": new_used,
            "max_trials": maximum,
            "remaining": max(0, maximum - new_used),
            "visitor_id": vid,
        }

    def release(self, visitor_id: str) -> dict[str, Any]:
        """Hand back a trial for a call that never delivered anything.

        ``consume`` says "Reserve one trial" and there was nothing to reserve *against*: the
        debit landed at the door and stayed there through every downstream failure. The paid
        path in this hub takes a hold instead, explicitly so that "a peer that 402s, times
        out or returns garbage never costs the buyer anything" — and there are nine exits
        between the reservation and the response. The free tier deserves the same rule; it is
        the same promise in a different currency.

        Measured on production before this existed: five invokes with a wrong envelope, each
        answered with a clear "retry with source_hub=..." hint, spent 5/5 of a caller's
        allowance. The next call was refused. A stranger's first five minutes with the mesh
        ended in exhaustion without a single result.

        The per-network counter is deliberately **not** rolled back. It exists to bound load,
        and a refused call consumed real work; only the allowance — which is a promise about
        delivered value — is returned.
        """
        if not _ENABLED:
            return {"enabled": False}
        vid = _normalize_visitor(visitor_id)
        if not vid:
            return {"error": "invalid_visitor_id"}

        window = current_window_key()
        with self._lock, self._backend.get_connection() as conn:
            if window:
                row = conn.execute(
                    "UPDATE visitor_trials_windowed "
                    "SET used = CASE WHEN used > 0 THEN used - 1 ELSE 0 END, updated_at = ? "
                    "WHERE visitor_id = ? AND window_key = ? AND used > 0 RETURNING used",
                    (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), vid, window),
                ).fetchone()
            else:
                row = conn.execute(
                    "UPDATE visitor_trials "
                    "SET used = CASE WHEN used > 0 THEN used - 1 ELSE 0 END, updated_at = ? "
                    "WHERE visitor_id = ? AND used > 0 RETURNING used",
                    (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), vid),
                ).fetchone()
            if not row:
                # Nothing recorded — a release without a consume, or the window turned
                # underneath it. Either way there is nothing to give back, and inventing a
                # negative balance would hand out free calls next window.
                conn.commit()
                return {"ok": True, "used": 0, "released": False}
            new_used = int(row[0])
            conn.commit()

        return {
            "ok": True,
            "used": new_used,
            "released": True,
            "max_trials": max_per_visitor(),
            "remaining": max(0, max_per_visitor() - new_used),
            "visitor_id": vid,
        }

    def _get_used(self, visitor_id: str) -> int:
        window = current_window_key()
        with self._backend.get_connection() as conn:
            if window:
                row = conn.execute(
                    "SELECT used FROM visitor_trials_windowed WHERE visitor_id = ? AND window_key = ?",
                    (visitor_id, window),
                ).fetchone()
                return int(row[0]) if row else 0
            row = conn.execute(
                "SELECT used FROM visitor_trials WHERE visitor_id = ?", (visitor_id,)
            ).fetchone()
            return int(row[0]) if row else 0

    def _ip_within_limit(self, ip: str) -> bool:
        cutoff = time.time() - 3600
        with self._lock, self._backend.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM ip_hits WHERE ip = ? AND ts > ?", (ip, cutoff)
            ).fetchone()[0]
            return count < max_per_ip_hour()

    def _record_ip(self, ip: str) -> None:
        now = time.time()
        with self._lock, self._backend.get_connection() as conn:
            conn.execute("INSERT INTO ip_hits (ip, ts) VALUES (?, ?)", (ip, now))
            conn.execute("DELETE FROM ip_hits WHERE ts < ?", (now - 7200,))
            conn.commit()


_ledger: SandboxTrialLedger | None = None
_ledger_lock = threading.Lock()


def _get_ledger() -> SandboxTrialLedger:
    global _ledger
    if _ledger is None:
        with _ledger_lock:
            if _ledger is None:
                _ledger = SandboxTrialLedger()
    return _ledger


def ensure_trial_ledger() -> None:
    """Build the trial ledger now, so a bad configuration fails the DEPLOY, not a visitor.

    It is otherwise created on the first free invoke, which is how a hub that could not run
    its own free tier passed every startup check and then answered 500 to the first stranger
    who tried it — for a week, on the busiest hub in the federation, with nothing in any
    health endpoint to say so.
    """
    _get_ledger()


def sandbox_quota(visitor_id: str) -> dict[str, Any]:
    return _get_ledger().quota(visitor_id)


def consume_sandbox_trial(visitor_id: str, client_ip: str = "") -> dict[str, Any]:
    return _get_ledger().consume(visitor_id, client_ip=client_ip)


def release_sandbox_trial(visitor_id: str) -> dict[str, Any]:
    """Give back a trial the caller got nothing for. Pairs with ``consume_sandbox_trial``."""
    return _get_ledger().release(visitor_id)


def new_visitor_id() -> str:
    return f"vis_{uuid.uuid4().hex[:20]}"


def _normalize_visitor(visitor_id: str) -> str:
    vid = (visitor_id or "").strip()
    if len(vid) < 8 or len(vid) > 64:
        return ""
    if not all(c.isalnum() or c in "_-" for c in vid):
        return ""
    return vid


def sandbox_demo_result(capability_id: str, product_id: str, user_input: dict[str, Any]) -> dict[str, Any]:
    """Deterministic preview payload when factory is unavailable (CI / offline demos)."""
    text = ""
    if isinstance(user_input, dict):
        text = str(user_input.get("text") or user_input.get("message") or user_input.get("task") or "")[:200]
    return {
        "output": {
            "mode": "sandbox_preview",
            "capability_id": capability_id,
            "product_id": product_id,
            "echo": text or "(empty input)",
            "note": "Sandbox trial — connect AIFACTORY_PUBLIC_URL for live execution.",
        },
        "sandbox": True,
    }
