"""Real local EVM payments using the exact typed data and calldata shipped by Studio.

No external chain or buyer funds: Anvil accounts and UniUSD are disposable fixtures.
"""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from eth_account import Account

from tests._mandate_kit import hub
from tests.test_studio_paid import listing, node
from tests.test_topup_chain import (  # reuse the existing local-chain fixture, no live RPC
    chain, wired, pytestmark, _DEPLOYER, _OPERATOR, _STRANGER, _FORGE,
    _run, _rpc, _usdc_balance, _mine,
)

ROOT = Path(__file__).resolve().parents[2]


def send(rpc, tx, *, broadcast=True):
    nonce = int(_rpc(rpc, "eth_getTransactionCount", [_STRANGER[0], "pending"]), 16)
    signed = Account.sign_transaction({**tx, "value": 0, "gas": 300_000, "nonce": nonce, "chainId": 8453,
        "maxFeePerGas": 2_000_000_000, "maxPriorityFeePerGas": 1_000_000_000, "type": 2}, _STRANGER[1])
    raw = "0x" + signed.raw_transaction.hex().removeprefix("0x")
    if not broadcast:
        return raw
    tx_hash = _rpc(rpc, "eth_sendRawTransaction", [raw])
    for _ in range(50):
        receipt = _rpc(rpc, "eth_getTransactionReceipt", [tx_hash])
        if receipt:
            assert receipt["status"] == "0x1", receipt
            return tx_hash
        time.sleep(0.1)
    raise AssertionError("local transaction was not mined")


def browser_code(step, signature=None):
    if not shutil.which("node") or not (ROOT / "hephaestus/studio/node_modules/typescript").exists():
        pytest.skip("Node and Studio TypeScript dependency are required")
    script = """
import ts from './hephaestus/studio/node_modules/typescript/lib/typescript.js';
import fs from 'node:fs';
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync('hephaestus/studio/src/paidApi.ts', 'utf8');
const js = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 });
const api = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
const answer = input.signature ? api.paymentTransaction(input.step, input.wallet, input.signature)
    : api.authorizationData(input.step, input.wallet);
process.stdout.write(JSON.stringify(answer));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
        input=json.dumps(dict(step=step, wallet=_STRANGER[0], signature=signature)),
        text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("root_sku", [False, True])
def test_wallet_pays_the_seller_and_the_pipeline_finishes_once(wired, monkeypatch, tmp_path, split, root_sku):
    rpc, token = wired["rpc"], wired["token"]
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "250" if split else "0")
    if split:
        fixture = _run(["forge", "create", "--rpc-url", rpc, "--private-key", _DEPLOYER[1],
            "test/StudioPaymentToken.sol:StudioPaymentToken", "--broadcast", "--json"], cwd=str(_FORGE))
        assert fixture.returncode == 0, fixture.stderr
        token = re.search(r'"deployedTo"\s*:\s*"(0x[0-9a-fA-F]{40})"', fixture.stdout).group(1)
        assert _run(["cast", "send", token, "mint(address,uint256)", _STRANGER[0], "20000000",
            "--private-key", _DEPLOYER[1], "--rpc-url", rpc]).returncode == 0
        monkeypatch.setenv("AIMARKET_X402_ASSET", token)
        deployed = _run(["forge", "create", "--rpc-url", rpc, "--private-key", _DEPLOYER[1],
            "src/MarketSplitter.sol:MarketSplitter", "--broadcast", "--json", "--constructor-args", _OPERATOR[0], "250"], cwd=str(_FORGE))
        assert deployed.returncode == 0, deployed.stderr
        address = re.search(r'"deployedTo"\s*:\s*"(0x[0-9a-fA-F]{40})"', deployed.stdout).group(1)
        monkeypatch.setenv("AIMARKET_MARKET_SPLITTER", address)
        monkeypatch.setenv("AIMARKET_MARKET_FEE_TO", _OPERATOR[0])
    seller = _DEPLOYER[0]
    before = _usdc_balance(rpc, token, seller)
    buyer_before = _usdc_balance(rpc, token, _STRANGER[0])
    with hub(monkeypatch, tmp_path) as (client, db):
        listing(db, payout=seller)
        listing(db, cid="demo.end@v1", payout=seller, price=0,
            input_schema={"type": "object", "required": ["reading"], "properties": {"reading": {"type": "integer"}}})
        q = client.post("/studio/preflight", json={"nodes": [node(),
            {**node("end", "demo.end@v1", depends_on=["read"]), "input": {"reading": "${read.reading}"}}]}).json()
        assert q["ready"], q
        headers = {"X-Studio-Run-Token": q["access_token"]}
        url = f"/studio/paid-runs/{q['run_id']}/advance"
        start = dict(step_id="read", wallet=_STRANGER[0])
        if root_sku:
            prepared = client.post(f"/studio/paid-runs/{q['run_id']}/prepare-pipeline",
                                  json={"wallet": _STRANGER[0]}, headers=headers).json()
            step = prepared["offers"][0]
        else:
            prepared = client.post(url, json=start, headers=headers).json()
            step = prepared["next_step"]
        typed = browser_code(step)
        assert typed["primaryType"] == ("ReceiveWithAuthorization" if split else "TransferWithAuthorization")
        signature = Account.sign_typed_data(_STRANGER[1], full_message=typed).signature.hex()
        tx = browser_code(step, "0x" + signature.removeprefix("0x"))
        if root_sku:
            raw = send(rpc, tx, broadcast=False)
            request = {"product_id": "hephaestus", "capability_id": "pipeline.run@v1", "input": {
                "run_id": q["run_id"], "access_token": q["access_token"], "transactions": {"read": raw}}}
            final = client.post("/ai-market/v2/invoke", json=request).json()
            for _ in range(10):
                if final["status"] in ("completed", "failed"):
                    break
                _mine(rpc)
                final = client.post("/ai-market/v2/invoke", json=request).json()
            tx_hash = final["bill_of_materials"]["steps"][0]["tx_hash"]
            replay = client.post("/ai-market/v2/invoke", json=request).json()
            assert len(final["subcontracting"]["nodes"]) == 3
        else:
            tx_hash = send(rpc, tx)
            _mine(rpc)
            paid = client.post(url, json={**start, "tx_hash": tx_hash}, headers=headers).json()
            assert paid["next_step"]["id"] == "end", paid
            final = client.post(url, json=dict(step_id="end", wallet=_STRANGER[0]), headers=headers).json()
            replay = client.post(url, json={**start, "tx_hash": tx_hash}, headers=headers).json()
        assert final["status"] == "completed", final
        assert final["final_result"] == {"reading": 7}
        assert final["bill_of_materials"]["total_usd"] == 0.004
        assert final["bill_of_materials"]["steps"][0]["payment"]["tx_hash"] == tx_hash
        assert replay == final
    assert _usdc_balance(rpc, token, seller) - before == (3900 if split else 4000)
    assert buyer_before - _usdc_balance(rpc, token, _STRANGER[0]) == 4000
