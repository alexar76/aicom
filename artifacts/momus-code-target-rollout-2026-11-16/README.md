# MOMUS reads code: the `code` target and the fix loop for source findings (admin-vps, 2026-11-16)

Owner, 2026-11-16: «в итоге все это ловить и исправлять должен момус и как минимум не хуже вулнетикса»; «Yes, start
MOMUS»; «проверь если ок давай запустим на проде штатный флоу исправлений проконтролируем процесс а потом заберем
ветку момуса с исправлениями и потом опишем это кейс в доках на 5 языках».

## What changed (main, Gitea)

| Commit | What |
|---|---|
| 9d176d3a0 | push gate: Vulnetix-class rules + Semgrep on every push (scripts/code_scan_gate.sh) |
| 37b010c34 | MOMUS `code` target (momus/targets/code.py, rules in momus.codescan); per-finding gate on the newest `momus/fix-<id>-<n>`; `code:<area>` blame, security core → human; SKOPOS conductor code path (push → MOMUS gates the branch → DONE `branch_verified`, no build/deploy/auto-merge, no re-open per scan) |
| 05857acb7, 57e61c8cd | remediation fixer: one file per code finding, from the MOMUS-signed Blame title, inside the ticket's area, for areas the host enables; source read from AIFACTORY_REMEDIATION_CODE_ROOT (the PRAXIS drill keeps its tree) |
| (safe.directory) | code target reads a repository owned by Gitea's user through a private global gitconfig |
| (dedup) | a code finding's corpus identity includes rule, file and function |

## Production (admin-vps)

- Images (FROM the live `*-hc-live-20261031`, only the named files; each live file equalled main before the change,
  except the conductor's bundled MOMUS `engine/remediation.py`, which got only the diff):
  `aicom-security:momus-backend-code-20261116` (+ git), `skopos-remediation-code-20261116`,
  `remediation-fixer-code-20261116`. Dockerfiles in this folder.
- MOMUS reads Gitea's own bare repository read-only (`/code/aicom.git`), target
  `aicom-source|file:///code/aicom.git|code`. No credential, no network.
- Fixer: `/srv/momus-code/aicom` = shallow checkout of main from the same local repository, refreshed every 5 min
  (`momus-code-checkout.timer`, script in this folder, 5.0 GB), mounted at `/code-src`; code areas
  `ai-service-mesh,plugins,metis,web`.
- Autopilot (`/etc/skopos-autopilot.env`): scan rota + policy `aicom-source` (critical/high/medium, 2 sightings);
  caps raised for the proving run (per component 3 → 7, per day 8 → 14) — `switch.py caps-restore` after.
- Kit on the host: `/root/momus-code-rollout-20261116/` (switch.py with `rollback`, backups `*.pre`, watch.log).

## First live scan, 05:02–05:07Z

- 7 findings at main 13c0deae7: FWD trust ×2 (ai-service-mesh client_ip, aimarket-zk plugin), check-then-connect ×4
  (metis tools/aimarket, web providers probe, web search_v2, invoke_v2), open without key ×1 (skopos a2a_ingress →
  human governance).
- Two defects found and fixed during rollout: (1) git refused Gitea's repository (`dubious ownership`; safe.directory
  is honoured only from global config); (2) the corpus dedup key collapsed 3 + 4 findings into 2 rows. The target was
  renamed `aicom-code` → `aicom-source` so the two collapsed rows (mom-4c45820adbd14a61, mom-c39bc80e309743ce, target
  `aicom-code`) can never be dispatched — no corpus row was edited or deleted.

## The fix loop (05:02–06:17Z)

Times are UTC from `watch.log` on the host and the conductor's `jobs.jsonl`.

