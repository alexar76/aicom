# Multica integration: review for the bug classes Vulnetix found — 2026-11-05

Owner: «проверь наше решение по вульнетиксу». The same classes as the October audits (artifacts of 10-24, 10-25 and
10-28): endpoints open without a key, checking a name and then connecting to it, trusting forwarded client
addresses, secrets reaching errors or logs, and allowlists that can be stepped around. Scope: everything built for
Multica on 2026-11-04/05. Covered: the order seller (`multica/provider`), the supplier reviewer and the weekly
post (`multica/supplier-review`, `multica/weekly-post`), the read-only database function, the egress proxy, the
order agent's OpenCode permissions, and the shared daemon on attested. Also the hub manifest change.

## Findings

| # | Severity | What | State |
|---|---|---|---|
| 1 | medium | The order agent's allowlist reached every task in the workspace and allowed redirects | LIVE on attested since 07:35Z |
| 2 | medium | The agent user can rename the folder that holds the WARDEN plugin | LIVE on attested since 08:04Z |
| 3 | low | The attested hub's public manifest showed container addresses for 14 capabilities of 5 services | LIVE on modelmarket.dev 06:03Z and hub.attestedmemory.net 09:04Z |
| 4 | medium (latent) | A call another hub routes here on its own key would make all of that hub's buyers one Attested Memory owner | LIVE on hub.attestedmemory.net since 07:38Z; other hubs run no memory provider |

### 1. Order agent: every task reachable, redirects allowed

The order agent's OpenCode rules were `"*": "deny"` plus `multica issue get *`, `multica issue comment list *` and
`multica issue status * done --no-start`. OpenCode 1.18.32 checks every command in a line separately, including
commands inside `$(...)`, backticks and pipes (`tool/shell.ts` walks all `command` nodes), so chaining a second
command does not get past `deny`. Two gaps remained:

- **Any task, not its own.** `*` matches any id, and Multica's task token is bound to the workspace, not to the
  task's issue (`server/internal/middleware/auth.go`). The workspace holds 65 tasks (57 from autopilots, 8 by
  hand), with sequential ids `MY-1`, `MY-2`, ... Text a buyer controls reaches the agent: PR titles and repo
  descriptions of the GitHub account they order. If that text talks the agent into `multica issue get MY-<n>`, the
  task's content can go into the summary. The summary is the buyer's result, and Multica posts it itself, outside
  the tool calls WARDEN sees. The service's check passes text without links. The same gap let the agent close any
  task. Not exploited: DeepSeek refused obvious injections in our tests, and the order instructions say GitHub
  text is data. But nothing technical stopped it.
- **Redirects.** OpenCode checks a redirected command together with its redirect, and `multica issue get *` also
  matches `multica issue get X > FILE`. As the user `node`, the agent could overwrite the global OpenCode config
  (`~/.config/opencode/opencode.jsonc`), the daemon's Multica login (`~/.multica/config.json`) or `~/.bashrc`
  with the task's JSON. That breaks every agent on the daemon; it does not run code (JSON is not a shell script,
  and the config schema refuses it).

**Fix** (`multica/provider/order-task/`):

- `order-task`: a root-owned wrapper with two forms, `order-task get <issue>` and `order-task done <issue>`. It
  refuses any id that is not `MY-<digits>` or a lower-case UUID before calling Multica, reads the task, and
  prints it or closes it only if `assignee_type`/`assignee_id` name the order agent. Otherwise it exits 3 and
  prints nothing.
