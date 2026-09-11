"""Open the deployed site in a browser and decide whether it is actually a product.

Every gate in this pipeline measures a sandbox: uvicorn on loopback, a venv assembled for the run,
a preview build served from disk. That is the right place to catch most defects and the wrong place
to decide that a deployment works, because the two environments differ in exactly the ways that
break deployments.

This gate is the last word: it drives the LIVE URL the way a person would — every SPA route, every
form, every public API the OpenAPI document advertises — and it is allowed to un-publish. A page
that renders while its only feature answers 200 with a Python TypeError hidden as UNKNOWN is not a
product. Measured on Sentinel: `/api/health` was 200, the primary button was clicked on an empty
required form, styled_ratio passed, and the visitor still saw

    AtlasClient.get_situation_brief() got an unexpected keyword argument 'west'
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from web.backend.services.browser_e2e_deep import exception_in_product_output

logger = logging.getLogger(__name__)

# Measured on the real failure: the deployed page had 9 of 31 elements carrying any non-default
# styling — 29% — and looked like an unstyled document to the person who opened it. A designed page
# styles most of what it renders; a ratio this low means the markup is asking for rules that do not
# exist. Kept as a ratio rather than a count because a large page can fail while a small one passes.
_MIN_STYLED_RATIO = 0.45
_MIN_ELEMENTS_TO_JUDGE = 10

# Berlin: the same geo the demo journey uses, so an empty answer is a defect rather than a blank
# spot on the map. LA is the live-gate mesh probe: Berlin often has zero LIVE pins, which is an
# honest ATLAS refuse — not a deploy defect. Connection failures still fail the gate everywhere.
_LIVE_LAT = "52.52"
_LIVE_LON = "13.40"
_MESH_PROBE_LAT = "34.05"
_MESH_PROBE_LON = "-118.25"

_MESH_UNREACHABLE_RE = re.compile(
    r"All connection attempts failed|Connection refused|ConnectTimeout|ConnectError|"
    r"Name or service not known|nodename nor servname|Failed to establish a new connection|"
    r"Max retries exceeded|Network is unreachable|"
    r"Mesh unavailable:.*(localhost|127\.0\.0\.1|Connect|attempts failed)|"
    # Soft mesh failure: serverless answered 200 with RuleEngine placeholder. Sentinel
    # shipped green live_gate while /api/advisory stayed UNKNOWN forever because this
    # phrase was treated as an honest refuse, not a deploy defect.
    r"mesh response unavailable|"
    r"payment_authorization|Status 40\d|X-Payment-Channel|escrow",
    re.I,
)

# Paid invoke that reached Hub but cannot settle. Not a code defect — developer
# rewriting atlas_client.py cannot mint USDC. Checked before unreachable so
# "insufficient balance" is not mislabeled as a missing invoke path.
_MESH_PAYMENT_RE = re.compile(
    r"insufficient balance|payment_authorization|not open on chain|"
    r"escrow channel|X-Payment-Channel",
    re.I,
)

_LIVE_MESH_PAYMENT_MARKERS = (
    "live_mesh_payment_ops",
    "insufficient balance",
    "payment_authorization",
    "not open on chain",
    "escrow channel",
    "aimarket_participant.env",
)

HUMAN_REVIEW_KIND_LIVE_MESH_PAYMENT = "live_mesh_payment_ops"


def _code_dir_for(product_id: str | None, data_root: str | Path | None) -> Path | None:
    if not product_id:
        return None
    try:
        from core.paths import code_dir as resolve_code_dir

        path = resolve_code_dir(product_id, data_root=data_root)
    except Exception:
        return None
    return path if path.is_dir() else None


def _auth_seed_repair_files(code_dir: Path | None) -> list[str]:
    """Files that must read SANDBOX_DEMO_* so the live gate can log in after publish."""
    if code_dir is None or not code_dir.is_dir():
        return []
    candidates = (
        "backend/app/seed.py",
        "backend/app/demo_seed.py",
        "backend/app/services/seeding.py",
        "backend/app/services/demo_seed.py",
        "backend/app/routers/auth.py",
        "backend/app/routers/workspace.py",
        "backend/app/core/seed.py",
        "backend/app/db/seed.py",
        # An unstable identity is minted by the model default and resolved in the session
        # dependency; a repair round that only opens the seeds cannot fix either end.
        "backend/app/models/user.py",
        "backend/app/models/workspace.py",
        "backend/app/deps.py",
        "backend/app/schemas/auth.py",
        "backend/app/schemas/branding.py",
        "frontend/src/api.ts",
        "frontend/src/pages/Branding.tsx",
    )
    found: list[str] = []
    for rel in candidates:
        if (code_dir / rel).is_file() and rel not in found:
            found.append(rel)
    if found:
        return found
    skip = {"tests", "test", "node_modules", ".venv", "venv"}
    try:
        for path in code_dir.rglob("*.py"):
            if any(part in skip for part in path.parts):
                continue
            name = path.name.lower()
            if "seed" not in name and path.name != "auth.py":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:40_000]
            except OSError:
                continue
            if "SANDBOX_DEMO" in text or "demo" in name:
                rel = path.relative_to(code_dir).as_posix()
                if rel not in found:
                    found.append(rel)
            if len(found) >= 6:
                break
    except Exception:
        return found
    return found


def _is_demo_auth_failure(status: int, path: str, body: str = "") -> bool:
    if status not in (401, 403):
        return False
    low_path = (path or "").lower()
    if any(tok in low_path for tok in ("/auth/login", "/api/auth", "/login", "/token")):
        return True
    low_body = (body or "").lower()
    return "invalid credentials" in low_body or "incorrect password" in low_body


def _issue_for_demo_auth(*, where: str, status: int, body: str = "") -> str:
    snippet = " ".join((body or "")[:160].split())
    return (
        f"live_demo_auth_mismatch:POST {where}:{status} on the DEPLOYED site. "
        "Factory live-gate credentials (SANDBOX_DEMO_EMAIL / SANDBOX_DEMO_PASSWORD) were rejected. "
        "The Vercel bundle must inject those env vars into api/index.py and vercel.json, and the "
        "product seed must create that user from env — not only local fallbacks like "
        "operator@….local. Fix publish injection / seed env wiring; do not treat this as a "
        "missing Python dependency. "
        f"Body: {snippet}"
    )


def _repair_scope_from_issues(issues: list[str], code_dir: Path | None) -> list[str]:
    """Name the files a repair round must open, so scope does not wander into operator TSX."""
    from core.repair_batches import _files_in

    named: list[str] = []
    blob = " ".join(issues)
    for rel in _files_in(blob):
        if rel not in named:
            named.append(rel)
    if re.search(
        r"live_demo_auth_mismatch|live_http_401|live_ephemeral_identity|"
        r"live_session_not_durable|live_authed_feature_dead|live_branding|"
        r"Invalid credentials|/auth/login|SANDBOX_DEMO|/workspace/branding",
        blob,
        re.I,
    ):
        for rel in _auth_seed_repair_files(code_dir):
            if rel not in named:
                named.append(rel)
    if re.search(
        r"live_mesh_unreachable|All connection attempts failed|/aimarket/invoke|ATLAS_BASE|"
        r"mesh response unavailable|payment_authorization|aimarket_participant",
        blob,
        re.I,
    ):
        candidates = (
            "backend/app/services/atlas_client.py",
            "backend/app/services/aimarket_participant.py",
            "backend/app/config.py",
            "backend/app/routers/advisory.py",
            "app/services/atlas_client.py",
            "app/services/aimarket_participant.py",
            "app/routers/advisory.py",
        )
        for rel in candidates:
            if code_dir is not None and (code_dir / rel).is_file() and rel not in named:
                named.append(rel)
        if code_dir is not None and not any("atlas_client" in r for r in named):
            try:
                for path in code_dir.rglob("atlas_client.py"):
                    rel = path.relative_to(code_dir).as_posix()
                    if rel not in named:
                        named.append(rel)
                    break
                for path in code_dir.rglob("aimarket_participant.py"):
                    rel = path.relative_to(code_dir).as_posix()
                    if rel not in named:
                        named.append(rel)
                    break
                for path in code_dir.rglob("advisory.py"):
                    if "router" in path.as_posix() or path.parent.name == "routers":
                        rel = path.relative_to(code_dir).as_posix()
                        if rel not in named:
                            named.append(rel)
                        break
            except Exception:
                pass
    if code_dir is None:
        return named[:12]
    class_hits = re.findall(r"\b([A-Z][A-Za-z0-9]+)[.]([A-Za-z_][A-Za-z0-9_]*)\s*\(", blob)
    needles: list[str] = []
    for cls, method in class_hits:
        needles.append(f"class {cls}")
        needles.append(f"def {method}")
        needles.append(f"async def {method}")
        needles.append(f".{method}(")
    if not needles:
        return named[:12]
    skip = {"tests", "test", "node_modules", ".venv", "venv", "alembic", "migrations"}
    try:
        for path in code_dir.rglob("*.py"):
            if any(part in skip for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:80_000]
            except OSError:
                continue
            if any(n in text for n in needles):
                rel = path.relative_to(code_dir).as_posix()
                if rel not in named:
                    named.append(rel)
            if len(named) >= 12:
                break
    except Exception:
        return named[:12]
    return named[:12]


def _returned_tuple_status(body: str) -> int | None:
    """The error code in a handler that returned ``(payload, status)`` instead of a Response.

    ``return {"detail": "Not Found"}, 404`` is not an error in FastAPI — the tuple becomes the
    response *body*, serialised as ``[{"detail":"Not Found"},404]``, and the status line says
    200. Sentinel shipped with that in its SPA catch-all, so every unknown ``/api/`` path
    answered 200 and no client could tell a missing route from a working one.

    Deliberately narrow: a JSON array of two or three elements whose *second* element is an
    integer HTTP error code — the status sits at index 1 in both ``(body, status)`` and
    ``(body, status, headers)`` — and whose first is an object or string. A list of plain
    numbers does not match, and neither does a body that merely mentions 404.
    """
    try:
        payload = json.loads(body) if body else None
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, list) or not (2 <= len(payload) <= 3):
        return None
    code = payload[1]
    if isinstance(code, bool) or not isinstance(code, int):
        return None
    if not 400 <= code <= 599:
        return None
    if not isinstance(payload[0], (dict, str)):
        return None
    return code


def _issue_for_returned_tuple(*, where: str, status: int, code: int, body: str) -> str:
    snippet = " ".join((body or "")[:200].split())
    return (
        f"api_status_contract:{where}:{status} on the DEPLOYED site answered HTTP {status} with a "
        f"body that is a serialised (payload, {code}) tuple: {snippet}. A handler returned "
        f"`something, {code}` instead of a Response, so FastAPI made the tuple the body and the "
        f"status line still says {status}. Every caller — browser, SDK, monitor and this gate — "
        f"reads that as success. Return JSONResponse(status_code={code}, ...) or raise "
        f"HTTPException({code}). The SPA catch-all in backend/app/main.py is the shape that "
        "shipped."
    )


# A path no product defines. Anything under /api/ that answers 2xx here is a catch-all
# swallowing unknown routes — the same defect seen from the outside.
_MISSING_API_PROBE = "/api/__aicom_missing_route_probe__"


def _probe_unknown_api_path(base: str) -> tuple[list[str], dict[str, Any]]:
    """An undefined API route must not answer 2xx."""
    from web.backend.services.product_demo_journey import _call

    status, body = _call("GET", base.rstrip("/") + _MISSING_API_PROBE, timeout=45.0)
    report = {"path": _MISSING_API_PROBE, "status": status, "body": (body or "")[:200]}
    issues: list[str] = []
    if 200 <= status < 300:
        code = _returned_tuple_status(body)
        if code:
            issues.append(
                _issue_for_returned_tuple(
                    where=_MISSING_API_PROBE, status=status, code=code, body=body
                )
            )
        else:
            snippet = " ".join((body or "")[:200].split())
            issues.append(
                f"api_missing_route_is_200:{_MISSING_API_PROBE}:{status} on the DEPLOYED site. A "
                f"route the product does not define answered {status}: {snippet}. The SPA "
                "catch-all is serving requests under /api/, so a caller cannot distinguish a "
                "missing endpoint from a working one and a typo in the frontend fails silently. "
                "Let unknown /api/ paths 404 (see backend/app/main.py)."
            )
    return issues, report


def _jwt_subject(token: str) -> str:
    """The identity a token names, read without verifying — this is a probe, not auth."""
    import base64

    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return ""
    return str(claims.get("sub") or claims.get("user_id") or "")


# Always probe these after login even when OpenAPI omits them. Relay shipped a green
# live gate while /api/workspace/branding answered 500 "internal error" because the
# durability probe only looked for operator/admin/me/dashboard and ignored 5xx.
_DEFAULT_AUTH_FEATURE_PROBES = (
    "/api/auth/me",
    "/api/workspace/branding",
    "/api/handoffs",
    "/api/operator/me",
)


def _protected_probe_paths(paths: dict[str, Any]) -> list[str]:
    """Documented GETs most likely to require the session, so a 401/5xx means something."""
    out: list[str] = []
    tokens = (
        "operator",
        "admin",
        "account",
        "/me",
        "dashboard",
        "workspace",
        "branding",
        "handoff",
        "inbox",
        "session",
    )
    for path, ops in (paths or {}).items():
        if not isinstance(ops, dict) or "get" not in ops:
            continue
        p = str(path)
        if "{" in p:
            continue
        if any(tok in p.lower() for tok in tokens):
            out.append(p)
    for fallback in _DEFAULT_AUTH_FEATURE_PROBES:
        if fallback not in out:
            out.append(fallback)
    return out[:8]


def _issue_for_authed_feature_dead(*, path: str, status: int, body: str) -> str:
    snippet = " ".join((body or "")[:200].split())
    return (
        f"live_authed_feature_dead:{path}:{status} on the DEPLOYED site after a 200 login. "
        "The visitor can sign in, but the authenticated feature the product exists for "
        f"answers {status}: {snippet}. Typical causes: session cookie name mismatch vs "
        "Bearer (login sets relay_session / access_token but deps look for another cookie), "
        "naive vs aware datetime compare on session expiry (TypeError → generic "
        "'internal error'), BrandingOut/WorkspaceOut.model_validate choking on an Enum "
        "tier, or a catch-all Exception handler hiding the real traceback. Fix ONE shared "
        "get_current_operator that accepts Authorization Bearer FIRST then the session "
        "cookie; normalize expires_at tzinfo before compare; return branding as plain "
        "field dicts (tier as .value str). Do not leave Branding as a blank page or "
        "'internal error' after login."
    )


def _probe_session_durability(
    base: str, login_path: str, email: str, password: str, paths: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """A session minted once must still authenticate on the next request.

    Serverless runs the product on many instances, each with its own empty database under
    ``/tmp``. A demo user re-seeded per instance with a random primary key makes every login
    mint a token naming an identity no *other* instance can resolve, so the dashboard answers
    401 "User not found" on roughly every other request. One login followed immediately by a
    sweep never sees it: those requests land on the instance that was just warmed. This probe
    logs in several times concurrently — which forces several instances — and then replays each
    token, which is what a visitor's second page view does.

    Measured on Sentinel's published deployment: 10 logins, 9 distinct identities, and 5 of 6
    replayed tokens rejected with 401 "User not found" — while the gate reported passed=True.

    Measured on Relay: login + /api/auth/me were 200 while /api/workspace/branding returned
    500 ``{"detail":"internal error"}`` — durability only counted 401/403, so Branding shipped
    broken. 5xx on an authenticated feature probe is a dead product, not a soft skip.
    """
    from concurrent.futures import ThreadPoolExecutor

    from web.backend.services.product_demo_journey import _call, attempt_login

    report: dict[str, Any] = {"login_path": login_path}
    issues: list[str] = []
    probes = _protected_probe_paths(paths)
    report["probe_paths"] = probes

    def _login(_: int) -> str:
        try:
            token, _trace = attempt_login(base, login_path, email, password)
        except Exception:
            return ""
        return token

    with ThreadPoolExecutor(max_workers=6) as pool:
        tokens = [t for t in pool.map(_login, range(6)) if t]
    report["logins_succeeded"] = len(tokens)
    if not tokens:
        # A login that never succeeds is already reported by the sweep; nothing to add here.
        return issues, report

    subjects = {s for s in (_jwt_subject(t) for t in tokens) if s}
    report["distinct_subjects"] = len(subjects)
    if len(subjects) > 1:
        issues.append(
            f"live_ephemeral_identity:{login_path}: {len(tokens)} logins with the same "
            f"credentials minted {len(subjects)} different user identities on the DEPLOYED site. "
            "Each serverless instance seeds its own database, so a token issued by one instance "
            "names a primary key the others have never stored and every later request answers "
            "401. Seed the demo identity with a key derived from its email (deterministic across "
            "instances) instead of a random uuid, and resolve the session by the stable claim."
        )

    replay_failures: list[dict[str, Any]] = []
    feature_5xx: list[dict[str, Any]] = []
    for token in tokens[:4]:
        for path in probes:
            status, body = _call("GET", base.rstrip("/") + path, token=token, timeout=60.0)
            # 404 on a fallback probe means this product simply has no such route — ignore.
            if status == 404 and path in _DEFAULT_AUTH_FEATURE_PROBES:
                continue
            if status in (401, 403):
                replay_failures.append({"path": path, "status": status, "body": (body or "")[:160]})
            elif status >= 500:
                feature_5xx.append({"path": path, "status": status, "body": (body or "")[:200]})
    report["replay_failures"] = replay_failures[:8]
    report["feature_5xx"] = feature_5xx[:8]
    if replay_failures and not issues:
        first = replay_failures[0]
        issues.append(
            f"live_session_not_durable:{first['path']}:{first['status']} on the DEPLOYED site "
            f"after a 200 login ({len(replay_failures)} of the replays were rejected). "
            f"Body: {first['body']}. The session works on the instance that served the login and "
            "nowhere else, so the authenticated UI fails on the visitor's next request. Persist "
            "the identity or derive it deterministically so any instance resolves the same token."
        )
    # Deduplicate by path — concurrent tokens often hit the same broken route.
    seen_5xx: set[str] = set()
    for hit in feature_5xx:
        path = str(hit.get("path") or "")
        if path in seen_5xx:
            continue
        seen_5xx.add(path)
        issues.append(
            _issue_for_authed_feature_dead(
                path=path,
                status=int(hit.get("status") or 500),
                body=str(hit.get("body") or ""),
            )
        )
    return issues, report


def _issue_for_mesh_unreachable(*, where: str, status: int, reason: str) -> str:
    snippet = " ".join((reason or "")[:220].split())
    return (
        f"live_mesh_unreachable:{where}:{status} on the DEPLOYED site: {snippet}. "
        "The serverless function cannot reach the public ATLAS/Hub mesh. Publish must inject "
        "AIMARKET_HUB_URL=https://modelmarket.dev (and/or ATLAS_BASE_URL=https://atlas.modelmarket.dev), "
        "call /ai-market/v2/invoke — not legacy /aimarket/invoke — and send "
        "X-AIMarket-Sandbox-Visitor and/or X-Payment-Channel (not demo X-Agent-Key alone)."
    )


def _issue_for_mesh_payment(*, where: str, status: int, reason: str) -> str:
    snippet = " ".join((reason or "")[:220].split())
    return (
        f"live_mesh_payment_ops:{where}:{status} on the DEPLOYED site: {snippet}. "
        "Hub reached the invoke but refused to settle (empty, expired, or unopened escrow). "
        "Operator: scripts/reopen_product_escrow_channel.py <product_id> then republish. "
        "Do not send this to developer — atlas_client.py cannot mint USDC."
    )


def live_gate_is_payment_ops(live_gate: dict[str, Any] | None, issues: list[str] | None = None) -> bool:
    """True when the live URL failed because Hub/escrow cannot pay, not because code is wrong."""
    blob_parts: list[str] = []
    if isinstance(live_gate, dict):
        blob_parts.extend(str(i) for i in (live_gate.get("issues") or []))
    if issues:
        blob_parts.extend(str(i) for i in issues)
    blob = " ".join(blob_parts).lower()
    return any(m in blob for m in _LIVE_MESH_PAYMENT_MARKERS)


def live_gate_is_demo_auth(live_gate: dict[str, Any] | None, issues: list[str] | None = None) -> bool:
    """True when the live URL failed the factory demo login / session — a known autofix class."""
    blob_parts: list[str] = []
    if isinstance(live_gate, dict):
        blob_parts.extend(str(i) for i in (live_gate.get("issues") or []))
    if issues:
        blob_parts.extend(str(i) for i in issues)
    blob = " ".join(blob_parts).lower()
    return any(m in blob for m in _LIVE_GATE_COMPLETION_BLOCKERS)


# Operator COMPLETE / auto-recovery must not stamp a product finished while the
# deployed visitor/operator path is still 401. Measured: Sentinel live-gate wrote
# live_demo_auth_mismatch, then operator_complete --force (storefront-only skip)
# plus a dishonest live_gate.passed=True left POST /api/auth/login broken.
_LIVE_GATE_COMPLETION_BLOCKERS = (
    "live_demo_auth_mismatch",
    "live_http_401",
    "live_ephemeral_identity",
    "live_session_not_durable",
    "live_authed_feature_dead",
    "invalid credentials",
    "operator_login_401",
)


def live_gate_blocks_completion(product: dict[str, Any] | None) -> str | None:
    """Reason to refuse COMPLETE, or None when live-gate does not block.

    Auth 401 blocks even if ``passed`` was later stamped True. A failed gate
    (``passed is False``) also blocks unless it was skipped. Payment-ops is a
    separate park path; it still must not COMPLETE.
    """
    if not isinstance(product, dict):
        return None
    lg = product.get("live_gate")
    if not isinstance(lg, dict):
        return None
    issues = [str(i) for i in (lg.get("issues") or [])]
    blob = " ".join(issues).lower()
    for marker in _LIVE_GATE_COMPLETION_BLOCKERS:
        if marker in blob:
            return (issues[0] if issues else marker)[:300]
    if lg.get("skipped"):
        return None
    if lg.get("passed") is False:
        return (issues[0] if issues else "live_gate_failed")[:300]
    return None


def park_product_live_mesh_payment_ops(product: dict[str, Any], live_gate: dict[str, Any]) -> None:
    """Hold at HUMAN_REVIEW. Another developer round cannot fund an escrow channel."""
    pid = str(product.get("id") or "").strip()
    issues = [str(i) for i in (live_gate.get("issues") or [])]
    reason = (
        issues[0]
        if issues
        else "Live mesh payment ops: Hub refused a paid invoke (empty or expired escrow)."
    )
    product["state"] = "HUMAN_REVIEW_PENDING"
    product["human_review_kind"] = HUMAN_REVIEW_KIND_LIVE_MESH_PAYMENT
    product["human_review_reason"] = reason[:2000]
    product["live_gate"] = live_gate
    product["last_bug_context"] = {
        "source": "live_deployment_gate",
        "quality_gates_feedback": live_gate_quality_feedback(live_gate),
    }
    product["updated_at"] = time.time()
    product["operator_locked"] = True
    product["operator_locked_at"] = time.time()
    if pid:
        try:
            from web.backend.services.product_followup import set_product_pipeline_on_hold

            set_product_pipeline_on_hold(pid, True)
        except Exception:
            logger.debug("live_mesh_payment_ops hold failed for %s", pid, exc_info=True)


def _issue_for_exception(*, where: str, status: int, hit: str, body: str) -> str:
    snippet = " ".join((body or "")[:220].split())
    return (
        f"live_exception_in_ui:{where}:{status} on the DEPLOYED site: {hit}. "
        "The endpoint answered 200 (or painted the page) with a Python exception in the body, "
        "which the honesty policy wrapped as UNKNOWN. This is a call/signature mismatch, not "
        "missing sensors. Fix the call site to match the method signature "
        "(backend/app/routers/advisory.py calling backend/app/services/atlas_client.py is the "
        "shape that shipped). Do NOT swallow TypeError/AttributeError into UNKNOWN. "
        f"Body: {snippet}"
    )


def _sweep_live_api(base: str) -> tuple[list[str], dict[str, Any]]:
    """Exercise every documented GET on the deployed origin, filling required query params."""
    from web.backend.services.product_demo_journey import (
        _find_login_paths,
        _openapi,
        attempt_login,
        sweep_get_endpoints,
    )
    from core.demo_identity import sandbox_demo_email
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose

    issues: list[str] = []
    report: dict[str, Any] = {"base": base}
    doc = _openapi(base)
    paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
    report["openapi_path_count"] = len(paths)
    try:
        missing_issues, missing_report = _probe_unknown_api_path(base)
        report["missing_route_probe"] = missing_report
        issues.extend(missing_issues)
    except Exception as exc:
        report["missing_route_probe_error"] = str(exc)[:160]
    token = ""
    login_paths = _find_login_paths(paths) if paths else []
    report["login_paths"] = login_paths
    if login_paths:
        try:
            email = sandbox_demo_email()
            password = effective_sandbox_demo_password_for_compose()
            token, trace = attempt_login(base, login_paths[0], email, password)
            report["login"] = {k: v for k, v in trace.items() if k != "attempts"}
            report["login_attempts"] = (trace.get("attempts") or [])[:3]
        except Exception as exc:
            report["login_error"] = str(exc)[:160]
        # A 5xx on login is a dead product. A 401 means factory demo credentials were not
        # seeded on Vercel (missing SANDBOX_DEMO_* in the publish bundle, or seed ignores them).
        for attempt in (report.get("login_attempts") or []):
            if not isinstance(attempt, dict):
                continue
            status = int(attempt.get("status") or 0)
            body = str(attempt.get("body") or "")
            hit = exception_in_product_output(body)
            if hit:
                issues.append(_issue_for_exception(where=login_paths[0], status=status, hit=hit, body=body))
            elif _is_demo_auth_failure(status, login_paths[0], body):
                issues.append(
                    _issue_for_demo_auth(where=login_paths[0], status=status, body=body)
                )
            elif status >= 500:
                issues.append(
                    f"live_http_{status}:POST {login_paths[0]}:{status} on the DEPLOYED site. "
                    "Login is production, not the sandbox."
                )
        # One login followed by an immediate sweep only ever measures the instance it warmed.
        if token:
            try:
                dur_issues, dur_report = _probe_session_durability(
                    base, login_paths[0], email, password, paths
                )
                report["session_durability"] = dur_report
                issues.extend(dur_issues)
            except Exception as exc:
                report["session_durability_error"] = str(exc)[:160]
    if paths:
        results, sweep_issues = sweep_get_endpoints(base, paths, token)
        report["endpoints"] = results
        issues.extend(sweep_issues)
    # Always hit the geo feature even when OpenAPI is missing or relocated: this is the
    # call a visitor makes from the widget, and health-only probes never reach it.
    # Use an ATLAS-hot bbox for the mesh reachability probe (Berlin is often empty LIVE).
    from web.backend.services.product_demo_journey import _call

    for path in (
        f"/api/advisory?lat={_MESH_PROBE_LAT}&lon={_MESH_PROBE_LON}",
        f"/advisory?lat={_MESH_PROBE_LAT}&lon={_MESH_PROBE_LON}",
        f"/api/advisory?lat={_LIVE_LAT}&lon={_LIVE_LON}",
        f"/advisory?lat={_LIVE_LAT}&lon={_LIVE_LON}",
    ):
        status, body = _call("GET", base.rstrip("/") + path, timeout=90.0)
        report.setdefault("feature_probes", []).append({"path": path, "status": status, "body": (body or "")[:300]})
        if status == 0:
            continue
        tuple_code = _returned_tuple_status(body) if 200 <= status < 300 else None
        hit = exception_in_product_output(body)
        if tuple_code:
            issues.append(
                _issue_for_returned_tuple(where=path, status=status, code=tuple_code, body=body)
            )
        elif hit:
            issues.append(_issue_for_exception(where=path, status=status, hit=hit, body=body))
        elif status >= 500:
            issues.append(
                f"live_api_dead:{path}:{status} on the DEPLOYED site — {(body or '')[:160]}. "
                "The page is static build output and renders regardless; the backend behind it "
                "does not run."
            )
        elif 200 <= status < 400:
            try:
                payload = json.loads(body) if body else {}
            except ValueError:
                payload = {}
            overall = payload.get("overall") if isinstance(payload, dict) else None
            reason = ""
            if isinstance(overall, dict):
                reason = str(overall.get("reason") or "")
            mesh_text = reason or body or ""
            if _MESH_PAYMENT_RE.search(mesh_text):
                issues.append(_issue_for_mesh_payment(where=path, status=status, reason=reason or body))
            elif _MESH_UNREACHABLE_RE.search(mesh_text):
                issues.append(_issue_for_mesh_unreachable(where=path, status=status, reason=reason or body))
            else:
                hit = exception_in_product_output(reason or body)
                if hit:
                    issues.append(_issue_for_exception(where=path, status=status, hit=hit, body=reason or body))
        break
    return issues, report


def check_live_deployment(
    url: str,
    *,
    product_id: str | None = None,
    data_root: str | Path | None = None,
    timeout_sec: float = 180.0,
) -> dict[str, Any]:
    """Drive a real browser against a deployed URL. Full UI of every route, not a load+click."""
    out: dict[str, Any] = {"url": url, "passed": False, "issues": [], "skipped": False}
    if not url:
        out["skipped"] = True
        out["reason"] = "no_url"
        return out

    issues: list[str] = out["issues"]
    code_dir = _code_dir_for(product_id, data_root)
    origin = url.rstrip("/")

    # HTTP sweep first: the TypeError in /api/advisory is visible without a browser, and a
    # missing Playwright must not skip a product that already leaked a Python exception.
    api_issues, api_report = _sweep_live_api(origin)
    out["api_sweep"] = api_report
    issues.extend(api_issues)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        out["repair_scope"] = _repair_scope_from_issues(issues, code_dir)
        out["reason"] = f"playwright_unavailable:{exc}"
        if issues:
            out["passed"] = False
            out["skipped"] = False
            return out
        out["skipped"] = True
        return out

    from web.backend.services.browser_e2e_deep import (
        deep_crawl_gate_issues,
        run_deep_crawl,
        spa_routes_from_source,
    )

    console_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    json_bodies: list[dict[str, Any]] = []
    # Paths that answered 2xx at some point in the crawl. A 401 on a path that later succeeded
    # is the crawler arriving before it submitted the login form; a 401 on a path that never
    # succeeded is the authenticated UI failing for a visitor.
    ok_paths: set[str] = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            try:
                page = browser.new_page()
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text[:300])
                    if msg.type == "error"
                    else None,
                )

                def _on_response(response) -> None:
                    try:
                        status = int(response.status)
                        path = urlparse(response.url).path or "/"
                        if 200 <= status < 300:
                            ok_paths.add(path)
                        body = ""
                        try:
                            ct = (response.headers.get("content-type") or "").lower()
                            if status >= 400 or "json" in ct or "advisory" in path:
                                body = (response.text() or "")[:2000]
                        except Exception:
                            body = ""
                        if body:
                            json_bodies.append({"path": path, "status": status, "body": body[:800]})
                            tuple_code = (
                                _returned_tuple_status(body) if 200 <= status < 300 else None
                            )
                            if tuple_code:
                                issues.append(
                                    _issue_for_returned_tuple(
                                        where=path, status=status, code=tuple_code, body=body
                                    )
                                )
                            hit = exception_in_product_output(body)
                            if hit:
                                issues.append(
                                    _issue_for_exception(where=path, status=status, hit=hit, body=body)
                                )
                        if status >= 400:
                            failed_requests.append(
                                {
                                    "method": (response.request.method or "GET").upper(),
                                    "path": path,
                                    "status": status,
                                    "body": body[:400],
                                }
                            )
                    except Exception:
                        pass

                page.on("response", _on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
                try:
                    page.wait_for_selector("h1, [role='heading'], #root > *", timeout=8_000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                text = (page.inner_text("body") or "").strip()
                out["text_length"] = len(text)
                if len(text) < 40:
                    issues.append(
                        f"live_blank_page:{url}: the deployed page renders {len(text)} characters of "
                        "text. Whatever the build produced, a visitor sees nothing."
                    )
                hit = exception_in_product_output(text)
                if hit:
                    issues.append(_issue_for_exception(where="/", status=200, hit=hit, body=text))

                # Is anything actually styled? Class names that resolve to no CSS rule leave every
                # element at browser defaults, which is precisely how a "successful" deploy looks
                # like a 1996 document.
                styled = page.evaluate(
                    """() => {
                        const els = Array.from(document.querySelectorAll('body *')).slice(0, 400);
                        let styled = 0;
                        for (const el of els) {
                            const cs = getComputedStyle(el);
                            const painted =
                            (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)'
                                && cs.backgroundColor !== 'transparent') ||
                                (cs.borderTopWidth && cs.borderTopWidth !== '0px') ||
                                (cs.borderRadius && cs.borderRadius !== '0px') ||
                                (cs.boxShadow && cs.boxShadow !== 'none') ||
                                cs.display === 'flex' || cs.display === 'grid' ||
                            (cs.padding && cs.padding !== '0px') ||
                            // Color/font are how a compact designed widget actually looks
                            // styled. Sentinel's public page hydrates 15 elements; 6 had
                            // padding/flex (40%) and the rest were painted only by
                            // `color: var(--text)` / Inter — below _MIN_STYLED_RATIO 0.45
                            // with a page that is visibly a product, not a 1996 document.
                            (cs.color && cs.color !== 'rgb(0, 0, 0)'
                                && cs.color !== 'rgba(0, 0, 0, 1)') ||
                            (cs.fontFamily && !/^(?:serif|sans-serif|monospace|Times)/i.test(cs.fontFamily));
                            if (painted) styled++;
                        }
                        return { total: els.length, styled };
                    }"""
                )
                out["styling"] = styled
                if isinstance(styled, dict) and styled.get("total", 0) >= _MIN_ELEMENTS_TO_JUDGE:
                    total = int(styled.get("total") or 0)
                    count = int(styled.get("styled") or 0)
                    ratio = count / total if total else 1.0
                    out["styled_ratio"] = round(ratio, 2)
                    if ratio < _MIN_STYLED_RATIO:
                        issues.append(
                            f"live_unstyled_page:{url}: only {count} of "
                            f"{total} elements ({int(ratio * 100)}%) have any non-default styling — no "
                            "background, border, radius, shadow, flex/grid or padding. The page is "
                            "rendering unstyled: the stylesheet the markup expects is not being "
                            "applied. Check that the classes used in the markup have rules behind "
                            "them (and that any utility framework the markup assumes is actually "
                            "installed and configured)."
                        )

                # The page load may touch no API at all — this product waits for input before it
                # calls anything, which is why a completely dead backend passed a green browser
                # gate. So ask the deployment directly.
                api_paths = ("/api/health", "/api/healthz", "/openapi.json", "/api")
                api_alive = None
                for path in api_paths:
                    try:
                        resp = page.request.get(url.rstrip("/") + path, timeout=20_000)
                        status = int(resp.status)
                        body = ""
                        try:
                            body = (resp.text() or "")[:300]
                        except Exception:
                            body = ""
                        crashed = (
                            "FUNCTION_INVOCATION_FAILED" in body
                            or "A server error has occurred" in body
                        )
                        if 200 <= status < 500 and not crashed:
                            api_alive = f"{path} -> {status}"
                            break
                        if status >= 500 or crashed:
                            api_alive = False
                            issues.append(
                                f"live_api_dead:{path}:{status} on the DEPLOYED site"
                                + (f" — {body.strip()[:160]}" if body.strip() else "")
                                + ". The page is static build output and renders regardless; the "
                                "backend behind it does not run. A dependency present in the "
                                "preview venv and absent from the deployment fails exactly here, "
                                "and every feature of the product is unreachable."
                            )
                            break
                    except Exception:
                        continue
                out["api"] = api_alive

                # Full UI of the deployed app: every React-Router route from source, every form
                # (lat/lon filled, login filled), every visible button. A gate that only clicks
                # the primary CTA on an empty required form certifies nothing — HTML5 validation
                # swallows the click and the TypeError behind Get Safety Status never runs.
                seed_urls = [origin]
                if code_dir is not None:
                    seed_urls.extend(
                        urljoin(origin + "/", route.lstrip("/"))
                        for route in spa_routes_from_source(code_dir)
                    )
                crawl = run_deep_crawl(
                    page,
                    base_origin=origin,
                    start_url=origin + "/",
                    screenshot_dir=None,
                    max_pages=24,
                    max_depth=6,
                    per_nav_timeout_ms=18_000,
                    max_forms_per_page=4,
                    max_button_clicks_per_page=10,
                    seed_urls=seed_urls,
                )
                out["ui_crawl"] = {
                    "pages_visited": crawl.get("pages_visited"),
                    "visited_unique": crawl.get("visited_unique"),
                    "pages": [
                        {
                            "url": p.get("url"),
                            "status": p.get("status"),
                            "text_snippet": (p.get("text_snippet") or "")[:400],
                        }
                        for p in (crawl.get("pages") or [])[:24]
                    ],
                }
                issues.extend(deep_crawl_gate_issues(crawl))
                for p in crawl.get("pages") or []:
                    snippet = str(p.get("text_snippet") or "")
                    hit = exception_in_product_output(snippet)
                    if hit:
                        issues.append(
                            _issue_for_exception(
                                where=str(p.get("url") or "/"),
                                status=int(p.get("status") or 200),
                                hit=hit,
                                body=snippet,
                            )
                        )

                for fr in failed_requests[:8]:
                    status = int(fr.get("status") or 0)
                    path = str(fr.get("path") or "")
                    body = str(fr.get("body") or "")
                    # Crawling /#/operator before the login form is submitted fires
                    # protected /api/* calls that 401. That is not a deploy defect — but the
                    # excuse only holds for a path the crawl went on to load successfully.
                    # Excusing every 401 because *login* returned a token is how a dashboard
                    # that 401s on every request shipped green: the sweep's token proved the
                    # endpoint works on one warm instance, not that the visitor's session does.
                    if status in (401, 403) and path.startswith("/api/") and path in ok_paths:
                        continue
                    if _is_demo_auth_failure(status, path, body):
                        issues.append(_issue_for_demo_auth(where=path, status=status, body=body))
                        continue
                    issues.append(
                        f"live_http_{status}:{fr.get('method')} {path}:{status} on the "
                        "DEPLOYED site. This is production, not the sandbox: a dependency that "
                        "exists in the preview venv and not in the deployment fails exactly here."
                    )
                for ce in console_errors[:6]:
                    low = ce.lower()
                    if "401" in low or "unauthorized" in low:
                        sweep = out.get("api_sweep") or {}
                        login_ok = any(
                            isinstance(a, dict)
                            and a.get("token")
                            and int(a.get("status") or 0) == 200
                            for a in (sweep.get("login_attempts") or [])
                        )
                        # A console 401 carries no path to correlate, so the excuse rests on the
                        # session being durable. If the durability probe saw one identity per
                        # login and no rejected replay, a pre-login 401 is crawler noise.
                        durability = sweep.get("session_durability") or {}
                        durable = (
                            int(durability.get("distinct_subjects") or 1) <= 1
                            and not (durability.get("replay_failures") or [])
                        )
                        if login_ok and durable:
                            continue
                    issues.append(f"live_console_error: {ce}")
            finally:
                browser.close()
    except Exception as exc:
        out["skipped"] = True
        out["reason"] = f"browser_error:{str(exc)[:200]}"
        return out

    # Dedup: the same TypeError is reported from the HTTP sweep, the response listener, and the
    # crawl snippet. One finding is the instruction; three copies bury the file names.
    seen: set[str] = set()
    compact: list[str] = []
    for item in issues:
        key = item[:220]
        if key in seen:
            continue
        seen.add(key)
        compact.append(item)
    out["issues"] = compact
    out["failed_requests"] = failed_requests[:12]
    out["console_errors"] = console_errors[:12]
    out["json_bodies"] = json_bodies[:12]
    out["repair_scope"] = _repair_scope_from_issues(compact, code_dir)
    out["passed"] = not compact
    return out


def vercel_publish_failure_as_live_gate(
    *,
    product_id: str,
    exit_code: int | None = None,
    stderr: str = "",
    stdout: str = "",
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A Vercel CLI / requirements parse failure is the same class of defect as a live UI fail.

    The sandbox can still be green: preview used to install requirements line-by-line. The
    public --prod cannot. Without this payload the executor sees live_gate={} and walks to
    COMPLETED with vercel.ok: false.
    """
    bundle = bundle or {}
    blob = f"{stderr or ''}\n{stdout or ''}"
    issues: list[str] = []
    repair_scope: list[str] = []
    for raw in bundle.get("invalid_requirements") or []:
        issues.append(f"invalid_requirement:{raw}")
        repair_scope.append("backend/requirements.txt")
        repair_scope.append("requirements.txt")
    compact_err = ""
    for line in blob.splitlines():
        if "could not parse" in line.lower() or "couldn't parse" in line.lower():
            compact_err = line.strip()
            break
        if "error:" in line.lower() and "requirement" in line.lower():
            compact_err = line.strip()
            break
    if compact_err:
        issues.append(f"vercel_build_failed: {compact_err[:240]}")
        repair_scope.extend(["backend/requirements.txt", "requirements.txt"])
    elif exit_code not in (None, 0):
        tail = (stderr or stdout or "").strip().splitlines()
        last = next((ln.strip() for ln in reversed(tail) if ln.strip()), f"exit {exit_code}")
        issues.append(f"vercel_build_failed: exit {exit_code}: {last[:240]}")
        if "requirement" in blob.lower():
            repair_scope.extend(["backend/requirements.txt", "requirements.txt"])
    if not issues:
        issues.append("vercel_build_failed: production deploy did not publish")

    try:
        from core.paths import data_root

        code_dir = Path(data_root()) / "code" / product_id
        if code_dir.is_dir():
            from web.backend.services.requirements_manifest import iter_requirement_files

            for p in iter_requirement_files(code_dir):
                try:
                    rel = p.relative_to(code_dir).as_posix()
                except ValueError:
                    rel = p.name
                if rel not in repair_scope:
                    repair_scope.append(rel)
    except Exception:
        pass

    seen: set[str] = set()
    scope: list[str] = []
    for item in repair_scope:
        if item and item not in seen:
            seen.add(item)
            scope.append(item)

    return {
        "passed": False,
        "skipped": False,
        "source": "vercel_publish",
        "issues": issues[:12],
        "repair_scope": scope[:8],
        "exit_code": exit_code,
        "stderr_tail": (stderr or "")[-2000:],
    }


