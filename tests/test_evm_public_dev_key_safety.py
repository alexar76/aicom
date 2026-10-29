"""Actual-chain/dev-key gates, exercised using mocked RPCs and disposable keys."""
from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = "0x" + "12" * 20


@pytest.fixture(autouse=True)
def module_paths(monkeypatch, tmp_path):
    for relative in ("lottery/relayer", "lottery/agent", "alien-monitor/backend"):
        monkeypatch.syspath_prepend(str(ROOT / relative))
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "factory"))
    monkeypatch.delenv("ALIEN_UNIVERSE_BUYER_RPC", raising=False)


@lru_cache(maxsize=1)
def dev_key():
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(" ".join(["test"] * 11 + ["junk"])).key.hex()


class Eth:
    def __init__(self, chain_id):
        self.chain_id = chain_id
        self.accounts = []
        self.gas_price = 1
        self.sent = []

    def contract(self, **kwargs):
        return SimpleNamespace()

    def get_transaction_count(self, *args):
        return 0

    def send_raw_transaction(self, raw):
        self.sent.append(raw)
        return bytes.fromhex("11" * 32)

    def wait_for_transaction_receipt(self, *args, **kwargs):
        return {"status": 1}


def w3(actual=31337, rpc="http://127.0.0.1:8545"):
    return SimpleNamespace(eth=Eth(actual), provider=SimpleNamespace(endpoint_uri=rpc), is_connected=lambda: True)


def chain(monkeypatch, *, actual=31337, configured=31337, rpc="http://127.0.0.1:8545", urls=None):
    module = importlib.import_module("ailottery_relayer.chain")
    connected = w3(actual, rpc)
    monkeypatch.setattr(module, "connect_web3", lambda urls: connected)
    return module.Chain(rpc, configured, ADDRESS, rpc_urls=urls), connected


def test_guard_copies_match_and_cover_all_default_anvil_hardhat_accounts():
    canonical = (ROOT / "security/evm_dev_key_safety.py").read_bytes()
    for relative in (
        "lottery/relayer/ailottery_relayer/dev_key_safety.py",
        "lottery/agent/ailottery_agent/dev_key_safety.py", "alien-monitor/backend/evm_dev_key_safety.py",
    ):
        assert (ROOT / relative).read_bytes() == canonical
    from security.evm_dev_key_safety import is_public_dev_key
    Account.enable_unaudited_hdwallet_features()
    mnemonic = " ".join(["test"] * 11 + ["junk"])
    assert all(is_public_dev_key(Account.from_mnemonic(
        mnemonic, account_path=f"m/44'/60'/0'/0/{i}",
    ).key) for i in range(20))
    assert not is_public_dev_key(Account.create().key)


@pytest.mark.parametrize("rpc", ["https://rpc.example.invalid", "http://203.0.113.10", "http://169.254.169.254", "http://localhost.evil.invalid", "http://user:password@localhost:8545"])
def test_public_rpc_cannot_spoof_a_development_chain(rpc):
    from security.evm_dev_key_safety import require_local_dev_chain
    with pytest.raises(RuntimeError):
        require_local_dev_chain(w3(31337, rpc), rpc)


@pytest.mark.parametrize("rpc", ["http://127.0.0.1:8545", "http://localhost:8545", "http://chain:8545", "http://lottery-chain:8545", "http://host.docker.internal:8545", "http://172.17.0.1:8546"])
def test_verified_private_development_chain_remains_supported(rpc):
    from security.evm_dev_key_safety import require_local_dev_chain
    assert require_local_dev_chain(w3(31337, rpc), rpc) == 31337
    with pytest.raises(RuntimeError):
        require_local_dev_chain(w3(8453, rpc), rpc)


def test_lottery_checks_actual_rpc_chain_before_constructing_contract(monkeypatch):
    with pytest.raises(RuntimeError, match="chain ID"):
        chain(monkeypatch, actual=8453, configured=31337)


@pytest.mark.parametrize("method", ["transfer", "send", "sign_beacon", "sign_voucher", "sign_work_seat"])
@pytest.mark.parametrize("unsafe", ["real_chain", "public_rpc", "changed_chain"])
def test_lottery_refuses_before_signing_or_broadcast(method, unsafe, monkeypatch):
    rpc = "https://rpc.example.invalid" if unsafe == "public_rpc" else "http://127.0.0.1:8545"
    actual = 8453 if unsafe == "real_chain" else 31337
    client, connected = chain(monkeypatch, actual=actual, configured=actual, rpc=rpc)
    if unsafe == "changed_chain":
        connected.eth.chain_id = 8453
    args = {
        "transfer": (dev_key(), ADDRESS, 1), "send": (None, dev_key()),
        "sign_beacon": (dev_key(), 1, b"x" * 32, 10, b"y" * 32),
        "sign_voucher": (dev_key(), ADDRESS, 1, 100, 9999),
        "sign_work_seat": (dev_key(), ADDRESS, "0x" + "ab" * 32, 1, 100, 9999),
    }
    with pytest.raises(RuntimeError):
        getattr(client, method)(*args[method])
    assert connected.eth.sent == []


