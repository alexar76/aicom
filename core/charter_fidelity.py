"""Check that a written specification still contains what the operator asked for.

The pipeline had no such check, and the gap is expensive in both directions.

**Omission.** An operator amended a product's charter with two explicit requirements — how
the interface must behave when the mesh's free allowance runs out, and an optional wallet
bound through the environment — and re-ran the PM stage with both spelled out in the task's
own revision note. The spec that came back mentioned neither. Nothing noticed: the architect
started, then the developer started, and the requirements would have surfaced as missing
features several hundred thousand tokens later, if at all.

**Invention.** The same spec added a custom chart builder, draft/published/archived dashboard
lifecycle states, and "Free tier (100 invokes/mo)" — a quota that exists nowhere in this
ecosystem, whose real terms are five calls per caller per hour. Invented scope is what turns
one product into eighty-five files of repair rounds, and an invented *price* is worse than
inflated scope: it ships a promise the operator never made.

So two deterministic checks, no model call:

* every charter section the operator marked as a requirement must be *represented* in the
  spec, judged by the identifiers it names (env vars, headers, JSON fields, capability ids —
  exact strings, so there is no NLP and no fuzziness);
* numbers the spec presents as prices or quotas must be traceable to the charter.

The first is a blocking gate with a deliberately low bar: it fails only on **total** omission
of a marked section, which is unambiguous and was exactly what happened. Requiring every
identifier would fail specs that legitimately paraphrase, and a gate that cries wolf gets
switched off. The second only reports, because a number the charter does not contain may
still be a reasonable product decision — but the operator should see it before it ships.
"""

from __future__ import annotations

import re

# The operator marks a section by putting this in its header. Explicit rather than inferred:
# a charter is mostly guidance, and promoting all of it to gated requirements would make
# every paraphrase a build failure.
REQUIREMENT_MARKER = "operator requirement"

_SECTION_RE = re.compile(r"^=+\s*(?P<title>.+?)\s*=+\s*$", re.M)

# Exact strings a spec can be expected to carry through verbatim.
_IDENTIFIER_PATTERNS = (
    re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b"),        # SCREAMING_SNAKE env vars
    re.compile(r"\bX-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b"),        # X-Header-Names
    re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\b"),        # snake_case JSON fields
    re.compile(r"\b[a-z][a-z0-9]*\.[a-z0-9_.]+@v\d+\b"),        # capability ids
)

# Words that are snake_case by coincidence rather than by contract. Requiring a spec to
# repeat these says nothing about whether it honoured the requirement.
_IDENTIFIER_STOPWORDS = frozenset(
    {
        "and_or",
        "e_g",
        "i_e",
        "read_them",
        "do_not",
    }
)

_PRICE_OR_QUOTA_PATTERNS = (
    re.compile(r"\$\s?\d+(?:[.,]\d+)?", re.I),
    re.compile(r"\b\d[\d,]*\s*(?:invokes?|calls?|requests?)\s*(?:/|per\s+)\s*(?:mo|month|day|hour|week|min\w*)\b", re.I),
    re.compile(r"\b\d[\d,]*\s*(?:invokes?|calls?|requests?)\s+(?:free|included)\b", re.I),
    re.compile(r"\bfree tier\b[^.\n]{0,60}?\b\d[\d,]*\b", re.I),
)


def sections(charter: str) -> list[tuple[str, str]]:
    """``[(title, body), ...]`` for a charter written with ``=== TITLE ===`` headers."""
    text = charter or ""
    marks = list(_SECTION_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group("title"), text[start:end]))
    return out


def marked_sections(charter: str) -> list[tuple[str, str]]:
    return [
        (title, body)
        for title, body in sections(charter)
        if REQUIREMENT_MARKER in title.lower()
    ]


