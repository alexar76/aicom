"""Give every unattested Memory Unit its ledger receipt.

    python -m memory_market.reconcile_provenance          # attest what is missing
    python -m memory_market.reconcile_provenance --count  # only count; writes nothing
    python -m memory_market.reconcile_provenance --check  # compare attested units with the ledger

A write asks the Provenance Ledger for a ``created`` receipt once, and a ledger that is down or slow
leaves the unit ``unattested``. This finishes those: for each unit it first looks for a ``created``
receipt of the same content in the owner's name already in the ledger (an attest that landed while
its answer was lost; a receipt someone else appended with the same hash is not taken),
and only asks for a new one when there is none, so running it again never doubles a receipt. A unit
the ledger still cannot take stays unattested and is counted. scripts/systemd/ has an hourly timer
that runs it and then --check; it pages by id and is safe beside the service.

``--check`` is the comparison from outside the ledger. The ledger's own ``chain_head`` check holds
its database against itself, so whoever can write that database can delete receipts and move the
head together. The market keeps, for every attested unit, the receipt id and chain root the ledger
returned; ``--check`` requires that receipt to still be in the unit's chain with that root, and the
ledger to verify it. A mismatch is printed per unit and the command exits 2. It cannot see receipts
appended after the one the market recorded (an owner's own appends through the hub).
"""

from __future__ import annotations

import argparse
import json
import sys

from .clients import TrustClients
from .config import get_settings


def reconcile(store, clients: TrustClients, *, write: bool = True, page: int = 200) -> dict[str, int]:
    result = {"unattested": 0, "linked": 0, "attested": 0, "failed": 0}
    after = ""
    while True:
        units = store.unattested(page, after)
        if not units:
            return result
        for unit in units:
            result["unattested"] += 1
            if not write:
                continue
            receipt = clients.created_receipt(unit)
            if receipt:
                result["linked"] += 1
            else:
                receipt = clients.attest(unit, "created", unit.owner_id)
                if not receipt:
                    result["failed"] += 1
                    continue
                result["attested"] += 1
            store.set_provenance(unit.id, receipt["id"], receipt["chain_root"])
        after = units[-1].id


def check(store, clients: TrustClients, *, page: int = 200) -> dict:
    result: dict = {"attested": 0, "matching": 0, "unreachable": 0, "mismatched": []}
    after = ""
    while True:
        units = store.attested(page, after)
        if not units:
            return result
        for unit in units:
            result["attested"] += 1
            lineage = clients.lineage(unit.id)
            verdict = clients.verify_receipt(unit.provenance.receipt_id) if unit.provenance.receipt_id else None
            if lineage is None or (unit.provenance.receipt_id and verdict is None):
                result["unreachable"] += 1
                continue
            problem = _mismatch(unit, lineage, verdict)
            if problem:
                result["mismatched"].append({"memory_id": unit.id, "receipt_id": unit.provenance.receipt_id,
                                             "problem": problem})
            else:
                result["matching"] += 1
        after = units[-1].id


def _mismatch(unit, lineage: dict, verdict: dict | None) -> str | None:
    receipt_id, root = unit.provenance.receipt_id, unit.provenance.lineage_root
    if not receipt_id or not root:
        return "attested here without a receipt id or chain root"
    in_chain = [r for r in lineage.get("receipts") or [] if r.get("id") == receipt_id]
    if not in_chain:
        return "the recorded receipt is no longer in the ledger chain"
    if in_chain[0].get("chain_root") != root:
        return "the receipt's chain root differs from the one the ledger returned on append"
    if not (verdict or {}).get("valid"):
        failed = sorted(k for k, ok in ((verdict or {}).get("checks") or {}).items() if not ok)
        return "the ledger does not verify the receipt: " + (", ".join(failed) or "invalid")
    return None


def main(argv: list[str] | None = None) -> int:
    from .app import store

    parser = argparse.ArgumentParser(prog="python -m memory_market.reconcile_provenance",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", action="store_true", help="only count unattested units")
    parser.add_argument("--check", action="store_true",
                        help="compare each attested unit's recorded receipt and root with the ledger")
    args = parser.parse_args(argv)
    if args.check:
        outcome = check(store(), TrustClients(get_settings()))
        print(json.dumps(outcome))
        return 2 if outcome["mismatched"] else (1 if outcome["unreachable"] else 0)
    result = reconcile(store(), TrustClients(get_settings()), write=not args.count)
    print(json.dumps(result))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
