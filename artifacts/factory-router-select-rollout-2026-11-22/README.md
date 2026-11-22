# Factory: the routing rule's provider is used — production, 2026-11-22

Host factory-vps, container `aicom-app-1`. Times are UTC from the host clock. Owner's yes: «Выкати сейчас».

## What changed

Source: aicom `4f86b3819` (`llm/router.py`, `tests/test_llm_provider_selection.py`). `_select_provider` read
`default_provider` before the routing rule, so the provider chosen per task type in the admin routing editor never took
effect while a default was configured, and without a default the rule's fallback provider was picked ahead of its
preferred one. Now: the rule's provider (loaded and not UNAVAILABLE) → default → fastest; after a failure: the rule's
fallback → default → critical escalation. Models still come from the chosen provider's heavy/light slot.

The running `router.py` is older than main (no `provider_secrets`, a 47-line difference elsewhere), so the image
carries the running file with the same hunks (`router-fix.patch`; the hunk diff equals main's but for line numbers),
not main's file. Running file sha256 28d464ae…, new b4a861a9… (`files.sha256`).

## Image

| | |
|---|---|
| Running before | `aicom-security:aicom-app-1-search20-8c2f6e0a` (`sha256:8dd6b0aa…`) with `routes_providers.py` copied in by the routing-save activation of 06:46Z |
| Compose pin before | `aicom-security:aicom-app-1-routing-save-8242d71dc` (`sha256:33a77d58…`, search20 + that `routes_providers.py`) |
| After | `aicom-security:aicom-app-1-router-select-4f86b3819` = `sha256:0cc66fcc7efa9cb8acdc2835f6c2448fa785ed5ac25bdf21d8ad96e82d4b6da2`, `FROM` the routing-save image + `llm/router.py` (`Dockerfile`) |

Built on top of the routing-save image so that fix (08:39 +0100, `8242d71dc`, another session's, active in the
container but not yet in the image the container ran) is kept: after the switch the container has both files.

## Checks

- `check.py` inside the new image, no network: architecture_design (rule: deepseek_api) → deepseek_api; "auto",
  an unloaded provider and a task type without a rule → the default; failover deepseek → rule fallback → default.
  The same script on the routing-save image fails (all → default).
- No Factory build running before the switch: batch queue empty (items 0), director logging only analysis cycles.
- Replacement with `rollout_container.py` (from `/root/factory-search-20261120`) 06:57:29–06:57:48: dry run first; no
  environment name removed or set; mounts (`/app/data`, docker socket) and ports (127.0.0.1:9080, :9081) as before.
- 06:58: healthy, 0 restarts; `/api/health` 200, frontend 200; `pipeline_worker`, `director.worker` and uvicorn
  started with the new image; `llm/router.py` and `routes_providers.py` have the expected hashes. Log: the known
  "stranded product … DEV_FIXING" lines (8 days old), nothing new.
- Live config through the new router: only `openrouter_api` is loaded (the rules name disabled local_ollama /
  deepseek_api), so every task type still goes to openrouter_api with its heavy/light model, as before.
- `docker-compose.host-docker.yml` on the host names the new image (written in place; `/root/claudecode/aicom` keeps its
  immutable flag); `/root/claudecode/aicom/llm/router.py` written in place with the new file, as the routing-save
  activation did for its file. `aicom-factory-guard`: "factory tree whole".

Not checked: a real build with a second provider enabled and named in a rule (none is enabled).

## Rollback

On factory-vps, from `/root/factory-router-select-20261122`:

    python3 rollout_container.py aicom-app-1 --image aicom-security:aicom-app-1-routing-save-8242d71dc --health http://127.0.0.1:9081/api/health

then write `docker-compose.host-docker.yml.pre` back over `/root/claudecode/aicom/docker-compose.host-docker.yml` and
`router.py.before` over `/root/claudecode/aicom/llm/router.py`, in place. The previous container is kept stopped as
`aicom-app-1-security-prev-1795330649497581208`.
