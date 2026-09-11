"""
Authenticated demo journey: does the product actually work when someone logs in?

The existing runtime gate boots the app and probes ``/health`` plus one route
*unauthenticated*. That is enough to prove the process starts and nothing more —
a product whose every business endpoint returns HTTP 500 behind auth passes it
cleanly. Two real defects shipped through that hole in the same build:

  * login returned 500 because the seeded demo address used a reserved TLD;
  * ``GET /api/v1/accounts`` returned 500 on a UUID/str column mismatch.

Both are invisible without credentials, and both are the first thing a reviewer
hits. This module logs in with the demo identity the factory itself seeds, then
sweeps every GET endpoint — filling required parameters from the OpenAPI schema, so the
app is asked to do its job rather than merely to refuse — and reports anything that 5xxes.

It reuses the sandbox preview machinery (``start_fastapi_preview``) so the app
boots the same way the live preview boots — right interpreter, right venv, right
environment — instead of guessing an entrypoint.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Endpoints that are destructive or slow enough to be worth skipping in a smoke pass.
_SKIP_PATH_MARKERS = ("/export", "/download", "/push-", "/webhook", "/stream")


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _call(
    method: str,
    url: str,
    *,
    token: str = "",
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, str] | None = None,
    timeout: float = 10.0,
    max_body: int = 4000,
) -> tuple[int, str]:
    data = None
    headers: dict[str, str] = {"Accept": "application/json"}
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urlencode(form_body).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url=url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            return int(getattr(r, "status", 200)), body[:max_body]
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            pass
        return int(getattr(e, "code", 500)), body
    except (URLError, TimeoutError, OSError) as e:
        return 0, str(e)[:400]


OPENAPI_CANDIDATES = (
    "/openapi.json",
    "/api/openapi.json",
    "/api/v1/openapi.json",
    "/api/v2/openapi.json",
)


def wait_until_ready(base: str, timeout_sec: float = 60.0) -> bool:
    """uvicorn binds the port before startup hooks finish (migrations, seeding).

    Probing too early yields a hung socket and an empty route table, so poll a
    cheap endpoint until the app answers.
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        for path in (*OPENAPI_CANDIDATES, "/api/health", "/health"):
            status, _ = _call("GET", f"{base}{path}", timeout=5.0)
            if 200 <= status < 500:
                return True
        time.sleep(1.0)
    return False


def _openapi(base: str) -> dict[str, Any]:
    # Generated apps often relocate the schema (`openapi_url=f"{API_V1_STR}/openapi.json"`),
    # and a real product's schema runs well past any smoke-test body cap.
    for path in OPENAPI_CANDIDATES:
        status, body = _call("GET", f"{base}{path}", timeout=20.0, max_body=4_000_000)
        if status != 200:
            continue
        try:
            doc = json.loads(body)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("paths"):
            return doc
    return {}


def _find_login_paths(paths: dict[str, Any]) -> list[str]:
    out = []
    for path, ops in paths.items():
        if not isinstance(ops, dict) or "post" not in ops:
            continue
        low = path.lower()
        if "login" in low or "signin" in low or low.endswith("/token"):
            out.append(path)
    return sorted(out, key=lambda p: (0 if "auth" in p.lower() else 1, len(p)))


def _extract_token(body: str) -> str:
    try:
        doc = json.loads(body)
    except ValueError:
        return ""
    if not isinstance(doc, dict):
        return ""
    for key in ("access_token", "accessToken", "token", "jwt"):
        val = doc.get(key)
        if isinstance(val, str) and val:
            return val
    inner = doc.get("data")
    if isinstance(inner, dict):
        return _extract_token(json.dumps(inner))
    return ""


def attempt_login(base: str, path: str, email: str, password: str) -> tuple[str, dict[str, Any]]:
    """Try the shapes generated auth endpoints actually use. Returns (token, trace)."""
    attempts: list[dict[str, Any]] = []
    payloads = [
        ("form", {"username": email, "password": password}),
        ("json_email", {"email": email, "password": password}),
        ("json_username", {"username": email, "password": password}),
    ]
    for kind, payload in payloads:
        if kind == "form":
            status, body = _call("POST", f"{base}{path}", form_body=payload)
        else:
            status, body = _call("POST", f"{base}{path}", json_body=payload)
        token = _extract_token(body) if status < 300 else ""
        attempts.append({"kind": kind, "status": status, "token": bool(token), "body": body[:300]})
        if token:
            return token, {"path": path, "attempts": attempts}
    return "", {"path": path, "attempts": attempts}


