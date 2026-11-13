#!/usr/bin/env python3
"""Canary and promote only the three METIS provider telemetry modules."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time

import previous_rollout as base
from previous_tavily_rollout import AUTH_PROBE

BASELINE = "sha256:8c4d597c6a8951a92490f1fc2ed68a28567d47dca79c5b9e1c0e386874416ee3"
NAME = "metis"
PUBLIC = "https://metis.modelmarket.dev"
TAG = "metis:0.2.6-local-provider-events-20261113"
CANARY = "metis-canary-provider-events-20261113"
ROLLBACK = "metis-rollback-provider-events-20261113"
MODULE_ROOT = "/usr/local/lib/python3.11/site-packages/metis"
MODULES = {
    "exoskeleton.py": (
        "de792247ed8732778dcb2b9bb02eaf8408888738eeaad5350492a2767da51613",
        "ddcbc2e5aa68e7a39df334ef3a1c2d3bff79ff3b9b9762ca4bdaf44f53c4f8c9",
    ),
    "tools/registry.py": (
        "7ccf1097ecb3d3ce39c3f5c675a005c5fca09638f0437b67d2587174c3449b20",
        "15d00495966258fad4adc5f86963ac130efadb82925de6f364cd9aaddb02a96d",
    ),
    "observability/provider_events.py": (
        None,
        "790f98b19b324ed8f76f60ce16f2bbae480ded276de1f4c51d7b6573a3a71b53",
    ),
}

OFFLINE = r"""
import asyncio
import json
from uuid import UUID
from unittest.mock import AsyncMock, patch

import httpx
from metis.config import RuntimeConfig
from metis.exoskeleton import Metis
from metis.tools import registry as search

async def main():
    runtime = Metis.__new__(Metis)
    runtime.config = RuntimeConfig(_env_file=None, web_search_provider="tavily",
                                   web_search_url="https://93.184.216.34/html/")
    tools = runtime._build_builtin_tools()
    url = search.TavilySearchTool.url
    fallback = runtime.config.web_search_url
    provider = AsyncMock(side_effect=[
        httpx.Response(200, request=httpx.Request("POST", url), json={"results":[]}),
        httpx.Response(429, request=httpx.Request("POST", url)),
        httpx.Response(200, request=httpx.Request("POST", fallback),
                       text='<a class="result__snippet">Fallback</a>'),
    ])
    events = []
    async def capture(request):
        assert str(request.url) == "https://monitor.invalid/api/provider-events"
        assert request.headers["Authorization"] == "Bearer canary-scoped-token"
        event = json.loads(request.content)
        assert UUID(event.pop("event_id")).version == 4
        events.append(event)
        return httpx.Response(204)
    client = httpx.AsyncClient
    def offline_client(**kwargs):
        assert kwargs["follow_redirects"] is False
        return client(transport=httpx.MockTransport(capture), **kwargs)
    with patch.object(search, "safe_post", provider), patch.object(httpx, "AsyncClient", offline_client):
        assert not (await tools.execute("web_search", " ")).success
        assert (await tools.execute("web_search", "Private query")).success
        assert "DuckDuckGo" in (await tools.execute("web_search", "Private fallback query")).output
        await asyncio.sleep(0)
    assert events == [
        {"provider":"tavily", "source":"metis", "operation":"search", "status":status}
        for status in ("succeeded", "failed")
    ]
    print(json.dumps({"mode":"network-disabled fixture", "events":events, "redaction":"passed"}))

