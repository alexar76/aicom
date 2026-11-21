#!/usr/bin/env python3
"""An independent implementation of the E0-E4 grade floor of narko4u/evidence-record-spec.

Written from the rule text (VERIFIABILITY-OVERVIEW.md: Axis A/B/C, "What makes a party independent", the
E0-E4 ladder table, the receipt claims) and the README, not from evidence_grade_rules.py, so that a run of
the published corpus is a second reading of the text rather than the same code twice. Standard library only.

    python3 grade_independent.py <spec checkout>             # grade-floor/cases + fixtures/negative records
    python3 grade_independent.py --record a.json [b.json…]   # grade records of your own

A record gets a rung (E0..E4) and a decision: "accepted" when every claim it makes is supported at that rung,
"rejected" otherwise. The rung is derived from what the record says it observed; nothing the record stamps
raises it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LADDER = ["E0", "E1", "E2", "E3", "E4"]

# Axis A, as the ladder table reads it: the agent's own account is E0, a framework outside the agent E1, a
# boundary component of the deployment E2. A boundary component can rise no further on its own account:
# E3 needs a party that is not the deployment (Axis C).
SOURCE_RUNG = {
    "agent_self_report": "E0",
    "framework": "E1",
    "gateway_proxy": "E2",
    "sandbox": "E2",
    "operating_system": "E2",
    "network_sensor": "E2",
    "security_sensor": "E2",
    # Parties outside the deployment: their own account is not the deployment's.
    "identity_provider": "E2",
    "external_authority": "E2",
}
# Axis C custody of an engine name. Fail closed: an engine not listed is not independent.
CUSTODY = {
    "self_report": "SELF", "framework": "SELF", "gateway_proxy": "SELF", "sandbox": "SELF",
    "operating_system": "SELF", "network_sensor": "SELF", "security_sensor": "SELF",
    "counterparty_gateway": "PEER",
    "identity_provider": "EXTERNAL", "external_authority": "EXTERNAL",
}
# The agent's own account or a framework inside it has no outside party an anchor could bind to.
UNANCHORABLE = {"agent_self_report", "framework"}
CLAIM_FLOOR = {"emission-conformant": "E1", "operationally-conformant": "E3"}


def _lower(a: str, b: str) -> str:
    return a if LADDER.index(a) <= LADDER.index(b) else b


def grade(record: dict) -> dict:
    obs = record.get("observation") or {}
    ver = record.get("verification") or {}
    integ = record.get("integrity") or {}
    source = obs.get("source")
    notes: list[str] = []

    if source not in SOURCE_RUNG:
        return {"rung": "E0", "notes": ["unknown source: fail closed"], **_decide(record, "E0")}
    rung = SOURCE_RUNG[source]

    if (record.get("reconciliation") or {}).get("state") == "no_independent_evidence":
        notes.append("reconciliation says no independent evidence: E0")
        return {"rung": "E0", "notes": notes, **_decide(record, "E0")}

    engines = {e for e in (ver.get("basis_engines") or []) if isinstance(e, str)} | {source}
    outside = sorted(e for e in engines if CUSTODY.get(e) in ("PEER", "EXTERNAL"))
    own_id = record.get("record_id")
    references = [p for p in (record.get("provenance") or []) if isinstance(p, str) and p.strip() and p != own_id]
    if outside and references:
        rung = "E3"
        notes.append(f"independent party {outside} with a reference to its own record")
    elif outside:
        notes.append(f"{outside} named without a reference to that party's record: capped at E2")
    else:
        notes.append("no PEER or EXTERNAL party: cannot pass E2")

    if rung == "E3":
        verifiers = [v for v in (integ.get("verifiable_by") or []) if isinstance(v, str) and v and v != record.get("agent_id")]
        if source in UNANCHORABLE:
            notes.append("source cannot be anchored")
        elif integ.get("timestamped") is True and integ.get("chain_linked") is True and verifiers:
            rung = "E4"
            notes.append("timestamped, chain-linked, verifier other than the agent: anchored")
        else:
            notes.append("anchor markers incomplete: stays E3")
    return {"rung": rung, "notes": notes, **_decide(record, rung)}


def _decide(record: dict, rung: str) -> dict:
    reasons = []
    for c in record.get("claims") or []:
        claim = (c or {}).get("claim")
        if claim not in CLAIM_FLOOR:
            reasons.append(f"unknown claim {claim!r}")
            continue
        if LADDER.index(rung) < LADDER.index(CLAIM_FLOOR[claim]):
            reasons.append(f"{claim} needs {CLAIM_FLOOR[claim]}, record supports {rung}")
        if claim == "operationally-conformant" and (record.get("reconciliation") or {}).get("state") != "agreement":
            reasons.append("operationally-conformant needs reconciliation agreement")
    if (record.get("verification") or {}).get("basis") not in (None, f"{(record.get('verification') or {}).get('vantage')}_{(record.get('verification') or {}).get('method')}"):
        reasons.append("basis is not {vantage}_{method}")
    if (record.get("observation") or {}).get("relationship") == "derived" and not record.get("provenance"):
        reasons.append("derived record without provenance")
    if "grade" in record:
        reasons.append("a record may not carry a grade member")
    return {"decision": "rejected" if reasons else "accepted", "reasons": reasons}


def run_corpus(root: Path) -> int:
    rows, bad = [], 0
    for case in sorted((root / "grade-floor" / "cases").glob("*/case.json")):
        c = json.loads(case.read_text())
        got = grade(c["record"])
        exp = c.get("expect") or {}
        ok = got["rung"] == exp.get("derived_grade") and got["decision"] == exp.get("decision")
        bad += not ok
        rows.append((c["case_id"], exp.get("derived_grade"), exp.get("decision"), got["rung"], got["decision"], ok, got["notes"] + got["reasons"]))
    for f in sorted((root / "fixtures" / "negative").glob("*.json")):
        r = json.loads(f.read_text())
        if "observation" not in r:
            rows.append((f.stem, "-", "rejected (appraisal)", "-", "not graded: appraisal fixture", None, []))
            continue
        got = grade(r)
        ok = got["decision"] == "rejected"
        bad += not ok
        rows.append((f.stem, "-", "rejected", got["rung"], got["decision"], ok, got["notes"] + got["reasons"]))
    for name, er, ed, gr, gd, ok, why in rows:
        mark = "OK " if ok else ("-- " if ok is None else "DIFF")
        print(f"{mark} {name:58} expected {er:3} {ed:21} got {gr:3} {gd}")
        if ok is False:
            print("      " + "; ".join(why))
    graded = sum(1 for r in rows if r[5] is not None)
    print(f"\n{graded - bad}/{graded} graded cases agree with the published expectation")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec", nargs="?", type=Path)
    ap.add_argument("--record", nargs="+", type=Path)
    a = ap.parse_args(argv)
    if a.record:
        for p in a.record:
            print(p.name, json.dumps(grade(json.loads(p.read_text())), ensure_ascii=False))
        return 0
    if not a.spec:
        ap.error("give the spec checkout or --record")
    return run_corpus(a.spec)


if __name__ == "__main__":
    sys.exit(main())
