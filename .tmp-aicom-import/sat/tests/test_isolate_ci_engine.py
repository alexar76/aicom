"""isolate_ci_engine must change only the networks entries of the CI compose file.

PyYAML reads YAML 1.1, where `222:22` is the base-60 number 13342; Docker Compose
reads YAML 1.2, where it is a port mapping. Re-serialising the file through PyYAML
turned Gitea's SSH mapping into `- 13342`. The docker CLI below is a fake: it keeps
the live networks and answers `compose config` with a YAML 1.2 reading of the file.
"""
import copy
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "security" / "isolate_ci_engine.py"


class Yaml12(yaml.SafeLoader):
    """SafeLoader without YAML 1.1's base-60 integers, as Compose reads files."""


Yaml12.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:int"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}
Yaml12.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^[-+]?[0-9]+$"), list("-+0123456789"))


def compose_view(text, project="gitea"):
    """Roughly what `docker compose config --format json` prints."""
    doc = yaml.load(text, Loader=Yaml12)
    for svc in doc["services"].values():
        nets = svc.get("networks")
        if nets is None:
            svc["networks"] = {"default": None}
        elif isinstance(nets, list):
            svc["networks"] = {n: None for n in nets}
    top = doc.get("networks") or {}
    if any("default" in s["networks"] for s in doc["services"].values()):
        top.setdefault("default", {"name": project + "_default"})
    doc["networks"] = top
    doc["name"] = project
    return doc


class FakeDocker:
    def __init__(self, compose_path):
        self.path = compose_path
        self.networks = {"bridge": set(), "gitea_default": {"gitea", "gitea-runner-dind", "act_runner"}}
        self.calls = []

    def reaches(self):
        return any({"gitea-runner-dind", "act_runner"} <= m for m in self.networks.values())

    def __call__(self, *args, input=None, cwd=None):
        self.calls.append(args)
        if args[0] == "inspect":
            nets = {n: {} for n, members in self.networks.items() if args[1] in members}
            return json.dumps([{"Config": {"Labels": {"com.docker.compose.project": "gitea"}},
                                "NetworkSettings": {"Networks": nets, "Ports": {"2375/tcp": None}}}])
        if args[0] == "exec":
            if "_ping" in args[-1]:
                return "OK" if self.reaches() else ""
            return "[]"
        if args[:2] == ("network", "ls"):
            return "\n".join(self.networks)
        if args[:2] == ("network", "create"):
            self.networks[args[2]] = set()
            return ""
        if args[:2] == ("network", "inspect"):
            return json.dumps([{"Containers": {str(i): {"Name": n}
                                               for i, n in enumerate(sorted(self.networks[args[2]]))}}])
        if args[:2] == ("network", "connect"):
            self.networks[args[-2]].add(args[-1])
            return ""
        if args[:2] == ("network", "disconnect"):
            self.networks[args[2]].discard(args[3])
            return ""
        if args[0] == "compose":
            text = input.decode() if "-" in args else self.path.read_text()
            try:
                view = compose_view(text)
            except yaml.YAMLError as exc:
                raise subprocess.CalledProcessError(15, args) from exc
            return json.dumps(view) if "json" in args else ""
        raise AssertionError(f"unexpected docker call {args}")

    def mutations(self):
        return [c for c in self.calls if c[:2] in (("network", "create"), ("network", "connect"),
                                                    ("network", "disconnect"))]


GITEA = """\
# Gitea and its CI runner. keep-1
services:
  server:
    image: gitea/gitea:1.22
    container_name: gitea
    ports:
      - 3000:3000   # web keep-2
      - 222:22      # git over ssh keep-3
    volumes:
      - ./data:/data
  runner-dind:
    image: docker:27-dind
    container_name: gitea-runner-dind
    privileged: true
    networks:
      - default
    # keep-4: the engine must never publish 2375
    environment:
      DOCKER_TLS_CERTDIR: ""
  act_runner:
    image: gitea/act_runner:0.2.11
    container_name: act_runner
    environment:
      DOCKER_HOST: tcp://runner-dind:2375  # keep-5
"""

LAYOUTS = {
    "block-lists-and-no-top-level-networks": GITEA,
    "flow-lists-and-existing-top-level-networks": GITEA.replace(
        "    networks:\n      - default\n", "    networks: [default]\n").replace(
        "    container_name: act_runner\n",
        "    container_name: act_runner\n    networks:\n      - default\n") + (
        "networks:\n  default:\n    name: gitea_default   # keep-6\n"),
    "indentless-lists-and-mapping-networks": GITEA.replace(
        "    networks:\n      - default\n", "    networks:\n    - default\n").replace(
        "    container_name: act_runner\n",
        "    container_name: act_runner\n    networks:\n      default:\n"),
    "engine-without-networks-key": GITEA.replace("    networks:\n      - default\n", ""),
    "json-compose-file": json.dumps({"services": {
        "server": {"image": "gitea/gitea:1.22", "container_name": "gitea", "ports": ["222:22"]},
        "runner-dind": {"image": "docker:27-dind", "container_name": "gitea-runner-dind"},
        "act_runner": {"image": "gitea/act_runner:0.2.11", "container_name": "act_runner"}}}, indent=2),
}


