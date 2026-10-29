"""Bazaar discovery-extension schema quality scoring.

The Oct 2026 catalog crawl measured the gap this scores: 87.8% of Bazaar
listings ship a hollow output — just {"type", "example"} with no typed
schema — and only 0.4% state liveness. RouteVerdict grades the extension
a target publishes in its own 402: is there a discovery extension at all,
does its output schema type real fields, is an example input present, and
does the resource description stay inside the 500-char limit the CDP
facilitator enforces (longer descriptions make CDP reject payments).
"""

from __future__ import annotations


def _schema_types_real_fields(schema: object, depth: int = 0) -> bool:
    """True when a JSON Schema actually pins down fields: typed
    properties, typed items, or an enum — not just {"type": "object"}."""
    if not isinstance(schema, dict) or depth > 6:
        return False
    if schema.get("enum"):
        return True
    props = schema.get("properties")
    if isinstance(props, dict):
        for sub in props.values():
            if isinstance(sub, dict) and ("type" in sub or "enum" in sub or "$ref" in sub):
                return True
            if _schema_types_real_fields(sub, depth + 1):
                return True
    items = schema.get("items")
    if isinstance(items, dict) and ("type" in items or "properties" in items):
        return True
    return False


def _untyped_property_count(schema: object) -> int:
    """Properties declared with no type information at all ({}) — the
    schema looks complete but pins nothing down."""
    if not isinstance(schema, dict):
        return 0
    props = schema.get("properties")
    if not isinstance(props, dict):
        return 0
    count = 0
    for sub in props.values():
        if isinstance(sub, dict) and not any(
            k in sub for k in ("type", "enum", "$ref", "properties", "items")
        ):
            count += 1
    return count


def evaluate_schema_quality(bazaar: dict | None, description: str | None) -> dict:
    """Score the discovery metadata a target publishes.

    Returns {"extension_present", "hollow", "score", "deductions"} where
    score is 0-100 when an extension exists (None when it does not —
    absence is scored by the caller, not hidden inside a zero here) and
    each deduction is {"name", "points", "detail"}.
    """
    if bazaar is None:
        return {"extension_present": False, "hollow": None, "score": None, "deductions": []}

    deductions: list[dict] = []
    score = 100

    def deduct(name: str, points: int, detail: str) -> None:
        nonlocal score
        deductions.append({"name": name, "points": points, "detail": detail})
        score -= points

    info = bazaar.get("info") if isinstance(bazaar.get("info"), dict) else {}
    output = info.get("output") if isinstance(info.get("output"), dict) else None
    input_info = info.get("input") if isinstance(info.get("input"), dict) else None

    hollow = False
    if output is None:
        hollow = True
        deduct("output section missing", 50, "The Bazaar extension has no info.output — buyers learn nothing about the response shape.")
    else:
        out_schema = output.get("schema")
        if out_schema is None:
            hollow = True
            deduct(
                "hollow output (example only, no schema)",
                45,
                "info.output carries only type/example — the hollow shape 87.8% of listings ship. No field is typed, so a buyer cannot validate a response.",
            )
        elif not _schema_types_real_fields(out_schema):
            hollow = True
            deduct(
                "output schema types no real fields",
                30,
                "An output schema exists but declares no typed properties, items, or enum — it pins nothing down.",
            )
        else:
            untyped = _untyped_property_count(out_schema)
            if untyped:
                deduct(
                    "untyped output properties",
                    min(20, 5 * untyped),
                    f"{untyped} output propert{'y has' if untyped == 1 else 'ies have'} no type information.",
                )
        if "example" not in output:
            deduct("no output example", 5, "info.output has no example response for a buyer to sanity-check against the schema.")

    if input_info is None:
        deduct("input section missing", 15, "The Bazaar extension has no info.input — buyers get no example request.")
    elif "body" not in input_info and "queryParams" not in input_info and "pathParams" not in input_info:
        deduct("no example input", 10, "info.input carries no example body/params a buyer can copy.")

    if description is None:
        deduct("no resource description", 10, "The 402 resource object has no description — the text a buying agent reads to decide.")
    elif len(description) > 500:
        deduct(
            "description over 500 characters",
            10,
            f"Description is {len(description)} chars; the CDP facilitator rejects payments for resources described in over 500.",
        )

    return {
        "extension_present": True,
        "hollow": hollow,
        "score": max(0, score),
        "deductions": deductions,
    }