| Time | What happened |
|---|---|
| after the 05:02–05:07 scan | Autopilot dispatched the six non-core findings as signed tickets; skopos a2a_ingress went to human governance (security core). |
| 05:23:56 | All six **escalated after 3 attempts**. The fixer refused every ticket with "Blame carries a post-quantum signature this service cannot verify". This failure had existed since ORACLE_PQC went on in September: every new ticket since then was refused, and the loop had only ever run on an August praxis ticket. Fix 9b2fc73d6: the fixer verifies ML-DSA-65 as well. |
| 06:03 | Five branches pushed, all **verified by the gate**. Review: one (`invoke_v2`, 2d7e3efa8) only added `# vx-ok: ...`, and the gate honoured the mark. |
| 06:10 | The gate fix 4e4070277 went live: marks are honoured only when they are already on main; the fixer refuses patches that add silencing marks; and the conductor re-asks the gate about waiting branches. |
| 06:11 | `invoke_v2` reopened; a new branch, 16a99a3f8, was pushed and verified. |
| 06:17 | `web providers probe` escalated again. The fixer refused its own output three times: undefined `logger` / `HTTPException`, a cut-off rewrite, and an added vx-ok. |

Settled state (06:30Z): 5 `done` + `branch_verified`, 1 escalated, 1 human-governance.
Caps restored by `switch.py caps-restore` (3 per component, 8 per day).

### Review of the five verified branches

The gate re-runs the finding's rule on the branch. It proves the rule no longer matches, not that
the code is right. Two branches were right and three were wrong:

| Branch | Verdict | Why |
|---|---|---|
| `momus/fix-mom-f83d29f3cf254806-1` (aimarket-zk) | **taken**, main f382c4348 | `AIMARKET_ZK_TRUSTED_PROXIES` CIDR list replaces the yes/no flag. Its vx-ok line was dropped, plus a log warning for the old flag and 5 tests. |
| `momus/fix-mom-fa8250468f2c4d5a-1` (ai-service-mesh) | **taken with changes**, main f08b6ded1 | The branch hard-coded all of RFC 1918 as trusted and added a vx-ok. In main it is now `MESH_TRUSTED_PROXIES`, default loopback; the prod overlay sets 172.16.0.0/12, because the live peer is the compose gateway 172.20.0.1. |
| `momus/fix-mom-5f53ba285a7f4cb3-2` (metis tools/aimarket) | rejected | Resolves the name a second time after the check and connects to that unchecked answer; requests `https://<ip>` with no SNI/Host, so TLS fails. |
| `momus/fix-mom-5a38279368ae41a1-2` (web search_v2) | rejected | Same pattern: second `getaddrinfo`, HTTPS to a bare IP. |
| `momus/fix-mom-5ae46e61c5e84605-2` (web invoke_v2) | rejected | Same pattern again (the -1 branch was the vx-ok-only one). |

The rejected branches stay in Gitea as they are; nothing was deleted. Their findings are still open
on main, so MOMUS will keep seeing them.

### What this run says about MOMUS

- **Finding:** 7 real instances of Vulnetix bug classes still on main after the Vulnetix fixes,
  found by MOMUS on its own schedule, signed, and deduplicated per file and function.
- **Fixing:** 2 of 7 were fixed correctly by the loop: one as is, one after a reviewer's edit. The
  fix loop had been dead since September (PQ refusal) and no alert noticed.
- **Gating:** the gate was gamed twice on the first day (an acceptance comment, and a fix that
  only satisfies the rule). The first is closed. The second is open: the check-then-connect rule
  should require that the address that was checked is the one the code connects to. Until then,
  a person merges every code branch (by design, no auto-merge for `code:` components).
- **Open:** a human rejection is not yet recorded anywhere the conductor reads, so a rejected
  branch stays `branch_verified` until main changes.

## Same day, 06:40–07:10Z: the open items closed (main 6dbfb7fb3)

Owner: «Ещё не сделано — делай», «как сделать лучше? чинит же фабрика?», «а алерт покажет?».

