"""Search must put the right capability first, not the most-trusted one.

`search_capabilities` matched ANY term and then ordered by `trust_score` alone, so
relevance played no part in the result at all. On the live catalogue that meant the oracle
family (trust 0.265) lost every query to Platon (0.5): "verifiable delay proof" answered
platon.random instead of chronos.eval, "cascade risk in a network" answered platon.beacon
instead of ablation.cascade. The right capability existed, was priced, was executable —
and was unreachable through the only way a buyer looks for it.

The fixture mirrors the real shape of that catalogue, including the trust gap, because the
gap is what made the bug invisible in any test with uniform trust.
"""

from __future__ import annotations

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.semantic_search import rank_capabilities

CATALOGUE = [
    ("chronos.eval@v1", "chronos.eval",
     "Evaluate the VDF: y = g^(2^T) mod N via T sequential squarings. Verifiable delay proof.", 0.265),
    ("chronos.verify@v1", "chronos.verify", "Verify a VDF proof. Cheap, trustless.", 0.265),
    ("ablation.cascade@v1", "ablation.cascade",
     "Analyse a network's systemic cascade risk. Treats the graph as a load-bearing structure.", 0.265),
    ("lumen.score@v1", "lumen.score",
     "Single-agent trust lookup: PageRank score, rank and percentile. Reputation of an agent.", 0.265),
    ("fermat.route@v1", "fermat.route", "Compute the globally least-time composite route.", 0.265),
    ("landauer.audit@v1", "landauer.audit", "Audit a computation's thermodynamic cost.", 0.265),
    # Higher trust, and deliberately worded so a term-count tie is possible.
    ("platon.random@v1", "platon.random", "Signed chaos-VRF randomness with proof.", 0.5),
    ("platon.beacon@v1", "platon.beacon", "Hash-chained randomness beacon round, verifiable.", 0.5),
    ("platon.state@v1", "platon.state", "Snapshot of the 32D universe: telemetry, oscillators, risk.", 0.5),
    ("skopos.security.posture@v1", "Security posture", "Fleet security score, grade, top alerts.", 0.5),
]


@pytest.fixture
def db(tmp_path):
    d = HubDatabase(tmp_path / "search.db")
    for cid, name, desc, trust in CATALOGUE:
        d.upsert_capability(Capability(
            capability_id=cid, product_id="p", name=name, version="v1", description=desc,
            input_schema={}, output_schema={}, price_per_call_usd=0.01,
            source_hub="peer", trust_score=trust, invoke_url="https://p/invoke",
        ))
    return d


@pytest.mark.parametrize(
    "query,expected_first",
    [
        # Each of these answered a higher-trust, less relevant capability before.
        ("verifiable delay proof", "chronos.eval@v1"),
        ("cascade risk in a network", "ablation.cascade@v1"),
        ("reputation of an agent", "lumen.score@v1"),
        ("least-time route", "fermat.route@v1"),
        ("thermodynamic cost of a computation", "landauer.audit@v1"),
        # And the high-trust rows must still win when they are genuinely the best match.
        ("fleet security posture", "skopos.security.posture@v1"),
    ],
)
def test_the_best_match_ranks_first(db, query, expected_first):
    got = [c.capability_id for c in db.search_capabilities(query, limit=5)]
    assert got and got[0] == expected_first, f"{query!r} -> {got}"


def test_trust_only_breaks_ties(db):
    """Two rows matching a query equally well should order by trust — the old behaviour,
    kept, but demoted to what it was always suited for."""
    got = [c.capability_id for c in db.search_capabilities("randomness", limit=5)]
    assert got[:2] == ["platon.random@v1", "platon.beacon@v1"] or got[:2] == [
        "platon.beacon@v1", "platon.random@v1"
    ], got
    # …and both outrank a 0.265 row that does not mention randomness at all.
    assert "platon.state@v1" not in got[:2], got


