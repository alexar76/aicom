"""The backend E2E gate blamed the product for a container the factory left behind.

``ensure_ephemeral_postgres`` starts a throwaway Postgres named after the product, and cleans up
first by looking the name up in ``_PG_CONTAINERS`` — a **process-local** dict. A container left by
a previous process is not in that dict, so nothing is removed, and the name it still holds is
derived from the product id and therefore identical on the next attempt:

    docker run rc=125 err=docker: Error response from daemon: Conflict. The container name
    "/aicom-pg-e2e-prod-bdb1634806de" is already in use

The gate then reported ``Backend runtime E2E: boot/probe failed`` and that reached the repair round
as a finding about the product — whose backend had never been started. Deploying the factory
restarts its process, so the case that defeats the cleanup is the most frequent one there is.

Cleanup is now by name rather than by memory, with one retry if the name is taken between the
clean and the run (two overlapping QA runs for one product).
"""

from __future__ import annotations

import subprocess

import pytest

from web.backend.services import sandbox_docker


class _Docker:
    """Records docker argv and answers from a scripted list of return codes."""

    def __init__(self, run_results: list[int]):
        self.calls: list[list[str]] = []
        self.run_results = list(run_results)

    def __call__(self, cmd, *a, **kw):
        self.calls.append(list(cmd))
        argv = " ".join(cmd)
        if cmd[:3] == ["docker", "run", "-d"]:
            rc = self.run_results.pop(0) if self.run_results else 0
            err = "Conflict. The container name \"/aicom-pg-x\" is already in use" if rc else ""
            return subprocess.CompletedProcess(cmd, rc, "cid\n" if not rc else "", err)
        return subprocess.CompletedProcess(cmd, 0, "ok\n", "")

    def argv_for(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]


@pytest.fixture
def docker(monkeypatch):
    d = _Docker([0])
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    monkeypatch.setattr(sandbox_docker, "docker_available", lambda: True)
    monkeypatch.setattr(sandbox_docker, "docker_cli_env", lambda: {})
    monkeypatch.setattr(sandbox_docker, "docker_daemon_host", lambda: "127.0.0.1")
    monkeypatch.setattr(sandbox_docker, "_published_container_port", lambda *a, **k: 55432)
    monkeypatch.setattr(sandbox_docker, "_wait_pg_ready", lambda *a, **k: True)
    sandbox_docker._PG_CONTAINERS.clear()
    return d


def test_a_container_this_process_never_started_is_removed(docker):
    """The exact production case: fresh process, container left by the previous one."""
    assert sandbox_docker._PG_CONTAINERS == {}, "precondition: nothing remembered"

    port, url, status = sandbox_docker.ensure_ephemeral_postgres("e2e-prod-bdb1634806de")

    assert status == "ok" and port == 55432 and url
    removals = docker.argv_for("docker", "rm", "-f")
    assert removals, "nothing was removed, so the next run hits the name conflict again"
    assert removals[0][-1] == "aicom-pg-e2e-prod-bdb1634806de", removals


def test_the_clean_happens_before_the_run(docker):
    """Removing it afterwards would be removing the container we just started."""
    sandbox_docker.ensure_ephemeral_postgres("e2e-prod-x")
    order = [c[:3] for c in docker.calls]
    assert order.index(["docker", "rm", "-f"]) < order.index(["docker", "run", "-d"]), order


def test_a_name_taken_mid_flight_is_retried_once(monkeypatch, docker):
    """Two overlapping QA runs for one product: fail, remove, succeed."""
    docker.run_results = [125, 0]
    port, _url, status = sandbox_docker.ensure_ephemeral_postgres("e2e-prod-x")
    assert status == "ok" and port == 55432
    assert len(docker.argv_for("docker", "run", "-d")) == 2, "the conflict was not retried"
    assert len(docker.argv_for("docker", "rm", "-f")) == 2, "the retry did not free the name"


def test_a_run_that_keeps_failing_still_gives_up(docker):
    """A retry loop here would hang the gate instead of failing it."""
    docker.run_results = [125, 125]
    port, url, status = sandbox_docker.ensure_ephemeral_postgres("e2e-prod-x")
    assert (port, url, status) == (None, None, "postgres_start_failed")
    assert len(docker.argv_for("docker", "run", "-d")) == 2, "it retried more than once"


def test_stopping_works_after_a_restart_forgot_the_name(docker):
    """Leaving it running is what breaks the *next* run, so the fallback matters most here."""
    sandbox_docker._PG_CONTAINERS.clear()
    sandbox_docker.stop_ephemeral_services("e2e-prod-bdb1634806de")
    removals = docker.argv_for("docker", "rm", "-f")
    assert removals and removals[-1][-1] == "aicom-pg-e2e-prod-bdb1634806de", removals