- `opencode-order-agent.json`: `bash` allows only `/home/node/tools/order/order-task get *` and `... done *`;
  after them, `*>*`, `*<*`, `*$*` and ``*`*`` are denied (OpenCode takes the last matching rule). `multica`
  itself, `comment list` and everything else are denied.
- Tests: `tests/test_order_task.py` (21: own task read and closed; another agent's or a member's task refused for
  both actions with no output and no status call; 13 odd argument forms refused before Multica is called; an
  unknown task) and `tests/order_permissions.test.mjs` (4: the rules evaluated with OpenCode's own `match()` from
  `packages/core/src/util/wildcard.ts` and its last-rule-wins order, over allowed forms, other commands, 9
  redirect/`$`/backtick forms and nested commands).
- Rollout (waits for the owner's yes): the wrapper goes to `/home/node/tools/order/` through the daemon's home
  volume, owned by root. `~/tools` is already owned by 501:root, so `node` cannot change the folder. Then
  `multica agent env set` writes the new `OPENCODE_CONFIG_CONTENT` for agent 0ac4ba96, and
  `multica agent update --instructions` writes the two new commands into steps 1 and 3 (the repo's
  `multica/provider/agent-instructions.ru.md` already has them; the live agent still has the old text). No daemon restart
  (the agent's environment is read per task). Check: one test order of $0.05 (summary by the agent, task closed
  by the agent), and `order-task get` on another agent's task refused inside the daemon.

### 2. The WARDEN plugin can be renamed away

On the daemon, `~/.config/opencode/plugin` and `~/.config/opencode/warden` belong to 501:root, so the agent user
`node` cannot change the files. But `~/.config/opencode` and `/home/node` belong to `node`, and Linux allows
renaming a folder inside a folder you own. Tested on a copy with the same ownership in the same volume: writing
into the root-owned file was refused, `mv guard guard-off` succeeded. Renaming the plugin folder, or `~/.config`,
means sessions started after that run without the flow guard. Today only WARDEN's own rule stops it: it refuses
calls that touch its settings, which the staged attack on 11-04 confirmed for listing and grepping the plugin
folder. Whether it also catches renaming a parent folder was not tested. The order agent cannot run `mv` at
all; the agents with a full shell (вжик, the reviewer, the shopper, the weekly post) can.

Fix (live since 08:04Z, see the rollout below): keep the guard where no folder on its path belongs to `node`.
Bind-mount the plugin and its library read-only to a root-owned path (for example `/opt/opencode-guard`), and
point OpenCode at it with `OPENCODE_CONFIG_DIR` in the daemon's environment. Check `opencode debug config` as
`node`, and check that renaming `~/.config` no longer drops the plugin. The daemon's own Multica login in
`~/.multica/config.json` is readable by every agent for the same reason: agents and the daemon run as the same
user. That is how Multica's daemon works; only running agents under a separate user would change it.

### 3. Container addresses in the attested hub's manifest

The hub-side fix (`published_invoke_url`, `aimarket_hub/hub_routes/catalog.py`, 13 tests) is live on modelmarket.dev
since 06:03Z today. hub.attestedmemory.net runs a different `catalog.py` and still lists memory-market,
truth-layer, provenance-ledger and the two Multica capabilities with their container addresses. It gets the fix
with its next rollout from main or a ported overlay.

### 4. Memory owners for calls routed by another hub

The hub names its authenticated buyer to the operator's own providers with `X-AIMarket-Buyer-Ref`
(`aimarket_hub/provider_buyer_ref.py`, since 11-04), and Attested Memory keys a buyer's private memory by it.
When another hub routes a call here, it authenticates with **its own** key when it holds one here
(`federated_delivery.py` sends `X-API-Key: <peer key>` with `X-AIMarket-Routing-Hub`), or pays from its own
channel. The receiving hub then saw a credit account and named it as the buyer. Every buyer of that hub would
become one memory owner and could read the others' "private" memories. That is the 11-04 bug again, one hub
further.

Not exploited. The attested hub holds one such account, «peer hub: independentai.network/hub (resells Attested
capabilities)», created 2026-10-04. Its call log has no successful `memory.*` call on it. All of them came from
вжик's own account or from trial and sandbox callers, which get no private memory.

**Fix** (aimarket-hub): `_Call.routed_by_hub` is set when the request carries `X-AIMarket-Routing-Hub` (only a
hub routing to a peer sends it, `federated_delivery.py`). `buyer_identity` then names nobody for credits, a
mandate or a channel. A verified x402 payment the buyer made still names the buyer. The header is
unauthenticated, but sending it can only make the sender anonymous. Tests in
`tests/test_provider_buyer_ref.py`:
- 3 new unit cases;
- an end-to-end case: two buyers routed through the same peer key get no reference, and the same account calling
  for itself still does.

Both new tests fail without the change. Run on the invoke, federation, peer, routing, memory and buyer test files:
445 passed, 3 skipped. Rollout to the hubs that run memory providers waits for the owner (the attested hub first).

## Rollout, 2026-11-05 (owner: «Yes, roll out»)

Times are attested's clock (UTC). The alerter had nothing open, and no Multica task was running.

**Order agent (finding 1), 07:34–07:36Z.**

- The wrapper went into the daemon's home volume as root:root 755. The folder is
  `/var/lib/docker/volumes/multica_daemon_home/_data/tools/order/`, seen as `/home/node/tools/order/` inside the
  daemon; sha256 `420e1bc4a9147dcf…` equals the repo file. Checks as `node`:
  - `order-task get MY-65` (the order agent's task) printed it;
  - `get MY-60` (the weekly-post agent's task) exited 3 with nothing printed;
  - `get "MY-1;id"` exited 2;
  - `touch` inside the folder and `mv` of the folder were refused.
- Backups in `/root/multica-order-task-20261105/` (mode 600): `instructions.before.txt` and `opencode.before.json`
  (the old `OPENCODE_CONFIG_CONTENT`, md5 0d16f370… = kit-v2/order-agent-opencode.json).
- `multica agent env set 0ac4ba96… --custom-env-stdin` with the new `OPENCODE_CONFIG_CONTENT`. The other five keys
  were passed as `****`, so they stayed as they were: empty, blanking the daemon's keys for this agent. Lengths
  before and after: all 0. `multica agent update 0ac4ba96… --instructions` with
  `multica/provider/agent-instructions.ru.md`. In the database, md5 of the config is aa9a782c… and of the
  instructions b4c74513…, both equal to the repo files. No daemon restart.
- Test order MY-66 (alexar76, 2 days, $0.05, balance 4.71 → 4.66): `summary_by: agent`, done 31 s after the order.
  The agent's only tool calls were `order-task get <uuid>` and `order-task done <uuid>`. The wrapper works under
  Multica's task token as well as the daemon login, and the task was closed by the agent.
- Rollback: `multica agent env set` with `opencode.before.json` (other keys `****`) and
  `multica agent update --instructions "$(cat instructions.before.txt)"`. The wrapper can stay.

**attested hub (finding 4), 07:38Z.**

- The live `provider_buyer_ref.py` equalled the repo's `bbe3dad45^`, so the overlay uses the fixed file. The live
  `invoke.py` differs from the repo: it is the 3,334-line file the hub runs. The two edits were applied to the live
  file at their only occurrences, and the diff is those 4 lines. The edit is inside `_read_call`, which has the
  request.
- Image `attested-memory-hub:rbh-20261105` (`/root/rbh-20261105/`: Dockerfile, both files, `smoke.py`) is built
  FROM the running `attested-memory-hub:cf-20261104`. The offline smoke passed (with temporary database paths):
  the field, 6 owner cases, and files equal to the build context.
- `/root/vx-20261029/rollout_container.py attested-memory-hub-hub-1 --image attested-memory-hub:rbh-20261105
  --health http://127.0.0.1:9084/ai-market/v2/health` gave `healthy: true`. The previous container is kept as
  `attested-memory-hub-hub-1-security-prev-1793864320927248726`. Health 200 locally and at
  https://hub.attestedmemory.net.