def test_healthy_development_payment_and_signature_remain_valid(monkeypatch):
    client, connected = chain(monkeypatch)
    assert client.transfer(dev_key(), ADDRESS, 7)["status"] == 1
    assert Account.recover_transaction(connected.eth.sent[0]) == Account.from_key(dev_key()).address
    value = client.sign_voucher(dev_key(), ADDRESS, 1, 100, 9999)
    assert len(value) == 65


def test_fresh_private_key_keeps_real_chain_support(monkeypatch):
    client, connected = chain(monkeypatch, actual=8453, configured=8453, rpc="https://rpc.example.invalid")
    account = Account.create()
    assert client.transfer(account.key, ADDRESS, 3)["status"] == 1
    assert Account.recover_transaction(connected.eth.sent[0]) == account.address


def test_failover_rechecks_the_exact_broadcast_endpoint_chain(monkeypatch):
    from ailottery_relayer.rpc import FailoverHTTPProvider, HTTPProvider
    seen = []

    def response(self, method, params):
        seen.append(method)
        if method == "eth_chainId":
            return {"result": "0x2105"}  # The fallback is Base, while config says local Anvil.
        pytest.fail("a transaction reached the mismatched fallback endpoint")

    monkeypatch.setattr(HTTPProvider, "make_request", response)
    provider = FailoverHTTPProvider(["http://127.0.0.1:8545"])
    provider.expected_chain_id = 31337
    signed = Account.sign_transaction({
        "nonce": 0, "gasPrice": 1, "gas": 21000, "to": ADDRESS, "value": 1, "chainId": 31337,
    }, dev_key())
    with pytest.raises(RuntimeError, match="wrong chain ID"):
        provider.make_request("eth_sendRawTransaction", [signed.raw_transaction.hex()])
    assert seen == ["eth_chainId"]


@pytest.mark.parametrize("typed", [False, True])
def test_failover_refuses_raw_bytes_signed_for_another_chain_before_rpc(typed, monkeypatch):
    from ailottery_relayer.rpc import FailoverHTTPProvider, HTTPProvider
    monkeypatch.setattr(HTTPProvider, "make_request", lambda *args: pytest.fail("wrong-domain raw bytes reached RPC"))
    transaction = {"nonce": 0, "gas": 21000, "to": ADDRESS, "value": 1, "chainId": 8453}
    transaction.update({"type": 2, "maxFeePerGas": 2, "maxPriorityFeePerGas": 1} if typed else {"gasPrice": 1})
    signed = Account.sign_transaction(transaction, Account.create().key)
    provider = FailoverHTTPProvider(["http://127.0.0.1:8545"])
    provider.expected_chain_id = 31337
    with pytest.raises(RuntimeError, match="different chain"):
        provider.make_request("eth_sendRawTransaction", [signed.raw_transaction.hex()])


@pytest.mark.parametrize("slot", ["OPERATOR_KEY", "ORACLE_SIGNER_KEY", "TREASURY_KEY", "SPONSOR_KEY", "BENEFACTOR_KEY", "FAUCET_KEY", "AGENT_KEYS"])
def test_lottery_live_config_rejects_default_key_in_every_money_role(slot, monkeypatch):
    from ailottery_relayer.config import Config
    fresh = Account.create().key.hex()
    for name in ("OPERATOR_KEY", "ORACLE_SIGNER_KEY", "TREASURY_KEY", "SPONSOR_KEY", "BENEFACTOR_KEY", "FAUCET_KEY"):
        monkeypatch.setenv(name, fresh)
    monkeypatch.setenv("UNI_AUTO_WALLET", "0")
    monkeypatch.setenv("LOTTERY_MODE", "live")
    monkeypatch.setenv("CHAIN_ID", "8453")
    monkeypatch.setenv("RPC_URL", "https://rpc.example.invalid")
    monkeypatch.setenv(slot, dev_key())
    with pytest.raises(RuntimeError, match="Public test"):
        Config.from_env()


