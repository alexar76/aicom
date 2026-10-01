#!/usr/bin/env python3
"""Ask every provider whether the model ids we are configured with still exist.

WHY THIS SHAPE, AND NOT A CHECK INSIDE THE REPOSITORY
-----------------------------------------------------
The id that actually goes on the wire is in NONE of the repository's layers:

  * ``data/config/model_providers.yaml`` is gitignored (``.gitignore:25``) — only the
    ``.example.yaml`` is tracked, and the example is not what any deployment runs.
  * The federation judge does not use ``llm/router.py`` at all. Its model lives in a
    container's or systemd unit's environment (``AIMARKET_FEDERATION_JUDGE_MODEL``).

So a checker that reads the repo checks a file nobody runs. This one runs ON A HOST and
reads that host's effective configuration and environment. Run it over ssh for a fleet.

Measured 2026-09-05, which is what this exists to prevent:
  * DeepSeek serves only deepseek-v4-flash / deepseek-v4-pro / deepseek-v4-flash-vision-exp.
    ``deepseek-chat`` appeared 57 times in the tree and is gone from DeepSeek's own API.
  * Groq's llama3-* were decommissioned, and their DOCUMENTED replacements
    (llama-3.3-70b-versatile / llama-3.1-8b-instant) were themselves past shutdown by then —
    which is exactly why a human picking "the obvious newer name" is not a mechanism.
  * ``claude-3-5-*-latest`` aliased snapshots that had already retired.

WHAT IT DOES NOT DO, DELIBERATELY
---------------------------------
It never writes, never repairs, never prints a key. A checker that edits configuration is a
checker that can blank a working deployment during a provider outage. It reports; a human or a
separate, explicit tool acts.

HOW IT DECIDES — AND WHY NOT FROM /v1/models
--------------------------------------------
By making one 1-token call per configured id, not by reading a listing. Providers disagree
about what a retired name does, so a listing cannot answer "will this work". Measured:

    DeepSeek    deepseek-chat / deepseek-reasoner / deepseek-coder  -> 200 OK,
                every one of them ANSWERED BY deepseek-v4-flash, and none of the three
                appears in DeepSeek's own /v1/models listing.
    OpenRouter  anthropic/claude-3-5-sonnet-latest -> 400 "is not a valid model ID"
                meta-llama/llama-3-70b-instruct    -> 404 "No endpoints found"

A gate built on the listing would have blocked a deploy over `deepseek-chat`, which works.

THREE VERDICTS
--------------
``ok``      the id answered, as itself.
``aliased`` it answered, but a DIFFERENT model did the work. Warn, never block. This is the
            state nobody can see today: ask for `deepseek-reasoner`, a reasoning model, and
            `deepseek-v4-flash` replies. The call succeeds and the bill is paid, so nothing
            complains — which is precisely why it needs saying out loud.
``dead``    the provider refused it (4xx naming the model). Exit 1: that call is already
            broken, so failing loudly costs nothing.

``unverifiable`` (no key, provider unreachable, transport error) is a WARNING and never fails
the run. Otherwise a provider outage or an unset key would turn this into a red light that
says nothing about our configuration, and a red light that lies gets muted.

Usage:
    python3 scripts/verify_model_ids.py                 # this host
    python3 scripts/verify_model_ids.py --json          # machine-readable
    python3 scripts/verify_model_ids.py --config PATH   # explicit config file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - a bare host may not have PyYAML
    yaml = None  # type: ignore[assignment]

#: Per-request timeout. Deliberately short: this runs before every deploy and publish, and a
#: provider that has not answered in 8s is not going to make the verdict any better.
TIMEOUT_S = float(os.getenv("AIMARKET_MODEL_PROBE_TIMEOUT_S", "8") or 8)

#: Total wall clock for the whole check. Measured: six probes against a TCP-accepting,
#: never-replying provider took exactly 6x the per-request timeout, serially. The example
#: config has 14 rows, so a partial outage meant minutes of silence before every deploy —
#: and under a CI job timeout that silence IS a block. Past the budget the remaining rows are
#: reported unverifiable, which never blocks, so the deploy proceeds instead of hanging.
TOTAL_BUDGET_S = float(os.getenv("AIMARKET_MODEL_PROBE_BUDGET_S", "45") or 45)

#: Where a host's effective config usually is, in the order we look. The repo's own
#: `core.paths.model_providers_path()` is preferred when importable, but this script must run
#: on a host with no dependencies installed, so it falls back to plain paths.
CONFIG_CANDIDATES = (
    "data/config/model_providers.yaml",
    "/app/data/config/model_providers.yaml",
    "/root/claudecode/aicom/data/config/model_providers.yaml",
    "/opt/aicom/data/config/model_providers.yaml",
    "/root/ecosystem/aicom/data/config/model_providers.yaml",
)


def _get_json(url: str, headers: dict[str, str]) -> Any:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _ids_from(payload: Any) -> list[str]:
    """Model ids out of an OpenAI-shaped or Anthropic-shaped listing."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data") or payload.get("models") or []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            ident = row.get("id") or row.get("name")
            if ident:
                out.append(str(ident))
        elif isinstance(row, str):
            out.append(row)
    return out


