"""Find a subsystem the product was never asked for, and say to remove it.

Measured on the live product, which is a weather-and-wildfire safety companion:

    routers/analytics.py          258 lines, imports 8 names that exist nowhere
    schemas/analytics.py           78 lines
    services/analytics_engine.py    3 lines  — a stub, which is why those 8 never resolve
    models/analytics.py           139 lines, 7 tables: dashboards, charts, datasets, share_links…

478 lines of BI dashboard, registered in ``main.py``, in a product whose charter says *"autonomous,
LLM-free safety companion … weather, wildfire and flooding … proves every statement with a signed
evidence receipt … invoking the ATLAS sensor-mesh"*. No dashboards, no charts, no datasets, no CSV
export — not in the charter, not in the spec, not in the idea.

It came from a methodology gate that classified the product as ``analytics_bi`` and demanded
``POST /api/datasets``, ``POST /api/dashboards``, ``GET /api/dashboards/{id}/export``. The factory
built them, left the engine as a stub, and **eight of the nine remaining blocking defects live in that
one router**. Rounds had been spending themselves trying to make the wrong product compile, and every
"define ``get_dashboard_data``" instruction was work in the wrong direction: succeeding would have
been worse than failing.

One finding that says "this subsystem is not part of this product" replaces eight that say "write the
missing half of it".

Deleting code is the most destructive advice a gate can give, so the bar is deliberately high:

* the cluster must be **actively broken** — at least ``MIN_DEFECTS`` blocking static defects. Merely
  unused code is not this gate's business.
* its distinctive vocabulary must be **absent from the charter**, checked over the idea, the spec and
  the admin instructions together.
* the charter must be substantial enough to be evidence. An empty charter means no opinion, never
  "nothing is chartered, delete everything".
* the finding must name the **registration sites** too. Deleting a router without unregistering it
  turns an ImportError into a different ImportError.
"""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any

# Below this, a broken import is a defect to fix rather than evidence of a whole foreign subsystem.
MIN_DEFECTS = 3

# A charter shorter than this cannot be used to conclude that something is absent from it.
MIN_CHARTER_CHARS = 200

# Words that carry no domain meaning, so their absence from a charter proves nothing.
_STOPWORDS = frozenset(
    {
        "api", "app", "service", "services", "schema", "schemas", "model", "models", "router",
        "routers", "util", "utils", "core", "engine", "data", "create", "out", "in", "get", "set",
        "list", "new", "base", "main", "test", "tests", "src", "backend", "frontend", "index",
        "type", "types", "helper", "helpers", "common", "shared", "lib", "config", "settings",
    }
)


# Infrastructure vocabulary: a charter does not mention a logger, and its absence proves nothing about
# whether a subsystem was ordered. Kept separate from ``_STOPWORDS`` on purpose — that set also decides
# what forms a cluster, and putting "security" in it would stop a genuinely security-named subsystem
# from ever being recognised as one.
_GENERIC_WORDS = frozenset(
    {"logger", "log", "logging", "security", "token", "generate", "format", "parse", "handler",
     "client", "cache", "session", "request", "response", "error", "exception", "middleware"}
)


# Specification fields that record what was ORDERED. Everything else in a spec — and everything in
# the product's stored state — is the pipeline talking about the order, not the order itself.
CHARTER_SPEC_FIELDS = (
    "product_name",
    "summary",
    "description",
    "overview",
    "goals",
    "objectives",
    "personas",
    "scope",
    "out_of_scope",
    "user_stories",
    "functional_requirements",
    "non_functional_requirements",
    "acceptance_criteria",
    "constraints",
)

# Deliberately NOT in that list: `domain`. That field is what the pipeline CONCLUDED about the
# product, and treating a conclusion as part of the order is how this went wrong. Measured: the
# charter QA assembled came to 28,067 characters and contained "analytics/bi" — from the text of a
# finding, "Methodology gate (analytics_bi): domain_api_endpoint_missing", stored in the product's own
# state. So a gate complaining that BI endpoints were missing became the evidence that BI had been
# ordered, which protected the BI subsystem from removal, which kept the gate complaining. A closed
# loop in which a misclassification licenses itself.


def charter_text(idea: Any, specification: Any, admin_instructions: Any = "") -> str:
    """What the customer asked for, and nothing the pipeline has said about it.

    Assembled by whitelist rather than by dumping the specification, because a spec accumulates gate
    output, and a charter that contains our own findings can be made to say anything by a gate that
    is wrong.
    """
    parts: list[str] = [str(idea or ""), str(admin_instructions or "")]
    spec = specification
    if isinstance(spec, dict) and isinstance(spec.get("specification"), dict):
        spec = spec["specification"]
    if isinstance(spec, dict):
        for field in CHARTER_SPEC_FIELDS:
            value = spec.get(field)
            if value in (None, "", [], {}):
                continue
            parts.append(value if isinstance(value, str) else _json.dumps(value, ensure_ascii=False))
    return " ".join(p for p in parts if p)


