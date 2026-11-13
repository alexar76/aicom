#!/usr/bin/env python3
"""Roll out the Tavily web-search provider over the current production Metis image."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import previous_rollout as base

REVISION = "d6a77ce9f-tavily-fallback"
MODULES = {
    "config.py": (
        "18e98d2a9f768cd161b7ae8a1db2a431449b1cb386c94ab026a50c1a78f70cf5",
        "a4be4649f258b0bcf92baa6f9340ea14115dd54fbdd9c969b31dfdaa72bb5c71",
    ),
    "exoskeleton.py": (
        "7afac73031d943360b56a4de94c34cd0a3ad49195e7436c9002c6f5131ed7086",
        "de792247ed8732778dcb2b9bb02eaf8408888738eeaad5350492a2767da51613",
    ),
    "security/ssrf.py": (
        "9edbe59cb5ab3fc0116747a61d273fd5549a6d0dc884973d9e95bdd2eeed633c",
        "01f6e6afc11b0c8e40c4d2a570fbd90cf3eeea7129db4ef44d22d8970fcca25d",
    ),
    "tools/registry.py": (
        "cde1fa1cfb1e58f388a14bc89e305b2a197196f0842a30f18595624809971c88",
        "7ccf1097ecb3d3ce39c3f5c675a005c5fca09638f0437b67d2587174c3449b20",
    ),
}
AUTH_MODULES = {
    "api/auth.py": "459baab900986a12098a62f2c8c3ce70479646b0d3cd229fc764530fa3c3b70d",
    "coordinator_server.py": "76455f23fbb8e67cd5bad38013a274479193a8ecb5fa2c1dea2555e7ee4fc21e",
    "distributed/server.py": "3d647b7127296b4e22bc8bb04e026ac068d2b1945dbf030760b8534938a1dadb",
}
TARGETS = {
    "metis": (
        "sha256:a8c1412a7925813027ac9fc4715859142f1a7a1aa004d4296969ef1f0843019e",
        "https://metis.modelmarket.dev",
    ),
}
SEARCH_ENV = "METIS_WEB_SEARCH_PROVIDER=tavily"
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
    result = base.run(["docker", "exec", name, "python", "-c", command, *MODULES, *AUTH_MODULES])
    modules = json.loads(result.stdout)
    if any(modules[path] != [f"{MODULE_ROOT}/{path}", hashes[updated]]
           for path, hashes in MODULES.items()):
        raise RuntimeError("Metis module origin or SHA-256 mismatch")
    if any(modules[path] != [f"{MODULE_ROOT}/{path}", digest] for path, digest in AUTH_MODULES.items()):
        raise RuntimeError("Previously deployed authorization module changed")
    return {path: entry[1] for path, entry in modules.items()}


SEARCH_PROBE = r"""
import asyncio
import json
from urllib.parse import urlsplit
from unittest.mock import patch

import httpx

from metis.config import RuntimeConfig
from metis.exoskeleton import Metis
from metis.tools import registry as search_tools

async def verify():
    runtime = Metis.__new__(Metis)
    runtime.config = RuntimeConfig.from_yaml('/app/config/prod.yaml')
    assert runtime.config.enable_web_search and runtime.config.web_search_provider == 'tavily'
    registry = runtime._build_builtin_tools()
    assert 'web_search' in registry.names()
    query = 'RFC 9110 status code 402 HTTP semantics'
    result = await registry.execute('web_search', query)
    actual_provider = 'duckduckgo' if 'Search provider: DuckDuckGo' in result.output else 'tavily'
    links = [line.strip() for line in result.output.splitlines() if line.strip().startswith('https://')]
    snippets = sum(line.startswith('- ') for line in result.output.splitlines())
    assert result.success and snippets and all(urlsplit(url).hostname for url in links)
    assert actual_provider != 'tavily' or links

    real_post = search_tools.safe_post

    async def simulate_tavily_quota(url, **kwargs):
        if url == search_tools.TavilySearchTool.url:
            return httpx.Response(429, request=httpx.Request('POST', url))
        return await real_post(url, **kwargs)

    with patch.object(search_tools, 'safe_post', simulate_tavily_quota):
        fallback = await registry.execute('web_search', query)
    fallback_snippets = sum(line.startswith('- ') for line in fallback.output.splitlines())
    assert fallback.success and 'Search provider: DuckDuckGo' in fallback.output and fallback_snippets
    print(json.dumps({'tool': result.name, 'provider': runtime.config.web_search_provider,
                      'actual_provider': actual_provider, 'result_count': snippets,
                      'key_configured': bool(runtime.config.tavily_api_key),
                      'result_hosts': sorted({urlsplit(url).hostname for url in links}),
                      'forced_429_live_fallback_results': fallback_snippets}))

asyncio.run(verify())
"""


def tavily_payload(old, image, **kwargs):
    payload = base.payload(old, image, **kwargs)
    environment = payload.get('Env') or []
    if any(value.startswith('METIS_WEB_SEARCH_PROVIDER=') for value in environment):
        raise RuntimeError('Existing environment provider setting would be overwritten')
    payload['Env'] = [*environment, SEARCH_ENV]
    return payload


def preservation_check(old, current):
    expected = old['Config'].get('Env') or []
    if (current['Config'].get('Env') or []) != [*expected, SEARCH_ENV]:
        raise RuntimeError('Tavily setting was not the only environment change')
    comparable = copy.deepcopy(current)
    comparable['Config']['Env'] = old['Config'].get('Env')
    return {**base.audit_runtime(old, comparable), 'only_environment_addition': SEARCH_ENV}


def search_probe(name):
    result = base.run(['docker', 'exec', name, 'python', '-c', SEARCH_PROBE], ok=False)
    if result.returncode:
        raise RuntimeError('The configured web_search tool or the forced quota fallback did not return live results')
    payload = json.loads(result.stdout.splitlines()[-1])
    if payload['provider'] != 'tavily' or not payload['result_count']:
        raise RuntimeError('Missing live Tavily results')
    return payload


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
                 tavily_payload(old, new_image, canary=True, data_copy=statecopy))
        base.run(["docker", "start", canary])
        probe = base.probe(canary)
        hashes = module_hashes(canary, updated=True)
        search = search_probe(canary)
        base.run(["docker", "exec", canary, "python", "-c", AUTH_PROBE])
        if probe["knowledge_entries"] != before["knowledge_entries"]:
            raise RuntimeError("Canary knowledge count differs from baseline")
        receipt = {"name": name, "revision": REVISION, "old_image": image, "new_image": new_image,
                   "before": before, "baseline_probe": old_probe, "canary": probe,
                   "module_sha256": hashes, "canary_search": search, "production_auth_regression": "passed", "prepared": True}
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
        base.api("POST", "/containers/create?name=" + name, tavily_payload(old, receipt["new_image"]))
        replacement = True
        base.run(["docker", "start", name])
        probe = base.probe(name)
        hashes = module_hashes(name, updated=True)
        preservation = preservation_check(old, base.inspect(name))
        search = search_probe(name)
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
                       module_sha256=hashes, production_search=search, docker_health=health, rollback_container=rollback,
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
