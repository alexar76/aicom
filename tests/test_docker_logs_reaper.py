"""scripts/docker_logs_reaper.py: which processes count as an abandoned `docker logs` call."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docker_logs_reaper.py"
spec = importlib.util.spec_from_file_location("docker_logs_reaper", SCRIPT)
reaper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reaper)


@pytest.mark.parametrize("cmd", [
    "docker logs ecosystem-aimarket-hub-1 --tail 40",          # the 2026-10-08 culprits
    "docker logs --tail 80 helios-worker",
    "/usr/bin/docker logs -n 15 hub",
    "docker container logs hub",
    "docker -H unix:///var/run/docker.sock logs hub",
    "docker --context=prod logs hub",
    "docker compose logs --tail 50",
    "docker compose -f docker-compose.yml logs hub",           # -f before logs is the compose file
    "docker-compose -f x.yml logs",
    "/usr/libexec/docker/cli-plugins/docker-compose compose logs hub",
    "docker service logs web",
    "docker logs --follow=false hub",
])
def test_stale_logs_calls(cmd):
    assert reaper.is_stale_logs_call(cmd.split())


@pytest.mark.parametrize("cmd", [
    "docker logs -f hub",
    "docker logs --follow hub",
    "docker logs -tf hub",
    "docker logs --tail 100 -f hub",
    "docker compose -f docker-compose.yml logs -f",
    "docker ps",
    "docker container ls",
    "docker exec hub sh -c docker logs x",
    "docker -H tcp://x:2375 ps",
    "bash -c docker logs hub --tail 15",
    "python3 logs.py",
    "",
])
def test_left_alone(cmd):
    assert not reaper.is_stale_logs_call(cmd.split())
