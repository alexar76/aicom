# Multica QA: secrets, stored output and egress

Local integration kit, 10 November 2026. Nothing here deploys, publishes a package, changes a live firewall or
marks TONM-14 passed. The five-language [Multica manual](../manual/README.md) remains the main setup guide.

The network allowlist belongs to the **Multica deployment**: a dedicated Docker network, egress proxy and
host firewall. WARDEN checks observed tool actions; it is not the container's network firewall. Both controls
are needed, and an allowed API remains a possible destination for leaked data.

## 1. Build the corrected WARDEN locally

From the `warden/` directory, using Node.js >=20 and the installed development dependencies:

```sh
npm run build
npm run typecheck
./node_modules/.bin/vitest run test/flow-guard-source-egress.test.ts test/flow-guard.test.ts test/flow-guard-credential-boundary.test.ts
npm run test:redteam
```

This workspace's package version remains `0.23.1-dev.20261108`. It is a local development build, not proof of a
fix in the reported deployed `@aimarket/warden@0.24.0`. No npm or GitHub publication is part of this kit.

The local source now checks known credential patterns, recorded secret fingerprints, supported encoded
payloads and recognized credential-file shell references **before** any outside text has been observed.
The first `curl -d @/tmp/fake/.env` is covered without waiting for that curl's output. A credential read alone
does not block a clean session's unrelated build or public status request. `off` and `audit` retain their
documented nonblocking behavior. This is bounded detection, not arbitrary information-flow analysis.

Literal reads of `playwright-report/` and `test-results/` supply external-source provenance out of the box. WARDEN
does not name Multica in its code: the Multica CLI (`issue get`, `issue list`, `issue search`, `issue comment list`)
becomes an outside source through the shipped preset `warden/examples/policies/multica.flow-policy.json`. Add custom
command prefixes and report roots in the operator-controlled policy the same way, for example:

```json
{
  "mode": "deny",
  "untrustedSources": {
    "commands": [["order-task", "get"]],
    "paths": ["qa/reports"]
  }
}
```

