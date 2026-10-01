"""The satellite against the hub's OWN code — not against my reading of it.

A satellite that merely looks right gets indexed as zero capabilities and says nothing about
why. So these tests import the hub's real `Signer`, `validate_well_known` and
`validate_manifest` and put the satellite's actual documents through them. If the canonical
string drifts by one separator, or a required field is renamed upstream, this fails here
rather than silently on a production crawl.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aimarket-hub"))

from uni.capabilities import load_catalogue  # noqa: E402
from uni.satellite import (  # noqa: E402
    Satellite, Signer, manifest_canonical, provider_canonical,
)

hub_signing = pytest.importorskip(
    "aimarket_hub.signing", reason="hub package not importable in this environment")
hub_validator = pytest.importorskip("aimarket_hub.validator")


@pytest.fixture()
def sat(tmp_path):
    return Satellite(load_catalogue("khronos"), "https://uni.example.dev/sat/khronos",
                     Signer(tmp_path / "key.pem"))


class TestTheDocumentsThePeerServes:
    def test_the_well_known_passes_the_hubs_own_validator(self, sat):
        assert hub_validator.validate_well_known(sat.well_known()) == []

    def test_the_manifest_passes_the_hubs_own_validator(self, sat):
        assert hub_validator.validate_manifest(sat.manifest()) == []

    def test_advertised_urls_are_absolute_and_on_the_public_base(self, sat):
        """The crawler fetches `manifest_url` verbatim. A relative path, or the loopback
        address the process happens to be bound to, is unreachable from where the hub runs."""
        wk = sat.well_known()
        for field in ("manifest_url", "mcp_endpoint"):
            assert wk[field].startswith("https://uni.example.dev/sat/khronos/")

    def test_the_invoke_endpoint_is_the_one_that_gets_the_envelope(self, sat):
        """A peer advertising an mcp_endpoint ending in /ai-market/v2/invoke is sent
        {capability_id, input, product_id, source_hub}; anything else gets the legacy
        /capabilities/{product}/{cap}/invoke path with the bare input."""
        assert sat.well_known()["mcp_endpoint"].endswith("/ai-market/v2/invoke")


class TestTheSignatureTheHubWillCheck:
    def test_our_canonical_is_byte_identical_to_the_hubs(self, sat):
        """The single most fragile line in the whole exercise: the hub hashes `tools` with
        plain `json.dumps` — DEFAULT separators. A compact dump here produces a different
        digest and a signature that fails with 'Invalid manifest signature' and nothing else."""
        manifest = sat.manifest()
        hub = hub_signing.Signer.__new__(hub_signing.Signer)
        assert manifest_canonical(manifest) == hub.manifest_canonical(manifest)

    def test_the_hub_verifies_the_manifest_against_the_pinned_key(self, sat):
        manifest = sat.manifest()
        hub = hub_signing.Signer.__new__(hub_signing.Signer)
        pinned = sat.well_known()["signer_public_key"]
        assert hub.verify_manifest_signature(manifest, pinned) is True

    def test_a_tampered_price_breaks_the_signature(self, sat):
        """What the signature is FOR: a relay must not be able to reprice a peer's catalogue."""
        manifest = sat.manifest()
        manifest["tools"][0]["price_per_call_usd"] = 999.0
        hub = hub_signing.Signer.__new__(hub_signing.Signer)
        assert hub.verify_manifest_signature(
            manifest, sat.well_known()["signer_public_key"]) is False

    def test_a_tampered_by_hub_trust_score_breaks_the_signature(self, sat):
        manifest = sat.manifest()
        manifest["by_hub"]["local"]["trust_score"] = 0.01
        hub = hub_signing.Signer.__new__(hub_signing.Signer)
        assert hub.verify_manifest_signature(
            manifest, sat.well_known()["signer_public_key"]) is False

    def test_the_wrong_key_does_not_verify(self, sat, tmp_path):
        stranger = Signer(tmp_path / "stranger.pem")
        hub = hub_signing.Signer.__new__(hub_signing.Signer)
        assert hub.verify_manifest_signature(
            sat.manifest(), stranger.public_key_b64) is False

    def test_the_key_survives_a_restart(self, tmp_path):
        """The hub pins this key on first contact and refuses the peer forever if it changes.
        A satellite that generates a new key on restart takes itself out of the federation."""
        path = tmp_path / "key.pem"
        first = Signer(path).public_key_b64
        assert Signer(path).public_key_b64 == first


