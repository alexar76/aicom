"""One transfer, one credit — across the hub and the Factory.

The hub image does not ship the web stack, so it claims deposits with its own copy of the
registry (aimarket_hub/deposit_claims.py) while the Factory uses
web/backend/services/ai_market_protocol/on_chain.py. They are one registry only when both
name a claim the same way and both write the same directory; either difference lets one
transfer fund a hub channel and also buy a Factory license.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from web.backend.services.ai_market_protocol import on_chain as factory_claims

ROOT = Path(__file__).resolve().parents[1]
HUB_CLAIMS_FILE = ROOT / "aimarket-hub" / "aimarket_hub" / "deposit_claims.py"
REBUILD = ROOT / "scripts" / "deploy_hub_rebuild.sh"

TX = "0x" + "ab" * 32


def _hub_claims():
    spec = importlib.util.spec_from_file_location("hub_deposit_claims_under_test", HUB_CLAIMS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hub_claims = _hub_claims()


@pytest.mark.parametrize("chain,tx", [
    ("base", TX),
    ("Base", TX.upper().replace("0X", "0x")),
    (" base ", "0X" + "AB" * 32),
    ("base", "ab" * 32),                                   # bare hex, no 0x
    ("solana", "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"),
])
def test_both_doors_name_a_claim_the_same_way(chain, tx):
    assert hub_claims.deposit_claim_key(chain, tx) == factory_claims.deposit_claim_key(chain, tx)


def test_a_base58_signature_stays_case_significant():
    sig = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"
    assert hub_claims.deposit_claim_key("solana", sig) != hub_claims.deposit_claim_key("solana", sig.lower())


@pytest.fixture
def shared_dir(tmp_path, monkeypatch):
    d = tmp_path / "shared-claims"
    monkeypatch.setenv("AIMARKET_DEPOSIT_CLAIMS_DIR", str(d))
    return d


def test_a_hub_claim_blocks_the_factory(shared_dir):
    got = hub_claims.claim_deposit(chain="base", tx_hash=TX, stack="aimarket-hub", claim_id="ch-1")
    assert got["ok"], got
    again = factory_claims.claim_deposit(chain="Base", tx_hash=TX.upper().replace("0X", "0x"),
                                         stack="web-checkout", claim_id="order-1")
    assert again == {"ok": False, "error": "already_claimed", "claim": got["claim"]}


def test_a_factory_claim_blocks_the_hub(shared_dir):
    got = factory_claims.claim_deposit(chain="base", tx_hash="ab" * 32, stack="web-checkout", claim_id="order-1")
    assert got["ok"], got
    again = hub_claims.claim_deposit(chain="base", tx_hash=TX, stack="aimarket-hub", claim_id="ch-1")
    assert again["ok"] is False and again["error"] == "already_claimed"


def test_a_named_directory_that_cannot_be_written_refuses_on_both_sides(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setenv("AIMARKET_DEPOSIT_CLAIMS_DIR", str(blocker / "claims"))
    fallback = tmp_path / "local"
    for module in (hub_claims, factory_claims):
        got = module.claim_deposit(chain="base", tx_hash=TX, stack="s", claim_id="c", fallback_dir=fallback)
        assert got == {"ok": False, "error": "deposit_registry_unavailable"}
    assert not fallback.exists(), "a configured registry must never be swapped for a local one"


# ── The hub rollout wires the shared directory ───────────────────────────────────────────
def _script() -> str:
    return REBUILD.read_text(encoding="utf-8")


def _docker_run(script: str) -> str:
    m = re.search(r"^docker run -d --name \"\$NAME\".*?\"\$IMAGE\"$", script, re.S | re.M)
    assert m, "the hub's docker run is no longer recognisable"
    return m.group(0)


def test_the_hub_container_gets_the_shared_registry():
    run = _docker_run(_script())
    assert '-e AIMARKET_DEPOSIT_CLAIMS_DIR="$CLAIMS_DIR_IN_HUB"' in run
    assert '-v "${CLAIMS_HOST_DIR}:${CLAIMS_DIR_IN_HUB}"' in run
    # The export stays read-only; the registry is the only writable piece of the Factory tree.
    assert '-v "${FACTORY_EXPORT}:/factory_data:ro"' in run


def test_the_registry_defaults_to_where_the_factory_writes_it():
    script = _script()
    default = re.search(r'CLAIMS_HOST_DIR="\$\{AIMARKET_DEPOSIT_CLAIMS_HOST_DIR:-([^}]+)\}"', script)
    assert default, "the host directory is no longer configurable"
    # The Factory's default: $AIFACTORY_DATA_ROOT/state/ai_market/deposit_claims, with ./data
    # bind-mounted from the runtime tree the CI deploy syncs into.
    deploy = (ROOT / ".gitea" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    dest = re.search(r"DEST=(\S+)", deploy).group(1)
    assert default.group(1) == f"{dest}/data/" + "/".join(factory_claims._SHARED_CLAIMS_SUBPATH)


def test_the_rollout_checks_what_the_hub_resolved_and_rolls_back():
    script = _script()
    check = script.index("from aimarket_hub.deposit_claims import deposit_claims_dir")
    assert check < script.index('if [[ -n "$fail" ]]; then'), "checked after the rollback decision"
    assert '[[ "$resolved" == "$CLAIMS_DIR_IN_HUB" ]]' in script


def test_the_hubs_earlier_claims_are_carried_without_overwrite():
    script = _script()
    assert '[[ -e "$CLAIMS_HOST_DIR/${claim##*/}" ]] && continue' in script
    assert script.index("carried=$((carried + 1))") < script.index('log "Swapping containers"')
