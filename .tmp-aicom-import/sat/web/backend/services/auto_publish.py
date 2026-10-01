"""
Auto-publish generated product code to a static host after the DevOps stage.

Reads toggles from ``general.auto_publish_*`` in ``/app/config.yaml`` (same as Admin → Settings).
Secrets **must** be supplied via environment variables — never commit tokens.

Supported providers:
  - ``vercel`` — requires ``VERCEL_TOKEN``; optional ``VERCEL_ORG_ID``, ``VERCEL_PROJECT_ID``
  - ``netlify`` — requires ``NETLIFY_AUTH_TOKEN``; optional ``NETLIFY_SITE_ID`` (otherwise draft URL)
  - ``cloudflare_pages`` — requires ``CLOUDFLARE_API_TOKEN``; ``general.auto_publish_cf_project_name`` + account

CLI tools must be on ``PATH`` inside the container/host (``vercel``, ``netlify``, ``wrangler``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.paths import config_path
from core.config_merge import load_merged_config
from core.paths import data_root

logger = logging.getLogger(__name__)

CONFIG_PATH = config_path()
_VERCEL_SECRET_FILE = "vercel_token"


def _vercel_token() -> str:
    tok = os.environ.get("VERCEL_TOKEN", "").strip()
    if tok:
        return tok
    p = Path(data_root()) / "secrets" / _VERCEL_SECRET_FILE
    try:
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def _which_vercel() -> str | None:
    found = shutil.which("vercel")
    if found:
        return found
    extra = Path(data_root()) / ".npm-global" / "bin" / "vercel"
    if extra.is_file():
        return str(extra)
    return None


_URL_RE = re.compile(r"https://[^\s\)]+\.vercel\.app[^\s\)]*", re.I)
_NETLIFY_URL_RE = re.compile(r"https://[^\s\)]+\.netlify\.app[^\s\)]*", re.I)
_CF_URL_RE = re.compile(r"https://[^\s\)]+\.pages\.dev[^\s\)]*", re.I)


def _read_general() -> dict[str, Any]:
    try:
        raw = load_merged_config(CONFIG_PATH)
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("auto_publish: could not read config: %s", e)
        return {}


def _product_delivery_profile(product_id: str) -> str:
    """Read delivery_profile from pipeline.json, SQLite extras, or specification.json."""
    import json
    import sqlite3

    from core.paths import pipeline_json_path

    try:
        pj = pipeline_json_path()
        if pj.is_file():
            doc = json.loads(pj.read_text(encoding="utf-8"))
            products = doc.get("products") if isinstance(doc, dict) else None
            if isinstance(products, dict):
                p = products.get(product_id)
                if isinstance(p, dict):
                    spec = p.get("specification") if isinstance(p.get("specification"), dict) else {}
                    raw = p.get("delivery_profile") or spec.get("delivery_profile") or ""
                    if raw:
                        return str(raw)
    except Exception as e:
        logger.debug("auto_publish: pipeline.json delivery_profile lookup failed for %s: %s", product_id, e)

    try:
        db = Path(data_root()) / "state" / "pipeline.db"
        if db.is_file():
            con = sqlite3.connect(str(db))
            try:
                row = con.execute(
                    "SELECT extras FROM products WHERE id = ?",
                    (product_id,),
                ).fetchone()
            finally:
                con.close()
            if row and row[0]:
                extras = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                if isinstance(extras, dict):
                    raw = extras.get("delivery_profile") or ""
                    if raw:
                        return str(raw)
    except Exception as e:
        logger.debug("auto_publish: sqlite delivery_profile lookup failed for %s: %s", product_id, e)

    try:
        spec_path = Path(data_root()) / "specs" / product_id / "specification.json"
        if spec_path.is_file():
            doc = json.loads(spec_path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                raw = doc.get("delivery_profile") or ""
                if raw:
                    return str(raw)
    except Exception as e:
        logger.debug("auto_publish: spec delivery_profile lookup failed for %s: %s", product_id, e)

    return ""


def _extract_url(stdout: str, stderr: str, provider: str) -> str | None:
    blob = f"{stdout}\n{stderr}"
    if provider == "vercel":
        m = _URL_RE.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
    if provider == "netlify":
        m = _NETLIFY_URL_RE.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
        for line in blob.splitlines():
            line = line.strip()
            if line.startswith("https://") and "netlify" in line:
                return line.split()[0].rstrip(".)'`\"")
    if provider == "cloudflare_pages":
        m = _CF_URL_RE.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
    for pat in (_URL_RE, _NETLIFY_URL_RE, _CF_URL_RE):
        m = pat.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
    return None


def verify_published_url(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Confirm a published URL is actually reachable by someone who is not us.

    A deploy that exits 0 and hands back a URL still is not published if the URL
    answers 302 to an SSO login. Vercel Deployment Protection does exactly that,
    account-wide, and every "published" product on this account was gated that way
    without the pipeline noticing.
    """
    import urllib.error
    import urllib.request

    out: dict[str, Any] = {"url": url, "reachable": False}
    if not url:
        out["reason"] = "no_url"
        return out

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            out["redirect_to"] = newurl
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
            out["status"] = int(getattr(r, "status", 200))
            out["reachable"] = 200 <= out["status"] < 400
            return out
    except urllib.error.HTTPError as e:
        out["status"] = int(getattr(e, "code", 0))
        target = out.get("redirect_to") or e.headers.get("location", "") if e.headers else ""
        out["redirect_to"] = target
        if target and any(tok in target for tok in ("sso-api", "vercel.com/login", "/sso?")):
            out["reason"] = "deployment_protection"
            out["detail"] = (
                "The deployment answers with an SSO redirect, so the link only works for "
                "someone signed into the hosting account. Turn off Deployment Protection "
                "for this project (or restrict it to preview deployments) to make it public."
            )
            return out
        # A plain in-app redirect (/ -> /login) is fine.
        out["reachable"] = 300 <= out["status"] < 400 and bool(target)
        return out
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        out["reason"] = f"unreachable:{str(e)[:200]}"
        return out


