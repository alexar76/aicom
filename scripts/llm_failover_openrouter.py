#!/usr/bin/env python3
"""
Emergency LLM failover: DeepSeek outage → OpenRouter (MiniMax-M3 + Kimi-K3 in Metis).

Usage:
  python3 scripts/llm_failover_openrouter.py apply --from-metis-env
  python3 scripts/llm_failover_openrouter.py apply --openrouter-key-env OPENROUTER_API_KEY
  python3 scripts/llm_failover_openrouter.py restore-deepseek
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MINIMAX_MODEL = "minimax/minimax-m3"
KIMI_K3_MODEL = "moonshotai/kimi-k3"
METIS_REFERER = "https://metis.modelmarket.dev"
FACTORY_REFERER = "https://magic-ai-factory.com"

METIS_OPENROUTER_HEADERS = {
    "HTTP-Referer": METIS_REFERER,
    "X-Title": "Metis",
}

SATELLITE_ENV_OVERRIDES = {
    "OPENROUTER_API_KEY": None,  # filled at runtime
    "ATLAS_LLM_PROVIDER": "openrouter_api",
    "ATLAS_LLM_BASE_URL": OPENROUTER_BASE,
    "ATLAS_LLM_MODEL": MINIMAX_MODEL,
    "ATLAS_LLM_MODEL_LIGHT": MINIMAX_MODEL,
    "MOMUS_LLM_PROVIDER": "openai",
    "MOMUS_LLM_BASE_URL": OPENROUTER_BASE,
    "MOMUS_LLM_MODEL": MINIMAX_MODEL,
    "HELIOS_LLM_PROVIDER": "openai-compatible",
    "HELIOS_LLM_BASE_URL": OPENROUTER_BASE,
    "HELIOS_LLM_MODEL": MINIMAX_MODEL,
    "DIOSCURI_LLM_PROVIDER": "openai-compatible",
    "DIOSCURI_LLM_BASE_URL": OPENROUTER_BASE,
    "DIOSCURI_LLM_MODEL": MINIMAX_MODEL,
    "TREASURY_LLM_PROVIDER": "openai",
    "MOMUS_LLM_API_KEY": None,
}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup(path: Path) -> Path:
    dest = path.with_suffix(path.suffix + f".bak-{_ts()}")
    shutil.copy2(path, dest)
    return dest


def _read_env_key_from_file(env_path: str, key: str) -> str:
    path = Path(env_path)
    if not path.is_file():
        raise RuntimeError(f"env file not found: {env_path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"{key} not found in {env_path}")


def _read_env_key_from_remote(ssh_target: str, env_path: str, key: str) -> str:
    if ssh_target in ("", "local", "localhost") or env_path.startswith("/"):
        local = Path(env_path)
        if local.is_file():
            return _read_env_key_from_file(env_path, key)
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        ssh_target,
        f"grep -E '^{re.escape(key)}=' {env_path} | head -1",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"{key} not found in {ssh_target}:{env_path}")
    line = proc.stdout.strip()
    if "=" not in line:
        raise RuntimeError(f"malformed env line: {line[:20]}...")
    return line.split("=", 1)[1].strip().strip('"').strip("'")


def _upsert_env_lines(env_path: Path, updates: dict[str, str]) -> None:
    lines: list[str] = []
    seen: set[str] = set()
    marker = "# --- llm_failover_openrouter (auto) ---"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip() == marker:
                break
            key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
            if key in updates:
                continue
            lines.append(line)
    lines.append(marker)
    for key, val in updates.items():
        if val is None:
            continue
        lines.append(f"{key}={val}")
        seen.add(key)
    lines.append(f"# applied {_ts()}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _openrouter_module(model: str, *, temperature: float | None = None) -> dict[str, Any]:
    mod: dict[str, Any] = {
        "provider": "openai_compat",
        "model": model,
        "base_url": OPENROUTER_BASE,
        "api_key_env": "OPENROUTER_API_KEY",
        "extra_headers": dict(METIS_OPENROUTER_HEADERS),
    }
    if temperature is not None:
        mod["temperature"] = temperature
    return mod


def patch_metis_prod_yaml(data: dict[str, Any]) -> dict[str, Any]:
    """Switch Metis base + DeepSeek seats to OpenRouter; intent_parser_c → Kimi-K3."""
    out = dict(data)
    out["provider"] = "openai_compat"
    out["base_model"] = MINIMAX_MODEL
    out["base_url"] = OPENROUTER_BASE
    out["api_key_env"] = "OPENROUTER_API_KEY"

    modules = dict(out.get("modules") or {})
    kimi_roles = {"intent_parser_c"}
    for name, mod in list(modules.items()):
        if not isinstance(mod, dict):
            continue
        env = str(mod.get("api_key_env") or "")
        url = str(mod.get("base_url") or "")
        if env != "DEEPSEEK_API_KEY" and "deepseek.com" not in url:
            continue
        temp = mod.get("temperature")
        model = KIMI_K3_MODEL if name in kimi_roles else MINIMAX_MODEL
        modules[name] = _openrouter_module(model, temperature=temp if isinstance(temp, (int, float)) else None)
    out["modules"] = modules
    return out


def apply_factory_hold() -> dict[str, Any]:
    from core.config_overlay import patch_primary_overlay
    from core.factory_hold import is_factory_on_hold

    patch_primary_overlay({"general.factory_on_hold": True})
    return {"factory_on_hold": is_factory_on_hold()}


def apply_factory_openrouter(api_key: str) -> dict[str, Any]:
    from llm.persist_openrouter import sync_openrouter_provider_config

    return sync_openrouter_provider_config(api_key=api_key, reset_circuit=True)


def apply_local_env(repo_root: Path, api_key: str) -> Path:
    env_path = repo_root / ".env"
    updates = {k: v for k, v in SATELLITE_ENV_OVERRIDES.items() if v is not None}
    updates["OPENROUTER_API_KEY"] = api_key
    updates["MOMUS_LLM_API_KEY"] = api_key
    _upsert_env_lines(env_path, updates)
    return env_path


def apply_metis_local(prod_yaml: str, api_key: str, *, restart: bool) -> dict[str, Any]:
    prod = Path(prod_yaml)
    data = yaml.safe_load(prod.read_text(encoding="utf-8")) or {}
    bak = _backup(prod)
    patched = patch_metis_prod_yaml(data if isinstance(data, dict) else {})
    tmp = Path("/tmp") / f"metis-prod-failover-{_ts()}.yaml"
    tmp.write_text(
        yaml.safe_dump(patched, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    shutil.move(str(tmp), str(prod))
    envp = Path("/opt/metis/.env")
    if envp.is_file():
        _upsert_env_lines(envp, {"OPENROUTER_API_KEY": api_key})
    if restart:
        subprocess.run(["docker", "restart", "metis"], check=False)
    return {"backup": str(bak), "prod": str(prod), "env": str(envp)}


def apply_metis_remote(ssh_target: str, prod_yaml: str, api_key: str, *, restart: bool) -> dict[str, Any]:
    remote_py = r"""
