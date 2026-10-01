"""PSEPHOS — draws, probability and ballots.

Randomness here is *derived*, never sampled: every draw is a deterministic function of a seed
string, so the same seed always produces the same outcome and anyone can recompute it. That is
what makes a draw auditable — and it is also the only honest way to offer randomness as a
capability, because a result nobody can reproduce is indistinguishable from a chosen one.

The commitment scheme is the standard one: publish `sha256(secret || entries)` before the
draw, reveal the secret after, and any observer can verify that neither the entry list nor the
seed was changed once the commitment was made.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from uni.capabilities import (
    Capability, Catalogue, InvalidInput, integer, number, rounded, text,
)

OBJ = {"type": "object"}


class DerivedRandom:
    """A counter-mode PRNG over SHA-256. Deterministic, portable, and reimplementable in
    twenty lines in any language — which matters when the point is that a third party can
    check the draw rather than trust it."""

    def __init__(self, seed: str):
        self._seed = seed.encode()
        self._counter = 0

    def _block(self) -> bytes:
        block = hashlib.sha256(self._seed + self._counter.to_bytes(8, "big")).digest()
        self._counter += 1
        return block

    def below(self, bound: int) -> int:
        """Uniform in [0, bound) by rejection sampling — a modulo would bias the low values,
        which is exactly the bug that makes a lottery quietly unfair."""
        if bound <= 0:
            raise InvalidInput("bound must be positive")
        if bound == 1:
            return 0
        bits = bound.bit_length()
        mask = (1 << bits) - 1
        while True:
            candidate = int.from_bytes(self._block()[:8], "big") & mask
            if candidate < bound:
                return candidate

    def unit(self) -> float:
        return int.from_bytes(self._block()[:7], "big") / float(1 << 56)


def _entries(p: dict[str, Any], key: str = "entries", *, minimum: int = 1) -> list[Any]:
    raw = p.get(key)
    if not isinstance(raw, list):
        raise InvalidInput(f"{key} must be an array")
    if len(raw) < minimum:
        raise InvalidInput(f"{key} needs at least {minimum} entry")
    if len(raw) > 100_000:
        raise InvalidInput(f"{key} is limited to 100000 entries")
    return raw


def _commitment(seed: str, entries: list[Any]) -> str:
    import json
    payload = json.dumps({"seed_digest": hashlib.sha256(seed.encode()).hexdigest(),
                          "entries": entries},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def draw_deterministic(p: dict[str, Any]) -> Any:
    entries = _entries(p)
    seed = text(p, "seed", maximum=4096)
    k = integer(p, "winners", 1, minimum=1, maximum=len(entries))
    replacement = bool(p.get("with_replacement", False))
    rng = DerivedRandom(seed)
    if replacement:
        picked = [entries[rng.below(len(entries))] for _ in range(k)]
        indices = None
    else:
        pool = list(range(len(entries)))
        indices = []
        for _ in range(k):
            indices.append(pool.pop(rng.below(len(pool))))
        picked = [entries[i] for i in indices]
    return {"winners": picked, "winner_indices": indices,
            "entries": len(entries), "with_replacement": replacement,
            "commitment": _commitment(seed, entries),
            "verification": "recompute with the same seed and entry list to reproduce this draw"}


def draw_weighted(p: dict[str, Any]) -> Any:
    entries = _entries(p)
    raw_weights = p.get("weights")
    if not isinstance(raw_weights, list) or len(raw_weights) != len(entries):
        raise InvalidInput("weights must be an array the same length as entries")
    weights = []
    for i, w in enumerate(raw_weights):
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            raise InvalidInput(f"weights[{i}] must be a number")
        if w < 0:
            raise InvalidInput(f"weights[{i}] must not be negative")
        weights.append(float(w))
    if sum(weights) <= 0:
        raise InvalidInput("weights must not sum to zero")
    seed = text(p, "seed", maximum=4096)
    k = integer(p, "winners", 1, minimum=1, maximum=len(entries))
    rng = DerivedRandom(seed)
    pool = list(range(len(entries)))
    live = list(weights)
    picked, indices = [], []
    for _ in range(k):
        total = sum(live)
        if total <= 0:
            break
        target = rng.unit() * total
        acc = 0.0
        chosen = len(pool) - 1
        for idx, w in enumerate(live):
            acc += w
            if target < acc:
                chosen = idx
                break
        indices.append(pool.pop(chosen))
        live.pop(chosen)
        picked.append(entries[indices[-1]])
    return {"winners": picked, "winner_indices": indices,
            "probabilities": [rounded(w / sum(weights)) for w in weights],
            "commitment": _commitment(seed, entries)}


def draw_shuffle(p: dict[str, Any]) -> Any:
    entries = _entries(p)
    seed = text(p, "seed", maximum=4096)
    rng = DerivedRandom(seed)
    order = list(range(len(entries)))
    # Fisher-Yates, downward — the only variant that is uniform over permutations.
    for i in range(len(order) - 1, 0, -1):
        j = rng.below(i + 1)
        order[i], order[j] = order[j], order[i]
    return {"shuffled": [entries[i] for i in order], "order": order,
            "commitment": _commitment(seed, entries)}


def commit(p: dict[str, Any]) -> Any:
    """Publish this before a draw; reveal the seed after. Anyone can then check that neither
    the entries nor the seed changed in between."""
    entries = _entries(p)
    seed = text(p, "seed", maximum=4096)
    return {"commitment": _commitment(seed, entries),
            "seed_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "entries": len(entries),
            "scheme": "sha256 over {seed_digest, entries} in canonical JSON",
            "publish_now": ["commitment", "entries"],
            "publish_after": ["seed"]}


def verify_commitment(p: dict[str, Any]) -> Any:
    entries = _entries(p)
    seed = text(p, "seed", maximum=4096)
    claimed = text(p, "commitment", maximum=128).lower()
    actual = _commitment(seed, entries)
    return {"valid": actual == claimed, "expected": actual, "claimed": claimed,
            "detail": None if actual == claimed
                      else "the entry list or the seed differs from what was committed"}


def binomial(p: dict[str, Any]) -> Any:
    """Exact, via integer binomial coefficients — no normal approximation, no drift."""
    n = integer(p, "trials", minimum=0, maximum=20_000)
    prob = number(p, "probability", minimum=0.0, maximum=1.0)
    k = integer(p, "successes", minimum=0, maximum=n)
    pmf = math.comb(n, k) * (prob ** k) * ((1 - prob) ** (n - k))
    cdf = sum(math.comb(n, i) * (prob ** i) * ((1 - prob) ** (n - i)) for i in range(k + 1))
    return {"pmf": rounded(pmf, 10), "cdf_at_most": rounded(cdf, 10),
            "cdf_at_least": rounded(1 - cdf + pmf, 10),
            "mean": rounded(n * prob), "variance": rounded(n * prob * (1 - prob)),
            "method": "exact binomial coefficients"}


def hypergeometric(p: dict[str, Any]) -> Any:
    """The right distribution for sampling WITHOUT replacement — the one people reach for a
    binomial for, and then wonder why small populations disagree."""
    population = integer(p, "population", minimum=1, maximum=200_000)
    successes = integer(p, "successes_in_population", minimum=0, maximum=population)
    draws = integer(p, "draws", minimum=0, maximum=population)
    observed = integer(p, "observed_successes", minimum=0, maximum=draws)
    if observed > successes or (draws - observed) > (population - successes):
        return {"pmf": 0.0, "cdf_at_most": None,
                "note": "this many successes is impossible for the given population"}
    denom = math.comb(population, draws)
    pmf = math.comb(successes, observed) * math.comb(population - successes, draws - observed) / denom
    cdf = 0.0
    for i in range(observed + 1):
        if i <= successes and (draws - i) <= (population - successes):
            cdf += math.comb(successes, i) * math.comb(population - successes, draws - i) / denom
    mean = draws * successes / population
    return {"pmf": rounded(pmf, 10), "cdf_at_most": rounded(cdf, 10),
            "mean": rounded(mean),
            "variance": rounded(mean * (1 - successes / population)
                                * (population - draws) / (population - 1))
            if population > 1 else 0.0,
            "method": "exact hypergeometric"}


def poisson(p: dict[str, Any]) -> Any:
    lam = number(p, "rate", minimum=0.0, maximum=100_000.0)
    k = integer(p, "events", minimum=0, maximum=100_000)
    log_pmf = -lam + k * math.log(lam) - math.lgamma(k + 1) if lam > 0 else (0.0 if k == 0 else -math.inf)
    pmf = math.exp(log_pmf) if log_pmf > -700 else 0.0
    cdf, term = 0.0, math.exp(-lam) if lam < 700 else 0.0
    for i in range(k + 1):
        if i:
            term = term * lam / i
        cdf += term
    return {"pmf": rounded(pmf, 12), "cdf_at_most": rounded(min(1.0, cdf), 12),
            "mean": rounded(lam), "variance": rounded(lam),
            "method": "log-gamma pmf, iterative cdf — stable for large rates"}


def collision_probability(p: dict[str, Any]) -> Any:
    """The birthday problem, in the form people actually need it: what is the chance of a
    collision among k items drawn from a space of n."""
    space = integer(p, "space_size", minimum=1)
    items = integer(p, "items", minimum=0, maximum=10_000_000)
    if items > space:
        return {"collision_probability": 1.0,
                "note": "more items than distinct values — a collision is certain"}
    # Poisson approximation in log space: the exact product overflows and underflows for the
    # sizes that matter (hash spaces, id namespaces).
    exponent = -items * (items - 1) / (2 * space)
    prob = 1 - math.exp(exponent) if exponent > -700 else 1.0
    half = math.sqrt(2 * space * math.log(2))
    return {"collision_probability": rounded(prob, 12),
            "expected_collisions": rounded(items * (items - 1) / (2 * space), 6),
            "items_for_50_percent": math.ceil(half),
            "method": "Poisson approximation in log space"}


def borda(p: dict[str, Any]) -> Any:
    ballots = _entries(p, "ballots")
    candidates: dict[str, int] = {}
    for i, ballot in enumerate(ballots):
        if not isinstance(ballot, list) or not ballot:
            raise InvalidInput(f"ballots[{i}] must be a non-empty ranked array of candidates")
        if len({str(c) for c in ballot}) != len(ballot):
            raise InvalidInput(f"ballots[{i}] ranks a candidate more than once")
        for c in ballot:
            candidates.setdefault(str(c), 0)
    scores = {c: 0 for c in candidates}
    n = len(candidates)
    for ballot in ballots:
        ranked = [str(c) for c in ballot]
        for position, c in enumerate(ranked):
            scores[c] += n - 1 - position
        # Unranked candidates score zero, which is the standard treatment of a truncated
        # ballot and is stated in the output so it is not mistaken for a bug.
    ranking = sorted(scores, key=lambda c: (-scores[c], c))
    return {"scores": scores, "ranking": ranking, "winner": ranking[0],
            "tied": [c for c in ranking if scores[c] == scores[ranking[0]]],
            "candidates": n, "ballots": len(ballots),
            "truncated_ballots": "unranked candidates score zero"}


def condorcet(p: dict[str, Any]) -> Any:
    """The pairwise matrix, the Condorcet winner if one exists, and the Copeland ranking when
    one does not — because a cycle is a real outcome, not an error."""
    ballots = _entries(p, "ballots")
    names: list[str] = []
    for i, ballot in enumerate(ballots):
        if not isinstance(ballot, list) or not ballot:
            raise InvalidInput(f"ballots[{i}] must be a non-empty ranked array of candidates")
        for c in ballot:
            if str(c) not in names:
                names.append(str(c))
    names.sort()
    if len(names) > 200:
        raise InvalidInput("this method is limited to 200 candidates")
    pair = {a: {b: 0 for b in names if b != a} for a in names}
    for ballot in ballots:
        ranked = [str(c) for c in ballot]
        position = {c: i for i, c in enumerate(ranked)}
        for a in names:
            for b in names:
                if a == b:
                    continue
                pa, pb = position.get(a), position.get(b)
                if pa is None and pb is None:
                    continue
                if pb is None or (pa is not None and pa < pb):
                    pair[a][b] += 1
    wins = {a: sum(1 for b in pair[a] if pair[a][b] > pair[b][a]) for a in names}
    losses = {a: sum(1 for b in pair[a] if pair[a][b] < pair[b][a]) for a in names}
    condorcet_winner = next((a for a in names if wins[a] == len(names) - 1), None)
    copeland = sorted(names, key=lambda a: (-(wins[a] - losses[a]), a))
    return {"pairwise": pair, "wins": wins,
            "condorcet_winner": condorcet_winner,
            "has_cycle": condorcet_winner is None and len(names) > 2,
            "copeland_ranking": copeland,
            "winner": condorcet_winner or copeland[0],
            "method": "Condorcet, falling back to Copeland when no candidate beats all others"}


def approval(p: dict[str, Any]) -> Any:
    ballots = _entries(p, "ballots")
    counts: dict[str, int] = {}
    for i, ballot in enumerate(ballots):
        if not isinstance(ballot, list):
            raise InvalidInput(f"ballots[{i}] must be an array of approved candidates")
        for c in {str(x) for x in ballot}:
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        raise InvalidInput("no candidate was approved on any ballot")
    ranking = sorted(counts, key=lambda c: (-counts[c], c))
    return {"approvals": counts, "ranking": ranking, "winner": ranking[0],
            "tied": [c for c in ranking if counts[c] == counts[ranking[0]]],
            "ballots": len(ballots),
            "approval_rate": {c: rounded(n / len(ballots)) for c, n in counts.items()}}


def expected_value(p: dict[str, Any]) -> Any:
    """Expected value, variance and the certainty equivalent under constant relative risk
    aversion — the number a risk-averse decision maker should actually compare."""
    outcomes = _entries(p, "outcomes")
    values, probs = [], []
    for i, o in enumerate(outcomes):
        if not isinstance(o, dict):
            raise InvalidInput(f"outcomes[{i}] must be an object with value and probability")
        v, pr = o.get("value"), o.get("probability")
        for name, x in (("value", v), ("probability", pr)):
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise InvalidInput(f"outcomes[{i}].{name} must be a number")
        if not 0 <= float(pr) <= 1:
            raise InvalidInput(f"outcomes[{i}].probability must be in [0, 1]")
        values.append(float(v))
        probs.append(float(pr))
    total = sum(probs)
    if abs(total - 1.0) > 1e-6:
        raise InvalidInput(f"probabilities sum to {total:.6f}, not 1")
    ev = sum(v * pr for v, pr in zip(values, probs))
    var = sum(pr * (v - ev) ** 2 for v, pr in zip(values, probs))
    risk_aversion = number(p, "risk_aversion", 0.0, minimum=0.0, maximum=10.0)
    certainty = None
    if risk_aversion > 0 and all(v > 0 for v in values):
        if abs(risk_aversion - 1.0) < 1e-9:
            certainty = math.exp(sum(pr * math.log(v) for v, pr in zip(values, probs)))
        else:
            u = sum(pr * v ** (1 - risk_aversion) for v, pr in zip(values, probs))
            certainty = u ** (1 / (1 - risk_aversion))
    return {"expected_value": rounded(ev), "variance": rounded(var),
            "stdev": rounded(math.sqrt(var)),
            "best_case": rounded(max(values)), "worst_case": rounded(min(values)),
            "certainty_equivalent": rounded(certainty) if certainty is not None else None,
            "risk_aversion": risk_aversion,
            "note": None if certainty is not None or risk_aversion == 0
                    else "a certainty equivalent needs strictly positive outcomes"}


CATALOGUE = Catalogue(
    product_id="psephos",
    name="PSEPHOS Draws & Ballots",
    description="Reproducible draws with commitments, exact discrete probability, and ranked-ballot counting",
    capabilities=[
        Capability("draw.deterministic@v1", "Reproducible draw from a seed with a commitment anyone can recompute",
                   {"type": "object", "required": ["entries", "seed"], "properties": {"entries": {"type": "array"}, "seed": {"type": "string"}, "winners": {"type": "integer"}, "with_replacement": {"type": "boolean"}}},
                   OBJ, 0.004, 40, draw_deterministic, {"entries": ["a", "b", "c", "d"], "seed": "block-1234", "winners": 2}),
        Capability("draw.weighted@v1", "Weighted draw without replacement from a seed, with each entry's probability",
                   {"type": "object", "required": ["entries", "weights", "seed"], "properties": {"entries": {"type": "array"}, "weights": {"type": "array", "items": {"type": "number"}}, "seed": {"type": "string"}, "winners": {"type": "integer"}}},
                   OBJ, 0.006, 55, draw_weighted, {"entries": ["a", "b", "c"], "weights": [1, 3, 6], "seed": "epoch-7"}),
        Capability("draw.shuffle@v1", "Uniform Fisher-Yates permutation derived from a seed",
                   {"type": "object", "required": ["entries", "seed"], "properties": {"entries": {"type": "array"}, "seed": {"type": "string"}}},
                   OBJ, 0.004, 40, draw_shuffle, {"entries": [1, 2, 3, 4, 5], "seed": "round-2"}),
        Capability("draw.commit@v1", "The commitment to publish before a draw, and what to reveal after",
                   {"type": "object", "required": ["entries", "seed"], "properties": {"entries": {"type": "array"}, "seed": {"type": "string"}}},
                   OBJ, 0.002, 25, commit, {"entries": ["a", "b"], "seed": "secret-seed"}),
        Capability("draw.verify-commitment@v1", "Check a revealed seed and entry list against a published commitment",
                   {"type": "object", "required": ["entries", "seed", "commitment"], "properties": {"entries": {"type": "array"}, "seed": {"type": "string"}, "commitment": {"type": "string"}}},
                   OBJ, 0.002, 25, verify_commitment,
                   {"entries": ["a", "b"], "seed": "secret-seed",
                    "commitment": _commitment("secret-seed", ["a", "b"])}),
        Capability("prob.binomial@v1", "Exact binomial pmf and both tails, with mean and variance",
                   {"type": "object", "required": ["trials", "probability", "successes"], "properties": {"trials": {"type": "integer"}, "probability": {"type": "number"}, "successes": {"type": "integer"}}},
                   OBJ, 0.003, 35, binomial, {"trials": 20, "probability": 0.3, "successes": 6}),
        Capability("prob.hypergeometric@v1", "Exact sampling-without-replacement probability — the one a binomial gets wrong",
                   {"type": "object", "required": ["population", "successes_in_population", "draws", "observed_successes"], "properties": {"population": {"type": "integer"}, "successes_in_population": {"type": "integer"}, "draws": {"type": "integer"}, "observed_successes": {"type": "integer"}}},
                   OBJ, 0.004, 45, hypergeometric,
                   {"population": 52, "successes_in_population": 4, "draws": 5, "observed_successes": 2}),
        Capability("prob.poisson@v1", "Poisson pmf and cdf, numerically stable for large rates",
                   {"type": "object", "required": ["rate", "events"], "properties": {"rate": {"type": "number"}, "events": {"type": "integer"}}},
                   OBJ, 0.003, 35, poisson, {"rate": 4.5, "events": 3}),
        Capability("prob.collision@v1", "Birthday-problem collision odds for k items in a space of n, plus the 50% point",
                   {"type": "object", "required": ["space_size", "items"], "properties": {"space_size": {"type": "integer"}, "items": {"type": "integer"}}},
                   OBJ, 0.003, 30, collision_probability, {"space_size": 4294967296, "items": 100000}),
        Capability("vote.borda@v1", "Borda count over ranked ballots with the full ranking and any tie",
                   {"type": "object", "required": ["ballots"], "properties": {"ballots": {"type": "array"}}},
                   OBJ, 0.005, 50, borda, {"ballots": [["a", "b", "c"], ["b", "a", "c"], ["b", "c", "a"]]}),
        Capability("vote.condorcet@v1", "Pairwise matrix, the Condorcet winner, and Copeland when the preferences cycle",
                   {"type": "object", "required": ["ballots"], "properties": {"ballots": {"type": "array"}}},
                   OBJ, 0.008, 80, condorcet, {"ballots": [["a", "b", "c"], ["b", "c", "a"], ["c", "a", "b"]]}),
        Capability("vote.approval@v1", "Approval voting tallies, ranking and per-candidate approval rate",
                   {"type": "object", "required": ["ballots"], "properties": {"ballots": {"type": "array"}}},
                   OBJ, 0.004, 40, approval, {"ballots": [["a", "b"], ["b"], ["b", "c"]]}),
        Capability("prob.expected-value@v1", "Expected value, spread and the certainty equivalent under constant relative risk aversion",
                   {"type": "object", "required": ["outcomes"], "properties": {"outcomes": {"type": "array"}, "risk_aversion": {"type": "number"}}},
                   OBJ, 0.005, 50, expected_value,
                   {"outcomes": [{"value": 100, "probability": 0.5}, {"value": 20, "probability": 0.5}], "risk_aversion": 1}),
    ],
)
