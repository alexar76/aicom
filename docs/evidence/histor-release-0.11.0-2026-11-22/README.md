# HISTOR 0.11.0 — prepared 2026-11-22, not on PyPI

Owner, 2026-11-22: «готовь выпуск HISTOR». Version 0.11.0 in aicom `b243d0fe1` (`pyproject.toml`, `histor/__init__.py`,
`server.json` twice, `CITATION.cff`, `uv.lock`); `CHANGELOG.md` section "0.11.0 — 2026-11-22".

What it carries since 0.10.0 (PyPI, 2026-11-17): the address detector fix (`newAddresses` no longer lists a field of
an object; `python -m histor.recount_addresses`), the money-tool changes feed, the subregistry, signed publisher
statements and `GET /api/v1/fingerprints`. The last four are other work of 2026-11-18…22, already in main.

| Check | Result |
|---|---|
| Tests | 1,690 of 1,691 (`tests.log`): `test_upgrade_end_to_end.py::test_toolcost_client_and_histor_server_interoperate_modern_without_initialize` failed once at load average 25; that file alone, three runs: 2 of 2 each. The full run of the commit before the version change: 1,691 of 1,691 |
| Freshness gate | "tree ahead of PyPI (latest 0.10.0) — unpublished, fine" (`dry-run.log`) |
| Dry-run build | `./scripts/publish_pypi.sh histor --dry-run` in a clean worktree of `b243d0fe1` (Python 3.12 build venv): wheel and sdist built, `twine check` PASSED for both |
| Wheel | `aimarket_histor-0.11.0-py3-none-any.whl`, 1,100,430 bytes, sha256 `5aa91478795e9df3c8d6d39eb230331b08852f8f4b373a6abd4a3bc00ff3f5c5`; 79 files, 72 `.py` (= main), `histor/tlds.txt` and `histor/curated.json` inside; `diffing.py`, `tlds.txt`, `recount_addresses.py` byte-equal to the commit |
| Sdist | `aimarket_histor-0.11.0.tar.gz`, 6,427,940 bytes, sha256 `ce324882ede7e5297885c72c0c643daabbd6dc12913e43981aa53e18963ea597`; larger than 0.10.0's (3.57 MB) because `scanner/vendor` now holds WARDEN 0.37.1 (3.9 MB) |

The upload rebuilds, so compare the published files with the tree, not with these hashes.

Production HISTOR does not wait for PyPI: it runs the detector fix as an overlay image since 18:08Z
(`docs/evidence/histor-address-detector-2026-11-22`).
