"""The hub verifying a deposit itself, because the canonical verifier is not in its image.

`modelmarket.dev` ran for weeks with `AIFACTORY_PROD=1`, the stub off, and
`verify_tx_payment_details` unimportable (`No module named 'web'` — that verifier lives in
the web app, whose package `__init__` pulls in the whole stack). Every deposit-funded
`channel/open` was therefore refused with "on-chain verification unavailable". Nothing
noticed, because the ESCROW-funded door worked and carried all 13 channels the hub has
ever opened (`tx_hash` empty on every row), and 0 refusals in the log reads like health.

The decode logic is exercised here against synthetic receipts; it is also checked against
a real Base USDC transfer in `test_deposit_verify_live.py`.
"""

from __future__ import annotations

from aimarket_hub.deposit_verify import TRANSFER_TOPIC, DepositCheck, verify_deposit

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
HUB = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
PAYER = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
TX = "0x" + "a1" * 32


def _topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def _receipt(*, to: str = HUB, units: int = 5_000_000, token: str = USDC,
             status: int = 1, block: int = 1000, extra_logs: list | None = None) -> dict:
    logs = [{
        "address": token,
        "topics": [TRANSFER_TOPIC, _topic(PAYER), _topic(to)],
        "data": hex(units),
    }]
    logs.extend(extra_logs or [])
    return {"status": hex(status), "blockNumber": hex(block), "logs": logs}


def _rpc(receipt: dict | None, head: int = 1010, decimals: int = 6):
    def call(method: str, params: list):
        if method == "eth_getTransactionReceipt":
            return receipt
        if method == "eth_blockNumber":
            return hex(head)
        if method == "eth_call":
            return hex(decimals)
        raise AssertionError(f"unexpected RPC {method}")
    return call


def _check(**kwargs) -> DepositCheck:
    defaults = dict(tx_hash=TX, amount_usd=5.0, chain="base", token="USDC",
                    recipient=HUB, min_confirmations=2, token_address=USDC)
    defaults.update(kwargs)
    return verify_deposit(**defaults)


class TestAccepts:
    def test_exact_payment_names_the_payer(self):
        check = _check(rpc=_rpc(_receipt()))
        assert check.ok
        assert check.sender == PAYER.lower()
        assert check.confirmations == 11

    def test_overpayment_is_fine(self):
        assert _check(amount_usd=2.0, rpc=_rpc(_receipt(units=5_000_000))).ok

    def test_two_transfers_to_the_recipient_add_up(self):
        second = {"address": USDC, "topics": [TRANSFER_TOPIC, _topic(PAYER), _topic(HUB)],
                  "data": hex(3_000_000)}
        assert _check(amount_usd=8.0, rpc=_rpc(_receipt(units=5_000_000,
                                                        extra_logs=[second]))).ok

    def test_unrelated_logs_are_ignored(self):
        noise = {"address": "0x" + "cd" * 20, "topics": ["0x" + "ff" * 32], "data": "0x1"}
        assert _check(rpc=_rpc(_receipt(extra_logs=[noise]))).ok


class TestRefuses:
    def test_a_stranger_quoting_someone_elses_deposit(self):
        """PAYAUTH-003: recipient+amount alone proves only that SOMEBODY paid."""
        check = _check(rpc=_rpc(_receipt(to="0x" + "11" * 20)))
        assert not check.ok
        assert "moved no USDC to the configured recipient" in check.error

    def test_underpayment(self):
        check = _check(amount_usd=50.0, rpc=_rpc(_receipt(units=5_000_000)))
        assert not check.ok
        assert "short" in check.error

    def test_a_reverted_transaction(self):
        check = _check(rpc=_rpc(_receipt(status=0)))
        assert not check.ok
        assert "reverted" in check.error

    def test_an_unmined_transaction(self):
        check = _check(rpc=_rpc(None))
        assert not check.ok
        assert "not found or not yet mined" in check.error

    def test_too_few_confirmations(self):
        check = _check(min_confirmations=20, rpc=_rpc(_receipt(block=1000), head=1005))
        assert not check.ok
        assert "insufficient confirmations (6/20)" in check.error

    def test_a_transfer_of_a_different_token(self):
        check = _check(rpc=_rpc(_receipt(token="0x" + "ee" * 20)))
        assert not check.ok
        assert "moved no USDC" in check.error

    def test_two_payers_in_one_transaction(self):
        other = {"address": USDC,
                 "topics": [TRANSFER_TOPIC, _topic("0x" + "22" * 20), _topic(HUB)],
                 "data": hex(5_000_000)}
        check = _check(rpc=_rpc(_receipt(extra_logs=[other])))
        assert not check.ok
        assert "ambiguous payer" in check.error

    def test_the_native_coin_has_no_price(self):
        check = _check(token="ETH", rpc=_rpc(_receipt()))
        assert not check.ok
        assert "price oracle" in check.error

    def test_a_malformed_hash(self):
        assert "32-byte transaction hash" in _check(tx_hash="buyer-1757", rpc=_rpc(_receipt())).error

    def test_no_recipient_configured(self):
        assert "no payment recipient" in _check(recipient="", rpc=_rpc(_receipt())).error

    def test_an_rpc_that_will_not_answer(self):
        def dead(method, params):
            raise RuntimeError("connection refused")
        check = _check(rpc=dead)
        assert not check.ok
        assert "could not reach the chain" in check.error


