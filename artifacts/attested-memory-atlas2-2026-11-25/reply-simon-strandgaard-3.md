# Reply to Simon Strandgaard on the third Atlas reading

Recipient is Simon Strandgaard, in the existing Attested Memory thread. The review
covers public revision `84e7057` and is published at Atlas commit `7f203a21`.

## Text

Hi Simon,

Thanks for re-reading `84e7057` and for correcting the database description. Your notes on evidence packs and the limits of the stored root were especially helpful.

The hourly reconcile timer is enabled on our hosted instance. I verified that the 25 November run at 18:23 UTC succeeded. The local follow-up adds an installer for the shipped systemd units.

The follow-up checks current read access when a caller requests an evidence pack tied to a memory. Personal and Team users can also read the pack through the same actor and team checks as the memory. New non-public receipts omit source and parent references and the evidence pack ID. Previously signed receipts retain their original fields.

Owner grants and revocations now record their history in the same transaction as the access change. Reconciliation verifies signatures and links across the available lineage. It can also export verified heads for comparison with a copy retained outside the shared database's administrative boundary. Independent retention is an operator step. The bundled deployment still uses one PostgreSQL database and role.

I also made the claim boundary explicit in the docs: the truth verdict summarizes submitted evidence, and labels on buyer-started chains are assertions attributed to that buyer.

These follow-up changes are in the local tree. Thanks again for the public review.

Best regards,
Alex
