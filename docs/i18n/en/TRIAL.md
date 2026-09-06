# Free trial and upgrade

Personal has a 7-day free trial. Team has a 14-day trial. Expert Market has a
1-day trial. A trial is claimed once per verified actor and product.

The browser creates an Ed25519 actor proof. The Gateway issues one `ask_...`
trial key without a wallet payment. The key expires automatically and follows
the same introspection, rotation and revocation rules as a paid key.

When you are ready, choose a paid plan. The Gateway creates an exact canonical
USDC invoice on Base, KOVA verifies the transaction and a new paid key is
issued automatically after the required confirmations.
