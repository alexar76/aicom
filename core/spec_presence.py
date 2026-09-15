"""One answer to "is there a specification to hold this build to?".

Several gates compare a built product against its specification: spec alignment, the
acceptance-scenario pack, the release critic. Each one needs the same precondition, and
when the precondition is false each one fails in a way that reads as a product defect —
"spec is empty", "0 acceptance scenarios, minimum 2", "the demo invents a brand". None of
those can be fixed by editing code, because the missing thing is upstream.

That is not hypothetical. A product whose PM task was *cancelled* reached the developer
with no ``data/specs/<id>/specification.json`` at all and absorbed roughly seventy
developer/QA rounds against gates that could never pass, spending a model call each round
to rediscover the emptiness.

Hence one predicate, imported by every caller rather than re-implemented next to each
gate: a spec whose substance fields are all empty is *absent*, and absence is a pipeline
input defect, never the product's fault.
"""

from __future__ import annotations

# What a specification is for: material to compare the build against. A dict holding only
# bookkeeping — ids, timestamps, a delivery profile — is present in the file system and
# empty in the sense that matters.
SPEC_SUBSTANCE_FIELDS: tuple[str, ...] = (
    "product_name",
    "description",
    "core_features",
    "functional_requirements",
    "user_stories",
)


def spec_has_substance(inner_spec: object) -> bool:
    """True when at least one substance field carries content.

    Deliberately generous: one non-empty field is enough. A stricter bar belongs to the
    spec *quality* gate, whose job is judging a spec that exists. This predicate answers
    only whether there is anything to judge, and being generous here keeps it from
    rewinding a product that has a thin-but-real spec into another PM round.
    """
    if not isinstance(inner_spec, dict):
        return False
    for field in SPEC_SUBSTANCE_FIELDS:
        value = inner_spec.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, tuple, dict, set)) and len(value) > 0:
            return True
    return False