def live_gate_quality_feedback(live_gate: dict[str, Any]) -> dict[str, Any]:
    """The payload the developer agent already knows how to read."""
    issues = [str(i) for i in (live_gate.get("issues") or [])]
    return {
        "passed": False,
        "blocking_defects": issues,
        "repair_scope": list(live_gate.get("repair_scope") or []),
        "live_gate": live_gate,
        "reasons": issues,
    }


def live_gate_dev_fixing_task(product_id: str, product: dict[str, Any], live_gate: dict[str, Any]) -> dict[str, Any]:
    """A DEV_FIXING task whose findings name the Vercel UI failure, not a sandbox 401.

    Payment/escrow ops failures are not code defects — mark them so developer does
    not thrash bcrypt/security.py while Hub returns ``not open on chain``.
    """
    qg = live_gate_quality_feedback(live_gate)
    issues = [str(i) for i in (qg.get("blocking_defects") or [])]
    payment_ops = live_gate_is_payment_ops(live_gate, issues)
    findings = [{"severity": "critical", "title": issue, "detail": issue} for issue in issues[:20]]
    if payment_ops:
        findings.insert(
            0,
            {
                "severity": "critical",
                "title": "live_mesh_payment_ops: reopen on-chain escrow (not a Python dep fix)",
                "detail": (
                    "Hub refused paid mesh because the product escrow channel is not Open. "
                    "Operator: scripts/reopen_product_escrow_channel.py <product_id> then republish. "
                    "Do not rewrite bcrypt/security.py for this finding."
                ),
            },
        )
    return {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": product_id,
        "agent_type": "developer",
        "state": "DEV_FIXING",
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "input_data": {
            "product_id": product_id,
            "idea": product.get("idea", ""),
            "qa_findings": findings,
            "quality_gates_feedback": qg,
            "qa_gate_blocked": True,
            "live_gate_blocked": True,
            "live_mesh_payment_ops": payment_ops,
        },
        "created_at": time.time(),
        "priority": 5,
        "auto_requeue_reason": "live_deployment_gate",
    }