def verify_published_api(url: str, *, timeout: float = 25.0) -> dict[str, Any]:
    """Confirm the deployed BACKEND answers, not just the page in front of it.

    A full-stack publish reports success on the strength of the HTML at ``/``. That HTML is static:
    Vercel serves it from the build output whether or not the Python function behind it can even be
    imported. Measured on the first real publish of this product — page 200, and every API route:

        FUNCTION_INVOCATION_FAILED
        File "/var/task/api/app/utils/security.py", line 7: import jwt
        ModuleNotFoundError: No module named 'jwt'

    "Published" was logged, the pipeline moved to SALES_ACTIVE, and the product could not serve a
    single request. A publish gate that only looks at the shell certifies the one part of a
    full-stack product that cannot fail.
    """
    import json as _json
    import urllib.error
    import urllib.request

    out: dict[str, Any] = {"url": url, "api_ok": False, "probes": []}
    if not url:
        out["reason"] = "no_url"
        return out

    base = url.rstrip("/")
    for path in ("/api/health", "/api/healthz", "/openapi.json", "/api"):
        probe: dict[str, Any] = {"path": path}
        try:
            req = urllib.request.Request(base + path, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                probe["status"] = int(getattr(r, "status", 200))
                body = r.read(400).decode("utf-8", "replace")
                probe["body"] = body[:200]
        except urllib.error.HTTPError as e:
            probe["status"] = int(getattr(e, "code", 0))
            try:
                probe["body"] = e.read(400).decode("utf-8", "replace")[:200]
            except Exception:
                probe["body"] = ""
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            probe["status"] = 0
            probe["body"] = str(e)[:200]
        out["probes"].append(probe)
        status = probe.get("status") or 0
        # 404 means the app answered and has no such route — the function imported fine.
        if 200 <= status < 500 and status != 0:
            body = str(probe.get("body") or "")
            if "FUNCTION_INVOCATION_FAILED" in body or "A server error has occurred" in body:
                continue
            out["api_ok"] = True
            out["proof"] = f"{path} -> {status}"
            return out
        if status >= 500:
            out["reason"] = f"api_5xx:{path}:{status}"
            out["detail"] = str(probe.get("body") or "")[:300]
    out.setdefault("reason", "api_unreachable")
    return out


def _merge_publish_record(product_id: str, payload: dict[str, Any]) -> None:
    """Keep ``state/<pid>/auto_publish.json`` as the single source of publish truth."""
    out_path = Path(data_root()) / "state" / product_id / "auto_publish.json"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logger.warning("auto_publish: could not persist record for %s: %s", product_id, e)


def _load_pipeline_product(product_id: str) -> dict[str, Any]:
    """Best-effort product row from whichever pipeline store is active."""
    import sqlite3

    from core.paths import pipeline_json_path

    try:
        db = Path(data_root()) / "state" / "pipeline.db"
        if db.is_file():
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            try:
                row = con.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            finally:
                con.close()
            if row:
                product = dict(row)
                for key in ("tags", "extras", "spec", "generic_metadata"):
                    raw = product.get(key)
                    if isinstance(raw, str) and raw.strip():
                        try:
                            product[key] = json.loads(raw)
                        except ValueError:
                            pass
                return product
    except Exception as e:
        logger.debug("auto_publish: sqlite product lookup failed for %s: %s", product_id, e)

    try:
        pj = pipeline_json_path()
        if pj.is_file():
            doc = json.loads(pj.read_text(encoding="utf-8"))
            products = doc.get("products") if isinstance(doc, dict) else None
            if isinstance(products, dict) and isinstance(products.get(product_id), dict):
                return products[product_id]
    except Exception as e:
        logger.debug("auto_publish: pipeline.json product lookup failed for %s: %s", product_id, e)
    return {}


def _register_agent_if_applicable(product_id: str, result: dict[str, Any]) -> None:
    """Seed the agent registry when the shipped product is an autonomous agent.

    Waiting for the agent's own first heartbeat would leave a just-published
    serverless participant invisible until someone happened to visit it.
    """
    try:
        from web.backend.services.agent_registry import bootstrap_from_publish, product_is_agent

        product = _load_pipeline_product(product_id)
        if not product_is_agent(product):
            return
        url = str(result.get("vercel_url") or result.get("published_url") or "")
        spec = product.get("spec") if isinstance(product.get("spec"), dict) else {}
        inner = spec.get("specification") if isinstance(spec.get("specification"), dict) else spec
        name = str(inner.get("product_name") or product.get("name") or product_id)
        record = bootstrap_from_publish(
            product_id=product_id,
            name=name,
            public_url=url,
            capabilities=list(inner.get("capabilities_used") or []),
        )
        logger.info("auto_publish %s: registered agent %s in the economy roster", product_id, record["agent_id"])
    except Exception as e:
        # Never fail a publish because the roster write failed.
        logger.warning("auto_publish: agent registration skipped for %s: %s", product_id, e)


def _publish_fullstack_to_vercel(product_id: str, general: dict[str, Any]) -> dict[str, Any] | None:
    """Build a Vercel bundle for a full-stack product and deploy it.

    Returns ``None`` when Vercel publishing is not configured (not an error —
    the factory preview is still a valid delivery), otherwise a result dict.
    """
    provider = str(general.get("auto_publish_provider") or "none").strip().lower()
    if provider != "vercel":
        return None
    if os.environ.get("AIFACTORY_VERCEL_FULLSTACK", "1").strip().lower() in ("0", "false", "no"):
        return None
    token = _vercel_token()
    if not token:
        return {"ok": False, "error": "VERCEL_TOKEN not set"}
    vercel_bin = _which_vercel()
    if not vercel_bin:
        return {"ok": False, "error": "vercel CLI not found on PATH (npm i -g vercel)"}

    from web.backend.services.vercel_fullstack_adapter import build_vercel_bundle

    code_dir = Path(data_root()) / "code" / product_id
    # The Vercel project is named after the deployed directory. A shared name like
    # "vercel_bundle" puts every full-stack product into one project, each deploy
    # overwriting the last — the first real deploy landed on
    # https://vercelbundle-….vercel.app. Name the directory for the product.
    bundle_dir = Path(data_root()) / "state" / product_id / "vercel" / product_id
    try:
        bundle = build_vercel_bundle(code_dir, bundle_dir)
    except Exception as e:
        logger.exception("vercel bundle failed for %s", product_id)
        return {"ok": False, "error": f"bundle_failed:{e}"}
    if not bundle.get("ok"):
        return {"ok": False, "error": bundle.get("error") or "bundle_failed", "bundle": bundle}

    if bundle.get("invalid_requirements"):
        from web.backend.services.live_deployment_gate import vercel_publish_failure_as_live_gate

        live_gate = vercel_publish_failure_as_live_gate(
            product_id=product_id,
            bundle=bundle,
        )
        logger.warning(
            "Vercel publish for %s refused unparseable requirements.txt: %s",
            product_id,
            "; ".join(str(x)[:120] for x in (bundle.get("invalid_requirements") or [])[:3]),
        )
        return {
            "ok": False,
            "error": "invalid_requirements",
            "published_url": "",
            "publicly_reachable": False,
            "reachability": {},
            "exit_code": None,
            "bundle": bundle,
            "stdout_tail": "",
            "stderr_tail": "",
            "ts": time.time(),
            "live_gate": live_gate,
        }

    env = os.environ.copy()
    env["VERCEL_TOKEN"] = token
    data = Path(data_root())
    env["HOME"] = str(data)
    env["XDG_CACHE_HOME"] = str(data / ".cache")
    env["XDG_CONFIG_HOME"] = str(data / ".local")
    env["XDG_DATA_HOME"] = str(data / ".local" / "share")
    cmd = [vercel_bin, str(bundle_dir), "--prod", "--yes", "--token", token]
    if env.get("VERCEL_ORG_ID"):
        cmd.extend(["--scope", env["VERCEL_ORG_ID"]])
    timeout = int(os.environ.get("AIFACTORY_AUTO_PUBLISH_TIMEOUT_SEC", "900"))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout_after_{timeout}s", "bundle": bundle}
    url = _extract_url(proc.stdout, proc.stderr, "vercel")
    ok = proc.returncode == 0 and bool(url)
    reachability = verify_published_url(url) if ok else {}
    api_health = verify_published_api(url) if ok else {}
    if ok and not reachability.get("reachable"):
        # Exit 0 with a URL nobody outside the account can open is not published.
        ok = False
        logger.warning(
            "Vercel publish for %s produced a gated URL (%s): %s",
            product_id,
            reachability.get("reason") or reachability.get("status"),
            reachability.get("detail") or reachability.get("redirect_to") or "",
        )
    # The last word belongs to a browser pointed at the deployed URL. Everything before this
    # measured a sandbox, and the sandbox is where the two defects that shipped today were
    # invisible: an import that resolved in the preview venv and not in the function, and 47
    # utility classes that styled nothing. Both were obvious in two seconds to a person who opened
    # the link, so the gate opens the link.
    live_gate: dict[str, Any] = {}
    if proc.returncode != 0 or not url:
        from web.backend.services.live_deployment_gate import vercel_publish_failure_as_live_gate

        live_gate = vercel_publish_failure_as_live_gate(
            product_id=product_id,
            exit_code=proc.returncode,
            stderr=proc.stderr or "",
            stdout=proc.stdout or "",
            bundle=bundle,
        )
        ok = False
        logger.warning(
            "Vercel CLI failed for %s rc=%s: %s",
            product_id,
            proc.returncode,
            "; ".join(str(i)[:160] for i in (live_gate.get("issues") or [])[:3]),
        )
    elif ok:
        try:
            from web.backend.services.live_deployment_gate import check_live_deployment

            live_gate = check_live_deployment(url, product_id=product_id)
        except Exception as live_exc:
            logger.warning("Live deployment gate could not run for %s: %s", product_id, live_exc)
            live_gate = {"skipped": True, "reason": f"gate_error:{live_exc}"}
        if not live_gate.get("skipped") and not live_gate.get("passed"):
            ok = False
            logger.warning(
                "Vercel publish for %s FAILED the live deployment gate: %s — the deployment is not "
                "recorded as published",
                product_id,
                "; ".join(str(i)[:160] for i in (live_gate.get("issues") or [])[:3]),
            )

    if ok and api_health and not api_health.get("api_ok"):
        ok = False
        logger.warning(
            "Vercel publish for %s served the page but its API is dead (%s): %s — the deployment "
            "is not usable and is not being recorded as published",
            product_id,
            api_health.get("reason"),
            str(api_health.get("detail") or "")[:200],
        )
    if live_gate:
        record_extra = {"live_gate": live_gate}
        try:
            _merge_publish_record(product_id, {**record_extra, "url": url, "ok": ok})
        except Exception as rec_exc:
            logger.debug("Could not persist live gate record for %s: %s", product_id, rec_exc)
    if ok:
        logger.info(
            "Vercel full-stack publish OK %s → %s (api: %s)",
            product_id,
            url,
            api_health.get("proof") or "n/a",
        )
    else:
        logger.warning(
            "Vercel full-stack publish incomplete %s rc=%s url=%s",
            product_id,
            proc.returncode,
            url,
        )
    return {
        "ok": ok,
        "published_url": url,
        "publicly_reachable": bool(reachability.get("reachable")),
        "reachability": reachability,
        "exit_code": proc.returncode,
        "bundle": bundle,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "ts": time.time(),
        "live_gate": live_gate,
    }


def try_publish_after_devops(product_id: str) -> dict[str, Any]:
    """Sync helper (call via asyncio.to_thread from pipeline worker)."""
    general = _read_general()
    if not general.get("auto_publish_enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled"}

    dp = _product_delivery_profile(product_id)
    from core.delivery_profile import FULL_SOFTWARE, MARKETING_LANDING, normalize_delivery_profile

    ndp = normalize_delivery_profile(dp)
    if ndp == FULL_SOFTWARE:
        from web.backend.services.working_app_publish import try_publish_working_app

        logger.info("auto_publish %s: full_software → live factory preview + Vercel bundle", product_id)
        result = try_publish_working_app(product_id)
        # A full-stack product must also be reachable outside the factory: ship the
        # built SPA plus the FastAPI app as a Vercel serverless function.
        vercel = _publish_fullstack_to_vercel(product_id, general)
        if vercel:
            result = dict(result)
            result["vercel"] = vercel
            if vercel.get("ok") and vercel.get("published_url"):
                result["vercel_url"] = vercel["published_url"]
            if vercel.get("live_gate"):
                result["live_gate"] = vercel["live_gate"]
            _merge_publish_record(product_id, result)
        _register_agent_if_applicable(product_id, result)
        return result

    landing_only = general.get("auto_publish_landing_only", True)
    if landing_only and ndp != MARKETING_LANDING:
        logger.info("auto_publish skip %s: not_marketing_landing dp=%s", product_id, dp)
        return {
            "ok": False,
            "skipped": True,
            "reason": "not_marketing_landing",
            "delivery_profile": dp,
        }

    provider = str(general.get("auto_publish_provider") or "none").strip().lower()
    if provider in ("", "none", "off", "false"):
        return {"ok": False, "skipped": True, "reason": "provider_none"}

    code_dir = Path(data_root()) / "code" / product_id
    if not code_dir.is_dir():
        return {"ok": False, "error": "code_dir_missing", "path": str(code_dir)}

    out_path = Path(data_root()) / "state" / product_id / "auto_publish.json"
    env = os.environ.copy()

    cmd: list[str]
    timeout = int(os.environ.get("AIFACTORY_AUTO_PUBLISH_TIMEOUT_SEC", "900"))

    try:
        if provider == "vercel":
            token = _vercel_token()
            if not token:
                err = "VERCEL_TOKEN not set"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            env["VERCEL_TOKEN"] = token
            data = Path(data_root())
            env["HOME"] = str(data)
            env["XDG_CACHE_HOME"] = str(data / ".cache")
            env["XDG_CONFIG_HOME"] = str(data / ".local")
            env["XDG_DATA_HOME"] = str(data / ".local" / "share")
            vercel_bin = _which_vercel()
            if not vercel_bin:
                err = "vercel CLI not found on PATH (npm i -g vercel)"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            cmd = [vercel_bin, str(code_dir), "--prod", "--yes", "--token", token]
            if env.get("VERCEL_ORG_ID"):
                cmd.extend(["--scope", env["VERCEL_ORG_ID"]])

        elif provider == "netlify":
            auth = env.get("NETLIFY_AUTH_TOKEN", "").strip()
            if not auth:
                err = "NETLIFY_AUTH_TOKEN not set"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            netlify_bin = shutil.which("netlify")
            if not netlify_bin:
                err = "netlify CLI not found on PATH"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            cmd = [netlify_bin, "deploy", "--prod", "--dir", str(code_dir), "--auth", auth]
            site = str(general.get("auto_publish_netlify_site_id") or "").strip()
            if site:
                cmd.extend(["--site", site])

        elif provider == "cloudflare_pages":
            tok = env.get("CLOUDFLARE_API_TOKEN", "").strip()
            if not tok:
                err = "CLOUDFLARE_API_TOKEN not set"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            wrangler_bin = shutil.which("wrangler")
            if not wrangler_bin:
                err = "wrangler CLI not found on PATH (npm i -g wrangler)"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            proj = str(general.get("auto_publish_cf_project_name") or "").strip()
            if not proj:
                proj = f"aifactory-{product_id.replace('prod-', '')[:12]}"
            account = env.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
            cmd = [wrangler_bin, "pages", "deploy", str(code_dir), "--project-name", proj]
            if account:
                cmd.extend(["--account-id", account])
        else:
            return {"ok": False, "error": f"unknown_provider:{provider}"}

        log_cmd = [
            "<redacted>" if (i and cmd[i - 1] in ("--token", "--auth")) else part
            for i, part in enumerate(cmd[:8])
        ]
        logger.info("Auto-publish %s → %s (%s)", product_id, provider, " ".join(log_cmd))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        url = _extract_url(proc.stdout, proc.stderr, provider)
        ok = proc.returncode == 0 and bool(url)
        payload = {
            "ok": ok,
            "product_id": product_id,
            "provider": provider,
            "exit_code": proc.returncode,
            "published_url": url,
            "stdout_tail": (proc.stdout or "")[-8000:],
            "stderr_tail": (proc.stderr or "")[-8000:],
            "ts": time.time(),
        }
        if proc.returncode != 0:
            payload["error"] = "cli_failed"
        elif not url:
            payload["error"] = "url_not_detected"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if ok:
            logger.info("Auto-publish OK %s → %s", product_id, url)
        else:
            logger.warning(
                "Auto-publish incomplete %s rc=%s url=%s",
                product_id,
                proc.returncode,
                url,
            )
        return payload
    except subprocess.TimeoutExpired:
        err = f"timeout_after_{timeout}s"
        _write_result(out_path, product_id, provider, ok=False, error=err)
        return {"ok": False, "error": err}
    except Exception as e:
        logger.exception("Auto-publish failed for %s", product_id)
        _write_result(out_path, product_id, provider, ok=False, error=str(e))
        return {"ok": False, "error": str(e)}


def _write_result(path: Path, product_id: str, provider: str, ok: bool, error: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ok": ok,
                "product_id": product_id,
                "provider": provider,
                "error": error,
                "ts": time.time(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
