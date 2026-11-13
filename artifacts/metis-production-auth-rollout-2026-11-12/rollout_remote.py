#!/usr/bin/env python3
"""Deploy three production auth modules over the current Metis image."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import previous_rollout as base

REVISION = "f1c579ab4"
MODULES = {
    "api/auth.py": (
        "623d70f6ae4220010c12ea1523993a82eabc84ea8dbf6e207b675459e49a3434",
        "459baab900986a12098a62f2c8c3ce70479646b0d3cd229fc764530fa3c3b70d",
    ),
    "coordinator_server.py": (
        "d4bbec047001efb2cd10895a1804893c35f280d7da1c07024ab2d19288100efb",
        "76455f23fbb8e67cd5bad38013a274479193a8ecb5fa2c1dea2555e7ee4fc21e",
    ),
    "distributed/server.py": (
        "dd4f5379bba9bf6896b40a98546517359e8bd03a2159dbbb4ed1db5ac3350ed3",
        "3d647b7127296b4e22bc8bb04e026ac068d2b1945dbf030760b8534938a1dadb",
    ),
}
TARGETS = {
    "metis": (
        "sha256:9cd20af791953d54f4a9dbe1ad4a48def535c06524e1e040d9fa43ca311ffca4",
        "https://metis.modelmarket.dev",
    ),
    "metis-appeal": (
        "sha256:c19f324fb9679feb86d6c964164ab1ad7094bd05ae2305212973bd2637d280c3",
        "https://attestedmemory.net/metis-appeal",
    ),
}
MODULE_ROOT = "/usr/local/lib/python3.11/site-packages/metis"
AUTH_PROBE = r"""
import asyncio
import os
import tempfile
from pathlib import Path

from httpx import ASGITransport, AsyncClient

for key in (
    "METIS_API_KEY", "SUPERBRAIN_API_KEY", "COGNITIVE_API_KEY",
    "METIS_PRODUCTION", "SUPERBRAIN_PRODUCTION", "COGNITIVE_PRODUCTION",
    "AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_ENV", "METIS_CONFIG_PATH",
):
    os.environ.pop(key, None)
os.environ["METIS_LOCAL_RELAY"] = "1"
os.environ["METIS_LOCAL_UNVERIFIED"] = "1"
os.environ["METIS_WEB_SEARCH_URL"] = "https://1.1.1.1/html/"

from metis.api import auth
from metis.api.app import create_app
from metis.config import ProviderKind, RuntimeConfig
from metis.coordinator_server import create_coordinator_app
from metis.distributed.server import create_app as create_worker_app

auth._PROC_NET_TCP = ()

async def status(app, method, path, **kwargs):
    transport = ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        return (await client.request(method, path, **kwargs)).status_code

async def verify():
    with tempfile.TemporaryDirectory() as temp:
        def config(production):
            return RuntimeConfig(production=production, provider=ProviderKind.MOCK,
                                 allow_test_provider=True, memory_dir=Path(temp) / "memory")

        assert await status(create_app(config(False)), "GET", "/v1/models") == 200
        assert await status(create_app(config(True)), "GET", "/v1/models") == 401
        assert await status(create_coordinator_app(config=config(True)), "GET", "/v1/models") == 401
        os.environ["METIS_PRODUCTION"] = "false"
        os.environ["AIFACTORY_PROD"] = "1"
        assert await status(create_coordinator_app(config=config(False)), "POST", "/v1/query",
                            json={"query": "rollout probe"}) == 500
        assert await status(create_worker_app(), "POST", "/metis/invoke", content=b"{}") == 500

