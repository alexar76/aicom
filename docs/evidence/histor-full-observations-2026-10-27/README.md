# Complete observations of four MCP dependencies

Date: 27 October 2026. All artifacts are local to the alexar76 ecosystem in `aicom`.

- [Reports and conclusions](../../../output/histor-full-observations-2026-10-27/README.md).
- [Current complete pairs](../../../output/histor-full-observations-2026-10-27/current/report.md):
  `unchanged: 4`, `unknown: 0`.
- [Controlled package release comparisons](../../../output/histor-full-observations-2026-10-27/package-replays/report.md):
  `changed: 1`, `unchanged: 1`, `unknown: 1`.
- [Report verification](report-verification.json) and [offline rebuild script](build_reports.py).
- [WARDEN capture provenance](warden/README.md) and [Python package capture provenance](python-packages/README.md).
- Hub: [baseline](hub/baseline.json), [recheck](hub/recheck.json),
  [baseline wire](hub/baseline-wire.json), [recheck wire](hub/recheck-wire.json),
  [capture implementation](hub/capture_hub.py), [provenance](hub/provenance.json).

The four current pairs contain full raw tool definitions, negotiated protocol and known equal
launch conditions. All successful captures mark `extrasCoverage: observed`. WARDEN supplies
title and annotation fields on all nine tools; Hub and both Python packages advertise no extra
members in their complete raw responses. Observed absence is retained without invented fields.

Thirteen selected capture files feed the new reports: eight current baseline/recheck captures,
one old WARDEN source replay, and four captures for the Python release comparisons. Twelve are
successful; old Oracle `0.3.1` fails before the protocol handshake and remains a failed observation.

WARDEN's old exact Git source and current local source are freshly compiled with recorded
runtime/compiler provenance. Both core digests match their original HISTOR before/after
records. These new captures do not restore the missing original historical extras/context.
Packager and Oracle use exact official wheel bytes whose hashes and package metadata were
checked. Package versions remain separate from server self-reported versions.

Hub metadata came from its public HTTP endpoint; the other captures ran locally without tool
calls. WARDEN's OS sandbox denies network. Python package launchers deny networking and child
processes through audit hooks. Old wheel downloads were read-only. No credentials, paid calls,
package installations, production state writes, deployment or GitHub publication were used.

Two preliminary Hub collector attempts are also preserved: `hub/current-baseline.json` is the
failed network-restricted attempt; `hub/current-baseline-public.json` is a successful initial
collector observation. The audited report pairs use `hub/baseline.json` and `hub/recheck.json`
with raw replies and an explicit no-auth/no-proxy launch profile.

The report rebuild uses only frozen captures. It verifies all five languages in each set,
same findings, exact workflow checklist meanings and associations, Markdown/JSON agreement,
byte-for-byte repeatability, unchanged capture files and default English output.
Original historical records remain untouched; their `unknown: 4` is not relabeled retroactively.