def apply_known_live_auth_fix(
    product_id: str,
    product: dict[str, Any],
    live_gate: dict[str, Any],
    *,
    data_root: str | None = None,
) -> list[str]:
    """Write known live-auth patches into the product tree. Empty → not this class, or already applied.

    Covers demo-login 401, Relay salt/cookie mismatch, and string-UUID vs SQLAlchemy
    UUID-column 500s. Source mismatch heals even when the live probe already looks green.
    """
    from core.paths import code_dir as resolve_code_dir
    from web.backend.services.vercel_fullstack_adapter import (
        apply_live_auth_autofix,
        relay_source_session_mismatch,
        relay_source_uuid_pk_mismatch,
        relay_source_pinned_mismatch,
    )

    root = resolve_code_dir(product_id, data_root=data_root) if data_root else resolve_code_dir(product_id)
    source_mismatch = (
        relay_source_session_mismatch(root)
        or relay_source_uuid_pk_mismatch(root)
        or relay_source_pinned_mismatch(root)
    )
    if live_gate_is_payment_ops(live_gate):
        return []
    if not live_gate_is_demo_auth(live_gate) and not source_mismatch:
        return []
    if product.get("live_auth_autofix_republished") and not source_mismatch:
        return []
    notes = apply_live_auth_autofix(root)
    if notes:
        product["live_auth_autofix"] = notes
        product["live_auth_autofix_at"] = time.time()
        logger.warning(
            "Live auth autofix wrote %s for %s (factory-owned, not Cursor)",
            ", ".join(notes[:8]),
            product_id,
        )
    return notes


