# Reply to Simon Strandgaard (re-read of attested-memory @ 25d6b1a, his atlas commit a9b7c179f) — DRAFT 2026-11-25

Owner sends in the same thread AFTER §171 (mirror sync); replace <SHA> with the mirror commit.
2026-11-25 ~16:10Z: §171 reported done, but GitHub main is still 25d6b1a (ls-remote), new test files 404 → not sendable yet.
All four points checked against the code; fixes in aicom main 445100fe7, LIVE on attestedmemory.net 2026-11-25 14:49Z.
Plus five gaps from our own reading in the same style: main 6ba17aacf, LIVE 15:20Z. Mirror must be at 6ba17aacf or newer.

## Text

Hi Simon,

Thanks for the quick re-read. The four points held, and they are fixed at
https://github.com/alexar76/attested-memory/commit/<SHA> :

1. A deleted head row no longer comes back. The backfill from receipts runs once, for databases from before
   receipt_heads existed, and is then marked done. After that a memory with receipts but no head fails chain_head,
   and append refuses to extend it instead of starting again from genesis.

2. The market's copy of the chain root is now compared. python -m memory_market.reconcile_provenance --check
   requires each attested unit's recorded receipt to still be in its ledger chain, with the root the ledger returned
   on append, and the ledger to verify it. A test deletes the newest receipt and moves the head back: the ledger's
   own checks pass, and --check reports the unit. It cannot see receipts appended after the one the market recorded.

3. memory.attest@v1 through the hub now extends only a chain whose first receipt is the caller's, and starts no
   chain under a Memory Market id; the market gives those their first receipt. The reconcile links a created
   receipt only when it is in the unit owner's name.

4. scripts/systemd has an hourly timer that runs the reconcile and then --check.

Reading the code again the way you do, I found five more and fixed them in the same range:

- A payment or verification receipt that landed before the creation receipt marked the unit attested, so the
  reconcile never added the creation. Only a created receipt sets attested now.
- lineage.get is open to any hub caller, and a payment receipt named the buyer and the transaction. It now
  carries a hash commitment to the order, the transaction and the buyer.
- Receipts of units that are not public carried their source references and parent ids, which the catalogue
  withholds from other callers; they now carry hashes. A verification receipt of such a unit carries a hash of
  the evidence pack id.
- The catalogue showed every unit's evidence pack id, and evidence.pack returns the claim to anyone holding it.
  The id now goes only to callers who may read the unit.
- docs/capabilities.md called a grant revocable, but nothing revoked one. Owners can now (DELETE on the grant, or
  memory.share with revoke: true); access a buyer paid for stays. The Python client has share and revoke from
  attested-memory 0.3.0.

The README also no longer says a poisoned memory is caught: the truth status is the owner's submitted evidence.

The ledger tests went from 11 to 13 and the market tests from 28 to 33, and tests/test_provenance_crosscheck.py
runs the market against a real ledger. All of it runs on attestedmemory.net since 25 November.

Best regards,
Alex
