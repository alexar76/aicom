"""Extended MCP tool surface — registers Phase 1–3 oracle tools on a FastMCP instance."""

from __future__ import annotations

from typing import Annotated, Any, Callable

from pydantic import Field

RunFn = Callable[[str, dict], str]


def register_extended_tools(mcp: Any, run: RunFn) -> None:
    """Register consensus, thermodynamics, routing, risk, sampling, and resilience tools."""

    ValuesList = Annotated[
        list[float],
        Field(
            description="Agent-submitted scalar estimates to aggregate (>=1 value).",
            min_length=1,
            examples=[[1.2, 1.1, 1.15, 99.0, 1.18]],
        ),
    ]
    TrimFraction = Annotated[
        float,
        Field(
            description="Fraction trimmed from each tail for trimmed mean (0..0.499).",
            ge=0.0,
            le=0.499,
            examples=[0.1],
        ),
    ]
    GateOps = Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "Operation DAG for Landauer audit. Each gate: "
                "{id, gate, inputs:[id,...], width?}. Reversible gates erase 0 bits; "
                "boolean gates erase fan_in-1."
            ),
            examples=[[
                {"id": "a", "gate": "input", "width": 1},
                {"id": "b", "gate": "input", "width": 1},
                {"id": "c", "gate": "and", "inputs": ["a", "b"]},
            ]],
        ),
    ]
    RouteEdges = Annotated[
        list[Any],
        Field(
            description=(
                "Directed weighted edges: [u, v, weight] or "
                "{from, to, cost?, latency?, reputation?} for blended refractive index."
            ),
            examples=[[["s", "a", 1], ["a", "t", 1], ["s", "b", 1], ["b", "t", 5]]],
        ),
    ]
    NodeLabel = Annotated[
        str,
        Field(description="Start or goal node label.", examples=["s", "t"]),
    ]
    GraphEdges = Annotated[
        list[list[Any]],
        Field(
            description="Directed graph edges as [u, v] label pairs.",
            examples=[[["A", "B"], ["B", "C"], ["C", "A"]]],
        ),
    ]
    Points2D = Annotated[
        list[list[float]],
        Field(
            description="List of [x, y] coordinates (>=3 points) for TSP optimization.",
            min_length=3,
            examples=[[[0, 0], [1, 0], [0.5, 1]]],
        ),
    ]

    @mcp.tool()
    def aggregate_values(values: ValuesList, trim: TrimFraction = 0.1) -> str:
        """Robust consensus aggregation of multi-agent estimates (Murmuration).

        Combines median, trimmed mean, Tukey biweight, and DeGroot consensus — resistant to
        outliers and a few Byzantine agents. Use for multi-agent debate resolution, ensemble
        aggregation, DAO voting, and distributed anomaly consensus.

        Cost ~$0.002 USDC per call.
        """
        return run("aggregate_values", {"values": values, "trim": trim})

    @mcp.tool()
    def audit_compute_cost(
        ops: GateOps,
        temperature_k: Annotated[float, Field(ge=1.0, le=10_000.0, description="Kelvin (default 300).")] = 300.0,
    ) -> str:
        """Thermodynamic compute-cost audit via Landauer's principle (Landauer).

        Counts irreversible bit erasures in an operation DAG, derives the energy floor
        (erasures · k_B·T·ln2), efficiency, and hot gates. Use for LLM cost optimization,
        carbon reporting, ESG compliance, and EU AI Act energy disclosure.

        Cost ~$0.01 USDC per call.
        """
        return run("audit_compute_cost", {"ops": ops, "temperature_k": temperature_k})

    @mcp.tool()
    def verify_compute_cost(
        ops: GateOps,
        irreversible_bits: Annotated[int | None, Field(description="Claimed erasure count to verify.")] = None,
        energy_floor_j: Annotated[float | None, Field(description="Claimed energy floor (joules) to verify.")] = None,
        temperature_k: float = 300.0,
    ) -> str:
        """Trustless replay of a Landauer thermodynamic audit (Landauer verify).

        Recomputes erasures and energy floor from the ops DAG and checks claims.
        Cost ~$0.001 USDC.
        """
        payload: dict[str, Any] = {"ops": ops, "temperature_k": temperature_k}
        if irreversible_bits is not None:
            payload["irreversible_bits"] = irreversible_bits
        if energy_floor_j is not None:
            payload["energy_floor_j"] = energy_floor_j
        return run("verify_compute_cost", payload)

    @mcp.tool()
    def compute_least_time_route(
        edges: RouteEdges,
        start: NodeLabel,
        goal: NodeLabel,
        blend: Annotated[
            dict[str, float] | None,
            Field(description="Blend coefficients {cost, latency, reputation, latency_scale} for dict edges."),
        ] = None,
    ) -> str:
        """Least-time routing with eikonal potentials + dual certificate (Fermat).

        Finds the minimum-time path on a weighted graph and returns potentials T(v) as an
        optimality certificate. Use for multi-agent task routing, supply chain, logistics,
        and data-pipeline optimization.

        Cost ~$0.01 USDC per call.
        """
        payload: dict[str, Any] = {"edges": edges, "start": start, "goal": goal}
        if blend is not None:
            payload["blend"] = blend
        return run("compute_least_time_route", payload)

    @mcp.tool()
    def verify_least_time_route(
        edges: RouteEdges,
        start: NodeLabel,
        goal: NodeLabel,
        potentials: Annotated[dict[str, float], Field(description="Dual certificate T(v) from compute_least_time_route.")],
        path: Annotated[list[Any] | None, Field(description="Claimed path (node labels).")] = None,
        total: Annotated[float | None, Field(description="Claimed path total time.")] = None,
        blend: dict[str, float] | None = None,
    ) -> str:
        """Trustless certificate check for a Fermat least-time route (Fermat verify).

        Confirms feasibility on every edge and tightness on the path in O(E) time.
        Cost ~$0.001 USDC.
        """
        payload: dict[str, Any] = {
            "edges": edges,
            "start": start,
            "goal": goal,
            "potentials": potentials,
        }
        if path is not None:
            payload["path"] = path
        if total is not None:
            payload["total"] = total
        if blend is not None:
            payload["blend"] = blend
        return run("verify_least_time_route", payload)

    @mcp.tool()
    def analyze_cascade_risk(
        edges: GraphEdges,
        grains: Annotated[int, Field(ge=1, le=100_000, description="Stress grains to drive.")] = 4000,
        nonce: Annotated[str, Field(description="Commit-reveal nonce for drive schedule.")] = "0",
        s_min: Annotated[int, Field(ge=1, description="Power-law fit lower cutoff.")] = 1,
        dissipation: Annotated[int, Field(ge=0, description="Grains leaked per topple.")] = 1,
        nodes: Annotated[list[Any] | None, Field(description="Optional explicit node labels.")] = None,
        capacities: Annotated[dict[str, int] | None, Field(description="Per-node toppling thresholds.")] = None,
        sinks: Annotated[list[Any] | None, Field(description="Sink nodes that dissipate stress.")] = None,
    ) -> str:
        """Systemic cascade-risk analysis via abelian sandpile / SOC (Ablation).

        Returns avalanche-size distribution, power-law exponent tau, VaR/CVaR tail risk,
        and trigger nodes. Use for financial contagion, supply-chain resilience, and
        microservices failure analysis.

        Cost ~$0.01 USDC per call.
        """
        payload: dict[str, Any] = {
            "edges": edges,
            "grains": grains,
            "nonce": nonce,
            "s_min": s_min,
            "dissipation": dissipation,
        }
        if nodes is not None:
            payload["nodes"] = nodes
        if capacities is not None:
            payload["capacities"] = capacities
        if sinks is not None:
            payload["sinks"] = sinks
        return run("analyze_cascade_risk", payload)

    @mcp.tool()
    def verify_cascade_risk(
        edges: GraphEdges,
        claimed_tau: Annotated[float | None, Field(description="Claimed power-law exponent.")] = None,
        claimed_topple_total: Annotated[int | None, Field(description="Claimed topple total.")] = None,
        seed: Annotated[str | None, Field(description="Reveal seed (after nonce commitment).")] = None,
        grains: int = 4000,
        nonce: str = "0",
        s_min: int = 1,
        dissipation: int = 1,
    ) -> str:
        """Trustless replay of an Ablation cascade analysis (Ablation verify).

        Re-runs the sandpile and checks tau / topple_total claims.
        Cost ~$0.001 USDC.
        """
        payload: dict[str, Any] = {
            "edges": edges,
            "grains": grains,
            "nonce": nonce,
            "s_min": s_min,
            "dissipation": dissipation,
        }
        if claimed_tau is not None:
            payload["claimed_tau"] = claimed_tau
        if claimed_topple_total is not None:
            payload["claimed_topple_total"] = claimed_topple_total
        if seed is not None:
            payload["seed"] = seed
        return run("verify_cascade_risk", payload)

    @mcp.tool()
    def get_quasirandom_sequence(
        count: Annotated[int, Field(ge=1, le=4096, description="Number of Halton points.")] = 256,
        dim: Annotated[int, Field(ge=1, le=8, description="Dimension (default 2).")] = 2,
        skip: Annotated[int, Field(ge=0, description="Skip first N sequence indices.")] = 0,
    ) -> str:
        """Halton low-discrepancy quasi-random sequence (Lattice).

        Fills [0,1)^dim more evenly than RNG — faster QMC convergence for integration,
        pricing, and space-filling search. Deterministic from (count, dim, skip).

        Cost ~$0.002 USDC per call.
        """
        return run("get_quasirandom_sequence", {"count": count, "dim": dim, "skip": skip})

    @mcp.tool()
    def optimize_route(
        points: Points2D,
        iterations: Annotated[int, Field(ge=1, le=50_000, description="2-opt improvement budget.")] = 1000,
    ) -> str:
        """Euclidean TSP tour with optimality gap certificate (Colony).

        Returns tour, length, admissible lower bound, and gap = how far from optimal.
        Use for routing, scheduling, and logistics with a quality proof.

        Cost ~$0.005 USDC per call.
        """
        return run("optimize_route", {"points": points, "iterations": iterations})

    @mcp.tool()
    def get_blue_noise(
        count: Annotated[int, Field(ge=1, le=2048, description="Number of points.")] = 256,
        candidates: Annotated[int, Field(ge=1, le=100, description="Best-candidate pool size.")] = 10,
        seed: Annotated[int | None, Field(description="Optional seed for reproducibility.")] = None,
    ) -> str:
        """Blue-noise point set via Mitchell best-candidate (Turing).

        Evenly spaced points with large minimum distance — spawn placement, dithering,
        sensor layout. Omit seed for os.urandom (reported back).

        Cost ~$0.002 USDC per call.
        """
        payload: dict[str, Any] = {"count": count, "candidates": candidates}
        if seed is not None:
            payload["seed"] = seed
        return run("get_blue_noise", payload)

    @mcp.tool()
    def analyze_network_resilience(
        edges: GraphEdges,
        samples: Annotated[int, Field(ge=2, le=500, description="Collapse curve resolution.")] = 50,
        nonce: Annotated[str, Field(description="Commit-reveal nonce for attack order.")] = "0",
        attack: Annotated[
            str,
            Field(description="Attack mode: targeted, random, or both."),
        ] = "both",
        nodes: Annotated[list[Any] | None, Field(description="Optional isolated node labels.")] = None,
    ) -> str:
        """Percolation threshold and network resilience analysis (Percola).

        Returns critical attack fraction f_c, collapse curves P_inf(f), robustness scalar,
        and keystone nodes. Use before joining exposure graphs or multi-hop agent routes.

        Cost ~$0.01 USDC per call.
        """
        payload: dict[str, Any] = {"edges": edges, "samples": samples, "nonce": nonce, "attack": attack}
        if nodes is not None:
            payload["nodes"] = nodes
        return run("analyze_network_resilience", payload)

    @mcp.tool()
    def verify_network_resilience(
        edges: GraphEdges,
        f_c: Annotated[float, Field(description="Claimed critical attack fraction to verify.")],
        attack: Annotated[str, Field(description="Attack mode used in the original analysis.")] = "targeted",
        seed: Annotated[str | None, Field(description="Reveal seed for random attack order.")] = None,
        samples: int = 50,
        nonce: str = "0",
    ) -> str:
        """Trustless replay of a Percola percolation threshold (Percola verify).

        Recomputes the attack sweep and checks the claimed f_c.
        Cost ~$0.001 USDC.
        """
        payload: dict[str, Any] = {
            "edges": edges,
            "f_c": f_c,
            "attack": attack,
            "samples": samples,
            "nonce": nonce,
        }
        if seed is not None:
            payload["seed"] = seed
        return run("verify_network_resilience", payload)
