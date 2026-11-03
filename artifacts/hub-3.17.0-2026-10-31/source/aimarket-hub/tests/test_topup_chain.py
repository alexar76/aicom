"""A stranger buys credit with USDC, on a real chain, and spends it — end to end.

anvil runs with Base's chain id, UniUSD (contracts/evm/src/UniUSD.sol — the UNI bubble's USDC,
EIP-3009 implemented, not stubbed) plays USDC, and the hub is the real app pointed at that RPC.
Nothing is stubbed between the 402 and the credit: the stranger opens its own account, takes the
top-up 402, signs a transferWithAuthorization over the offer's nonce with eth_account, sends the
transaction itself (the hub holds no key), and the hub reads the receipt and credits it.

Uses anvil's published throwaway keys only, on a throwaway local chain. Skipped when foundry or
eth-account is absent.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests._mandate_kit import balance, hub, list_static

_REPO = Path(__file__).resolve().parents[2]
_FORGE = _REPO / "contracts/evm"
# anvil's deterministic development accounts — public by design, valid only on a local chain.
_DEPLOYER = ("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
             "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
_OPERATOR = ("0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
             "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")
_STRANGER = ("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
             "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a")
BASE_CHAIN_ID = 8453


def _have_eth_account() -> bool:
    try:
        import eth_account  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.skipif(not _have_eth_account(), reason="eth-account not installed"),
    pytest.mark.skipif(not (shutil.which("anvil") and shutil.which("forge") and shutil.which("cast")),
                       reason="foundry (anvil/forge/cast) not installed — the chain path is UNPROVEN here"),
    pytest.mark.skipif(not (_FORGE / "src/UniUSD.sol").exists(), reason="contracts/evm not in this checkout"),
]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kw)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _deploy(rpc: str) -> str:
    proc = _run(["forge", "create", "--rpc-url", rpc, "--private-key", _DEPLOYER[1],
                 "src/UniUSD.sol:UniUSD", "--broadcast", "--json"], cwd=str(_FORGE))
    if proc.returncode != 0:
        pytest.skip(f"forge create failed: {proc.stderr[-400:]}")
    match = re.search(r'"deployedTo"\s*:\s*"(0x[0-9a-fA-F]{40})"', proc.stdout)
    if not match:
        pytest.skip(f"no deployment address in forge output: {proc.stdout[-300:]}")
    return match.group(1)


def _rpc(rpc: str, method: str, params: list) -> object:
    body = httpx.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=10).json()
    assert "error" not in body, body
    return body["result"]


def _usdc_balance(rpc: str, token: str, who: str) -> int:
    out = _run(["cast", "call", token, "balanceOf(address)(uint256)", who, "--rpc-url", rpc]).stdout.strip()
    return int(out.split()[0])


def _send(rpc: str, key: str, to: str, data: str) -> str:
    """Sign and send a transaction from `key` — the buyer pays its own gas."""
    from eth_account import Account

    sender = Account.from_key(key).address
    nonce = int(_rpc(rpc, "eth_getTransactionCount", [sender, "pending"]), 16)
    tx = {"to": to, "data": data, "value": 0, "gas": 200_000, "nonce": nonce, "chainId": BASE_CHAIN_ID,
          "maxFeePerGas": 2_000_000_000, "maxPriorityFeePerGas": 1_000_000_000, "type": 2}
    signed = Account.sign_transaction(tx, key)
    raw = signed.raw_transaction if hasattr(signed, "raw_transaction") else signed.rawTransaction
    tx_hash = _rpc(rpc, "eth_sendRawTransaction", ["0x" + raw.hex().removeprefix("0x")])
    # anvil's automine is not synchronous with eth_sendRawTransaction on every version: the
    # receipt can lag the send by a few milliseconds, which made this test fail ~1 run in 4.
    # Wait for it the way a real client does.
    receipt = None
    for _ in range(100):
        receipt = _rpc(rpc, "eth_getTransactionReceipt", [tx_hash])
        if receipt:
            break
        time.sleep(0.05)
    assert receipt and receipt["status"] == "0x1", receipt
    return str(tx_hash)


def _pay_offer(rpc: str, offer: dict, key: str, sender: str) -> str:
    """What a stranger's agent does with the 402: sign the typed data, send the calldata."""
    from eth_account import Account

    from aimarket_agent.topup import calldata, typed_data

    typed = typed_data(offer, sender=sender, valid_before=int(time.time()) + 600)
    signature = Account.sign_typed_data(key, full_message=typed).signature.hex()
    return _send(rpc, key, offer["accepts"][0]["asset"], calldata(typed, "0x" + signature.removeprefix("0x")))


