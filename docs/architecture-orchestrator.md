# Orchestrator architecture notes

## Pipeline worker and SRP

`pipeline_worker.py` hosts the main dequeue loop (phases 0–6). Per-task agent dispatch, gates, and remediation live in:

- `orchestrator/task_executor.py` — `PipelineTaskExecutor.process_task()` (extracted from the former monolithic `_process_task`).
- `orchestrator/pipeline_worker_sidecars.py` — `PipelineWorkerSidecarMixin`: marketplace readiness, optional `__runtime_test__` command inference, storefront-related gates.
- `orchestrator/worker_utils.py` — shared helpers (`env_truthy`, delivery profile resolution, monitoring refresh payload).

The concrete worker class composes the mixin so the core file stays readable without duplicating long helper blocks.

## Pipeline state machine: sync vs async

`orchestrator/state_machine.py` exposes both synchronous methods (`complete_task`, `fail_task`, …) and async variants (`acomplete_task`, `afail_task`, …) because callers include threaded code paths and asyncio workers.

Shared logic:

- **Completion** — `_apply_task_completion` updates the task, records Prometheus task duration / completion counters, advances product state, and enqueues the next task when appropriate. Sync callers then call `_save_state()`; async callers use `_asave_state_to_sqlite` or `asyncio.to_thread(self._save_state_to_json)` so persistence matches the `use_sqlite` flag.
- **Failure** — `_apply_task_failure` handles retries, permanent failure, product `FAILED` state, metrics, and logging. Both `fail_task` and `afail_task` delegate to it before persisting.

This keeps metrics and logging consistent between sync and async entry points.

## Director decisions: JSON vs SQLite

Two artifacts show up in discussions of “Director state”:

1. **`/app/data/state/director_decisions.json`** — human-facing file written by the Director worker and read by the admin API for pending/applied decisions. This path is the canonical **document** for operators and the UI.
2. **`director_decisions.db` (SQLite)** — `orchestrator/director_integration.py` keeps a SQLite database alongside the JSON path (same basename, `.db` suffix). It is used for structured storage and can **migrate** legacy JSON into the DB on first init when the DB is empty.

In short: the admin panel and worker still speak JSON on disk; the orchestrator integration layer adds SQLite for pipeline-side consumers and one-time migration. Unifying on a single backend would be a larger change; until then, treat JSON as the source for “what the UI shows” and the integration module as the bridge for applying decisions inside the worker process.

## Layered config in workers

Workers and services that read scheduling or feature toggles should use merged platform config (see `docs/configuration.md`) so Docker and local checkouts behave the same when defaults live in `config/fragments/` and overrides live in `config.yaml`.