def test_stopwords_do_not_decide_the_ranking(db):
    """"of", "a", "in" appear in most descriptions; matching them ranked by noise."""
    got = [c.capability_id for c in db.search_capabilities("the cost of a computation", limit=3)]
    assert got[0] == "landauer.audit@v1", got


def test_an_all_stopword_query_still_searches(db):
    """Filtering every term must not silently turn into "return the whole catalogue"."""
    got = db.search_capabilities("what is it for", limit=3)
    assert len(got) <= 3


def test_empty_browse_diversifies_across_hubs(tmp_path):
    """Empty intent must not fill every slot with one high-trust peer."""
    d = HubDatabase(tmp_path / "diverse.db")
    for i in range(8):
        d.upsert_capability(Capability(
            capability_id=f"platon.cap{i}@v1", product_id="platon", name=f"p{i}",
            description="Signed randomness", source_hub="https://oracles.example/platon",
            source_hub_name="Platon", trust_score=0.9, invoke_url="https://p/i",
            price_per_call_usd=0.01,
        ))
    for sku in ("gaia.grid.read@v1", "gaia.quake.read@v1", "gaia.tide.read@v1"):
        d.upsert_capability(Capability(
            capability_id=sku, product_id="gaia", name=sku.split(".")[1],
            description="Live relay reading", source_hub="https://iot.example",
            source_hub_name="GAIA", trust_score=0.3, invoke_url="https://g/i",
            price_per_call_usd=0.001,
        ))
    ranked = d.search_capabilities_ranked("", limit=6)
    hubs = {c.source_hub for c, _ in ranked}
    assert "https://iot.example" in hubs, [c.capability_id for c, _ in ranked]
    assert all(s == 0.0 for _, s in ranked)  # browse, not a relevance claim


def test_live_intent_finds_gaia_relays(tmp_path):
    """'live' must recall SKUs that say relay/attested, not only the word 'live'."""
    d = HubDatabase(tmp_path / "live.db")
    d.upsert_capability(Capability(
        capability_id="platon.random@v1", product_id="p", name="random",
        description="Signed chaos-VRF randomness", source_hub="https://o",
        trust_score=0.5, invoke_url="https://p/i", price_per_call_usd=0.01,
    ))
    d.upsert_capability(Capability(
        capability_id="gaia.grid.read@v1", product_id="gaia", name="grid",
        description="Live UK grid carbon-intensity relay", source_hub="https://iot",
        trust_score=0.3, invoke_url="https://g/i", price_per_call_usd=0.001,
    ))
    got = [c.capability_id for c in d.search_capabilities("live sensors", limit=5)]
    assert "gaia.grid.read@v1" in got, got
    scores = {c.capability_id: s for c, s in d.search_capabilities_ranked("live", limit=5)}
    assert scores["gaia.grid.read@v1"] > 0
    assert scores.get("platon.random@v1", 0) < scores["gaia.grid.read@v1"]


def test_relevance_score_is_not_a_constant(db):
    ranked = db.search_capabilities_ranked("verifiable delay proof", limit=5)
    assert ranked
    scores = [s for _, s in ranked]
    assert scores[0] > scores[-1] or len(set(scores)) > 1 or ranked[0][0].capability_id == "chronos.eval@v1"
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert not all(s == 0.8 for s in scores)