def test_non_anvil_published_private_fingerprint_has_the_same_production_gate(monkeypatch):
    import hashlib
    from security import evm_dev_key_safety as safety
    account = Account.create()
    monkeypatch.setattr(safety, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(bytes(account.key)).hexdigest()}))
    with pytest.raises(RuntimeError):
        safety.require_signing_chain(w3(8453, "https://rpc.example.invalid"), 8453, ["https://rpc.example.invalid"], account.key)
    safety.require_signing_chain(w3(), 31337, ["http://127.0.0.1:8545"], account.key)


def test_all_public_default_accounts_are_refused_as_production_wallet_derivation_seeds(monkeypatch):
    from ailottery_relayer.config import Config
    fresh = Account.create().key.hex()
    for name in ("OPERATOR_KEY", "ORACLE_SIGNER_KEY", "TREASURY_KEY", "SPONSOR_KEY", "BENEFACTOR_KEY", "FAUCET_KEY"):
        monkeypatch.setenv(name, fresh)
    monkeypatch.setenv("LOTTERY_MODE", "live")
    monkeypatch.setenv("CHAIN_ID", "8453")
    monkeypatch.setenv("RPC_URL", "https://rpc.example.invalid")
    monkeypatch.setenv("UNI_AUTO_WALLET", "1")
    Account.enable_unaudited_hdwallet_features()
    key = Account.from_mnemonic(" ".join(["test"] * 11 + ["junk"]), account_path="m/44'/60'/0'/0/19").key.hex()
    monkeypatch.setenv("UNI_WALLET_SEED", key)
    with pytest.raises(RuntimeError, match="public wallet seed"):
        Config.from_env()


def test_standalone_agent_refuses_public_key_before_address_or_loop(monkeypatch):
    module = importlib.import_module("ailottery_agent.__main__")
    monkeypatch.setenv("AGENT_KEY", dev_key())
    monkeypatch.setenv("RPC_URL", "https://rpc.example.invalid")
    monkeypatch.setenv("CHAIN_ID", "31337")
    fake = lambda provider: w3(31337, "https://rpc.example.invalid")
    fake.HTTPProvider = lambda *args, **kwargs: None
    monkeypatch.setattr(module, "Web3", fake)
    monkeypatch.setattr(module, "_addr", lambda: pytest.fail("unsafe agent proceeded to the contract"))
    with pytest.raises(RuntimeError):
        module.main()