# Plausible values for a required query parameter, so an endpoint is actually exercised
# instead of being asked to refuse. Skipping parameterised endpoints was a blind spot with a
# measurable cost: a weather product's ONLY public feature is GET /api/advisory?lat=&lon=, this
# sweep called it bare, recorded the 422 for the missing arguments as "correct", and the real
# call was never made. That call raises `TypeError: get_advisory() missing 1 required
# positional argument: 'request'` and returns 500 — a defect that survived roughly ninety
# repair rounds because nothing ever asked the product to do its job.
_GEO_HINTS = {
    # Berlin: somewhere every hazard and weather feed actually has readings, so an empty
    # answer means a real defect rather than a blank spot on the map.
    "lat": 52.52, "latitude": 52.52,
    "lon": 13.40, "lng": 13.40, "longitude": 13.40,
}


def _sample_query_value(param: dict[str, Any]) -> Any:
    """A value the endpoint should accept, derived from its own declared schema."""
    name = str(param.get("name") or "").lower()
    schema = param.get("schema") if isinstance(param.get("schema"), dict) else {}
    if schema.get("enum"):
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]
    if name in _GEO_HINTS:
        return _GEO_HINTS[name]
    kind = str(schema.get("type") or "").lower()
    if kind in ("number", "integer"):
        # Respect a declared range rather than sending 1 into a min/max the app enforces.
        lo, hi = schema.get("minimum"), schema.get("maximum")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            mid = (lo + hi) / 2
            return int(mid) if kind == "integer" else mid
        if isinstance(lo, (int, float)):
            return lo
        return 1
    if kind == "boolean":
        return "false"
    if kind == "array":
        return ""
    return "test"


def _required_query(op: dict[str, Any]) -> dict[str, Any]:
    """Required query parameters filled from the schema; empty when there are none."""
    out: dict[str, Any] = {}
    params = op.get("parameters")
    if not isinstance(params, list):
        return out
    for param in params:
        if not isinstance(param, dict) or param.get("in") != "query":
            continue
        if not param.get("required"):
            continue
        name = str(param.get("name") or "").strip()
        if name:
            out[name] = _sample_query_value(param)
    return out


def sweep_get_endpoints(
    base: str,
    paths: dict[str, Any],
    token: str,
    *,
    limit: int = 25,
) -> tuple[list[dict[str, Any]], list[str]]:
    """GET every parameterless endpoint with the demo token; collect 5xx as issues."""
    from web.backend.services.browser_e2e_deep import exception_in_product_output

    results: list[dict[str, Any]] = []
    issues: list[str] = []
    checked = 0
    for path in sorted(paths):
        if checked >= limit:
            break
        ops = paths[path]
        if not isinstance(ops, dict) or "get" not in ops:
            continue
        if "{" in path:
            continue
        low = path.lower()
        if any(marker in low for marker in _SKIP_PATH_MARKERS):
            continue
        if low in ("/openapi.json", "/docs", "/redoc"):
            continue
        # Satisfy the endpoint's own declared required parameters. Calling it bare only proves
        # it can say no, and a product whose single feature needs lat/lon then passes this
        # sweep while 500ing on every real request.
        get_op = ops.get("get") if isinstance(ops.get("get"), dict) else {}
        query = _required_query(get_op)
        url = f"{base}{path}"
        if query:
            url += "?" + urlencode(query)
        status, body = _call("GET", url, token=token)
        checked += 1
        results.append({"path": path, "status": status, "query": query or None})
        leak = exception_in_product_output(body)
        if status == 0:
            issues.append(f"demo_journey_unreachable:{path}:{body[:120]}")
        elif status >= 500:
            issues.append(f"demo_journey_5xx:{path}:{status}:{body[:200]}")
        elif leak:
            # 200 with a TypeError in the JSON is the honesty-policy trap: Sentinel answered
            # UNKNOWN forever because except Exception swallowed
            # get_situation_brief(west=...) vs (lat, lon).
            issues.append(
                f"demo_journey_exception_in_200:{path}:{status}:{leak}. "
                "The product answered 200 with a Python exception in the body. Fix the call "
                "to match the method signature; do not wrap TypeError as UNKNOWN."
            )
        elif status in (401, 403) and token:
            # Say HOW this client authenticates, or the rounds guess. Measured: six rounds
            # flip-flopped the analytics/operator routers between cookie-only auth and
            # Bearer-header auth, each undoing the previous, because the finding named the 401
            # and nothing else. This journey logs in, takes access_token from the response BODY,
            # and sends it as "Authorization: Bearer <token>" — it holds no cookie jar at all.
            issues.append(
                f"demo_journey_auth_rejected:{path}:{status}: the endpoint refused the token "
                "obtained from the login response. This client authenticates ONLY via the "
                "'Authorization: Bearer <access_token>' header (it does not keep cookies), so "
                "the route's auth dependency must accept that header — read it FIRST, and fall "
                "back to the session cookie for browser use. Do not remove cookie support; add "
                "header support alongside it, in ONE shared dependency used by every protected "
                "route, so the routers stop alternating between the two."
            )
        elif status == 422 and query:
            # The app rejected values built from its OWN schema, so either the schema lies or
            # the validation does. Either way a caller following the documented contract is
            # refused, which is a defect rather than correct strictness.
            issues.append(
                f"demo_journey_rejects_own_schema:{path}:{status}:sent={query} body={body[:150]}"
            )
    return results, issues