These rules only add distrust. `labels` for Bash and broad trusted-source overrides are not an escape route.
See the [guard contract](https://github.com/alexar76/warden/blob/main/docs/flow-guard.md) for literal-command coverage and remaining limits.

Install the built package and regenerated hook/plugin files into an operator-owned image or read-only mount;
record the package/file hashes and effective policy. Keep policy, hooks and plugin code unwritable by the agent.
For Claude Code, retain fail-closed PreToolUse handling and test it with the exact installed client version.
For OpenCode/Codex, use their matching adapters. Never mix an old npm package with new source-only claims.

Strict `deny` still refuses opaque shell programs after external text. Do not label `npm run`, `node -e` or the
whole Multica CLI read-only to make QA pass. Run a fixed test job in a separate minimal-credential QA worker
before the analysis agent reads its reports, or provide a separately reviewed fixed-operation broker. This kit
does not add such a broker or grant arbitrary post-taint commands. Let Multica publish the scrubbed final
answer rather than requiring the agent to bypass the guard to post a comment.

## 2. Scrub the result before storage

[0001-redact-task-results.patch](patches/0001-redact-task-results.patch) is a local patch against reviewed
upstream Multica `v0.8.0` source. It reuses upstream `redact.Text` and its recursive value walker:

- complete/fail payloads are scrubbed before the daemon's retry outbox and HTTP callback;
- replayed legacy outbox payloads are scrubbed before sending;
- message batches (content, output, nested input) and progress summaries are scrubbed before transmission;
- backend complete/fail request fields are scrubbed before serialization or logging;
- `TaskService` scrubs result JSON and errors before the database query, covering callers beyond the HTTP handler.

`output_summary` is scrubbed when present in result JSON; a downstream summary derived from scrubbed `output`
does not receive the original token. Any separate service that generates or stores a summary from raw text must
also cross a checked boundary. Invalid JSON results are refused, numbers retain precision and excessive nesting
is replaced with the upstream redactor's depth-limit placeholder.

Prerequisites: Python >=3.11, Git (local patch application only), an upstream source checkout matching the
[per-file checksums](patches/0001-redact-task-results.json), and its Go toolchain/dependencies. From this directory:

```sh
python3 apply-output-patch.py --source-root /path/to/multica --check
python3 apply-output-patch.py --source-root /path/to/multica
```

The helper refuses changed source, escaping paths and checksum mismatches before applying. It is idempotent
for the exact patched files. It does not download source or touch remotes. For a different Multica version,
port and review the patch; do not remove the checksum guard.

From the patched checkout's `server/` directory:

```sh
go test ./pkg/redact ./internal/daemon ./internal/handler ./internal/service -run 'TestAicom|TestTerminalReport|TestSanitizeTask' -count=1 -v
```

Rebuild and deploy **both daemon and backend**, record image hashes, then run the acceptance checks below.
The patch contains original regression tests for callbacks, on-disk outbox, legacy replay, backend sanitizers
and the database-query boundary. Upstream source/attribution: [Multica](https://github.com/multica-ai/multica/tree/v0.8.0),
with its [LICENSE](https://github.com/multica-ai/multica/blob/v0.8.0/LICENSE) and
[NOTICE](https://github.com/multica-ai/multica/blob/v0.8.0/NOTICE); retain them when rebuilding.

Use an isolated test database with the upstream schema for handler/database integration checks. The upstream
handler package can exit successfully without running tests when PostgreSQL is unavailable: check for the
expected `=== RUN`/`PASS` lines, not only exit code 0. The local evidence includes an actually executed handler
test and completed/failed storage readback against a fresh PostgreSQL cluster, then shut down. Its additional
verification probe source is retained beside the logs; it is not part of the deployment patch.

This fixes the reported raw known-token path. It does **not** promise detection of arbitrary secrets, encodings,
paraphrases or covert channels. It does not remove secrets already present in a database, runtime session files,
old queue files, backups or external logs. Inventory and remediate existing history separately; rotate real
credentials if exposure is established. A Stop hook is not the final storage owner.

## 3. Isolate the network

Use the [egress deployment kit](egress/README.md): a Compose overlay, exact-host proxy allowlist, merged-config
validator, a printable host-firewall plan and probes. The plan is for Linux Docker's iptables backend and the
template's exact addresses. It refuses to generate rules for the nftables backend. It never executes firewall
commands; review and apply the generated plan with the host's firewall manager.

Choose the actual model/API and dev/prod hostnames from deployment configuration. No TONmobile hostnames or
credentials are invented here. Keep runtime package installation and broad GitHub SSH access out of the QA
allowlist; install dependencies during image build. An HTTP proxy does not constrain arbitrary SSH by itself.
Avoid mounting production secrets into QA, and scope any required Multica/model credentials narrowly.

## Acceptance before unblocking

Keep separate evidence for the WARDEN decision, network enforcement and stored output:

1. Use an isolated fake canary, a known-listening receiver and a fresh session. `Read .env` then the **first**
   upload must receive WARDEN `deny` before execution. Receiver-side evidence must show no delivery; a curl
   timeout is not evidence of nondelivery. Repeat with a task/comment read and a workspace QA report first.
2. Exercise denied destinations through the proxy, direct IPv4/IPv6, a cleared proxy environment, external DNS,
   SSH and the host-gateway receiver (the reported `172.18.0.1:9999`, or the actual gateway on the target host).
   Check allowed API/backend health controls without sending credentials. Repeat after container recreation
   and host restart. A network denial alone does not establish a WARDEN denial.
3. Deliberately generate a fake token in a final answer and an error. Verify its absence from the task result,
   output summaries, comments, message transcript, retry outbox and test receiver. Do not print the raw canary
   into shared test logs; record decisions and boolean matches.
4. Complete a normal QA job and deliver its safe final report using the intended workflow. A profile that blocks
   every useful action does not pass. Keep a denial as a stop signal; do not ask the agent to find alternatives.

Local evidence is kept in [artifacts/multica-security-2026-11-10](../../artifacts/multica-security-2026-11-10/).
The Docker Engine is unavailable in this workspace, so live container/firewall/reboot and server database
acceptance remain deployment checks. Local loopback, query-boundary and configuration fixtures are not a live
TONM-14 run.
