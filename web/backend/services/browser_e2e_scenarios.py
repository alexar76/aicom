"""
Declarative Playwright scenarios for SPA / auth flows (complement to BFS deep crawl).

Load from ``data/code/<product_id>/e2e-scenarios.json`` or ``AIFACTORY_BROWSER_SCENARIO_FILE``.
Disable with ``AIFACTORY_BROWSER_SCENARIOS=0``.

JSON shape::

    [
      {
        "name": "login",
        "steps": [
          {"goto": "/login"},
          {"fill": {"selector": "#email", "value": "${AIFACTORY_E2E_EMAIL}"}},
          {"fill": {"selector": "#password", "value": "${AIFACTORY_E2E_PASSWORD}"}},
          {"click": "button[type='submit']"},
          {"wait_ms": 800},
          {"wait_selector": {"selector": "text=Dashboard", "timeout_ms": 15000}}
        ]
      }
    ]

Environment placeholders use ``${VAR_NAME}`` (fallback empty string if unset).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def substitute_env_values(obj: Any) -> Any:
    """Recursively replace ${VAR} in strings using ``os.environ``."""

    def _sub_str(s: str) -> str:
        def repl(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1).strip(), "")

        return _ENV_PLACEHOLDER.sub(repl, s)

    if isinstance(obj, str):
        return _sub_str(obj)
    if isinstance(obj, dict):
        return {k: substitute_env_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_env_values(x) for x in obj]
    return obj


def load_scenario_specs(code_dir: Path) -> list[dict[str, Any]]:
    raw_path = os.environ.get("AIFACTORY_BROWSER_SCENARIO_FILE", "").strip()
    path = Path(raw_path) if raw_path else code_dir / "e2e-scenarios.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("browser scenarios: cannot load %s: %s", path, e)
        return []
    if isinstance(data, dict) and isinstance(data.get("scenarios"), list):
        return substitute_env_values(list(data["scenarios"]))
    if isinstance(data, list):
        return substitute_env_values(data)
    logger.warning("browser scenarios: unexpected JSON shape in %s", path)
    return []


def scenarios_enabled() -> bool:
    return os.environ.get("AIFACTORY_BROWSER_SCENARIOS", "1").strip().lower() not in ("0", "false", "no")


def run_declarative_scenarios(page: Any, base_origin: str, specs: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute scenario specs; mutate ``page``. Returns summary dict."""
    out: dict[str, Any] = {"ran": False, "scenarios": [], "issues": []}
    if not specs:
        return out
    out["ran"] = True

    origin = base_origin.rstrip("/")

    for spec in specs:
        name = str(spec.get("name") or "scenario")
        steps = spec.get("steps") if isinstance(spec.get("steps"), list) else []
        scen_log: list[dict[str, Any]] = []
        try:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                if "goto" in step:
                    path = str(step["goto"] or "").strip()
                    if path.startswith("http://") or path.startswith("https://"):
                        dest = path
                    else:
                        dest = urljoin(origin + "/", path.lstrip("/"))
                    page.goto(dest, wait_until="domcontentloaded", timeout=45_000)
                    scen_log.append({"step": i, "goto": dest})
                elif "click" in step:
                    sel = str(step["click"])
                    page.locator(sel).first.click(timeout=15_000)
                    scen_log.append({"step": i, "click": sel})
                elif "fill" in step and isinstance(step["fill"], dict):
                    fd = step["fill"]
                    sel = str(fd.get("selector") or "")
                    val = str(fd.get("value") or "")
                    page.locator(sel).first.fill(val, timeout=15_000)
                    scen_log.append({"step": i, "fill": sel})
                elif "wait_ms" in step:
                    ms = int(step["wait_ms"])
                    page.wait_for_timeout(max(0, min(ms, 60_000)))
                    scen_log.append({"step": i, "wait_ms": ms})
                elif "wait_selector" in step:
                    ws = step["wait_selector"]
                    if isinstance(ws, str):
                        page.wait_for_selector(ws, timeout=15_000)
                        scen_log.append({"step": i, "wait_selector": ws})
                    elif isinstance(ws, dict):
                        sel = str(ws.get("selector") or "")
                        to = int(ws.get("timeout_ms") or 15_000)
                        page.wait_for_selector(sel, timeout=max(1000, min(to, 120_000)))
                        scen_log.append({"step": i, "wait_selector": sel})
                elif "expect_visible" in step:
                    sel = str(step["expect_visible"])
                    loc = page.locator(sel).first
                    loc.wait_for(state="visible", timeout=15_000)
                    scen_log.append({"step": i, "expect_visible": sel})
                else:
                    scen_log.append({"step": i, "skipped_unknown": list(step.keys())})
            out["scenarios"].append({"name": name, "ok": True, "log": scen_log})
        except Exception as e:
            err = str(e)[:400]
            out["issues"].append(f"scenario:{name}:{err}")
            out["scenarios"].append({"name": name, "ok": False, "error": err, "log": scen_log})
    return out