def try_factory_live_auth_heal(
    product_id: str,
    product: dict[str, Any],
    live_gate: dict[str, Any],
    *,
    data_root: str | None = None,
) -> dict[str, Any]:
    """Factory-owned heal for the demo-auth 401 class: patch source, republish, re-gate.

    Returns healed=True when the new live gate passed. Cursor must not SSH-edit the product.
    """
    notes = apply_known_live_auth_fix(product_id, product, live_gate, data_root=data_root)
    if not notes:
        return {"healed": False, "applied": []}
    product["live_auth_autofix_republished"] = True
    from web.backend.services.auto_publish import try_publish_after_devops

    pub = try_publish_after_devops(product_id)
    lg = (pub or {}).get("live_gate") if isinstance(pub, dict) else None
    out: dict[str, Any] = {"healed": False, "applied": notes, "publish": pub}
    if isinstance(lg, dict):
        product["live_gate"] = lg
        out["live_gate"] = lg
        if lg.get("passed") or lg.get("skipped"):
            out["healed"] = True
            logger.warning(
                "Live auth autofix republished %s and the live gate passed (%s)",
                product_id,
                ", ".join(notes[:6]),
            )
            return out
    logger.warning(
        "Live auth autofix republished %s; live gate still failing → developer",
        product_id,
    )
    return out


