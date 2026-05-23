"""Tests for spot auction, agent personas, and capability NFT."""

import pytest

from aimarket_hub.spot_auction import AuctionBus, AuctionTask, Bid
from aimarket_hub.agent_personas import PersonaGenerator, AgentPersona
from aimarket_hub.capability_nft import CapabilityNFT, NFTRegistry


class TestAuctionBus:
    def test_post_task(self):
        bus = AuctionBus()
        task = bus.post_task("audit landing page", budget_usd=5.0, deadline_s=60)
        assert task.task_id
        assert task.status == "open"
        assert task.budget_usd == 5.0

    def test_place_and_pick_bid(self):
        bus = AuctionBus()
        task = bus.post_task("audit landing", budget_usd=5.0)
        bid = bus.place_bid(task.task_id, "hub1", "audit@v1", 2.10, 18000, 0.96)
        assert bid.provider_hub == "hub1"

        bids = bus.get_bids_for_task(task.task_id)
        assert len(bids) == 1

        result = bus.pick_bid(task.task_id, bid.bid_id)
        assert result["awarded_to"] == "hub1"
        assert result["price_usd"] == 2.10

    def test_place_bid_over_budget_raises(self):
        bus = AuctionBus()
        task = bus.post_task("audit", budget_usd=1.0)
        with pytest.raises(ValueError):
            bus.place_bid(task.task_id, "hub1", "audit@v1", 5.0, 1000)

    def test_place_bid_on_closed_task_raises(self):
        bus = AuctionBus()
        task = bus.post_task("audit", budget_usd=5.0)
        bid = bus.place_bid(task.task_id, "hub1", "audit@v1", 2.0, 1000)
        bus.pick_bid(task.task_id, bid.bid_id)  # Task is now awarded
        with pytest.raises(ValueError):
            bus.place_bid(task.task_id, "hub2", "audit@v1", 1.0, 1000)

    def test_expire_old_tasks(self):
        bus = AuctionBus()
        task = bus.post_task("audit", budget_usd=5.0, deadline_s=0)  # Immediate expiry
        import time
        time.sleep(0.1)
        expired = bus.expire_old_tasks()
        assert expired >= 1

    def test_get_my_bids(self):
        bus = AuctionBus()
        task = bus.post_task("test", budget_usd=5.0)
        bus.place_bid(task.task_id, "hub1", "a@v1", 1.0, 1000)
        bus.place_bid(task.task_id, "hub1", "b@v1", 1.5, 800)
        assert len(bus.get_my_bids("hub1")) == 2

    def test_stats(self):
        bus = AuctionBus()
        stats = bus.stats()
        assert "open_tasks" in stats
        assert "total_bids" in stats


class TestPersonaGenerator:
    def test_generates_persona(self):
        gen = PersonaGenerator(seed=42)
        persona = gen.generate("translate.multi@v2", "prod-001",
                               description="Translate text",
                               stats={"total_invocations": 412, "success_rate": 0.96, "avg_price_usd": 0.40})
        assert persona.name
        assert persona.full_name
        assert "Translator" in persona.role
        assert persona.introduce()
        assert "412" in persona.cv_blurb or "96%" in persona.cv_blurb

    def test_persona_deterministic(self):
        gen = PersonaGenerator(seed=42)
        p1 = gen.generate("translate.multi@v2", "p1")
        p2 = gen.generate("translate.multi@v2", "p1")
        assert p1.name == p2.name

    def test_discovery_entry(self):
        gen = PersonaGenerator(seed=42)
        p = gen.generate("legal.review@v1", "p1")
        entry = p.discovery_entry()
        assert "persona" in entry
        assert entry["persona"]["name"] == p.name

    def test_generate_for_product(self):
        gen = PersonaGenerator(seed=42)
        personas = gen.generate_for_product("p1", "Legal AI", [
            {"capability_id": "legal.review@v1", "description": "Review docs"},
            {"capability_id": "summarize@v1", "description": "Summarize"},
        ])
        assert len(personas) == 2
        assert personas[0].name != personas[1].name

    def test_default_avatar(self):
        gen = PersonaGenerator(seed=42)
        p = gen.generate("unknown_cap@v1", "p1")
        assert p.avatar_emoji


