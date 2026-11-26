# aimarket-hub 3.22.2 — built 2026-11-26, PyPI = colleague step §175

PyPI has 3.22.1 (2026-11-25). 3.22.2 adds one change, main 91b373a10: an entry copied from a peer is served only for
48 hours after the last verified read of that peer's catalogue (`AIMARKET_FEDERATED_MAX_UNVERIFIED_S`, default 172800,
0 = off); each crawl deletes the expired rows. Nothing else changed in aimarket-hub since 3.22.1. Details and the live
rollout: ../hub-federated-validity-2026-11-26/README.md. The six hubs already run this change as overlays (17:05–17:09Z).

Built with `uv build` from `git archive 91b373a10 aimarket-hub` (clean tree). Sums: wheels/SHA256SUMS.

## Checks

- `twine check`: both PASSED.
- The wheel's 230 package sources equal the commit byte for byte; the 6 `static/ui` files are generated at build, as in
  3.22.0 and 3.22.1.
- Fresh Python 3.12 venv: `aimarket_hub.__version__` 3.22.2, the bound present (default 172800).
- Full hub suite on the commit: 4377 passed, 2 failed — the two failing since 3.22.0
  (`test_mandates_hardening::TestJobTree::test_each_receipt_commits_to_its_own_children_by_their_receipt_ids`,
  `test_pipeline_provider::test_free_graph_needs_no_wallet_and_returns_one_sub1_tree`).