# Imports every module of the product package and reports each distinct failure.
# Importing only the app entrypoint stops at the first bad module, so a build with
# five broken files needs five QA rounds (and five LLM repair cycles) to surface
# them one at a time. This sweeps them in a single pass.
_IMPORT_SWEEP = r'''
import importlib, json, os, sys, traceback

root = os.getcwd()
SKIP = {"tests", "test", "node_modules", "__pycache__", ".venv", "venv",
        "preview-venv", ".aicom_sandbox", "alembic", "migrations", "site-packages"}

entry = sys.argv[1] if len(sys.argv) > 1 else ""
modules = []
if entry:
    modules.append(entry)
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
    for name in filenames:
        if not name.endswith(".py") or name == "__init__.py":
            continue
        rel = os.path.relpath(os.path.join(dirpath, name), root)
        mod = rel[:-3].replace(os.sep, ".")
        if mod not in modules:
            modules.append(mod)

failures = []
seen = set()
for mod in modules:
    try:
        importlib.import_module(mod)
    except BaseException as exc:
        tb = traceback.extract_tb(sys.exc_info()[2])
        frame = ""
        for f in reversed(tb):
            if root in (f.filename or ""):
                frame = "%s:%s" % (os.path.relpath(f.filename, root), f.lineno)
                break
        line = "%s: %s" % (type(exc).__name__, exc)
        key = (line[:160], frame)
        if key in seen:
            continue
        seen.add(key)
        failures.append({"module": mod, "error": line[:300], "where": frame})
    if len(failures) >= 12:
        break
print(json.dumps(failures))
'''


