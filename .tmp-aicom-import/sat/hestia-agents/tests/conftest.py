"""Reach the sibling HESTIA sources when this package sits in the monorepo.

The admission tests want the real `hestia.scan.admit_handler` — asserting that a
handler passes a copy of the rules would prove nothing. Standalone checkouts do
not have the sibling, so those tests skip rather than fail.

The payment tests want a chain as well, and a wallet: `FakeWallet` and
`FakeChain` below stand in for both without a key, so that what the buyer was
told to sign and what it was told to send are held against each other.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import pytest

MONOREPO_HESTIA = Path(__file__).resolve().parent.parent.parent / "hestia"

if MONOREPO_HESTIA.is_dir() and str(MONOREPO_HESTIA) not in sys.path:
    sys.path.insert(0, str(MONOREPO_HESTIA))


def admit_handler_or_skip():
    try:
        from hestia.scan import admit_handler
    except ImportError:  # pragma: no cover - standalone checkout
        pytest.skip("sibling hestia/ sources are not on the path")
    return admit_handler


@pytest.fixture
def admit():
    return admit_handler_or_skip()


@pytest.fixture(autouse=True)
def no_payment_secret_in_the_environment(monkeypatch):
    """`call`, `compute` and `pay-compute` step 2 read HESTIA_PAYMENT_SECRET when no
    --secret is given. One left in the shell that runs the tests would be presented
    in every such call; each test that wants one sets it."""
    monkeypatch.delenv("HESTIA_PAYMENT_SECRET", raising=False)


class FakeNetwork:
    """The network under the `httpx` module the CLI imports, for one test.

    `httpx.post` and `httpx.Client` are swapped for versions that send every
    request through `handler` (an httpx.MockTransport handler) and keep it in
    `requests`, with the timeout it went out under in `timeouts`. The CLI's own
    `_client()` and `_http()` still run, so what they build is under test too.
    Without a handler a request fails the test: nothing leaves the process.
    """

    def __init__(self, httpx_module) -> None:
        self._httpx = httpx_module
        self._client_class = httpx_module.Client
        self.handler = None
        self.requests: list = []
        self.timeouts: list = []

    def _transport(self):
        def route(request):
            self.requests.append(request)
            if self.handler is None:
                raise AssertionError(f"unexpected request: {request.method} {request.url}")
            return self.handler(request)

        return self._httpx.MockTransport(route)

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.timeouts.append(timeout)
        with self._client_class(transport=self._transport()) as client:
            return client.post(url, json=json, headers=headers)

    def client(self, *, timeout=None):
        self.timeouts.append(timeout)
        return self._client_class(transport=self._transport(), timeout=timeout)


@pytest.fixture
def network(monkeypatch):
    httpx = pytest.importorskip("httpx")
    fake = FakeNetwork(httpx)
    monkeypatch.setattr(httpx, "post", fake.post)
    monkeypatch.setattr(httpx, "Client", fake.client)
    return fake


# ------------------------------------------------------------ wallet and chain

SELECTOR = "0xe3ee160e"  # transferWithAuthorization, as hestia_agents.x402 writes it
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AUTHORIZATION_USED_TOPIC = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
# The token the hearth's test settings name (hestia.config.Settings.for_test).
USDC_DOMAIN = {
    "name": "USD Coin",
    "version": "2",
    "chainId": 8453,
    "verifyingContract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}


def _authorized(domain: dict, message: dict) -> str:
    """What a signature commits to: EIP-712's struct hash, with sha256 for keccak.
    Every field the real one covers is here, so changing any one changes it."""
    fields = (
        domain["name"], str(domain["version"]), int(domain["chainId"]),
        domain["verifyingContract"].lower(), message["from"].lower(), message["to"].lower(),
        int(message["value"]), int(message["validAfter"]), int(message["validBefore"]),
        message["nonce"].lower(),
    )
    return hashlib.sha256(repr(fields).encode()).hexdigest()


class FakeWallet:
    """eth_signTypedData_v4 without a key: r is the digest of what was signed."""

    @staticmethod
    def sign(typed: dict) -> str:
        return "0x" + _authorized(typed["domain"], typed["message"]) + "22" * 32 + "1b"


def _topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


class FakeChain:
    """A token contract and the node in front of it.

    `send(calldata)` executes transferWithAuthorization as the token would. It
    cannot recover a signer, but it holds the signature to exactly the arguments
    in the calldata (r must be FakeWallet's digest of them under this token's
    domain), refuses a validBefore that has passed and a nonce already used, and
    reverts otherwise — as a real token reverts calldata that differs from what
    was signed. A mined transfer carries the Transfer and
    AuthorizationUsed(authorizer, nonce) logs the hearth reads; `rpc` answers the
    JSON-RPC calls hestia.payments makes.
    """

    def __init__(self, domain: dict | None = None) -> None:
        self.domain = domain or USDC_DOMAIN
        self.receipts: dict[str, dict] = {}
        self.used: set[str] = set()
        self.head = 100

    def send(self, data: str) -> str:
        assert data.startswith(SELECTOR) and len(data) == len(SELECTOR) + 9 * 64, data
        words = [data[len(SELECTOR) + i * 64:len(SELECTOR) + (i + 1) * 64] for i in range(9)]
        message = {
            "from": "0x" + words[0][24:],
            "to": "0x" + words[1][24:],
            "value": int(words[2], 16),
            "validAfter": int(words[3], 16),
            "validBefore": int(words[4], 16),
            "nonce": "0x" + words[5],
        }
        accepted = (
            words[7] == _authorized(self.domain, message)
            and message["validAfter"] <= time.time() < message["validBefore"]
            and message["nonce"] not in self.used
        )
        token = self.domain["verifyingContract"]
        logs = []
        if accepted:
            self.used.add(message["nonce"])
            # FiatToken's order: it marks the authorization used, then moves the money.
            logs = [
                {"address": token, "data": "0x",
                 "topics": [AUTHORIZATION_USED_TOPIC, _topic(message["from"]), message["nonce"]]},
                {"address": token, "data": hex(message["value"]),
                 "topics": [TRANSFER_TOPIC, _topic(message["from"]), _topic(message["to"])]},
            ]
        self.head += 1
        tx = "0x" + hashlib.sha256(f"{self.head}:{data}".encode()).hexdigest()
        self.receipts[tx] = {
            "status": "0x1" if accepted else "0x0",
            "blockNumber": hex(self.head),
            "logs": logs,
        }
        return tx

    def rpc(self, _url, method, params, _timeout):
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(params[0])
        if method == "eth_blockNumber":
            return hex(self.head + 1)
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(int(time.time()))}
        raise AssertionError(f"unexpected rpc {method}")


def hestia_or_skip():
    """(TestClient, build_app, Settings) from the sibling hearth, or a skip."""
    try:
        from fastapi.testclient import TestClient
        from hestia.app import build_app
        from hestia.config import Settings
    except ImportError:  # pragma: no cover - standalone checkout
        pytest.skip("sibling hestia/ sources (and fastapi) are not importable")
    return TestClient, build_app, Settings


@pytest.fixture
def hestia_parts():
    return hestia_or_skip()


@pytest.fixture
def wallet():
    return FakeWallet()


@pytest.fixture
def chain(monkeypatch):
    """A FakeChain, and the one an in-process hearth reads its payments from."""
    fake = FakeChain()
    try:
        import hestia.payments
    except ImportError:  # pragma: no cover - standalone checkout
        return fake
    monkeypatch.setattr(hestia.payments, "_rpc", fake.rpc)
    return fake