| Commit | What | Live |
|---|---|---|
| 05977ff78 | VX-918-CHECK-THEN-CONNECT also fires on a second DNS lookup after the check whose answer no check examines (in place or via a helper such as `_resolve_pinned_host`). Same rule id, so the gate on the existing findings now fails all three rejected branches (checked with main-only marks). Main still shows exactly the 5 known findings. | momus-backend-code-20261116b |
| 4cf789ef4 | Conductor flags each job `fixer_refused` / `patch_received`; `/api/remediation/stats` carries the counts; alerter checks `remediation_stats_published`, `remediation_fixer_answers` (refusals and no patch in 24 h), `remediation_breaker_closed`. Reviewer rejection: `POST /remediation/jobs/{id}/review` (operator token, exact branch, reason); the job becomes FAILED, the next ticket reopens it, the fixer's first attempt is told the reason. | skopos-remediation-code-20261116b; alerter on skopos-vps (backup `ecosystem_alert.py.pre-remediation-20261116`) |
| ea6b1b1ad, 6dbfb7fb3 | Fixer: per-rule guide in the prompt (what is wrong, the fix, what never to do) with this repo's own fixed functions read from `/code-src` (aimarket-mcp `pin_target`, ATLAS `_delivery_target`, mesh `client_ip`, metis `local_caller`); the finding's rule (MOMUS's module from `/code-src`) runs on the rewrite before a push. | remediation-fixer-code-20261116b |
| c37e44b1d | mesh e2e tests skip unless the port answers as an ai-service-mesh (on the Mac :8090 is another project's container) | — |

- Overlay kit: `b/` (Dockerfiles FROM the code-20261116 images, `switch_b.py apply|rollback`, backups `*.pre-b`);
  each build context holds the named files from `git show 6dbfb7fb3:<path>` (not kept here; hashes matched on the host).
  Each replaced live file equalled main 37ebe613f before the swap (sha256 compared).
- nginx: `location = /remediation/stats` on momus.modelmarket.dev → `127.0.0.1:9402/api/remediation/stats`
  (GET only; backup `b/momus.modelmarket.dev.pre-remediation-stats`). The jobs, review and breaker routes stay on loopback.
- Rejections recorded 07:0xZ for mom-5f53ba285a7f4cb3, mom-5a38279368ae41a1, mom-5ae46e61c5e84605 (state `failed`,
  review attached; `b/reject.py`). They reopen on the next ticket within the autopilot's cooldown (6 h) and caps.
- The fixer counters start at 0: jobs before 07:00Z carry no such flags.

Tests: scanner 40, momus 548, skopos 1002 (3 dashboard failures predate), alerter 205, fixer 132, mesh 47 + 3 skipped.

## Third overlay, 2026-11-17: rules from outside advisories (owner «Да, выкатывай»)

Rules of main 443f0f422 (`VX-295-TLS-OFF`, `VX-918-FETCH-UNCHECKED`, `VX-918-REDIRECT-AFTER-CHECK`,
`VX-306-ROUTE-NO-AUTH`; measurement in `artifacts/momus-outside-cves-2026-11-16/`).

- Only momus-backend carries the module. The fixer reads it from `/code-src` (shallow main, already at 443f0f42);
  skopos-remediation has no copy.
- Live `vulnetix_classes.py` and `targets/code.py` equalled main 443f0f422^ (sha256 591bb0e4…, eb7ee80f…).
- Image `aicom-security:momus-backend-code-20261117` = sha256:782b929a… FROM code-20261116b plus the two files
  (a6789e6f…, 9ec3efb9…), kit `c/` (Dockerfile, `switch_c.py apply|rollback`, compose backup `*.pre-c`) on admin-vps
  in `/root/momus-code-rollout-20261116/c/`.
- Switched 2026-11-17 04:11:15Z (server). After: running, 0 restarts, no error lines; momus.modelmarket.dev
  `/remediation/stats` 200. A read-only scan by the live target of main 443f0f422: 7 findings — the 5 known
  (CHECK-THEN-CONNECT 4, OPEN-WITHOUT-KEY 1) and 2 new `VX-306-ROUTE-NO-AUTH` (relay-scout-fix api, scripts/
  local_image_server.py), the same as the local run. They enter the loop at the next code cycle under the usual caps.
- Rollback: `python3 /root/momus-code-rollout-20261116/c/switch_c.py rollback`.