asyncio.run(main())
"""


def module_hashes(name, updated):
    command = (
        "import hashlib,json,sys;from pathlib import Path;import metis;"
        "root=Path(metis.__file__).parent;"
        "print(json.dumps([str(root),{name:hashlib.sha256((root/name).read_bytes()).hexdigest()"
        " if (root/name).exists() else None for name in sys.argv[1:]}]))"
    )
    root, hashes = json.loads(base.run(["docker", "exec", name, "python", "-c", command, *MODULES]).stdout)
    if root != MODULE_ROOT or hashes != {name: values[updated] for name, values in MODULES.items()}:
        raise RuntimeError("METIS module origin or SHA-256 mismatch")
    return hashes


def monitor_env(old, root):
    configured = {entry.split("=", 1)[0] for entry in old["Config"].get("Env", [])}
    names = {"ALIEN_MONITOR_URL", "ALIEN_PROVIDER_EVENTS_TOKEN"}
    if configured.intersection(names):
        raise RuntimeError("METIS provider telemetry settings already exist")
    path = root / "monitor-token.private"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("METIS requires a private root-owned scoped token")
    token = path.read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{32,256}", token):
        raise RuntimeError("METIS scoped token is invalid")
    return ["ALIEN_MONITOR_URL=https://monitor.modelmarket.dev", f"ALIEN_PROVIDER_EVENTS_TOKEN={token}"]


def prepare(root):
    old = base.inspect(NAME)
    if old["Image"] != BASELINE or not old["State"]["Running"]:
        raise RuntimeError("Live METIS image drift")
    snapshot = root / "old-inspect.private.json"
    if snapshot.exists():
        saved = json.loads(snapshot.read_text())
        if saved["Id"] != old["Id"] or (root / "receipt.sanitized.json").exists():
            raise RuntimeError("METIS canary already completed or its baseline changed")
        base.audit_runtime(saved, old)
    module_hashes(NAME, updated=False)
    before = base.external(PUBLIC, auth_key=base.expected_key(old))
    data = base.data_source(old)
    required = 2 * sum(p.stat().st_size for p in data.rglob("*") if p.is_file()) + 256 * 1024**2
    if any(shutil.disk_usage(path).free < required for path in (root, "/var/lib/docker")):
        raise RuntimeError("Insufficient space for the image overlay and rollback data")
    if not snapshot.exists():
        base.save_private(snapshot, old)
    baseline_tag = "metis:rollout-base-" + BASELINE[7:23]
    base.run(["docker", "tag", BASELINE, baseline_tag])
    if base.inspect(baseline_tag)["Id"] != BASELINE:
        raise RuntimeError("Baseline image tag identity mismatch")
    copies = []
    for module, (_, expected) in MODULES.items():
        relative = f"metis/metis/{module}"
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError("METIS source transfer SHA-256 mismatch")
        copies.append(f"COPY {relative} {MODULE_ROOT}/{module}")
    (root / "Dockerfile").write_text("\n".join([f"FROM {baseline_tag}", *copies]) + "\n")
    (root / ".dockerignore").write_text("*\n!Dockerfile\n!metis/\n!metis/metis/\n!metis/metis/**\n")
    build = base.run(["docker", "build", "--network=none", "--pull=false", "-t", TAG, str(root)],
                     ok=False, env={**os.environ, "DOCKER_BUILDKIT": "0"})
    (root / "build.private.log").write_text(build.stdout + "\n" + build.stderr)
    if build.returncode:
        raise RuntimeError("METIS image build failed")
    image = base.inspect(TAG)["Id"]
    base.emit("built", image=image, baseline=BASELINE)
    offline = base.run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
                        "-e", "ALIEN_MONITOR_URL=https://monitor.invalid", "-e",
                        "ALIEN_PROVIDER_EVENTS_TOKEN=canary-scoped-token", image, "-c", OFFLINE])
    statecopy = root / "canary-data"
    if statecopy.exists():
        shutil.rmtree(statecopy)
    base.clone_data(data, statecopy, consistent_sqlite=True)
    try:
        base.api("POST", "/containers/create?name=" + CANARY, base.payload(old, image, canary=True, data_copy=statecopy))
        base.run(["docker", "start", CANARY])
        check = base.probe(CANARY)
        if check["knowledge_entries"] != before["knowledge_entries"]:
            raise RuntimeError("Canary knowledge differs from baseline")
        hashes = module_hashes(CANARY, updated=True)
        base.run(["docker", "exec", CANARY, "python", "-c", AUTH_PROBE])
        receipt = {"old_image": BASELINE, "new_image": image, "before": before,
                   "canary": check, "module_sha256": hashes, "offline": json.loads(offline.stdout.splitlines()[-1]),
                   "production_auth_regression": "passed", "prepared": True}
        base.save_private(root / "receipt.sanitized.json", receipt)
        base.emit("canary_pass", **receipt)
    finally:
        base.run(["docker", "rm", "-f", CANARY], ok=False)


def promote(root):
    old = json.loads((root / "old-inspect.private.json").read_text())
    receipt_path = root / "receipt.sanitized.json"
    receipt = json.loads(receipt_path.read_text())
    current = base.inspect(NAME)
    if (not receipt.get("prepared") or receipt.get("promoted") or current["Id"] != old["Id"]
            or current["Image"] != BASELINE or not current["State"]["Running"]):
        raise RuntimeError("Prepared METIS target or live identity drift")
    base.audit_runtime(old, current)
    if base.run(["docker", "container", "inspect", ROLLBACK], ok=False).returncode == 0:
        raise RuntimeError("METIS rollback container name already exists")
    additions = monitor_env(old, root)
    payload = base.payload(old, receipt["new_image"])
    payload["Env"] = [*(payload.get("Env") or []), *additions]
    stopped = renamed = replacement = False
    disconnected = []
    try:
        base.run(["docker", "stop", "--time", "30", NAME])
        stopped = True
        base.clone_data(base.data_source(old), root / "production-data-before")
        for network in old["NetworkSettings"]["Networks"]:
            base.run(["docker", "network", "disconnect", network, NAME])
            disconnected.append(network)
        base.run(["docker", "rename", NAME, ROLLBACK])
        renamed = True
        base.api("POST", "/containers/create?name=" + NAME, payload)
        replacement = True
        base.run(["docker", "start", NAME])
        probe = base.probe(NAME)
        hashes = module_hashes(NAME, updated=True)
        check = base.inspect(NAME)
        if (check["Config"].get("Env") or []) != payload["Env"]:
            raise RuntimeError("Expected scoped METIS environment additions were not applied")
        comparable = copy.deepcopy(check)
        comparable["Config"]["Env"] = old["Config"].get("Env")
        preserved = base.audit_runtime(old, comparable)
        public = base.external(PUBLIC, auth_key=base.expected_key(old))
        if probe["knowledge_entries"] < receipt["before"]["knowledge_entries"]:
            raise RuntimeError("METIS knowledge count declined after promotion")
        for _ in range(24):
            health = base.inspect(NAME)["State"].get("Health", {}).get("Status")
            if health == "healthy":
                break
            time.sleep(2)
        else:
            raise RuntimeError("Promoted METIS healthcheck did not become healthy")
        receipt.update(promoted=True, production=probe, external=public, preservation=preserved,
                       module_sha256=hashes, docker_health=health, rollback_container=ROLLBACK,
                       environment_additions=[item.split("=", 1)[0] for item in additions])
        base.save_private(receipt_path, receipt)
        base.emit("promoted", **receipt)
    except Exception:
        if replacement:
            base.run(["docker", "rm", "-f", NAME])
        if renamed:
            base.run(["docker", "rename", ROLLBACK, NAME])
        if stopped:
            for network in disconnected:
                settings = base.endpoints(old, static=True)[network]
                base.api("POST", "/networks/" + network + "/connect",
                         {"Container": NAME, "EndpointConfig": settings})
            base.run(["docker", "start", NAME])
        base.emit("rolled_back", name=NAME, old_image=BASELINE)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "promote"))
    args = parser.parse_args()
    os.umask(0o077)
    try:
        (prepare if args.action == "prepare" else promote)(Path(__file__).resolve().parent)
    except RuntimeError as exc:
        base.emit("error", reason=str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        base.emit("error", error_type=type(exc).__name__)
        raise SystemExit(1) from None