def test_a_missing_container_is_not_an_error(docker):
    """`docker rm -f` on an absent name exits non-zero; that is the normal case."""
    monkey = _Docker([0])

    def failing(cmd, *a, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(cmd, 1, "", "No such container: x")
        return monkey(cmd, *a, **kw)

    sandbox_docker.subprocess.run = failing
    try:
        _port, _url, status = sandbox_docker.ensure_ephemeral_postgres("e2e-prod-x")
    finally:
        sandbox_docker.subprocess.run = subprocess.run
    assert status == "ok", "an absent container was treated as a failure"


def test_docker_being_unavailable_is_still_reported_plainly(monkeypatch):
    monkeypatch.setattr(sandbox_docker, "docker_available", lambda: False)
    assert sandbox_docker.ensure_ephemeral_postgres("x") == (None, None, "docker_unavailable")


# --- and nothing should accumulate in the first place -----------------------------------------


def _listing(names: list[str], ages_h: dict[str, float]):
    """A docker stub whose `ps` returns `names` and whose `inspect` dates them."""
    import datetime as _dt

    def run(cmd, *a, **kw):
        if cmd[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(cmd, 0, "\n".join(names) + "\n", "")
        if cmd[:2] == ["docker", "inspect"]:
            name = cmd[-1]
            if name not in ages_h:
                return subprocess.CompletedProcess(cmd, 1, "", "No such object")
            when = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=ages_h[name])
            # Docker emits nanoseconds, which fromisoformat rejects.
            stamp = when.strftime("%Y-%m-%dT%H:%M:%S.") + "123456789Z"
            return subprocess.CompletedProcess(cmd, 0, stamp + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run


def test_containers_left_by_dead_processes_are_reaped(monkeypatch):
    """Production had ten, the oldest up for 46 hours.

    Two of them held the names this product's demo-journey and backend-E2E gates needed, so both
    reported its backend as unbootable for the whole run — and the demo journey votes on whether a
    repair round is kept, which made our own rubbish a party to throwing work away.
    """
    from web.backend.services.sandbox_docker import reap_stale_ephemeral_containers

    names = ["aicom-pg-journey-prod-bdb1634806de", "aicom-pg-e2e-prod-bdb1634806de"]
    monkeypatch.setattr(
        sandbox_docker.subprocess, "run", _listing(names, {n: 46.0 for n in names})
    )
    assert sorted(reap_stale_ephemeral_containers(env={})) == sorted(names)


def test_a_container_still_in_use_survives(monkeypatch):
    """A gate's Postgres lives for minutes; reaping a live one would break the run it serves."""
    from web.backend.services.sandbox_docker import reap_stale_ephemeral_containers

    names = ["aicom-pg-journey-prod-x", "aicom-pg-e2e-prod-y"]
    monkeypatch.setattr(
        sandbox_docker.subprocess,
        "run",
        _listing(names, {"aicom-pg-journey-prod-x": 0.05, "aicom-pg-e2e-prod-y": 46.0}),
    )
    assert reap_stale_ephemeral_containers(env={}) == ["aicom-pg-e2e-prod-y"]


def test_this_process_own_container_is_never_reaped(monkeypatch):
    """Even past the age threshold — a long QA run is not a leak."""
    from web.backend.services.sandbox_docker import reap_stale_ephemeral_containers

    name = "aicom-pg-journey-prod-mine"
    sandbox_docker._PG_CONTAINERS["journey-prod-mine"] = name
    try:
        monkeypatch.setattr(sandbox_docker.subprocess, "run", _listing([name], {name: 99.0}))
        assert reap_stale_ephemeral_containers(env={}) == []
    finally:
        sandbox_docker._PG_CONTAINERS.clear()


def test_an_unknowable_age_is_left_alone(monkeypatch):
    """A live Postgres mid-query is worth more than a tidy container list."""
    from web.backend.services.sandbox_docker import reap_stale_ephemeral_containers

    monkeypatch.setattr(sandbox_docker.subprocess, "run", _listing(["aicom-pg-mystery"], {}))
    assert reap_stale_ephemeral_containers(env={}) == []


def test_the_sweep_runs_without_anyone_wiring_it_up(docker, monkeypatch):
    """Lazy and once per process: a startup hook is a thing someone can forget to call."""
    called: list[bool] = []
    monkeypatch.setattr(
        sandbox_docker,
        "reap_stale_preview_resources",
        lambda **kw: called.append(True) or {"containers": 0, "volumes": 0, "networks": 0},
    )
    sandbox_docker._REAPED_THIS_PROCESS = False
    sandbox_docker.ensure_ephemeral_postgres("e2e-prod-a")
    sandbox_docker.ensure_ephemeral_postgres("e2e-prod-b")
    assert called == [True], "the sweep ran per call instead of per process"


def test_a_failing_sweep_never_fails_the_gate(docker, monkeypatch):
    """Tidying up must not be able to break the thing it tidies for."""
    def boom(**kw):
        raise RuntimeError("docker daemon went away")

    monkeypatch.setattr(sandbox_docker, "reap_stale_preview_resources", boom)
    sandbox_docker._REAPED_THIS_PROCESS = False
    _port, _url, status = sandbox_docker.ensure_ephemeral_postgres("e2e-prod-a")
    assert status == "ok"