class TestNFTRegistry:
    def test_mint_nft(self):
        registry = NFTRegistry()
        nft = registry.mint("cap@v1", "p1", 100, 0.40, "0xAlice")
        assert nft.total_calls == 100
        assert nft.remaining_calls == 100
        assert nft.owner_address == "0xAlice"
        assert nft.price_per_call_usd == 0.40

    def test_transfer_nft(self):
        from aimarket_hub.signing import Signer
        registry = NFTRegistry()
        # Owner has a signing key registered
        alice_signer = Signer(key_path="/tmp/test_alice_key")
        registry.register_owner_pubkey("0xAlice", alice_signer.public_key_b64)

        nft = registry.mint("cap@v1", "p1", 100, 0.40, "0xAlice")
        canonical = f"transfer:{nft.token_id}:0xAlice:0xBob:0"
        sig = alice_signer.sign_canonical(canonical)
        result = registry.transfer(nft.token_id, "0xAlice", "0xBob", sig)
        assert result["transferred"]
        assert nft.owner_address == "0xBob"
        assert nft.transfer_count == 1

    def test_transfer_not_owner_fails(self):
        registry = NFTRegistry()
        nft = registry.mint("cap@v1", "p1", 100, 0.40, "0xAlice")
        result = registry.transfer(nft.token_id, "0xEve", "0xBob", "any-sig")
        assert "error" in result

    def test_transfer_without_signature_fails(self):
        """Transfer requires signature from owner's pubkey."""
        registry = NFTRegistry()
        nft = registry.mint("cap@v1", "p1", 100, 0.40, "0xAlice")
        result = registry.transfer(nft.token_id, "0xAlice", "0xBob")
        # Owner pubkey not registered → must error
        assert "error" in result

    def test_consume_call(self):
        registry = NFTRegistry()
        nft = registry.mint("cap@v1", "p1", 100, 0.40, "0xAlice")
        result = registry.consume_call(nft.token_id)
        assert result["consumed"]
        assert nft.remaining_calls == 99

    def test_nft_exhausted(self):
        registry = NFTRegistry()
        nft = registry.mint("cap@v1", "p1", 2, 0.40, "0xAlice")
        registry.consume_call(nft.token_id)
        registry.consume_call(nft.token_id)
        assert nft.is_exhausted
        result = registry.consume_call(nft.token_id)
        assert "error" in result

    def test_gift(self):
        from aimarket_hub.signing import Signer
        registry = NFTRegistry()
        alice_signer = Signer(key_path="/tmp/test_alice_gift_key")
        registry.register_owner_pubkey("0xAlice", alice_signer.public_key_b64)

        # First we mint to know the token_id for signing canonical
        # gift() handles mint + transfer atomically — we need a way to sign first.
        # Compute canonical for a known token_id pattern (transfer_count=0).
        # Simpler: do the mint manually, then call transfer with proper signature.
        nft_pre = registry.mint("cap@v1", "p1", 50, 0.40, "0xAlice")
        canonical = NFTRegistry.compute_gift_canonical(nft_pre.token_id, "0xAlice", "0xBob")
        sig = alice_signer.sign_canonical(canonical)
        result = registry.transfer(nft_pre.token_id, "0xAlice", "0xBob", sig)
        assert result["transferred"]
        assert nft_pre.owner_address == "0xBob"
        assert nft_pre.remaining_calls == 50

    def test_get_owned(self):
        registry = NFTRegistry()
        nft = registry.mint("cap@v1", "p1", 10, 0.40, "0xAlice")
        owned = registry.get_owned("0xAlice")
        assert len(owned) == 1
        assert registry.get_owned("0xBob") == []

    def test_stats(self):
        registry = NFTRegistry()
        registry.mint("a@v1", "p1", 100, 0.40, "0xAlice")
        registry.mint("b@v1", "p2", 50, 0.30, "0xBob")
        stats = registry.stats()
        assert stats["total_nfts"] == 2
        assert stats["active_nfts"] == 2

    def test_metadata(self):
        registry = NFTRegistry()
        nft = registry.mint("translate.multi@v2", "p1", 100, 0.40, "0xAlice")
        meta = nft.metadata()
        assert "AIMarket:" in meta["name"]
        assert meta["attributes"][0]["value"] == "translate.multi@v2"