def _resolve_key(block: dict[str, Any], provider: str = "") -> str:
    """The key this provider would use, from the same places the router looks.

    Returned only so it can be sent in a header. It is never printed, logged or stored — the
    report says `key: yes/no`, never a value or a prefix.
    """
    inline = str(block.get("api_key") or "").strip()
    # `sk-keep` is this repo's placeholder for "the real one lives elsewhere".
    if inline and inline != "sk-keep":
        return inline
    env_name = block.get("api_key_env")
    if env_name:
        from_env = (os.environ.get(str(env_name)) or "").strip()
        if from_env:
            return from_env
    # `data/secrets/llm/<provider>_api_key` is where this repo actually keeps keys on a
    # workstation — `llm/persist_openrouter._resolve_api_key` reads the same place. Without
    # this fallback the publish-time gate is vacuous on a laptop: the key is right there on
    # disk, the environment is empty, and every row comes back "could not ask".
    if provider:
        # Provider ids carry an `_api` suffix that the filename does not repeat:
        # `deepseek_api` -> `deepseek_api_key`, matching what persist_openrouter.py writes.
        stem = provider[:-4] if provider.endswith("_api") else provider
        names = (f"{stem}_api_key", f"{provider}_api_key")
        for base in ("data/secrets/llm", os.path.expanduser("~/.aicom/secrets/llm")):
            path = next((os.path.join(base, n) for n in names
                         if os.path.isfile(os.path.join(base, n))), "")
            if path:
                try:
                    with open(path, encoding="utf-8") as fh:
                        found = fh.read().strip()
                    if found:
                        return found
                except OSError:
                    pass
    return ""


def list_models(name: str, block: dict[str, Any]) -> tuple[list[str] | None, str]:
    """(ids, note). ids is None when we could not ask — never an empty list for that."""
    base = str(block.get("base_url") or "").rstrip("/")
    if not base:
        return None, "no base_url"
    key = _resolve_key(block, name)
    ptype = str(block.get("provider_type") or "")

    if ptype == "anthropic":
        if not key:
            return None, "no key in env"
        url = f"{base}/models"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        # Local runtimes (ollama, lm_studio) legitimately need no key.
        needs_key = bool(block.get("api_key_env")) or bool(block.get("api_key"))
        if needs_key and not key:
            return None, "no key in env"
        url = f"{base}/models"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        if base.endswith(":11434"):  # ollama speaks its own dialect
            url = f"{base}/api/tags"

    try:
        return _ids_from(_get_json(url, headers)), ""
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - any transport failure is "could not ask"
        return None, type(exc).__name__




