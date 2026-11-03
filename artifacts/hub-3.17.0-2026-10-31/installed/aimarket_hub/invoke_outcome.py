"""Classify an invoke for the live ticker: delivered, missed, or incomplete input.

A peer that answers ``ok: false`` with ``lat/lon required`` did its job, and so did
the hub that routed to it. Recording that as ``success=0`` made ATLAS look like it
was failing, and the storefront percentage (``98.1% успех``) fell on every sandbox
click that sent ``{text: query}`` instead of coordinates. Those rows still belong on
the tape — they are traffic — but they are neither a provider miss nor a refusal by
this hub, and they are counted as neither.

``ok``         — work delivered.
``fail``       — usable input, provider did not deliver (empty coverage, 5xx, timeout).
``incomplete`` — the CALLER did not send what the capability needs. Its own mark on
                 the tape, its own counter in the summary, and outside the success
                 rate entirely: nobody refused anything and nothing was missed.
``refused``    — this hub or the provider declined on policy (quota, plan, blocked
                 consumer), or the provider has no data at the place asked ("no LIVE
                 readings within 2500 km" for a point in mid-ocean). Kept as a separate
                 class because it IS an answer someone gave, unlike ``incomplete``, which
                 is a malformed request.

Only ``ok`` and ``fail`` are scored, so the success rate moves only when our own
infrastructure fails to deliver: a coverage gap is an answer about the world, and a
bad request is the caller's.
"""

from __future__ import annotations

import re
from typing import Any

OUTCOME_OK = "ok"
OUTCOME_FAIL = "fail"
OUTCOME_INCOMPLETE = "incomplete"
OUTCOME_REFUSED = "refused"
OUTCOMES = (OUTCOME_OK, OUTCOME_FAIL, OUTCOME_INCOMPLETE, OUTCOME_REFUSED)
#: Classes that describe traffic rather than performance, so they are not scored.
UNSCORED_OUTCOMES = (OUTCOME_INCOMPLETE, OUTCOME_REFUSED)

# Peers spell "you did not give me X" in their own words, and a fixed list of phrases
# cannot keep up: `atlas.situation.brief@v1` answers "west/south/east/north bbox
# required", which matched NONE of the nine literals this used to carry, so it kept
# scoring as a provider miss. Match the SHAPE of the sentence instead.
_INCOMPLETE_INPUT = re.compile(
    r"\b(?:required|require|provide|missing|must\s+(?:be\s+)?(?:set|supplied|provided)"
    r"|expected|unknown\s+\w+|no\s+valid|invalid\s+(?:input|argument|parameter|coordinates?)"
    r"|malformed|not\s+a\s+valid"
    # GAIA: "gaia.weather.read needs a place: latitude and longitude, or city ...".
    # Named nouns only — "needs a restart" is a provider failure, not a bad request.
    r"|needs?\s+(?:a|an)\s+(?:place|location|city|coordinates?|device(?:_id)?|bbox|value"
    r"|input|parameter|field|query))\b",
    re.IGNORECASE,
)
# A provider with no sensor near the place asked answered truthfully about the world;
# nothing of ours failed to deliver. ATLAS: "no LIVE readings within 2500 km for layers
# ['weather']"; GAIA: "no live weather relay within 75 km of Tokyo; the nearest is ...".
# Scored as a miss, every buyer probing a point in mid-ocean pulled ATLAS's success rate
# down on the modelmarket.dev tape.
# A distance in km and a sensor noun, both required: "no live response within 10 s" is a
# dead upstream (ours), not a coverage gap.
_NO_COVERAGE = re.compile(
    r"\bno\s+live\s+(?:[\w-]+\s+){0,3}?(?:readings?|relays?|stations?|sensors?|pins?)"
    r"\s+within\s+[\d.,]+\s*km\b",
    re.IGNORECASE,
)
# …but "payment required" and "authorization required" are refusals by somebody, not
# a malformed request, and they must not be laundered into the unscored bucket by the
# word they happen to share.
_NOT_INPUT = re.compile(
    r"\b(?:payment|payments|paid|billing|invoice|credit|credits|balance|funds|quota|"
    r"limit|rate.?limit|throttl\w*|auth\w*|api.?key|token|channel|subscription|plan|"
    r"permission|forbidden|denied|blocked|suspended)\b",
    re.IGNORECASE,
)