def import_failure_report(code_dir: Path, *, sandbox_id: str = "import-probe") -> list[str]:
    """Every module of the product that will not import, with file:line.

    A build that will not boot is the most common QA verdict and the least useful
    one, because the message stops at "port never opened". Importing in the same
    interpreter the preview uses recovers the real causes —
    ``NameError: name 'Boolean' is not defined  (app/models/source.py:16)``.
    """
    import subprocess
    import sys

    from web.backend.services.sandbox_preview_api import detect_fastapi_backend
    from web.backend.services.sandbox_preview_env import build_fastapi_preview_env

    info = detect_fastapi_backend(Path(code_dir))
    if not info:
        return []
    cwd = info["cwd"]
    module = str(info["module"]).split(":", 1)[0]
    try:
        # Same sandbox id as the failed boot → reuses that prepared venv and its
        # SQLite fallback URL. Probing with the factory's own interpreter instead
        # would report a missing psycopg2 rather than the product's actual defect.
        env, prep = build_fastapi_preview_env(
            sandbox_id=sandbox_id,
            code_dir=Path(code_dir),
            cwd=cwd,
            skip_heavy_setup=False,
        )
        python = prep.get("preview_python") or sys.executable
        proc = subprocess.run(
            [str(python), "-c", _IMPORT_SWEEP, module],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except Exception as exc:
        return [f"import probe failed: {exc}"[:400]]

    try:
        failures = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return [tail[-1][:300]] if tail else []
    if not isinstance(failures, list):
        return []
    return [
        f"{f.get('error')}  ({f.get('where') or f.get('module')})"
        for f in failures
        if isinstance(f, dict)
    ]


def import_failure_reason(code_dir: Path, *, sandbox_id: str = "import-probe") -> str:
    """First import failure as one line (kept for callers wanting a short reason)."""
    report = import_failure_report(code_dir, sandbox_id=sandbox_id)
    return report[0] if report else ""



def tracebacks_from_stderr(text: str, limit: int = 3) -> list[str]:
    """Pull the exception lines out of a uvicorn stderr dump.

    "500: Internal Server Error" tells the agent an endpoint is broken and nothing
    about why — the same dead end "uvicorn_failed_to_listen" was. The server logged
    a traceback; it just never reached the finding.
    """
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith("Traceback (most recent call last)"):
            continue
        # The exception is the last non-frame line of the block.
        exception = ""
        for follow in lines[idx + 1 : idx + 60]:
            if follow.startswith((" ", "\t")):
                continue  # frame line or source echo
            stripped = follow.strip()
            if not stripped or stripped.startswith(("File \"", "^")):
                continue
            if stripped.startswith(("Traceback", "During handling", "The above")):
                break
            if stripped.startswith(("INFO:", "WARNING:", "DEBUG:", "ERROR:")):
                break  # the traceback ended before this log line
            exception = stripped
            break  # first unindented non-frame line IS the exception
        if exception and exception not in seen:
            seen.add(exception)
            out.append(exception[:400])
        if len(out) >= limit:
            break
    return out


def run_demo_journey(product_id: str, data_root: str | Path | None = None) -> dict[str, Any]:
    """Boot the product, log in as the demo user, and exercise its read endpoints."""
    if not _truthy("AIFACTORY_DEMO_JOURNEY_E2E", "1"):
        return {"passed": True, "skipped": True, "reason": "disabled"}

    from core.demo_identity import sandbox_demo_email
    from core.paths import code_dir as resolve_code_dir
    from core.paths import resolve_data_root
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose
    from web.backend.services.sandbox_preview_api import (
        detect_fastapi_backend,
        start_fastapi_preview,
        terminate_preview_process,
    )

    root = resolve_data_root(data_root)
    product_code = resolve_code_dir(product_id, data_root=root)
    if not product_code.is_dir():
        return {"passed": True, "skipped": True, "reason": "no_code_dir"}
    if detect_fastapi_backend(product_code) is None:
        return {"passed": True, "skipped": True, "reason": "no_fastapi_entry"}

    # Stable per product, not per run. A fresh id each round built a fresh preview
    # venv each round: 74 of them, ~14 GB, on two products in one afternoon — and it
    # reinstalled every dependency before each check. Reusing the directory keeps the
    # gate fast and the disk finite.
    sandbox_id = f"journey-{product_id}"
    try:
        from web.backend.services.sandbox_preview_env import reset_stale_demo_sqlite

        wiped = reset_stale_demo_sqlite(product_code, sandbox_id)
        if wiped:
            logger.info("demo journey %s: wiped stale sqlite %s", product_id, wiped)
    except Exception:
        logger.debug("demo journey sqlite reset skipped", exc_info=True)
    started = time.time()
    port, proc, status = start_fastapi_preview(sandbox_id=sandbox_id, code_dir=product_code)
    if not port:
        # "uvicorn failed to listen" tells a developer nothing. Import every module
        # and hand back all the real exceptions with file:line, so one repair round
        # can fix all of them instead of peeling them off one per QA cycle.
        failures = import_failure_report(product_code, sandbox_id=sandbox_id)
        issues = [f"demo_journey_boot_failed:{status}"]
        issues += [f"import_error: {line}" for line in failures]
        return {
            "passed": False,
            "skipped": False,
            "issues": issues,
            "boot_status": status,
            "import_errors": failures,
        }

    base = f"http://127.0.0.1:{int(port)}"
    email = sandbox_demo_email()
    password = effective_sandbox_demo_password_for_compose()
    report: dict[str, Any] = {
        "skipped": False,
        "base_url": base,
        "demo_email": email,
        "boot_status": status,
    }
    issues: list[str] = []
    # Probed BEFORE the endpoint sweep, so an endpoint that times out on a dead dependency can
    # be reported as a consequence rather than as its own defect. See the block at the bottom of
    # this module for the 38 reverted rounds this exists to end.
    try:
        report["external_unreachable"] = probe_external_dependencies(
            Path(product_code), own_port=int(port)
        )
        if report["external_unreachable"]:
            logger.warning(
                "demo journey: %s declares %d external base URL(s) that do not answer: %s",
                product_id,
                len(report["external_unreachable"]),
                ", ".join(f"{d['url']} ({d['source']})" for d in report["external_unreachable"]),
            )
    except Exception as exc:
        logger.debug("demo journey: external dependency probe failed: %s", exc)
        report["external_unreachable"] = []
    try:
        ready = wait_until_ready(base, timeout_sec=_env_float("AIFACTORY_DEMO_JOURNEY_READY_SEC", 90.0))
        report["ready"] = ready
        doc = _openapi(base) if ready else {}
        paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
        report["openapi_path_count"] = len(paths)
        if not ready:
            issues.append("demo_journey_never_became_ready")
        elif not paths:
            issues.append("demo_journey_no_openapi")

        login_paths = _find_login_paths(paths)
        report["login_paths"] = login_paths
        token = ""
        if login_paths:
            token, trace = attempt_login(base, login_paths[0], email, password)
            report["login"] = trace
            if not token:
                statuses = [a.get("status") for a in trace.get("attempts", [])]
                # Two different defects hide behind "no token", and the message must not conflate
                # them. Measured: the login came to answer 200 with body {"message":"ok"} — no token,
                # no session — and the issue still read `statuses=[200, 422, 422]`, which points at
                # the STATUS, which was fine. The round needed to be pointed at the response body.
                ok_attempt = next(
                    (a for a in trace.get("attempts", []) if (a.get("status") or 599) < 300),
                    None,
                )
                if ok_attempt:
                    issues.append(
                        f"demo_login_no_token:{login_paths[0]}: login answered "
                        f"{ok_attempt.get('status')} but the response body carries no token "
                        f"(body={str(ok_attempt.get('body'))[:120]!r}). The client cannot "
                        "authenticate any subsequent request. Return an access token in the "
                        "response body (e.g. {\"access_token\": ..., \"token_type\": "
                        "\"bearer\"}) — do not change the status code, it is already correct. "
                        "IMPORTANT: if the route declares response_model=..., FastAPI silently "
                        "strips every field that model does not declare — so the fix is TWO "
                        "edits: add the fields to the return AND declare access_token/token_type "
                        "on the response model class. Editing only the handler changes nothing "
                        "observable."
                    )
                else:
                    issues.append(
                        f"demo_login_failed:{login_paths[0]}:statuses={statuses} "
                        f"(seeded demo user {email} must be able to sign in)"
                    )
        else:
            report["login"] = {"skipped": "no_login_endpoint"}

        results, sweep_issues = sweep_get_endpoints(base, paths, token)
        report["endpoints"] = results
        issues.extend(sweep_issues)

        # A 5xx without its traceback is unfixable feedback. The app logged one;
        # read it off the preview process before the process goes away.
        if any("demo_journey_5xx" in str(i) for i in sweep_issues):
            stderr_text = ""
            try:
                terminate_preview_process(proc)
                if proc is not None and proc.stderr is not None:
                    stderr_text = proc.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                stderr_text = ""
            proc = None
            traces = tracebacks_from_stderr(stderr_text)
            if traces:
                report["server_tracebacks"] = traces
                issues.append(
                    "demo_journey_5xx_cause: " + " | ".join(traces)
                )
    finally:
        terminate_preview_process(proc)

    report["issues"] = issues
    report["passed"] = not issues
    report["elapsed_sec"] = round(time.time() - started, 2)
    return report


# ── External dependencies the sandbox cannot reach ───────────────────────────────────────────
# Sentinel (prod-bdb1634806de) spent 38 reverted rounds and 12 days here, and the mechanism was
# this: its advisory endpoint is supposed to call ATLAS, and the product carried two different
# addresses for it —
#
#   backend/app/services/aimarket_participant.py:29   DEFAULT_ATLAS = "https://atlas.modelmarket.dev"
#   backend/app/config.py:9                           atlas_base_url = "http://localhost:8001"
#
# Nothing listens on localhost:8001 in the sandbox. So every round that restored the real call
# produced `demo_journey_unreachable:/api/advisory:timed out`, which scored as a regression
# (9 -> 12, weight 3 for one high finding — the arithmetic matches exactly), and the guard threw
# the round away. The ONLY edit that made the gate green was replacing the call with a static
# placeholder, which is what the developer eventually did: it silenced the finding and deleted
# the product's reason to exist. The pipeline was not failing to fix a hard bug; it was actively
# selecting for the wrong fix, because a timeout caused by a dead dependency is scored the same
# as a hung handler.
#
# So: probe the addresses the product itself declares. An unreachable one is a CONFIG defect
# with a file and a line — fixable in one round — and while it stands, the endpoint timeouts it
# causes must not vote on the revert.
_CONFIG_FILES = (
    "config.py", "settings.py", ".env", ".env.example", ".env.local",
    "app/config.py", "app/settings.py", "app/core/config.py",
    "backend/app/config.py", "backend/app/settings.py", "backend/app/core/config.py",
    "backend/.env", "backend/.env.example",
)
# Loopback ports belonging to the product itself are not external dependencies — the journey
# boots the app and talks to it there. Only OTHER loopback ports are suspicious.
_URL_RE = None


def _declared_external_urls(code_dir: Path, own_port: int | None = None) -> list[dict[str, Any]]:
    """``[{url, source}]`` for every http(s) base URL the product's config declares.

    Read out of config files rather than the running process: the point is to name the file and
    line a developer must edit, and a URL discovered at runtime cannot be pointed at.
    """
    import re

    global _URL_RE
    if _URL_RE is None:
        _URL_RE = re.compile(r"""https?://[^\s"'`,)\]}]+""")

    seen: dict[str, str] = {}
    for rel in _CONFIG_FILES:
        path = code_dir / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for raw in _URL_RE.findall(line):
                url = raw.rstrip(".,;")
                # Strip a path: only the base is probed, because a health path is a guess and a
                # 404 on one does not mean the service is down.
                try:
                    from urllib.parse import urlsplit

                    parts = urlsplit(url)
                    if not parts.hostname:
                        continue
                    if own_port and parts.port == own_port and parts.hostname in ("localhost", "127.0.0.1"):
                        continue
                    # A product's own public address is not a dependency on anything. Measured on
                    # Sentinel: `sentinel_public_url = "http://localhost:8000"` was reported
                    # alongside its two real dead dependencies, and a finding that names a
                    # non-problem next to two real ones is how a gate teaches people to skim it.
                    # Keyed on the setting name rather than the port, because the product's port
                    # inside the sandbox is not the port its config remembers.
                    key = line.split("=")[0].split(":")[0].strip().lower()
                    if parts.hostname in ("localhost", "127.0.0.1") and any(
                        marker in key
                        for marker in (
                            "public",
                            "self",
                            "site",
                            "own",
                            "callback",
                            # CORS / Vite allowlists name a browser origin, not a
                            # service the sandbox should GET. Relay's .env.example
                            # `CORS_ORIGIN=http://localhost:5173` is the comment's
                            # "leave blank in production" hint — probing it scored
                            # a high Config finding and parked the repair loop.
                            "cors",
                            "origin",
                            "vite",
                        )
                    ):
                        continue
                    base = f"{parts.scheme}://{parts.netloc}"
                except Exception:
                    continue
                seen.setdefault(base, f"{rel}:{lineno}")
    return [{"url": url, "source": src} for url, src in sorted(seen.items())]


def probe_external_dependencies(
    code_dir: Path, *, own_port: int | None = None, timeout: float = 6.0
) -> list[dict[str, Any]]:
    """Which declared external base URLs do not answer. Empty list means all of them do."""
    dead: list[dict[str, Any]] = []
    for entry in _declared_external_urls(Path(code_dir), own_port=own_port):
        status, body = _call("GET", entry["url"], timeout=timeout)
        # Any HTTP answer at all — including 404 — proves something is listening, which is all
        # this check claims. Only a transport failure counts as unreachable.
        if status == 0:
            dead.append({**entry, "detail": str(body)[:160]})
    return dead
