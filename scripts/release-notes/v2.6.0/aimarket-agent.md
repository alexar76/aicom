# aimarket-agent 2.6.0 — receipts verified per signer, protocol proofs bound, Ed25519 hardened

```bash
pip install aimarket-agent==2.6.0
```

The last GitHub release was v2.2.0 (2026-08-12); PyPI has shipped 2.3–2.6 since. What changed:

- **Receipts are verified against the key that signed them** (2.2.0, kept since): a federated provider's Ed25519 signature is checked against the provider's key, resolved per origin and cached, not the hub's; the v2 rejection canonical (`reason`, `verify_score`, `trace_id`, `refunded`, `channel_id`) is understood; the `.well-known` key fetch cannot be steered (fragment and query dropped, http/https only, no redirects).
- **Every Ed25519 verifier refuses small-order keys** (2026-10-12), and the 2026-10-14 releases exist to ship exactly those fixes: the files had changed after each version was published, so the version numbers moved.
- **Protocol proofs are bound and payment/credit transitions protected** (2026-10-25): a mandate's request proof signs the exact bytes sent; a mandate or job refusal is reported as `refused`, apart from a content-safety verdict.
- Mandates and `JobContext` follow hub 3.16.0: an agent holds its own key and the owner's limits and never sees the owner's API key; a provider buying while serving a call passes the job it was handed.
- CI: every action pinned, read-only default tokens, OIDC jobs run no dependency code; the CI badge shows the repository's real Actions status.

Coming in 2.6.1 (in the monorepo now): the free trial from the CLI and SDK (`--sandbox-visitor`, `AIMARKET_SANDBOX_VISITOR`), `invoke --source-hub`, and error text on a refused call instead of a bare ✗.

Full history: the monorepo [aicom](https://github.com/alexar76/aicom) `aimarket-agent/` commits.