- Live check with free reads of MY-66's result through вжик's key:
  - a direct call returned 200, `done`, `summary_by: agent`;
  - the same key with `X-AIMarket-Routing-Hub: https://peer.example`: the provider got no buyer reference and
    answered 403, the hub answered 502, nothing was charged;
  - without a key: 502, as before.

  So direct buyers keep their reference, and routed calls name nobody.
- Rollback: the same script with `--image attested-memory-hub:cf-20261104`.
- Compose drift, fixed after the owner's «делай» (07:58Z). `/opt/aicom/attested/attested-memory-hub/docker-compose.yml`
  (backup `docker-compose.yml.bak-20261105-image`) still named the 31 October images for three services, while
  later images were running:
  - hub: compose `aicom-security:attested-memory-hub-hub-1-hc-live-20261031`, running `rbh-20261105`;
  - memory-market and provenance-ledger: compose hc-live, running `bref-20261104`, the 11-04 memory-owner fix.

  A plain `docker compose up` would have brought back the bug where all buyers share one memory owner. First,
  compose and the live containers were compared for each of the three. Environment (secret values compared, not
  printed), ports, networks, volumes, command and user were the same; only the image lines differed. Those three
  lines now name the running images, and `docker compose config` validates. Every service's compose image now
  equals its live image (postgres is the same digest written differently; truth-layer was already equal). A
  `compose up` would still recreate the containers, because rollout_container.py created them and their
  config-hash labels differ, but with the same images and settings. The services also keep `build:`, so
  `compose up --build` would build from the source tree at `/opt/aicom/attested/attested-memory-hub`, not from
  these images.