import json, sys, yaml
from pathlib import Path

prod = Path(sys.argv[1])
api_key = sys.argv[2]
data = yaml.safe_load(prod.read_text(encoding="utf-8")) or {}

MINIMAX = "minimax/minimax-m3"
KIMI = "moonshotai/kimi-k3"
BASE = "https://openrouter.ai/api/v1"
HDR = {"HTTP-Referer": "https://metis.modelmarket.dev", "X-Title": "Metis"}

def mod(model, temp=None):
    m = {"provider": "openai_compat", "model": model, "base_url": BASE,
         "api_key_env": "OPENROUTER_API_KEY", "extra_headers": HDR}
    if temp is not None: m["temperature"] = temp
    return m

data["provider"] = "openai_compat"
data["base_model"] = MINIMAX
data["base_url"] = BASE
data["api_key_env"] = "OPENROUTER_API_KEY"
modules = dict(data.get("modules") or {})
for name, slot in list(modules.items()):
    if not isinstance(slot, dict): continue
    env = str(slot.get("api_key_env") or "")
    url = str(slot.get("base_url") or "")
    if env != "DEEPSEEK_API_KEY" and "deepseek.com" not in url: continue
    t = slot.get("temperature")
    model = KIMI if name == "intent_parser_c" else MINIMAX
    modules[name] = mod(model, t if isinstance(t, (int, float)) else None)
