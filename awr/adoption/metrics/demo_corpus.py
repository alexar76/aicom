#!/usr/bin/env python3
"""Mint the synthetic corpus the README's "what a run looks like" transcript is computed from.

    THIS CORPUS CONTAINS NO ADOPTION.  Every key here is derived from a seed published
    a few lines below.  Anyone can mint documents under any of these DIDs, so a document
    signed by one of them is evidence of nothing at all.  The corpus exists for exactly
    one purpose: so that a reader can re-run the numbers printed in README.md instead of
    trusting a transcript.

DRAFT ON DISK.  Nothing here sends, posts, publishes or uploads anything: it writes files
into a directory you name, signs them with the AWR reference implementation, and stops.

Usage (from the repository root)::

    python3 awr/adoption/metrics/adoption_metric.py --demo-corpus /tmp/awr-demo
    # or directly:
    python3 awr/adoption/metrics/demo_corpus.py /tmp/awr-demo

The output is byte-identical on every run: the six signing keys come from fixed published
seeds and every timestamp is a constant.  Two of the six are declared "ours" in the
``own-keys.txt`` the generator writes next to the corpus, so the transcript shows the
arithmetic the metric is built on -- five valid issuers, two declared, three counted.

All six DIDs are ALSO listed in this directory's real ``own-keys.txt``, which is the file
the tool reads by default.  That is deliberate and it is the honest arrangement: they are
keys this repository can issue under, so a demo document that strays into a real corpus must
count as zero.  It also means you must pass ``--own-keys <dir>/own-keys.txt`` explicitly to
see the demo arithmetic -- with the default own-keys file this corpus reports 0, which is
the correct answer for six keys whose private halves are published.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# the published seeds
# ---------------------------------------------------------------------------

#: Every demo seed is ``sha256(DEMO_SEED_PREFIX + role)``.  Published, therefore worthless
#: as evidence, therefore safe: a reader can derive every private key in this corpus.
DEMO_SEED_PREFIX = b"awr.adoption.demo-corpus/1:"

#: role -> (classification in the demo own-keys file, what the role is there to show)
DEMO_ROLES: Tuple[Tuple[str, str, str], ...] = (
    ("our-hub", "ours", "stands in for our own hub: valid documents that are not adoption"),
    ("our-metis", "ours", "stands in for our own verification tier"),
    ("swarm-runner", "foreign", "one adopter emitting a lot of volume (40 receipts)"),
    ("third-party-juror", "foreign", "one adopter that only ever verifies other people"),
    ("careful-labs", "foreign", "one adopter whose receipt reaches profile L2"),
    (
        "struggling-issuer",
        "foreign",
        "issues one document whose signature does not verify: named, not counted",
    ),
)

OURS = tuple(role for role, kind, _ in DEMO_ROLES if kind == "ours")

# Fixed clock. Everything is in the past relative to the --now the README run uses, so no
# AWR-TIME-001/002 warning depends on when you run this.
SWARM_FIRST = "2026-07-01T12:00:00Z"
SWARM_LAST = "2026-07-28T12:00:00Z"
HUB_DAYS = ("2026-07-02", "2026-07-03")
LABS_AT = "2026-07-20T09:00:00Z"
VERDICT_AT = "2026-07-21T09:00:00Z"
STRUGGLING_AT = "2026-07-22T09:00:00Z"

STAKE = {
    "scheme": "stake-evm-v1",
    "chainId": 8453,
    "contract": "0x0000000000000000000000000000000000000000",
    "amount": {"currency": "USD", "amount": "5.00"},
}

DEMO_NOTICE = (
    "SYNTHETIC DEMONSTRATION CORPUS. Every signing key below is derived from a seed "
    "published in awr/adoption/metrics/demo_corpus.py, so anyone can mint documents "
    "under these DIDs. Nothing here is adoption, and nothing here is evidence of "
    "anything. It exists so the transcript in README.md can be regenerated."
)


def _seed(role: str) -> bytes:
    return hashlib.sha256(DEMO_SEED_PREFIX + role.encode("utf-8")).digest()


def _uuid_from(label: str) -> str:
    """A deterministic RFC 4122-shaped URN, so document ids are stable across runs."""
    raw = bytearray(hashlib.sha256(DEMO_SEED_PREFIX + b"id:" + label.encode("utf-8")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x50  # version 5, i.e. name-based
    raw[8] = (raw[8] & 0x3F) | 0x80  # RFC 4122 variant
    hexed = raw.hex()
    return "urn:uuid:%s-%s-%s-%s-%s" % (
        hexed[0:8], hexed[8:12], hexed[12:16], hexed[16:20], hexed[20:32],
    )


def _import_awr() -> Any:
    here = os.path.dirname(os.path.abspath(__file__))
    reference = os.path.normpath(os.path.join(here, "..", "..", "reference", "python"))
    try:
        import awr  # type: ignore

        return awr
    except Exception:
        pass
    if os.path.isdir(reference) and reference not in sys.path:
        sys.path.insert(0, reference)
    import awr  # type: ignore

    return awr


def demo_keys(awr: Optional[Any] = None) -> Dict[str, Any]:
    """role -> SigningKey, derived from the published seeds."""
    module = awr or _import_awr()
    return {role: module.SigningKey.from_seed(_seed(role)) for role, _, _ in DEMO_ROLES}


def demo_dids(awr: Optional[Any] = None) -> Dict[str, str]:
    """role -> did:key. Used by the test that asserts every demo DID is declared as ours."""
    return {role: key.did for role, key in demo_keys(awr).items()}


# ---------------------------------------------------------------------------
# document builders
# ---------------------------------------------------------------------------


def _receipt(awr: Any, key: Any, *, label: str, when: str, model: str, name: str,
             settlement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    subject: Dict[str, Any] = {
        "work": {
            "modelId": model,
            "startedAt": when,
            "completedAt": when,
            "status": "succeeded",
        },
        "inputDigest": awr.EMPTY_PAYLOAD_SRI,
        "outputDigest": awr.EMPTY_PAYLOAD_SRI,
        "note": DEMO_NOTICE,
    }
    if settlement:
        subject["settlement"] = settlement
    return awr.issue_work_receipt(
        subject,
        key,
        document_id=_uuid_from(label),
        valid_from=when,
        created=when,
        issuer_name=name,
    )


def _verdict(awr: Any, key: Any, target: Dict[str, Any], *, label: str, when: str,
             name: str, stake: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    subject: Dict[str, Any] = {
        "verifiedWork": awr.document_reference(target),
        "verdict": "pass",
        "method": {"id": "urn:awr:demo:method:replay-check:v1", "name": "demo replay check"},
        "note": DEMO_NOTICE,
    }
    if stake:
        subject["stake"] = stake
    return awr.issue_verification_verdict(
        subject,
        key,
        document_id=_uuid_from(label),
        valid_from=when,
        created=when,
        issuer_name=name,
    )


def _tamper(document: Dict[str, Any]) -> Dict[str, Any]:
    """Break the signature without breaking the envelope, deterministically.

    The document still parses, still carries an ``issuer.id``, and still looks like a
    receipt -- which is the point: the metric must name the issuer and refuse to count it.
    """
    broken = json.loads(json.dumps(document))
    value = broken["proof"]["proofValue"]
    # Swap one base58 character for another valid one, in the middle of the signature.
    middle = len(value) // 2
    replacement = "3" if value[middle] != "3" else "4"
    broken["proof"]["proofValue"] = value[:middle] + replacement + value[middle + 1:]
    return broken


# ---------------------------------------------------------------------------
# the corpus
# ---------------------------------------------------------------------------


def build_documents(awr: Optional[Any] = None) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
    """Return ``(keys_by_role, files)`` where *files* maps a filename to its documents."""
    module = awr or _import_awr()
    keys = demo_keys(module)

    hub_receipts = [
        _receipt(
            module,
            keys["our-hub"],
            label="our-hub/%d" % (index,),
            when="%sT10:00:00Z" % (day,),
            model="claude-sonnet-5@anthropic",
            name="our-hub",
        )
        for index, day in enumerate(HUB_DAYS)
    ]

    # 40 receipts from one key: volume, not adopters. Dates walk from SWARM_FIRST to
    # SWARM_LAST so firstSeen/lastSeen in the report are the two constants above.
    swarm_receipts = []
    for index in range(40):
        if index == 0:
            when = SWARM_FIRST
        elif index == 39:
            when = SWARM_LAST
        else:
            # 40 receipts walked across 2026-07-01 .. 2026-07-28, several per day.
            when = "2026-07-%02dT12:00:00Z" % (1 + (index * 27) // 39,)
        swarm_receipts.append(
            _receipt(
                module,
                keys["swarm-runner"],
                label="swarm-runner/%d" % (index,),
                when=when,
                model="demo-model@example",
                name="swarm-runner",
            )
        )

    # A stranger verifying one of OUR receipts. Still one adopter, still not our number.
    swarm_verdict = _verdict(
        module,
        keys["swarm-runner"],
        hub_receipts[0],
        label="swarm-runner/verdict",
        when=SWARM_LAST,
        name="swarm-runner",
    )

    labs_receipt = _receipt(
        module,
        keys["careful-labs"],
        label="careful-labs/receipt",
        when=LABS_AT,
        model="claude-opus-5@anthropic",
        name="careful-labs",
    )
    # Two verdicts from two distinct issuers, neither the receipt's issuer, each carrying
    # a stake: SPEC §10.3, so the receipt reaches L2. Profile changes nothing about
    # whether a document counts -- that is one of the things the transcript shows.
    juror_verdict = _verdict(
        module,
        keys["third-party-juror"],
        labs_receipt,
        label="third-party-juror/verdict",
        when=VERDICT_AT,
        name="third-party-juror",
        stake=STAKE,
    )
    metis_verdict = _verdict(
        module,
        keys["our-metis"],
        labs_receipt,
        label="our-metis/verdict",
        when=VERDICT_AT,
        name="our-metis",
        stake=STAKE,
    )

    struggling = _tamper(
        _receipt(
            module,
            keys["struggling-issuer"],
            label="struggling-issuer/receipt",
            when=STRUGGLING_AT,
            model="demo-model@example",
            name="struggling-issuer",
        )
    )

    files: Dict[str, List[Dict[str, Any]]] = {
        "ours-hub-receipts.json": hub_receipts,
        "ours-metis-verdict.awr.json": [metis_verdict],
        "swarm-runner.jsonl": swarm_receipts + [swarm_verdict],
        "third-party-juror.awr.json": [juror_verdict],
        "careful-labs-receipt.awr.json": [labs_receipt],
        # Byte-identical copy of a document already in swarm-runner.jsonl: the same
        # document id must collapse to one, not count twice.
        "duplicate-of-swarm-0001.awr.json": [swarm_receipts[0]],
        "struggling-001.awr.json": [struggling],
    }
    return keys, files


def write_corpus(directory: str, awr: Optional[Any] = None) -> Dict[str, Any]:
    """Write the corpus, an own-keys file and a NOTICE. Returns a small summary dict."""
    module = awr or _import_awr()
    keys, files = build_documents(module)

    corpus = os.path.join(directory, "corpus")
    os.makedirs(corpus, exist_ok=True)

    written: List[str] = []
    document_count = 0
    for name, documents in sorted(files.items()):
        path = os.path.join(corpus, name)
        with open(path, "w", encoding="utf-8") as handle:
            if name.endswith(".jsonl"):
                for document in documents:
                    handle.write(json.dumps(document, ensure_ascii=False) + "\n")
            elif len(documents) == 1:
                handle.write(json.dumps(documents[0], indent=2, ensure_ascii=False) + "\n")
            else:
                handle.write(json.dumps(documents, indent=2, ensure_ascii=False) + "\n")
        written.append(name)
        document_count += len(documents)

    # An unreadable input, on purpose: a corpus collected in the wild has one, and the
    # tool must report it rather than quietly scanning 7 files and calling it 8.
    with open(os.path.join(corpus, "junk.json"), "w", encoding="utf-8") as handle:
        handle.write("{this is not JSON, and a real corpus always has one of these\n")
    written.append("junk.json")

    own_keys_path = os.path.join(directory, "own-keys.txt")
    lines = [
        "# own-keys file for the SYNTHETIC demo corpus in ./corpus.",
        "#",
        "# " + DEMO_NOTICE.replace(". ", ".\n# "),
        "#",
        "# Two of the six demo issuers are declared here. The other four are left out so",
        "# that the transcript in ../README.md shows the arithmetic: five valid issuers,",
        "# two declared as ours, three counted. Removing these two lines makes the",
        "# headline 5 instead of 3, which is the metric's one failure mode.",
        "",
    ]
    for role in OURS:
        lines.append("%s  # demo / %s / synthetic, seed published in demo_corpus.py" % (keys[role].did, role))
    with open(own_keys_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    notice_path = os.path.join(directory, "NOTICE.txt")
    with open(notice_path, "w", encoding="utf-8") as handle:
        handle.write(DEMO_NOTICE + "\n\nDIDs in this corpus, and the role each one plays:\n\n")
        for role, kind, why in DEMO_ROLES:
            handle.write("  %s\n      %-8s %s\n" % (keys[role].did, kind, why))
        handle.write(
            "\nEvery seed is sha256(%r + role). Derive them yourself:\n"
            "  python3 -c \"import hashlib; print(hashlib.sha256(%r + b'swarm-runner').hexdigest())\"\n"
            % (DEMO_SEED_PREFIX, DEMO_SEED_PREFIX)
        )

    return {
        "directory": directory,
        "corpus": corpus,
        "ownKeys": own_keys_path,
        "notice": notice_path,
        "files": sorted(written),
        "documents": document_count,
        "dids": {role: keys[role].did for role, _, _ in DEMO_ROLES},
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: demo_corpus.py DIRECTORY\n\n"
            "Writes a synthetic, deterministic AWR corpus plus the own-keys file the\n"
            "README transcript is computed with. No network access, nothing published.\n"
        )
        return 2
    try:
        module = _import_awr()
    except Exception as exc:  # pragma: no cover - depends on the machine
        sys.stderr.write(
            "the AWR reference implementation is required to sign the demo corpus: %s: %s\n"
            % (type(exc).__name__, exc)
        )
        return 2
    summary = write_corpus(args[0], module)
    sys.stderr.write(DEMO_NOTICE + "\n\n")
    sys.stderr.write(
        "wrote %d documents in %d files to %s\n"
        % (summary["documents"], len(summary["files"]), summary["corpus"])
    )
    sys.stderr.write("own-keys file (declares 2 of 6 demo DIDs): %s\n\n" % (summary["ownKeys"],))
    sys.stderr.write(
        "now reproduce the README transcript:\n"
        "  python3 %s %s --own-keys %s --format human --now 2026-07-31T12:00:00Z --require-reference\n"
        % (
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "adoption_metric.py"),
            summary["corpus"],
            summary["ownKeys"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