**WARDEN guard (finding 2), 07:56–08:05Z (owner: «делай»).**

- `/opt/multica/opencode-guard/` on the host holds `plugin/warden.js` and the 20 library files. Everything is
  root:root, folders 755, files 644. The files are copied from the daemon's home, identical by sha256.
- Pre-test in the running daemon (a copy in `/tmp`, removed afterwards). With `OPENCODE_CONFIG_DIR` set, OpenCode
  listed the plugin from that folder; with `HOME` pointing at an empty folder, it still did; without the variable it
  listed none.
- `/opt/multica/docker-compose.yml` (backup `docker-compose.yml.bak-20261105-guard`) mounts that folder at
  `/opt/opencode-guard`, and the daemon's environment has `OPENCODE_CONFIG_DIR: /opt/opencode-guard`. The restart
  waited for вжик's 08:00 run (MY-67, done 08:02).
- First restart, with the mount `:ro`: OpenCode stopped at start with `FileSystem.writeFile
  (/opt/opencode-guard/.gitignore)`. It writes a `.gitignore` into every config folder, aborts on a read-only file
  system, and skips a folder it may not write (the pre-test's case). No task ran in those minutes. Second restart
  without `:ro`: the folder is still root-owned and `node` cannot write it; nothing in the container runs as root.
  `opencode debug config` exited 0.
- The old copy (`~/.config/opencode/plugin` and `~/.config/opencode/warden`) moved out of the volume to
  `/root/multica-guard-20261105/old-plugin` and `old-warden`, so the guard loads once.
- Checks as `node`:
  - the only plugin listed is `file:///opt/opencode-guard/plugin/warden.js`, and with `HOME` elsewhere (as if
    `~/.config` were renamed) it still is;
  - `touch` in the plugin folder, appending to a library file and `rm` of the loader were refused, and so were `mv`
    of `/opt/opencode-guard` and `mv` of its `plugin` folder;
  - a real `opencode run` (08:04:50Z) answered, and the guard wrote that session's state file
    (`~/.local/state/warden/claude-code/flow/…`, 08:04:54Z).
- Rollback: restore the compose backup, move `old-plugin` and `old-warden` back to
  `.config/opencode/plugin` and `.config/opencode/warden` in the volume, recreate the daemon.
- The manual said "a root-owned, read-only mount". In all five languages it now says to mount the folder writable
  but owned by root, and why.

**attested hub manifest (finding 3), 09:04Z (owner: «7-1 делай»).**

- Before: the public manifest at https://hub.attestedmemory.net listed 265 tools. 14 of them showed a container
  address on plain http: memory-market (6), truth-layer (4), provenance-ledger (2), multica-provider (2).
- The live `catalog.py` (sha256 a4b259587d17…) differs from the repo. `published_invoke_url` from the repo's
  bbe3dad45, with its two imports, went into the live file, and the manifest line now calls it. The diff is that
  function plus one line. Image `attested-memory-hub:mgw-20261105`, FROM the running `rbh-20261105`; files in
  `attested-hub-mgw/` here. The offline smoke passed with the hub's own `AIMARKET_INVOKE_HOST_GATEWAY` (6 address
  cases, file = build context).
