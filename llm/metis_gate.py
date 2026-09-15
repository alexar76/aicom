"""Optional Metis confidence-gate for the AI-Factory — auto-detecting & fail-open.

The factory can turn a high-stakes autonomous decision from *"trust one LLM
call"* into *"deliberate → verify → get a confidence score → proceed or flag"*
by routing the decision through a **Metis** deployment's ``POST /v1/verify``
endpoint and reading back its verification envelope.

Independence is a hard invariant of this module:

* **The factory never imports metis.** This module talks to Metis over plain
  HTTP (stdlib ``urllib`` only — zero third-party imports), so Metis need not be
  installed for the factory to run.
* **Auto-detect by default.** With ``AIFACTORY_METIS_GATE`` unset (or ``auto``),
  the gate probes Metis's ``/health`` once per TTL. If Metis answers, the gate
  uses it; if not, it falls through and the factory behaves exactly as it does
  with no gate at all. A missing Metis costs one fast, cached probe — not a
  timeout on every stage.
* **Fail-open, always.** Any connection error, timeout, non-200, or engine-side
  error yields a "proceed" verdict (``ok=True``). Metis being down, slow, or
  absent can never block or change the factory's behaviour, and never raises.

Only when Metis actually answers with ``needs_clarification`` (or a success
whose ``verify_score`` is below the threshold) does the gate report ``ok=False``
— an advisory signal the caller may log, annotate, or (opt-in) escalate.

Modes (``AIFACTORY_METIS_GATE``)
--------------------------------
* ``auto`` (default, or unset) — probe ``/health``; use Metis iff detected.
* ``on`` / ``1`` / ``true`` — always attempt Metis (still fail-open on error).
* ``off`` / ``0`` / ``false`` — never contact Metis (hard disable).

Environment
-----------
======================================  =======================================
``AIFACTORY_METIS_GATE``                ``auto`` (default) | ``on`` | ``off``
``AIFACTORY_METIS_GATE_BLOCK``          opt-in: let ``ok=False`` escalate (default off)
``AIFACTORY_METIS_URL`` / ``METIS_URL`` Metis base URL (default ``http://127.0.0.1:8080``)
``AIFACTORY_METIS_API_KEY`` / ``METIS_API_KEY``  optional bearer token
``AIFACTORY_METIS_GATE_TIMEOUT``        verify seconds (default ``30``)
``AIFACTORY_METIS_PROBE_TIMEOUT``       health-probe seconds (default ``2``)
``AIFACTORY_METIS_PROBE_TTL``           seconds to cache detection (default ``60``)
``AIFACTORY_METIS_GATE_MIN_SCORE``      verify threshold 0..1 (default ``0.7``)
``AIFACTORY_METIS_GATE_ROUTE``          fast|thinking|council|agent (default ``council``)
======================================  =======================================
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger("aifactory.metis_gate")

_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off", "disable", "disabled"}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def metis_gate_mode() -> str:
    """Resolved mode: ``auto`` (default) | ``on`` | ``off``."""
    v = _env("AIFACTORY_METIS_GATE", "auto").lower()
    if v in _OFF:
        return "off"
    if v in _ON:
        return "on"
    return "auto"


def metis_gate_enabled() -> bool:
    """True unless explicitly turned off (auto and on both may use Metis)."""
    return metis_gate_mode() != "off"


def metis_gate_blocking() -> bool:
    """True when an ``ok=False`` verdict is allowed to escalate (opt-in)."""
    return _env("AIFACTORY_METIS_GATE_BLOCK", "0").lower() in _ON


def _base_url() -> str:
    return (_env("AIFACTORY_METIS_URL") or _env("METIS_URL") or "http://127.0.0.1:8080").rstrip("/")


def _api_key() -> str:
    return _env("AIFACTORY_METIS_API_KEY") or _env("METIS_API_KEY")


def _float_env(name: str, default: float, *, lo: float = 0.0, hi: float = 1e9) -> float:
    try:
        return min(hi, max(lo, float(_env(name, str(default)))))
    except ValueError:
        return default


def _timeout() -> float:
    return _float_env("AIFACTORY_METIS_GATE_TIMEOUT", 300.0, lo=1.0)


def _probe_timeout() -> float:
    return _float_env("AIFACTORY_METIS_PROBE_TIMEOUT", 2.0, lo=0.2)


def _probe_ttl() -> float:
    return _float_env("AIFACTORY_METIS_PROBE_TTL", 60.0, lo=1.0)


def _min_score() -> float:
    return _float_env("AIFACTORY_METIS_GATE_MIN_SCORE", 0.7, lo=0.0, hi=1.0)


def _route() -> str:
    return _env("AIFACTORY_METIS_GATE_ROUTE", "council") or "council"


# ── Detection cache ──────────────────────────────────────────────────────────
# Populated by _metis_available(); avoids probing (or timing out) on every call.
_PROBE: dict[str, Any] = {"ok": None, "ts": 0.0}


def reset_probe_cache() -> None:
    """Forget the cached detection result (used by tests and after config change)."""
    _PROBE["ok"] = None
    _PROBE["ts"] = 0.0


def _metis_available(timeout: Optional[float] = None) -> bool:
    """Cheap, cached ``GET /health`` probe. Never raises."""
    now = time.monotonic()
    cached = _PROBE["ok"]
    if cached is not None and (now - float(_PROBE["ts"])) < _probe_ttl():
        return bool(cached)
    ok = False
    try:
        req = urllib.request.Request(f"{_base_url()}/health", method="GET")
        key = _api_key()
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=timeout or _probe_timeout()) as resp:
            ok = 200 <= getattr(resp, "status", resp.getcode()) < 300
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        ok = False
    _PROBE["ok"] = ok
    _PROBE["ts"] = now
    return ok


@dataclass
class GateVerdict:
    """Outcome of a gate check.

    ``ok`` is the single decision bit: ``True`` means *proceed* — the gate
    passed, was disabled, or Metis was unavailable (fail-open). ``False`` means
    Metis actively flagged low confidence / needed clarification.
    """

    ok: bool
    available: bool
    verified: bool
    status: str  # success | needs_clarification | error | disabled | unavailable
    verify_score: float
    answer: str = ""
    clarifications: List[str] = field(default_factory=list)
    route: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _proceed(status: str, reason: str) -> GateVerdict:
    return GateVerdict(
        ok=True, available=False, verified=False, status=status, verify_score=0.0, reason=reason
    )


def build_understanding_query(idea: str, spec: Optional[str] = None) -> str:
    """Compose a build-readiness prompt so Metis's confidence gate can fire.

    Metis will return ``needs_clarification`` (→ ``ok=False``) when the idea/spec
    is too ambiguous to build without guessing — exactly the signal an autonomous
    factory otherwise lacks.
    """
    parts = [
        "You are a build-readiness reviewer for an autonomous product factory.",
        "Decide whether the following product is specified well enough to build "
        "WITHOUT guessing. If anything critical is ambiguous, missing, or "
        "contradictory, ask for clarification instead of answering.",
        f"IDEA:\n{(idea or '').strip()[:8000]}",
    ]
    if spec and spec.strip():
        parts.append(f"SPEC:\n{spec.strip()[:8000]}")
    return "\n\n".join(parts)


def verify(
    query: str,
    *,
    route: Optional[str] = None,
    min_score: Optional[float] = None,
    timeout: Optional[float] = None,
) -> GateVerdict:
    """Run one auto-detecting, fail-open gate check. Never raises."""
    mode = metis_gate_mode()
    if mode == "off":
        return _proceed("disabled", "gate disabled")
    q = (query or "").strip()
    if not q:
        return _proceed("disabled", "empty query")

    # Auto mode: skip fast if Metis isn't detected (cached). "on" mode calls
    # unconditionally (still fail-open below).
    if mode == "auto" and not _metis_available():
        return _proceed("unavailable", "auto: metis not detected")

    threshold = min_score if min_score is not None else _min_score()
    payload = {"input": q, "route": route or _route(), "min_verify_score": threshold}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_base_url()}/v1/verify",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    key = _api_key()
    if key:
        req.add_header("Authorization", f"Bearer {key}")

    try:
        with urllib.request.urlopen(req, timeout=timeout or _timeout()) as resp:
            body: Any = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # Fail-open: Metis unreachable / slow / malformed → proceed unchanged.
        logger.info("metis gate unavailable, proceeding (fail-open): %s", exc)
        _PROBE["ok"] = False  # remember the miss so the next call skips fast
        _PROBE["ts"] = time.monotonic()
        return _proceed("unavailable", type(exc).__name__)

    if not isinstance(body, dict):
        return _proceed("unavailable", "non-object response")

    status = str(body.get("status") or "error")
    verified = bool(body.get("verified"))
    try:
        score = float(body.get("verify_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    clar = [str(c) for c in (body.get("clarifications") or [])]
    answer = str(body.get("answer") or "")
    resp_route = str(body.get("route") or (route or _route()))

    if status == "error":
        # Engine-side error is treated as fail-open (do not block the factory).
        return GateVerdict(
            ok=True, available=True, verified=False, status="error",
            verify_score=score, answer=answer, route=resp_route, reason="engine_error",
        )
    if status == "needs_clarification":
        return GateVerdict(
            ok=False, available=True, verified=False, status=status,
            verify_score=score, answer=answer, clarifications=clar, route=resp_route,
            reason="needs_clarification",
        )
    ok = verified or score >= threshold
    return GateVerdict(
        ok=ok, available=True, verified=verified, status=status, verify_score=score,
        answer=answer, clarifications=clar, route=resp_route,
        reason="verified" if ok else "low_confidence",
    )


def verify_product_understanding(
    idea: str, spec: Optional[str] = None, **kwargs: Any
) -> GateVerdict:
    """Convenience: gate a product's build-readiness from its idea/spec."""
    return verify(build_understanding_query(idea, spec), **kwargs)
