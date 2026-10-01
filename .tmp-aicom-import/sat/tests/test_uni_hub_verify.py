"""The UNI hub's post-start verifier must refuse exactly what the 2026-09-16 redeploy did.

A stale copy of the deploy script brought the bubble hub back healthy with six published
fixes undone, and nothing noticed for eight days. These pin that the verifier fails each
one of them, and passes the configuration that was restored on 2026-09-24.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("uni_hub_verify", ROOT / "deploy" / "uni-hub-verify.py")
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)
sys.path.insert(0, str(ROOT / "scripts"))
import ecosystem_alert  # noqa: E402

BASE = "https://uni.modelmarket.dev"
SATS = ("khronos", "kyma", "psephos", "stoicheion", "diktyon", "horizon")


def good_env() -> dict[str, str]:
    seeds = [f"{BASE}/sat/{s}/.well-known/ai-market.json" for s in SATS]
    return {
        "AIMARKET_HUB_URL": BASE,
        "AIMARKET_ADMIN_TOKEN": "x" * 43,
        "AIMARKET_AUTO_CRAWL": "1",
        "AIMARKET_SEED_LIST": ",".join(seeds),
        "AIMARKET_SEED_PUBKEYS": json.dumps({s: "key" for s in seeds}),
        "AIMARKET_SELLS_FOR": ",".join(f"{BASE}/sat/{s}" for s in SATS),
        "AIMARKET_CHAIN_REALM": "uni",
    }


def failed(env: dict[str, str]) -> list[str]:
    return [rule for rule, holds in verify.rules(env, BASE) if not holds]


def test_the_restored_configuration_passes():
    assert failed(good_env()) == []


def test_the_2026_09_16_regression_fails_six_ways():
    env = dict(good_env(),
               AIMARKET_HUB_URL="http://127.0.0.1:9183",
               AIMARKET_ADMIN_TOKEN="uni-admin-token-not-a-secret-in-a-bubble",
               AIMARKET_AUTO_CRAWL="0",
               AIMARKET_SEED_LIST="")
    env.pop("AIMARKET_SEED_PUBKEYS")
    env.pop("AIMARKET_SELLS_FOR")
    assert len(failed(env)) == 6


def test_an_outside_seed_is_refused():
    """The committed federation_seeds.json names REAL satellites; the bubble must not."""
    env = good_env()
    env["AIMARKET_SEED_LIST"] += ",https://atlas.modelmarket.dev/.well-known/ai-market.json"
    assert any("seed list" in r for r in failed(env))


def test_a_seed_without_a_pin_is_refused():
    env = good_env()
    pins = json.loads(env["AIMARKET_SEED_PUBKEYS"])
    pins.pop(next(iter(pins)))
    env["AIMARKET_SEED_PUBKEYS"] = json.dumps(pins)
    assert any("pinned key" in r for r in failed(env))


def test_every_published_token_is_refused_as_the_admin_token():
    for token in verify.PUBLISHED_ADMIN_TOKENS:
        assert failed(dict(good_env(), AIMARKET_ADMIN_TOKEN=token)), token


def test_the_verifier_and_the_alerter_agree_on_the_published_tokens():
    assert verify.PUBLISHED_ADMIN_TOKENS == ecosystem_alert.PUBLISHED_ADMIN_TOKENS


def test_the_deploy_script_runs_the_verifier_and_can_boot_the_current_image():
    script = (ROOT / "deploy" / "uni-hub.sh").read_text(encoding="utf-8")
    assert "uni-hub-verify.py" in script
    # Current hub images refuse to start without a durable sandbox trial ledger.
    assert "AIMARKET_SANDBOX_DB_PATH=/app/data/" in script
    assert "AIMARKET_AUTO_CRAWL=1" in script
