"""
Estimated USD cost for LLM calls logged to ``llm_calls.jsonl``.

Uses $/1M tokens — optionally **input/output** when usage splits exist, or **heavy/light**
provider rates when only totals exist (same rough ops visibility — not billing-grade).

Override defaults via ``/app/data/config/llm_pricing.yaml`` (optional).

Env:
  AIFACTORY_LLM_PRICING_YAML — path to YAML overrides (default: data/config/llm_pricing.yaml if exists).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from core.paths import llm_pricing_config_path
from llm.provider_ids import is_legacy_provider_id, normalize_llm_provider_id

_yaml_cache: tuple[float, dict[str, Any]] = (0.0, {})

# Blended USD per 1M total tokens (admin estimate only; vendor pricing changes frequently).
_BUILTIN_MODEL_USD_PER_MTOK: dict[str, float] = {
    "deepseek-chat": 0.27,
    "deepseek-reasoner": 0.95,
    "deepseek-coder": 0.27,
    "claude-3-5-sonnet-latest": 3.0,
    "claude-3-5-haiku-latest": 0.9,
    "gpt-4o": 5.0,
    "gpt-4o-mini": 0.35,
    "gpt-4-turbo": 10.0,
    "llama3-70b-8192": 0.59,
    "llama3-8b-8192": 0.05,
}

# Input / output USD per 1M tokens (when API returns prompt_tokens + completion_tokens).
_BUILTIN_MODEL_IN_OUT_PER_MTOK: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.14, 0.28),
    "deepseek-coder": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
    "claude-3-5-sonnet-latest": (3.0, 15.0),
    "claude-3-5-haiku-latest": (0.25, 1.25),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "llama3-70b-8192": (0.59, 0.79),
    "llama3-8b-8192": (0.05, 0.08),
}

_BUILTIN_PROVIDER_DEFAULT_USD_PER_MTOK: dict[str, float] = {
    "deepseek_api": 0.35,
    "deep-seek": 0.35,  # legacy id in old configs / llm_calls.jsonl
    "dee-seek": 0.35,  # legacy id in old llm_calls.jsonl
    "deepseek": 0.35,
    "groq_api": 0.08,
    "together_ai": 0.55,
    "anthropic_cloud": 2.5,
    "openai_compatible": 0.5,
}

# Optional per-role fallback when only total tokens are known (heavy vs light model ids).
_BUILTIN_PROVIDER_ROLE_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "deepseek_api": {"heavy": 0.40, "light": 0.22},
    "deep-seek": {"heavy": 0.40, "light": 0.22},
    "groq_api": {"heavy": 0.08, "light": 0.05},
}

_DEFAULT_FALLBACK_PER_MTOK = 0.5


def _pricing_yaml_path() -> Path:
    return llm_pricing_config_path()


def _load_pricing_overrides() -> dict[str, Any]:
    global _yaml_cache
    p = _pricing_yaml_path()
    try:
        mtime = p.stat().st_mtime if p.is_file() else 0.0
    except OSError:
        mtime = 0.0
    if mtime == _yaml_cache[0] and _yaml_cache[1]:
        return _yaml_cache[1]
    if not p.is_file():
        _yaml_cache = (mtime, {})
        return {}
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        data = raw if isinstance(raw, dict) else {}
        _yaml_cache = (mtime, data)
        return data
    except Exception:
        _yaml_cache = (mtime, {})
        return {}


def _norm_role(role: Optional[str]) -> str:
    r = str(role or "").strip().lower()
    return r if r in ("heavy", "light") else "heavy"


def _model_yaml_entry(model: str) -> Any:
    m = (model or "").strip().lower()
    if not m:
        return None
    ov = _load_pricing_overrides().get("models")
    if not isinstance(ov, dict):
        return None
    for key, val in ov.items():
        if str(key).strip().lower() == m:
            return val
    for key, val in ov.items():
        ks = str(key).strip().lower()
        if ks and ks in m:
            return val
    return None


def _rates_model_in_out(model: str) -> Optional[tuple[float, float]]:
    """Return (input_per_mtok, output_per_mtok) if configured."""
    raw = _model_yaml_entry(model)
    if isinstance(raw, dict):
        inp = raw.get("input_per_mtok")
        outp = raw.get("output_per_mtok")
        if isinstance(inp, (int, float)) and isinstance(outp, (int, float)):
            return float(inp), float(outp)
    m = (model or "").strip().lower()
    return _BUILTIN_MODEL_IN_OUT_PER_MTOK.get(m)


def _rate_for_model(model: str) -> Optional[float]:
    """Blended $/Mtok for model (YAML float or builtin)."""
    m = (model or "").strip().lower()
    if not m:
        return None
    raw = _model_yaml_entry(model)
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        b = raw.get("blended_per_mtok")
        if isinstance(b, (int, float)):
            return float(b)
    ov = _load_pricing_overrides().get("models")
    if isinstance(ov, dict):
        for key, val in ov.items():
            if str(key).strip().lower() == m and isinstance(val, (int, float)):
                return float(val)
        for key, val in ov.items():
            ks = str(key).strip().lower()
            if ks and ks in m and isinstance(val, (int, float)):
                return float(val)
    return _BUILTIN_MODEL_USD_PER_MTOK.get(m)


def _provider_yaml_entry(provider: str) -> Any:
    canon = normalize_llm_provider_id(provider).lower()
    if not canon:
        return None
    ov = _load_pricing_overrides().get("providers")
    if not isinstance(ov, dict):
        return None
    for key in (canon, (provider or "").strip().lower()):
        if key and key in ov:
            return ov[key]
    return None


def _rate_for_provider(provider: str) -> Optional[float]:
    canon = normalize_llm_provider_id(provider).lower()
    if not canon:
        return None
    raw = _provider_yaml_entry(provider)
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        b = raw.get("blended_per_mtok")
        if isinstance(b, (int, float)):
            return float(b)
    return _BUILTIN_PROVIDER_DEFAULT_USD_PER_MTOK.get(canon)


def _rate_for_provider_role(provider: str, model_role: Optional[str]) -> Optional[float]:
    """$/Mtok when only total tokens are known; uses heavy/light if configured."""
    canon = normalize_llm_provider_id(provider).lower()
    role = _norm_role(model_role)
    raw = _provider_yaml_entry(provider)
    if isinstance(raw, dict):
        hk = "heavy_per_mtok" if role == "heavy" else "light_per_mtok"
        lk = "light_per_mtok" if role == "heavy" else "heavy_per_mtok"
        v = raw.get(hk)
        if isinstance(v, (int, float)):
            return float(v)
        # fall back to sibling role then blended keys inside dict
        v2 = raw.get(lk)
        if isinstance(v2, (int, float)):
            return float(v2)
        b = raw.get("blended_per_mtok")
        if isinstance(b, (int, float)):
            return float(b)
    # Prefer per-role built-ins before a single blended default for the provider.
    role_map = _BUILTIN_PROVIDER_ROLE_USD_PER_MTOK.get(canon)
    if isinstance(role_map, dict):
        rv = role_map.get(role)
        if isinstance(rv, (int, float)):
            return float(rv)
    return _rate_for_provider(provider)


def _global_default_per_mtok() -> float:
    ov = _load_pricing_overrides()
    if isinstance(ov.get("default_per_mtok"), (int, float)):
        return float(ov["default_per_mtok"])
    return _DEFAULT_FALLBACK_PER_MTOK


def estimate_llm_call_cost_usd(
    provider: str,
    model: str,
    tokens_used: int | float | None = None,
    *,
    prompt_tokens: int | float | None = None,
    completion_tokens: int | float | None = None,
    model_role: str | None = None,
) -> Optional[float]:
    """
    Estimated USD for one call.

    If ``prompt_tokens`` and ``completion_tokens`` are both set (typical OpenAI usage),
    applies input/output rates when available; otherwise blended on the sum.

    If only totals are available, uses model blended rate, then provider role (heavy/light),
    then provider default, then global default.
    """
    provider = normalize_llm_provider_id(provider)
    pt: Optional[float] = None
    ct: Optional[float] = None
    try:
        if prompt_tokens is not None:
            pt = float(prompt_tokens)
        if completion_tokens is not None:
            ct = float(completion_tokens)
    except (TypeError, ValueError):
        pt, ct = None, None

    use_split = pt is not None and ct is not None and (pt > 0 or ct > 0)
    total_from_usage = (pt + ct) if use_split and pt is not None and ct is not None else None

    tot: Optional[float] = None
    try:
        if tokens_used is not None:
            tot = float(tokens_used)
    except (TypeError, ValueError):
        tot = None

    if total_from_usage is not None and total_from_usage > 0:
        token_basis: Optional[float] = total_from_usage
    elif tot is not None and tot > 0:
        token_basis = tot
    else:
        return None

    # ── Input/output split pricing ─────────────────────────────────────────
    if use_split and pt is not None and ct is not None:
        rates_io = _rates_model_in_out(model)
        if rates_io is not None:
            inp_r, out_r = rates_io
            usd = (max(pt, 0.0) / 1_000_000.0) * inp_r + (max(ct, 0.0) / 1_000_000.0) * out_r
            return round(usd, 6)
        blended = _rate_for_model(model)
        if blended is not None:
            usd = ((max(pt, 0.0) + max(ct, 0.0)) / 1_000_000.0) * blended
            return round(usd, 6)
        rate = _rate_for_provider_role(provider, model_role)
        if rate is None:
            rate = _rate_for_provider(provider)
        if rate is None:
            rate = _global_default_per_mtok()
        usd = ((max(pt, 0.0) + max(ct, 0.0)) / 1_000_000.0) * rate
        return round(usd, 6)

    # ── Total tokens only ────────────────────────────────────────────────
    if token_basis is None or token_basis <= 0:
        raise ValueError("token_basis must be a positive number")
    rate = _rate_for_model(model)
    if rate is None:
        rate = _rate_for_provider_role(provider, model_role)
    if rate is None:
        rate = _rate_for_provider(provider)
    if rate is None:
        rate = _global_default_per_mtok()
    usd = (token_basis / 1_000_000.0) * rate
    return round(usd, 6)


def enrich_llm_log_entry(entry: dict[str, Any]) -> None:
    """Mutates JSONL dict in-place: sets ``estimated_cost_usd`` when missing."""
    if not isinstance(entry, dict):
        return
    raw_provider = str(entry.get("provider") or "")
    provider = normalize_llm_provider_id(raw_provider)
    if provider and provider != raw_provider:
        entry["provider"] = provider
        if raw_provider and entry.get("provider_legacy") is None:
            entry["provider_legacy"] = raw_provider
    if entry.get("estimated_cost_usd") is not None:
        return
    model = str(entry.get("model") or "")
    tokens = entry.get("tokens_used")

    def _num(x: Any) -> Optional[float]:
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return float(x)
        return None

    pt = _num(entry.get("prompt_tokens"))
    ct = _num(entry.get("completion_tokens"))
    mr = entry.get("model_role")
    cost = estimate_llm_call_cost_usd(
        provider,
        model,
        tokens,
        prompt_tokens=pt,
        completion_tokens=ct,
        model_role=str(mr) if mr is not None else None,
    )
    if cost is not None:
        entry["estimated_cost_usd"] = cost


def invalidate_pricing_yaml_cache() -> None:
    """Call after editing ``llm_pricing.yaml`` on disk."""
    global _yaml_cache
    _yaml_cache = (0.0, {})


def effective_provider_fallback_usd_per_mtok(
    provider: str,
) -> tuple[float, str]:
    """
    Blended $/1M tokens used when the model id has no specific rate (same chain as estimate).

    Returns (rate, source) where source is override | builtin | default_yaml | default_builtin.
    """
    canon = normalize_llm_provider_id(provider).lower()
    if not canon:
        return _DEFAULT_FALLBACK_PER_MTOK, "default_builtin"
    raw = _provider_yaml_entry(provider)
    if isinstance(raw, (int, float)):
        return float(raw), "override"
    if isinstance(raw, dict):
        b = raw.get("blended_per_mtok")
        if isinstance(b, (int, float)):
            return float(b), "override"
    if canon in _BUILTIN_PROVIDER_DEFAULT_USD_PER_MTOK:
        return _BUILTIN_PROVIDER_DEFAULT_USD_PER_MTOK[canon], "builtin"
    d = _load_pricing_overrides().get("default_per_mtok")
    if isinstance(d, (int, float)):
        return float(d), "default_yaml"
    return _DEFAULT_FALLBACK_PER_MTOK, "default_builtin"


def yaml_override_usd_per_mtok_for_provider(provider: str) -> Optional[float]:
    """Blended override in YAML for this provider id (scalar or blended_per_mtok), if any."""
    raw = _provider_yaml_entry(provider)
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        b = raw.get("blended_per_mtok")
        if isinstance(b, (int, float)):
            return float(b)
    return None


def builtin_provider_fallback_usd_per_mtok(provider: str) -> Optional[float]:
    """Built-in default $/1M for provider id (no YAML)."""
    canon = normalize_llm_provider_id(provider).lower()
    if not canon:
        return None
    return _BUILTIN_PROVIDER_DEFAULT_USD_PER_MTOK.get(canon)


def migrate_llm_calls_provider_ids(
    path: Path,
    *,
    dry_run: bool = False,
    re_enrich_cost: bool = True,
) -> dict[str, int]:
    """
    Rewrite legacy ``provider`` ids in ``llm_calls.jsonl`` to canonical names (in-place).

    Sets ``provider_legacy`` when the id changes. Optionally recomputes ``estimated_cost_usd``.
    """
    stats = {"lines": 0, "migrated": 0, "re_enriched": 0, "skipped": 0, "errors": 0}
    if not path.is_file():
        return stats

    out_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        stats["lines"] += 1
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            stats["errors"] += 1
            out_lines.append(line)
            continue
        if not isinstance(entry, dict):
            stats["skipped"] += 1
            out_lines.append(line)
            continue

        raw = str(entry.get("provider") or "")
        if is_legacy_provider_id(raw):
            canon = normalize_llm_provider_id(raw)
            entry["provider"] = canon
            if entry.get("provider_legacy") is None:
                entry["provider_legacy"] = raw
            stats["migrated"] += 1
            if re_enrich_cost:
                entry.pop("estimated_cost_usd", None)
                enrich_llm_log_entry(entry)
                if entry.get("estimated_cost_usd") is not None:
                    stats["re_enriched"] += 1

        out_lines.append(json.dumps(entry, ensure_ascii=False))

    if not dry_run and stats["migrated"] > 0:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")

    return stats


def write_llm_pricing_provider_rate(provider: str, usd_per_mtok: Optional[float]) -> None:
    """
    Persist or remove provider-tier rate in ``llm_pricing.yaml``.
    ``usd_per_mtok`` None removes the override; other keys in the file are preserved.
    """
    path = _pricing_yaml_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            data = raw if isinstance(raw, dict) else {}
        except Exception:
            data = {}
    prov = data.setdefault("providers", {})
    if not isinstance(prov, dict):
        prov = {}
        data["providers"] = prov
    key = (provider or "").strip().lower()
    if not key:
        raise ValueError("provider id is required")
    if usd_per_mtok is None:
        prov.pop(key, None)
    else:
        prov[key] = float(usd_per_mtok)
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    invalidate_pricing_yaml_cache()
