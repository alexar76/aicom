# Reply to Simon Strandgaard on the third Atlas reading

Recipient is Simon Strandgaard, in the existing Attested Memory thread. The review
covers public revision `84e7057` and is published at Atlas commit `7f203a21`.

## Text

Hi Simon,

Thanks for re-reading `84e7057` and for correcting the shared database description. We deployed a follow-up to the hosted instance based on your findings.

On one synthetic private memory, both Personal Memory and the Hub’s `evidence.pack@v1` capability returned HTTP 404 before a grant, 200 with the grant, and 404 after revocation. The owner could still read the pack. The access history retained both grant and revoke pairs. New receipts for non-public memories omit source references, parent IDs and evidence pack IDs. Previously signed receipts retain their original fields.

Reconciliation now checks signatures and links from the first available receipt through the stored head. The production check matched all nine attested memories, with zero mismatches or unreachable records. Exporting the verified heads and checking against that export also passed. The bundled deployment still shares a PostgreSQL database and role. A checkpoint provides an independent reference when an operator keeps it outside that database’s administrative boundary.

The hourly timer is active, and the source now includes an installer for new deployments. The docs also clarify that the truth verdict summarizes submitted evidence and that event labels on buyer-started chains are assertions attributed to the buyer.

Best regards,
Alex