asyncio.run(verify())
"""


def module_hashes(name, updated):
    command = (
        "import hashlib,importlib.util,json,pathlib,sys;"
        "out={p:(pathlib.Path(importlib.util.find_spec('metis.'+p[:-3].replace('/','.')).origin)) "
        "for p in sys.argv[1:]};"
        "print(json.dumps({k:[str(p),hashlib.sha256(p.read_bytes()).hexdigest()] for k,p in out.items()}))"
    )
    result = base.run(["docker", "exec", name, "python", "-c", command, *MODULES])
    modules = json.loads(result.stdout)
    if any(modules[path] != [f"{MODULE_ROOT}/{path}", hashes[updated]]
           for path, hashes in MODULES.items()):
        raise RuntimeError("Metis module origin or SHA-256 mismatch")
    return {path: entry[1] for path, entry in modules.items()}


def prepare(name, root, image, external, canary, tag):
    old = base.inspect(name)
    if old["Image"] != image or not old["State"]["Running"]:
        raise RuntimeError("Live image drift")
    if (root / "old-inspect.private.json").exists():
        raise RuntimeError("This rollout root already has a snapshot")
    module_hashes(name, updated=False)
    before = base.external(external, auth_key=base.expected_key(old))
    old_probe = base.probe(name)
    if not base.expected_key(old):
        raise RuntimeError("Live bearer key is missing")
    data = base.data_source(old)
    required = 2 * sum(p.stat().st_size for p in data.rglob("*") if p.is_file()) + 256 * 1024**2
    if shutil.disk_usage(root).free < required or shutil.disk_usage("/var/lib/docker").free < required:
        raise RuntimeError("Insufficient space for the image overlay and rollback data")
    base.save_private(root / "old-inspect.private.json", old)
    baseline_tag = f"{name}:rollout-base-{image.split(':')[1][:16]}"
    base.run(["docker", "tag", image, baseline_tag])
    if base.inspect(baseline_tag)["Id"] != image:
        raise RuntimeError("Baseline image tag identity mismatch")
    copies = []
    for path, hashes in MODULES.items():
        relative = f"metis/metis/{path}"
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != hashes[1]:
            raise RuntimeError("Source transfer SHA-256 mismatch")
        copies.append(f"COPY {relative} {MODULE_ROOT}/{path}")
    dockerfile = [f"FROM {baseline_tag}", *copies]
    (root / "Dockerfile").write_text("\n".join(dockerfile) + "\n")
    (root / ".dockerignore").write_text("*\n!Dockerfile\n!metis/\n!metis/metis/\n!metis/metis/**\n")
    build = base.run(["docker", "build", "--network=none", "--pull=false", "-t", tag, str(root)],
                     ok=False, env={**os.environ, "DOCKER_BUILDKIT": "0"})
    build_log = root / "build.private.log"
    build_log.write_text(build.stdout + "\n" + build.stderr)
    build_log.chmod(0o600)
    if build.returncode:
        raise RuntimeError("Derived image build failed; private remote log retained")
    new_image = base.inspect(tag)["Id"]
    base.emit("built", name=name, revision=REVISION, baseline=image, candidate=new_image)
    statecopy = root / "canary-data"
    base.clone_data(data, statecopy, consistent_sqlite=True)
    try:
        base.api("POST", "/containers/create?name=" + canary,
                 base.payload(old, new_image, canary=True, data_copy=statecopy))
        base.run(["docker", "start", canary])
        probe = base.probe(canary)
        hashes = module_hashes(canary, updated=True)
        base.run(["docker", "exec", canary, "python", "-c", AUTH_PROBE])
        if probe["knowledge_entries"] != before["knowledge_entries"]:
            raise RuntimeError("Canary knowledge count differs from baseline")
        receipt = {"name": name, "revision": REVISION, "old_image": image, "new_image": new_image,
                   "before": before, "baseline_probe": old_probe, "canary": probe,
                   "module_sha256": hashes, "production_auth_regression": "passed", "prepared": True}
        base.save_private(root / "receipt.sanitized.json", receipt)
        base.emit("canary_pass", **receipt)
    finally:
        base.run(["docker", "rm", "-f", canary], ok=False)


def promote(name, root, image, external, rollback):
    old = json.loads((root / "old-inspect.private.json").read_text())
    receipt_path = root / "receipt.sanitized.json"
    receipt = json.loads(receipt_path.read_text())
    current = base.inspect(name)
    if (not receipt.get("prepared") or receipt.get("promoted") or current["Id"] != old["Id"]
            or current["Image"] != image or not current["State"]["Running"]):
        raise RuntimeError("Prepared target or live identity drift")
    base.audit_runtime(old, current)
    if base.run(["docker", "container", "inspect", rollback], ok=False).returncode == 0:
        raise RuntimeError("Rollback container name already exists")
    stopped = renamed = replacement = False
    disconnected = []
    try:
        base.run(["docker", "stop", "--time", "30", name])
        stopped = True
        base.clone_data(base.data_source(old), root / "production-data-before")
        for network in old["NetworkSettings"]["Networks"]:
            base.run(["docker", "network", "disconnect", network, name])
            disconnected.append(network)
        base.run(["docker", "rename", name, rollback])
        renamed = True
        base.api("POST", "/containers/create?name=" + name, base.payload(old, receipt["new_image"]))
        replacement = True
        base.run(["docker", "start", name])
        probe = base.probe(name)
        hashes = module_hashes(name, updated=True)
        preservation = base.audit_runtime(old, base.inspect(name))
        public = base.external(external, auth_key=base.expected_key(old))
        if probe["knowledge_entries"] < receipt["before"]["knowledge_entries"]:
            raise RuntimeError("Promoted knowledge count is lower than baseline")
        for _ in range(24):
            health = base.inspect(name)["State"].get("Health", {}).get("Status")
            if health == "healthy":
                break
            time.sleep(2)
        else:
            raise RuntimeError("Promoted Docker healthcheck did not become healthy")
        receipt.update(promoted=True, production=probe, external=public, preservation=preservation,
                       module_sha256=hashes, docker_health=health, rollback_container=rollback,
                       data_backup_present=(root / "production-data-before").is_dir())
        base.save_private(receipt_path, receipt)
        base.emit("promoted", **receipt)
    except Exception:
        if replacement:
            base.run(["docker", "rm", "-f", name])
        if renamed:
            base.run(["docker", "rename", rollback, name])
        if stopped:
            for network in disconnected:
                settings = base.endpoints(old, static=True)[network]
                base.api("POST", "/networks/" + network + "/connect",
                         {"Container": name, "EndpointConfig": settings})
            base.run(["docker", "start", name])
        base.emit("rolled_back", name=name, old_image=image)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "promote"))
    parser.add_argument("name", choices=TARGETS)
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    image, external = TARGETS[args.name]
    if args.action == "prepare":
        prepare(args.name, root, image, external,
                f"{args.name}-canary-{REVISION}", f"{args.name}:0.2.6-local-{REVISION}")
    else:
        promote(args.name, root, image, external, f"{args.name}-rollback-{REVISION}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        base.emit("error", reason=str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        base.emit("error", error_type=type(exc).__name__)
        raise SystemExit(1) from None
