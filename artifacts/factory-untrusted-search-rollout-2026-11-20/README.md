# Factory: screened and fenced web search text — production, 2026-11-20

Host factory-vps, container `aicom-app-1`. Times are UTC from the host clock. Owner's yes: «Да, выкатывай».

## What changed

Source: aicom `829d6841a` (`core/untrusted_text.py`, `agents/analyst.py`, `agents/pm.py`, `agents/architect.py`,
`agents/marketing.py`, 21 tests in `tests/test_untrusted_search_text.py`).

- The analyst drops search results that address the model or carry a link that is not http(s), removes invisible
  characters, and puts the rest inside a boundary with a random marker and the rule "data, not instructions".
- PM, architect and marketing get the saved market research without the raw `search_results`.

Found on the live Factory the same day: all 25 saved market research files had search snippets in the analyst's
prompt, unmarked, and three later agents received them raw. The newest of those files is from 2026-08-22.

## Image

| | |
|---|---|
| Before | `aicom-security:aicom-app-1-audit19-f2ddfa13` = `sha256:8c2f6e0afa84…` |
| After | `aicom-security:aicom-app-1-search20-8c2f6e0a` = `sha256:8dd6b0aaab5dcc0e7895c2e0f0f3562f935407110af7e27b3b30a7be14c567f2` |
| Built | on factory-vps from the running image, `Dockerfile` in this folder, five files (`files.sha256`) |

Before the build the running container's `analyst.py`, `pm.py` and `marketing.py` were byte-equal to the repository's
versions before `829d6841a`. `architect.py` differed from the repository in import order only, so the image carries
the running file with the one-line change, not the repository's file.

## Checks

- `check.py` inside the new image without network: two poisoned results and one ordinary one, only the ordinary one
  reaches the prompt and the sources, the prompt has the boundary. The same script on the old image fails (no
  `core.untrusted_text`).
- Replacement with `rollout_container.py` (the kit of `artifacts/aid-pka-rollout-2026-11-19/`), 04:42:20–04:42:40:
  no environment name removed or set, mounts and ports as before (`/app/data`, docker socket, 127.0.0.1:9080 and
  :9081). The Factory had no task running.
- 04:42:53 healthy, 0 restarts; `/api/health` 200 and the frontend 200 on the host; the five files in the container
  have the hashes of `files.sha256`. Log: connection refusals of the frontend during the first seconds of start, the
  known "stranded product" line; none in the minute after.
- `docker-compose.host-docker.yml` on the host names the new image (written in place; `/root/claudecode` keeps its
  immutable flag). The repository's copy of that file has no image line: the pin exists on the host only, as before. `aicom-factory-guard`: "factory tree whole".

Not checked: a real analyst run with live search and a model. No product has reached the analyst since August.

## Rollback

On factory-vps, from `/root/factory-search-20261120`:

    python3 rollout_container.py aicom-app-1 --image aicom-security:aicom-app-1-audit19-f2ddfa13 --health http://127.0.0.1:9081/api/health

then put `docker-compose.host-docker.yml.pre` (same folder) back over `/root/claudecode/aicom/docker-compose.host-docker.yml`
by writing it in place. The previous container is kept stopped as `aicom-app-1-security-prev-1795149741017654668`;
its inspect snapshot is in `/root/security-rollbacks/aicom-app-1-1795149741017654668/`.