- `rollout_container.py ... --image attested-memory-hub:mgw-20261105` gave healthy. The previous container is kept as
  `attested-memory-hub-hub-1-security-prev-1793869453352088108`; public health 200.
- After: 265 tools, no container address left. The 14 show `https://hub.attestedmemory.net/ai-market/v2/invoke`, all
  still `live`. Routing still goes to the containers: a free read of MY-66's result through the hub answered 200,
  `done`, `summary_by: agent`.
- Compose (backup `docker-compose.yml.bak-20261105-mgw`) names `mgw-20261105` for the hub, so compose and the live
  container match again.
- Rollback: `rollout_container.py attested-memory-hub-hub-1 --image attested-memory-hub:rbh-20261105 --health
  http://127.0.0.1:9084/ai-market/v2/health`, and the compose backup.

## Checked and clean

- **Order seller.** Every call needs the hub's token (`X-AIMarket-Internal-Token`, at least 32 characters,
  compared in constant time); the service refuses to start without it. Results are bound to the buyer the hub
  names, so another buyer gets 404. No published port: only the hub's network and Multica's reach it.
- **Outbound calls.** GitHub only at the fixed base `https://api.github.com`, with the login checked against
  GitHub's own syntax and no redirects followed. The webhook and the hub registration use operator-set URLs. Nothing
  connects to an address taken from input.
- **Secrets in errors.** The webhook URL carries its token. A failed webhook call is turned into a fixed 502
  text, and the job is deleted without logging the exception. Every other failure logs only the exception's type.
  The GitHub token travels only in a request header.
- **Database function.** `provider_ro.order_answers` is `SECURITY DEFINER` with `SET search_path = pg_catalog,
  pg_temp`. It checks the job id against `^job_[0-9a-f]{32}$` and reads only listed columns, through a NOLOGIN
  owner. The login role can only execute it. The job-id match against the task description cannot be forged from
  GitHub text: inside the JSON payload a quote in a title is escaped, so `"job_id":"` cannot appear there.
- **Agent answers.** One JSON object with exactly `job_id` and `summary`, matching job id, at most 2000
  characters, links only to `https://github.com/`; control and direction characters are removed.
- **Scripted agents.** `run.sh` fetches fixed hub paths only; `review.mjs` and `collect.mjs` open no sockets and
  read only the downloaded files.
- **Egress proxy.** tinyproxy with `FilterDefaultDeny Yes`, host patterns anchored at both ends (`^github\.com$`),
  CONNECT only to 443, clients only from the agents' subnet.
- **Ports.** On attested the only published Multica port is the gateway on `127.0.0.1:13300` (SSH tunnel). The
  provider, backend, database, proxy and daemon have none.
- **Forwarded addresses.** Nothing in the Multica code reads `X-Forwarded-For` or `X-Real-IP`.
- **Hub manifest change.** Display only: the stored address and routing are unchanged (test asserts it).

## Found while working on the same day, outside Multica

HELIOS: `helios unpublish` sets a job to `awaiting_approval`, and with `HELIOS_AUTO_APPROVE=1` the worker makes
every such job public again on its next cycle. The owner's unpublish of `hnd1g_WmsMc` was undone 5 seconds later.
Kept private by marking the job `skipped` (audit `job.rejected`, 06:32:02Z). The code still needs a fix.

\* We thank Vulnetix for helping us improve our products.