def mark_product_live_gate_failed(product: dict[str, Any], live_gate: dict[str, Any]) -> None:
    product["state"] = "BUG_FOUND"
    product["live_gate"] = live_gate
    product["last_bug_context"] = {
        "source": "live_deployment_gate",
        "quality_gates_feedback": live_gate_quality_feedback(live_gate),
    }
    product["updated_at"] = time.time()


_VERCEL_INFRA_MARKERS = (
    "VERCEL_TOKEN not set",
    "vercel CLI not found",
    "provider_none",
    "disabled",
    "not_marketing_landing",
)


def _read_auto_publish_record(product_id: str) -> dict[str, Any]:
    if not product_id:
        return {}
    try:
        from core.paths import data_root

        path = Path(data_root()) / "state" / product_id / "auto_publish.json"
        if not path.is_file():
            return {}
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def live_gate_from_saved_vercel_record(product_id: str) -> dict[str, Any] | None:
    """A saved ``vercel.ok: false`` is a product defect, not a reason to stay COMPLETED.

    The live URL gate cannot see it: the previous production alias still answers 200
    while the new ``--prod`` died on ``requirements.txt``. DevOps already finished,
    so the in-loop live_gate_failed flag is gone. This reads the publish receipt.
    """
    doc = _read_auto_publish_record(product_id)
    vercel = doc.get("vercel")
    if not isinstance(vercel, dict):
        return None
    if vercel.get("ok") is True:
        return None
    if vercel.get("skipped"):
        return None
    blob = " ".join(
        str(x) for x in (vercel.get("error"), doc.get("error"), vercel.get("stderr_tail")) if x
    )
    if any(m.lower() in blob.lower() for m in _VERCEL_INFRA_MARKERS):
        return None
    existing = vercel.get("live_gate")
    if isinstance(existing, dict) and existing.get("passed") is False and not existing.get("skipped"):
        return existing
    evidence = (
        vercel.get("exit_code") not in (None, 0)
        or bool(vercel.get("invalid_requirements") or (vercel.get("bundle") or {}).get("invalid_requirements"))
        or "could not parse" in blob.lower()
        or "couldn't parse" in blob.lower()
        or str(vercel.get("error") or "") == "invalid_requirements"
    )
    if not evidence:
        return None
    bundle = vercel.get("bundle") if isinstance(vercel.get("bundle"), dict) else {}
    if vercel.get("invalid_requirements") and "invalid_requirements" not in bundle:
        bundle = {**bundle, "invalid_requirements": vercel.get("invalid_requirements")}
    return vercel_publish_failure_as_live_gate(
        product_id=product_id,
        exit_code=vercel.get("exit_code") if isinstance(vercel.get("exit_code"), int) else None,
        stderr=str(vercel.get("stderr_tail") or ""),
        stdout=str(vercel.get("stdout_tail") or ""),
        bundle=bundle,
    )


