# Reply to Simon Strandgaard (Agent Memory Atlas reading of attested-memory @ ca686945c) — SENT 2026-11-25 by the owner (qwezzy721@gmail.com, same thread)

§169 done 2026-11-25 05:12Z: mirror tip 25d6b1ab4f0983d2d3c3b35bf03c40535d9c91db (CI pytest/build/deploy green; all fixes present). Owner sends from qwezzy721@gmail.com as a reply in the same thread.

Checked 2026-11-24: all four points confirmed in the code. Fixes in aicom main 09e18a07c (Gitea), tests listed in the
commit; LIVE on attestedmemory.net 2026-11-24 (ROLLOUT.md here). Report: https://neoneye.github.io/agent-memory-atlas/systems/attested-memory/

## Text

Hi Simon,

Thank you for the careful reading. All four points hold, and the first three were bugs. They are fixed at https://github.com/alexar76/attested-memory/commit/25d6b1ab4f0983d2d3c3b35bf03c40535d9c91db :

1. Ledger.verify now also checks signer_key: both public keys in the receipt must be the ledger's own (or keys listed in PROVENANCE_TRUSTED_PUBLIC_KEYS and PROVENANCE_TRUSTED_PQ_PUBLIC_KEYS, for receipts signed before a rotation). A new test rewrites a row, recomputes both hashes and re-signs with another key; the hashes and signature still agree, and verify rejects it on the key. It also checks chain_head: the memory's newest stored receipt must be the head the ledger recorded, so deleting the newest receipts of a chain now fails verification. That head lives in the same database, so it catches lost or deleted rows, not someone who also rewrites the head; for that, a caller should compare against the chain_root it was given on append.

2. memory.write@v1 through the hub now requests a receipt, as the REST write does. python -m memory_market.reconcile_provenance attests units left unattested. It first looks for a created receipt of the same content already in the ledger, so a write whose receipt landed while the answer was lost is linked rather than attested twice.

3. memory.attest@v1 now refuses a caller the hub does not name (anonymous or trial), as the market's capability route does. lineage.get and receipt.verify stay open.

4. truth.status is now a read filter. Catalog and memory.search@v1 leave out memories the Truth Layer rejected unless the caller passes truth (a list of statuses, or any). A rejected memory stays readable by id, with its status. The verification method itself is unchanged: it still weighs submitted evidence, and the README still calls semantic verification an extension point.

The ledger tests grew from 7 to 11 and the market tests from 24 to 28. Three of the new ledger tests fail on ca686945c and pass at 25d6b1a. The same changes are running on attestedmemory.net since 24 November, and the five units written while the ledger missed them now have their receipts. While checking the deployment I also found that the hosted service still ran the older actor proof, signed over actor, time and nonce only; since 25 November it runs the request-bound one that is in the repository, covering destination, method, path, query and body.

If you re-read at the new pin, I'd be glad to hear what still falls short.

Best regards,
Alex