@pytest.fixture
def semantic_catalogue():
    """Small but adversarial slice of the live federated catalogue."""
    rows = [
        ("gaia.weather.read@v1", "Live attested weather: temperature, humidity and wind"),
        ("gaia.fire.read@v1", "Live NASA FIRMS wildfire hotspot"),
        ("gaia.jamming.read@v1", "Live GNSS interference event"),
        ("gaia.ais.read@v1", "Own-edge AIS vessel feeder"),
        ("gaia.ais.public.read@v1", "Live Fintraffic Digitraffic AIS snapshot Finnish waters CC BY 4.0 credit Fintraffic not GFW"),
        ("gaia.cyclone.read@v1", "Live NOAA NHC CPHC active tropical cyclones Atlantic East Pacific hurricane not JTWC"),
        ("gaia.adsb.public.read@v1", "Live ADSB.lol area snapshot ODbL cite ADSB.lol not own-edge not OpenSky"),
        ("atlas.fire.weather@v1", "Wildfire hotspots from NASA FIRMS and/or Copernicus EFFIS in a bbox plus nearest live weather"),
        ("atlas.situation.brief@v1", "Cross-layer situation brief for a bbox: flood, EFFIS, lightning, alerts, events, volcano and other LIVE layers"),
        ("atlas.watchbox.check@v1", "Check a geographic watchbox and layer filter"),
        ("platon.random@v1", "Signed chaos-VRF randomness"),
        ("percola.verify@v1", "Verify a graph percolation removal order"),
        ("chronos.eval@v1", "Verifiable delay proof that sequential time passed"),
        ("aestus.seal@v1", "Seal a time-lock puzzle for later opening"),
    ]
    return [
        Capability(
            capability_id=cid,
            product_id=cid.split(".", 1)[0],
            name=cid.split("@", 1)[0],
            description=description,
            source_hub="https://peer.example",
            trust_score=0.4,
            success_rate_30d=0.98,
            p50_latency_ms=100,
            price_per_call_usd=0.001,
            invoke_url="https://peer.example/invoke",
        )
        for cid, description in rows
    ]


@pytest.mark.parametrize(
    "query,expected_first",
    [
        ("погода сейчас", "gaia.weather.read@v1"),
        ("честная случайность для лотереи", "platon.random@v1"),
        ("protect a ship from navigation spoofing", "gaia.jamming.read@v1"),
        ("защитить судно от навигационных помех", "gaia.jamming.read@v1"),
        ("что предупредит корабль если GPS глушат", "gaia.jamming.read@v1"),
        ("alerta de interferencia GPS para un barco", "gaia.jamming.read@v1"),
        ("preuve de délai vérifiable", "chronos.eval@v1"),
        ("附近森林火灾天气", "atlas.fire.weather@v1"),
        ("EFFIS Copernicus fire weather", "atlas.fire.weather@v1"),
        ("flood river brief", "atlas.situation.brief@v1"),
        ("finnish ais vessels fintraffic", "gaia.ais.public.read@v1"),
        # A US desk types "hurricane", never "cyclone" — the NHC feed has to
        # answer the word people actually use.
        ("hurricane tracking", "gaia.cyclone.read@v1"),
        ("ураган в атлантике", "gaia.cyclone.read@v1"),
        ("monitor wildfire near a facility and alert me", "atlas.watchbox.check@v1"),
    ],
)
def test_multilingual_natural_language_intents_rank_the_right_tool(
    semantic_catalogue, query, expected_first
):
    _intent, matches = rank_capabilities(
        query,
        semantic_catalogue,
        limit=5,
        localized_descriptions={},
    )
    assert matches, query
    assert matches[0].capability.capability_id == expected_first, [
        (m.capability.capability_id, m.score, m.matched_concepts) for m in matches
    ]
    assert matches[0].match_type in {"semantic", "hybrid", "exact"}
    assert matches[0].matched_concepts


def test_exact_id_stays_deterministic_and_typo_gets_a_safe_fallback(semantic_catalogue):
    _intent, exact = rank_capabilities(
        "gaia.weather.read@v1", semantic_catalogue, localized_descriptions={}
    )
    assert exact[0].capability.capability_id == "gaia.weather.read@v1"
    assert exact[0].match_type == "exact"

    _intent, typo = rank_capabilities(
        "wether", semantic_catalogue, localized_descriptions={}
    )
    assert typo[0].capability.capability_id == "gaia.weather.read@v1"
    assert typo[0].match_type in {"fuzzy", "hybrid", "lexical"}


