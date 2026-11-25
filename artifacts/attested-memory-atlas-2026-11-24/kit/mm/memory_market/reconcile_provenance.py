"""Give every unattested Memory Unit its ledger receipt.

    python -m memory_market.reconcile_provenance          # attest what is missing
    python -m memory_market.reconcile_provenance --count  # only count; writes nothing

A write asks the Provenance Ledger for a ``created`` receipt once, and a ledger that is down or slow
leaves the unit ``unattested``. This finishes those: for each unit it first looks for a ``created``
receipt of the same content already in the ledger (an attest that landed while its answer was lost),
and only asks for a new one when there is none, so running it again never doubles a receipt. A unit
the ledger still cannot take stays unattested and is counted. Run it from a timer or after a ledger
outage; it pages by id and is safe beside the service.
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


def main(argv: list[str] | None = None) -> int:
    from .app import store

    parser = argparse.ArgumentParser(prog="python -m memory_market.reconcile_provenance",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", action="store_true", help="only count unattested units")
    args = parser.parse_args(argv)
    result = reconcile(store(), TrustClients(get_settings()), write=not args.count)
    print(json.dumps(result))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