@pytest.mark.parametrize("writer", ["_forge_run", "_forge_run_in_dir", "_deploy_acex_forge"])
@pytest.mark.parametrize("rpc,actual", [("https://rpc.example.invalid", 31337), ("http://127.0.0.1:8545", 8453)])
def test_alien_refuses_wrong_chain_or_public_rpc_before_forge(writer, rpc, actual, monkeypatch, tmp_path):
    module = importlib.import_module("universe_deploy")
    import web3
    fake = lambda provider: w3(actual, rpc)
    fake.HTTPProvider = lambda *args, **kwargs: None
    monkeypatch.setattr(web3, "Web3", fake)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/unused/forge")
    monkeypatch.setattr(module, "resolve_evm_contracts_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "resolve_acex_evm_dir", lambda: tmp_path)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("unsafe Forge broadcast attempted"))
    engine = module.ContractDeployMixin()
    engine.evm_rpc = rpc
    engine.evm_usdt_address = ADDRESS
    with pytest.raises(RuntimeError):
        if writer == "_forge_run":
            engine._forge_run("script.s.sol", ADDRESS, {})
        elif writer == "_forge_run_in_dir":
            engine._forge_run_in_dir(tmp_path, "script.s.sol", {})
        else:
            engine._deploy_acex_forge()


def test_verified_private_development_forge_path_remains_usable(monkeypatch, tmp_path):
    module = importlib.import_module("universe_deploy")
    import web3
    fake = lambda provider: w3()
    fake.HTTPProvider = lambda *args, **kwargs: None
    monkeypatch.setattr(web3, "Web3", fake)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/unused/forge")
    monkeypatch.setattr(module, "resolve_evm_contracts_dir", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda cmd, **kwargs: (
        calls.append(cmd) or SimpleNamespace(returncode=0, stdout="", stderr="")
    ))
    engine = module.ContractDeployMixin()
    engine.evm_rpc = "http://127.0.0.1:8545"
    engine.evm_usdt_address = ""
    engine._parse_broadcast_address = lambda *args: ADDRESS
    assert engine._forge_run("script.s.sol", ADDRESS, {}) == ADDRESS
    assert len(calls) == 1 and "--broadcast" in calls[0]
    assert calls[0][calls[0].index("--chain-id") + 1] == "31337"


def test_alien_buyer_refuses_real_or_public_settlement_and_unsigned_context(monkeypatch):
    from universe_external_buyer import ExternalAIBuyer
    buyer = ExternalAIBuyer()
    monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_RPC", "https://rpc.example.invalid")
    client, _, _, why = buyer._settlement_chain(None)
    assert client is None and "unsafe" in why
    with pytest.raises(RuntimeError):
        buyer._sign_challenge("challenge")
    monkeypatch.delenv("ALIEN_UNIVERSE_BUYER_RPC")
    realm = SimpleNamespace(_w3=w3(8453), evm_rpc="http://127.0.0.1:8545", evm_usdt_address=ADDRESS)
    client, _, _, why = buyer._settlement_chain(realm)
    assert client is None and "unsafe" in why


def test_alien_buyer_verified_dev_signature_remains_valid():
    from universe_external_buyer import ExternalAIBuyer, UNI_BUYER_KEY
    from eth_account.messages import encode_defunct
    buyer = ExternalAIBuyer()
    realm = SimpleNamespace(_w3=w3(), evm_rpc="http://127.0.0.1:8545", evm_usdt_address=ADDRESS)
    assert buyer._settlement_chain(realm)[3] == ""
    signature = buyer._sign_challenge("payment challenge")
    assert Account.recover_message(encode_defunct(text="payment challenge"), signature=signature) == Account.from_key(UNI_BUYER_KEY).address


def test_rpc_failover_logs_no_endpoint_credentials_and_keeps_healthy_response(monkeypatch, caplog):
    module = importlib.import_module("ailottery_relayer.rpc")
    rpc = "https://user-canary:password-canary@rpc.example.invalid/v2/path-canary?api_key=query-canary"
    provider = module.FailoverHTTPProvider(["https://first.example.invalid", rpc])
    calls = []

    def request(current, method, params):
        calls.append((current.endpoint_uri, method, params))
        if len(calls) == 1:
            raise ConnectionError(f"connection reset while using {rpc}")
        return {"jsonrpc": "2.0", "id": 1, "result": "0x7a69"}

    monkeypatch.setattr(module.HTTPProvider, "make_request", request)
    module.log.addHandler(caplog.handler)
    try:
        assert provider.make_request("eth_chainId", [])["result"] == "0x7a69"
    finally:
        module.log.removeHandler(caplog.handler)
    assert len(calls) == 2 and calls[-1][0] == rpc
    assert "RPC failover" in caplog.text and "endpoint 2 of 2" in caplog.text
    assert all(marker not in caplog.text for marker in (
        rpc, "user-canary", "password-canary", "path-canary", "query-canary", "rpc.example.invalid",
    ))


@pytest.mark.parametrize("failure_stage", ["connect", "cached_chain", "realm_chain"])
def test_buyer_transport_errors_never_echo_rpc_credentials(failure_stage, monkeypatch, caplog):
    from universe_external_buyer import ExternalAIBuyer
    import web3

    rpc = "http://127.0.0.1:8545/v2/path-canary"

    class BrokenEth:
        @property
        def chain_id(self):
            raise OSError(f"provider failed at {rpc}; exception-canary")

    connected = SimpleNamespace(eth=BrokenEth(), provider=SimpleNamespace(endpoint_uri=rpc))
    buyer = ExternalAIBuyer()
    realm = SimpleNamespace(_w3=connected, evm_rpc=rpc, evm_usdt_address=ADDRESS)
    if failure_stage != "realm_chain":
        monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_RPC", rpc)
    if failure_stage == "cached_chain":
        buyer._settle_w3 = connected
        buyer._settle_rpc = rpc
    elif failure_stage == "connect":
        def failed_connect(provider):
            raise OSError(f"provider failed at {rpc}; exception-canary")
        failed_connect.HTTPProvider = lambda *args, **kwargs: None
        monkeypatch.setattr(web3, "Web3", failed_connect)
    client, _, accounts, why = buyer._settlement_chain(realm)
    assert client is None and not accounts and "OSError" in why
    assert ("unreachable" if failure_stage == "connect" else "unsafe") in why
    assert all(marker not in why + caplog.text for marker in (rpc, "path-canary", "exception-canary"))
    assert buyer._settle_signing_context is None


@pytest.mark.parametrize("rpc", [
    "http://user-canary:password-canary@127.0.0.1:8545",
    "http://127.0.0.1:8545?api_key=query-canary",
])
def test_buyer_rejected_rpc_userinfo_and_query_are_not_echoed(rpc, monkeypatch, caplog):
    from universe_external_buyer import ExternalAIBuyer
    monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_RPC", rpc)
    client, _, _, why = ExternalAIBuyer()._settlement_chain(None)
    assert client is None and "unsafe" in why
    assert rpc not in why + caplog.text and "canary" not in why + caplog.text
