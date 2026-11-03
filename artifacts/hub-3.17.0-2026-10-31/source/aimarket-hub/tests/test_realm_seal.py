"""Escape attempts. Every one of these must fail.

UNI is a parallel chain of our own — Anvil, chain id 31337, our contracts, a USD-pegged
token funded from nowhere — and its whole point is that from inside it is indistinguishable
from the live economy. That only means something if the bubble is sealed, and before this it
was not: two defaults reached straight out of it.

* `chain_net` defaults `base` to public RPC endpoints and auto-loads
  `deployments/base-mainnet.json`, so a hub told "you are on base" inside a bubble read and
  wrote against Base mainnet addresses over the public internet.
* the x402 asset table hard-codes the REAL Base USDC contract and `eip155:8453`, so a 402
  issued inside the bubble was a payment offer valid on mainnet. An agent inside holding a
  funded real key could sign it, and that signature settles on Base — money leaving the
  simulation, which is the exact thing that must be impossible.

What is NOT claimed: hiding the chain id. A participant who signs anything needs it — it is
inside the EIP-712 domain separator — so an inside agent can always read which chain it is
on. The seal guarantees the half that matters: it can never act outside.
"""
from __future__ import annotations

import pytest

from pathlib import Path

from aimarket_hub import chain_net, realm, x402

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
UNI_TOKEN = "0x5FbDB2315678afecb367f032d93F642f64180aa3"  # a deterministic Anvil deployment


@pytest.fixture()
def uni(monkeypatch):
    monkeypatch.setenv("AIMARKET_CHAIN_REALM", "uni")
    monkeypatch.setenv("AIMARKET_UNI_CHAIN_ID", "31337")
    return monkeypatch


