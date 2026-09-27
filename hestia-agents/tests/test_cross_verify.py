"""Compute and cross-verify against hearths faked at the HTTP layer.

test_compute_client.py runs two real hearths in-process, which proves the client
and the hearth agree; but a real hearth only ever answers well. These fakes
answer the way a broken or dishonest one would: a 500, a body that is not JSON,
a missing field, a receipt edited after it was signed, one key behind both URLs.
Each of those must end as a refusal (exit 1) or a DISAGREE, never as an AGREE
or a traceback. The requests are asserted too, in order: a cross-check that pays
a hearth before it knows the comparison can mean anything has already spent the
buyer's money on nothing.

The fakes sign with their own spelling of the hearth's canonical form
(hestia/signing.py object_canonical) rather than the client's, so a client that
drifted from the wire format would fail here instead of agreeing with itself.
The input and the signed .well-known carry text outside ASCII for the same
reason: escaped and raw UTF-8 are different bytes, so a client that escaped
would compute other digests and check other signed bytes than the hearth's.

The direct paid door (pay-compute, then compute --tx --secret) is held to the
same standard: a payment it builds must be one only its secret redeems, and a
402 it cannot build that payment from, or a secret the door would refuse as
guessable, is refused in one line before anything is signed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import sys
import types
import uuid
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from hestia_agents import cli
from hestia_agents.compute import (
    CROSS_METHOD,
    RECEIPT_KIND,
    RUN,
    VERIFY,
    ComputeClientError,
    PaymentRequired,
    awr_verdict,
    call,
    cross_verify,
    payment_terms,
)
from hestia_agents.manifests import handler_source
from hestia_agents.x402 import TRANSFER_WITH_AUTHORIZATION_SELECTOR, calldata, typed_data

A = "http://hearth-a.test"
B = "http://hearth-b.test"
SLUG = "json-canonical"
DOCUMENT = {"document": {"b": 1, "a": [1, 2], "name": "Zoë Ångström"}}
FUNCTION_SHA = hashlib.sha256(handler_source(SLUG).encode()).hexdigest()
OTHER_SHA = "e" * 64
INVOKE = "/ai-market/v2/invoke"
WELL_KNOWN = "/.well-known/ai-market.json"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
COMPUTE_WALLET = "0x" + "c0" * 20
BUYER = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
# 32 bytes as random ones look; "5e" * 32 is a pattern the hearth refuses as guessable.
SECRET = "0x" + hashlib.sha256(b"the buyer's payment secret").hexdigest()
GUESSABLE = "0x" + "5e" * 32
GUESSED = (
    "is guessable (fewer than 16 distinct bytes): anyone could open its nonce; "
    "use 32 random bytes"
)
SECRET_NONCE = "0x" + hashlib.sha256(bytes.fromhex(SECRET[2:])).hexdigest()
TX = "0x" + "9" * 64
SIGNATURE = "0x" + "11" * 32 + "22" * 32 + "1b"


def compute_quote(**over) -> dict:
    """A compute 402 in the shape hestia/app.py _compute_unpaid answers with."""
    body = {
        "ok": False,
        "error": "payment_required",
        "detail": "compute is priced",
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": "1000",
            "asset": USDC,
            "payTo": COMPUTE_WALLET,
            "extra": {"name": "USD Coin", "version": "2", "decimals": 6, "symbol": "USDC",
                      "chainId": 8453, "verifyingContract": USDC},
        }],
        "pay_to": COMPUTE_WALLET,
        "amount_usd": 0.001,
        "amount_units": "1000",
        "chain": "base",
        "token": "USDC",
        "token_contract": USDC,
        "binding": "secret",
        "nonce_rule": "sha256(secret)",
        "max_age_s": 3600,
    }
    body.update(over)
    return body


def wire_canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(wire_canonical(value)).hexdigest()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def reply(status: int, body: Any) -> httpx.Response:
    # Serialised here rather than by httpx, so a hearth can send NaN as a broken one might.
    return httpx.Response(
        status, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
    )


def canonicalise(payload: dict) -> dict:
    return {"canonical": wire_canonical(payload["document"]).decode()}


class FakeHearth:
    """One hearth: a signed .well-known, a signed compute catalogue, and an invoke
    door that runs `function` and signs a receipt shaped as COMPUTE.md describes.
    Every attribute is a way to make it answer wrongly."""

    def __init__(
        self,
        url: str,
        *,
        key: Ed25519PrivateKey | None = None,
        python_version: str = "3.12.13",
        platform: str = "Linux-6.8.0-x86_64",
    ) -> None:
        self.url = url
        self.key = key or Ed25519PrivateKey.generate()
        self.enabled = True
        self.functions: list[dict] = [
            {"slug": SLUG, "function_sha256": FUNCTION_SHA, "admissible": True}
        ]
        self.function = canonicalise
        self.facts = {"python_version": python_version, "platform": platform}
        self.catalogue_key: Ed25519PrivateKey | None = None
        self.well_known_forged: dict = {}
        self.receipt_changes: dict = {}  # before signing: the hearth itself says something odd
        self.receipt_forged: dict = {}  # after signing: an edit the signature does not cover
        self.receipt_key: Ed25519PrivateKey | None = None  # signs, and names itself, instead
        self.receipt_algorithm = "ed25519"
        self.envelope_omits: tuple[str, ...] = ()
        self.replies: dict[str, httpx.Response] = {}

    @property
    def public_key(self) -> str:
        return b64(self.key.public_key().public_bytes_raw())

    @property
    def receipt_id(self) -> str:
        return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, self.url)}"

    def sign(
        self, document: dict, key: Ed25519PrivateKey | None = None, algorithm: str = "ed25519"
    ) -> dict:
        # The block names whichever key signed, as a real one would: a check that
        # trusted the block's own public_key would then pass a stranger's receipt.
        signer = key or self.key
        block = {
            "algorithm": algorithm,
            "public_key": b64(signer.public_key().public_bytes_raw()),
            "value": b64(signer.sign(wire_canonical(document))),
        }
        return {**document, "signature": block}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self.replies:
            return self.replies[path]
        if request.method == "GET" and path == WELL_KNOWN:
            document = self.sign(
                {"hearth": self.url, "operator": "Hestia Zoë", "signer_public_key": self.public_key}
            )
            return reply(200, {**document, **self.well_known_forged})
        if request.method == "GET" and path == "/v1/compute":
            listing = {"enabled": self.enabled, "functions": self.functions}
            return reply(200, self.sign(listing, self.catalogue_key))
        if request.method == "POST" and path == INVOKE:
            return self.invoke(json.loads(request.content))
        return reply(404, {"detail": f"no route {request.method} {path}"})

    def invoke(self, sent: dict) -> httpx.Response:
        capability, job = sent["capability_id"], sent["input"]
        output = self.function(job["input"])
        replicas = 2 if capability == VERIFY else 1
        receipt = {
            "kind": RECEIPT_KIND,
            "id": self.receipt_id,
            "capability_id": capability,
            "method": "hestia.replicate@v1" if replicas == 2 else "hestia.run@v1",
            "replicas": replicas,
            "hearth": self.url,
            "slug": job["slug"],
            "function_sha256": FUNCTION_SHA,
            "input_sha256": digest(job["input"]),
            "output_sha256": digest(output),
            "cpu_ms": [4] * replicas,
            "max_rss_kb": [9000] * replicas,
            "wall_ms": [21] * replicas,
            "runtime": "subprocess",
            **self.facts,
            "same_operator": True,
        }
        receipt.update(self.receipt_changes)
        signed = self.sign(receipt, self.receipt_key, self.receipt_algorithm)
        receipt = {**signed, **self.receipt_forged}
        envelope = {
            "ok": True,
            "result": {"output": output, "compute_receipt": receipt},
            "signature": "host-envelope-signature",
            "provider_pubkey": self.public_key,
        }
        return reply(200, {k: v for k, v in envelope.items() if k not in self.envelope_omits})


class Hearths:
    """Routes each request to the fake hearth its host names."""

    def __init__(self, *hearths: FakeHearth) -> None:
        self.by_host = {httpx.URL(h.url).host: h for h in hearths}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return self.by_host[request.url.host](request)


class FakeAwr(types.ModuleType):
    """Stands in for the awr package: records what it is asked to sign."""

    class SigningKey:
        def __init__(self, did: str) -> None:
            self.did = did

        @classmethod
        def generate(cls):
            return cls("did:key:zEphemeral")

    def __init__(self) -> None:
        super().__init__("awr")
        self.issued: list[tuple[dict, Any]] = []
        self.key_files: list[str] = []

    def load_key_file(self, path: str):
        self.key_files.append(path)
        return self.SigningKey("did:key:zBuyer")

    @staticmethod
    def canonical_sri(document: dict) -> str:
        return "sha256-" + digest(document)

    def issue_verification_verdict(self, subject: dict, key) -> dict:
        self.issued.append((subject, key))
        return {"issuer": {"id": key.did}, "credentialSubject": subject}


@pytest.fixture
def hearths(network):
    pair = FakeHearth(A), FakeHearth(B)
    network.handler = Hearths(*pair)
    return pair


@pytest.fixture
def fake_awr(monkeypatch):
    module = FakeAwr()
    monkeypatch.setitem(sys.modules, "awr", module)
    return module


@pytest.fixture
def no_awr(monkeypatch):
    # A None entry makes `import awr` raise ImportError, installed or not.
    monkeypatch.setitem(sys.modules, "awr", None)


def posts(network) -> list[httpx.Request]:
    return [r for r in network.requests if r.method == "POST"]


def disagreeing(payload: dict) -> dict:
    # Valid JSON, honestly signed, and not the canonical form: a different answer.
    return {"canonical": json.dumps(payload["document"])}


# ------------------------------------------------------------ one call


def test_a_call_fetches_the_key_then_posts_the_documented_body(network, hearths) -> None:
    a, _ = hearths
    with network.client() as client:
        checked = call(client, A + "/", SLUG, DOCUMENT)

    assert [(r.method, str(r.url)) for r in network.requests] == [
        ("GET", f"{A}{WELL_KNOWN}"),
        ("POST", f"{A}{INVOKE}"),
    ]
    post = network.requests[1]
    assert json.loads(post.content) == {
        "capability_id": RUN,
        "input": {"slug": SLUG, "input": DOCUMENT},
    }
    assert "x-api-key" not in post.headers
    assert "x-payment" not in post.headers
    assert checked.problems == []
    assert checked.public_key == a.public_key
    assert checked.output == {"canonical": '{"a":[1,2],"b":1,"name":"Zoë Ångström"}'}
    assert checked.receipt["id"] == a.receipt_id


def test_a_call_carries_the_pin_the_hub_key_and_the_payment_it_is_given(network, hearths) -> None:
    with network.client() as client:
        checked = call(
            client, A, SLUG, DOCUMENT, capability_id=VERIFY, function_sha256=FUNCTION_SHA,
            api_key="hub-key", tx_hash="0xfeed",
        )

    post = posts(network)[0]
    assert json.loads(post.content) == {
        "capability_id": VERIFY,
        "input": {"slug": SLUG, "input": DOCUMENT, "function_sha256": FUNCTION_SHA},
    }
    assert post.headers["x-api-key"] == "hub-key"
    assert post.headers["x-payment"] == "0xfeed"
    assert "x-payment-secret" not in post.headers
    assert checked.problems == []
    assert checked.receipt["replicas"] == 2


def test_a_direct_payment_carries_the_secret_its_nonce_commits_to(network, hearths) -> None:
    with network.client() as client:
        call(client, A, SLUG, DOCUMENT, tx_hash=TX, payment_secret=SECRET)

    post = posts(network)[0]
    assert (post.headers["x-payment"], post.headers["x-payment-secret"]) == (TX, SECRET)
    assert "x-api-key" not in post.headers


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"payment_secret": SECRET},
         "a payment secret redeems a payment: send it with the transaction (tx_hash)"),
        ({"payment_secret": SECRET[:-2], "tx_hash": TX},
         "the payment secret is not 0x followed by 64 hex digits"),
        ({"payment_secret": SECRET_NONCE[2:], "tx_hash": TX},
         "the payment secret is not 0x followed by 64 hex digits"),
        # Well formed, and refused at the key-less door after the buyer paid under it.
        ({"payment_secret": GUESSABLE, "tx_hash": TX}, f"the payment secret {GUESSED}"),
        ({"payment_secret": "0x" + bytes(range(15)).hex() + "00" * 17, "tx_hash": TX},
         f"the payment secret {GUESSED}"),
    ],
    ids=["no-transaction", "short", "unprefixed", "one-byte-repeated", "fifteen-distinct"],
)
def test_a_secret_that_cannot_redeem_anything_is_refused_before_sending(
    network, hearths, kwargs, message
) -> None:
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        call(client, A, SLUG, DOCUMENT, **kwargs)
    assert str(refused.value) == message
    assert network.requests == []


def test_a_key_already_known_is_not_fetched_again(network, hearths) -> None:
    a, _ = hearths
    with network.client() as client:
        call(client, A, SLUG, DOCUMENT, public_key=a.public_key)
    assert [(r.method, r.url.path) for r in network.requests] == [("POST", INVOKE)]


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (httpx.Response(502, text="<html>bad gateway</html>"), f"{A}: HTTP 502, not JSON"),
        (reply(200, [1, 2]), f"{A}: not a JSON object"),
        (reply(409, {"detail": "pinned function_sha256 differs"}),
         f"{A}: HTTP 409 pinned function_sha256 differs"),
        (reply(404, {"detail": "no such function"}), f"{A}: HTTP 404 no such function"),
        (reply(500, {"error": "boom"}), f"{A}: HTTP 500 {{'error': 'boom'}}"),
        (reply(200, {"ok": False, "refuse_reason": "replicas_disagree", "detail": "bytes differ"}),
         f"{A}: replicas_disagree: bytes differ"),
        (reply(200, {"ok": False, "refuse_reason": "function_error"}), f"{A}: function_error:"),
        (reply(200, {"ok": True, "result": "not an object"}),
         f"{A}: the answer carries no compute receipt"),
        (reply(200, {"ok": True, "result": {"output": {}}}),
         f"{A}: the answer carries no compute receipt"),
    ],
    ids=["5xx-html", "json-list", "409", "404", "500-json", "ok-false", "ok-false-no-detail",
         "result-not-object", "no-receipt"],
)
def test_an_answer_that_is_not_a_signed_result_is_refused(
    network, hearths, answer, message
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = answer
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        call(client, A, SLUG, DOCUMENT)
    assert str(refused.value) == message
    assert not isinstance(refused.value, PaymentRequired)


def test_a_402_hands_the_quote_to_the_buyer(network, hearths) -> None:
    a, _ = hearths
    terms = {"ok": False, "detail": "send 0.01 USDC", "pay_to": "0x" + "c0" * 20}
    a.replies[INVOKE] = reply(402, terms)
    with network.client() as client, pytest.raises(PaymentRequired) as needed:
        call(client, A, SLUG, DOCUMENT)
    assert needed.value.quote == terms
    assert str(needed.value) == "send 0.01 USDC"

    a.replies[INVOKE] = reply(402, {"ok": False})
    with network.client() as client, pytest.raises(PaymentRequired) as needed:
        call(client, A, SLUG, DOCUMENT)
    assert str(needed.value) == "payment required"


@pytest.mark.parametrize(
    "spoil",
    [
        lambda h: h.well_known_forged.update({"hearth": "http://someone-else.test"}),
        lambda h: h.well_known_forged.update({"signer_public_key": FakeHearth(B).public_key}),
        lambda h: h.replies.update(
            {WELL_KNOWN: reply(200, h.sign({"hearth": h.url}))}
        ),
    ],
    ids=["edited-after-signing", "names-another-key", "names-no-key"],
)
def test_a_well_known_not_signed_by_the_key_it_names_stops_the_call(
    network, hearths, spoil
) -> None:
    a, _ = hearths
    spoil(a)
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        call(client, A, SLUG, DOCUMENT)
    assert str(refused.value) == f"{A}: .well-known is not signed by the key it names"
    assert posts(network) == []


@pytest.mark.parametrize(
    ("kwargs", "changes", "forged", "problems"),
    [
        ({}, {"kind": "hestia.other@v1"}, {}, ["unknown receipt kind 'hestia.other@v1'"]),
        ({}, {"capability_id": VERIFY}, {}, ["the receipt is for a different capability"]),
        ({"function_sha256": OTHER_SHA}, {}, {},
         ["the receipt names a different function than the one pinned"]),
        ({}, {"input_sha256": "0" * 64}, {},
         ["the receipt names a different input than the one sent"]),
        ({}, {"output_sha256": "0" * 64}, {},
         ["the output returned does not match the digest the receipt signs"]),
        ({}, {}, {"cpu_ms": [1]},
         ["the receipt is not signed by this hearth's published key"]),
    ],
    ids=["kind", "capability", "pinned-function", "input", "output", "edited-after-signing"],
)
def test_each_thing_wrong_with_a_receipt_is_named(
    network, hearths, kwargs, changes, forged, problems
) -> None:
    a, _ = hearths
    a.receipt_changes, a.receipt_forged = changes, forged
    with network.client() as client:
        checked = call(client, A, SLUG, DOCUMENT, **kwargs)
    assert checked.problems == problems


def test_an_output_that_cannot_be_canonicalised_is_a_problem_not_a_crash(network, hearths) -> None:
    a, _ = hearths
    a.function = lambda _payload: {"value": float("nan")}
    with network.client() as client:
        checked = call(client, A, SLUG, DOCUMENT)
    assert checked.problems == ["the output returned does not match the digest the receipt signs"]


@pytest.mark.parametrize(
    "spoil",
    [
        lambda h: setattr(h, "receipt_key", Ed25519PrivateKey.generate()),
        lambda h: setattr(h, "receipt_algorithm", "rsa"),
    ],
    ids=["another-key-naming-itself", "not-ed25519"],
)
def test_a_receipt_signed_by_anything_but_the_published_ed25519_key_is_named(
    network, hearths, spoil
) -> None:
    a, _ = hearths
    spoil(a)
    with network.client() as client:
        checked = call(client, A, SLUG, DOCUMENT)

    assert checked.problems == ["the receipt is not signed by this hearth's published key"]
    # Neither receipt is garbage: its bytes verify under the key its own block
    # names. What refuses it is the published key and the algorithm, which is
    # the point: a check that believed the block would have passed it.
    block = checked.receipt["signature"]
    named = Ed25519PublicKey.from_public_bytes(base64.b64decode(block["public_key"]))
    body = {k: v for k, v in checked.receipt.items() if k != "signature"}
    named.verify(base64.b64decode(block["value"]), wire_canonical(body))


def test_an_answer_without_ok_is_judged_by_its_receipt(network, hearths) -> None:
    # Only an explicit ok: false is a refusal, as the hearth itself reads its
    # workers' envelopes; what a buyer relies on is the signed receipt.
    a, _ = hearths
    a.envelope_omits = ("ok",)
    with network.client() as client:
        checked = call(client, A, SLUG, DOCUMENT)
    assert checked.problems == []
    assert checked.output == canonicalise(DOCUMENT)


# ---------------------------------------------------------- cross-check


def test_two_hearths_that_agree(network, hearths) -> None:
    a, b = hearths
    with network.client() as client:
        check = cross_verify(client, (A, B), SLUG, DOCUMENT, api_key="hub-key")

    assert check.agree is True
    assert check.function_sha256 == FUNCTION_SHA
    assert check.input_sha256 == digest(DOCUMENT)
    assert (check.first.hearth, check.second.hearth) == (A, B)
    assert (check.first.public_key, check.second.public_key) == (a.public_key, b.public_key)
    assert (check.first.receipt["id"], check.second.receipt["id"]) == (a.receipt_id, b.receipt_id)
    assert check.notes == []
    # Both keys and both listings are settled before either hearth is paid, and
    # each key is fetched once.
    assert [(r.method, str(r.url)) for r in network.requests] == [
        ("GET", f"{A}{WELL_KNOWN}"),
        ("GET", f"{B}{WELL_KNOWN}"),
        ("GET", f"{A}/v1/compute"),
        ("GET", f"{B}/v1/compute"),
        ("POST", f"{A}{INVOKE}"),
        ("POST", f"{B}{INVOKE}"),
    ]
    for post in posts(network):
        assert json.loads(post.content)["input"]["function_sha256"] == FUNCTION_SHA
        assert post.headers["x-api-key"] == "hub-key"


def test_two_honest_hearths_with_different_outputs_disagree(network, hearths) -> None:
    _, b = hearths
    b.function = disagreeing
    with network.client() as client:
        check = cross_verify(client, (A, B), SLUG, DOCUMENT)
    assert check.agree is False
    assert check.first.problems == [] and check.second.problems == []
    assert check.first.receipt["output_sha256"] != check.second.receipt["output_sha256"]


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (reply(500, {"detail": "worker crashed"}), f"{B}: HTTP 500 worker crashed"),
        (reply(404, {"detail": "no such function"}), f"{B}: HTTP 404 no such function"),
        (httpx.Response(502, text="<html>bad gateway</html>"), f"{B}: HTTP 502, not JSON"),
        (reply(200, {"ok": False, "refuse_reason": "wall_time_exceeded"}),
         f"{B}: wall_time_exceeded:"),
        (reply(200, {"ok": True, "result": {}}), f"{B}: the answer carries no compute receipt"),
    ],
    ids=["500", "404", "not-json", "ok-false", "no-receipt"],
)
def test_one_hearth_failing_fails_the_cross_check(network, hearths, answer, message) -> None:
    _, b = hearths
    b.replies[INVOKE] = answer
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        cross_verify(client, (A, B), SLUG, DOCUMENT)
    assert str(refused.value) == message


RECEIPT_PROBLEMS = [
    "the receipt is not signed by this hearth's published key",
    "the receipt names a different input than the one sent",
    "the output returned does not match the digest the receipt signs",
]


def spoil_receipt(hearth: FakeHearth) -> None:
    # Signed over another input, then its output digest edited: three problems at once.
    hearth.receipt_changes = {"input_sha256": "0" * 64}
    hearth.receipt_forged = {"output_sha256": digest({"canonical": "{}"})}


@pytest.mark.parametrize(
    "spoiled", [(A,), (B,), (A, B)], ids=["first", "second", "both"]
)
def test_a_bad_receipt_from_either_side_is_named_and_fails_the_cross_check(
    network, hearths, spoiled
) -> None:
    for hearth in hearths:
        if hearth.url in spoiled:
            spoil_receipt(hearth)
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        cross_verify(client, (A, B), SLUG, DOCUMENT)
    # Every problem, each under the hearth that caused it, the first hearth first.
    assert str(refused.value) == "; ".join(
        f"{url}: {problem}" for url in spoiled for problem in RECEIPT_PROBLEMS
    )


def test_a_platform_difference_is_noted_but_does_not_decide(network) -> None:
    network.handler = Hearths(
        FakeHearth(A),
        FakeHearth(B, python_version="3.11.9", platform="macOS-15.3-arm64"),
    )
    with network.client() as client:
        check = cross_verify(client, (A, B), SLUG, DOCUMENT)
    assert check.agree is True
    assert check.notes == [
        "python_version differs (3.12.13 vs 3.11.9): "
        "a disagreement may be the platform, not the operator",
        "platform differs (Linux-6.8.0-x86_64 vs macOS-15.3-arm64): "
        "a disagreement may be the platform, not the operator",
    ]


@pytest.mark.parametrize(
    ("spoil", "message"),
    [
        (lambda a, b: setattr(b, "key", a.key), "both hearths sign with the same key"),
        (lambda a, b: setattr(
            b, "functions", [{"slug": SLUG, "function_sha256": OTHER_SHA, "admissible": True}]),
         f"{B} lists '{SLUG}' as {OTHER_SHA}, not {FUNCTION_SHA}: a different function"),
        (lambda a, b: setattr(b, "functions", [
            {"slug": SLUG, "function_sha256": FUNCTION_SHA, "admissible": False,
             "refused": "reads the clock"}]),
         f"'{SLUG}' is listed but not admissible for compute: reads the clock"),
        (lambda a, b: setattr(b, "functions", []), f"no compute function '{SLUG}' is listed"),
        (lambda a, b: setattr(b, "enabled", False), f"{B} does not sell compute"),
        (lambda a, b: setattr(b, "catalogue_key", Ed25519PrivateKey.generate()),
         f"{B}: the compute catalogue is not signed by its key"),
        (lambda a, b: b.well_known_forged.update({"hearth": "http://elsewhere.test"}),
         f"{B}: .well-known is not signed by the key it names"),
        (lambda a, b: b.replies.update({WELL_KNOWN: httpx.Response(503, text="down")}),
         f"{B}{WELL_KNOWN}: HTTP 503, not JSON"),
    ],
    ids=["same-key", "other-bytes", "inadmissible", "unlisted", "compute-off",
         "catalogue-other-key", "well-known-edited", "well-known-not-json"],
)
def test_a_cross_check_that_could_not_mean_anything_is_refused_before_paying(
    network, hearths, spoil, message
) -> None:
    spoil(*hearths)
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        cross_verify(client, (A, B), SLUG, DOCUMENT)
    assert message in str(refused.value)
    assert posts(network) == []


def test_a_buyer_pin_stands_in_for_the_first_listing_but_must_match_the_second(
    network, hearths
) -> None:
    a, _ = hearths
    a.functions = []  # not consulted: the buyer named the bytes
    with network.client() as client:
        check = cross_verify(client, (A, B), SLUG, DOCUMENT, function_sha256=FUNCTION_SHA)
    assert check.agree is True and check.function_sha256 == FUNCTION_SHA
    assert f"{A}/v1/compute" not in [str(r.url) for r in network.requests]

    network.requests.clear()
    with network.client() as client, pytest.raises(ComputeClientError, match="a different"):
        cross_verify(client, (A, B), SLUG, DOCUMENT, function_sha256=OTHER_SHA)
    assert posts(network) == []


def no_digest_listed(url: str) -> str:
    return (
        f"{url} lists '{SLUG}' with no function_sha256: there are no bytes to pin, "
        "so the two hearths could run different functions and still agree"
    )


@pytest.mark.parametrize(
    ("unlisted", "pin", "refused_for"),
    [
        ((A, B), "", A),
        ((A,), "", A),
        ((B,), "", B),
        ((B,), FUNCTION_SHA, B),
    ],
    ids=["both", "first", "second", "second-under-a-buyer-pin"],
)
@pytest.mark.parametrize("unlisted_as", [None, ""], ids=["absent", "empty"])
def test_listings_without_a_function_digest_are_refused_before_paying(
    network, hearths, unlisted, pin, refused_for, unlisted_as
) -> None:
    for hearth in hearths:
        if hearth.url in unlisted:
            listing = {"slug": SLUG, "admissible": True}
            if unlisted_as is not None:
                listing["function_sha256"] = unlisted_as
            hearth.functions = [listing]
        # What the refusal prevents: unpinned, B could run other bytes and still pass.
        hearth.receipt_changes = {"function_sha256": OTHER_SHA} if hearth.url == B else {}
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        cross_verify(client, (A, B), SLUG, DOCUMENT, function_sha256=pin)
    assert str(refused.value) == no_digest_listed(refused_for)
    assert posts(network) == []


def test_a_trailing_slash_on_either_hearth_is_not_sent(network, hearths) -> None:
    with network.client() as client:
        check = cross_verify(client, (A + "/", B + "/"), SLUG, DOCUMENT)
    assert check.agree is True
    assert [(r.method, str(r.url)) for r in network.requests] == [
        ("GET", f"{A}{WELL_KNOWN}"),
        ("GET", f"{B}{WELL_KNOWN}"),
        ("GET", f"{A}/v1/compute"),
        ("GET", f"{B}/v1/compute"),
        ("POST", f"{A}{INVOKE}"),
        ("POST", f"{B}{INVOKE}"),
    ]


# ------------------------------------------------------------ AWR verdict


@pytest.mark.parametrize(("function", "verdict", "score"), [
    (canonicalise, "pass", "1"),
    (disagreeing, "fail", "0"),
])
def test_the_verdict_judges_the_first_receipt_with_the_second_as_evidence(
    network, hearths, fake_awr, function, verdict, score
) -> None:
    _, b = hearths
    b.function = function
    with network.client() as client:
        check = cross_verify(client, (A, B), SLUG, DOCUMENT)
    key = fake_awr.SigningKey("did:key:zBuyer")

    document = awr_verdict(check, key)

    ((subject, signer),) = fake_awr.issued
    assert signer is key
    assert document == {"issuer": {"id": "did:key:zBuyer"}, "credentialSubject": subject}
    assert subject["verifiedWork"] == {
        "id": check.first.receipt["id"],
        "digestSRI": "sha256-" + digest(check.first.receipt),
    }
    assert subject["evidence"] == [
        {"kind": "hestia-compute-receipt", "digestSRI": "sha256-" + digest(check.second.receipt)}
    ]
    assert (subject["verdict"], subject["score"]) == (verdict, score)
    assert subject["method"]["id"] == CROSS_METHOD
    assert subject["method"]["name"]


def test_a_verdict_without_the_awr_package_is_a_client_error(network, hearths, no_awr) -> None:
    with network.client() as client:
        check = cross_verify(client, (A, B), SLUG, DOCUMENT)
    with pytest.raises(ComputeClientError, match="needs the awr package"):
        awr_verdict(check, object())


# -------------------------------------------------------------- CLI compute


def compute_argv(*extra: str) -> list[str]:
    return ["compute", SLUG, "--hearth", A, "--input", json.dumps(DOCUMENT), *extra]


def test_cli_compute_prints_the_checked_receipt(
    network, hearths, tmp_path, monkeypatch, capsys
) -> None:
    a, _ = hearths
    monkeypatch.delenv("HESTIA_COMPUTE_API_KEY", raising=False)
    document = tmp_path / "doc.json"
    document.write_text(json.dumps(DOCUMENT), encoding="utf-8")

    assert cli.main(["compute", SLUG, "--hearth", A, "--input", f"@{document}"]) == 0

    output = canonicalise(DOCUMENT)
    assert capsys.readouterr().out.splitlines() == [
        "  result    : " + json.dumps(output, sort_keys=True),
        f"  hearth    : {A}",
        f"  key       : {a.public_key[:44]}...",
        "  method    : hestia.run@v1  replicas=1",
        f"  function  : {FUNCTION_SHA}",
        f"  input     : {digest(DOCUMENT)}",
        f"  output    : {digest(output)}",
        "  measured  : cpu_ms=[4] max_rss_kb=[9000] wall_ms=[21]",
        "  runtime   : subprocess python 3.12.13 on Linux-6.8.0-x86_64  same_operator=True",
    ]
    (post,) = posts(network)
    assert json.loads(post.content)["input"]["input"] == DOCUMENT
    assert "x-api-key" not in post.headers
    assert network.timeouts == [40.0]


def test_cli_compute_sends_the_hub_key_and_never_prints_it(
    network, hearths, monkeypatch, capsys
) -> None:
    from_env = "env-hub-key-" + "e" * 20
    from_flag = "flag-hub-key-" + "f" * 20
    monkeypatch.setenv("HESTIA_COMPUTE_API_KEY", f"  {from_env} ")

    assert cli.main(compute_argv()) == 0
    assert cli.main(compute_argv("--api-key", from_flag)) == 0

    env_call, flag_call = posts(network)
    assert env_call.headers["x-api-key"] == from_env
    assert flag_call.headers["x-api-key"] == from_flag
    out = capsys.readouterr().out
    assert from_env not in out and from_flag not in out


def test_cli_compute_passes_the_pin_the_payment_and_the_replicated_sku(
    network, hearths, capsys
) -> None:
    assert cli.main(compute_argv("--pin", FUNCTION_SHA, "--tx", "0xfeed", "--replicated")) == 0

    (post,) = posts(network)
    assert json.loads(post.content) == {
        "capability_id": VERIFY,
        "input": {"slug": SLUG, "input": DOCUMENT, "function_sha256": FUNCTION_SHA},
    }
    assert post.headers["x-payment"] == "0xfeed"
    assert "  method    : hestia.replicate@v1  replicas=2" in capsys.readouterr().out


def test_cli_compute_prints_every_problem_and_exits_1(network, hearths, capsys) -> None:
    a, _ = hearths
    a.receipt_changes = {"kind": "hestia.other@v1", "input_sha256": "0" * 64}

    assert cli.main(compute_argv()) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("  result    : ")  # what came back is still shown
    assert lines[-2:] == [
        "  PROBLEM   : unknown receipt kind 'hestia.other@v1'",
        "  PROBLEM   : the receipt names a different input than the one sent",
    ]


@pytest.mark.parametrize(
    ("terms", "lines"),
    [
        ({"ok": False, "detail": "send 0.01 USDC", "pay_to": "0x" + "c0" * 20,
          "amount_usd": 0.01, "token": "USDC", "chain": "base", "binding": "address"},
         ["  402 send 0.01 USDC",
          "  pay       : 0.01 USDC on base",
          "  to        : 0x" + "c0" * 20 + "  (compute payments only; no nonce)",
          "  then      : compute ... --tx <tx hash>"]),
        ({"ok": False, "detail": "buy this through the hub"}, ["  402 buy this through the hub"]),
        (compute_quote(detail="send X-Payment-Secret"),
         ["  402 send X-Payment-Secret",
          "  pay       : 0.001 USDC on base",
          f"  to        : {COMPUTE_WALLET}  (compute payments only)",
          "  bound by  : a secret you choose; the nonce you sign is its sha256",
          f"  build it  : hestia-agents pay-compute {SLUG} --hearth {A} --from 0xYOURADDRESS",
          "  then      : compute ... --tx <tx hash> --secret <secret>"]),
    ],
    ids=["older-hearth-by-address", "without-address", "by-secret"],
)
def test_cli_compute_402_prints_the_terms_it_was_given_and_exits_2(
    network, hearths, capsys, terms, lines
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, terms)
    assert cli.main(compute_argv()) == 2
    assert capsys.readouterr().out.splitlines() == lines


def test_cli_compute_402_names_the_sku_it_was_asked_for(network, hearths, capsys) -> None:
    # The price differs between run and verify: pay-compute must quote the same one.
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    assert cli.main(compute_argv("--replicated")) == 2
    assert (
        f"  build it  : hestia-agents pay-compute {SLUG} --hearth {A} --replicated "
        "--from 0xYOURADDRESS"
    ) in capsys.readouterr().out.splitlines()


def test_cli_compute_presents_the_secret_with_the_payment(network, hearths) -> None:
    assert cli.main(compute_argv("--tx", TX, "--secret", SECRET)) == 0

    (post,) = posts(network)
    assert (post.headers["x-payment"], post.headers["x-payment-secret"]) == (TX, SECRET)


def test_cli_compute_reads_the_secret_from_a_file_or_the_environment(
    network, hearths, monkeypatch, tmp_path
) -> None:
    kept = tmp_path / "secret"
    kept.write_text(f"{SECRET}\n", encoding="utf-8")

    assert cli.main(compute_argv("--tx", TX, "--secret", f"@{kept}")) == 0
    monkeypatch.setenv("HESTIA_PAYMENT_SECRET", SECRET)
    assert cli.main(compute_argv("--tx", TX)) == 0
    # Without a payment the environment's secret stays where it is.
    assert cli.main(compute_argv()) == 0

    from_file, from_env, unpaid = posts(network)
    assert from_file.headers["x-payment-secret"] == SECRET
    assert from_env.headers["x-payment-secret"] == SECRET
    assert "x-payment-secret" not in unpaid.headers


def test_cli_compute_refuses_a_secret_file_it_cannot_read(
    network, hearths, capsys, tmp_path
) -> None:
    missing = tmp_path / "no-such-secret"
    assert cli.main(compute_argv("--tx", TX, "--secret", f"@{missing}")) == 1
    assert capsys.readouterr().out == (
        f"  refused   : --secret cannot read {missing}: No such file or directory\n"
    )
    assert network.requests == []


@pytest.mark.parametrize(
    "terms",
    [compute_quote(detail="that payment secret does not open its nonce"),
     {"ok": False, "detail": "that payment secret does not open its nonce"}],
    ids=["with-terms", "without-terms"],
)
def test_cli_compute_402_after_a_payment_prints_the_refusal_only(
    network, hearths, capsys, terms
) -> None:
    """The defect: a payment presented and refused was answered with the terms and
    a `pay-compute` line, which invites paying a second time for one call."""
    a, _ = hearths
    a.replies[INVOKE] = reply(402, terms)

    assert cli.main(compute_argv("--tx", TX, "--secret", SECRET)) == 2

    assert capsys.readouterr().out == "  402 that payment secret does not open its nonce\n"


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (["--secret", SECRET],
         "a payment secret redeems a payment: send it with the transaction (tx_hash)"),
        (["--tx", TX, "--secret", "0xYOURSECRET"],
         "the payment secret is not 0x followed by 64 hex digits"),
        (["--tx", TX, "--secret", "0x" + "00" * 32], f"the payment secret {GUESSED}"),
    ],
    ids=["no-transaction", "template", "guessable"],
)
def test_cli_compute_refuses_a_secret_it_cannot_use_before_sending(
    network, hearths, capsys, flags, message
) -> None:
    assert cli.main(compute_argv(*flags)) == 1
    assert capsys.readouterr().out == f"  refused   : {message}\n"
    assert network.requests == []


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (reply(500, {"detail": "worker crashed"}), f"{A}: HTTP 500 worker crashed"),
        (httpx.Response(502, text="<html>"), f"{A}: HTTP 502, not JSON"),
        (reply(200, {"ok": False, "refuse_reason": "cpu_limit_exceeded", "detail": "4000 ms"}),
         f"{A}: cpu_limit_exceeded: 4000 ms"),
    ],
    ids=["500", "not-json", "ok-false"],
)
def test_cli_compute_refusals_exit_1(network, hearths, capsys, answer, message) -> None:
    a, _ = hearths
    a.replies[INVOKE] = answer
    assert cli.main(compute_argv()) == 1
    assert capsys.readouterr().out == f"  refused   : {message}\n"


@pytest.mark.parametrize("command", ["compute", "cross-verify"])
@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{nope", "--input is not JSON"),
        ("[1, 2]", "--input must be a JSON object"),
        ('"text"', "--input must be a JSON object"),
    ],
    ids=["not-json", "list", "string"],
)
def test_bad_input_is_refused_before_anything_is_sent(
    network, hearths, command, raw, message
) -> None:
    hearth_args = ["--hearth", A] if command == "compute" else ["--hearth", A, "--hearth", B]
    argv = [command, SLUG, *hearth_args, "--input", raw]
    with pytest.raises(SystemExit, match=message):
        cli.main(argv)
    assert network.requests == []


@pytest.mark.parametrize("command", ["compute", "cross-verify"])
@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda path: None, "--input cannot read {path}: No such file or directory"),
        (lambda path: path.mkdir(), "--input cannot read {path}: Is a directory"),
        (lambda path: path.write_bytes(b'{"document": "\xff"}'),
         "--input {path} is not UTF-8 text"),
    ],
    ids=["missing", "a-directory", "not-utf-8"],
)
def test_a_missing_input_file_is_refused_with_a_message(
    network, hearths, tmp_path, command, make, message
) -> None:
    path = tmp_path / "input.json"
    make(path)
    hearth_args = ["--hearth", A] if command == "compute" else ["--hearth", A, "--hearth", B]
    with pytest.raises(SystemExit) as refused:
        cli.main([command, SLUG, *hearth_args, "--input", f"@{path}"])
    assert refused.value.code == message.format(path=path)
    assert network.requests == []


def test_compute_needs_an_input(network) -> None:
    with pytest.raises(SystemExit) as refused:
        cli.main(["compute", SLUG, "--hearth", A])
    assert refused.value.code == 2
    assert network.requests == []


def test_cli_compute_defaults_to_hestia_public_base(network, monkeypatch) -> None:
    network.handler = Hearths(FakeHearth("https://hearth.example"))
    monkeypatch.setenv("HESTIA_PUBLIC_BASE", "https://hearth.example")
    assert cli.main(["compute", SLUG, "--input", json.dumps(DOCUMENT)]) == 0
    assert {r.url.host for r in network.requests} == {"hearth.example"}


# --------------------------------------------------------- CLI cross-verify


def cross_argv(*extra: str) -> list[str]:
    return ["cross-verify", SLUG, "--hearth", A, "--hearth", B, "--input", json.dumps(DOCUMENT),
            *extra]


@pytest.mark.parametrize(("flags", "capability"), [([], RUN), (["--replicated"], VERIFY)])
def test_cli_cross_verify_prints_both_sides_and_agrees(
    network, hearths, capsys, flags, capability
) -> None:
    a, b = hearths

    assert cli.main(cross_argv(*flags)) == 0

    output_sha = digest(canonicalise(DOCUMENT))
    assert capsys.readouterr().out.splitlines() == [
        f"  function  : {FUNCTION_SHA}",
        f"  input     : {digest(DOCUMENT)}",
        f"  {A}",
        f"    output  : {output_sha}",
        f"    key     : {a.public_key[:44]}...",
        f"  {B}",
        f"    output  : {output_sha}",
        f"    key     : {b.public_key[:44]}...",
        "  verdict   : AGREE",
    ]
    assert [json.loads(p.content)["capability_id"] for p in posts(network)] == [capability] * 2
    assert network.timeouts == [40.0]


def test_cli_cross_verify_passes_the_pin_and_the_hub_key(network, hearths, monkeypatch) -> None:
    monkeypatch.setenv("HESTIA_COMPUTE_API_KEY", "env-hub-key")

    assert cli.main(cross_argv("--pin", FUNCTION_SHA, "--api-key", "flag-hub-key")) == 0

    assert f"{A}/v1/compute" not in [str(r.url) for r in network.requests]
    for post in posts(network):
        assert post.headers["x-api-key"] == "flag-hub-key"
        assert json.loads(post.content)["input"]["function_sha256"] == FUNCTION_SHA


def test_cli_cross_verify_disagreement_exits_1(network, hearths, capsys) -> None:
    _, b = hearths
    b.function = disagreeing
    assert cli.main(cross_argv()) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "  verdict   : DISAGREE"
    assert lines[3] != lines[6], "the two output digests printed must differ"


def test_cli_cross_verify_prints_platform_notes(network, capsys) -> None:
    network.handler = Hearths(FakeHearth(A), FakeHearth(B, python_version="3.11.9"))
    assert cli.main(cross_argv()) == 0
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "  note      : python_version differs (3.12.13 vs 3.11.9): "
        "a disagreement may be the platform, not the operator",
        "  verdict   : AGREE",
    ]


def test_cli_cross_verify_one_hearth_failing_writes_no_verdict(
    network, hearths, fake_awr, tmp_path, capsys
) -> None:
    _, b = hearths
    b.replies[INVOKE] = reply(500, {"detail": "worker crashed"})
    target = tmp_path / "verdict.json"

    assert cli.main(cross_argv("--verdict-out", str(target))) == 1

    assert capsys.readouterr().out == f"  refused   : {B}: HTTP 500 worker crashed\n"
    assert not target.exists()
    assert fake_awr.issued == []


def test_cli_cross_verify_a_bad_first_receipt_writes_no_verdict(
    network, hearths, fake_awr, tmp_path, capsys
) -> None:
    # The verdict would judge exactly this receipt: it must not be issued over it.
    a, _ = hearths
    spoil_receipt(a)
    target = tmp_path / "verdict.json"

    assert cli.main(cross_argv("--verdict-out", str(target))) == 1

    problems = "; ".join(f"{A}: {problem}" for problem in RECEIPT_PROBLEMS)
    assert capsys.readouterr().out == f"  refused   : {problems}\n"
    assert not target.exists()
    assert fake_awr.issued == []


@pytest.mark.parametrize(
    "hearth_args",
    [[], ["--hearth", A], ["--hearth", A, "--hearth", B, "--hearth", "http://hearth-c.test"]],
    ids=["none", "one", "three"],
)
def test_cli_cross_verify_needs_exactly_two_hearths(network, hearths, hearth_args) -> None:
    argv = ["cross-verify", SLUG, *hearth_args, "--input", json.dumps(DOCUMENT)]
    with pytest.raises(SystemExit, match="exactly two --hearth URLs"):
        cli.main(argv)
    assert network.requests == []


@pytest.mark.parametrize(("function", "code"), [(canonicalise, 0), (disagreeing, 1)])
def test_cli_cross_verify_without_awr_says_no_verdict_was_written(
    network, hearths, no_awr, tmp_path, capsys, function, code
) -> None:
    _, b = hearths
    b.function = function
    target = tmp_path / "verdict.json"

    assert cli.main(cross_argv("--verdict-out", str(target))) == code

    assert "  no AWR verdict written: the awr package is not installed" in (
        capsys.readouterr().out.splitlines()
    )
    assert not target.exists()


def test_cli_cross_verify_writes_a_verdict_under_an_ephemeral_key(
    network, hearths, fake_awr, tmp_path, capsys
) -> None:
    a, _ = hearths
    target = tmp_path / "verdict.json"

    assert cli.main(cross_argv("--verdict-out", str(target))) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[-2:] == [
        "  awr key   : ephemeral did:key:zEphemeral (pass --awr-key to sign as yourself)",
        f"  wrote     : {target} (pass)",
    ]
    text = target.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    written = json.loads(text)
    ((subject, key),) = fake_awr.issued
    assert written == {"issuer": {"id": "did:key:zEphemeral"}, "credentialSubject": subject}
    assert written["credentialSubject"]["verifiedWork"]["id"] == a.receipt_id
    assert fake_awr.key_files == []


def test_cli_cross_verify_signs_a_failing_verdict_with_the_buyers_key(
    network, hearths, fake_awr, tmp_path, capsys
) -> None:
    _, b = hearths
    b.function = disagreeing
    target = tmp_path / "verdict.json"
    key_file = tmp_path / "me.jwk"

    assert cli.main(cross_argv("--verdict-out", str(target), "--awr-key", str(key_file))) == 1

    out = capsys.readouterr().out
    assert "ephemeral" not in out
    assert out.splitlines()[-1] == f"  wrote     : {target} (fail)"
    assert fake_awr.key_files == [str(key_file)]
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["issuer"]["id"] == "did:key:zBuyer"
    assert written["credentialSubject"]["verdict"] == "fail"


# --------------------------------------------------------------- pay-compute


def pay_compute_argv(*extra: str) -> list[str]:
    return ["pay-compute", SLUG, "--hearth", A, "--from", BUYER, *extra]


def to_sign(out: str) -> dict:
    printed, _end = json.JSONDecoder().raw_decode(out[out.index("{"):])
    return printed


def after_to_sign(out: str) -> list[str]:
    return out[out.index("\n}\n") + 3:].splitlines()


def test_payment_terms_asks_the_door_with_no_key_and_no_payment(network, hearths) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    with network.client() as client:
        terms = payment_terms(client, A + "/", SLUG, capability_id=VERIFY)

    assert terms == compute_quote()
    (post,) = network.requests
    assert (post.method, str(post.url)) == ("POST", f"{A}{INVOKE}")
    assert json.loads(post.content) == {
        "capability_id": VERIFY, "input": {"slug": SLUG, "input": {}},
    }
    assert not {"x-api-key", "x-payment", "x-payment-secret"} & set(post.headers)


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (reply(401, {"ok": False, "error": "hub_key_required",
                     "detail": "compute is priced. It is sold through its hub"}),
         f"{A}: HTTP 401 compute is priced. It is sold through its hub"),
        (reply(200, {"ok": True}), f"{A}: HTTP 200 {{'ok': True}}"),
        (httpx.Response(402, text="<html>pay</html>"), f"{A}: HTTP 402, not JSON"),
    ],
    ids=["hub-key-only", "served-unpaid", "not-json"],
)
def test_payment_terms_are_only_a_402_that_states_them(network, hearths, answer, message) -> None:
    a, _ = hearths
    a.replies[INVOKE] = answer
    with network.client() as client, pytest.raises(ComputeClientError) as refused:
        payment_terms(client, A, SLUG)
    assert str(refused.value) == message


def test_pay_compute_makes_up_a_secret_and_signs_its_sha256(
    network, hearths, monkeypatch, capsys
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    monkeypatch.setattr("time.time", lambda: 1_800_000_000.5)

    assert cli.main(pay_compute_argv()) == 0

    (post,) = network.requests
    assert json.loads(post.content)["capability_id"] == RUN
    out = capsys.readouterr().out
    printed = to_sign(out)
    rest = after_to_sign(out)
    secret = rest[1].split()[2]
    nonce = "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()
    assert printed == typed_data(compute_quote(), sender=BUYER, valid_before=1_800_003_600,
                                 nonce=nonce)
    assert rest == [
        "",
        f"  secret         : {secret}   (keep private: whoever holds it redeems the payment)",
        f"  nonce          : {nonce}   (its sha256; public once mined)",
        "  valid before   : 1800003600",
        "",
        "  Or export HESTIA_PAYMENT_SECRET=<the secret above> and leave --secret out of the "
        "commands below: it then stays out of your shell history.",
        "  Then re-run with the signature to get the calldata:",
        f"    hestia-agents pay-compute {SLUG} --hearth {A} --from {BUYER} --secret {secret} "
        f"--valid-before 1800003600 --amount {printed['message']['value']} "
        f"--pay-to {printed['message']['to']} --signature 0x<65-byte signature>",
    ]
    assert cli.main(pay_compute_argv()) == 0
    assert after_to_sign(capsys.readouterr().out)[1].split()[2] != secret, "a new one each time"


def test_pay_compute_step_two_refuses_a_price_or_payee_that_changed(
    network, hearths, capsys
) -> None:
    """Step 1 prints what it signed; a redeploy between the steps would make step 2's
    calldata one the token reverts, after gas."""
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    step2 = pay_compute_argv(
        "--secret", SECRET, "--valid-before", "1800000000", "--signature", SIGNATURE
    )
    for amount, pay_to in (("999", COMPUTE_WALLET), (str(2500), "0x" + "ee" * 20)):
        assert cli.main([*step2, "--amount", amount, "--pay-to", pay_to]) == 1
        assert "Run step 1 again" in capsys.readouterr().out
    assert cli.main([*step2, "--amount", "999"]) == 1
    assert "go together" in capsys.readouterr().out


def test_quote_calls_a_non_finite_expiry_a_failure(network, capsys) -> None:
    from tests.test_cli import HEARTH, answering
    from tests.test_cli import quote as tenant_quote

    body = json.dumps({**tenant_quote(), "expires_at": float("nan")})
    network.handler = answering(402, text=body)
    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1
    assert "402 without payment terms" in capsys.readouterr().out


def test_pay_compute_signs_over_the_secret_it_is_given(network, hearths, capsys) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())

    assert cli.main(pay_compute_argv("--secret", SECRET, "--valid-before", "1800000000")) == 0

    out = capsys.readouterr().out
    assert to_sign(out)["message"]["nonce"] == SECRET_NONCE
    assert f"  secret         : {SECRET}   (keep private" in out


def test_pay_compute_step_two_prints_calldata_for_what_step_one_asked_to_sign(
    network, hearths, monkeypatch, capsys, chain, wallet
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    monkeypatch.setattr("time.time", lambda: 1_800_000_000.0)
    assert cli.main(pay_compute_argv("--replicated")) == 0
    out = capsys.readouterr().out
    signed = to_sign(out)
    signature = wallet.sign(signed)
    step_two = shlex.split(after_to_sign(out)[-1].replace("0x<65-byte signature>", signature))

    monkeypatch.setattr("time.time", lambda: 1_800_000_900.0)
    assert cli.main(step_two[1:]) == 0

    secret = step_two[step_two.index("--secret") + 1]
    lines = capsys.readouterr().out.splitlines()
    data = lines[3].split(":", 1)[1].strip()
    words = data[len(TRANSFER_WITH_AUTHORIZATION_SELECTOR):]
    assert "0x" + words[5 * 64:6 * 64] == signed["message"]["nonce"] == (
        "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()
    )
    assert int(words[4 * 64:5 * 64], 16) == 1_800_003_600
    assert data == calldata(signed, signature)
    assert chain.receipts[chain.send(data)]["status"] == "0x1"
    # Both steps asked for the SKU that is going to be called: its price is what was signed.
    assert [json.loads(r.content)["capability_id"] for r in posts(network)] == [VERIFY] * 2
    assert lines[:5] == [
        "  Send this transaction from the address you signed with:",
        f"    to       : {USDC}   (the token contract)",
        "    value    : 0",
        f"    data     : {data}",
        "",
    ]
    assert lines[5:] == [
        "  Then present it to the hearth within 3600s of it being mined:",
        f"    hestia-agents compute {SLUG} --hearth {A} --replicated "
        f"--input <JSON object or @file> --tx <tx hash> --secret {secret}",
    ]


@pytest.mark.parametrize("max_age", [0, None, "3600", True], ids=["zero", "absent", "text", "bool"])
def test_pay_compute_names_no_window_the_402_does_not_state(
    network, hearths, capsys, max_age
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote(max_age_s=max_age))
    assert cli.main(pay_compute_argv(
        "--secret", SECRET, "--valid-before", "1800000000", "--signature", SIGNATURE
    )) == 0
    assert "  Then present it to the hearth:" in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        (["--signature", SIGNATURE],
         "--signature needs the --secret and --valid-before step 1 printed: the signature "
         "covers the nonce the secret makes and the deadline"),
        (["--signature", SIGNATURE, "--secret", SECRET],
         "--signature needs the --secret and --valid-before step 1 printed: the signature "
         "covers the nonce the secret makes and the deadline"),
        (["--signature", SIGNATURE, "--valid-before", "1800000000"],
         "--signature needs the --secret and --valid-before step 1 printed: the signature "
         "covers the nonce the secret makes and the deadline"),
        (["--secret", SECRET[:-1]], "--secret is not 0x followed by 64 hex digits"),
        (["--secret", SECRET[2:] + "ab"], "--secret is not 0x followed by 64 hex digits"),
        (["--secret", "0xYOURSECRET"], "--secret is not 0x followed by 64 hex digits"),
        # The defect: these exited 0, and the buyer paid for a call the door refuses.
        (["--secret", "0x" + "00" * 32], f"--secret {GUESSED}"),
        (["--secret", GUESSABLE], f"--secret {GUESSED}"),
        (["--secret", "0x" + bytes(range(15)).hex() + "00" * 17], f"--secret {GUESSED}"),
        (["--secret", GUESSABLE, "--valid-before", "1800000000", "--signature", SIGNATURE],
         f"--secret {GUESSED}"),
    ],
    ids=["signature-alone", "no-deadline", "no-secret", "short-secret", "unprefixed-secret",
         "template-secret", "zeros", "one-byte-repeated", "fifteen-distinct",
         "guessable-in-step-2"],
)
def test_pay_compute_refuses_a_step_it_cannot_take_before_asking_the_hearth(
    network, hearths, capsys, flags, reason
) -> None:
    assert cli.main(pay_compute_argv(*flags)) == 1
    assert capsys.readouterr().out == f"  cannot build a payment: {reason}\n"
    assert network.requests == []


@pytest.mark.parametrize("sender", ["0xYOURADDRESS", BUYER[:-1], BUYER[2:]])
def test_pay_compute_refuses_a_paying_address_that_is_not_one(
    network, hearths, capsys, sender
) -> None:
    assert cli.main(["pay-compute", SLUG, "--hearth", A, "--from", sender]) == 1
    assert capsys.readouterr().out == (
        "  cannot build a payment: --from is not an address (0x followed by 40 hex digits)\n"
    )
    assert network.requests == []


@pytest.mark.parametrize(
    ("terms", "reason"),
    [
        (compute_quote(binding="address"),
         "this hearth binds compute payments by 'address', not by a secret, and pay-compute "
         "builds only a payment redeemed with your own secret"),
        ({k: v for k, v in compute_quote().items() if k != "binding"},
         "this hearth binds compute payments by None, not by a secret, and pay-compute "
         "builds only a payment redeemed with your own secret"),
        (compute_quote(nonce_rule="keccak256(secret)"),
         "this hearth derives the nonce by 'keccak256(secret)'; pay-compute knows only "
         "sha256(secret)"),
        (compute_quote(accepts=[]), "402 carried no 'accepts' entry"),
        (compute_quote(accepts=[{**compute_quote()["accepts"][0], "payTo": "the hearth"}]),
         "402 'accepts' entry names no address to pay (payTo)"),
    ],
    ids=["older-hearth-by-address", "no-binding", "other-nonce-rule", "no-accepts",
         "pay-to-not-an-address"],
)
def test_pay_compute_refuses_a_402_it_cannot_bind_to_a_secret(
    network, hearths, capsys, terms, reason
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, terms)
    # One line, nothing to sign: a payment built from these could not be redeemed.
    assert cli.main(pay_compute_argv()) == 1
    assert capsys.readouterr().out == f"  cannot build a payment: {reason}\n"


def test_pay_compute_reports_a_door_that_sells_only_through_its_hub(
    network, hearths, capsys
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(401, {"ok": False, "detail": "sold through its hub"})
    assert cli.main(pay_compute_argv()) == 1
    assert capsys.readouterr().out == f"  refused   : {A}: HTTP 401 sold through its hub\n"


def test_pay_compute_refuses_a_signature_that_is_not_one(network, hearths, capsys) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    assert cli.main(pay_compute_argv(
        "--secret", SECRET, "--valid-before", "1800000000", "--signature", "0xdeadbeef"
    )) == 1
    assert capsys.readouterr().out == (
        "  bad signature: signature must be 65 bytes (132 chars with 0x)\n"
    )


def test_pay_compute_refuses_a_deadline_that_is_not_a_unix_time(network, hearths, capsys) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    assert cli.main(pay_compute_argv("--valid-before", "-1")) == 1
    assert capsys.readouterr().out == (
        "  cannot build a payment: --valid-before is not a unix time "
        "(whole seconds, not negative)\n"
    )


def test_pay_compute_keeps_a_secret_given_in_a_file_in_the_file(
    network, hearths, monkeypatch, capsys, tmp_path, chain, wallet
) -> None:
    """Off the command line, and never written out: step 1 names the file, the
    commands it prints pass the file on, and the calldata signs its sha256."""
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    kept = tmp_path / "secret"
    kept.write_text(f"{SECRET}\n", encoding="utf-8")
    monkeypatch.setattr("time.time", lambda: 1_800_000_000.0)

    assert cli.main(pay_compute_argv("--secret", f"@{kept}")) == 0

    out = capsys.readouterr().out
    signed = to_sign(out)
    assert signed["message"]["nonce"] == SECRET_NONCE
    rest = after_to_sign(out)
    assert rest[1] == (
        f"  secret         : in {kept}   (keep private: whoever holds it redeems the payment)"
    )
    step_two = shlex.split(rest[-1].replace("0x<65-byte signature>", wallet.sign(signed)))
    assert step_two[step_two.index("--secret") + 1] == f"@{kept}"
    assert SECRET not in out

    assert cli.main(step_two[1:]) == 0

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert chain.receipts[chain.send(lines[3].split(":", 1)[1].strip())]["status"] == "0x1"
    assert lines[-1].endswith(f"--tx <tx hash> --secret @{kept}")
    assert SECRET not in out


def test_pay_compute_step_two_reads_the_secret_from_the_environment(
    network, hearths, monkeypatch, capsys, wallet
) -> None:
    a, _ = hearths
    a.replies[INVOKE] = reply(402, compute_quote())
    monkeypatch.setenv("HESTIA_PAYMENT_SECRET", SECRET)

    # Step 1 does not: a secret left in the environment would sign every new payment
    # over one nonce, which the token takes once.
    assert cli.main(pay_compute_argv()) == 0
    out = capsys.readouterr().out
    assert to_sign(out)["message"]["nonce"] != SECRET_NONCE
    assert SECRET not in out

    signed = typed_data(
        compute_quote(), sender=BUYER, valid_before=1_800_000_000, nonce=SECRET_NONCE
    )
    signature = wallet.sign(signed)
    assert cli.main(pay_compute_argv("--valid-before", "1800000000", "--signature", signature)) == 0

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[3] == f"    data     : {calldata(signed, signature)}"
    assert lines[-2:] == [
        "  Then present it to the hearth within 3600s of it being mined, with "
        "HESTIA_PAYMENT_SECRET still set:",
        f"    hestia-agents compute {SLUG} --hearth {A} --input <JSON object or @file> "
        "--tx <tx hash>",
    ]
    assert SECRET not in out


@pytest.mark.parametrize(
    ("secret", "reason"),
    [(GUESSABLE, f"HESTIA_PAYMENT_SECRET {GUESSED}"),
     ("0xYOURSECRET", "HESTIA_PAYMENT_SECRET is not 0x followed by 64 hex digits")],
    ids=["guessable", "template"],
)
def test_pay_compute_holds_the_environments_secret_to_the_same_rules(
    network, hearths, monkeypatch, capsys, secret, reason
) -> None:
    monkeypatch.setenv("HESTIA_PAYMENT_SECRET", secret)
    assert cli.main(
        pay_compute_argv("--valid-before", "1800000000", "--signature", SIGNATURE)
    ) == 1
    assert capsys.readouterr().out == f"  cannot build a payment: {reason}\n"
    assert network.requests == []


def test_pay_compute_refuses_a_secret_file_it_cannot_read(
    network, hearths, capsys, tmp_path
) -> None:
    missing = tmp_path / "no-such-secret"
    assert cli.main(pay_compute_argv("--secret", f"@{missing}")) == 1
    assert capsys.readouterr().out == (
        f"  cannot build a payment: --secret cannot read {missing}: No such file or directory\n"
    )
    assert network.requests == []


def test_pay_compute_quotes_a_hearth_with_awkward_characters_for_the_shell(
    network, capsys
) -> None:
    hearth = FakeHearth("http://hearth-c.test")
    hearth.replies["/a b" + INVOKE] = reply(402, compute_quote())
    network.handler = Hearths(hearth)
    assert cli.main(
        ["pay-compute", SLUG, "--hearth", "http://hearth-c.test/a b", "--from", BUYER]
    ) == 0
    command = after_to_sign(capsys.readouterr().out)[-1]
    assert "--hearth 'http://hearth-c.test/a b' --from" in command
    assert shlex.split(command)[3:5] == ["--hearth", "http://hearth-c.test/a b"]
