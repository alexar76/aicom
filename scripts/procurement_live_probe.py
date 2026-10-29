#!/usr/bin/env python3
"""Exercise procurement over real HTTPS and a real configured OpenRouter model.

The Hub/provider run on loopback with disposable databases and a temporary TLS identity.
Credits here are TEST grants, not production money. Only the remote model call is billed.
The remote factory's key stays in its container. No production config or catalogue changes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import socket
import ssl
import sys
import tempfile
import textwrap
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "aimarket-hub")]

# Executed inside the existing factory container. Reads configuration but never prints keys.
MODEL_CALL = r'''
import json, os, sys
import httpx, yaml
from core.paths import model_providers_path
from llm.provider_secrets import resolve_provider_api_key
data = json.load(sys.stdin)
conf = yaml.safe_load(model_providers_path().read_text())
provider = conf["providers"][conf["default_provider"]]
assert provider.get("enabled") and provider.get("base_url", "").rstrip("/") == "https://openrouter.ai/api/v1"
key = resolve_provider_api_key(provider)
assert key, "configured provider has no credential"
model = provider["models"]["light"]
messages = [{"role": "system", "content": 'Diagnose the supplied synthetic Python code. Return JSON only, matching the acceptance contract in the request: {"contract":"copied", "issue":"copied", "fingerprint":"copied", "diagnosis":[{"file":"a supplied path", "line":1, "evidence":"exact substring of that source line", "explanation":"the defect", "suggested_check":"a check to reproduce it"}]}. diagnosis must be an array even for a single finding. Do not execute code. Report the defect, not a replacement program.'},
            {"role": "user", "content": json.dumps(data)}]
phase = "metadata"
with httpx.Client(timeout=22, follow_redirects=False) as client:
    models = client.get("https://openrouter.ai/api/v1/models")
    models.raise_for_status()
    price = next(m["pricing"] for m in models.json()["data"] if m["id"] == model)
    # UTF-8 bytes conservatively bound input tokens; output is capped independently.
    bound = len(json.dumps(messages).encode()) * float(price["prompt"]) + 800 * float(price["completion"]) + float(price.get("request", 0))
    assert 0 <= bound <= .25, "model cost bound exceeds $0.25"
    phase = "inference"
    reply = client.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + key},
        json={"model": model, "messages": messages, "max_tokens": 800, "temperature": 0,
              "response_format": {"type": "json_object"}, "reasoning": {"enabled": False}})
    if reply.status_code != 200:
        print(json.dumps({"error": "model_http_error", "status": reply.status_code})); sys.exit(1)
    phase = "parse"
    body = reply.json()
    choice = body["choices"][0]
    assert choice.get("finish_reason") == "stop", "incomplete model response"
    result = json.loads(choice["message"]["content"])
    print(json.dumps({"result": result, "model": model, "usage": body.get("usage"),
                      "generation_id": body.get("id"), "cost_bound_usd": bound}))
'''


def listener() -> socket.socket:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    sock.setblocking(False)
    return sock


def certificate(root: Path) -> tuple[Path, Path]:
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AICOM isolated live probe")])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = root / "tls.pem", root / "tls.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    key_path.chmod(0o600)
    return cert_path, key_path


async def run(args, root: Path) -> dict:
    os.environ.update({"AIFACTORY_DATA_ROOT": str(root / "factory"),
                       "AIFACTORY_MAX_PIPELINE_COST_USD": "2", "AIFACTORY_FACTORY_ON_HOLD": "0",
                       "AIMARKET_CREDITS_ENABLED": "1", "AIFACTORY_CRYPTO_ENABLED": "0",
                       "AIMARKET_SKIP_SEED": "1", "AIMARKET_AUTO_CRAWL": "0",
                       "AIMARKET_ALLOW_LOCAL_PUBLISH": "1", "AIMARKET_ORACLE_FAMILY_URL": "off",
                       "AIMARKET_SANDBOX_STUB_INVOKE": "0", "AIMARKET_SUBCONTRACT_SWEEP_S": "0"})
    import httpx
    import uvicorn
    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.credits import CreditsLedger
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.models import Capability
    from aimarket_hub.signing import Signer
    from fastapi import FastAPI, HTTPException

    from core.procurement_store import PurchaseStore
    from orchestrator.procurement import prepare_diagnosis

    provider = FastAPI()
    calls = []

    @provider.post("/diagnose")
    async def diagnose(body: dict):
        if calls:
            raise HTTPException(409, "probe permits only one model request")
        calls.append({"started_at": datetime.now(UTC).isoformat()})
        safe_code = ("try:\n" + textwrap.indent(MODEL_CALL, "    ")
                     + "\nexcept Exception as e:\n    print(json.dumps({'error':type(e).__name__, 'phase':globals().get('phase', 'setup')}))\n")
        remote = shlex.join(["docker", "exec", "-i", args.container, "python", "-c", safe_code])
        process = await asyncio.create_subprocess_exec(
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", args.ssh_host, remote,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(json.dumps(body["input"]).encode()), 35)
        except TimeoutError:
            process.kill()
            await process.wait()
            calls[0]["error"] = "bridge_timeout"
            raise HTTPException(504, "model bridge timed out; no retry") from None
        if process.returncode:
            # stderr could contain a library exception with credentials; do not forward it.
            calls[0]["error"] = "model_bridge_failed"
            raise HTTPException(502, "model bridge failed; no retry")
        response = json.loads(stdout)
        if response.get("error"):
            calls[0].update(response)
            raise HTTPException(502, "model did not deliver; no retry")
        calls[0].update({k: response.get(k) for k in ("model", "usage", "generation_id", "cost_bound_usd")})
        return {"result": response["result"]}

    provider_socket, hub_socket = listener(), listener()
    hub_url = f"https://127.0.0.1:{hub_socket.getsockname()[1]}"
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "signer", pqc=True)
    config = HubConfig()
    config.hub_url, config.hub_name = hub_url, "AICOM isolated live probe — test credits"
    config.auto_crawl, config.seed_list, config.crypto_enabled = False, [], False
    db.upsert_capability(Capability(
        capability_id="aicom.diagnose@v1", product_id="live-diagnosis-probe", name="Live model diagnosis",
        description="Diagnose Python code using a real configured model; isolated test account",
        input_schema={"type": "object", "required": ["contract", "issue", "fingerprint", "files"]},
        price_per_call_usd=.1, trust_score=1, source_hub="local",
        invoke_url=f"http://127.0.0.1:{provider_socket.getsockname()[1]}/diagnose"))
    app = create_app(config=config, db=db, signer=signer)
    ledger = CreditsLedger(db._conn)
    account = ledger.create_account(label="isolated probe — not production funds", grant_usd=.5)
    os.environ["AIFACTORY_PROCUREMENT_API_KEY"] = account["api_key"]
    factory = root / "factory"
    (factory / "config").mkdir(parents=True)
    (factory / "config/procurement.json").write_text(json.dumps({
        "enabled": True, "hub_url": hub_url, "hub_public_key": signer.public_key_b64,
        "hub_pq_public_key": signer.pq_public_key_b64,
        "providers": [{"product_id": "live-diagnosis-probe", "capability_id": "aicom.diagnose@v1"}],
        "share_globs": ["app/*.py"]}))
    code = factory / "code/probe/app/main.py"
    code.parent.mkdir(parents=True)
    code.write_text("def divide(x):\n    return 1 / x\n")
    cert, key = certificate(root)
    servers = [uvicorn.Server(uvicorn.Config(provider, log_level="critical", access_log=False)),
               uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False,
                                            ssl_certfile=str(cert), ssl_keyfile=str(key)))]
    tasks = [asyncio.create_task(server.serve(sockets=[sock]))
             for server, sock in zip(servers, (provider_socket, hub_socket), strict=True)]
    try:
        for _ in range(500):
            if all(s.started for s in servers):
                break
            if any(t.done() for t in tasks):
                await asyncio.gather(*tasks)
                raise RuntimeError("probe server exited during startup")
            await asyncio.sleep(.02)
        else:
            raise RuntimeError("probe server startup timed out")
        state = {"root": factory, "product": {"id": "probe"},
                 "task": {"id": "repair", "product_id": "probe"}, "task_queue": [],
                 "input_data": {"qa_findings": [{"file": "app/main.py", "title": "Division by zero",
                                                 "severity": "high"}]}}
        trace = []
        async def observe(response):
            trace.append({"method": response.request.method, "path": response.request.url.path,
                          "status": response.status_code})
        async with httpx.AsyncClient(verify=ssl.create_default_context(cafile=str(cert)), trust_env=False,
                                     timeout=40, event_hooks={"response": [observe]}) as client:
            for n in (1, 2, 3):
                state["task_queue"].append({"id": f"dev-{n}", "product_id": "probe", "agent_type": "developer",
                                            "status": "completed", "completed_at": n})
                diagnosis = await prepare_diagnosis(**state, client=client)
                if n < 3:
                    assert diagnosis is None and not calls
            before_replay = len(trace)
            replay = await prepare_diagnosis(**state, client=client)
            replay_without_network = len(trace) == before_replay
        rows = PurchaseStore(factory).orders()
        remaining = ledger.account(account["account_id"])
        passed = bool(diagnosis and replay == diagnosis and replay_without_network and len(calls) == 1
                      and len(rows) == 1 and rows[0]["status"] == "accepted"
                      and rows[0]["charged"] == 100_000 and rows[0]["reserved"] == 0
                      and remaining["balance_usd"] == .4)
        return {"passed": passed, "at_utc": datetime.now(UTC).isoformat(),
                "environment": "isolated real HTTPS Hub + real external model; test credit grant",
                "production_payment_verified": False, "production_modified": False,
                "http_trace": trace, "model_calls": calls, "diagnosis": diagnosis,
                "replay_without_network": replay_without_network,
                "test_credit_before_usd": .5, "test_credit_after_usd": remaining["balance_usd"],
                "orders": [{k: row[k] for k in ("id", "status", "payment", "charged", "reserved", "reason")}
                           for row in rows],
                "deliveries": [{k: value for k, value in json.loads(row["response"] or "{}").items()
                                if k in ("success", "receipt", "result", "price_usd", "remaining_balance")}
                               for row in rows if row["response"] and row["response"] != "null"],
                "hub_public_key": signer.public_key_b64, "hub_pq_public_key": signer.pq_public_key_b64}
    finally:
        for server in servers:
            server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
        provider_socket.close()
        hub_socket.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", required=True, help="Existing factory SSH alias; never a credential")
    parser.add_argument("--container", default="aicom-app-1")
    parser.add_argument("--output", type=Path, required=True, help="Sanitized evidence JSON")
    args = parser.parse_args()
    if args.ssh_host.startswith("-"):
        parser.error("invalid SSH host")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aicom-live-probe-") as tmp:
        result = asyncio.run(run(args, Path(tmp)))
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