class TestWhatTheCrawlerWillAcceptFromUs:
    def test_every_row_declares_itself_as_the_origin(self, sat):
        """`source_hub` must be "local" or this peer's own host. The crawler skips anything
        else as a re-export — that rule is why 96 duplicate rows once vanished from the live
        catalogue, and a satellite that names someone else indexes as zero."""
        for tool in sat.tools():
            assert tool["source_hub"] == "local"

    def test_no_price_or_latency_would_be_dropped_or_clamped(self, sat):
        for tool in sat.tools():
            assert 0.0 <= tool["price_per_call_usd"] <= 1000.0
            assert 0 <= tool["p50_latency_ms"] <= 300_000

    def test_the_manifest_is_fresh_on_every_read(self, sat):
        """The crawler rejects a manifest whose signed `generated_at` is older than its max
        age, reading it as a replay. So it cannot be built once and cached."""
        stamp = sat.manifest()["generated_at"]
        parsed = time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        assert abs(time.mktime(parsed) - time.mktime(time.gmtime())) < 5

    def test_an_unobserved_capability_says_so_rather_than_claiming_a_score(self, sat):
        for tool in sat.tools():
            assert tool["reputation_basis"] == "unobserved"
            assert tool["observations_30d"] == 0

    def test_a_served_call_turns_the_rate_into_a_measurement(self, sat):
        cap = sat.catalogue.capabilities[0]
        code, _body, _sig = sat.invoke(cap.capability_id, dict(cap.example))
        assert code == 200
        row = next(t for t in sat.tools() if t["capability_id"] == cap.capability_id)
        assert row["reputation_basis"] == "measured"
        assert row["observations_30d"] == 1
        assert row["success_rate_30d"] == 1.0

    def test_the_counts_it_advertises_match_what_it_publishes(self, sat):
        wk, manifest = sat.well_known(), sat.manifest()
        assert wk["capabilities_count"] == len(manifest["tools"])
        assert manifest["capabilities_count"] == len(manifest["tools"])
        assert manifest["local_capabilities"] == len(manifest["tools"])
        # A count that exceeds what `tools` carries makes the hub log an index shortfall and
        # tells a peer we have stock we will not show.
        assert manifest["total_capabilities"] == len(manifest["tools"])


class TestInvoke:
    def test_a_good_call_returns_the_envelope_the_hub_normalises(self, sat):
        code, body, signature = sat.invoke("series.describe@v1", {"series": [1, 2, 3]})
        assert code == 200
        assert body["success"] is True
        assert body["result"]["n"] == 3
        assert signature

    def test_the_response_signature_is_bound_to_the_request(self, sat):
        """Signing the envelope instead of `input` alone produces a valid signature over the
        wrong canonical — which the hub reports as 'invalid provider response signature',
        a message that hides the payload on purpose and hid the cause with it."""
        payload = {"series": [1, 2, 3]}
        _code, body, signature = sat.invoke("series.describe@v1", payload)
        hub = hub_signing.Signer.__new__(hub_signing.Signer)
        canonical = provider_canonical("series.describe@v1", "khronos", payload, body["result"])
        assert hub.verify(sat.signer.public_key_b64, signature, canonical) is True
        wrong = provider_canonical("series.describe@v1", "khronos", {"series": [9]}, body["result"])
        assert hub.verify(sat.signer.public_key_b64, signature, wrong) is False

    def test_an_unknown_capability_is_a_404_not_a_crash(self, sat):
        code, body, _ = sat.invoke("nope@v1", {})
        assert code == 404
        assert body["error"] == "capability_not_found"

    def test_a_bad_input_is_a_400_and_does_not_count_as_a_failure(self, sat):
        code, body, _ = sat.invoke("series.describe@v1", {"series": "not a list"})
        assert code == 400
        assert body["error"] == "invalid_input"
        row = next(t for t in sat.tools() if t["capability_id"] == "series.describe@v1")
        # The attempt is counted; the success rate is not punished for the caller's mistake.
        assert row["observations_30d"] == 1
        assert row["success_rate_30d"] == 0.0

    def test_a_non_object_input_is_refused(self, sat):
        code, body, _ = sat.invoke("series.describe@v1", ["not", "an", "object"])
        assert code == 400
        assert body["error"] == "invalid_input"


class TestTheSealIsNotBrokenByThePeer:
    def test_nothing_the_satellite_serves_names_a_real_chain_or_asset(self, sat):
        """A bubble peer that advertised a mainnet asset would hand an inside agent a payment
        offer valid outside — the exact leak `realm.py` exists to refuse."""
        rendered = json.dumps([sat.well_known(), sat.manifest()])
        for forbidden in (
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # Base USDC
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # Ethereum USDC
            "eip155:8453", "eip155:1", "mainnet.base.org", "infura", "alchemy",
        ):
            assert forbidden not in rendered.lower()

    def test_it_advertises_no_peers_of_its_own(self, sat):
        """The crawler follows `peers` breadth-first. A satellite that listed an outside hub
        would walk the bubble's own crawler out of the bubble."""
        assert sat.well_known()["peers"] == []

    def test_nothing_it_serves_admits_being_a_simulation(self, sat):
        """The invariant, stated by the owner: from the inside the bubble must be
        indistinguishable from the live economy."""
        rendered = json.dumps([sat.well_known(), sat.manifest()]).lower()
        for tell in ("simulation", "simulated", "fake", "bubble", "sandbox", "test-only"):
            assert tell not in rendered, f"the word {tell!r} leaks into a public payload"
