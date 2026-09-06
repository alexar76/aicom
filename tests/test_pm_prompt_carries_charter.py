"""The operator's charter must reach the model, not a keyword summary of its first lines.

Root cause of "the PM stage ignores operator requirements", and it was not ignoring them.
The charter reached generation ONLY through ``compile_product_brief``, which reduces any
charter to:

* ``domain`` — one word matched against a seven-item keyword list;
* ``audience_hints`` / ``constraints`` — flags from two more short keyword lists;
* ``primary_outcomes`` — **the first six sentences over 20 characters**.

So a 9 000-character engineering charter arrived as a handful of leading sentences and some
flags. An operator appended two sections explicitly marked as requirements; the PM stage
dropped both on five consecutive attempts while the gate's feedback named the exact
identifiers to include. Nothing was disobeying anything — the text was discarded before the
prompt was built.

These tests pin the two properties that fix it: the charter goes in whole, and the sections
the gate will refuse a spec for are restated as mandatory, so the prompt asks for exactly
what the gate checks.
"""

from __future__ import annotations

import agents.pm as pm

CHARTER = """
=== WHAT IT IS ===
A browser safety companion. No LLM at runtime.

=== FREE-TIER BEHAVIOUR IN THE INTERFACE (operator requirement) ===
On 402 payment_required keep the last advisory, labelled with its read time.
Read quota_window and renews from the body.

=== UI / DESIGN BAR ===
Dark, calm palette.

=== WALLET: OPTIONAL, OFF BY DEFAULT (operator requirement) ===
WALLET_ENABLED=0 unless set. When 1, read WALLET_ADDRESS and WALLET_CHAIN.
""".strip()

# Far enough past the first six sentences that the old compiler could not have carried it.
TAIL_MARKER = "WALLET_ADDRESS"


def test_marked_sections_are_extracted_for_the_prompt():
    out = pm._mandated_charter_sections(CHARTER)
    assert "FREE-TIER BEHAVIOUR IN THE INTERFACE" in out
    assert "WALLET: OPTIONAL, OFF BY DEFAULT" in out
    assert TAIL_MARKER in out, "a requirement at the end of the charter must survive"
    # Unmarked guidance is not promoted to a gated requirement.
    assert "Dark, calm palette" not in out


def test_an_unmarked_charter_yields_no_mandatory_block():
    """Most charters mark nothing; they must not all become gated requirements."""
    assert pm._mandated_charter_sections("=== NOTES ===\nJust guidance.") == ""


def test_empty_charter_is_handled():
    assert pm._mandated_charter_sections("") == ""


def test_the_compiler_alone_loses_the_tail():
    """Documents *why* the verbatim block is needed, against the real compiler.

    If this ever stops being true — if the compiler starts carrying whole charters — the
    verbatim block becomes redundant rather than wrong, and this test says so out loud.
    """
    from web.backend.services.spec_compiler import compile_product_brief
    import json

    brief = compile_product_brief("A safety companion.", CHARTER)
    carried = json.dumps(brief, ensure_ascii=False)
    assert TAIL_MARKER not in carried, (
        "the compiler now carries the charter tail; re-check whether the verbatim block in "
        "the PM prompt is still load-bearing"
    )


def test_the_prompt_marks_the_charter_as_outranking_inference():
    """A charter competing with market research must win, and must say so.

    The PM stage escalates delivery profile from market research; without an explicit
    precedence line, an operator instruction and a research inference read as equal weight.
    """
    src = pm.__file__
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "OPERATOR CHARTER (verbatim, authoritative)" in text
    assert "outranks inference" in text
    assert "MANDATORY REQUIREMENTS" in text
    # The prompt must state the same contract the gate enforces, or the gate is just a wall.
    assert "acceptance_criteria" in text
    assert "Do NOT invent prices or quotas" in text