class TestReadiness:
    def test_a_hub_that_cannot_verify_says_so(self, monkeypatch):
        from aimarket_hub import channels

        monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "")
        detail = channels._native_verifier_ready("no-such-chain", "USDC")
        assert "error" in detail

    def test_base_usdc_is_ready_out_of_the_box(self):
        from aimarket_hub import channels

        detail = channels._native_verifier_ready("base", "USDC")
        assert "error" not in detail, detail
        assert detail["rpc_endpoints"] > 0
        assert detail["token_address"].lower() == USDC.lower()


class TestRpcSelection:
    def test_an_override_is_exclusive_not_merely_first(self, monkeypatch):
        """A sealed realm must not fail over to the real chain it is imitating.

        The UNI bubble calls its Anvil "base" (`AIMARKET_RPC_BASE=http://172.17.0.1:8546`,
        `AIMARKET_ADDR_BASE_USDC=<bubble token>`) because its premise is being
        indistinguishable from live. Appending the public Base endpoints after that would
        let one blip on the bubble node send the lookup to Base mainnet, where a bubble
        transaction does not exist — a safe refusal with a completely misleading reason.
        """
        from aimarket_hub.deposit_verify import rpc_urls_for

        monkeypatch.delenv("AIMARKET_DEPOSIT_RPC_URL", raising=False)
        monkeypatch.setenv("AIMARKET_RPC_BASE", "http://172.17.0.1:8546")
        assert rpc_urls_for("base") == ["http://172.17.0.1:8546"]

    def test_the_registry_is_used_when_nothing_is_pinned(self, monkeypatch):
        from aimarket_hub.deposit_verify import rpc_urls_for

        monkeypatch.delenv("AIMARKET_DEPOSIT_RPC_URL", raising=False)
        monkeypatch.delenv("AIMARKET_RPC_BASE", raising=False)
        urls = rpc_urls_for("base")
        assert urls and all(u.startswith("http") for u in urls)
        assert any("base" in u for u in urls)

    def test_the_bubble_token_override_wins(self, monkeypatch):
        """`AIMARKET_ADDR_BASE_USDC` is how the bubble maps the symbol to its own token."""
        from aimarket_hub.deposit_verify import token_address_for

        monkeypatch.setenv("AIMARKET_ADDR_BASE_USDC", "0x5fbdb2315678afecb367f032d93f642f64180aa3")
        assert token_address_for("base", "USDC").lower() == "0x5fbdb2315678afecb367f032d93f642f64180aa3"


def test_explicit_rpc_list_stays_exclusive(monkeypatch):
    from aimarket_hub.deposit_verify import rpc_urls_for
    monkeypatch.setenv('AIMARKET_DEPOSIT_RPC_URL', ' https://first.test, https://second.test, ')
    monkeypatch.setenv('AIMARKET_RPC_BASE', 'https://must-not-fall-through.test')
    assert rpc_urls_for('base') == ['https://first.test', 'https://second.test']


def test_registry_chain_id_reads_a_comma_separated_override_like_the_verifier(monkeypatch):
    """rpc_urls_for() splits AIMARKET_DEPOSIT_RPC_URL on commas; registry_chain_id() passed the
    whole string to eth_chainId, so the claim registry could never key such a deposit."""
    from aimarket_hub import deposit_verify
    answers = {"https://a.example": 8453, "https://b.example": 8453, "https://c.example": 1}
    monkeypatch.setattr(deposit_verify, "_rpc_chain_id", lambda url, timeout=5.0: answers.get(url))
    monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "https://a.example, https://b.example")
    assert deposit_verify.registry_chain_id("base") == 8453
    monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "https://a.example,https://c.example")
    assert deposit_verify.registry_chain_id("base") is None  # nodes disagree: fail closed
    monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "https://down.example")
    assert deposit_verify.registry_chain_id("base") is None