@pytest.fixture(scope="module")
def chain():
    port = _free_port()
    proc = subprocess.Popen(["anvil", "--port", str(port), "--chain-id", str(BASE_CHAIN_ID), "--silent",
                             "--accounts", "4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rpc = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            if _run(["cast", "chain-id", "--rpc-url", rpc]).returncode == 0:
                break
            time.sleep(0.2)
        else:
            pytest.skip("anvil did not become ready")
        token = _deploy(rpc)
        # UniUSD's mint is open: this is the bubble's dollar, on a chain that exists for this test.
        assert _run(["cast", "send", token, "mint(address,uint256)", _STRANGER[0], "20000000",
                     "--private-key", _DEPLOYER[1], "--rpc-url", rpc]).returncode == 0
        yield {"rpc": rpc, "token": token}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


@pytest.fixture
def wired(chain, monkeypatch):
    monkeypatch.setenv("AIMARKET_TOPUP_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_X402_ASSET", chain["token"])
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", _OPERATOR[0])
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", chain["rpc"])
    monkeypatch.setenv("AIMARKET_CREDITS_OPEN_SIGNUP", "1")
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0")
    from aimarket_hub import topup

    topup._VERIFY_LOG.clear()
    return chain


def _mine(rpc: str) -> None:
    _rpc(rpc, "anvil_mine", ["0x1"])


def test_a_stranger_buys_credit_with_usdc_and_spends_it(wired, monkeypatch, tmp_path):
    from aimarket_hub import channels

    rpc, token = wired["rpc"], wired["token"]
    operator_before = _usdc_balance(rpc, token, _OPERATOR[0])
    with hub(monkeypatch, tmp_path) as (client, db):
        # 1. The stranger opens its own account — no operator involved, no free grant.
        opened = client.post("/ai-market/v2/accounts", json={"label": "a stranger's agent"}).json()
        key, account = opened["api_key"], opened["account_id"]
        assert opened["balance_usd"] == 0.0
        # 2. It asks for 5 USDC of credit and is quoted an ordinary x402 offer.
        offer_resp = client.post("/ai-market/v2/account/topup", headers={"X-API-Key": key}, json={"amount_usd": 5})
        assert offer_resp.status_code == 402
        offer = offer_resp.json()
        nonce = offer["nonce"]
        # 3. It signs and sends the authorization itself.
        tx_hash = _pay_offer(rpc, offer, _STRANGER[1], _STRANGER[0])
        # 4. One confirmation is not enough (AIMARKET_TOPUP_MIN_CONFIRMATIONS defaults to 2).
        early = client.post(f"/ai-market/v2/topups/{nonce}", json={"tx_hash": tx_hash})
        assert early.status_code == 409 and early.json()["error"] == "payment_not_final"
        _mine(rpc)
        credited = client.post(f"/ai-market/v2/topups/{nonce}", headers={"X-API-Key": key},
                               json={"tx_hash": tx_hash})
        assert credited.status_code == 200, credited.text
        assert credited.json()["credited_usd"] == 5.0 and credited.json()["balance_usd"] == 5.0
        assert credited.json()["payer"].lower() == _STRANGER[0].lower()
        # 5. The money is on chain, at the operator — the hub never touched it.
        assert _usdc_balance(rpc, token, _OPERATOR[0]) - operator_before == 5_000_000
        # 6. The credit pays for work.
        list_static(db, price=0.004)
        work = client.post("/ai-market/v2/invoke", headers={"X-API-Key": key},
                           json={"product_id": "demo-echo", "capability_id": "demo.echo@v1", "input": {}})
        assert work.status_code == 200 and work.json()["success"] is True
        assert balance(db, account) == pytest.approx(4.996)
        # 7. The same payment credits nothing more — at this door or the channel door.
        again = client.post(f"/ai-market/v2/topups/{nonce}", json={"tx_hash": tx_hash})
        assert again.status_code == 200 and again.json()["idempotent_replay"] is True
        channel = channels._claim_deposit_shared(chain="base", tx_hash=tx_hash, channel_id="ch_x", amount_cents=500)
        assert channel["ok"] is False and channel["error"] == "already_claimed"
        assert balance(db, account) == pytest.approx(4.996)


def test_a_plain_transfer_is_not_credited_and_a_short_authorization_is_credited_for_what_arrived(
        wired, monkeypatch, tmp_path):
    rpc, token = wired["rpc"], wired["token"]
    with hub(monkeypatch, tmp_path) as (client, db):
        opened = client.post("/ai-market/v2/accounts", json={"label": "b"}).json()
        key, account = opened["api_key"], opened["account_id"]
        offer = client.post("/ai-market/v2/account/topup", headers={"X-API-Key": key},
                            json={"amount_usd": 2}).json()
        # A plain transfer of the right amount to the right wallet: nothing binds it to the offer.
        plain = _run(["cast", "send", token, "transfer(address,uint256)", _OPERATOR[0], "2000000",
                      "--private-key", _STRANGER[1], "--rpc-url", rpc, "--json"])
        plain_tx = json.loads(plain.stdout)["transactionHash"]
        _mine(rpc)
        _mine(rpc)
        r_plain = client.post(f"/ai-market/v2/topups/{offer['nonce']}", json={"tx_hash": plain_tx})
        assert r_plain.status_code == 402 and "no EIP-3009 authorization" in r_plain.json()["detail"]
        assert balance(db, account) == 0.0
        # An authorization over the offer's nonce for one base unit less: bound to this account,
        # so it is credited — for what arrived, rounded down to the millicent.
        short = dict(offer, accepts=[dict(offer["accepts"][0], maxAmountRequired="1999999")])
        short_tx = _pay_offer(rpc, short, _STRANGER[1], _STRANGER[0])
        _mine(rpc)
        r_short = client.post(f"/ai-market/v2/topups/{offer['nonce']}", json={"tx_hash": short_tx})
        left = balance(db, account)
    assert r_short.status_code == 200 and r_short.json()["paid_usd"] == 1.999999
    assert left == pytest.approx(1.99999)