def test_unknown_intent_does_not_fabricate_relevance(semantic_catalogue):
    _intent, matches = rank_capabilities(
        "quantum banana upholstery", semantic_catalogue, localized_descriptions={}
    )
    assert matches == []


@pytest.mark.parametrize(
    "query,expected_first",
    [
        # The public ODbL relay and the own-edge feeder share the aviation concept,
        # so the only thing separating them is the wording of the request. This
        # asserts placement only: an exact-word request legitimately matches
        # lexically, and the shared multilingual test above pins match_type.
        ("public adsb aircraft positions", "gaia.adsb.public.read@v1"),
        ("adsb.lol snapshot", "gaia.adsb.public.read@v1"),
    ],
)
def test_public_relay_outranks_its_own_edge_twin(semantic_catalogue, query, expected_first):
    _intent, matches = rank_capabilities(
        query, semantic_catalogue, limit=5, localized_descriptions={}
    )
    assert matches, query
    assert matches[0].capability.capability_id == expected_first, [
        m.capability.capability_id for m in matches[:3]
    ]


# ── The id word must beat a shared concept (live, 2026-09-25) ─────────────────────────────

_GAIA_SIBLINGS = [
    ("gaia.weather.read@v1", "gaia.weather.read",
     "Current weather (temperature, humidity, pressure, wind) at a place: pass latitude+longitude "
     "or city (e.g. \"Tokyo\"); GAIA reads the nearest live Open-Meteo relay within 75 km, or "
     "refuses. Ed25519-attested.", 0),  # the live row: measured sub-ms, stored as 0
    ("gaia.spacewx.read@v1", "gaia.spacewx.read",
     "Live space-weather relay — NOAA SWPC planetary Kp + OVATION aurora, solar-wind / GOES X-ray "
     "summaries (U.S. PD), and/or NASA DONKI notifications. Default device_id=swpc-01. "
     "Ed25519-attested.", 200),
    ("gaia.water_quality.read@v1", "gaia.water_quality.read",
     "Live USGS monitoring-locations registry joined to latest-continuous (public domain): water "
     "temperature, pH, dissolved oxygen and specific observations. Pass bbox.", 730),
]


def _siblings(weather_p50):
    return [
        Capability(capability_id=cid, product_id="gaia.gateway", name=name, description=desc,
                   price_per_call_usd=0.001, source_hub="https://iot.example", trust_score=0.5,
                   success_rate_30d=0.5, p50_latency_ms=weather_p50 if cid.startswith("gaia.weather") else p50)
        for cid, name, desc, p50 in _GAIA_SIBLINGS
    ]


def test_an_ambiguous_word_is_settled_once_latency_is_measured():
    """"temperature" is literally in water_quality's text too ("water temperature"), so the
    words alone cannot separate them; the crawler's measured-latency fix (p50 1, not 0) does."""
    _, matches = rank_capabilities("temperature Berlin", _siblings(1), limit=3, localized_descriptions={})
    assert matches[0].capability.capability_id == "gaia.weather.read@v1"


@pytest.mark.parametrize("query", ["current weather in Berlin", "weather"])
def test_the_capability_named_for_the_need_ranks_first(query):
    """All three share the weather concept, so they tied at the semantic floor and quality
    alone decided — putting space weather and water quality above weather.read, whose id
    literally says weather. weather.read keeps its live p50 of 0 (scored as "unknown"), so
    this pins the relevance fix on its own, not the latency one."""
    caps = [
        Capability(capability_id=cid, product_id="gaia.gateway", name=name, description=desc,
                   price_per_call_usd=0.001, source_hub="https://iot.example", trust_score=0.5,
                   success_rate_30d=0.5, p50_latency_ms=p50)
        for cid, name, desc, p50 in _GAIA_SIBLINGS
    ]
    _, matches = rank_capabilities(query, caps, limit=3, localized_descriptions={})
    assert matches[0].capability.capability_id == "gaia.weather.read@v1", [
        (m.capability.capability_id, round(m.score, 4)) for m in matches
    ]


