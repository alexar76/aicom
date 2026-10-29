# Real HISTOR language verification and English default

Date: 27 October 2026. Work is local to the alexar76 ecosystem in `aicom`.

English is now the default across the report CLI, Python API, internal analysis helpers,
fallback title and renderer fallback for a report without `language`. The CLI help and
canonical synthetic example watchlist are English. Explicit Russian examples use
`watchlist.ru.json`; the previous English alias remains usable. Supplied labels, source
excerpts and embedded prose in historical report files remain their original data.

- [Five real-data reports and checklist comparison](../../../output/histor-upgrade-brief-real-i18n-2026-10-27/README.md).
- [English default report](../../../output/histor-upgrade-brief-real-i18n-2026-10-27/report.md).
- [Real-data verification](verification.json), [expected findings](expected.json),
  [translated labels](labels.json), [reproduction script](verify_real.py).
- [Acceptance checks and source hashes](acceptance.json), [pytest log](pytest.log),
  [JUnit](pytest.xml), [synthetic example](synthetic-example.log), [real example](real-example.log).
- [Original frozen source integrity](../histor-real-upgrade-2026-10-27/input-integrity.json)
  and [projection provenance](../histor-real-upgrade-2026-10-27/projection-provenance.json).

The saved public HISTOR data provides two core-definition comparison pairs (Hub and WARDEN)
and two incomplete histories (Oracle Gateway and Packager). All four overall results remain
`unknown`. Each locale retains six workflows and the same 21 checklist meanings and tool
associations. Language selection does not introduce new observations, erase uncertainty or
establish that an update is ready to deploy.

The runner performs 12 offline CLI runs: each of five explicit languages twice, plus two runs
without `--lang`. It checks unchanged inputs, byte-for-byte repeatability, default output equal
to explicit English, full normalized analysis equal to the original report, exact checklist
message sequences, 21 original raw hashes, five content addresses and six snapshot projections.
Every one of the 21 Markdown checklist lines is also decoded and compared with its JSON text,
tool association and order, in each language.
No source signature is claimed as verified. An independent read-only review also checks
translation meaning and the retained evidence limits.

All 103 scoped report, capture, rendering and language tests passed, including 42 language
regressions. The synthetic example also passed 12 offline runs, including the omitted-language
English check. CLI help is English and records `default: en`; Russian or Chinese environment
locale settings do not change the default. Ruff and diff checks passed.

This task uses frozen responses collected earlier on 27 October 2026; it does not fetch fresh
data or invoke MCP tools. No package installation, payment, deployment or GitHub publication
was performed. Original evidence is preserved; only derived localized bundles are generated.

Reproduce from the workspace root:

```bash
histor/.venv/bin/python docs/evidence/histor-real-upgrade-i18n-2026-10-27/verify_real.py
```
