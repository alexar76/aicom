"""rollout_container must carry a container's namespace borrowers and run-time choices
across a swap, and put everything back when any step fails.

The engine below is a fake of the Docker API: it keeps containers, images, names and
network namespaces, applies Docker's image/config merge on create and its container:
networking rules on create and start. No Docker daemon is involved.
"""
import copy
import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "security"
HUB_URL = "http://127.0.0.1:9083/.well-known/ai-market.json"
THEMIS_URL = "http://127.0.0.1:9460/health"  # published by the hub, served by THEMIS
ATLAS_URL = "http://127.0.0.1:9300/health"


def docker_merge(user, image):
    """What Docker does with a create request's config and its image's defaults."""
    cfg = copy.deepcopy(user)
    img = image["Config"]
    keys = {e.partition("=")[0] for e in cfg.get("Env") or []}
    cfg["Env"] = list(cfg.get("Env") or []) + [
        e for e in img.get("Env") or [] if e.partition("=")[0] not in keys]
    cfg["Labels"] = {**(img.get("Labels") or {}), **(cfg.get("Labels") or {})}
    if not cfg.get("Entrypoint"):
        if not cfg.get("Cmd"):
            cfg["Cmd"] = img.get("Cmd")
        if cfg.get("Entrypoint") is None:
            cfg["Entrypoint"] = img.get("Entrypoint")
    for key in ("WorkingDir", "User", "StopSignal"):
        if not cfg.get(key):
            cfg[key] = img.get(key, "")
    if cfg.get("Healthcheck") is None:
        cfg["Healthcheck"] = img.get("Healthcheck")
    cfg["ExposedPorts"] = {**(img.get("ExposedPorts") or {}), **(cfg.get("ExposedPorts") or {})}
    return cfg


