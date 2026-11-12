"""Replay of an already-stored escrow authorization abandons the hub's own claim."""
import sys
sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")
import pytest
from aimarket_hub.escrow_bridge import authorization, chain, store, eip712
from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization
from aimarket_hub.escrow_bridge.errors import AuthorizationRejected

_ESCROW = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
_HUB = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
_TOKEN = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
_ESCROW_CHANNEL = "0x" + "11" * 32
_RECEIPT = "0x" + "22" * 32
_CHAIN_ID = 8453
_ZERO = "0x" + "00" * 20
_KEY = "0x" + "42" * 32
_NOW = 1_000_000


def _payload(amount=1_000_000, receipt=_RECEIPT):
    from eth_account import Account
    auth = DebitAuthorization(channel_id=_ESCROW_CHANNEL, hub=_HUB, token=_TOKEN, amount=amount,
                              receipt_id=receipt, nonce=0, deadline=_NOW + 3600)
    digest = eip712.debit_digest(auth, chain_id=_CHAIN_ID, verifying_contract=_ESCROW)
    sig = Account._sign_hash(digest, Account.from_key(_KEY).key).signature.hex()
    return {**auth.as_message(), "signature": sig if sig.startswith("0x") else "0x" + sig}


def test_replay_abandons_the_delivered_claim(tmp_path, monkeypatch):
    from eth_account import Account
    monkeypatch.setenv("AIMARKET_ESCROW_CONTRACT", _ESCROW)
    monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", _HUB)
    ch = chain.EscrowChannel(channel_id=_ESCROW_CHANNEL, depositor=Account.from_key(_KEY).address,
                             hub=_ZERO, token=_TOKEN, deposit_amount=5_000_000, balance=5_000_000,
                             used_amount=0, expires_at=4_000_000_000, nonce=0, status=chain.STATUS_OPEN)
    monkeypatch.setattr(chain, "chain_id", lambda: _CHAIN_ID)
    monkeypatch.setattr(chain, "escrow_address", lambda: _ESCROW)
    monkeypatch.setattr(chain, "read_channel", lambda cid, address=None: ch)
    st = store.AuthorizationStore(str(tmp_path / "bridge.db"))
    args = dict(ledger_channel_id="ch_abc", escrow_channel_id=_ESCROW_CHANNEL,
                expected_amount_usd=1.0, expected_receipt_id=_RECEIPT, authorizations=st, now=_NOW)
    p = _payload()
    authorization.verify_and_store(payload=p, **args)          # call served & captured
    assert st.get(_RECEIPT).status == store.PENDING
    # Buyer replays the same signed authorization (e.g. with a wrong channel secret so the
    # idempotency middleware scopes it differently) -> refused...
    with pytest.raises(AuthorizationRejected) as exc:
        authorization.verify_and_store(payload=p, **args)
    print("refusal:", exc.value)
    row = st.get(_RECEIPT)
    print("status after replay:", row.status, row.last_error)
    print("unresolved:", st.unresolved())
    # ...but the hub's claim on the delivered call is gone
    assert row.status == store.ABANDONED
    assert st.unresolved() == []