def apply_vercel_publish_failure_to_snapshot(
    product_id: str,
    product: dict[str, Any],
    task_queue: list[dict[str, Any]],
) -> bool:
    """Reopen a COMPLETED product in the worker snapshot when Vercel --prod failed."""
    from core.agent_roles import is_developer_agent

    live_gate = live_gate_from_saved_vercel_record(product_id)
    if not live_gate:
        return False
    if live_gate_is_payment_ops(live_gate):
        park_product_live_mesh_payment_ops(product, live_gate)
        logger.warning(
            "Saved Vercel live gate is payment-ops for %s — parked HUMAN_REVIEW, no developer",
            product_id,
        )
        return True
    if any(
        t.get("product_id") == product_id
        and is_developer_agent(t.get("agent_type"))
        and str(t.get("state") or "").upper() == "DEV_FIXING"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        mark_product_live_gate_failed(product, live_gate)
        return True
    heal = try_factory_live_auth_heal(product_id, product, live_gate)
    if heal.get("healed"):
        logger.warning(
            "Saved Vercel demo-auth for %s healed by factory autofix+republish",
            product_id,
        )
        return True
    mark_product_live_gate_failed(product, live_gate)
    task_queue.append(live_gate_dev_fixing_task(product_id, product, live_gate))
    logger.warning(
        "Saved Vercel publish failure returned %s to DEV_FIXING (%s)",
        product_id,
        "; ".join(str(i)[:100] for i in (live_gate.get("issues") or [])[:2]),
    )
    return True


def enqueue_repair_from_live_gate(product_id: str, live_gate: dict[str, Any]) -> dict[str, Any]:
    """Send an already-published product back to DEV_FIXING. COMPLETED is allowed.

    DevOps only runs the live gate once. A TypeError that shipped sits on Vercel forever
    unless something can reopen a COMPLETED product — reopen_failed_product refuses
    anything that is not FAILED.
    """
    if live_gate.get("skipped") or live_gate.get("passed") is not False:
        return {"ok": False, "reason": "live_gate_did_not_fail"}

    from core.paths import pipeline_db_path
    from core.agent_roles import is_developer_agent

    pid = product_id.strip()
    from orchestrator.sqlite_manager import SQLiteManager

    db = pipeline_db_path()
    if db.is_file():
        sm = SQLiteManager(str(db))
        sm.connect()
        try:
            product = sm.get_product(pid)
            if not product:
                return {"ok": False, "reason": "product_not_found"}
            if live_gate_is_payment_ops(live_gate):
                park_product_live_mesh_payment_ops(product, live_gate)
                sm.upsert_product(product)
                return {
                    "ok": True,
                    "parked": True,
                    "product_state": "HUMAN_REVIEW_PENDING",
                    "reason": "live_mesh_payment_ops",
                }
            tasks = sm.get_tasks_by_product(pid)
            if any(
                is_developer_agent(t.get("agent_type"))
                and str(t.get("state") or "").upper() == "DEV_FIXING"
                and str(t.get("status") or "").lower() in ("pending", "running")
                for t in tasks
            ):
                mark_product_live_gate_failed(product, live_gate)
                sm.upsert_product(product)
                return {"ok": True, "recovery_already_pending": True, "product_state": "BUG_FOUND"}
            heal = try_factory_live_auth_heal(pid, product, live_gate)
            if heal.get("healed"):
                sm.upsert_product(product)
                return {
                    "ok": True,
                    "healed": True,
                    "autofix": heal.get("applied") or [],
                    "product_state": str(product.get("state") or ""),
                }
            mark_product_live_gate_failed(product, live_gate)
            task = live_gate_dev_fixing_task(pid, product, live_gate)
            sm.upsert_product(product)
            sm.upsert_task(task)
            logger.warning(
                "Live Vercel gate returned %s to DEV_FIXING (%s)",
                pid,
                "; ".join(str(i)[:100] for i in (live_gate.get("issues") or [])[:2]),
            )
            return {"ok": True, "task_id": task["id"], "product_state": "BUG_FOUND"}
        finally:
            sm.close()

    from core.pipeline_state_writer import read_pipeline_state, write_pipeline_state

    data = read_pipeline_state()
    products = data.get("products") or {}
    task_queue = data.get("task_queue") or []
    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}
    if live_gate_is_payment_ops(live_gate):
        park_product_live_mesh_payment_ops(product, live_gate)
        write_pipeline_state(data)
        return {
            "ok": True,
            "parked": True,
            "product_state": "HUMAN_REVIEW_PENDING",
            "reason": "live_mesh_payment_ops",
        }
    if any(
        t.get("product_id") == pid
        and is_developer_agent(t.get("agent_type"))
        and str(t.get("state") or "").upper() == "DEV_FIXING"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        mark_product_live_gate_failed(product, live_gate)
        write_pipeline_state(data)
        return {"ok": True, "recovery_already_pending": True, "product_state": "BUG_FOUND"}
    heal = try_factory_live_auth_heal(pid, product, live_gate)
    if heal.get("healed"):
        write_pipeline_state(data)
        return {
            "ok": True,
            "healed": True,
            "autofix": heal.get("applied") or [],
            "product_state": str(product.get("state") or ""),
        }
    mark_product_live_gate_failed(product, live_gate)
    task = live_gate_dev_fixing_task(pid, product, live_gate)
    task_queue.append(task)
    data["task_queue"] = task_queue
    write_pipeline_state(data)
    return {"ok": True, "task_id": task["id"], "product_state": "BUG_FOUND"}


def recheck_published_live_ui(product_id: str, url: str) -> dict[str, Any]:
    """Run the full Vercel UI gate against an existing URL and reopen on failure."""
    live_gate = check_live_deployment(url, product_id=product_id)
    out: dict[str, Any] = {"live_gate": live_gate}
    if live_gate.get("skipped") or live_gate.get("passed"):
        out["ok"] = True
        out["repaired"] = False
        return out
    enq = enqueue_repair_from_live_gate(product_id, live_gate)
    out.update(enq)
    out["repaired"] = bool(enq.get("ok"))
    return out

