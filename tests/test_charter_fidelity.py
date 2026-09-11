"""A spec has to keep what the operator asked for, and must not invent commercial terms.

Regression cover for one PM run, observed end to end. The operator amended a product's
charter with two sections marked as requirements — how the interface must behave when the
mesh's free allowance is spent, and an optional wallet bound through the environment — and
re-ran the PM stage with both restated in the task's own revision note. The spec that came
back contained neither. It did contain a custom chart builder, draft/published/archived
dashboard lifecycle states, and "Free tier (100 invokes/mo)" — a quota that exists nowhere
in this ecosystem, whose published terms are five calls per caller per hour. Nothing checked
any of it: the architect started, and then the developer.

The gate is deliberately asymmetric, and the tests pin both halves of that asymmetry:

* **Omission blocks**, but only on *total* omission of a marked section. Requiring every
  identifier would fail a spec that legitimately paraphrases, and a gate that cries wolf is a
  gate someone turns off.
* **Invention only reports.** A number the charter omits can still be a fair product call;
  what must not happen is shipping it as though the operator had set it.
"""

from __future__ import annotations

import pytest

from core.charter_fidelity import (
    charter_fidelity_report,
    feedback_for_pm,
    identifiers_in,
    marked_sections,
    unrepresented_requirements,
    untraceable_commercial_terms,
)

CHARTER = """
=== WHAT IT IS ===
A browser safety companion. No LLM at runtime.

=== FREE-TIER BEHAVIOUR IN THE INTERFACE (operator requirement) ===
Send a stable X-AIMarket-Sandbox-Visitor id so the allowance is yours.
When the allowance is spent the mesh answers 402 payment_required. Keep showing the last
advisory with the time it was taken, and read quota_window and renews from the body.
An empty-coverage refusal carries refuse_reason and costs no allowance.

=== WALLET: OPTIONAL, OFF BY DEFAULT (operator requirement) ===
WALLET_ENABLED=0 unless the operator sets it. When 1, read WALLET_ADDRESS and WALLET_CHAIN.
Never a private key. Show the daily spend against SENTINEL_DAILY_INVOKE_BUDGET_USD.

=== UI / DESIGN BAR ===
Dark, calm, high-contrast palette.
"""


def test_only_marked_sections_are_gated():
    """A charter is mostly guidance; promoting all of it would fail every paraphrase."""
    titles = [t for t, _ in marked_sections(CHARTER)]
    assert len(titles) == 2
    assert all("operator requirement" in t.lower() for t in titles)
    assert not any("UI / DESIGN BAR" in t for t in titles)


def test_identifiers_are_exact_strings_not_prose():
    found = identifiers_in(CHARTER)
    for expected in (
        "X-AIMarket-Sandbox-Visitor",
        "WALLET_ENABLED",
        "WALLET_ADDRESS",
        "WALLET_CHAIN",
        "SENTINEL_DAILY_INVOKE_BUDGET_USD",
        "quota_window",
        "refuse_reason",
        "payment_required",
    ):
        assert expected in found, f"{expected} not extracted"
    # Ordinary words must not become requirements, or the gate blocks on wording.
    assert "allowance" not in found
    assert "operator" not in found


def test_the_observed_spec_fails_the_gate():
    """The real shape: eight invented features, zero mention of either requirement."""
    spec = {
        "product_name": "Sentinel",
        "core_features": [
            {"name": "Embeddable Safety Widget", "description": "A JavaScript snippet."},
            {"name": "Custom Analytics (Metrics, Filters, Charts)", "description": "Build charts."},
            {"name": "Dashboard Lifecycle Management", "description": "draft, published, archived."},
            {"name": "Tiered Plans with Metering", "description": "Free tier (100 invokes/mo)."},
        ],
    }
    report = charter_fidelity_report(CHARTER, spec)
    assert report["passed"] is False
    dropped = {g["section"] for g in report["gaps"]}
    assert len(dropped) == 2, dropped
    assert report["invented_terms"], "the fabricated 100 invokes/mo must be reported"


def test_a_spec_that_honours_the_requirements_passes():
    spec = {
        "core_features": [
            {
                "name": "Cached advisory when the free allowance is spent",
                "description": (
                    "On 402 payment_required, keep the last advisory, label it with its read "
                    "time, and read quota_window/renews from the body."
                ),
            },
            {
                "name": "Optional wallet",
                "description": "WALLET_ENABLED=0 by default; WALLET_ADDRESS when enabled.",
            },
        ]
    }
    report = charter_fidelity_report(CHARTER, spec)
    assert report["passed"] is True
    assert report["gaps"] == []


def test_one_identifier_per_section_is_enough():
    """The bar is 'not ignored', not 'quoted verbatim'.

    A spec that says "on 402 keep the last reading" has clearly engaged with the requirement
    even without naming WALLET_ADDRESS or refuse_reason. Blocking that would train people to
    paste identifiers rather than design behaviour.
    """
    spec = {"core_features": ["Handle 402 payment_required by showing the cached advisory",
                              "Respect WALLET_ENABLED"]}
    assert charter_fidelity_report(CHARTER, spec)["passed"] is True


def test_a_prose_only_requirement_cannot_block():
    """Nothing verifiable means nothing to assert — guessing would block on wording."""
    charter = """
=== TONE (operator requirement) ===
Write warmly and never scold the reader.
"""
    assert unrepresented_requirements(charter, {"core_features": ["anything"]}) == []


def test_invented_commercial_terms_are_found_and_traced():
    spec = {"core_features": ["Free tier: 100 invokes/mo", "Pro at $49 per seat"]}
    found = untraceable_commercial_terms(CHARTER, spec)
    claims = " ".join(f["claim"] for f in found)
    assert "100" in claims
    assert "$49" in claims


def test_a_price_the_charter_states_is_not_flagged():
    """Otherwise the gate punishes a spec for obeying the charter."""
    charter = CHARTER + "\nPricing: $49 per seat per month, decided by the operator.\n"
    found = untraceable_commercial_terms(charter, {"core_features": ["Pro at $49 per seat"]})
    assert found == [], found


def test_invention_alone_never_blocks():
    """Reported, not gated — a number the charter omits may still be a fair product call."""
    spec = {
        "core_features": [
            "Handle 402 payment_required with a cached advisory",
            "Respect WALLET_ENABLED",
            "Free tier: 100 invokes/mo",
        ]
    }
    report = charter_fidelity_report(CHARTER, spec)
    assert report["passed"] is True
    assert report["invented_terms"], "still surfaced to the operator"


def test_feedback_names_the_exact_strings_that_were_dropped():
    """A bare 'try again' produced the same omission the first time."""
    report = charter_fidelity_report(CHARTER, {"core_features": ["Widget"]})
    text = feedback_for_pm(report)
    assert "WALLET_ENABLED" in text
    assert "X-AIMarket-Sandbox-Visitor" in text
    assert "acceptance_criteria" in text
    assert "correction, not a rewrite" in text


@pytest.mark.parametrize("spec", [None, {}, "", [], 0])
def test_an_empty_spec_fails_rather_than_crashing(spec):
    """The spec-absent path owns that case, but this must not raise on the way there."""
    report = charter_fidelity_report(CHARTER, spec)
    assert report["passed"] is False


def test_an_empty_charter_gates_nothing():
    """No marked requirements means no opinion — a charterless product is not blocked."""
    report = charter_fidelity_report("", {"core_features": ["whatever"]})
    assert report["passed"] is True
    assert report["invented_terms"] == []
