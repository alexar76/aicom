"""
Build domain acceptance packs from PM specification criteria.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _normalize_spec(spec_payload: dict[str, Any]) -> dict[str, Any]:
    inner = spec_payload.get("specification") if isinstance(spec_payload, dict) and "specification" in spec_payload else spec_payload
    return inner if isinstance(inner, dict) else {}


def build_domain_acceptance_pack(
    spec_payload: dict[str, Any], code_dir: "Path | None" = None
) -> dict[str, Any]:
    """Transform acceptance criteria into a runnable scenario checklist.

    Scenarios come from the specification AND, when ``code_dir`` is given, from the product's own
    ``docs/acceptance-scenarios.md``. The second source is what makes the gate satisfiable: the
    journey types are derived from the spec, a repair round cannot edit the spec, and the gate was
    therefore asking for something no round could deliver. Its message said "Only 18 acceptance
    scenarios detected; minimum required is 3" — a number that already passed — while the real
    reason was a missing journey type, which is exactly the kind of finding this pipeline has
    learned costs rounds without moving anything.
    """
    spec = _normalize_spec(spec_payload)
    scenarios: list[dict[str, Any]] = []

    def _steps_from_text(text: str) -> list[str]:
        parts = [p.strip() for p in re.split(r"[.;]\s+|\n+", text) if p.strip()]
        return parts[:6] if parts else [text.strip()]

    def _journey_type(text: str, title: str) -> str:
        blob = f"{title} {text}".lower()
        if any(k in blob for k in ("register", "sign up", "onboard", "create account", "login", "log in")):
            return "onboarding"
        if any(k in blob for k in ("export", "checkout", "purchase", "submit", "save", "generate", "analyze", "upload")):
            return "core_action"
        if any(k in blob for k in ("error", "invalid", "forbidden", "missing", "denied", "edge case", "empty")):
            return "edge_case"
        if any(k in blob for k in ("retry", "recover", "restore", "fallback", "reconnect", "resume", "reset password")):
            return "recovery"
        return "general"

    for idx, us in enumerate(spec.get("user_stories") or []):
        if not isinstance(us, dict):
            continue
        story = str(us.get("story") or "").strip()
        ac = str(us.get("acceptance_criteria") or "").strip()
        if not ac:
            continue
        scenarios.append(
            {
                "id": f"US-{idx + 1:02d}",
                "source": "user_story",
                "title": story or f"User story {idx + 1}",
                "acceptance_criteria": ac,
                "steps": _steps_from_text(ac),
                "journey_type": _journey_type(ac, story),
            }
        )

    for idx, fr in enumerate(spec.get("functional_requirements") or []):
        if not isinstance(fr, dict):
            continue
        title = str(fr.get("title") or fr.get("id") or f"Functional requirement {idx + 1}").strip()
        ac = str(fr.get("acceptance_criteria") or "").strip()
        if not ac:
            continue
        scenarios.append(
            {
                "id": str(fr.get("id") or f"FR-{idx + 1:02d}"),
                "source": "functional_requirement",
                "title": title,
                "acceptance_criteria": ac,
                "steps": _steps_from_text(ac),
                "journey_type": _journey_type(ac, title),
            }
        )

    # The product's own acceptance document counts. A round CAN write this file, which is the
    # difference between a gate that teaches and a gate that blocks.
    doc_scenarios: list[dict[str, Any]] = []
    if code_dir is not None:
        for name in ("docs/acceptance-scenarios.md", "docs/acceptance_scenarios.md"):
            doc = code_dir / name
            if not doc.is_file():
                continue
            try:
                text = doc.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            current: str | None = None
            body: list[str] = []

            def _flush(title: str | None, lines: list[str]) -> None:
                if not title:
                    return
                blob = "\n".join(lines).strip()
                doc_scenarios.append(
                    {
                        "id": f"DOC-{len(doc_scenarios) + 1:02d}",
                        "source": name,
                        "title": title,
                        "acceptance_criteria": blob or title,
                        "steps": _steps_from_text(blob or title),
                        "journey_type": _journey_type(blob, title),
                    }
                )

            for line in text.splitlines():
                heading = re.match(r"^#{2,4}\s+(.+?)\s*$", line)
                if heading:
                    _flush(current, body)
                    current, body = heading.group(1), []
                elif current:
                    body.append(line)
            _flush(current, body)
            break
    scenarios.extend(doc_scenarios)

    profile = str(spec.get("delivery_profile") or "marketing_landing")
    min_required = 3 if profile == "full_software" else 2
    journey_required = ["onboarding", "core_action", "edge_case", "recovery"] if profile == "full_software" else ["core_action"]
    journey_present = {str(s.get("journey_type")) for s in scenarios}
    missing_journeys = [j for j in journey_required if j not in journey_present]
    passed = len(scenarios) >= min_required and len(missing_journeys) == 0
    return {
        "delivery_profile": profile,
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "minimum_required": min_required,
        "journey_required": journey_required,
        "journey_present": sorted(journey_present),
        "missing_journeys": missing_journeys,
        "doc_scenario_count": len(doc_scenarios),
        "passed": passed,
    }
