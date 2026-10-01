"""The buyer side of compute, against two real hearths running in-process.

A cross-check is only worth something if it refuses to pass when it proves
nothing — one key on both hearths, different function bytes under one slug, a
receipt whose digests do not match what came back — so those refusals are
asserted as carefully as the agreement. The direct paid door is driven the same
way, through a token that holds each signature to its arguments.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
from urllib.parse import urlsplit

import pytest

from hestia_agents import cli
from hestia_agents.compute import (
    RUN,
    VERIFY,
    ComputeClientError,
    PaymentRequired,
    call,
    canonical_bytes,
    check_receipt,
    cross_verify,
    hearth_key,
    sha256_hex,
    signature_valid,
)
from hestia_agents.manifests import deploy_body, handler_source

KEY = "cross-verify-hub-key-" + "k" * 24
A = "http://hearth-a"
B = "http://hearth-b"
COMPUTE_WALLET = "0x" + "c0" * 20
BUYER = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
SET_ORDER = "def handle(payload):\n    return {'order': list(set(payload['words']))}\n"
WORDS = [f"w{i}-{chr(97 + i) * 3}" for i in range(26)]
DOCUMENT = {"document": {"b": 1, "a": [1, 2], "c": "x"}}


def _hestia():
    try:
        from fastapi.testclient import TestClient
        from hestia.app import build_app
        from hestia.config import Settings
    except ImportError:  # pragma: no cover - standalone checkout
        pytest.skip("sibling hestia/ sources (and fastapi) are not importable")
    return TestClient, build_app, Settings


def body_for(slug: str, source: str | None = None) -> dict:
    if source is None:
        return deploy_body(slug)
    body = deploy_body("json-canonical")
    body["slug"] = slug
    body["source"]["handler"] = source
    body["capability"]["capability_id"] = f"{slug}.fn@v1"
    return body


def hearth(tmp_path, url: str, functions: dict[str, str | None], *, key_from=None, **overrides):
    TestClient, build_app, Settings = _hestia()
    data = tmp_path / urlsplit(url).hostname
    if key_from is not None:
        data.mkdir(parents=True)
        shutil.copy(key_from / "provider.key", data / "provider.key")
    base = Settings.for_test(data)
    fields = {
        **base.__dict__,
        "compute_enabled": True,
        "compute_hub_keys": (KEY,),
        "compute_functions": tuple(functions),
        **overrides,
    }
    api = TestClient(build_app(Settings(**fields)), base_url=url)
    for slug, source in functions.items():
        res = api.post(
            "/v1/tenants",
            json=body_for(slug, source),
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 200, res.text
    return api


class Router:
    """One client for several in-process hearths, picked by host — the shape the
    CLI's single httpx.Client has against real ones."""

    def __init__(self, *clients) -> None:
        self.clients = {urlsplit(str(c.base_url)).hostname: c for c in clients}

    def _pick(self, url: str):
        return self.clients[urlsplit(url).hostname]

    def get(self, url, **kwargs):
        return self._pick(url).get(url, **kwargs)

    def post(self, url, **kwargs):
        return self._pick(url).post(url, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


@pytest.fixture
def pair(tmp_path):
    functions = {"json-canonical": None}
    return Router(hearth(tmp_path, A, functions), hearth(tmp_path, B, functions))


# ------------------------------------------------------------------ units


def test_canonical_bytes_match_the_hearths() -> None:
    _hestia()
    from hestia.compute_worker import canonical_bytes as hearth_canonical

    for value in (DOCUMENT, {"é": [1.5, None, True], "a": {"z": 0, "b": "ü"}}, {}):
        assert canonical_bytes(value) == hearth_canonical(value)


def test_a_signature_block_that_is_not_ours_is_invalid() -> None:
    assert signature_valid({"a": 1}, "AAAA") is False
    assert signature_valid({"a": 1, "signature": {"algorithm": "rsa"}}, "AAAA") is False
    garbage = {"a": 1, "signature": {"algorithm": "ed25519", "value": "!!"}}
    assert signature_valid(garbage, "AAAA") is False


# ------------------------------------------------------------ cross-check


def test_two_independent_hearths_agree_on_a_pure_function(pair) -> None:
    check = cross_verify(pair, (A, B), "json-canonical", DOCUMENT, api_key=KEY)
    assert check.agree is True
    assert check.function_sha256 == hashlib.sha256(
        handler_source("json-canonical").encode()
    ).hexdigest()
    assert check.input_sha256 == sha256_hex(canonical_bytes(DOCUMENT))
    assert check.first.public_key != check.second.public_key
    assert check.first.output["canonical"] == '{"a":[1,2],"b":1,"c":"x"}'
    assert check.first.problems == [] and check.second.problems == []


def test_replicated_calls_on_both_hearths_also_agree(pair) -> None:
    check = cross_verify(
        pair, (A, B), "json-canonical", DOCUMENT, capability_id=VERIFY, api_key=KEY
    )
    assert check.agree is True
    assert check.first.receipt["replicas"] == 2 == check.second.receipt["replicas"]


def test_hash_order_dependence_disagrees_across_hearths(tmp_path) -> None:
    functions = {"set-order": SET_ORDER}
    router = Router(hearth(tmp_path, A, functions), hearth(tmp_path, B, functions))
    check = cross_verify(router, (A, B), "set-order", {"words": WORDS}, api_key=KEY)
    # Each hearth signed its own answer honestly; they are different answers.
    assert check.agree is False
    assert check.first.problems == [] and check.second.problems == []


def test_one_key_on_both_hearths_is_not_a_cross_check(tmp_path) -> None:
    functions = {"json-canonical": None}
    first = hearth(tmp_path, A, functions)
    second = hearth(tmp_path, B, functions, key_from=tmp_path / "hearth-a")
    with pytest.raises(ComputeClientError, match="same key"):
        cross_verify(Router(first, second), (A, B), "json-canonical", DOCUMENT, api_key=KEY)


def test_different_bytes_under_one_slug_are_refused_before_paying(tmp_path) -> None:
    first = hearth(tmp_path, A, {"lookalike": SET_ORDER})
    impostor = SET_ORDER.replace("list(set(", "sorted(set(")
    second = hearth(tmp_path, B, {"lookalike": impostor})
    with pytest.raises(ComputeClientError, match="a different function"):
        cross_verify(Router(first, second), (A, B), "lookalike", {"words": WORDS}, api_key=KEY)


def test_an_unlisted_or_inadmissible_function_is_refused(tmp_path) -> None:
    clock = (
        "import datetime\n"
        "def handle(p):\n"
        "    return {'t': datetime.datetime.now().isoformat()}\n"
    )
    router = Router(
        hearth(tmp_path, A, {"clock": clock}), hearth(tmp_path, B, {"clock": clock})
    )
    with pytest.raises(ComputeClientError, match="not admissible"):
        cross_verify(router, (A, B), "clock", {}, api_key=KEY)
    with pytest.raises(ComputeClientError, match="no compute function"):
        cross_verify(router, (A, B), "absent-fn", {}, api_key=KEY)


def test_a_hearth_without_compute_is_refused(tmp_path) -> None:
    off = hearth(tmp_path, B, {}, compute_enabled=False)
    on = hearth(tmp_path, A, {"json-canonical": None})
    with pytest.raises(ComputeClientError, match="does not sell compute"):
        cross_verify(Router(on, off), (A, B), "json-canonical", DOCUMENT, api_key=KEY)


def test_a_forged_answer_is_caught(pair) -> None:
    checked = call(pair, A, "json-canonical", DOCUMENT, api_key=KEY)
    answer = {"result": {"output": checked.output, "compute_receipt": checked.receipt}}
    kwargs = {
        "hearth": A,
        "public_key": checked.public_key,
        "capability_id": RUN,
        "function_sha256": checked.receipt["function_sha256"],
        "input_sha256": sha256_hex(canonical_bytes(DOCUMENT)),
    }
    assert check_receipt(answer, **kwargs).problems == []

    swapped = {"result": {"output": {"canonical": "{}"}, "compute_receipt": checked.receipt}}
    assert "does not match the digest" in " ".join(check_receipt(swapped, **kwargs).problems)
    wrong_key = {**kwargs, "public_key": hearth_key(pair, B)}
    assert "not signed" in " ".join(check_receipt(answer, **wrong_key).problems)
    other_input = {**kwargs, "input_sha256": "0" * 64}
    assert "different input" in " ".join(check_receipt(answer, **other_input).problems)
    other_fn = {**kwargs, "function_sha256": "1" * 64}
    assert "different function" in " ".join(check_receipt(answer, **other_fn).problems)
    with pytest.raises(ComputeClientError, match="no compute receipt"):
        check_receipt({"result": {}}, **kwargs)


def test_a_refusal_and_an_unpaid_call_raise(tmp_path) -> None:
    api = hearth(tmp_path, A, {"json-canonical": None})
    router = Router(api)
    with pytest.raises(ComputeClientError, match="HTTP 401"):
        call(router, A, "json-canonical", DOCUMENT)  # no hub key, no direct door
    with pytest.raises(ComputeClientError, match="HTTP 409"):
        call(router, A, "json-canonical", DOCUMENT, api_key=KEY, function_sha256="a" * 64)
    paid = hearth(
        tmp_path,
        B,
        {"json-canonical": None},
        compute_hub_keys=(),
        compute_payout_address=COMPUTE_WALLET,
        payment_rpc_url="http://rpc.invalid",
    )
    with pytest.raises(PaymentRequired) as quote:
        call(Router(paid), B, "json-canonical", DOCUMENT)
    # The key-less door binds a payment to the buyer's own secret, not to the address.
    assert (quote.value.quote["binding"], quote.value.quote["nonce_rule"]) == (
        "secret", "sha256(secret)"
    )


def test_awr_verdicts_name_the_receipt_they_judged(pair, tmp_path) -> None:
    awr = pytest.importorskip("awr")
    from hestia_agents.compute import CROSS_METHOD, awr_verdict

    check = cross_verify(pair, (A, B), "json-canonical", DOCUMENT, api_key=KEY)
    key = awr.SigningKey.generate()
    verdict = awr_verdict(check, key)
    assert awr.verify_document(verdict)["valid"] is True
    subject = verdict["credentialSubject"]
    assert subject["verdict"] == "pass"
    assert subject["method"]["id"] == CROSS_METHOD
    assert subject["verifiedWork"]["id"] == check.first.receipt["id"]
    assert subject["verifiedWork"]["digestSRI"] == awr.canonical_sri(check.first.receipt)
    assert subject["evidence"][0]["digestSRI"] == awr.canonical_sri(check.second.receipt)
    assert verdict["issuer"]["id"] == key.did


# -------------------------------------------------------------------- CLI


def test_cli_cross_verify_agrees_and_writes_a_verdict(pair, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_http", lambda: pair)
    monkeypatch.setenv("HESTIA_COMPUTE_API_KEY", KEY)
    argv = [
        "cross-verify", "json-canonical", "--hearth", A, "--hearth", B,
        "--input", json.dumps(DOCUMENT),
    ]
    try:
        import awr  # noqa: F401
    except ImportError:
        has_awr = False
    else:
        has_awr = True
        argv += ["--verdict-out", str(tmp_path / "verdict.json")]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "AGREE" in out
    if has_awr:
        written = json.loads((tmp_path / "verdict.json").read_text())
        assert written["credentialSubject"]["verdict"] == "pass"


def test_cli_cross_verify_reports_a_disagreement(tmp_path, monkeypatch, capsys) -> None:
    functions = {"set-order": SET_ORDER}
    router = Router(hearth(tmp_path, A, functions), hearth(tmp_path, B, functions))
    monkeypatch.setattr(cli, "_http", lambda: router)
    words = tmp_path / "words.json"
    words.write_text(json.dumps({"words": WORDS}))
    code = cli.main(
        ["cross-verify", "set-order", "--hearth", A, "--hearth", B,
         "--input", f"@{words}", "--api-key", KEY]
    )
    assert code == 1
    assert "DISAGREE" in capsys.readouterr().out


def test_cli_cross_verify_needs_two_hearths() -> None:
    with pytest.raises(SystemExit, match="exactly two"):
        cli.main(["cross-verify", "json-canonical", "--hearth", A, "--input", "{}"])


def test_cli_compute_prints_a_checked_receipt(pair, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_http", lambda: pair)
    code = cli.main(
        ["compute", "json-canonical", "--hearth", A, "--input", json.dumps(DOCUMENT),
         "--api-key", KEY, "--replicated"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "hestia.replicate@v1" in out and "same_operator=True" in out


def test_cli_compute_refusal_and_quote(tmp_path, monkeypatch, capsys) -> None:
    paid = hearth(
        tmp_path,
        A,
        {"json-canonical": None},
        compute_hub_keys=(),
        compute_payout_address="0x" + "c0" * 20,
        payment_rpc_url="http://rpc.invalid",
    )
    monkeypatch.setattr(cli, "_http", lambda: Router(paid))
    args = ["compute", "json-canonical", "--hearth", A, "--input", json.dumps(DOCUMENT)]
    assert cli.main(args) == 2
    out = capsys.readouterr().out
    assert "compute payments only" in out
    assert f"hestia-agents pay-compute json-canonical --hearth {A} --from" in out
    with pytest.raises(SystemExit, match="JSON object"):
        cli.main(args[:-1] + ["[1, 2]"])
    with pytest.raises(SystemExit, match="not JSON"):
        cli.main(args[:-1] + ["{nope"])
    assert cli.main(args + ["--pin", "b" * 64]) == 1
    assert "refused" in capsys.readouterr().out


# ------------------------------------------------------ the direct paid door


def test_a_payment_pay_compute_builds_is_redeemed_by_its_secret_and_by_nobody_watching(
    tmp_path, monkeypatch, capsys, chain, wallet
) -> None:
    """End to end on a real hearth whose compute door takes direct payments. The
    hearth mints no nonce; the buyer's secret makes one. Once the payment is mined,
    its hash and nonce are public — a watcher presenting them gets a 402 — and the
    buyer, presenting the secret, gets one signed answer."""
    paid = hearth(
        tmp_path,
        A,
        {"json-canonical": None},
        compute_hub_keys=(),
        compute_payout_address=COMPUTE_WALLET,
        payment_rpc_url="http://rpc.invalid",
    )
    monkeypatch.setattr(cli, "_http", lambda: Router(paid))

    assert cli.main(["pay-compute", "json-canonical", "--hearth", A, "--from", BUYER]) == 0
    out = capsys.readouterr().out
    signed, _end = json.JSONDecoder().raw_decode(out[out.index("{"):])
    lines = out.splitlines()
    secret = next(line for line in lines if line.startswith("  secret ")).split()[2]
    nonce = signed["message"]["nonce"]
    assert nonce == "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()
    assert (signed["message"]["to"], signed["message"]["value"]) == (COMPUTE_WALLET, "1000")
    step_two = lines[-1].replace("0x<65-byte signature>", wallet.sign(signed))
    assert cli.main(shlex.split(step_two)[1:]) == 0
    lines = capsys.readouterr().out.splitlines()
    tx = chain.send(lines[3].split(":", 1)[1].strip())
    assert chain.receipts[tx]["status"] == "0x1"
    buyer = shlex.split(
        lines[-1].replace("<tx hash>", tx)
        .replace("<JSON object or @file>", shlex.quote(json.dumps(DOCUMENT)))
    )[1:]
    assert buyer[-2:] == ["--secret", secret]

    watched = ["compute", "json-canonical", "--hearth", A, "--input", json.dumps(DOCUMENT),
               "--tx", tx]
    wrong = "0x" + hashlib.sha256(b"a watcher guessing").hexdigest()
    for attempt in ([], ["--secret", nonce], ["--secret", wrong]):
        assert cli.main(watched + attempt) == 2, attempt
        # The refusal, and not how to pay: that would read as "pay again".
        (refusal,) = capsys.readouterr().out.splitlines()
        assert refusal.startswith("  402 "), refusal

    assert cli.main(buyer) == 0
    assert '"canonical"' in capsys.readouterr().out
    assert cli.main(buyer) == 2, "one payment, one call"
    assert "already been spent" in capsys.readouterr().out


@pytest.mark.parametrize(("distinct", "guessable"), [(15, True), (16, False)])
def test_the_guessable_rule_is_the_hearths(tmp_path, chain, distinct, guessable) -> None:
    """A client stricter than the hearth refuses secrets it would redeem; a looser one
    lets a buyer pay under a secret the door then refuses. Both sides of the line."""
    from hestia_agents.x402 import is_guessable

    paid = hearth(
        tmp_path, A, {"json-canonical": None}, compute_hub_keys=(),
        compute_payout_address=COMPUTE_WALLET, payment_rpc_url="http://rpc.invalid",
    )
    secret = "0x" + bytes(range(distinct)).hex() + "00" * (32 - distinct)
    # Straight to the door: the client would not send the guessable one.
    answer = paid.post(
        "/ai-market/v2/invoke",
        json={"capability_id": RUN, "input": {"slug": "json-canonical", "input": DOCUMENT}},
        headers={"X-Payment": "0x" + "9" * 64, "X-Payment-Secret": secret},
    )

    assert answer.status_code == 402
    assert ("guessable" in answer.json()["detail"]) is guessable
    assert is_guessable(secret) is guessable