@pytest.fixture
def iso(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("isolate_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(iso, monkeypatch, tmp_path, text, *extra):
    path = tmp_path / "docker-compose.yml"
    path.write_text(text)
    fake = FakeDocker(path)
    monkeypatch.setattr(iso, "docker", fake)
    monkeypatch.setattr("sys.argv", ["isolate_ci_engine.py", str(path), *extra])
    iso.main()
    return path, fake


def without_networks(doc):
    doc = copy.deepcopy(doc)
    doc.pop("networks", None)
    for name in ("runner-dind", "act_runner"):
        doc["services"][name].pop("networks", None)
    return doc


def test_ssh_port_mapping_and_comments_survive(iso, monkeypatch, tmp_path):
    path, fake = run(iso, monkeypatch, tmp_path, GITEA)
    text = path.read_text()
    assert "      - 222:22      # git over ssh keep-3\n" in text
    doc = yaml.load(text, Loader=Yaml12)
    assert doc["services"]["server"]["ports"] == ["3000:3000", "222:22"]
    for n in range(1, 6):
        assert f"keep-{n}" in text
    assert doc["services"]["runner-dind"]["networks"] == {"runner_engine": {"aliases": ["runner-dind"]}}
    assert doc["services"]["act_runner"]["networks"] == ["default", "runner_engine"]
    assert doc["networks"] == {"runner_engine": {"external": True, "name": "gitea_runner_engine"}}
    assert fake.networks["gitea_runner_engine"] == {"gitea-runner-dind", "act_runner"}
    assert "gitea-runner-dind" not in fake.networks["gitea_default"]


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_only_the_networks_entries_change(iso, monkeypatch, tmp_path, layout):
    original = LAYOUTS[layout]
    path, _ = run(iso, monkeypatch, tmp_path, original)
    text = path.read_text()
    before, after = yaml.load(original, Loader=Yaml12), yaml.load(text, Loader=Yaml12)
    assert without_networks(after) == without_networks(before)
    view = compose_view(text)
    assert view["services"]["runner-dind"]["networks"] == {"runner_engine": {"aliases": ["runner-dind"]}}
    assert set(view["services"]["act_runner"]["networks"]) == {"default", "runner_engine"}
    assert view["networks"]["runner_engine"] == {"external": True, "name": "gitea_runner_engine"}
    for line in original.splitlines():
        if "keep-" in line:
            assert line in text.splitlines()
    if layout == "json-compose-file":
        json.loads(text)  # a JSON compose file stays JSON


def test_edit_that_changes_anything_else_is_refused_before_any_live_change(iso, monkeypatch, tmp_path):
    real = iso.edit_compose
    monkeypatch.setattr(iso, "edit_compose", lambda text, net: real(text, net).replace("3000:3000", "3001:3000"))
    path = tmp_path / "docker-compose.yml"
    with pytest.raises(RuntimeError, match="services.server"):
        run(iso, monkeypatch, tmp_path, GITEA)
    assert path.read_text() == GITEA
    assert not list(tmp_path.glob("*.security-backup-*"))


def test_dry_run_prints_plan_and_diff_and_changes_nothing(iso, monkeypatch, tmp_path, capsys):
    path, fake = run(iso, monkeypatch, tmp_path, GITEA, "--dry-run")
    assert path.read_text() == GITEA
    assert fake.mutations() == []
    assert not list(tmp_path.glob("*.security-backup-*"))
    plan = json.loads(capsys.readouterr().out)
    assert plan["commands"] == [
        "docker network create gitea_runner_engine",
        "docker network connect --alias runner-dind gitea_runner_engine gitea-runner-dind",
        "docker network connect --alias act_runner gitea_runner_engine act_runner",
        "docker network disconnect gitea_default gitea-runner-dind",
    ]
    changed = [line for line in plan["compose_diff"] if line[:1] in "+-" and line[:3] not in ("+++", "---")]
    assert "-      - default" in changed
    assert "+    networks: {\"runner_engine\": {\"aliases\": [\"runner-dind\"]}}" in changed
    assert not any("222:22" in line or "environment" in line for line in changed)