def _error_text(payload: Any) -> str:
    """Whatever a provider calls its error message. Full length — the caller truncates.

    Shapes seen in the wild: {"error": {"message": ...}}, {"error": "..."},
    {"detail": "..."} (FastAPI / vLLM), {"message": ...}. Reading only one of them is how a
    refusal gets mistaken for an answer.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("error", "detail", "message"):
        val = payload.get(key)
        if not val:
            continue
        if isinstance(val, dict):
            return str(val.get("message") or val.get("detail") or val)
        return str(val)
    return ""


#: Refusals that mention the model but are NOT about its existence. The deny-list wins,
#: because every one of these is a live model the gate would otherwise call dead:
#:   "Unsupported parameter: 'max_tokens' is not supported with this model."
#:       — provoked BY THIS SCRIPT: we send max_tokens:1, and OpenAI's reasoning family
#:         rejects it outright. The probe would fail the very models it is checking.
#:   "key not allowed to access model. This key can only access models=[...]"  — entitlement
#:   "Quota exceeded for model deployment."                                    — billing
_NOT_ABOUT_EXISTENCE = (
    "unsupported parameter", "not supported with this model", "use 'max_completion_tokens'",
    "not allowed to access", "can only access", "quota", "balance", "rate limit",
    "content management", "filtered", "billing", "payment", "insufficient",
)

#: Phrases that actually mean "this id is not a model here". An allow-list, so a message we
#: have never seen is UNVERIFIABLE rather than a deploy-stopping verdict.
_MEANS_NO_SUCH_MODEL = (
    "does not exist", "not a valid model", "no endpoints found", "unknown model",
    "unknown or retired", "decommissioned", "deprecated", "retired", "no such model",
    "model_not_found", "invalid model", "supported api model names",
    "is not available", "not found for model",
)


def _looks_like_the_model(text: str, model: str) -> bool:
    """Does this refusal mean the id does not exist — as opposed to a key, quota or parameter?

    Run against the FULL message, never a truncation: a provider that names the id at
    character 220 is still naming it, and cutting the text first is how nine of ten dead ids
    were classified as fine.

    "Contains the word model" was the first attempt and it was wrong in the expensive
    direction: three documented live-model refusals contain it, and one of them is caused by
    this script's own `max_tokens`. Deny-list first, then an allow-list of phrases that
    really do mean absence; anything unrecognised stays unverifiable and never blocks.
    """
    lowered = (text or "").lower()
    if any(p in lowered for p in _NOT_ABOUT_EXISTENCE):
        return False
    if any(p in lowered for p in _MEANS_NO_SUCH_MODEL):
        return True
    # Naming the id and nothing else recognisable: treat as absence only if the message is
    # short enough to be a bare "no such model" and mentions the id itself.
    return bool(model) and model.lower() in lowered and len(lowered) < 200


def probe_model(block: dict[str, Any], model: str, provider: str = "") -> tuple[str, str, str]:
    """Ask the provider to answer ONE token with this id. Returns (verdict, note, answered_as).

    A LISTING CANNOT DECIDE THIS, and finding that out is the whole reason this function
    exists. Measured 2026-09-05 against the two providers we hold keys for:

        DeepSeek    deepseek-chat      -> 200, answered as model=deepseek-v4-flash
                    deepseek-reasoner  -> 200, answered as model=deepseek-v4-flash
                    (neither is in its /v1/models listing)
        OpenRouter  anthropic/claude-3-5-sonnet-latest -> 400 "is not a valid model ID"
                    meta-llama/llama-3-70b-instruct    -> 404 "No endpoints found"

    So "absent from /v1/models" means "will fail" at OpenRouter and means nothing at all at
    DeepSeek. A gate built on the listing would have blocked deploys over ids that work.

    The third verdict is the one nobody has today. `deepseek-reasoner` — a REASONING model —
    is answered by `deepseek-v4-flash`. The call succeeds, the bill is paid, and a different
    model than the one chosen did the work, silently. That is worse than a hard failure,
    because a hard failure gets noticed. It warns; it does not block, because the deployment
    is working and stopping it would be the wrong trade.

    Costs one token per configured id.
    """
    base = str(block.get("base_url") or "").rstrip("/")
    key = _resolve_key(block, provider)
    ptype = str(block.get("provider_type") or "")
    if not base:
        return "unverifiable", "no base_url", ""
    needs_key = bool(block.get("api_key_env")) or bool(block.get("api_key"))
    if needs_key and not key:
        return "unverifiable", "no key in env", ""

    if ptype == "anthropic":
        url = f"{base}/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {"model": model, "max_tokens": 1,
                   "messages": [{"role": "user", "content": "hi"}]}
    else:
        url = f"{base}/chat/completions"
        headers = {"content-type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {"model": model, "max_tokens": 1,
                   "messages": [{"role": "user", "content": "hi"}]}

    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        full = ""
        try:
            full = _error_text(json.loads(exc.read().decode("utf-8", "replace")))
        except Exception:
            pass
        detail = full[:90]
        # A 4xx is only a DEAD MODEL if the provider's own message is about the model.
        #
        # This is the difference between a useful gate and one that gets switched off. A 400
        # also means a malformed request, an exhausted quota, a content filter, or a key the
        # provider dislikes — and blocking a deploy because someone's balance ran out is
        # exactly the false alarm that teaches people to pass --skip. Both providers we can
        # observe say it plainly when it IS the model:
        #   DeepSeek    "The supported API model names are deepseek-v4-pro, ..."
        #   OpenRouter  "totally/made-up-model is not a valid model ID"
        #               "No endpoints found for meta-llama/llama-3-70b-instruct."
        # so requiring the word costs nothing and removes the whole class of false blocks.
        # Anything else 4xx is "we could not ask", which never blocks.
        if exc.code in (400, 404) and _looks_like_the_model(full, model):
            return "dead", f"HTTP {exc.code} {detail}", ""
        return "unverifiable", f"HTTP {exc.code} {detail}", ""
    except Exception as exc:  # noqa: BLE001
        return "unverifiable", type(exc).__name__, ""

    # A 200 is not an answer. Providers refuse inside a 200 body — measured against a mock
    # emitting real-world shapes, four dead ids came back as flat "ok" because nothing here
    # looked past the status line. `ok` must require EVIDENCE OF A COMPLETION, not merely the
    # absence of an HTTP error.
    err = _error_text(body)
    if err:
        if _looks_like_the_model(err, model):
            return "dead", f"HTTP 200 with an error: {err[:90]}", ""
        return "unverifiable", f"HTTP 200 with an error: {err[:90]}", ""

    choices = (body or {}).get("choices")
    content = (body or {}).get("content")          # Anthropic's messages shape
    if not choices and not content:
        return "unverifiable", "200 with no completion in the body", ""

    answered = str((body or {}).get("model") or "")
    if answered and answered != model:
        return "aliased", f"answered by {answered}", answered
    return "ok", "", answered


def check_config(path: str, deadline: float | None = None) -> list[dict[str, Any]]:
    if yaml is None:
        return [{"provider": "-", "role": "-", "model": "-", "enabled": False,
                 "is_default": False, "verdict": "unverifiable",
                 "note": "PyYAML not installed"}]
    # A config this cannot read is NOT this check's business. Malformed YAML is a real
    # problem and `llm/startup_validation.py` and the router both say so clearly; failing
    # here would kill a deploy with a confusing "model id" error for an unrelated reason.
    # Measured: before this guard, broken YAML exited 1 with a raw traceback.
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        if not isinstance(cfg, dict):
            raise ValueError("top level is not a mapping")
    except Exception as exc:  # noqa: BLE001 - unreadable is unverifiable, never fatal
        return [{"provider": "-", "role": "-", "model": "-", "enabled": False,
                 "is_default": False, "verdict": "unverifiable",
                 "note": f"config unreadable ({type(exc).__name__}) — not this check's call"}]
    providers = cfg.get("providers") or {}
    default = cfg.get("default_provider")
    rows: list[dict[str, Any]] = []

    if not isinstance(providers, dict):
        return [{"provider": "-", "role": "-", "model": "-", "enabled": False,
                 "is_default": False, "verdict": "unverifiable",
                 "note": f"`providers:` is {type(providers).__name__}, expected a mapping"}]
    for name, block in providers.items():
        if not isinstance(block, dict):
            continue
        models = block.get("models")
        if not isinstance(models, dict):
            # A string or a list here is a config typo. Saying so is useful; crashing on it
            # and letting the caller report "a model id is dead" is a lie that blocks a deploy.
            if models:
                rows.append({"provider": name, "role": "-", "model": str(models)[:40],
                             "enabled": bool(block.get("enabled")), "is_default": name == default,
                             "verdict": "unverifiable",
                             "note": f"`models:` is {type(models).__name__}, expected a mapping"})
            continue
        configured = {role: str(mid) for role, mid in models.items() if mid}
        if not configured:
            continue
        for role, mid in sorted(configured.items()):
            if deadline is not None and time.monotonic() > deadline:
                verdict, detail, _answered = "unverifiable", "time budget exhausted", ""
            else:
                verdict, detail, _answered = probe_model(block, mid, name)
            served = None
            if verdict in ("dead", "aliased"):
                # Only now is a listing worth fetching: to say what you could pick instead.
                served, _ = list_models(name, block)
            rows.append({
                "provider": name,
                "role": role,
                "model": mid,
                "served": served,
                "enabled": bool(block.get("enabled")),
                "is_default": name == default,
                "verdict": verdict,
                "note": detail,
            })

    # A default pointing at a provider that is absent or disabled is its own defect: it worked
    # here only because a fallback happened to be enabled, which is luck, not configuration.
    if default:
        blk = providers.get(default)
        if not isinstance(blk, dict):
            rows.append({"provider": default, "role": "-", "model": "-", "enabled": False,
                         "is_default": True, "verdict": "warn",
                         "note": "default_provider names a provider that is not defined"})
        elif not blk.get("enabled"):
            rows.append({"provider": default, "role": "-", "model": "-", "enabled": False,
                         "is_default": True, "verdict": "warn",
                         "note": "default_provider is DISABLED — the fleet runs on a fallback"})
    return rows


def check_judge_env() -> list[dict[str, Any]]:
    """The federation judge: configured in env, invisible to any repo-only check."""
    url = (os.environ.get("AIMARKET_FEDERATION_JUDGE_URL") or "").strip()
    model = (os.environ.get("AIMARKET_FEDERATION_JUDGE_MODEL") or "").strip()
    key = (os.environ.get("AIMARKET_FEDERATION_JUDGE_KEY")
           or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not (url and model):
        return []
    base = url.split("/chat/completions")[0].rstrip("/")
    block = {"base_url": base, "api_key": key, "provider_type": "openai_compatible"}
    if not key:
        verdict, detail = "unverifiable", "no judge key in env"
    else:
        verdict, detail, _ = probe_model(block, model)
    return [{"provider": "federation_judge (env)", "role": "judge", "model": model,
             "enabled": True, "is_default": False, "verdict": verdict, "note": detail}]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=None, help="model_providers.yaml (default: autodetect)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument(
        "--suggest", action="store_true",
        help="on a dead id, print what the provider serves now. It PROPOSES, never writes: "
             "which model plays `heavy` is a decision about cost, latency and capability, and "
             "/v1/models answers none of those. Groq's listing still contains two ids that are "
             "past their shutdown date and three that are speech models — an automatic picker "
             "would put a text-to-speech model in the heavy slot and call it fresh.",
    )
    args = ap.parse_args()

    path = args.config
    if not path:
        for cand in CONFIG_CANDIDATES:
            if os.path.isfile(cand):
                path = cand
                break

    deadline = time.monotonic() + TOTAL_BUDGET_S
    rows: list[dict[str, Any]] = []
    if path:
        rows += check_config(path, deadline)
    rows += check_judge_env()

    if not rows:
        print("nothing to check on this host (no model_providers.yaml, no judge env)")
        return 0

    if args.as_json:
        print(json.dumps({"config": path, "rows": rows}, indent=1))
    else:
        print(f"config: {path or '(none)'}")
        for r in rows:
            mark = {"ok": "ok  ", "dead": "DEAD", "aliased": "ALIAS", "warn": "warn",
                    "unverifiable": "  ? "}
            flag = " *default" if r.get("is_default") else ""
            on = "" if r.get("enabled") else " (disabled)"
            print("  %s %-22s %-8s %-42s%s%s %s" % (
                mark.get(r["verdict"], "?"), r["provider"], r["role"], r["model"], on, flag,
                r.get("note", "")))

    if args.suggest:
        for r in rows:
            served = r.get("served")
            if not served:
                continue
            print(f"\n  {r['provider']} serves {len(served)} id(s) now — pick one for "
                  f"`{r['role']}` yourself:")
            for ident in sorted(served):
                print(f"      {ident}")
            print("      (check the provider's deprecation page too: a listed id can still be "
                  "past its shutdown date)")

    aliased = [r for r in rows if r["verdict"] == "aliased"]
    if aliased:
        print(f"\n{len(aliased)} id(s) are answered by a DIFFERENT model than the one "
              "configured. The calls work and the bills are paid, but the model doing the "
              "work is not the one chosen — DeepSeek answers `deepseek-reasoner` with "
              "`deepseek-v4-flash`. Not a failure; worth a decision.")
    # A provider the deployment does not load cannot break it. The example ships five
    # `enabled: false` blocks, and merely having GROQ_API_KEY exported in a shell was enough
    # to make the publish gate dial a provider this deployment never uses — and block on it.
    ignored = [r for r in rows if r["verdict"] == "dead" and not r.get("enabled")]
    if ignored:
        print(f"\n  ({len(ignored)} dead id(s) in DISABLED providers — reported, not blocking)")
    dead = [r for r in rows if r["verdict"] == "dead" and r.get("enabled")]
    if dead:
        print(f"\n{len(dead)} configured model id(s) the provider REFUSES — those calls fail.")
        return 1
    return 0


if __name__ == "__main__":
    # Exit codes are a contract with model_id_gate:
    #   0  nothing configured is dead
    #   1  a provider REFUSED a configured id — block the deploy
    #   2  this checker could not run (a bug here, an unreadable config, a shape it does not
    #      understand). NEVER 1: an unrunnable check must not masquerade as a verdict, or a
    #      typo'd base_url stops a deploy with "a configured model id is no longer served",
    #      which is both wrong and unfixable by the person reading it.
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"verify_model_ids: could not run ({type(exc).__name__}: {exc}) — not a verdict",
              file=sys.stderr)
        sys.exit(2)