class TestTheBubbleCannotReachOut:
    def test_the_default_public_rpc_list_is_dropped(self, uni):
        """`base` presets four public endpoints. Inside the bubble there must be none."""
        spec = chain_net.network("base")
        assert spec.rpc_urls == (), f"the bubble kept public endpoints: {spec.rpc_urls}"

    def test_the_mainnet_address_table_is_dropped(self, uni):
        """The preset auto-loads real Base contracts when crypto is on."""
        spec = chain_net.network("base")
        assert spec.addresses == {}, f"the bubble kept live contracts: {spec.addresses}"

    def test_the_chain_id_is_the_private_one(self, uni):
        assert chain_net.network("base").chain_id == 31337

    def test_a_public_rpc_cannot_be_configured(self, uni):
        uni.setenv("AIMARKET_RPC_BASE", "https://mainnet.base.org")
        with pytest.raises(realm.RealmBreach) as exc:
            chain_net.network("base")
        assert "must not reach a real chain" in str(exc.value)

    def test_the_private_node_is_accepted(self, uni):
        uni.setenv("AIMARKET_RPC_BASE", "http://host.docker.internal:8545")
        spec = chain_net.network("base")
        assert spec.rpc_urls == ("http://host.docker.internal:8545",)

    def test_a_real_token_address_cannot_be_configured(self, uni):
        uni.setenv("AIMARKET_ADDR_BASE_USDC", BASE_USDC)
        with pytest.raises(realm.RealmBreach) as exc:
            chain_net.network("base")
        assert "real asset" in str(exc.value)

    def test_a_public_testnet_is_still_outside(self, uni):
        """Sepolia is not the bubble either — it is a real chain with real endpoints."""
        uni.setenv("AIMARKET_ADDR_BASE_USDC", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")
        with pytest.raises(realm.RealmBreach):
            chain_net.network("base")


class TestTheBubbleCannotIssueRealPaymentOffers:
    def test_no_terms_are_advertised_without_a_bubble_local_asset(self, uni):
        """The x402 table's default IS real Base USDC. Silence beats a mainnet offer."""
        uni.setenv("AIMARKET_X402_PAY_TO", "0x1218Ff3600000000000000000000000000000a0a")
        uni.setenv("AIMARKET_X402_CHAIN", "base")
        assert x402.payment_requirements(0.02) == []
        assert x402.payment_required_v2(0.02, "https://hub.example/x") is None

    def test_terms_use_the_private_chain_once_the_asset_is_local(self, uni):
        uni.setenv("AIMARKET_X402_PAY_TO", "0x1218Ff3600000000000000000000000000000a0a")
        uni.setenv("AIMARKET_X402_CHAIN", "base")
        uni.setenv("AIMARKET_X402_ASSET", UNI_TOKEN)
        terms = x402.payment_requirements(0.02)
        assert terms and terms[0]["network"] == "eip155:31337"
        assert terms[0]["asset"] == UNI_TOKEN
        assert x402.chain_id() == 31337

    def test_a_mainnet_payment_is_refused_inside_the_bubble(self, uni):
        """Somebody replays a real-Base authorization into the bubble: different network."""
        uni.setenv("AIMARKET_X402_PAY_TO", "0x1218Ff3600000000000000000000000000000a0a")
        uni.setenv("AIMARKET_X402_CHAIN", "base")
        uni.setenv("AIMARKET_X402_ASSET", UNI_TOKEN)
        result = x402.verify_payment(
            {
                "scheme": "exact", "network": "eip155:8453", "asset": BASE_USDC,
                "payload": {"authorization": {}, "signature": "0x" + "00" * 65},
            },
            price_usd=0.02,
        )
        assert result["ok"] is False
        assert "eip155:31337" in result["error"]


class TestLiveIsSealedToo:
    """The seal is symmetric: a live hub reading a simulated chain would report simulated
    money as real, which is the same lie pointed the other way."""

    def test_live_refuses_a_private_chain_id(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
        monkeypatch.setenv("AIMARKET_CHAIN", "bubblenet")
        monkeypatch.setenv("AIMARKET_CHAIN_ID", "31337")
        with pytest.raises(realm.RealmBreach) as exc:
            chain_net.network()
        assert "private chain" in str(exc.value)

    def test_live_refuses_a_loopback_rpc(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
        monkeypatch.setenv("AIMARKET_RPC_BASE", "http://127.0.0.1:8545")
        with pytest.raises(realm.RealmBreach) as exc:
            chain_net.network("base")
        assert "simulated chain" in str(exc.value)

    def test_the_live_default_is_untouched(self, monkeypatch):
        """Nothing about the reference deployment changes: no realm env, real network."""
        for var in ("AIMARKET_CHAIN_REALM", "AIMARKET_RPC_BASE", "AIMARKET_ADDR_BASE_USDC"):
            monkeypatch.delenv(var, raising=False)
        spec = chain_net.network("base")
        assert spec.chain_id == 8453
        assert spec.rpc_urls, "the live hub still needs its public endpoints"
        assert realm.realm() == "live"


class TestTheBubbleCanRunProductionPayments:
    """The seal is what lets the bubble be prod-shaped, which is the point of a simulation.

    `payment_readiness` refuses an Anvil address as the settlement recipient — correctly, on
    a live hub, because that key is public. Inside the bubble every address is an Anvil
    address, so the same rule would have made production-mode payments impossible there and
    forced UNI to run in a demo mode that behaves differently from LIVE. The guard now fires
    only where it means something.
    """

    ANVIL_HUB = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
    UNI_ESCROW = "0xf4Fe699cCEECE5e016521DDa25a4b8641248b624"

    def _readiness(self, monkeypatch, **env):
        from aimarket_hub.config import HubConfig

        for key, value in {
            "AIFACTORY_CRYPTO_ENABLED": "1", "AIFACTORY_PROD": "1",
            "AIFACTORY_PAYMENT_VERIFY_STUB": "0",
            # The bubble verifies deposits on its OWN chain for real; a demo-credit
            # shortcut would make it a fake inside a fake, and the suite's conftest turns
            # that on by default for every other test.
            "AIMARKET_ALLOW_DEMO_CREDIT": "0",
            "AIMARKET_PAYMENT_RECIPIENT": self.ANVIL_HUB,
            "AIMARKET_ESCROW_EVM_ADDRESS": self.UNI_ESCROW,
            **env,
        }.items():
            monkeypatch.setenv(key, value)
        return HubConfig().payment_readiness()

    def test_the_bubble_is_payment_ready_with_anvil_addresses(self, uni):
        assert self._readiness(uni) == []

    def test_the_boot_gate_agrees_with_the_readiness_gate(self, uni, monkeypatch, capsys):
        """Two gates check the same thing and must not disagree.

        `payment_readiness` reports; the CLI's own check REFUSES TO BOOT. Exempting only the
        first left the bubble unable to start in production mode at all — the second copy of
        a guard is exactly what this codebase has been bitten by before.
        """
        import aimarket_hub.cli as cli
        from aimarket_hub import realm

        assert realm.is_uni()
        source = Path(cli.__file__).read_text()
        assert "and not in_bubble" in source, (
            "the boot gate still refuses Anvil addresses unconditionally — UNI cannot start"
        )

    def test_a_live_hub_still_refuses_them(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
        reasons = self._readiness(monkeypatch)
        assert any("Anvil/Hardhat dev address" in r for r in reasons), reasons


class TestIndistinguishableFromInside:
    def test_the_network_keeps_its_name(self, uni):
        """Nothing in the bubble is labelled as a bubble."""
        spec = chain_net.network("base")
        assert spec.id == "base"
        assert spec.display_name == "Base"
        assert spec.testnet is False

    def test_the_realm_is_reported_only_to_the_operator(self, uni):
        described = realm.describe()
        assert described["realm"] == "uni"
        assert described["sealed"] is True
        assert "virtual" in str(described["note"])

    def test_the_public_manifest_says_nothing_about_the_realm(self, uni, tmp_path):
        from fastapi.testclient import TestClient

        from aimarket_hub.api import create_app
        from aimarket_hub.config import HubConfig
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.signing import Signer

        uni.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
        root = tmp_path / "hub"
        root.mkdir(parents=True, exist_ok=True)
        config = HubConfig()
        config.db_path = str(root / "hub.db")
        config.signing_key_path = str(root / "key")
        app = create_app(
            config=config, db=HubDatabase(root / "hub.db"), signer=Signer(root / "key"),
        )
        with TestClient(app) as client:
            body = client.get("/.well-known/ai-market.json").text
        assert '"uni"' not in body and "realm" not in body
        assert "simulated" not in body.lower()


def test_publish_accepts_the_gateway_the_invoke_path_may_already_call(monkeypatch):
    """The two gates must not disagree.

    The invoke path honours AIMARKET_INVOKE_HOST_GATEWAY; the publish gate knew only about
    loopback, so a hub could be configured to CALL an address it was forbidden to LIST —
    and the operator's own provider was unlistable for a reason the error never named. Not
    bubble-specific: any self-hosted hub with its provider on the docker gateway hits it.
    """
    from aimarket_hub.publish import _invoke_url_allowed

    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.delenv("AIMARKET_INVOKE_HOST_GATEWAY", raising=False)
    assert _invoke_url_allowed("http://127.0.0.1:9195/invoke")
    assert not _invoke_url_allowed("http://172.17.0.1:9195/invoke")

    monkeypatch.setenv("AIMARKET_INVOKE_HOST_GATEWAY", "172.17.0.1")
    assert _invoke_url_allowed("http://172.17.0.1:9195/invoke")
    # Still only the ONE address the operator named.
    assert not _invoke_url_allowed("http://10.0.0.5:9195/invoke")

    # And nothing is allowed without the opt-in at all.
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "0")
    assert not _invoke_url_allowed("http://172.17.0.1:9195/invoke")


def test_no_erc8004_declaration_points_out_of_the_bubble(uni):
    """The declaration names registries on a real chain and an agentId a reader is invited to
    resolve there — an identity leak where the asset one was a money leak."""
    uni.setenv("AIMARKET_ERC8004_AGENT_ID", "agent-1")
    uni.setenv("AIMARKET_ERC8004_NETWORK", "mainnet")
    assert x402.erc8004_declaration("https://hub.example") is None


def test_private_host_detection_covers_what_the_uni_stack_actually_uses():
    for host in ("localhost", "127.0.0.1", "10.1.2.3", "192.168.0.9", "host.docker.internal",
                 "anvil", "::1", "169.254.1.1"):
        assert realm.is_private_host(host), host
    for host in ("mainnet.base.org", "sepolia.base.org", "1.1.1.1", "modelmarket.dev"):
        assert not realm.is_private_host(host), host


# ── the federation door ───────────────────────────────────────────────────────────
#
# The chain seal was never the only way out. `federation_seeds.json` ships in the image with
# the six REAL satellites and their pinned keys, and `_parse_seed_list` falls back to that
# file whenever `AIMARKET_SEED_LIST` is empty — which is exactly how the bubble was deployed.
# Measured on the live bubble at uni.modelmarket.dev before this was fixed: its own
# /.well-known/ai-market.json published all six real hostnames under `federation.seed_list`.


def test_the_bubble_does_not_publish_the_real_ecosystems_addresses(uni, monkeypatch):
    """An agent inside the bubble could read the exact addresses of the world outside it.

    The seed list is not a private setting: it goes into `/.well-known/ai-market.json`, which
    is the first thing anything inside the bubble reads.
    """
    from aimarket_hub import config

    monkeypatch.delenv("AIMARKET_SEED_LIST", raising=False)
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://uni.example.dev")
    assert config._parse_seed_list() == []
    # The keys go with them: those pins are what would have made a real satellite trusted on
    # FIRST contact, with no approval step to stop it.
    assert config._parse_seed_pubkeys() == {}


def test_a_live_hub_still_gets_its_seeds(monkeypatch):
    """The fix must not quietly unfederate the real hub."""
    from aimarket_hub import config

    monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
    monkeypatch.delenv("AIMARKET_SEED_LIST", raising=False)
    seeds = config._parse_seed_list()
    assert len(seeds) >= 6
    assert any("atlas" in s for s in seeds)
    assert config._parse_seed_pubkeys()


def test_naming_an_outside_host_as_a_seed_is_a_startup_refusal(uni, monkeypatch):
    """One operator crawl would otherwise have indexed real, priced, outside-reachable
    endpoints into the bubble's catalogue — and a bubble invoke would then route real money
    to a real provider."""
    from aimarket_hub import config

    monkeypatch.setenv("AIMARKET_HUB_URL", "https://uni.example.dev")
    monkeypatch.setenv(
        "AIMARKET_SEED_LIST", "https://atlas.modelmarket.dev/.well-known/ai-market.json")
    with pytest.raises(realm.RealmBreach, match="outside host"):
        config._parse_seed_list()


def test_the_bubbles_own_satellites_are_allowed(uni, monkeypatch):
    """A bubble satellite lives behind the same public name as the bubble hub — which is also
    what lets it pass the crawler's private-address guard without weakening that guard."""
    from aimarket_hub import config

    monkeypatch.setenv("AIMARKET_HUB_URL", "https://uni.example.dev")
    monkeypatch.setenv(
        "AIMARKET_SEED_LIST",
        "https://uni.example.dev/sat/khronos/.well-known/ai-market.json,"
        "https://uni.example.dev/sat/kyma/.well-known/ai-market.json",
    )
    assert len(config._parse_seed_list()) == 2


def test_a_second_bubble_host_has_to_be_named_explicitly(uni, monkeypatch):
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://uni.example.dev")
    monkeypatch.setenv("AIMARKET_SEED_LIST", "https://sat.uni.example.dev/.well-known/ai-market.json")
    from aimarket_hub import config

    with pytest.raises(realm.RealmBreach):
        config._parse_seed_list()
    monkeypatch.setenv("AIMARKET_UNI_FEDERATION_HOSTS", "https://sat.uni.example.dev")
    assert len(config._parse_seed_list()) == 1


def test_the_seal_refuses_rather_than_guesses_when_it_cannot_tell_what_is_inside(uni, monkeypatch):
    """With no hub URL the seal has no definition of "inside". Failing open there would make
    the whole check decorative on exactly the deployment that forgot to configure itself."""
    monkeypatch.delenv("AIMARKET_HUB_URL", raising=False)
    monkeypatch.delenv("AIMARKET_UNI_FEDERATION_HOSTS", raising=False)
    with pytest.raises(realm.RealmBreach, match="cannot validate"):
        realm.check_seed("https://uni.example.dev/.well-known/ai-market.json")


def test_a_live_hub_refuses_a_private_seed(monkeypatch):
    """Symmetric, and for the same reason the rest of the seal is: a live hub seeding a
    simulated peer would report simulated capabilities as real stock, and would publish an
    unreachable internal name to every peer that reads its well-known."""
    monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
    with pytest.raises(realm.RealmBreach, match="private host"):
        realm.check_seed("http://172.17.0.1:9301/.well-known/ai-market.json")
