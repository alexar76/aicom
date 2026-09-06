"""
Fleet-wide LLM profile switching — DeepSeek API, Metis hybrid, OpenRouter emergency.

Profiles (see scripts/llm_fleet.yaml):
  deepseek-all   — everything on api.deepseek.com
  hybrid-metis   — DeepSeek fleet + Metis base/pro seats; MiniMax via OpenRouter on skeptic slots
  openrouter-all — emergency failover (factory hold + OpenRouter MiniMax + Kimi-K3 in Metis)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
FLEET_YAML = Path(__file__).with_name("llm_fleet.yaml")

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DS_PRO = "deepseek-v4-pro"
DS_FLASH = "deepseek-v4-flash"
MINIMAX = "minimax/minimax-m3"
KIMI_K3 = "moonshotai/kimi-k3"

METIS_HDR = {"HTTP-Referer": "https://metis.modelmarket.dev", "X-Title": "Metis"}

# Seats that use OpenRouter MiniMax in hybrid (canonical prod — BENCHMARKS.md).
METIS_OPENROUTER_HYBRID = frozenset({"intent_parser_b", "moa_proposer_skeptic"})
METIS_FLASH_SEATS = frozenset(
    {
        "intent_parser_a",
        "constraint_extractor",
        "ambiguity_hunter",
        "judge",
        "moa_proposer_pragmatist",
        "verifier",
        "router",
    }
)
METIS_PRO_SEATS = frozenset(
    {
        "intent_parser_c",
        "red_team",
        "moa_proposer_logician",
        "moa_refiner",
        "synthesizer",
        "aggregator",
    }
)

DEEPSEEK_ENV_DEFAULTS = {
    "ATLAS_LLM_PROVIDER": "deepseek_api",
    "ATLAS_LLM_BASE_URL": DEEPSEEK_BASE,
    "ATLAS_LLM_MODEL": DS_PRO,
    "ATLAS_LLM_MODEL_LIGHT": DS_FLASH,
    "MOMUS_LLM_PROVIDER": "deepseek",
    "MOMUS_LLM_MODEL": DS_PRO,
    "MOMUS_LLM_BASE_URL": "",
    "MOMUS_LLM_API_KEY": "",
    "HELIOS_LLM_PROVIDER": "deepseek",
    "HELIOS_LLM_BASE_URL": "",
    "HELIOS_LLM_MODEL": DS_PRO,
    "DIOSCURI_LLM_PROVIDER": "deepseek",
    "DIOSCURI_LLM_BASE_URL": "",
    "DIOSCURI_LLM_MODEL": DS_PRO,
    "TREASURY_LLM_PROVIDER": "deepseek",
}

OPENROUTER_ENV_OVERRIDES = {
    "ATLAS_LLM_PROVIDER": "openrouter_api",
    "ATLAS_LLM_BASE_URL": OPENROUTER_BASE,
    "ATLAS_LLM_MODEL": MINIMAX,
    "ATLAS_LLM_MODEL_LIGHT": MINIMAX,
    "MOMUS_LLM_PROVIDER": "openai",
    "MOMUS_LLM_BASE_URL": OPENROUTER_BASE,
    "MOMUS_LLM_MODEL": MINIMAX,
    "HELIOS_LLM_PROVIDER": "openai-compatible",
    "HELIOS_LLM_BASE_URL": OPENROUTER_BASE,
    "HELIOS_LLM_MODEL": MINIMAX,
    "DIOSCURI_LLM_PROVIDER": "openai-compatible",
    "DIOSCURI_LLM_BASE_URL": OPENROUTER_BASE,
    "DIOSCURI_LLM_MODEL": MINIMAX,
    "TREASURY_LLM_PROVIDER": "openai",
}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup(path: Path) -> Path:
    dest = path.with_suffix(path.suffix + f".bak-{_ts()}")
    shutil.copy2(path, dest)
    return dest


def load_fleet() -> dict[str, Any]:
    return yaml.safe_load(FLEET_YAML.read_text(encoding="utf-8")) or {}


def _deepseek_module(model: str, *, temperature: float | None = None) -> dict[str, Any]:
    m: dict[str, Any] = {
        "provider": "openai_compat",
        "model": model,
        "base_url": DEEPSEEK_BASE,
        "api_key_env": "DEEPSEEK_API_KEY",
    }
    if temperature is not None:
        m["temperature"] = temperature
    return m


def _openrouter_module(model: str, *, temperature: float | None = None) -> dict[str, Any]:
    m: dict[str, Any] = {
        "provider": "openai_compat",
        "model": model,
        "base_url": OPENROUTER_BASE,
        "api_key_env": "OPENROUTER_API_KEY",
        "extra_headers": dict(METIS_HDR),
    }
    if temperature is not None:
        m["temperature"] = temperature
    return m


def _slot_model(name: str, *, flash: bool = False) -> str:
    if name in METIS_OPENROUTER_HYBRID:
        return MINIMAX
    if name in METIS_FLASH_SEATS or flash:
        return DS_FLASH
    if name in METIS_PRO_SEATS:
        return DS_PRO
    return DS_PRO


def patch_metis_deepseek_all(data: dict[str, Any]) -> dict[str, Any]:
    """All Metis seats on DeepSeek native API."""
    out = deepcopy(data)
    out["provider"] = "openai_compat"
    out["base_model"] = DS_PRO
    out["base_url"] = DEEPSEEK_BASE
    out["api_key_env"] = "DEEPSEEK_API_KEY"
    modules = dict(out.get("modules") or {})
    for name, mod in list(modules.items()):
        if not isinstance(mod, dict):
            continue
        temp = mod.get("temperature")
        model = _slot_model(name, flash=name in METIS_FLASH_SEATS)
        if name in METIS_OPENROUTER_HYBRID:
            model = DS_PRO  # deepseek-all: no openrouter seats
        modules[name] = _deepseek_module(
            model, temperature=temp if isinstance(temp, (int, float)) else None
        )
    out["modules"] = modules
    return out


def patch_metis_hybrid(data: dict[str, Any]) -> dict[str, Any]:
    """Canonical prod: DeepSeek base + flash/pro seats; MiniMax on OpenRouter for skeptic slots."""
    out = deepcopy(data)
    out["provider"] = "openai_compat"
    out["base_model"] = DS_PRO
    out["base_url"] = DEEPSEEK_BASE
    out["api_key_env"] = "DEEPSEEK_API_KEY"
    modules = dict(out.get("modules") or {})
    for name, mod in list(modules.items()):
        if not isinstance(mod, dict):
            continue
        temp = mod.get("temperature")
        t = temp if isinstance(temp, (int, float)) else None
        if name in METIS_OPENROUTER_HYBRID:
            modules[name] = _openrouter_module(MINIMAX, temperature=t)
        else:
            model = _slot_model(name)
            modules[name] = _deepseek_module(model, temperature=t)
    out["modules"] = modules
    return out


def patch_metis_openrouter_all(data: dict[str, Any]) -> dict[str, Any]:
    """Emergency: OpenRouter MiniMax base; Kimi-K3 on intent_parser_c."""
    out = deepcopy(data)
    out["provider"] = "openai_compat"
    out["base_model"] = MINIMAX
    out["base_url"] = OPENROUTER_BASE
    out["api_key_env"] = "OPENROUTER_API_KEY"
    modules = dict(out.get("modules") or {})
    for name, mod in list(modules.items()):
        if not isinstance(mod, dict):
            continue
        env = str(mod.get("api_key_env") or "")
        url = str(mod.get("base_url") or "")
        if env != "DEEPSEEK_API_KEY" and "deepseek.com" not in url and env != "OPENROUTER_API_KEY":
            continue
        temp = mod.get("temperature")
        t = temp if isinstance(temp, (int, float)) else None
        model = KIMI_K3 if name == "intent_parser_c" else MINIMAX
        modules[name] = _openrouter_module(model, temperature=t)
    out["modules"] = modules
    return out


METIS_PATCHERS = {
    "deepseek_all": patch_metis_deepseek_all,
    "hybrid": patch_metis_hybrid,
    "openrouter_all": patch_metis_openrouter_all,
}


def _read_env_key(path: str, key: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f"env file not found: {path}")
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"{key} not found in {path}")


def _ssh_read_env_key(ssh: str, env_path: str, key: str) -> str:
    if Path(env_path).is_file():
        return _read_env_key(env_path, key)
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", ssh, f"grep -E '^{re.escape(key)}=' {env_path} | head -1"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or "=" not in (proc.stdout or ""):
        raise RuntimeError(f"{key} not found on {ssh}:{env_path}")
    return proc.stdout.strip().split("=", 1)[1].strip()


def _upsert_env(env_path: Path, updates: dict[str, str], *, marker: str) -> None:
    lines: list[str] = []
    keys = set(updates)
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip() == marker:
                break
            k = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
            if k in keys:
                continue
            lines.append(line)
    lines.append(marker)
    for k, v in updates.items():
        if v == "":
            lines.append(f"# {k}=  # cleared by profile switch")
        else:
            lines.append(f"{k}={v}")
    lines.append(f"# profile applied {_ts()}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_metis_profile(prod_yaml: str, mode: str, *, restart: bool = True) -> dict[str, Any]:
    prod = Path(prod_yaml)
    patcher = METIS_PATCHERS[mode]
    data = yaml.safe_load(prod.read_text(encoding="utf-8")) or {}
    bak = _backup(prod)
    patched = patcher(data if isinstance(data, dict) else {})
    tmp = Path("/tmp") / f"metis-profile-{_ts()}.yaml"
    tmp.write_text(yaml.safe_dump(patched, sort_keys=False, allow_unicode=True), encoding="utf-8")
    shutil.move(str(tmp), str(prod))
    if restart:
        subprocess.run(["docker", "restart", "metis"], check=False)
    return {"backup": str(bak), "mode": mode, "base_model": patched.get("base_model")}


def env_updates_for_profile(profile: str, *, openrouter_key: str = "") -> dict[str, str]:
    if profile == "openrouter-all":
        out = dict(OPENROUTER_ENV_OVERRIDES)
        out["OPENROUTER_API_KEY"] = openrouter_key
        out["MOMUS_LLM_API_KEY"] = openrouter_key
        return out
    out = dict(DEEPSEEK_ENV_DEFAULTS)
    if openrouter_key and profile == "hybrid-metis":
        out["OPENROUTER_API_KEY"] = openrouter_key
    return out


def apply_factory_profile_local(profile: str, *, deepseek_key: str = "", openrouter_key: str = "") -> dict[str, Any]:
    if profile == "openrouter-all":
        from llm.persist_openrouter import sync_openrouter_provider_config

        if not openrouter_key:
            openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        r = sync_openrouter_provider_config(api_key=openrouter_key or None)
        from core.config_overlay import patch_primary_overlay

        patch_primary_overlay({"general.factory_on_hold": True})
        return {"openrouter": r, "factory_on_hold": True}
    from llm.persist_deepseek import sync_deepseek_provider_config
    from core.config_overlay import patch_primary_overlay

    if not deepseek_key:
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    r = sync_deepseek_provider_config(api_key=deepseek_key or None)
    if profile == "deepseek-all":
        patch_primary_overlay({"general.factory_on_hold": False})
    return {"deepseek": r}


def cmd_scan(_args: argparse.Namespace) -> int:
    fleet = load_fleet()
    report: dict[str, Any] = {"hosts": {}}
    for hid, h in (fleet.get("hosts") or {}).items():
        ssh = h.get("ssh", "")
        entry: dict[str, Any] = {"label": h.get("label"), "ssh": ssh, "checks": []}
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=8",
                    ssh,
                    "docker ps --format '{{.Names}}' 2>/dev/null | head -30",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            running = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            expected = h.get("containers") or []
            entry["running"] = running
            entry["expected"] = expected
            entry["missing"] = [c for c in expected if c not in running]
        except Exception as exc:
            entry["error"] = str(exc)
        report["hosts"][hid] = entry
    print(json.dumps(report, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    fleet = load_fleet()
    profile = args.profile
    prof = (fleet.get("profiles") or {}).get(profile)
    if not prof:
        print(f"unknown profile: {profile}", file=sys.stderr)
        return 1

    metis_mode = prof["metis_mode"]
    report: dict[str, Any] = {"profile": profile, "ts": _ts()}

    or_key = (args.openrouter_key or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    ds_key = (args.deepseek_key or os.environ.get("DEEPSEEK_API_KEY") or "").strip()

    if args.host in ("all", "metis") and not args.no_metis:
        metis_h = fleet["hosts"]["metis"]
        prod = args.metis_prod_yaml or metis_h["prod_yaml"]
        if Path(prod).is_file():
            report["metis"] = apply_metis_profile(prod, metis_mode, restart=not args.no_restart)
        else:
            ssh = metis_h["ssh"]
            scp = subprocess.run(
                ["scp", "-o", "BatchMode=yes", str(Path(__file__)), f"{ssh}:/tmp/llm_routing.py"],
                check=False,
            )
            if scp.returncode != 0:
                print("metis scp failed", file=sys.stderr)
                return 1
            remote = (
                f"python3 /tmp/llm_routing.py apply --profile {profile} --no-metis --metis-prod-yaml {prod}"
            )
            subprocess.run(["ssh", "-o", "BatchMode=yes", ssh, remote], check=False)

    if args.host in ("all", "factory") and not args.no_factory:
        if not or_key and profile != "deepseek-all":
            try:
                metis_env = fleet["hosts"]["metis"]["env_file"]
                or_key = _ssh_read_env_key(fleet["hosts"]["metis"]["ssh"], metis_env, "OPENROUTER_API_KEY")
            except RuntimeError:
                pass
        if profile == "deepseek-all" and not ds_key:
            try:
                factory_env = fleet["hosts"]["factory"]["env_file"]
                ds_key = _ssh_read_env_key(fleet["hosts"]["factory"]["ssh"], factory_env, "DEEPSEEK_API_KEY")
            except RuntimeError:
                pass
        report["factory_local"] = apply_factory_profile_local(
            profile, deepseek_key=ds_key, openrouter_key=or_key
        )

    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fleet LLM profile switcher")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="List AI containers on all fleet hosts")
    scan_p.set_defaults(func=cmd_scan)

    apply_p = sub.add_parser("apply", help="Apply profile")
    apply_p.add_argument(
        "profile",
        choices=["deepseek-all", "hybrid-metis", "openrouter-all"],
    )
    apply_p.add_argument("--host", choices=["all", "factory", "metis", "oracles", "hub_lab"], default="all")
    apply_p.add_argument("--deepseek-key", default="")
    apply_p.add_argument("--openrouter-key", default="")
    apply_p.add_argument("--metis-prod-yaml", default="")
    apply_p.add_argument("--no-factory", action="store_true")
    apply_p.add_argument("--no-metis", action="store_true")
    apply_p.add_argument("--no-restart", action="store_true")
    apply_p.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