class Engine:
    def __init__(self):
        self.containers = {}
        self.images = {}
        self.calls = []
        self.bodies = {}
        self.fail_on = set()
        self.broken_images = set()
        self.generation = 0

    # -- setup helpers ---------------------------------------------------------------
    def image(self, tag, **config):
        image_id = "sha256:" + hashlib.sha256(tag.encode()).hexdigest()
        self.images[image_id] = {"Id": image_id, "RepoTags": [tag], "Config": config}
        return image_id

    def run(self, name, image, host, networks=(), mounts=(), **config):
        body = dict(config, Image=image, HostConfig=host,
                    NetworkingConfig={"EndpointsConfig": {n: {} for n in networks}})
        cid = self("POST", "/containers/create?name=" + name, body)["Id"]
        if mounts:
            self.containers[cid]["Mounts"] = list(mounts)
        if config.get("Hostname") is None and not host["NetworkMode"].startswith("container:"):
            self.containers[cid]["Config"]["Hostname"] = cid[:12]
        self("POST", f"/containers/{cid}/start")
        self.calls.clear()
        return cid

    # -- lookups -----------------------------------------------------------------------
    def find(self, ref):
        for c in self.containers.values():
            if ref in (c["Id"], c["Name"].lstrip("/")) or (len(ref) >= 12 and c["Id"].startswith(ref)):
                return c
        raise RuntimeError(f"HTTP 404 {ref}")

    def named(self, name):
        return self.find(name)

    def names(self):
        return sorted(c["Name"].lstrip("/") for c in self.containers.values())

    def reachable(self, borrower="themis", owner="modelmarket-hub"):
        o, b = self.find(owner), self.find(borrower)
        return (o["State"]["Running"] and b["State"]["Running"]
                and b["_netns"] is not None and b["_netns"] == o["_netns"])

    def health(self, url, timeout=90):
        hub = self.find("modelmarket-hub") if "9083" in url or "9460" in url else self.find("atlas")
        ok = hub["State"]["Running"] and hub["Image"] not in self.broken_images
        if url == THEMIS_URL:
            ok = ok and self.reachable()
        if not ok:
            raise RuntimeError("Health check failed")

    # -- the API -----------------------------------------------------------------------
    def __call__(self, method, path, body=None):
        self.calls.append((method, path))
        url = urllib.parse.urlsplit(path)
        parts = url.path.strip("/").split("/")
        query = dict(urllib.parse.parse_qsl(url.query))
        verb = "delete" if method == "DELETE" else parts[-1]
        target = query.get("name", "") if verb == "create" else (
            parts[1] if len(parts) > 1 and parts[0] == "containers" else "")
        for m, v, who in self.fail_on:
            if m == method and v == verb and who in (target, self._name_of(target)):
                raise RuntimeError(f"Docker {method} {url.path} failed: HTTP 500")
        if method == "GET" and parts == ["containers", "json"]:
            return [{"Id": c["Id"], "Names": [c["Name"]], "HostConfig": {"NetworkMode": c["HostConfig"]["NetworkMode"]}}
                    for c in self.containers.values() if c["State"]["Running"]]
        if method == "GET" and parts[0] == "containers":
            return self._public(self.find(parts[1]))
        if method == "GET" and parts[0] == "images":
            ref = "/".join(parts[1:-1])
            for img in self.images.values():
                if ref == img["Id"] or ref in img["RepoTags"]:
                    return copy.deepcopy(img)
            raise RuntimeError("HTTP 404 image")
        if verb == "create":
            return self._create(query["name"], body)
        c = self.find(parts[1])
        if verb == "delete":
            del self.containers[c["Id"]]
        elif verb == "stop":
            c["State"]["Running"] = False
        elif verb == "rename":
            if any(o["Name"] == "/" + query["name"] for o in self.containers.values() if o is not c):
                raise RuntimeError("HTTP 409 name in use")
            c["Name"] = "/" + query["name"]
        elif verb == "start":
            self._start(c)
        elif verb == "restart":
            c["State"]["Running"] = False
            self._start(c)
        else:
            raise AssertionError(f"unexpected call {method} {path}")
        return None

    def _name_of(self, ref):
        try:
            return self.find(ref)["Name"].lstrip("/")
        except RuntimeError:
            return ref

    def _public(self, c):
        return copy.deepcopy({k: v for k, v in c.items() if not k.startswith("_")})

    def _create(self, name, body):
        if any(c["Name"] == "/" + name for c in self.containers.values()):
            raise RuntimeError("HTTP 409 name in use")
        body = copy.deepcopy(body)
        self.bodies[name] = copy.deepcopy(body)
        host = body.pop("HostConfig")
        endpoints = body.pop("NetworkingConfig", {}).get("EndpointsConfig") or {}
        if host["NetworkMode"].startswith("container:") and (
                body.get("Hostname") or body.get("ExposedPorts") or host.get("PortBindings")):
            raise RuntimeError("HTTP 400 conflicting options with container: networking")
        image = next(img for img in self.images.values()
                     if body["Image"] in (img["Id"], *img["RepoTags"]))
        cid = hashlib.sha256(f"{name}/{len(self.bodies)}".encode()).hexdigest()
        mounts = [{"Type": "tmpfs", "Destination": m["Target"], "RW": True}
                  for m in host.get("Mounts") or [] if m["Type"] == "tmpfs"]
        for bind in host.get("Binds") or []:
            src, dst, mode = bind.split(":")
            mounts.append({"Type": "bind" if src.startswith("/") else "volume", "Name": src,
                           "Source": src, "Destination": dst, "RW": mode == "rw"})
        self.containers[cid] = {
            "Id": cid, "Name": "/" + name, "Image": image["Id"],
            "Config": docker_merge(body, image), "HostConfig": host, "Mounts": mounts,
            "NetworkSettings": {"Networks": {n: {"Aliases": (e.get("Aliases") or []) + [cid[:12]]}
                                             for n, e in endpoints.items()}},
            "State": {"Running": False}, "_netns": None,
        }
        return {"Id": cid}

    def _start(self, c):
        if c["State"]["Running"]:
            return
        mode = c["HostConfig"]["NetworkMode"]
        if mode.startswith("container:"):
            owner = self.find(mode.split(":", 1)[1])
            if not owner["State"]["Running"]:
                raise RuntimeError("HTTP 409 cannot join network of a non running container")
            c["_netns"] = owner["_netns"]
        else:
            self.generation += 1
            c["_netns"] = (c["Id"], self.generation)
        c["State"] = {"Running": True}
        if c["Config"].get("Healthcheck"):
            c["State"]["Health"] = {"Status": "healthy"}


