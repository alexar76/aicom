# Completed USD 1 fresh comparison

[English](https://github.com/alexar76/warden/blob/main/docs/flow-guard-model-comparison-2026-10-25.md) | [Русский](https://github.com/alexar76/warden/blob/main/docs/flow-guard-model-comparison-2026-10-25.ru.md) | [Español](https://github.com/alexar76/warden/blob/main/docs/flow-guard-model-comparison-2026-10-25.es.md) | [Français](https://github.com/alexar76/warden/blob/main/docs/flow-guard-model-comparison-2026-10-25.fr.md) | [中文](https://github.com/alexar76/warden/blob/main/docs/flow-guard-model-comparison-2026-10-25.zh.md)

[Russian report](../../growth/launchgate-live-comparison-2026-10-25.ru.md),
[English report](../../growth/launchgate-live-comparison-2026-10-25.en.md),
[manual reply draft](../../growth/launchgate-live-reply-2026-10-25.en.md).

`run-01` preserves a failed pre-API prerequisite/test-expectation attempt; its
owned root was removed and no model calls occurred. `runtime-build.json` records
the public Node base plus Bash/Python runtime preparation.

`run-02` is the completed, frozen comparison. The protocol and main fixture
bytes were fixed before smoke. No model outcome was replaced or used to tune
the main run. Five smoke, 30 controls, 720 main answers and 12 continuations
produce 767 API attempts. Estimated tariff cost $0.057983838; conservative peak
settlement $0.115967676, peak including reservations $0.125793172, ceiling $1.

Both candidate injected target rates are 27/48, published 44/48 and 46/48,
unguarded 48/48. Stop changed zero selected IDs in twelve continuations. All
720 final IDs admissible; all 30 user controls followed. Six known cases are
not an independent holdout or broad safety evidence.

The independent Linux artifact audit passed 21,015 checks. All 2,606 output
hashes were verified. Full answers, ledger, requests/responses, schedule, intents,
primary analysis and compiled artifact snapshots are in `run-02/outputs.tar.gz`.
Expanded `out/` and `generated/` directories are convenience extraction copies;
the archive and output manifest preserve their bytes.

All runtime execution was on Linux factory-vps, Docker runc. Guards/tests/audit
had no network; dev-dependency/OS preparation and the host model relay are the
explicit network exceptions. The key remained host-local. Both owned model
and audit roots were removed after collection. No production, GitHub, npm or
public-comment mutation occurred.

The post-run `audit_outputs.py` is an independent accounting implementation, not
an independent human/semantic adjudicator. `warning-reference-observations.json`
uses a limited English word screen and retains text; it does not infer awareness.
