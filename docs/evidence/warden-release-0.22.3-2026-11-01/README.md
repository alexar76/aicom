# WARDEN 0.22.3 release preparation

Prepared locally on 2026-11-01 with Node.js 22.22.1 on macOS. This directory records checks of the
exact npm archive described in `artifact.json`. Since 11:08Z the MOMUS release gate passes for it:
the evaluator passed this build and production HISTOR runs it (section "MOMUS evaluation and
HISTOR"). **Published by the owner at 2026-11-01 11:14:44Z** (section "Published").

## What 0.22.3 ships that npm 0.22.2 does not

- **MTL/1.1 tool-set digest** (`src/mtl.ts`, `src/jcs.ts`). npm 0.22.2 refuses any tool schema
  with a fraction or an exponent (`MTL-NUM-001`), an empty set (`MTL-SUBJ-002`) and a repeated name
  (`MTL-SUBJ-003`), so `--histor` sent no digest for them while HISTOR (MTL/1.1 since 2026-10-31)
  digests them. A set whose integers all lie inside 2^53 keeps its 0.22.2 digest.
- **CI marker** in the `--histor` User-Agent: `warden-scan/0.22.3 (ci; github-actions)`,
  `(ci; gitlab)` or `(ci)`; never the repository, runner or account.
- **`warden-mcp --help`** lists the commands (0.22.2 answered with the wrap parser's error, exit 2).
- Packaged docs link to public URLs instead of monorepo paths.

Version pins move to 0.22.3 in the READMEs (five languages), scan and flow-guard guides, the
Claude plugin, `action.yml`'s default, `.pre-commit-hooks.yaml`, `server.json`, `CITATION.cff`, the
landing page and the GitHub-org example. `docs/teams.md` keeps its record of the 2026-11-01 checks
run with 0.22.2.

## Checks (all passed except the release gate)

| Check | Result | File |
|---|---|---|
| TypeScript typecheck | clean | `typecheck.log` |
| Test suite | 1,390 tests in 57 files, 0 failures | `tests.log` |
| Red team | 28 scenarios, 0 attacks delivered | `redteam.log` |
| Ruleset | v16 `sha256-86y6iNc4R+LM5WmjSVxaCNgSMUEggeNOMQPUzq4L9n8=`, unchanged | `ruleset.log` |
| `npm pack` | 345 files, 939,899 bytes, sha256 `183e60ef…` | `pack.json`, `pack.log`, `artifact.json` |
| Archive vs npm 0.22.2 | same 345 paths; compiled JS differs only in `histor`, `jcs`, `mcp-server`, `mtl`, `scan`; `package.json` differs only in `version`; no runtime dependencies | `package-diff.txt` |
| Clean consumer | offline install without scripts; library import; `scan` exit 0; MCP `initialize` reports 0.22.3; `--help` exit 0; state dir untouched | `clean-consumer.json` |
| MTL/1.1 against live HISTOR | for a set with `0.5`, `1e-7`, an integer beyond 2^53 and a repeated name, 0.22.3 gives `sha256-0myjes…i30=`, the digest HISTOR returned for the same tools at 10:35Z (`POST /api/v1/check`, no `digestError`); published 0.22.2 refuses that set (`MTL-SUBJ-003`) and a single `0.5` (`MTL-NUM-001`) | `clean-consumer.json` |
| README demo output | `examples/scan-demo` scanned with this build prints exactly the block in the README | — |
| MOMUS release gate | blocked at preparation (`This exact WARDEN build has not passed`); **passes** after the evaluation and switch below | `quality.log`, `quality/quality-after.log` |

The npm 0.22.2 archive kept in `../histor-warden-release-2026-10-27/warden/` is the control; its
SHA-1 equals the registry's `dist.shasum` (`f31ef1c0…`). The native macOS sources are byte-identical
to 0.22.2's, so the Swift suite was not rerun. Reproduce the consumer check with
`node docs/evidence/warden-release-0.22.3-2026-11-01/clean-consumer-check.mjs`.

## MOMUS evaluation and HISTOR (2026-11-01, owner: «Yes, run it»)

`npm run check:quality` (also run by `prepublishOnly` and `scripts/publish_warden.sh`) reads
`https://histor.modelmarket.dev/security-quality/latest.json`. At preparation that receipt was run
`20261101T050101` for build `3b6b074c…` (0.22.2); `skopos-warden-quality rebind` refuses a changed
WARDEN build, so the full candidate path was taken. Files in `quality/`.

1. **Image.** `stage-candidate.py` (root, on admin-vps, from
   `/var/lib/momus-quality/release-candidates/20261101-warden-0.22.3`) checked the archive
   (sha256 `183e60ef…`) and `git archive 213d1f942 warden/src` (sha256 `bbe6f02c…`), then built
   `Dockerfile.candidate` with no network: the running HISTOR image wpp-20261101
   (`07b33b835aef`) with its vendored WARDEN replaced by the archive, the 0.22.3 source in
   `/opt/warden-source/src` and label `skopos.source.commit` = 213d1f942, as the trusted recipe
   does. Result `aicom-security:histor-histor-1-wd-20261101` = `sha256:8cc613352e22…`. Checked in
   the image before anything ran it: the installed WARDEN digests to `d7cc677e…`; 63 source files
   equal git's; `scan.mjs describe` differs from 0.22.2's only in the package name (ruleset v16);
   a poisoned probe scans byte-identically (3 matches); HISTOR imports at migration 18
   (`artifact-manifest.json`, `image-build.log`).
2. **Candidate run.** `systemd-run --unit=warden-release-quality-0223-20261101 …
   skopos-warden-quality candidate sha256:8cc61335…`, 10:59:02–11:07:15Z, exit 0. Signed receipt
   run `20261101T105907` (`candidate-signed.json`), checked with the gate's own `checkEvidence`:

   | Suite | Coverage | Missed | False positives | Incomplete |
   |---|---:|---:|---:|---:|
   | Development | 8,244 attacks + 362 benign | 0 | 0 | 0 |
   | Sealed holdout | 24 attacks + 24 benign | 0 | 0 | 0 |
   | Generated candidates | 17 unlabeled proposals | 0 | 0 | 0 |
   | Sandbox behaviour | 72 / 72 executed | 0 | 0 | 0 |

   Discovery round 39 complete; generation ok (12 admitted, 2 rejected; the run made model calls).
   Unlabeled proposals do not measure detection accuracy.
3. **Production.** `histor_warden_0223_overlay.sh`, 11:07:51–11:08:08Z (`rollout.log`):
   `authorize` accepted the candidate receipt for this image; compose switched wpp → wd; healthy;
   the sidecar reports 0.22.3; `skopos-warden-quality live` published the live receipt and moved
   the binding; `histor:warden-remediation-base` → `8cc613352e22`; the interrupted crawl restarted.
   Rollback is at the top of the script.
4. **After.** Public `latest.json` (`latest-signed.json`): run `20261101T105907`, phase live, build
   `d7cc677e…`, image `8cc613352e22`, source commit 213d1f942. `npm run check:quality` from
   `warden/`: `MOMUS release gate passed` (`quality-after.log`). On the host `live-image.json`,
   `source.json` and `/root/aicom/warden/src` name 0.22.3 (hashes equal git's). A public
   `POST /api/v1/check` with a poisoned, fractional tool set returns a digest and `block: 1` under
   the new pattern-set digest `sha256-/DVKIi…`; HISTOR re-labels targets with it as the crawl
   reaches them (same rules, new package name), as at earlier WARDEN upgrades.

HISTOR's own build now vendors this archive too (`histor/scanner/vendor/aimarket-warden-0.22.3.tgz`,
replacing the 0.20.0 local builds), so an image built from main carries the evaluated WARDEN.

## Published

The owner ran `scripts/publish_warden.sh` with their own npm login; npm records
`0.22.3` at 2026-11-01T11:14:44.619Z and `latest` → 0.22.3. The registry's `dist.shasum`
(`ecfedee2e663cbfb7180ba94f558836ec7d4a6e4`), `dist.integrity`, file count (345) and unpacked size
(3,184,520) equal `artifact.json`: the published bytes are this archive.

From the registry, with an empty npm cache, on a copy of `examples/scan-demo` outside the repository,
`npx -y @aimarket/warden@0.22.3 scan --project` prints the README's demo block byte for byte (exit 1:
one server blocked), and `npx -y @aimarket/warden@0.22.3 --help` prints the command list.

Inside a checkout the README's own recipe (`cd examples/scan-demo && npx -y @aimarket/warden@0.22.3
scan --project`) failed with `sh: warden-mcp: command not found`: npm walks up to `warden/package.json`,
whose name and version equal the requested package, takes the checkout for it and installs nothing.
`examples/scan-demo/package.json` (`private`, no dependencies) makes the demo its own project; with it
the recipe prints the same block inside the checkout. The same happened with 0.22.2 at its release
commit, so a clone of the mirror always hit it.

Left: sync the GitHub mirror of warden (owner); its READMEs, `.pre-commit-hooks.yaml` and
`action.yml` default already name 0.22.3, which now installs.
