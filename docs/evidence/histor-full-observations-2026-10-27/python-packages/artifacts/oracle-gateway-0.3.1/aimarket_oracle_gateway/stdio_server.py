#!/usr/bin/env python3
"""Stdio MCP server for Glama / Claude Desktop — AIMarket Oracle Gateway.

Exposes the full oracle family as MCP tools — pay-per-call over AIMarket v2:

  Platon (VRF) · Chronos (VDF) · LUMEN (reputation) · Murmuration (consensus) ·
  Landauer (thermodynamics) · Fermat (routing) · Ablation (cascade risk) ·
  Lattice (quasi-random) · Colony (TSP) · Turing (blue-noise) · Percola (resilience)

Every tool returns the same envelope (JSON string):
    {
      "capability_id": "<id>@v1",
      "result":        { …the oracle's verifiable output… },
      "price_usd":     <float, authoritative price charged>,
      "routing_fee_usd": <float, the slice that funds the ecosystem>,
      "source":        "hub" | "oracle-direct",
      "verifiable":    { "signed": <bool>, "has_proof": <bool> }
    }

Configure with environment variables:
    AIMARKET_HUB_URL        AIMarket Hub base URL — recommended (metered + paid; routing fee
                            funds the ecosystem). e.g. https://modelmarket.dev
    AIMARKET_ORACLE_URL     direct oracle-family URL — demo/free path used if no hub is set.
    AIMARKET_PAYMENT_CHANNEL  optional pre-opened payment-channel id (sent as X-Payment-Channel).
    AIMARKET_API_TOKEN      optional bearer token (dev/prod auth).
If neither URL is set, every tool fails closed with a clear message — it never fakes a result.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from aimarket_oracle_gateway.gateway_core import (
    CAPABILITIES,
    CAPABILITY_CATEGORIES,
    OracleGateway,
    list_capabilities_catalog,
)
from aimarket_oracle_gateway.mcp_tool_surface import register_extended_tools

mcp = FastMCP(
    "aimarket-oracle-gateway",
    instructions=(
        "Verifiable oracle services for autonomous agents — pay-per-call over the AIMarket "
        "protocol (no signup by default). Call `list_oracle_capabilities` first.\n\n"
        "Categories:\n"
        "• Randomness (Platon): get_random, get_randomness_beacon, ask_oracle, verify_random\n"
        "• Delay (Chronos): compute_vdf, verify_vdf\n"
        "• Reputation (LUMEN): get_reputation_scores, get_agent_trust, verify_reputation\n"
        "• Consensus (Murmuration): aggregate_values — multi-agent robust aggregation\n"
        "• Thermodynamics (Landauer): audit_compute_cost, verify_compute_cost — ESG / energy floor\n"
        "• Routing (Fermat): compute_least_time_route, verify_least_time_route\n"
        "• Risk (Ablation): analyze_cascade_risk, verify_cascade_risk — SOC cascade tails\n"
        "• Sampling (Lattice/Turing): get_quasirandom_sequence, get_blue_noise\n"
        "• Optimization (Colony): optimize_route — TSP with gap certificate\n"
        "• Resilience (Percola): analyze_network_resilience, verify_network_resilience\n\n"
        "Every paid tool returns {capability_id, result, price_usd, routing_fee_usd, source, "
        "verifiable}. Prefer verifying signatures/proofs/certificates over trusting the service."
    ),
)
_gateway = OracleGateway.from_env()


def _run(tool: str, payload: dict) -> str:
    """Invoke a capability through the gateway and serialize the result envelope."""
    return json.dumps(_gateway.call_tool(tool, payload), separators=(",", ":"))


register_extended_tools(mcp, _run)


# ── Shared parameter annotations (described once with examples, reused by tools) ──────────────
NumBytes = Annotated[
    int,
    Field(
        description=(
            "Number of random bytes to draw, 1..1024. The result's `random_hex` is this many "
            "bytes hex-encoded. Use 32 for a 256-bit seed/word."
        ),
        ge=1,
        le=1024,
        examples=[32, 64],
    ),
]
ClientSeed = Annotated[
    str,
    Field(
        description=(
            "Optional caller-supplied seed (hex) for domain separation — it is bound into the "
            "signed proof so two callers asking at the same tick get distinct, attributable "
            "randomness. Pass '' to omit."
        ),
        examples=["0xdeadbeef", ""],
    ),
]
Question = Annotated[
    str,
    Field(
        description="A question to answer from the oracle's entropy/state. Read-only; no side effects.",
        examples=["Which of these 3 options should I pick at random?"],
    ),
]
RandomHex = Annotated[
    str,
    Field(description="The `random_hex` value returned by get_random / get_randomness_beacon.", examples=["0x9f2c4a…"]),
]
RandProof = Annotated[
    dict[str, Any],
    Field(
        description="The `proof` object from the draw: {scheme, state_hash, client_seed, tick, timestamp, entropy_commitment}.",
        examples=[{"scheme": "platon-chaos-vrf/v1", "state_hash": "…", "client_seed": "", "tick": 42, "timestamp": "2026-06-18T00:00:00Z"}],
    ),
]
RandSignature = Annotated[
    dict[str, Any],
    Field(
        description="The `signature` object from the draw: {algorithm:'ed25519', public_key, value}.",
        examples=[{"algorithm": "ed25519", "public_key": "<b64>", "value": "<b64>"}],
    ),
]
VdfSeed = Annotated[
    str,
    Field(
        description="Seed (hex) the VDF is evaluated over; it binds the generator g, so the output is tied to this input.",
        examples=["0x1234abcd"],
    ),
]
Difficulty = Annotated[
    int,
    Field(
        description=(
            "T — the number of sequential squarings to perform (1..1_000_000). Higher T = more "
            "wall-clock work that cannot be parallelized/GPU-accelerated, i.e. a longer provable "
            "delay. ~1000 is a fast demo; tune T to the delay you need. "
            # Stated here because this schema is what a model reads before choosing a value, and
            # the range it may legally send now depends on payment. The oracle refuses an unpaid
            # call above 100_000 with HTTP 402 and a `free_tier` block naming the ceiling — the
            # VDF sells sequential CPU, so an unpaid caller gets a bounded amount of it. `le`
            # stays at 1_000_000 because that IS the limit once a payment channel is attached;
            # narrowing it would make the paid range unreachable through this tool.
            "NOTE: without a payment channel the provider caps T at 100_000 and answers "
            "402 payment_required above it (the response carries the exact ceiling). 100_000 is "
            "~0.7s of work and demonstrates the primitive fully; the full range needs payment."
        ),
        ge=1,
        le=1_000_000,
        examples=[1000, 100000],
    ),
]
VdfG = Annotated[str, Field(description="Generator g (hex) as returned by `compute_vdf`.", examples=["0x03"])]
VdfY = Annotated[str, Field(description="Claimed VDF output y = g^(2^T) mod N (hex) from `compute_vdf`.", examples=["0x9f2a…"])]
VdfT = Annotated[int, Field(description="Difficulty T (squarings) that produced y; must match the value used in `compute_vdf`.", examples=[1000])]
VdfProof = Annotated[
    dict[str, Any],
    Field(
        description="The Wesolowski proof object from `compute_vdf` — `{pi, l}` (pi = proof element, l = Fiat-Shamir prime).",
        examples=[{"pi": "0x1a2b…", "l": "0x65"}],
    ),
]
GraphNodes = Annotated[
    int,
    Field(
        description="Number of nodes in the directed trust graph, 1..100000. Node indices in `edges` must be in [0, nodes).",
        ge=1,
        le=100000,
        examples=[3, 1000],
    ),
]
GraphEdges = Annotated[
    list[list[float]],
    Field(
        description=(
            "Directed, weighted trust edges as `[from_index, to_index, weight]`. An edge i→j with "
            "weight w means node i confers w trust on node j. Weights need not be normalized."
        ),
        examples=[[[0, 1, 1.0], [1, 2, 0.5], [2, 0, 0.5]]],
    ),
]
Damping = Annotated[
    float,
    Field(
        description="PageRank damping factor in [0,1] (default 0.85). Lower = more weight on the uniform prior, dampening graph manipulation.",
        ge=0.0,
        le=1.0,
        examples=[0.85],
    ),
]
TargetNode = Annotated[
    int,
    Field(description="Index of the node whose trust score/rank/percentile to return (0-based, in [0, nodes)).", ge=0, examples=[1]),
]
ClaimedScores = Annotated[
    list[float],
    Field(description="The `scores` array from a get_reputation_scores result, to be re-derived and confirmed.", examples=[[0.3333, 0.3333, 0.3334]]),
]
GraphCommitment = Annotated[
    str,
    Field(description="Optional `graph_commitment` (0x… SHA-256) from the result, to bind the check to the exact graph. Pass '' to skip.", examples=["0xeb62af…", ""]),
]


@mcp.tool()
def get_random(num_bytes: NumBytes = 32, client_seed: ClientSeed = "") -> str:
    """Draw unbiasable, Ed25519-signed verifiable randomness (Platon).

    Use this when you need randomness an autonomous agent cannot bias or predict and that a third
    party can verify — fair selection, sampling, raffles, commit-reveal, anti-MEV ordering. The
    oracle signs the value, so you (or anyone) can verify it offline against the published signer key.

    Returns:
        The standard envelope (see server instructions). `result` contains:
          - `random_hex`: the random bytes, hex-encoded (`num_bytes` long).
          - `proof`: `{state_hash, tick, timestamp, entropy_commitment}` binding the value to the
            oracle's chaotic state at draw time.
          - `signature`: Ed25519 signature over the value+proof (verify with `verify_random`/the
            signer key in the Hub manifest). `verifiable.signed` will be true.
        Cost ~$0.004 USDC, charged per call.

    Example:
        get_random(num_bytes=32, client_seed="0xdeadbeef")
    """
    return _run("get_random", {"num_bytes": num_bytes, "client_seed": client_seed})


@mcp.tool()
def get_randomness_beacon() -> str:
    """Fetch the round's public randomness beacon (Platon) — one shared value all callers in the
    round observe, useful as a common coin / shared seed.

    Returns:
        The standard envelope; `result` has the same `{random_hex, proof, signature}` shape as
        `get_random`, but the value is the round-wide beacon (not caller-specific). Cost ~$0.004 USDC.

    Example:
        get_randomness_beacon()
    """
    return _run("get_randomness_beacon", {})


@mcp.tool()
def ask_oracle(question: Question) -> str:
    """Ask the Platon oracle for a grounded, entropy-derived read-only answer.

    Use for lightweight oracle-mediated decisions (e.g. an unbiased pick among options). Read-only —
    no side effects, no state change.

    Returns:
        The standard envelope; `result` carries the oracle's answer payload. Cost ~$0.003 USDC.

    Example:
        ask_oracle(question="Pick one at random: red, green, or blue?")
    """
    return _run("ask_oracle", {"question": question})


@mcp.tool()
def verify_random(random_hex: RandomHex, proof: RandProof, signature: RandSignature) -> str:
    """Verify a Platon randomness draw without re-running it (Platon verify).

    Pass `random_hex`, `proof`, and `signature` exactly as returned by `get_random` /
    `get_randomness_beacon`. Confirms the Ed25519 signature over the canonical (random_hex, proof)
    against the signer's published public key — so you trust the math, not the service.

    Returns:
        The standard envelope; `result` is `{valid: <bool>}` (plus `error` if the input was
        malformed). Cost ~$0.001 USDC.

    Example:
        verify_random(random_hex="0x9f2c…", proof={"scheme": "platon-chaos-vrf/v1", …},
                      signature={"algorithm": "ed25519", "public_key": "<b64>", "value": "<b64>"})
    """
    return _run("verify_random", {"random_hex": random_hex, "proof": proof, "signature": signature})


@mcp.tool()
def compute_vdf(seed: VdfSeed, difficulty: Difficulty = 1000) -> str:
    """Evaluate a Verifiable Delay Function (Chronos) — proof that real sequential work elapsed.

    Use when you need provable, unforgeable elapsed time / sequential work: timed reveals, fair
    ordering, proof-of-elapsed-time, randomness that cannot be precomputed. Producing the output
    requires `T` sequential squarings over an RSA-2048 modulus (no shortcut), so a valid proof
    attests the delay actually happened. Verify cheaply with `verify_vdf`.

    Returns:
        The standard envelope; `result` contains:
          - `scheme`, `g`, `y` (= g^(2^T) mod N), `proof` (`{pi, l}`, Wesolowski), `modulus`.
        `verifiable.has_proof` will be true. Cost ~$0.01 USDC.

    Example:
        compute_vdf(seed="0x1234abcd", difficulty=100000)
    """
    return _run("compute_vdf", {"seed": seed, "difficulty": difficulty})


@mcp.tool()
def verify_vdf(g: VdfG, y: VdfY, T: VdfT, proof: VdfProof) -> str:
    """Verify a Chronos VDF proof in a single exponentiation.

    Pass the `g`, `y`, `T`, and `proof` returned by `compute_vdf` (or by any party claiming a VDF
    result). Confirms `y = g^(2^T) mod N` without redoing the T squarings.

    Returns:
        The standard envelope; `result` is `{valid: <bool>}`. Cost ~$0.001 USDC.

    Example:
        verify_vdf(g="0x03", y="0x9f2a…", T=100000, proof={"pi": "0x1a2b…", "l": "0x65"})
    """
    return _run("verify_vdf", {"g": g, "y": y, "difficulty": T, "proof": proof})


@mcp.tool()
def get_reputation_scores(nodes: GraphNodes, edges: GraphEdges, damping: Damping = 0.85) -> str:
    """Compute PageRank/EigenTrust trust scores over a directed trust graph you supply (LUMEN).

    Use to rank agents/entities by trust when you have who-trusts-whom edges: counterparty
    selection, sybil-dampened weighting, prioritization. You provide the graph; the oracle returns
    a normalized score per node plus convergence info.

    Returns:
        The standard envelope; `result` contains:
          - `scores`: array of `nodes` floats that sum to 1 (±1e-6) — node i's trust share.
          - `iterations`, `converged`: power-iteration convergence info.
        Cost ~$0.005 USDC (scales with graph size).

    Example:
        get_reputation_scores(nodes=3, edges=[[0,1,1.0],[1,2,0.5],[2,0,0.5]], damping=0.85)
    """
    return _run("get_reputation_scores", {"nodes": nodes, "edges": edges, "damping": damping})


@mcp.tool()
def get_agent_trust(nodes: GraphNodes, edges: GraphEdges, target_node: TargetNode, damping: Damping = 0.85) -> str:
    """Trust score, rank, and percentile of ONE node in a trust graph you supply (LUMEN).

    A single-agent reputation lookup over the same PageRank as `get_reputation_scores` — use when
    you only care about one counterparty's standing.

    Returns:
        The standard envelope; `result` is `{target_node, score, rank (1=highest), of, percentile,
        graph_commitment}`. Cost ~$0.003 USDC.

    Example:
        get_agent_trust(nodes=3, edges=[[0,1,1.0],[1,2,0.5],[2,0,0.5]], target_node=1)
    """
    return _run("get_agent_trust", {"nodes": nodes, "edges": edges, "target_node": target_node, "damping": damping})


@mcp.tool()
def verify_reputation(nodes: GraphNodes, edges: GraphEdges, scores: ClaimedScores, damping: Damping = 0.85, graph_commitment: GraphCommitment = "") -> str:
    """Verify LUMEN reputation scores by re-deriving PageRank over the supplied graph (LUMEN verify).

    Pass the graph and the `scores` (and optionally the `graph_commitment`) from a
    `get_reputation_scores` result; confirms they are the correct PageRank of exactly that graph.

    Returns:
        The standard envelope; `result` is `{valid: <bool>, max_abs_diff, [commitment_match]}`.
        Cost ~$0.002 USDC.

    Example:
        verify_reputation(nodes=3, edges=[[0,1,1.0],[1,2,0.5],[2,0,0.5]], scores=[0.33,0.33,0.34])
    """
    payload: dict[str, Any] = {"nodes": nodes, "edges": edges, "scores": scores, "damping": damping}
    if graph_commitment:
        payload["graph_commitment"] = graph_commitment
    return _run("verify_reputation", payload)


@mcp.tool()
def list_oracle_capabilities() -> str:
    """List every oracle tool with capabilityId, price, category, and optional subscription tiers.

    Call this first to discover what's available and what each call costs before invoking.

    Returns:
        JSON with `tools` (flat catalog) and `categories` (group labels).

    Example:
        list_oracle_capabilities()
    """
    return json.dumps(
        {
            "tools": list_capabilities_catalog(),
            "categories": CAPABILITY_CATEGORIES,
            "tool_count": len(CAPABILITIES),
        },
        separators=(",", ":"),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
