"""LUMEN trust oracle client — PageRank/EigenTrust over the supply trust graph.

Every non-healthy return distinguishes TWO failure classes, because the caller must treat
them differently (see ``supply_security.refresh_publisher_trust``):

* ``unavailable=True`` — the oracle could not be consulted or answered nonsense (HTTP
  error, malformed payload, transport failure, non-finite score). Nothing is known about
  the entity, so the caller must NOT overwrite a stored score and must not gate on a
  manufactured one.
* ``unavailable=False`` with a ``no_edges``/``empty_graph`` reason — the oracle was not
  needed: the trust graph simply carries no signal about anyone yet. Deterministic and
  reproducible, which is what lets a brand-new publisher bootstrap.

In both cases ``score`` is ``None``. This client used to answer *every* failure with a
manufactured ``score: 0.5`` — above both the discover (0.25) and invoke (0.35) gates — so
an oracle outage silently granted passing trust to every publisher, including one that had
just been slashed. Inventing a number here is what made that fail-open possible, so the
number is gone.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Reasons that mean "the graph has nothing to say", as opposed to "the oracle is broken".
NO_SIGNAL_REASONS = frozenset({"no_edges", "empty_graph"})


def clamp01(n: float) -> float:
    """Clamp a FINITE number into [0, 1].

    Raises on NaN/inf/non-numeric instead of substituting 0.5: a malformed oracle score
    silently becoming a passing 0.5 is the same fail-open this module exists to prevent.
    Callers classify the failure as ``unavailable`` and fall back on policy, not on a
    number the oracle never produced.
    """
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(float(n)):
        raise ValueError(f"non-finite trust score: {n!r}")
    return max(0.0, min(1.0, float(n)))


def _no_signal(reason: str) -> dict[str, Any]:
    return {"score": None, "degraded": True, "unavailable": False, "reason": reason}


def _unavailable(reason: str) -> dict[str, Any]:
    return {"score": None, "degraded": True, "unavailable": True, "reason": reason}


class LumenTrustClient:
    """Calls ``lumen.reputation@v1`` on the oracle-family Hub endpoint."""

    def __init__(self, oracle_family_url: str, timeout_s: float = 8.0):
        self._base = oracle_family_url.rstrip("/")
        self._timeout = timeout_s

    def score_entity(self, entity_id: str, edges: list[tuple[str, str, float]]) -> dict[str, Any]:
        """Return {score, degraded, unavailable, reason?, rank?, nodes?, edges_count?}.

        ``score`` is a finite [0,1] percentile only when ``degraded`` is False; otherwise it
        is None and the caller applies policy (see the module docstring).
        """
        if not edges:
            return _no_signal("no_edges")

        nodes: list[str] = []
        index: dict[str, int] = {}

        def idx(n: str) -> int:
            if n not in index:
                index[n] = len(nodes)
                nodes.append(n)
            return index[n]

        # LUMEN is PageRank, which only takes non-negative weights, while the hub's graph
        # also records penalties (invoke_failure is -0.25). Sending one raw negative edge got
        # the whole request refused ("trust weight must be non-negative"), which the gate
        # reads as an unavailable oracle — so from the first failed invoke on, every new
        # publisher was scored untrusted, hidden from search and refused at invoke. Net the
        # edges per (source, target) the way PageRank would sum them anyway, and pass only
        # the positive balance: failures that outweigh successes leave that pair with no
        # trust to give. Slashes do not travel through here (`_penalize_trust_locally`).
        net: dict[tuple[str, str], float] = {}
        for src, dst, w in edges:
            w = float(w)
            if math.isfinite(w):
                net[(src, dst)] = net.get((src, dst), 0.0) + w
        lumen_edges: list[list[float | int]] = []
        for (src, dst), w in net.items():
            if w > 0:
                lumen_edges.append([idx(src), idx(dst), w])

        if entity_id not in index:
            idx(entity_id)

        if not lumen_edges:
            return _no_signal("empty_graph")

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base}/ai-market/v2/invoke",
                    json={
                        "capability_id": "lumen.reputation@v1",
                        "input": {"nodes": len(nodes), "edges": lumen_edges, "damping": 0.85},
                    },
                )
                if resp.status_code != 200:
                    logger.warning("LUMEN HTTP %s", resp.status_code)
                    return _unavailable(f"http_{resp.status_code}")
                payload = resp.json()
                output = payload.get("output") or payload.get("result") or payload
                scores = output.get("scores") if isinstance(output, dict) else None
                if not isinstance(scores, list) or not scores:
                    return _unavailable("bad_output")
                target = index[entity_id]
                if target >= len(scores):
                    return _unavailable("index_oob")
                try:
                    numeric = [float(s) for s in scores]
                    # A single NaN silently poisons the percentile: every `s <= raw`
                    # comparison against it is False, so the ranking would come back as a
                    # plausible-looking number derived from nothing. Reject the vector.
                    if not all(math.isfinite(s) for s in numeric):
                        raise ValueError("score vector contains non-finite entries")
                    raw = numeric[target]
                    percentile = clamp01(
                        sum(1 for s in numeric if s <= raw) / len(numeric)
                    )
                except (TypeError, ValueError) as exc:
                    # A non-numeric / NaN entry means the oracle's answer is unusable —
                    # unavailable, not "0.5 and carry on".
                    logger.warning("LUMEN returned unusable scores: %s", exc)
                    return _unavailable("bad_scores")
                rank = 1 + sum(1 for s in numeric if s > raw)
                return {
                    "score": percentile,
                    "degraded": False,
                    "unavailable": False,
                    "rank": rank,
                    "nodes": len(nodes),
                    "edges_count": len(lumen_edges),
                    "converged": output.get("converged"),
                }
        except Exception as exc:
            logger.warning("LUMEN unreachable: %s", exc)
            return _unavailable(str(exc)[:120] or "transport_error")