data["modules"] = modules
bak = prod.with_suffix(prod.suffix + ".bak-" + __import__("datetime").datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
bak.write_bytes(prod.read_bytes())
prod.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
envp = Path("/opt/metis/.env")
lines = envp.read_text(encoding="utf-8").splitlines() if envp.is_file() else []
out, seen = [], False
for line in lines:
    if line.startswith("OPENROUTER_API_KEY="):
        out.append("OPENROUTER_API_KEY=" + api_key)
        seen = True
    else:
        out.append(line)
if not seen:
    out.append("OPENROUTER_API_KEY=" + api_key)
envp.write_text("\n".join(out) + "\n", encoding="utf-8")
print(json.dumps({"backup": str(bak), "prod": str(prod), "env": str(envp)}))
"""
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        ssh_target,
        "python3",
        "-c",
        remote_py,
        prod_yaml,
        api_key,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "metis remote patch failed")
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    if restart:
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", ssh_target, "docker", "restart", "metis"],
            check=False,
        )
    return result


def docker_exec_factory(repo_root: Path, api_key: str) -> dict[str, Any]:
    """Apply inside aicom-app-1 when running on the factory host."""
    hold = apply_factory_hold()
    sync = apply_factory_openrouter(api_key)
    return {"hold": hold, "openrouter": sync}


def restart_factory_satellites(repo_root: Path) -> list[str]:
  restarted: list[str] = []
  for svc in ("atlas-atlas-1", "aicom-app-1", "alien-monitor"):
    proc = subprocess.run(["docker", "restart", svc], capture_output=True, text=True)
    if proc.returncode == 0:
      restarted.append(svc)
  return restarted


def cmd_apply(args: argparse.Namespace) -> int:
    api_key = (args.openrouter_key or "").strip()
    if not api_key and args.from_metis_env:
        try:
            api_key = _read_env_key_from_file(args.metis_env_path, "OPENROUTER_API_KEY")
        except RuntimeError:
            api_key = _read_env_key_from_remote(args.metis_ssh, args.metis_env_path, "OPENROUTER_API_KEY")
    if not api_key and args.openrouter_key_env:
        api_key = (os.environ.get(args.openrouter_key_env) or "").strip()
    if not api_key:
        print("ERROR: set OPENROUTER_API_KEY, --openrouter-key, or --from-metis-env", file=sys.stderr)
        return 1

    repo_root = Path(args.repo_root).resolve()
    report: dict[str, Any] = {"action": "apply", "ts": _ts()}

    if args.factory_hold and args.factory:
        report["factory_hold"] = apply_factory_hold()

    if args.factory:
        if args.in_docker:
            report["factory_openrouter"] = docker_exec_factory(repo_root, api_key)
        else:
            os.environ["OPENROUTER_API_KEY"] = api_key
            report["factory_openrouter"] = apply_factory_openrouter(api_key)
            report["env_file"] = str(apply_local_env(repo_root, api_key))

    if args.metis:
        if Path(args.metis_prod_yaml).is_file():
            report["metis"] = apply_metis_local(
                args.metis_prod_yaml,
                api_key,
                restart=not args.no_restart,
            )
        else:
            report["metis"] = apply_metis_remote(
                args.metis_ssh,
                args.metis_prod_yaml,
                api_key,
                restart=not args.no_restart,
            )

    if args.restart_containers and not args.in_docker:
        report["restarted"] = restart_factory_satellites(repo_root)

    print(json.dumps(report, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "action": "restore-deepseek",
                "note": "Restore latest *.bak-* beside prod.yaml / model_providers.yaml and set factory_on_hold false in Admin.",
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Emergency OpenRouter failover (MiniMax + Kimi-K3)")
    sub = parser.add_subparsers(dest="command", required=True)

    apply_p = sub.add_parser("apply", help="Switch ecosystem to OpenRouter")
    apply_p.add_argument("--repo-root", default=str(ROOT))
    apply_p.add_argument("--openrouter-key", default=None)
    apply_p.add_argument("--openrouter-key-env", default="OPENROUTER_API_KEY")
    apply_p.add_argument("--from-metis-env", action="store_true", help="Read OPENROUTER_API_KEY from Metis host .env")
    apply_p.add_argument("--metis-ssh", default=os.environ.get("METIS_SSH", "root@skopos.modelmarket.dev"))
    apply_p.add_argument("--metis-env-path", default="/opt/metis/.env")
    apply_p.add_argument("--metis-prod-yaml", default="/opt/metis/deploy/prod.yaml")
    apply_p.add_argument("--factory", action="store_true", default=True)
    apply_p.add_argument("--no-factory", action="store_true")
    apply_p.add_argument("--metis", action="store_true", default=True)
    apply_p.add_argument("--no-metis", action="store_true")
    apply_p.add_argument("--factory-hold", action="store_true", default=True)
    apply_p.add_argument("--no-factory-hold", action="store_true")
    apply_p.add_argument("--in-docker", action="store_true", help="Run factory patch via docker exec aicom-app-1")
    apply_p.add_argument("--restart-containers", action="store_true", default=True)
    apply_p.add_argument("--no-restart", action="store_true")
    apply_p.set_defaults(
        func=lambda a: cmd_apply(
            argparse.Namespace(
                **{
                    **vars(a),
                    "factory": a.factory and not a.no_factory,
                    "metis": a.metis and not a.no_metis,
                    "factory_hold": a.factory_hold and not a.no_factory_hold,
                    "restart_containers": a.restart_containers and not a.no_restart,
                }
            )
        )
    )

    restore_p = sub.add_parser("restore-deepseek", help="Print restore instructions")
    restore_p.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
