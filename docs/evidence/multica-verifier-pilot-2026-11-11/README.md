# Evidence replay for Multica `platform_smoke`

Multica issue #4098 includes a report of a Codex run marked complete without an inspectable worktree or commit. Issue #4804 asks for evidence on status transitions, including warn-mode examples. This pilot answers one narrower question for the existing fixed QA job. Can an operator distinguish a successful check, a failed check and a completed task with insufficient evidence? [Multica #4098](https://github.com/multica-ai/multica/issues/4098), [Multica #4804](https://github.com/multica-ai/multica/issues/4804)

## Run the offline pilot

From the checkout root with Python 3.9+ and Node 22.15+ on the Node 22 line (or a later version with `node:module.registerHooks`):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/evidence/multica-verifier-pilot-2026-11-11/replay.py
```

The script prints one JSON document. It returns 0 when all three expected outcomes match, including the expected worker failure. A nonzero replay exit means the replay failed, its prerequisites were missing, or its outcomes differed. The child process exit appears as `local_worker_exit_code`. The report records runtime versions and the SHA-256 of each exercised source and fixture. [Recorded result](result.json)

| Case | Synthetic task state | Ordered worker statuses | Worker exit | Tool result for this task | Verdict |
| --- | --- | --- | ---: | --- | --- |
| `healthy` | `completed` | `200 / 200 / 200` | 0 | Present and passing | `pass` |
| `required_check_failed` | `completed` | `200 / 503 / 200` | 1 | Present and failing | `fail` |
| `missing_same_task_report` | `completed` | `200 / 200 / 200` from the control task | 0 | Absent. The passing result belongs to another task. | `unverifiable` |

The order is backend, ModelMarket, Hub. `controller_status: 200` in all three cases means the broker processed a well-formed worker report, including the case with an actual child process exit of 1. The verdict uses the report for the matching task. Every case has a `completed` state, one recorded tool invocation and a success claim in final text. The third case excludes a passing result associated with a different synthetic task ID. Its `multica_acceptance_passed` stays `false`.

The replay runs the checked-out [worker CLI](../../../multica/qa-runner/worker/smoke.mjs), [broker subprocess and report validation](../../../multica/qa-runner/broker/broker.py) and [acceptance summarizer](../../../artifacts/multica-qa-runner-2026-11-10/create-profile.py). The Node preload replaces the worker's HTTP transport with fixed responses. The replay substitutes a fixed local Node command for the broker's Docker command and uses an in-memory task capture. It selects tool events by synthetic task ID before calling the summarizer, which normally receives a task-scoped SQL capture. This exercises report validation and acceptance logic with no network, server, credentials, Docker, model, database or Multica installation.

The earlier [MY-89 acceptance](../../../artifacts/multica-qa-runner-2026-11-10/final-acceptance.json) recorded a live native MCP call for the fixed job in our environment, with three HTTP 200 responses and a validated report in the stored result and comment. This replay covers the three fixture outcomes. It does not test the deployed MCP/TLS path, quotas, live endpoint health, worktree or commit contents, artifact quality, or the proposed Multica status transitions.

## Hand the pilot to one self-hosted operator

1. Run the offline command on a trusted checkout as an ordinary local user. Save the JSON and compare `matched_expected`, the source hashes, and the three verdicts. The first replication needs no change to a Multica instance.
2. For a follow-up on an existing private staging QA profile, use the operator-owned, pinned `platform_smoke` job from the [runner manual](../../../multica/qa-runner/README.md). Keep the runner private, keep the general shell denied and use only the fixed native tool call `qa_runner_task_execute` with `{"id":"platform_smoke"}`. Select a disposable staging issue. Use the offline failure case to show the negative outcome without interrupting a service.
3. Have the operator or reviewer compare the task identifier and invocation with the tool's stored result from that task. Record the fixed job name, source or image revision, bounded check statuses, worker exit, and whether capture was complete. If the report is absent, malformed or belongs to a different task, mark the outcome `unverifiable` and investigate the capture. Treat a valid required-check failure as `fail`. Keep the task's existing status visible for comparison during the pilot.
4. Keep task identifiers and raw records in the operator's instance. For a shared result, retain only the expected and observed verdicts, safe check labels and codes, runtime versions, hashes, and a short scope note. For a later code-task pilot, the reviewer would also need evidence from the same task that identifies the exact worktree, commit and required test results. `platform_smoke` validates only its own fixed status checks.
