"""MCP bindings for Sortes, Gauss, Aestus, Betti, Kantor and Fourier.

Parameter names and defaults follow the corresponding oracle capability specs.
Keep annotations evaluated: FastMCP introspects these nested functions later.
"""
from typing import Annotated, Any, Callable, Literal

from pydantic import Field


def register_family_tools(mcp: Any, run: Callable[[str, dict], str]) -> None:
    @mcp.tool()
    def sortes_draw(
        alpha: str,
        num_bytes: Annotated[int, Field(ge=1, le=64)] = 32,
    ) -> str:
        """ECVRF randomness bound to a caller seed (UTF-8 or 'hex:' bytes). ~$0.006 USDC."""
        return run("sortes_draw", {"alpha": alpha, "num_bytes": num_bytes})

    @mcp.tool()
    def sortes_verify(public_key: str, alpha: str, pi: str) -> str:
        """Verify a Sortes VRF draw using the public key and proof (hex). ~$0.001 USDC."""
        return run("sortes_verify", {"public_key": public_key, "alpha": alpha, "pi": pi})

    @mcp.tool()
    def gauss_field(
        X: list[list[float]], y: list[float], query: list[list[float]],
        hyperparams: dict[str, float] | None = None,
    ) -> str:
        """Gaussian-process posterior mean and uncertainty at query points. ~$0.006 USDC."""
        payload = {"X": X, "y": y, "query": query}
        if hyperparams is not None:
            payload["hyperparams"] = hyperparams
        return run("gauss_field", payload)

    @mcp.tool()
    def gauss_suggest(
        X: list[list[float]], y: list[float],
        candidates: list[list[float]] | None = None,
        bounds: list[list[float]] | None = None,
        grid: Annotated[int, Field(ge=2)] = 64,
        xi: Annotated[float, Field(ge=0)] = 0.01,
        goal: Literal["max", "min"] = "max",
        hyperparams: dict[str, float] | None = None,
    ) -> str:
        """Best next experiment by Expected Improvement; provide candidates or bounds. ~$0.006 USDC."""
        payload = {"X": X, "y": y, "grid": grid, "xi": xi, "goal": goal}
        for key, value in (("candidates", candidates), ("bounds", bounds), ("hyperparams", hyperparams)):
            if value is not None:
                payload[key] = value
        return run("gauss_suggest", payload)

    @mcp.tool()
    def gauss_verify(
        X: list[list[float]], y: list[float], query: list[list[float]],
        claimed_mean: list[float] | None = None, claimed_var: list[float] | None = None,
        tol: Annotated[float, Field(ge=0)] = 1e-6,
        hyperparams: dict[str, float] | None = None,
    ) -> str:
        """Replay a Gaussian-process posterior and check claimed mean/variance. ~$0.001 USDC."""
        payload = {"X": X, "y": y, "query": query, "tol": tol}
        for key, value in (("claimed_mean", claimed_mean), ("claimed_var", claimed_var), ("hyperparams", hyperparams)):
            if value is not None:
                payload[key] = value
        return run("gauss_verify", payload)

    @mcp.tool()
    def aestus_seal(
        data: str, encoding: Literal["utf8", "hex"] = "utf8",
        T: Annotated[int, Field(ge=1, le=5_000_000)] = 1_000_000,
        modulus_bits: Annotated[int, Field(ge=256, le=3072)] = 2048,
    ) -> str:
        """Seal data in an RSW time-lock puzzle. Sequential squarings enforce delay. ~$0.006 USDC."""
        return run("aestus_seal", {"data": data, "encoding": encoding, "T": T, "modulus_bits": modulus_bits})

    @mcp.tool()
    def aestus_open(puzzle: dict[str, Any]) -> str:
        """Open an Aestus puzzle by sequential squaring; may take time. ~$0.01 USDC."""
        return run("aestus_open", {"puzzle": puzzle})

    @mcp.tool()
    def aestus_verify(puzzle: dict[str, Any], b: str) -> str:
        """Verify the claimed modular-squaring result of an Aestus puzzle. ~$0.001 USDC."""
        return run("aestus_verify", {"puzzle": puzzle, "b": b})

    @mcp.tool()
    def betti_homology(
        points: list[list[float]],
        max_scale: Annotated[float | None, Field(gt=0)] = None,
        max_dim: Literal[1, 2] = 2,
        num_steps: Annotated[int, Field(ge=2, le=200)] = 40,
    ) -> str:
        """Persistent homology and Betti curves of a point cloud (up to 300 points). ~$0.008 USDC."""
        payload = {"points": points, "max_dim": max_dim, "num_steps": num_steps}
        if max_scale is not None:
            payload["max_scale"] = max_scale
        return run("betti_homology", payload)

    @mcp.tool()
    def betti_distance(
        points_a: list[list[float]], points_b: list[list[float]],
        dim: Literal[0, 1, 2] = 1,
        max_scale: Annotated[float | None, Field(gt=0)] = None,
    ) -> str:
        """Compare topological shape of two point clouds by persistence distance. ~$0.004 USDC."""
        payload = {"points_a": points_a, "points_b": points_b, "dim": dim}
        if max_scale is not None:
            payload["max_scale"] = max_scale
        return run("betti_distance", payload)

    def transport_input(a, b, cost, source_points, sink_points, p, metric):
        payload = {"a": a, "b": b, "p": p, "metric": metric}
        for key, value in (("cost", cost), ("source_points", source_points), ("sink_points", sink_points)):
            if value is not None:
                payload[key] = value
        return payload

    @mcp.tool()
    def kantor_transport(
        a: list[float], b: list[float], cost: list[list[float]] | None = None,
        source_points: list[list[float] | float] | None = None,
        sink_points: list[list[float] | float] | None = None,
        p: Annotated[float, Field(ge=0)] = 2,
        metric: Literal["euclidean", "sqeuclidean"] = "euclidean",
        method: Literal["exact", "sinkhorn"] = "exact",
        eps: Annotated[float, Field(ge=0)] = 0.1,
    ) -> str:
        """Optimal transport/Wasserstein distance; supply cost or source/sink points. ~$0.006 USDC."""
        payload = transport_input(a, b, cost, source_points, sink_points, p, metric)
        payload.update(method=method, eps=eps)
        return run("kantor_transport", payload)

    @mcp.tool()
    def kantor_verify(
        a: list[float], b: list[float], claimed_cost: float,
        plan: list[list[float]], potentials: dict[str, list[float]],
        cost: list[list[float]] | None = None,
        source_points: list[list[float] | float] | None = None,
        sink_points: list[list[float] | float] | None = None,
        p: Annotated[float, Field(ge=0)] = 2,
        metric: Literal["euclidean", "sqeuclidean"] = "euclidean",
        tol: Annotated[float, Field(ge=0)] = 1e-6,
    ) -> str:
        """Certify transport feasibility, primal cost and dual optimality. ~$0.001 USDC."""
        payload = transport_input(a, b, cost, source_points, sink_points, p, metric)
        payload.update(claimed_cost=claimed_cost, plan=plan, potentials=potentials, tol=tol)
        return run("kantor_verify", payload)

    @mcp.tool()
    def fourier_spectrum(
        edges: list[list[Any]], nodes: list[Any] | None = None,
        laplacian: Literal["normalized", "combinatorial"] = "normalized",
        k: Annotated[int, Field(ge=1, le=400)] = 6,
    ) -> str:
        """Graph Laplacian spectrum, connectivity and Fiedler cut. ~$0.005 USDC."""
        payload = {"edges": edges, "laplacian": laplacian, "k": k}
        if nodes is not None:
            payload["nodes"] = nodes
        return run("fourier_spectrum", payload)

    @mcp.tool()
    def fourier_verify(
        edges: list[list[Any]], eigenvalue: float, vector: list[float],
        nodes: list[Any] | None = None,
        laplacian: Literal["normalized", "combinatorial"] = "normalized",
        tol: Annotated[float, Field(ge=0, le=1e-3)] = 1e-6,
    ) -> str:
        """Certify an eigenpair; eigenvalue is sent as the oracle's `lambda` field. ~$0.001 USDC."""
        payload = {"edges": edges, "lambda": eigenvalue, "vector": vector, "laplacian": laplacian, "tol": tol}
        if nodes is not None:
            payload["nodes"] = nodes
        return run("fourier_verify", payload)
