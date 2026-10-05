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
        "AIMARKET_PQC": "1",
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


def test_a_classical_only_hub_is_refused():
    """2026-10-05: recreated without AIMARKET_PQC, the hub signed Ed25519 only and stayed green."""
    env = good_env()
    env.pop("AIMARKET_PQC")
    assert failed(env) == ["signs hybrid Ed25519 + ML-DSA-65 (AIMARKET_PQC)"]


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


# ── the money side (2026-10-01 host move) ────────────────────────────────────────────────
SETTLE, DEMO = "http://172.17.0.1:8546", "http://172.17.0.1:8545"
TOKEN, ESCROW, HUB = "0x5fbd", "0xe7f1", "0x7099"
LOTTERY = "0xdc64"


def chain_env(**over) -> dict[str, str]:
    env = {
        "AIMARKET_RPC_BASE": SETTLE, "ALIEN_EVM_RPC": DEMO,
        "AIMARKET_ADDR_BASE_USDC": TOKEN, "AIMARKET_X402_ASSET": TOKEN,
        "AIMARKET_ADDR_BASE_AIMARKETESCROW": ESCROW, "AIMARKET_ESCROW_CONTRACT": ESCROW,
        "AIMARKET_ESCROW_EVM_ADDRESS": ESCROW,
        "AIMARKET_PAYMENT_RECIPIENT": HUB, "AIMARKET_X402_PAY_TO": HUB, "AIMARKET_ESCROW_HUB_ADDRESS": HUB,
        "AIMARKET_CHARITY_LOTTERY_ADDRESS": LOTTERY,
    }
    env.update(over)
    return env


def chains(code_on: dict[str, set[str]]):
    def get_code(rpc, address):
        if rpc not in code_on:
            raise OSError("connection refused")
        return "0x60806040" if address in code_on[rpc] else "0x"
    return get_code


LIVE = chains({SETTLE: {TOKEN, ESCROW}, DEMO: {LOTTERY}})


def chain_failed(env, get_code=LIVE) -> list[str]:
    return [rule for rule, holds in verify.chain_rules(env, get_code) if not holds]


def test_the_restored_chain_configuration_passes():
    assert chain_failed(chain_env()) == []


def test_the_2026_10_01_move_is_refused():
    """Hub on the demo chain, with a token, escrow and lottery the demo chain's reset erased,
    and paid at Anvil #0."""
    env = chain_env(AIMARKET_RPC_BASE=DEMO, AIMARKET_ADDR_BASE_USDC="0xc634", AIMARKET_X402_ASSET="0xc634",
                    AIMARKET_ADDR_BASE_AIMARKETESCROW="0xd1a1", AIMARKET_ESCROW_CONTRACT="0xd1a1",
                    AIMARKET_ESCROW_EVM_ADDRESS="0xd1a1", AIMARKET_PAYMENT_RECIPIENT="0xf39f",
                    AIMARKET_X402_PAY_TO="0xf39f", AIMARKET_CHARITY_LOTTERY_ADDRESS="0x5910")
    assert len(chain_failed(env)) == 5  # all but "one token everywhere", which held


def test_a_missing_bubble_chain_is_refused():
    assert "the settlement token exists on the settlement chain" in chain_failed(
        chain_env(), chains({DEMO: {LOTTERY}}))
