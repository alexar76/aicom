"""Leftover DinD preview containers and dangling volumes must not sit until disk is full."""

from __future__ import annotations

import subprocess

from web.backend.services import sandbox_docker


class _Docker:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.ps: dict[str, list[str]] = {}
        self.ages_h: dict[str, float] = {}
        self.dangling: list[str] = []
        self.networks: list[str] = []
        self.rm_fail: set[str] = set()

    def __call__(self, cmd, *a, **kw):
        self.calls.append(list(cmd))
        if cmd[:2] == ["docker", "ps"]:
            filt = ""
            for i, part in enumerate(cmd):
                if part == "--filter" and i + 1 < len(cmd) and cmd[i + 1].startswith("name="):
                    filt = cmd[i + 1].split("=", 1)[1]
            names = [n for n in self.ps.get(filt, []) if filt in n or n.startswith(filt)]
            if filt and filt not in self.ps:
                names = [n for key, vals in self.ps.items() for n in vals if filt in n]
            return subprocess.CompletedProcess(cmd, 0, "\n".join(names) + ("\n" if names else ""), "")
        if cmd[:2] == ["docker", "inspect"]:
            name = cmd[-1]
            if name not in self.ages_h:
                return subprocess.CompletedProcess(cmd, 1, "", "No such object")
            import datetime as dt

            when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=self.ages_h[name])
            stamp = when.strftime("%Y-%m-%dT%H:%M:%S.") + "123456789Z"
            return subprocess.CompletedProcess(cmd, 0, stamp + "\n", "")
        if cmd[:3] == ["docker", "volume", "ls"]:
            return subprocess.CompletedProcess(cmd, 0, "\n".join(self.dangling) + "\n", "")
        if cmd[:3] == ["docker", "volume", "rm"]:
            if any(v in self.rm_fail for v in cmd[3:]):
                return subprocess.CompletedProcess(cmd, 1, "", "in use")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["docker", "network", "ls"]:
            return subprocess.CompletedProcess(cmd, 0, "\n".join(self.networks) + "\n", "")
        if cmd[:3] == ["docker", "network", "rm"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_stale_sandbox_http_containers_are_reaped(monkeypatch):
    d = _Docker()
    d.ps["sandbox-"] = ["sandbox-old", "sandbox-fresh"]
    d.ages_h = {"sandbox-old": 24.0, "sandbox-fresh": 0.2}
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    assert sandbox_docker.reap_stale_sandbox_containers(env={}) == ["sandbox-old"]


def test_pg_named_sandbox_is_not_double_counted_as_preview_container(monkeypatch):
    d = _Docker()
    d.ps["sandbox-"] = ["aicom-pg-sandbox-abc", "sandbox-dead"]
    d.ages_h = {"aicom-pg-sandbox-abc": 24.0, "sandbox-dead": 24.0}
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    assert sandbox_docker.reap_stale_sandbox_containers(env={}) == ["sandbox-dead"]


def test_dangling_volumes_are_removed(monkeypatch):
    d = _Docker()
    d.dangling = ["aaa" * 8, "bbb" * 8]
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    assert sandbox_docker.prune_unused_preview_volumes(env={}) == 2
    assert any(c[:3] == ["docker", "volume", "rm"] for c in d.calls)


def test_isolation_networks_are_removed(monkeypatch):
    d = _Docker()
    d.networks = ["aicom-sb-prod-bdb", "bridge"]
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    assert sandbox_docker.prune_unused_preview_networks(env={}) == 1
    assert ["docker", "network", "rm", "aicom-sb-prod-bdb"] in d.calls
    assert ["docker", "network", "rm", "bridge"] not in d.calls


def test_full_gc_reaps_containers_then_volumes(monkeypatch):
    d = _Docker()
    d.ps["aicom-pg-"] = ["aicom-pg-e2e-prod-x"]
    d.ps["sandbox-"] = ["sandbox-old"]
    d.ages_h = {"aicom-pg-e2e-prod-x": 22.0, "sandbox-old": 24.0}
    d.dangling = ["deadvol"]
    d.networks = ["aicom-sb-leftover"]
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    stats = sandbox_docker.reap_stale_preview_resources(env={})
    assert stats == {"containers": 2, "volumes": 1, "networks": 1}


def test_gc_kill_switch(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SANDBOX_GC", "0")
    d = _Docker()
    d.dangling = ["deadvol"]
    monkeypatch.setattr(sandbox_docker.subprocess, "run", d)
    assert sandbox_docker.reap_stale_preview_resources(env={}) == {
        "containers": 0,
        "volumes": 0,
        "networks": 0,
    }
    assert d.calls == []
