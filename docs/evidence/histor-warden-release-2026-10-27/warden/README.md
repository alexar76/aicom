# WARDEN 0.22.2 release preparation

Prepared locally on 2026-10-27 using Node.js 22.22.1 on macOS. This directory records checks of the exact npm artifact described in `artifact.json`; it does not attest npm publication.

The patch release includes the existing `server_info` unknown-key rejection and its regression tests. Package metadata, current install pins, five-language README/flow-guard instructions, plugin/action/pre-commit versions, changelog and measured test counters now identify 0.22.2. Historical changelog entries and frozen experiment identities remain unchanged.

## Passing checks

- TypeScript typecheck and build: `typecheck.log`, `build.log`.
- Full existing suite: 1,382 tests across 57 files, zero failures; `tests.log`, `tests.json`. The first sandboxed attempt could not open loopback fixtures and was interrupted; its separate log is retained as `tests-sandbox-attempt.log`. The successful run permitted local fixture sockets.
- Red-team: 28 scenarios, zero delivered attacks; `redteam.log`.
- Ruleset: v16, `sha256-86y6iNc4R+LM5WmjSVxaCNgSMUEggeNOMQPUzq4L9n8=`; `ruleset.log`.
- `npm pack` executed normal `prepare`/build. Artifact: `aimarket-warden-0.22.2.tgz`, 936,594 bytes, 345 files; `pack.json`, `pack.log`, `artifact.json`.
- Archive/secret inspection passed. Package has no runtime, optional or peer dependencies, test fixtures, state, source tree or compiled native binaries; it contains the intended macOS source. See `contents-check.json`, `distribution-secrets.log`.
- Offline clean consumer installed the exact archive without lifecycle scripts, imported its library, ran the CLI and MCP transport, reported version 0.22.2/protocol 2025-03-26/nine tools, accepted six legacy metadata shapes and rejected `extra`, `__proto__` and `constructor` without writes. Reproduce with `node clean-consumer-check.mjs`; see `clean-consumer.json`. Installation script suppression applies only to this isolated consumer check; release build and publication gates remain required.

## Remaining release gates and limitations

`npm run check:quality` rejected the new exact compiled build because the currently published signed result covers another digest (`quality.log`). Required compiled digest: `3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de`. A fresh matching signed MOMUS result and successful gate verification are required before publication; no gate was bypassed.

Native production and test Swift binaries compiled. The first full native macOS run passed 53/55; Unicode commit and sheet hit-test assertions failed (`macos.log`). Both cases then passed in isolation, 2/2 (`macos-targeted.log`). A full repeat passed 52/55 with three hit-test trigger assertions failing (`macos-rerun.log`). The differing failures concern AppKit test-path reachability: the failed race probes refused with zero handler effects before triggering the intended callback. Native/atomic implementation, fixture and build/test configuration matched the tracked baseline at that stage; hashes are recorded in `native-baseline-identity.json`.

The test harness now captures sanitized last-commit status/reason and includes it in the affected assertion diagnostics. Expected outcomes, assertion strength and coverage are unchanged; no readiness delay, skip, effect retry, production/native source or package-payload change was made. The subsequent diagnostic full suite passed **55/55** in 10.21 seconds (`macos-diagnosis.log`, `native-final.json`). This supplies a complete passing native run; it does not establish that the earlier intermittent behavior was fixed. Focus/window changes causing refusal before hit-test remain an unconfirmed explanation because no failure occurred in the diagnostic run. The final archive SHA256 and compiled digest still match `artifact.json`.

The packed artifact and compiled build are frozen after measurement. Publication and Git operations are handled separately by the parent release task.