def _words(text: str) -> set[str]:
    """Lowercase word-ish tokens, snake_case and CamelCase both split."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(text or ""))
    return {w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if len(w) > 2}


def _cluster_of(rel_path: str) -> str:
    """The subsystem a file belongs to: its stem's leading word.

    ``services/analytics_engine.py`` and ``routers/analytics.py`` are one subsystem; that is the whole
    point, since the defects are spread across the layers rather than concentrated in one file.
    """
    stem = Path(rel_path).stem.lower()
    head = re.split(r"[^a-z0-9]", stem)[0] if stem else ""
    return "" if head in _STOPWORDS else head


def find_unchartered_subsystems(
    code_dir: Path,
    charter_text: str,
    *,
    min_defects: int = MIN_DEFECTS,
) -> list[dict[str, Any]]:
    """Clusters of broken code whose vocabulary appears nowhere in what was ordered."""
    charter = str(charter_text or "")
    if len(charter.strip()) < MIN_CHARTER_CHARS:
        return []  # no opinion rather than a destructive one
    chartered = _words(charter)

    try:
        from web.backend.services.duplicate_module_check import (
            find_missing_instance_attributes,
            find_missing_modules,
            find_missing_symbols,
        )
    except Exception:
        return []

    # Group defects by the cluster of the file that *reads* them: the importer is the code that
    # should not exist, while the file that fails to define the name may be a legitimate stub.
    by_cluster: dict[str, dict[str, Any]] = {}

    def note(cluster: str, reader: str, label: str, vocabulary: str) -> None:
        if not cluster:
            return
        entry = by_cluster.setdefault(
            cluster, {"defects": [], "readers": set(), "words": set()}
        )
        entry["defects"].append(label)
        entry["readers"].add(reader)
        entry["words"] |= _words(vocabulary)

    try:
        for item in find_missing_symbols(code_dir, limit=200):
            for reader in item.get("importers") or []:
                note(
                    _cluster_of(str(reader)),
                    str(reader),
                    f"{item.get('module')}.{item.get('symbol')}",
                    f"{item.get('module')} {item.get('symbol')}",
                )
        for item in find_missing_modules(code_dir, limit=200):
            for reader in item.get("importers") or []:
                note(_cluster_of(str(reader)), str(reader), str(item.get("module")), str(item.get("module")))
        for item in find_missing_instance_attributes(code_dir, limit=200):
            for reader in item.get("readers") or []:
                rel = str(reader).split(":")[0]
                note(_cluster_of(rel), rel, str(item.get("attribute")), str(item.get("attribute")))
    except Exception:
        return []

    findings: list[dict[str, Any]] = []
    for cluster, entry in sorted(by_cluster.items()):
        if len(entry["defects"]) < min_defects:
            continue
        if cluster in chartered:
            continue  # the product asked for this; the defects are ordinary work
        if cluster in _GENERIC_WORDS:
            continue  # a `logger` cluster is plumbing, and no charter lists its plumbing
        meaningful = {
            w for w in entry["words"] if w not in _STOPWORDS and w not in _GENERIC_WORDS
        }
        foreign = meaningful - chartered
        # ANY foothold in the charter protects the cluster. Both failing cases were this: an
        # `advisory` cluster whose charter never says "advisory" but does say "evidence receipt", and
        # the ratio of foreign-to-chartered words was 3:2 — enough for a threshold to fire on the
        # product's own core. A gate that recommends deletion has to be wrong in the quiet direction,
        # so one chartered word anywhere in the subsystem's vocabulary is enough to leave it alone.
        if meaningful & chartered:
            continue
        if not foreign:
            continue

        # Everything that belongs to the cluster, and everything that wires it in.
        members = sorted(
            p.relative_to(code_dir).as_posix()
            for p in code_dir.rglob("*.py")
            if _cluster_of(p.relative_to(code_dir).as_posix()) == cluster
            and ".aicom_sandbox" not in p.parts
            and "node_modules" not in p.parts
        )
        registrations: list[str] = []
        pattern = re.compile(rf"\b{re.escape(cluster)}\b")
        for path in code_dir.rglob("*.py"):
            rel = path.relative_to(code_dir).as_posix()
            if rel in members or ".aicom_sandbox" in path.parts:
                continue
            try:
                if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                    registrations.append(rel)
            except OSError:
                continue

        findings.append(
            {
                "code": "unchartered_subsystem",
                "severity": "critical",
                "cluster": cluster,
                "file": members[0] if members else sorted(entry["readers"])[0],
                "files": members,
                "registered_in": sorted(registrations)[:6],
                "defect_count": len(entry["defects"]),
                "defects": sorted(set(entry["defects"]))[:10],
                "foreign_words": sorted(foreign)[:10],
                "detail": (
                    f"The '{cluster}' subsystem accounts for {len(entry['defects'])} blocking defects "
                    f"and nothing in the product's charter asks for it — none of "
                    f"{', '.join(sorted(foreign)[:6])} appears in the idea, the specification or the "
                    f"admin instructions. Files: {', '.join(members[:8])}. "
                    f"REMOVE them and unregister the subsystem in "
                    f"{', '.join(sorted(registrations)[:4]) or 'whatever imports it'} — deleting a "
                    "router without unregistering it only changes which ImportError you get. Do not "
                    "implement the missing names: succeeding at that would leave the product carrying "
                    "a second product it was never asked for."
                ),
            }
        )
    return findings