@pytest.fixture
def engine():
    e = Engine()
    old = e.image("modelmarket-hub:prod",
                  Env=["PATH=/usr/local/bin:/usr/bin:/bin", "PYTHON_VERSION=3.12.0", "LANG=C.UTF-8"],
                  Entrypoint=["python", "-m", "aimarket_hub", "serve"], Cmd=None, WorkingDir="/app",
                  Labels={"org.opencontainers.image.version": "old"}, ExposedPorts={"9083/tcp": {}},
                  Healthcheck={"Test": ["CMD-SHELL", "curl -f http://localhost:9083/ || exit 1"]})
    e.image("modelmarket-hub:new",
            Env=["PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin", "PYTHON_VERSION=3.13.1", "LANG=C.UTF-8"],
            Entrypoint=["python", "-m", "aimarket_hub", "serve", "--new"], Cmd=None, WorkingDir="/srv",
            Labels={"org.opencontainers.image.version": "new"}, ExposedPorts={"9083/tcp": {}},
            Healthcheck={"Test": ["CMD-SHELL", "curl -f http://localhost:9083/new || exit 1"]})
    themis = e.image("themis:prod", Env=["PATH=/usr/local/bin:/usr/bin:/bin"], Cmd=["python", "agent.py"],
                     ExposedPorts={"8080/tcp": {}}, Healthcheck={"Test": ["CMD", "python", "-c", "probe"]})
    hub = e.run("modelmarket-hub", old,
                {"NetworkMode": "aicom_aicom_net", "RestartPolicy": {"Name": "unless-stopped"},
                 "PortBindings": {"9083/tcp": [{"HostIp": "127.0.0.1", "HostPort": "9083"}],
                                  "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "9460"}]},
                 "Binds": ["hub_data:/app/data:rw"]},
                networks=("aicom_aicom_net", "bridge"),
                Env=["AIMARKET_HUB_NAME=main", "AIMARKET_ADMIN_TOKEN=s3cret-admin-token"],
                Labels={"aicom.role": "hub"}, ExposedPorts={"8080/tcp": {}})
    # Docker reports the joined container's hostname for a container: borrower.
    e.run("themis", themis, {"NetworkMode": "container:" + hub, "RestartPolicy": {"Name": "unless-stopped"},
                             "Binds": ["themis_data:/data:rw"]}, Env=["HOST=0.0.0.0"])
    e.find("themis")["Config"]["Hostname"] = hub[:12]
    return e


@pytest.fixture
def rollout(monkeypatch, tmp_path, engine):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("rollout_under_test", SCRIPTS / "rollout_container.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "api", engine)
    monkeypatch.setattr(module, "health", engine.health)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    # Snapshots go to a temp dir instead of /root/security-rollbacks.
    backups = tmp_path / "rollbacks"
    real_path = module.Path
    monkeypatch.setattr(module, "Path", lambda *a: backups if a == ("/root/security-rollbacks",) else real_path(*a))
    monkeypatch.setattr(module, "ROLLBACK_ROOT", backups, raising=False)
    module.backups = backups
    return module


def run(rollout, monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["rollout_container.py", *argv])
    return rollout.main()


HUB_ARGS = ("modelmarket-hub", "--health", HUB_URL, "--health", THEMIS_URL)


def test_namespace_borrower_moves_into_the_new_container(rollout, engine, monkeypatch, capsys):
    old_hub, old_themis = engine.named("modelmarket-hub")["Id"], engine.named("themis")["Id"]
    run(rollout, monkeypatch, *HUB_ARGS)
    hub, themis = engine.named("modelmarket-hub"), engine.named("themis")
    assert hub["Id"] != old_hub and themis["Id"] != old_themis
    assert themis["HostConfig"]["NetworkMode"] == "container:" + hub["Id"]
    assert engine.reachable(), "THEMIS must live in the namespace of the hub that is running now"
    # The hub still publishes THEMIS's port and keeps its volumes and restart policy.
    assert hub["HostConfig"]["PortBindings"]["8080/tcp"][0]["HostPort"] == "9460"
    assert themis["HostConfig"]["Binds"] == ["themis_data:/data:rw"]
    assert themis["HostConfig"]["RestartPolicy"] == {"Name": "unless-stopped"}
    prev = [c for c in engine.containers.values() if c["Name"].startswith("/themis-security-prev-")]
    assert len(prev) == 1 and prev[0]["Id"] == old_themis and not prev[0]["State"]["Running"]
    out = json.loads(capsys.readouterr().out)
    assert out["healthy"] is True and list(out["borrowers"]) == ["themis"]


def test_rollback_restarts_the_borrower_inside_the_restored_namespace(rollout, engine, monkeypatch):
    engine.broken_images.add(engine.image("modelmarket-hub:new"))
    old_hub, old_themis = engine.named("modelmarket-hub")["Id"], engine.named("themis")["Id"]
    with pytest.raises(RuntimeError, match="Health check failed"):
        run(rollout, monkeypatch, *HUB_ARGS, "--image", "modelmarket-hub:new")
    assert engine.named("modelmarket-hub")["Id"] == old_hub
    assert engine.named("themis")["Id"] == old_themis
    assert engine.reachable(), "a restored hub has a fresh namespace; THEMIS must be in it"
    assert engine.names() == ["modelmarket-hub", "themis"]


def test_rollback_continues_past_a_candidate_that_will_not_delete(rollout, engine, monkeypatch, capsys):
    engine.broken_images.add(engine.image("modelmarket-hub:new"))
    engine.fail_on |= {("DELETE", "delete", "modelmarket-hub"), ("DELETE", "delete", "themis")}
    old_hub = engine.named("modelmarket-hub")["Id"]
    # The original failure is what surfaces, not the failed clean-up.
    with pytest.raises(RuntimeError, match="Health check failed"):
        run(rollout, monkeypatch, *HUB_ARGS, "--image", "modelmarket-hub:new")
    hub = engine.named("modelmarket-hub")
    assert hub["Id"] == old_hub and hub["State"]["Running"]
    assert engine.reachable()
    failed = [c for c in engine.containers.values() if "-failed-" in c["Name"]]
    assert len(failed) == 2 and not any(c["State"]["Running"] for c in failed)
    report = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert report["rolled_back"] is False and len(report["rollback_errors"]) == 2


def test_failure_before_anything_stops_leaves_the_originals_running(rollout, engine, monkeypatch):
    before = {c["Id"] for c in engine.containers.values()}
    original_call = Engine.__call__

    def create_fails_for_themis(self, method, path, body=None):
        if method == "POST" and "create?name=themis-candidate-" in path:
            raise RuntimeError("Docker POST /containers/create failed: HTTP 500")
        return original_call(self, method, path, body)

    monkeypatch.setattr(Engine, "__call__", create_fails_for_themis)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        run(rollout, monkeypatch, *HUB_ARGS)
    assert {c["Id"] for c in engine.containers.values()} == before
    assert engine.reachable()
    assert not any(m == "POST" and p.endswith("/stop?t=30") for m, p in engine.calls)


def test_new_image_supplies_its_own_defaults_and_choices_survive(rollout, engine, monkeypatch):
    hub = engine.named("modelmarket-hub")
    # Choices made at run time: an override of an image variable and a user.
    hub["Config"]["Env"] = [e for e in hub["Config"]["Env"] if not e.startswith("LANG=")] + ["LANG=ru_RU.UTF-8"]
    hub["Config"]["User"] = "1000"
    run(rollout, monkeypatch, "modelmarket-hub", "--health", HUB_URL, "--image", "modelmarket-hub:new")
    new = engine.named("modelmarket-hub")["Config"]
    env = dict(e.partition("=")[::2] for e in new["Env"])
    assert env["PATH"] == "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin"
    assert env["PYTHON_VERSION"] == "3.13.1"
    assert env["LANG"] == "ru_RU.UTF-8" and new["User"] == "1000"
    assert env["AIMARKET_ADMIN_TOKEN"] == "s3cret-admin-token"
    assert new["Entrypoint"] == ["python", "-m", "aimarket_hub", "serve", "--new"]
    assert new["WorkingDir"] == "/srv"
    assert new["Healthcheck"]["Test"][-1].endswith("/new || exit 1")
    assert new["Labels"] == {"org.opencontainers.image.version": "new", "aicom.role": "hub"}


def test_explicit_cmd_survives_a_new_image(rollout, engine, monkeypatch):
    engine.named("modelmarket-hub")["Config"]["Cmd"] = ["--workers", "4"]
    run(rollout, monkeypatch, "modelmarket-hub", "--health", HUB_URL, "--image", "modelmarket-hub:new")
    new = engine.named("modelmarket-hub")["Config"]
    assert new["Entrypoint"] == ["python", "-m", "aimarket_hub", "serve", "--new"]
    assert new["Cmd"] == ["--workers", "4"]


def test_explicit_hostname_and_tmpfs_mounts_survive(rollout, engine, monkeypatch):
    img = engine.image("atlas:prod", Env=["PATH=/usr/bin"], Cmd=["atlas"])
    cid = engine.run("atlas", img, {"NetworkMode": "atlas_net", "RestartPolicy": {"Name": "always"},
                                    "Binds": ["atlas_data:/data:rw"],
                                    "Mounts": [{"Type": "tmpfs", "Target": "/run/secrets-scratch",
                                                "TmpfsOptions": {"SizeBytes": 1048576}}]},
                     networks=("atlas_net",), Hostname="atlas-node")
    assert engine.find(cid)["Config"]["Hostname"] == "atlas-node"
    run(rollout, monkeypatch, "atlas", "--health", ATLAS_URL)
    body = next(b for n, b in engine.bodies.items() if n.startswith("atlas-candidate-"))
    assert body["Hostname"] == "atlas-node"
    assert body["HostConfig"]["Mounts"] == [{"Type": "tmpfs", "Target": "/run/secrets-scratch",
                                             "TmpfsOptions": {"SizeBytes": 1048576}}]
    assert body["HostConfig"]["Binds"] == ["atlas_data:/data:rw"]


def test_docker_assigned_hostnames_are_not_carried_over(rollout, engine, monkeypatch):
    run(rollout, monkeypatch, *HUB_ARGS)
    bodies = {n.split("-candidate-")[0]: b for n, b in engine.bodies.items() if "-candidate-" in n}
    # The hub's is its short ID; THEMIS's is the hub's, which Docker refuses to be given.
    assert "Hostname" not in bodies["modelmarket-hub"]
    assert "Hostname" not in bodies["themis"]


def test_dry_run_prints_the_plan_and_changes_nothing(rollout, engine, monkeypatch, capsys):
    before = copy.deepcopy(engine.containers)
    run(rollout, monkeypatch, *HUB_ARGS, "--image", "modelmarket-hub:new", "--dry-run")
    assert {m for m, _ in engine.calls} == {"GET"}
    assert engine.containers == before
    assert not rollout.backups.exists()
    stdout = capsys.readouterr().out
    assert "s3cret-admin-token" not in stdout
    plan = json.loads(stdout)
    assert plan["dry_run"] is True and plan["borrowers"] == ["themis"]
    commands = plan["commands"]
    for step in ("docker stop -t 30 themis", "docker stop -t 30 modelmarket-hub",
                 "docker start modelmarket-hub", "docker start themis",
                 f"wait for {THEMIS_URL} to answer 200"):
        assert step in commands
    assert commands.index("docker stop -t 30 themis") < commands.index("docker stop -t 30 modelmarket-hub")
    assert "AIMARKET_ADMIN_TOKEN=<redacted>" in plan["create"]["modelmarket-hub"]["Env"]
    assert "PATH" in plan["image_env_names"]
    assert plan["create"]["themis"]["HostConfig"]["NetworkMode"].startswith("container:modelmarket-hub-candidate-")
