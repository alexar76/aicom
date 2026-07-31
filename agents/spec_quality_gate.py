"""
Post-PM specification quality gate — structural checks before Architect/Developer.

Validated against delivery_profile from agents.product_profile.
"""
from __future__ import annotations

import re
from typing import Any

from agents.product_profile import DESKTOP_APP, FULL_SOFTWARE, MARKETING_LANDING

# Prefix for every issue string so PM retries / logs show which gate failed.
STRUCTURAL_SPEC_PREFIX = "[structural_spec] "

# Minimum lengths for acceptance text (PM prompts should reference the same numbers)
USER_STORY_ACCEPTANCE_MIN_CHARS = 15
FUNCTIONAL_REQUIREMENT_ACCEPTANCE_MIN_CHARS = 20


def _sg(msg: str) -> str:
    return f"{STRUCTURAL_SPEC_PREFIX}{msg}"


def _str_len(s: Any, minimum: int = 1) -> bool:
    return isinstance(s, str) and len(s.strip()) >= minimum


def validate_specification(spec: dict[str, Any], delivery_profile: str) -> tuple[bool, list[str]]:
    """
    Return (ok, issues). issues are human-readable fix hints for PM retry prompt.
    """
    issues: list[str] = []
    if not isinstance(spec, dict):
        return False, [_sg("Specification must be a JSON object")]

    profile = delivery_profile if delivery_profile in (MARKETING_LANDING, FULL_SOFTWARE, DESKTOP_APP) else MARKETING_LANDING

    if not _str_len(spec.get("product_name"), 2):
        issues.append(_sg("product_name: required, min 2 chars"))
    else:
        pn = str(spec.get("product_name") or "")
        # Hash-like token spam (collision suffix echoed by the model, etc.)
        if len(re.findall(r"\b[0-9A-Fa-f]{4}\b", pn)) >= 3:
            issues.append(
                _sg(
                    "product_name: remove repeated hash-like fragments — use one clean human-readable title (brand + product)"
                )
            )
    if not _str_len(spec.get("description"), 40):
        issues.append(_sg("description: required, min 40 chars — include deliverable type and audience"))

    feats = spec.get("core_features") or []
    if not isinstance(feats, list) or len(feats) < 3:
        issues.append(_sg("core_features: need at least 3 items with name, description, priority"))

    stories = spec.get("user_stories") or []
    if not isinstance(stories, list) or len(stories) < 2:
        issues.append(_sg("user_stories: need at least 2 items, each with story and acceptance_criteria"))

    for j, us in enumerate(stories[:20]):
        if not isinstance(us, dict):
            issues.append(_sg(f"user_stories[{j}]: must be object with story + acceptance_criteria"))
            continue
        if not _str_len(us.get("story"), 10):
            issues.append(_sg(f"user_stories[{j}].story: too short or missing"))
        if not _str_len(us.get("acceptance_criteria"), USER_STORY_ACCEPTANCE_MIN_CHARS):
            issues.append(
                _sg(
                    f"user_stories[{j}].acceptance_criteria: must be testable "
                    f"(min {USER_STORY_ACCEPTANCE_MIN_CHARS} chars)"
                )
            )

    if profile in (FULL_SOFTWARE, DESKTOP_APP):
        fr = spec.get("functional_requirements") or []
        if not isinstance(fr, list) or len(fr) < 3:
            issues.append(
                _sg(
                    "functional_requirements: need ≥3 objects with id, title, description, acceptance_criteria "
                    "(testable outcomes)"
                )
            )
        else:
            for j, r in enumerate(fr[:30]):
                if not isinstance(r, dict):
                    issues.append(_sg(f"functional_requirements[{j}]: must be object"))
                    continue
                if not _str_len(r.get("id"), 1):
                    issues.append(_sg(f"functional_requirements[{j}].id: required (e.g. FR-01)"))
                if not _str_len(r.get("title"), 3):
                    issues.append(_sg(f"functional_requirements[{j}].title: required"))
                if not _str_len(r.get("acceptance_criteria"), FUNCTIONAL_REQUIREMENT_ACCEPTANCE_MIN_CHARS):
                    issues.append(
                        _sg(
                            f"functional_requirements[{j}].acceptance_criteria: must be detailed / testable "
                            f"(min {FUNCTIONAL_REQUIREMENT_ACCEPTANCE_MIN_CHARS} chars)"
                        )
                    )

        personas = spec.get("personas") or []
        if not isinstance(personas, list) or len(personas) < 1:
            issues.append(
                _sg("personas: need ≥1 {name, context, jobs_to_be_done: [strings]} aligned to audience research")
            )
        else:
            for j, p in enumerate(personas[:10]):
                if not isinstance(p, dict):
                    issues.append(_sg(f"personas[{j}]: must be object"))
                    continue
                if not _str_len(p.get("name"), 1):
                    issues.append(_sg(f"personas[{j}].name: required"))
                jtbd = p.get("jobs_to_be_done") or []
                if not isinstance(jtbd, list) or len(jtbd) < 1:
                    issues.append(_sg(f"personas[{j}].jobs_to_be_done: need at least one job string"))

        nfr = spec.get("non_functional_requirements") or []
        if not isinstance(nfr, list) or len(nfr) < 2:
            issues.append(
                _sg(
                    "non_functional_requirements: need ≥2 {category, requirement, measurable_criteria} "
                    "(e.g. performance, security, availability)"
                )
            )
        else:
            for j, n in enumerate(nfr[:15]):
                if not isinstance(n, dict):
                    issues.append(_sg(f"non_functional_requirements[{j}]: must be object"))
                    continue
                if not _str_len(n.get("requirement"), 10):
                    issues.append(_sg(f"non_functional_requirements[{j}].requirement: required"))
                if not _str_len(n.get("measurable_criteria"), 8):
                    issues.append(_sg(f"non_functional_requirements[{j}].measurable_criteria: how we verify"))

    if profile == DESKTOP_APP:
        blob = f"{spec.get('description') or ''} {spec.get('product_name') or ''}".lower()
        if not any(x in blob for x in ("desktop", "tauri", "electron", "flutter", "native", "offline", "local")):
            issues.append(
                _sg(
                    "desktop_app: description should state desktop runtime (Tauri/Electron/Flutter) "
                    "and local/offline behavior"
                )
            )

    spec.setdefault("delivery_profile", profile)
    return len(issues) == 0, issues
