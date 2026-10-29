# Public HISTOR 0.5.0 observation — 2026-10-27

During the final read-only registry audit, PyPI already contained `aimarket-histor`
0.5.0. This release team did not upload these files. Public registry metadata does
not identify the publisher, and the publisher is unknown to this audit.

The public release has the same application source and core metadata as the
frozen local candidate. Its wheel was independently built with another Hatchling
version. This is an observed relationship between the artifacts; it does not
establish who built or uploaded the public files.

| Artifact | Frozen local SHA256 | Observed public SHA256 |
| --- | --- | --- |
| Wheel | `bae7ec5b50582f3c2fda8eaa69814dec046cfac9ec011a424c2cbe6fe1648a99` | `72addda34b2670bdf55ff85c6d2714de504bdd7f091bbf9036028ff029c8220e` |
| Sdist | `1d912338b46b0cadc4176a09715d7b03f12c22c41cebf9956be621189ca4266c` | `1d912338b46b0cadc4176a09715d7b03f12c22c41cebf9956be621189ca4266c` |

PyPI records upload times `2026-10-27T14:39:21.778362Z` for the wheel and
`2026-10-27T14:39:24.799791Z` for the sdist. The public JSON response, its read time,
serial and fixed artifact URLs are preserved in `pypi-release.json` and
`public-receipt.json`. Both public downloads were checked against the registry
SHA256 digest. The downloaded sdist bytes are identical to the frozen archive;
the duplicate sdist was not saved again.

## Exact wheel differences

Both wheels contain the same 53 paths in the same order. All `histor/` application
files and the full `METADATA` contents are byte-identical. Exactly two archive
members differ:

1. `aimarket_histor-0.5.0.dist-info/WHEEL`: the local generator is `hatchling 1.32.4`;
   the public generator is `hatchling 1.27.0`. All other wheel fields agree.
2. `aimarket_histor-0.5.0.dist-info/RECORD`: only the hash for that `WHEEL` member
   changes. Every RECORD entry in both archives validates against its payload.

ZIP timestamps, compression, order, sizes and archive comments agree. The mismatch
does not come from `SOURCE_DATE_EPOCH`. See `wheel-comparison.json`,
`wheel-difference-explanation.json` and the reproducible comparison in
`comparison-validation.json`.

The frozen local artifacts and original manifest remain unchanged. The public
wheel is preserved separately in this directory. `audited-public-artifact.json`
records this one explicit observed hash and its relationship to the frozen
candidate. It neither replaces the frozen manifest nor accepts arbitrary hash
mismatches. No new upload, deletion, version bump or registry write was performed
during this audit.

## Public-wheel runtime verification

Installed the downloaded public wheel offline into a separate fresh virtualenv,
`/private/tmp/histor-release-public-consumer-050-20261027`, using the already cached
runtime dependencies. The same isolated installed-wheel verifier passed:

- all five languages, stable expected findings and localized checklists;
- byte-identical English output with omitted `--lang` and explicit `--lang en`;
- repeatable output and unchanged synthetic input files;
- modern MCP startup, `server/discover` and `tools/list`, protocol 2026-07-28,
  version 0.5.0 and the expected three tools.

See `consumer-smoke.log`, `consumer-install.log`, `consumer-pip-check.log` and
`distribution-secrets.log`. The public wheel passed the exact distribution
secret inspection. Only synthetic fixture reports were generated. No production
settings, keys, log contents or public MCP endpoint were used.

From this directory, compare the two preserved wheels without writing anything:

```sh
python3 -I compare_wheels.py \
  --local-wheel ../artifacts/aimarket_histor-0.5.0-py3-none-any.whl \
  --public-wheel aimarket_histor-0.5.0-py3-none-any.whl
```

Registry fields used here are documented by the [PyPI JSON API](https://docs.pypi.org/api/json/).
The public release is [aimarket-histor 0.5.0](https://pypi.org/project/aimarket-histor/0.5.0/).