def identifiers_in(text: str) -> set[str]:
    """Exact strings a spec should carry through: env vars, headers, fields, capability ids."""
    found: set[str] = set()
    for pattern in _IDENTIFIER_PATTERNS:
        for hit in pattern.findall(text or ""):
            token = hit.strip()
            if len(token) < 5 or token.lower() in _IDENTIFIER_STOPWORDS:
                continue
            found.add(token)
    return found


def _spec_text(spec: object) -> str:
    """Everything a spec says, flattened, so identifiers are found wherever they sit."""
    import json

    if isinstance(spec, str):
        return spec
    try:
        return json.dumps(spec, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(spec)


def unrepresented_requirements(charter: str, spec: object) -> list[dict[str, object]]:
    """Marked charter sections the spec does not reference at all.

    A section counts as represented when the spec mentions **any** identifier it names. The
    full missing list travels along so the re-run can be told precisely what to add rather
    than "try again" — a bare retry produced the same omission the first time.
    """
    blob = _spec_text(spec).lower()
    gaps: list[dict[str, object]] = []
    for title, body in marked_sections(charter):
        wanted = identifiers_in(body)
        if not wanted:
            # Nothing verifiable in this section; a prose-only requirement is not something
            # this check can judge, and guessing would block on paraphrase.
            continue
        present = {i for i in wanted if i.lower() in blob}
        if present:
            continue
        gaps.append(
            {
                "section": title,
                "identifiers_expected": sorted(wanted),
                "identifiers_found": [],
            }
        )
    return gaps


def untraceable_commercial_terms(charter: str, spec: object) -> list[dict[str, str]]:
    """Prices and quotas in the spec that the charter does not contain.

    Reported, never blocking. The case that motivated it — "Free tier (100 invokes/mo)" in a
    product whose ecosystem grants five calls an hour — is a fabricated promise; but a number
    the charter omits can also be a fair product call, so this is for the operator to judge.
    """
    charter_text = charter or ""
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for pattern in _PRICE_OR_QUOTA_PATTERNS:
        for hit in pattern.findall(_spec_text(spec)):
            claim = hit.strip()
            if claim in seen:
                continue
            digits = re.findall(r"\d[\d,]*", claim)
            if digits and all(d.replace(",", "") in charter_text.replace(",", "") for d in digits):
                continue
            seen.add(claim)
            findings.append(
                {
                    "claim": claim,
                    "detail": (
                        f"the spec states {claim!r}, which appears nowhere in the charter — "
                        "a price or quota the operator did not set must not ship as though "
                        "they had"
                    ),
                }
            )
    return findings


def charter_fidelity_report(charter: str, spec: object) -> dict[str, object]:
    """``{passed, gaps, invented_terms}``. ``passed`` is false only on total omission."""
    gaps = unrepresented_requirements(charter, spec)
    return {
        "passed": not gaps,
        "gaps": gaps,
        "invented_terms": untraceable_commercial_terms(charter, spec),
    }


def feedback_for_pm(report: dict[str, object]) -> str:
    """What to tell the PM stage, naming the exact strings that were dropped."""
    lines: list[str] = []
    gaps = report.get("gaps") or []
    if gaps:
        lines.append(
            "The specification omits requirements the operator marked as mandatory. Each "
            "section below must appear as core_features with testable acceptance_criteria, "
            "naming the identifiers listed so the build can be verified against them:"
        )
        for gap in gaps:  # type: ignore[union-attr]
            expected = ", ".join(gap.get("identifiers_expected", []))  # type: ignore[union-attr]
            lines.append(f"- {gap.get('section')}: {expected}")  # type: ignore[union-attr]
    invented = report.get("invented_terms") or []
    if invented:
        lines.append(
            "Also remove or correct these commercial claims, which the charter does not "
            "contain — do not invent prices or quotas:"
        )
        for term in invented:  # type: ignore[union-attr]
            lines.append(f"- {term.get('claim')}")  # type: ignore[union-attr]
    lines.append(
        "Keep everything already specified that the charter does support; this is a "
        "correction, not a rewrite."
    )
    return "\n".join(lines)
