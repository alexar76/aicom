"""Pure, testable core for the AIMarket Oracle Gateway MCP server.

Maps agent-legible MCP tool names to live oracle capabilities and invokes them over
AIMarket v2 — through the Hub (metered + routing fee) or directly against the
oracle-family. No MCP runtime is imported here.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any


class GatewayError(RuntimeError):
    """Raised on misconfiguration or an unknown tool (never swallows transport errors)."""


class SpendError(GatewayError):
    """Raised when a call would breach a spending cap, or the hub overcharges."""


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    product_id: str
    price_usd: float
    summary: str
    category: str = "oracle"
    # Optional SaaS packaging hints surfaced in list_oracle_capabilities (pay-per-call still default).
    subscription_tiers: tuple[tuple[str, int, float], ...] = ()


# tool name → capability. Each maps 1:1 to a live, signed, priced oracle capability.
CAPABILITIES: dict[str, CapabilitySpec] = {
    # ── Platon (randomness) ───────────────────────────────────────────────────
    "get_random": CapabilitySpec(
        "platon.random@v1", "prod-platon", 0.004,
        "Unbiasable, Ed25519-signed verifiable randomness with a proof you can verify.",
        "randomness",
        (("Starter", 10_000, 10.0), ("Pro", 100_000, 50.0)),
    ),
    "get_randomness_beacon": CapabilitySpec(
        "platon.beacon@v1", "prod-platon", 0.004,
        "Latest public randomness beacon (shared across callers in a round).",
        "randomness",
    ),
    "ask_oracle": CapabilitySpec(
        "platon.ask@v1", "prod-platon", 0.003,
        "Grounded, entropy-derived read-only answer to a question.",
        "randomness",
    ),
    "verify_random": CapabilitySpec(
        "platon.verify@v1", "prod-platon", 0.001,
        "Verify a Platon randomness draw (random_hex + proof + signature).",
        "randomness",
    ),
    # ── Chronos (VDF / proof-of-elapsed-time) ─────────────────────────────────
    "compute_vdf": CapabilitySpec(
        "chronos.eval@v1", "prod-chronos", 0.01,
        "Verifiable Delay Function: proves T sequential squarings (~elapsed time) over RSA-2048.",
        "delay",
        (("Starter", 10_000, 15.0), ("Pro", 100_000, 75.0)),
    ),
    "verify_vdf": CapabilitySpec(
        "chronos.verify@v1", "prod-chronos", 0.001,
        "Verify a VDF proof in one exponentiation.",
        "delay",
    ),
    # ── LUMEN (reputation / trust) ────────────────────────────────────────────
    "get_reputation_scores": CapabilitySpec(
        "lumen.reputation@v1", "prod-lumen", 0.005,
        "PageRank/EigenTrust trust scores over a directed trust graph you supply.",
        "reputation",
        (("Starter", 5_000, 20.0), ("Pro", 50_000, 100.0)),
    ),
    "get_agent_trust": CapabilitySpec(
        "lumen.score@v1", "prod-lumen", 0.003,
        "Trust score, rank, and percentile of one target node in a trust graph.",
        "reputation",
    ),
    "verify_reputation": CapabilitySpec(
        "lumen.verify@v1", "prod-lumen", 0.002,
        "Re-derive PageRank over a supplied graph and confirm claimed scores.",
        "reputation",
    ),
    # ── Murmuration (consensus aggregation) ───────────────────────────────────
    "aggregate_values": CapabilitySpec(
        "murmuration.aggregate@v1", "prod-murmuration", 0.002,
        "Robust consensus aggregation — median, trimmed mean, biweight, DeGroot convergence.",
        "consensus",
        (("Starter", 10_000, 10.0), ("Pro", 100_000, 50.0)),
    ),
    # ── Landauer (thermodynamic compute-cost audit) ───────────────────────────
    "audit_compute_cost": CapabilitySpec(
        "landauer.audit@v1", "prod-landauer", 0.01,
        "Thermodynamic audit: irreversible bit erasures, energy floor, efficiency, hot gates.",
        "thermodynamics",
        (("Starter", 10_000, 15.0), ("Pro", 100_000, 75.0)),
    ),
    "verify_compute_cost": CapabilitySpec(
        "landauer.verify@v1", "prod-landauer", 0.001,
        "Trustless replay of a Landauer audit — recompute erasures and energy floor.",
        "thermodynamics",
    ),
    # ── Fermat (least-time routing) ───────────────────────────────────────────
    "compute_least_time_route": CapabilitySpec(
        "fermat.route@v1", "prod-fermat", 0.01,
        "Least-time path on a weighted graph with eikonal potentials + dual certificate.",
        "routing",
        (("Starter", 10_000, 25.0), ("Pro", 100_000, 120.0)),
    ),
    "verify_least_time_route": CapabilitySpec(
        "fermat.verify@v1", "prod-fermat", 0.001,
        "Trustless O(E) certificate check for a Fermat least-time route.",
        "routing",
    ),
    # ── Ablation (cascade-risk / SOC) ─────────────────────────────────────────
    "analyze_cascade_risk": CapabilitySpec(
        "ablation.cascade@v1", "prod-ablation", 0.01,
        "SOC cascade-risk: avalanche distribution, power-law tau, VaR/CVaR, trigger nodes.",
        "risk",
        (("Starter", 5_000, 50.0), ("Pro", 50_000, 250.0)),
    ),
    "verify_cascade_risk": CapabilitySpec(
        "ablation.verify@v1", "prod-ablation", 0.001,
        "Trustless replay of an ablation sandpile cascade and tau claim.",
        "risk",
    ),
    # ── Lattice (quasi-random sequences) ──────────────────────────────────────
    "get_quasirandom_sequence": CapabilitySpec(
        "lattice.sequence@v1", "prod-lattice", 0.002,
        "Halton low-discrepancy quasi-random sequence in [0,1)^dim — QMC sampling.",
        "sampling",
    ),
    # ── Colony (TSP optimization + certificate) ─────────────────────────────────
    "optimize_route": CapabilitySpec(
        "colony.optimize@v1", "prod-colony", 0.005,
        "Euclidean TSP tour with admissible lower bound and optimality gap certificate.",
        "optimization",
    ),
    # ── Turing (blue-noise sampling) ────────────────────────────────────────────
    "get_blue_noise": CapabilitySpec(
        "turing.bluenoise@v1", "prod-turing", 0.002,
        "Mitchell best-candidate blue-noise point set — even spacing, no clumping.",
        "sampling",
    ),
    # ── Percola (network resilience / percolation threshold) ──────────────────
    "analyze_network_resilience": CapabilitySpec(
        "percola.threshold@v1", "prod-percola", 0.01,
        "Percolation threshold f_c, collapse curves, robustness scalar, keystone nodes.",
        "resilience",
    ),
    "verify_network_resilience": CapabilitySpec(
        "percola.verify@v1", "prod-percola", 0.001,
        "Trustless replay — recompute percolation sweep and check claimed f_c.",
        "resilience",
    ),
    # ── Sortes (ECVRF ungrindable verifiable randomness) ──────────────────────
    "sortes_draw": CapabilitySpec(
        "sortes.draw@v1", "prod-sortes", 0.006,
        "True ECVRF (RFC 9381) draw — one valid output per (key, input), offline-verifiable from an 80-byte proof.",
        "randomness",
    ),
    "sortes_verify": CapabilitySpec(
        "sortes.verify@v1", "prod-sortes", 0.001,
        "Verify an ECVRF proof offline — confirm the output is the unique valid one for (public key, input).",
        "randomness",
    ),
    # ── Gauss (Gaussian-process regression / active learning) ─────────────────
    "gauss_field": CapabilitySpec(
        "gauss.field@v1", "prod-gauss", 0.006,
        "Gaussian-process regression: calibrated posterior mean with honest uncertainty everywhere.",
        "learning",
    ),
    "gauss_suggest": CapabilitySpec(
        "gauss.suggest@v1", "prod-gauss", 0.006,
        "Single best next point to sample via Expected Improvement — principled Bayesian-optimization exploration.",
        "learning",
    ),
    "gauss_verify": CapabilitySpec(
        "gauss.verify@v1", "prod-gauss", 0.001,
        "Trustless replay of a Gauss GP posterior / suggestion claim.",
        "learning",
    ),
    # ── Aestus (RSW time-lock puzzles) ────────────────────────────────────────
    "aestus_seal": CapabilitySpec(
        "aestus.seal@v1", "prod-aestus", 0.006,
        "RSW time-lock: seal data so nobody can open it before ~T sequential squarings of wall-clock elapse.",
        "time-lock",
    ),
    "aestus_open": CapabilitySpec(
        "aestus.open@v1", "prod-aestus", 0.01,
        "Open an Aestus time-lock by performing the T squarings — no trapdoor holder, anyone can.",
        "time-lock",
    ),
    "aestus_verify": CapabilitySpec(
        "aestus.verify@v1", "prod-aestus", 0.001,
        "Verify an Aestus time-lock seal/opening — confirm the puzzle and recovered plaintext.",
        "time-lock",
    ),
    # ── Betti (persistent homology / shape of data) ───────────────────────────
    "betti_homology": CapabilitySpec(
        "betti.homology@v1", "prod-betti", 0.008,
        "Persistent homology (Vietoris-Rips): Betti numbers b0/b1/b2 (components, loops, voids) across scale.",
        "topology",
    ),
    "betti_distance": CapabilitySpec(
        "betti.distance@v1", "prod-betti", 0.004,
        "Bottleneck-distance drift alarm between two persistence diagrams — topological change detection.",
        "topology",
    ),
    # ── Kantor (exact optimal transport / Wasserstein) ────────────────────────
    "kantor_transport": CapabilitySpec(
        "kantor.transport@v1", "prod-kantor", 0.006,
        "Exact optimal transport (Wasserstein) via min-cost flow — transport plan plus Kantorovich dual potentials.",
        "transport",
    ),
    "kantor_verify": CapabilitySpec(
        "kantor.verify@v1", "prod-kantor", 0.001,
        "Verify a Kantor transport plan in O(m*n) from the dual potentials, without re-solving.",
        "transport",
    ),
    # ── Fourier (graph-spectral analysis) ─────────────────────────────────────
    "fourier_spectrum": CapabilitySpec(
        "fourier.spectrum@v1", "prod-fourier", 0.005,
        "Graph Laplacian spectrum: algebraic connectivity lambda-2, Fiedler vector, spectral cut & conductance.",
        "spectral",
    ),
    "fourier_verify": CapabilitySpec(
        "fourier.verify@v1", "prod-fourier", 0.001,
        "Trustless replay of a Fourier graph-spectral analysis — recompute the Laplacian spectrum and claims.",
        "spectral",
    ),
}

CAPABILITY_CATEGORIES: dict[str, str] = {
    "randomness": "Platon — verifiable randomness & entropy-derived answers",
    "delay": "Chronos — verifiable delay function (proof-of-elapsed-time)",
    "reputation": "LUMEN — PageRank/EigenTrust agent trust scoring",
    "consensus": "Murmuration — Byzantine-resistant multi-agent aggregation",
    "thermodynamics": "Landauer — thermodynamic compute-cost audit (ESG / EU AI Act)",
    "routing": "Fermat — least-time routing with dual optimality certificate",
    "risk": "Ablation — systemic cascade-risk (sandpile / SOC)",
    "sampling": "Lattice & Turing — quasi-random and blue-noise point sets",
    "optimization": "Colony — TSP routing with optimality gap certificate",
    "resilience": "Percola — percolation threshold & network keystone analysis",
    "learning": "Gauss — Gaussian-process regression & active-learning (Expected Improvement)",
    "time-lock": "Aestus — RSW time-lock puzzles (seal the future; anyone opens after ~T)",
    "topology": "Betti — persistent homology (shape of data, drift detection)",
    "transport": "Kantor — exact optimal transport (Wasserstein) with dual certificate",
    "spectral": "Fourier — graph-spectral analysis (Laplacian, Fiedler, spectral cut)",
}


def _unwrap(data: Any) -> Any:
    if isinstance(data, dict):
        for key in ("result", "output"):
            if isinstance(data.get(key), dict):
                return data[key]
        return data
    return {"value": data}


def _verifiable(result: Any) -> dict:
    """Surface verifiability handles an agent can check offline."""
    if not isinstance(result, dict):
        return {"signed": False, "has_proof": False, "certified": False}
    return {
        "signed": bool(result.get("signature")),
        "has_proof": bool(
            result.get("proof") or result.get("pi") or result.get("config_commitment")
        ),
        "certified": bool(
            result.get("valid") is not None
            or result.get("gap") is not None
            or result.get("circuit_commitment")
            or result.get("graph_commitment")
            or result.get("tau") is not None
            or result.get("f_c") is not None
        ),
    }


def list_capabilities_catalog() -> list[dict[str, Any]]:
    """Full storefront catalog for list_oracle_capabilities (grouped by category)."""
    rows: list[dict[str, Any]] = []
    for name, spec in CAPABILITIES.items():
        entry: dict[str, Any] = {
            "tool": name,
            "capability_id": spec.capability_id,
            "product_id": spec.product_id,
            "price_usd": spec.price_usd,
            "category": spec.category,
            "summary": spec.summary,
        }
        if spec.subscription_tiers:
            entry["subscription_tiers"] = [
                {"name": n, "calls_per_month": calls, "price_usd_month": price}
                for n, calls, price in spec.subscription_tiers
            ]
        rows.append(entry)
    return rows


@dataclass
class OracleGateway:
    """Routes MCP tool calls to AIMarket oracle capabilities."""

    hub_url: str = ""
    oracle_url: str = ""
    payment_channel: str = ""
    payment_channel_secret: str = ""
    api_token: str = ""
    source_hub: str = "mcp-oracle-gateway"
    routing_fee_bps: int = 100
    max_per_call_usd: float = 0.10
    max_total_usd: float = 5.0
    price_tolerance: float = 0.10
    spent_usd: float = 0.0
    http: Any = None

    @classmethod
    def from_env(cls) -> "OracleGateway":
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        return cls(
            hub_url=os.getenv("AIMARKET_HUB_URL", "").rstrip("/"),
            oracle_url=os.getenv("AIMARKET_ORACLE_URL", "").rstrip("/"),
            payment_channel=os.getenv("AIMARKET_PAYMENT_CHANNEL", ""),
            payment_channel_secret=os.getenv("AIMARKET_PAYMENT_CHANNEL_SECRET", ""),
            api_token=os.getenv("AIMARKET_API_TOKEN", ""),
            max_per_call_usd=_f("AIMARKET_MAX_PER_CALL_USD", 0.10),
            max_total_usd=_f("AIMARKET_MAX_SPEND_USD", 5.0),
            price_tolerance=_f("AIMARKET_PRICE_TOLERANCE", 0.10),
        )

    def _precheck_budget(self, price_hint: float) -> None:
        if price_hint > self.max_per_call_usd:
            raise SpendError(
                f"per-call price ${price_hint} exceeds cap ${self.max_per_call_usd} "
                f"(raise AIMARKET_MAX_PER_CALL_USD to allow)"
            )
        if self.spent_usd + price_hint > self.max_total_usd:
            raise SpendError(
                f"call would exceed total budget ${self.max_total_usd} (spent ${self.spent_usd:.4f}; "
                f"raise AIMARKET_MAX_SPEND_USD to allow)"
            )

    def _account(self, price_usd: float, price_hint: float) -> None:
        if price_hint > 0 and price_usd > price_hint * (1.0 + self.price_tolerance):
            raise SpendError(
                f"hub overcharged: charged ${price_usd} > advertised ${price_hint} "
                f"+{int(self.price_tolerance * 100)}% tolerance"
            )
        if self.spent_usd + price_usd > self.max_total_usd:
            raise SpendError(
                f"call would exceed total budget ${self.max_total_usd} (actual ${price_usd}; "
                f"spent ${self.spent_usd:.4f})"
            )
        self.spent_usd = round(self.spent_usd + price_usd, 6)

    def _client(self):
        if self.http is None:
            import httpx

            self.http = httpx.Client(timeout=30.0)
        return self.http

    def _post(self, url: str, body: dict, headers: dict) -> dict:
        try:
            resp = self._client().post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            import urllib.parse
            try:
                p = urllib.parse.urlsplit(url)
                host = f"{p.scheme}://{p.hostname or '?'}" if p.scheme else "<endpoint>"
            except Exception:  # noqa: BLE001
                host = "<endpoint>"
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else type(exc).__name__
            raise GatewayError(f"request to {host} failed: {detail}") from None

    def invoke(self, capability_id: str, payload: dict, *, product_id: str = "", price_hint: float = 0.0) -> dict:
        self._precheck_budget(price_hint)
        if self.hub_url:
            body = {
                "product_id": product_id,
                "capability_id": capability_id,
                "source_hub": self.source_hub,
                "input": payload,
            }
            headers: dict[str, str] = {}
            if self.payment_channel:
                headers["X-Payment-Channel"] = self.payment_channel
                if self.payment_channel_secret:
                    headers["X-Payment-Channel-Secret"] = self.payment_channel_secret
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            data = self._post(f"{self.hub_url}/ai-market/v2/invoke", body, headers)
            try:
                price = float(data.get("price_usd", price_hint) or price_hint)
            except (TypeError, ValueError) as exc:
                raise GatewayError("hub returned a price that is not a number") from exc
            # NaN made every cap comparison False and turned spent_usd into NaN for good; a
            # negative price refunded the budget. Either is a hub fault, not a charge.
            if not math.isfinite(price) or price < 0:
                raise GatewayError(f"hub returned an invalid price: {price!r}")
            result = _unwrap(data)
            self._account(price, price_hint)
            return {
                "capability_id": capability_id,
                "result": result,
                "price_usd": price,
                "routing_fee_usd": round(price * self.routing_fee_bps / 10_000, 6),
                "source": "hub",
                "verifiable": _verifiable(result),
            }
        if self.oracle_url:
            data = self._post(
                f"{self.oracle_url}/ai-market/v2/invoke",
                {"capability_id": capability_id, "input": payload},
                {},
            )
            try:
                price = float(data.get("price_usd", price_hint) or price_hint)
            except (TypeError, ValueError) as exc:
                raise GatewayError("hub returned a price that is not a number") from exc
            # NaN made every cap comparison False and turned spent_usd into NaN for good; a
            # negative price refunded the budget. Either is a hub fault, not a charge.
            if not math.isfinite(price) or price < 0:
                raise GatewayError(f"hub returned an invalid price: {price!r}")
            result = _unwrap(data)
            self._account(price, price_hint)
            return {
                "capability_id": capability_id,
                "result": result,
                "price_usd": price,
                "routing_fee_usd": 0.0,
                "source": "oracle-direct",
                "verifiable": _verifiable(result),
            }
        raise GatewayError(
            "No endpoint configured. Set AIMARKET_HUB_URL (paid via the protocol, recommended — "
            "the routing fee funds the ecosystem) or AIMARKET_ORACLE_URL (direct, demo/free)."
        )

    def call_tool(self, tool: str, payload: dict) -> dict:
        spec = CAPABILITIES.get(tool)
        if spec is None:
            raise GatewayError(f"unknown tool {tool!r}; known tools: {sorted(CAPABILITIES)}")
        return self.invoke(spec.capability_id, payload, product_id=spec.product_id, price_hint=spec.price_usd)
