# attested-memory 0.3.0 (Python client) — built 2026-11-25, NOT on PyPI yet (colleague step §172)

PyPI has 0.2.0 (2026-11-03). 0.3.0 adds `Client.share` / `Client.revoke` and the CLI `share` / `revoke`
(main e9a8b2e7f, worktree commit 5f598f1b8). Built with `uv build` from `git archive e9a8b2e7f
attested/attested-memory-hub/clients/python`, so nothing uncommitted is inside.

| file | sha256 |
|---|---|
| attested_memory-0.3.0-py3-none-any.whl | see wheels/SHA256SUMS |
| attested_memory-0.3.0.tar.gz | see wheels/SHA256SUMS |

## Checks

- `twine check`: both PASSED.
- Wheel in a fresh Python 3.12 venv: `attested-memory --version` → 0.3.0, `--help` lists share and revoke.
- sdist tests in that venv (`python -I`): tests/test_client.py 7 passed. tests/test_actor_contract.py needs FastAPI and
  the Memory Market package (it checks the client against the server code); it does not run standalone, as in 0.2.0.
- In the monorepo: client 12, attested/tests 6 (the real Client through Gateway → Personal Memory → Memory Market with
  production actor checks: stranger 403, share, read, non-owner revoke 403, revoke, read 403, unknown grantee 404),
  personal-memory 2, hub suites 104.

## Service side (needed by share/revoke) — LIVE on attestedmemory.net

- Memory Market revoke route: `atlas3-20261125`, 15:20:09Z (../attested-memory-atlas2-2026-11-25/ROLLOUT.md).
- Personal Memory 1.1.0 grant routes: `aicom-security:aicom-personal-memory-grants-20261125` (sha256:5f4d1437…) over
  `aicom-personal-memory-actorv2-20261125`, rolled 15:45:24Z with rollout_container.py (no env dropped, no borrowers);
  previous container kept as `aicom-personal-memory-1-security-prev-1795621524761064518`, snapshot
  /root/security-rollbacks/aicom-personal-memory-1-1795621524761064518/inspect.json. Live app.py matched main before.
- Live probe with this wheel (throwaway actor, invalid key, nothing written): share, revoke and read → 401 "SaaS API key
  is invalid or expired" from key introspection; before the roll, POST/DELETE …/grants were 404. A real share/revoke on
  prod was not run (it needs a trial account on the live site).

Rollback of Personal Memory: `python3 /root/security-20261031/rollout_container.py aicom-personal-memory-1 --image
aicom-security:aicom-personal-memory-actorv2-20261125 --health http://127.0.0.1:9410/healthz`.