def test_a_concept_only_match_gets_no_agreement_bonus():
    caps = [Capability(capability_id="gaia.water_quality.read@v1", product_id="p",
                       name="gaia.water_quality.read", description=_GAIA_SIBLINGS[2][2],
                       price_per_call_usd=0.001, source_hub="s", trust_score=0.5)]
    _, matches = rank_capabilities("current weather in Berlin", caps, limit=3, localized_descriptions={})
    for match in matches:
        assert match.lexical_score == 0.0
        assert match.score <= 0.6865 * 1.0 + 1e-6


# -- A description word must not buy the bonus (review, 2026-09-25) --

#: Real catalogue rows (descriptions verbatim); localized texts come from the packaged
#: cap-descriptions-i18n.json, which is where the RU inflection accident lives.
_DESCRIPTION_WORD_CASES = [
    ('gaia.verify@v1', 'gaia.verify', 'Statistical plausibility verdict over a GAIA reading (bounds, z-score, rate, sibling agreement, attestation) — the same math the /v1/verify escrow endpoint serves.', 0.5, 2, 0.002),
    ('gaia.window@v1', 'gaia.window', "Bundle of N attested readings from one device in a single invoke (micro-billing: clears the hub's 1-cent ledger quantum and the Pay-on-Verified price floor).", 0.5, 152, 0.05),
    ('atlas.watchbox.check@v1', 'atlas.watchbox.check@v1', 'Evaluate an ATLAS watchbox (bbox + layers) against the live fleet snapshot. Returns matches with LIVE/SIM flags and a content receipt. Agent poll SKU. Pass bbox+layers for an ephemeral check, or watchbox_id + owner_token to check a stored subscription.', 0.5, 80, 0.02),
    ('gauss.field@v1', 'gauss.field', 'GP posterior over a query field. Fits the RBF kernel to (X, y) and returns the predictive mean and variance (and std) at every query point — the calibrated uncertainty band that collapses to the noise floor at observations and breathes out to the prior sigma_f^2 far from data.', 0.5, 0, 0.006),
    ('gauss.suggest@v1', 'gauss.suggest', 'Best next experiment by Expected Improvement. Given (X, y) and either an explicit candidate set or bounds+grid, fits the GP and ranks candidates by EI(x) = (mu - f_best - xi)·Phi(z) + std·phi(z). Returns the argmax point, its EI, and the full acquisition vector — a calibrated alternative to hand-tuned UCB / bandit exploration. Supports max or min goals.', 0.5, 0, 0.006),
    ('colony.optimize@v1', 'colony.optimize', "Optimize a tour over >=3 2D points: nearest-neighbour + 2-opt. Returns the tour (a permutation), its length, an admissible lower bound (sum of each node's cheapest incident edge / 2), and gap = (length - lower_bound) / lower_bound. The gap is a certificate of how far from optimal the tour can possibly be.", 0.5, 1, 0.005),
]


@pytest.mark.parametrize("query, expected", [
    ("проверка показаний", "gaia.verify@v1"),
    ("bayesian optimization", "gauss.field@v1"),
])
def test_a_description_word_does_not_outrank_the_right_capability(query, expected):
    """With the bonus on ANY lexical hit, a word in gaia.window's RU text and
    'optimization' in colony.optimize's EN text beat the capabilities that do the job."""
    caps = [Capability(capability_id=cid, product_id="p", name=name, description=desc,
                       price_per_call_usd=price, source_hub="peer", trust_score=trust,
                       p50_latency_ms=p50) for cid, name, desc, trust, p50, price in _DESCRIPTION_WORD_CASES]
    _, matches = rank_capabilities(query, caps, limit=3)
    assert matches[0].capability.capability_id == expected, [m.capability.capability_id for m in matches]