def _present(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def reads_as_incomplete_input(reason: str) -> bool:
    """Does this refusal sentence describe a malformed request rather than a decision?"""
    text = (reason or "").strip()
    if not text:
        return False
    if _NOT_INPUT.search(text):
        return False
    return bool(_INCOMPLETE_INPUT.search(text))


def reads_as_no_coverage(reason: str) -> bool:
    """Does this refusal say the provider simply has no data near the place asked?"""
    text = (reason or "").strip()
    if not text or _NOT_INPUT.search(text):
        return False
    return bool(_NO_COVERAGE.search(text))


def missing_required_inputs(payload: Any, schema: Any) -> list[list[str]]:
    """The field groups the caller left out, or ``[]`` when the request is complete.

    A list of GROUPS, not of names, because a capability may legitimately have more than
    one way in and JSON Schema says so with ``anyOf``/``oneOf``. ATLAS's watchbox takes a
    stored ``watchbox_id`` plus its ``owner_token``, OR a bare ``west/south/east/north``
    bbox — a flat ``required`` list cannot express that, so the schema carried the rule in
    its prose description and nothing could act on it. Read as alternatives, the answer to
    an empty request is "requires watchbox_id, owner_token or west, south, east, north",
    which is the sentence a caller can actually fix.

    Satisfying ANY alternative means nothing is missing. Top-level ``required`` is checked
    as well, and independently: a field required on every branch is required.

    ``[]`` is also the answer when the schema declares no requirement at all. That is not a
    gap to paper over — a capability that names nothing has given no basis to judge, and
    guessing on its behalf would refuse calls it would have served.
    """
    values = payload if isinstance(payload, dict) else {}
    doc = schema if isinstance(schema, dict) else {}

    def _short(rule: Any) -> list[str]:
        fields = rule.get("required") if isinstance(rule, dict) else None
        fields = fields if isinstance(fields, (list, tuple)) else []
        return [
            name for name in fields
            if isinstance(name, str) and name and not _present(values, name)
        ]

    always = _short(doc)
    if always:
        return [always]

    branches = []
    for key in ("anyOf", "oneOf"):
        rules = doc.get(key)
        if isinstance(rules, (list, tuple)):
            branches.extend(r for r in rules if isinstance(r, dict) and r.get("required"))
    if not branches:
        return []
    shortfalls = [_short(rule) for rule in branches]
    if any(not gap for gap in shortfalls):
        return []                      # one alternative is fully satisfied
    return shortfalls


def classify_invoke_outcome(
    *,
    delivered: bool,
    refuse_reason: str = "",
    input_payload: Any = None,
    input_schema: Any = None,
) -> str:
    """Return ``ok`` / ``fail`` / ``incomplete`` / ``refused`` for one invoke envelope."""
    if delivered:
        return OUTCOME_OK
    if missing_required_inputs(input_payload, input_schema):
        return OUTCOME_INCOMPLETE
    if reads_as_incomplete_input(refuse_reason):
        return OUTCOME_INCOMPLETE
    if reads_as_no_coverage(refuse_reason):
        return OUTCOME_REFUSED
    return OUTCOME_FAIL


def normalize_outcome(outcome: str | None, *, success: bool) -> str:
    value = (outcome or "").strip().lower()
    if value in OUTCOMES:
        return value
    return OUTCOME_OK if success else OUTCOME_FAIL


def scored_success_rate(*, ok: int, fail: int, refused: int = 0, incomplete: int = 0) -> float:
    """Success among scored attempts. Unscored classes never move this number.

    No scored rows but some unscored traffic → 1.0 (nothing was missed).
    No rows at all → 0.0 (same as the previous empty-table default).
    """
    scored = ok + fail
    if scored > 0:
        return ok / scored
    if refused > 0 or incomplete > 0:
        return 1.0
    return 0.0
