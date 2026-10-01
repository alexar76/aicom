"""The operator commands (build, deploy, verify, quote, pay, call) at the HTTP layer.

Each command is judged by what a hearth would receive and what the operator is
told: the exact requests (method, URL, headers, body), the lines printed and the
exit code. The places where a quiet mistake costs most get the closest look: the
deploy token must never reach the terminal, `announce` must stay off unless it
is asked for, one failed agent must not hide the others, `quote` must not call
a hearth that failed "free", and `pay` must never hand over calldata built from
a quote or a signature that is not one — nor calldata for anything but what
step 1 printed to sign, and a payment only its secret redeems. That payment must
also still be redeemable when it is mined (a deadline no later than the nonce's
expiry), must still buy the call (terms unchanged between the steps), and must
never be paid twice because a refusal read like a price.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import time

import httpx
import pytest

from hestia_agents import cli, manifests
from hestia_agents.manifests import AGENTS, deploy_body
from hestia_agents.x402 import TRANSFER_WITH_AUTHORIZATION_SELECTOR, calldata, typed_data

HEARTH = "http://hearth.test"
TOKEN = "deploy-token-" + "t" * 24
# 32 bytes that look like a hearth's draw: a pattern such as "5e" * 32 is refused as
# guessable (fewer than 16 distinct bytes), which GUESSABLE is here for.
SECRET = "0x" + hashlib.sha256(b"the buyer's payment secret").hexdigest()
GUESSABLE = "0x" + "5e" * 32
# A wrong secret, but not a guessable one: what a watcher of the chain could bring.
WATCHER = "0x" + hashlib.sha256(b"a watcher guessing").hexdigest()
# The hearth's rule, spelled out here rather than taken from the code under test.
NONCE = "0x" + hashlib.sha256(bytes.fromhex(SECRET[2:])).hexdigest()
# When the quoted nonce stops being redeemable: past any clock a test sets, unless
# the test is about the expiry and says otherwise.
EXPIRES_AT = 4_000_000_000.7
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAY_TO = "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c"
BUYER = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
SIGNATURE = "0x" + "11" * 32 + "22" * 32 + "1b"
SLUGS = list(AGENTS)


def quote(binding: str = "eip3009", **over) -> dict:
    """A tenant 402 in the shape hestia/app.py answers with."""
    body = {
        "ok": False,
        "error": "payment_required",
        "detail": "payment required: 0.001 USDC",
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "1000",
                "asset": USDC,
                "payTo": PAY_TO,
                "extra": {
                    "name": "USD Coin",
                    "version": "2",
                    "decimals": 6,
                    "symbol": "USDC",
                    "chainId": 8453,
                    "verifyingContract": USDC,
                },
            }
        ],
        "pay_to": PAY_TO,
        "amount_usd": 0.001,
        "amount_units": "1000",
        "chain": "base",
        "token": "USDC",
        "token_contract": USDC,
        "nonce": NONCE,
        "binding": binding,
        # Only a hearth that binds payments hands one over, and only in this body.
        **({"payment_secret": SECRET} if binding == "eip3009" else {}),
        "expires_at": EXPIRES_AT,
    }
    body.update(over)
    return body


def spoiled(accept=None, extra=None, **top) -> dict:
    """quote() with its accepts[0] (and that entry's extra) changed; None deletes."""
    body = quote(**top)
    entry = body["accepts"][0]
    for target, changes in ((entry, accept or {}), (entry["extra"], extra or {})):
        for name, value in changes.items():
            if value is None:
                target.pop(name)
            else:
                target[name] = value
    return body


def sent(request: httpx.Request):
    return json.loads(request.content)


def answering(status: int, body=None, text: str | None = None):
    if text is not None:
        return lambda _request: httpx.Response(status, text=text)
    return lambda _request: httpx.Response(status, json=body)


def deployed(request: httpx.Request) -> httpx.Response:
    slug = sent(request)["slug"]
    return httpx.Response(
        200, json={"status": "created", "invoke_url": f"{HEARTH}/t/{slug}/invoke"}
    )


def served(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "result": {"canonical": "{}"},
            "signature": "S" * 88,
            "provider_pubkey": "P" * 44 + "-rest-of-the-key",
        },
    )


# ------------------------------------------------------------------- build


def test_build_regenerates_every_manifest_from_its_handler(tmp_path, monkeypatch, capsys) -> None:
    agents = tmp_path / "agents"
    for slug in SLUGS:
        (agents / slug).mkdir(parents=True)
        shutil.copy(manifests.AGENTS_DIR / slug / "handler.py", agents / slug / "handler.py")
    # An edit to one handler must show up in its manifest: it is generated, not copied.
    edited = agents / "json-canonical" / "handler.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    monkeypatch.setattr(manifests, "AGENTS_DIR", agents)

    assert cli.main(["build"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        f"wrote agents/{slug}/deploy.json" for slug in SLUGS
    ]
    for slug in SLUGS:
        text = (agents / slug / "deploy.json").read_text(encoding="utf-8")
        assert text.endswith("}\n")
        written = json.loads(text)
        assert written == deploy_body(slug)
        assert written["source"]["handler"] == (agents / slug / "handler.py").read_text(
            encoding="utf-8"
        )
    assert json.loads((agents / "json-canonical" / "deploy.json").read_text())["source"][
        "handler"
    ].endswith("# edited\n")


# ------------------------------------------------------------------ deploy


@pytest.mark.parametrize("token", [None, "", "   \n"])
def test_deploy_without_a_token_stops_before_sending_anything(network, monkeypatch, token) -> None:
    if token is None:
        monkeypatch.delenv("HESTIA_DEPLOY_TOKEN", raising=False)
    else:
        monkeypatch.setenv("HESTIA_DEPLOY_TOKEN", token)
    network.handler = deployed
    with pytest.raises(SystemExit, match="HESTIA_DEPLOY_TOKEN is empty"):
        cli.main(["deploy", "--hearth", HEARTH])
    assert network.requests == []


def test_deploy_posts_every_manifest_with_the_token_and_never_prints_it(
    network, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HESTIA_DEPLOY_TOKEN", f"  {TOKEN}\n")
    network.handler = deployed

    assert cli.main(["deploy", "--hearth", HEARTH + "/"]) == 0

    assert [(r.method, str(r.url)) for r in network.requests] == [
        ("POST", f"{HEARTH}/v1/tenants")
    ] * len(SLUGS)
    assert [sent(r) for r in network.requests] == [deploy_body(slug) for slug in SLUGS]
    assert all(sent(r)["announce"] is False for r in network.requests)
    assert [r.headers["authorization"] for r in network.requests] == [
        f"Bearer {TOKEN}"
    ] * len(SLUGS)
    assert network.timeouts == [30.0] * len(SLUGS)
    out = capsys.readouterr().out
    assert out.splitlines() == [
        f"  {slug}: created -> {HEARTH}/t/{slug}/invoke" for slug in SLUGS
    ]
    assert TOKEN not in out


def test_deploy_announces_only_when_asked_and_only_the_named_agents(network, monkeypatch) -> None:
    monkeypatch.setenv("HESTIA_DEPLOY_TOKEN", TOKEN)
    network.handler = deployed

    assert cli.main(["deploy", "--hearth", HEARTH, "--only", "commit-referee"]) == 0
    assert cli.main(
        ["deploy", "--hearth", HEARTH, "--only", "json-canonical", "--only", "rules-decide",
         "--announce"]
    ) == 0

    assert [sent(r) for r in network.requests] == [
        deploy_body("commit-referee", announce=False),
        deploy_body("json-canonical", announce=True),
        deploy_body("rules-decide", announce=True),
    ]


def test_a_refused_deploy_is_reported_and_the_others_still_go_out(
    network, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HESTIA_DEPLOY_TOKEN", TOKEN)
    refusal = "slug is taken by another owner " + "x" * 1000

    def handler(request):
        if sent(request)["slug"] == "json-canonical":
            return httpx.Response(409, text=refusal)
        return deployed(request)

    network.handler = handler

    assert cli.main(["deploy", "--hearth", HEARTH]) == 1

    assert len(network.requests) == len(SLUGS)
    out = capsys.readouterr().out
    assert out.splitlines() == [
        f"  json-canonical: FAILED 409 {refusal[:300]}"
        if slug == "json-canonical"
        else f"  {slug}: created -> {HEARTH}/t/{slug}/invoke"
        for slug in SLUGS
    ]
    assert TOKEN not in out


def test_deploy_rejects_an_agent_it_does_not_ship(network, monkeypatch) -> None:
    monkeypatch.setenv("HESTIA_DEPLOY_TOKEN", TOKEN)
    with pytest.raises(SystemExit) as refused:
        cli.main(["deploy", "--hearth", HEARTH, "--only", "no-such-agent"])
    assert refused.value.code == 2
    assert network.requests == []


# ------------------------------------------------------------------ verify


def test_verify_invokes_each_agent_twice_with_its_probe(network, capsys) -> None:
    network.handler = lambda request: httpx.Response(
        200, json={"result": {"path": request.url.path}, "signature": "sig" + request.url.path}
    )

    assert cli.main(["verify", "--hearth", HEARTH]) == 0

    assert [(r.method, str(r.url)) for r in network.requests] == [
        ("POST", f"{HEARTH}/t/{slug}/invoke") for slug in SLUGS for _ in range(2)
    ]
    assert [sent(r) for r in network.requests] == [
        cli.PROBES[slug] for slug in SLUGS for _ in range(2)
    ]
    # Verifying is a read: it must not carry the deploy token anywhere.
    assert all("authorization" not in r.headers for r in network.requests)
    assert network.timeouts == [30.0] * (2 * len(SLUGS))
    assert capsys.readouterr().out.splitlines() == [
        f"  {slug}: ok (signature repeats: True)" for slug in SLUGS
    ]


@pytest.mark.parametrize(
    ("second", "repeats"),
    [
        ({"result": {"n": 1}, "signature": "another"}, "False"),
        ({"result": {"n": 2}, "signature": "same"}, "True"),
    ],
    ids=["signature-changed", "result-changed"],
)
def test_an_answer_that_changes_between_two_calls_is_not_deterministic(
    network, capsys, second, repeats
) -> None:
    answers = iter([{"result": {"n": 1}, "signature": "same"}, second])
    network.handler = lambda _request: httpx.Response(200, json=next(answers))

    assert cli.main(["verify", "--hearth", HEARTH, "--only", "json-canonical"]) == 1

    assert capsys.readouterr().out == (
        f"  json-canonical: NOT DETERMINISTIC (signature repeats: {repeats})\n"
    )


def test_a_failed_probe_is_reported_and_the_other_agents_are_still_checked(
    network, capsys
) -> None:
    def handler(request):
        if request.url.path == "/t/rules-decide/invoke":
            return httpx.Response(503, text="tenant is not running " + "y" * 400)
        return httpx.Response(200, json={"result": {}, "signature": "s"})

    network.handler = handler

    assert cli.main(["verify", "--hearth", HEARTH]) == 1

    paths = [r.url.path for r in network.requests]
    assert paths.count("/t/rules-decide/invoke") == 1, "the second call is pointless after a 503"
    assert paths.count("/t/json-canonical/invoke") == 2
    assert paths.count("/t/commit-referee/invoke") == 2
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "  rules-decide: FAILED 503 " + ("tenant is not running " + "y" * 400)[:200]
    assert out[1:] == [
        "  json-canonical: ok (signature repeats: True)",
        "  commit-referee: ok (signature repeats: True)",
    ]


# ------------------------------------------------------------------- quote


def test_quote_says_a_free_agent_is_free(network, capsys) -> None:
    network.handler = answering(200, {"result": {}})

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "rules-decide"]) == 0

    (request,) = network.requests
    assert (request.method, str(request.url)) == ("POST", f"{HEARTH}/t/rules-decide/invoke")
    assert sent(request) == cli.PROBES["rules-decide"]
    assert network.timeouts == [30.0]
    assert capsys.readouterr().out == "  rules-decide: free right now (HTTP 200)\n"


UNBOUND = (
        "this hearth does not bind payments (binding 'none'): a plain transfer's hash "
        "is public once mined, so whoever presents it first takes the call you paid for. "
        "Do not pay it"
)
NO_SECRET = (
        "this 402 hands over no payment_secret (a hearth from before commit-reveal): the "
        "nonce alone redeems, so whoever presents the mined payment first takes the call "
        "you paid for. Do not pay it"
)


@pytest.mark.parametrize(
    ("body", "why"),
    [(quote(binding="none"), UNBOUND), (quote(payment_secret=None), NO_SECRET)],
    ids=["unbound", "older-hearth-without-a-secret"],
)
def test_quote_refuses_a_hearth_whose_payment_anyone_could_redeem(
    network, capsys, body, why
) -> None:
    """A plain transfer, or a nonce with no secret, is redeemed by whoever presents the
    mined transaction first: the buyer pays and a watcher takes the call."""
    network.handler = answering(402, body)

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1

    assert capsys.readouterr().out == f"  json-canonical: FAILED {why}\n"


def test_quote_for_a_bound_hearth_names_the_nonce_the_secret_and_the_next_commands(
    network, capsys
) -> None:
    network.handler = answering(402, quote(binding="eip3009"))

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "  json-canonical  [json.canonical@v1]",
        "    send      : 0.001 USDC  (1000 base units)",
        f"    to        : {PAY_TO}",
        f"    on        : base   token {USDC}",
        f"    nonce     : {NONCE}   (expires 4000000000)",
        f"    secret    : {SECRET}   (keep private: whoever holds it redeems the payment)",
        "    pay with  : transferWithAuthorization signed over that nonce",
        "    build it  : hestia-agents pay json-canonical --from 0xYOURADDRESS",
        "    note      : pay asks for a 402 of its own, with a new nonce and secret: redeem "
        "what it builds with the secret pay prints, not the one above",
        "    then      : hestia-agents call json-canonical --tx <tx hash> "
        "--secret <the secret pay printed>",
    ]


@pytest.mark.parametrize(
    "secret",
    [WATCHER, NONCE, "0x1234", 42],
    ids=["another-secret", "the-nonce-itself", "short", "not-text"],
)
def test_a_quote_whose_secret_does_not_open_its_nonce_is_a_failure(
    network, capsys, secret
) -> None:
    # Found out here, by a sha256, rather than after paying.
    network.handler = answering(402, quote(payment_secret=secret))

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1

    assert capsys.readouterr().out == (
        "  json-canonical: FAILED the 402's payment_secret does not open its nonce: "
        "a payment signed over that nonce could never be redeemed\n"
    )


def test_a_quote_whose_secret_is_guessable_is_a_failure(network, capsys) -> None:
    # It opens its nonce, but so could anyone: `call --secret` would refuse to present it.
    guessable_nonce = "0x" + hashlib.sha256(bytes.fromhex(GUESSABLE[2:])).hexdigest()
    network.handler = answering(402, quote(nonce=guessable_nonce, payment_secret=GUESSABLE))

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1

    assert capsys.readouterr().out == (
        "  json-canonical: FAILED the 402's payment_secret is guessable (fewer than 16 "
        "distinct bytes): anyone could open its nonce and redeem the payment before you\n"
    )


def test_quote_never_hands_its_own_secret_to_the_payment_pay_builds(network, capsys) -> None:
    """The defect: quote printed a secret for its own nonce and then `call --secret
    <secret>`, but pay asks for a 402 of its own. quote -> pay -> call with quote's
    secret presented a secret that opens a nonce nobody paid under."""
    minted = Hearth402s()
    network.handler = minted

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 0
    quoted = capsys.readouterr().out.splitlines()
    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 0
    paid = capsys.readouterr().out

    quote_secret, pay_secret = minted.secrets
    assert f"  payment secret : {pay_secret}   (keep private" in paid
    assert quote_secret != pay_secret and quote_secret not in paid
    then = next(line for line in quoted if line.startswith("    then "))
    assert quote_secret not in then and "<the secret pay printed>" in then


@pytest.mark.parametrize("status", [401, 404, 409, 500, 503])
def test_quote_does_not_call_a_failing_hearth_free(network, capsys, status) -> None:
    answer = "tenant is not running " + "q" * 400
    network.handler = answering(status, text=answer)

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1

    assert capsys.readouterr().out == f"  json-canonical: FAILED {status} {answer[:200]}\n"


def test_one_agent_failing_its_quote_does_not_hide_the_others(network, capsys) -> None:
    def handler(request):
        if request.url.path == "/t/rules-decide/invoke":
            return httpx.Response(500, text="boom")
        if request.url.path == "/t/json-canonical/invoke":
            return httpx.Response(402, json=quote())
        return httpx.Response(200, json={"result": {}})

    network.handler = handler

    assert cli.main(["quote", "--hearth", HEARTH]) == 1

    assert [r.url.path for r in network.requests] == [f"/t/{slug}/invoke" for slug in SLUGS]
    assert capsys.readouterr().out.splitlines() == [
        "  rules-decide: FAILED 500 boom",
        "  json-canonical  [json.canonical@v1]",
        "    send      : 0.001 USDC  (1000 base units)",
        f"    to        : {PAY_TO}",
        f"    on        : base   token {USDC}",
        f"    nonce     : {NONCE}   (expires {int(EXPIRES_AT)})",
        f"    secret    : {SECRET}   (keep private: whoever holds it redeems the payment)",
        "    pay with  : transferWithAuthorization signed over that nonce",
        "    build it  : hestia-agents pay json-canonical --from 0xYOURADDRESS",
        "    note      : pay asks for a 402 of its own, with a new nonce and secret: redeem "
        "what it builds with the secret pay prints, not the one above",
        "    then      : hestia-agents call json-canonical --tx <tx hash> "
        "--secret <the secret pay printed>",
        "  commit-referee: free right now (HTTP 200)",
    ]


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(402, text="<html>payment required</html>"),
        httpx.Response(402, json=["not", "an", "object"]),
        httpx.Response(402, json=quote(pay_to=None)),
        httpx.Response(402, json=quote(amount_usd="")),
        httpx.Response(402, json={k: v for k, v in quote().items() if k != "token_contract"}),
        httpx.Response(402, json=quote(binding="eip3009", nonce=None)),
    ],
    ids=["not-json", "json-list", "no-pay-to", "empty-amount", "no-token-contract",
         "bound-without-nonce"],
)
def test_a_402_that_states_no_price_is_a_failure_not_a_quote(network, capsys, answer) -> None:
    network.handler = lambda _request: answer

    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1

    assert capsys.readouterr().out == (
        f"  json-canonical: FAILED 402 without payment terms: {answer.text[:200]}\n"
    )


# --------------------------------------------------------------------- pay


def printed_typed_data(out: str) -> dict:
    printed, _end = json.JSONDecoder().raw_decode(out[out.index("{"):])
    return printed


def after_typed_data(out: str) -> list[str]:
    return out[out.index("\n}\n") + 3:].splitlines()


def said(lines: list[str], name: str) -> str:
    """The value on step 1's `  <name> : <value>   (...)` line."""
    return next(line for line in lines if line.startswith(f"  {name} ")).split(":", 1)[1].split()[0]


def test_pay_prints_typed_data_bound_to_the_quoted_nonce(network, monkeypatch, capsys) -> None:
    network.handler = answering(402, quote())
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.9)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH + "/", "--from", BUYER]) == 0

    (request,) = network.requests
    assert (request.method, str(request.url)) == ("POST", f"{HEARTH}/t/json-canonical/invoke")
    assert sent(request) == cli.PROBES["json-canonical"]
    assert "x-payment" not in request.headers
    assert network.timeouts == [30.0]
    out = capsys.readouterr().out
    # The default deadline is one hour from now.
    assert printed_typed_data(out) == typed_data(quote(), sender=BUYER, valid_before=1_700_003_600)
    assert "data     :" not in out
    # Everything step 2 needs back, the secret the call will need, and until when.
    assert after_typed_data(out) == [
        "",
        f"  nonce          : {NONCE}",
        "  valid before   : 1700003600",
        "  redeem by      : 4000000000   (the hearth refuses this nonce after that)",
        f"  payment secret : {SECRET}   (keep private: whoever holds it redeems the payment)",
        "",
        "  Then re-run with the signature to get the calldata; send it and call before "
        "4000000000:",
        f"    hestia-agents pay json-canonical --hearth {HEARTH}/ --from {BUYER} --nonce {NONCE} "
        f"--valid-before 1700003600 --amount 1000 --pay-to {PAY_TO} "
        "--signature 0x<65-byte signature>",
    ]


def test_pay_uses_the_deadline_it_is_given(network, capsys) -> None:
    network.handler = answering(402, quote())

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER,
         "--valid-before", "1800000000"]
    ) == 0

    out = capsys.readouterr().out
    printed, _end = json.JSONDecoder().raw_decode(out[out.index("{"):])
    assert printed["message"]["validBefore"] == "1800000000"


# ------------------------------------------------ the deadline and the invoice

NOW = 1_800_000_000.0
EXPIRY = 1_800_000_900.4  # the hearth's default invoice: 900 s after the 402


def step_one(network, monkeypatch, body: dict, *flags: str) -> int:
    network.handler = answering(402, body)
    monkeypatch.setattr(time, "time", lambda: NOW)
    return cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *flags])


def test_the_default_deadline_stops_where_the_nonce_does(network, monkeypatch, capsys) -> None:
    """The defect: validBefore defaulted to an hour while the invoice lives 900 s, so a
    payment mined in between moved the money and was refused "nonce has expired"."""
    assert step_one(network, monkeypatch, quote(expires_at=EXPIRY)) == 0

    out = capsys.readouterr().out
    assert printed_typed_data(out)["message"]["validBefore"] == "1800000900"
    rest = after_typed_data(out)
    assert rest[2:4] == [
        "  valid before   : 1800000900",
        "  redeem by      : 1800000900   (the hearth refuses this nonce after that)",
    ]
    assert rest[-2] == (
        "  Then re-run with the signature to get the calldata; send it and call before "
        "1800000900:"
    )
    assert "--valid-before 1800000900 " in rest[-1]


def test_an_invoice_that_outlives_the_hour_leaves_the_hour(network, monkeypatch, capsys) -> None:
    assert step_one(network, monkeypatch, quote(expires_at=NOW + 7200)) == 0

    rest = after_typed_data(capsys.readouterr().out)
    assert rest[2:4] == [
        "  valid before   : 1800003600",
        "  redeem by      : 1800007200   (the hearth refuses this nonce after that)",
    ]


@pytest.mark.parametrize(
    ("given", "code"), [("1800000900", 0), ("1800000100", 0), ("1800000901", 1)]
)
def test_a_deadline_given_may_not_outlive_the_nonce(
    network, monkeypatch, capsys, given, code
) -> None:
    assert step_one(network, monkeypatch, quote(expires_at=EXPIRY), "--valid-before", given) == code

    out = capsys.readouterr().out
    if code == 0:
        assert printed_typed_data(out)["message"]["validBefore"] == given
    else:
        # One line and nothing to sign.
        assert out == (
            "  cannot build a payment: --valid-before 1800000901 is later than this 402's "
            "nonce can be redeemed (1800000900): a payment mined after that would pay for "
            "nothing\n"
        )


def test_a_nonce_already_expired_is_not_signed_over(network, monkeypatch, capsys) -> None:
    assert step_one(network, monkeypatch, quote(expires_at=NOW - 1)) == 1

    assert capsys.readouterr().out == (
        "  cannot build a payment: this 402's nonce expired at 1799999999: nothing signed "
        "over it could be redeemed\n"
    )


NOT_A_TIME = "  cannot build a payment: 402 'expires_at' is not a unix time\n"


@pytest.mark.parametrize(
    "expires", ["soon", True, -1, 0, [1]], ids=["text", "bool", "negative", "zero", "list"]
)
def test_a_bound_402_whose_expiry_is_not_a_time_is_refused(
    network, monkeypatch, capsys, expires
) -> None:
    assert step_one(network, monkeypatch, quote(expires_at=expires)) == 1

    assert capsys.readouterr().out == NOT_A_TIME


@pytest.mark.parametrize("number", ["NaN", "Infinity"])
def test_a_bound_402_whose_expiry_is_not_finite_is_refused(
    network, monkeypatch, capsys, number
) -> None:
    body = json.dumps(quote()).replace(f"{EXPIRES_AT}", number)
    network.handler = lambda _request: httpx.Response(
        402, content=body.encode(), headers={"content-type": "application/json"}
    )
    monkeypatch.setattr(time, "time", lambda: NOW)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 1

    assert capsys.readouterr().out == NOT_A_TIME


@pytest.mark.parametrize(
    "body",
    [{k: v for k, v in quote().items() if k != "expires_at"}],
    ids=["bound-without-an-expiry"],
)
def test_a_402_that_sets_no_redeem_by_keeps_the_hour(network, monkeypatch, capsys, body) -> None:
    assert step_one(network, monkeypatch, body) == 0

    rest = after_typed_data(capsys.readouterr().out)
    assert "  valid before   : 1800003600" in rest
    assert not any(line.startswith("  redeem by") for line in rest)
    assert rest[-2] == "  Then re-run with the signature to get the calldata:"


STEP_TWO = [
    "--nonce", NONCE, "--valid-before", "1800000000", "--amount", "1000", "--pay-to", PAY_TO,
    "--signature", SIGNATURE,
]


@pytest.mark.parametrize(
    ("body", "asked"),
    [
        (spoiled(accept={"maxAmountRequired": "2000"}), f"2000 base units to {PAY_TO}"),
        (spoiled(accept={"payTo": BUYER}), f"1000 base units to {BUYER}"),
    ],
    ids=["price-changed", "payee-changed"],
)
def test_step_two_refuses_terms_that_changed_since_step_one(
    network, capsys, body, asked
) -> None:
    """The defect: step 2 took the amount and payee from a fresh 402. A redeploy
    between the steps made calldata that differs from what was signed (the token
    reverts it), or that pays what the hearth no longer takes for the call."""
    network.handler = answering(402, body)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *STEP_TWO]) == 1

    assert capsys.readouterr().out == (
        f"  cannot build a payment: the hearth now asks {asked}, not the 1000 to {PAY_TO} "
        "step 1 printed to sign: that payment would not buy the call. Run step 1 again\n"
    )


def test_step_two_takes_the_payee_in_either_case(network, capsys) -> None:
    # An address is case-insensitive; a checksum spelling is the same payee.
    network.handler = answering(402, spoiled(accept={"payTo": PAY_TO.lower()}))

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *STEP_TWO]) == 0

    assert "    data     : 0xe3ee160e" in capsys.readouterr().out


def test_a_redeploy_between_the_steps_is_caught_by_the_command_step_one_printed(
    network, capsys
) -> None:
    network.handler = answering(402, quote())
    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 0
    printed = after_typed_data(capsys.readouterr().out)[-1]
    step_two = shlex.split(printed.replace("0x<65-byte signature>", SIGNATURE))
    assert step_two[step_two.index("--amount") + 1] == "1000"
    assert step_two[step_two.index("--pay-to") + 1] == PAY_TO

    network.handler = answering(402, spoiled(accept={"maxAmountRequired": "1500"}))
    assert cli.main(step_two[1:]) == 1

    out = capsys.readouterr().out
    assert "data     :" not in out
    assert out.startswith("  cannot build a payment: the hearth now asks 1500 base units")


def test_pay_with_a_signature_prints_the_calldata_and_the_call_to_make(network, capsys) -> None:
    network.handler = answering(402, quote())

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *STEP_TWO]
    ) == 0

    expected = calldata(typed_data(quote(), sender=BUYER, valid_before=1800000000), SIGNATURE)
    assert expected.startswith(TRANSFER_WITH_AUTHORIZATION_SELECTOR)
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "  Send this transaction from the address you signed with:",
        f"    to       : {USDC}   (the token contract)",
        "    value    : 0",
        f"    data     : {expected}",
        "",
        "  Then present it to the hearth, before the redeem-by time step 1 printed:",
        f"    hestia-agents call json-canonical --hearth {HEARTH} --tx <tx hash> "
        "--secret <payment secret from step 1>",
    ]


class Hearth402s:
    """A bound hearth's 402s as a real one mints them: a new secret, and so a new
    nonce, every time it is asked."""

    def __init__(self) -> None:
        self.secrets: list[str] = []

    def __call__(self, _request: httpx.Request) -> httpx.Response:
        secret = "0x" + hashlib.sha256(f"secret {len(self.secrets)}".encode()).hexdigest()
        self.secrets.append(secret)
        nonce = "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()
        return httpx.Response(402, json=quote(nonce=nonce, payment_secret=secret))


def test_step_two_prints_calldata_for_exactly_what_step_one_asked_to_sign(
    network, monkeypatch, capsys, chain, wallet
) -> None:
    """The defect: step 2 took a fresh 402 — a new nonce — and a fresh deadline from
    the clock, so the calldata it printed never matched the signature step 1 asked
    for, and the token contract reverted it. Here the hearth mints a new nonce per
    402 and the clock moves between the steps, as they do."""
    minted = Hearth402s()
    network.handler = minted
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 0

    out = capsys.readouterr().out
    signed = printed_typed_data(out)
    signature = wallet.sign(signed)
    step_two = shlex.split(after_typed_data(out)[-1].replace("0x<65-byte signature>", signature))
    assert step_two[0] == "hestia-agents"

    monkeypatch.setattr(time, "time", lambda: 1_800_000_900.0)
    assert cli.main(step_two[1:]) == 0

    first, second = minted.secrets
    assert first != second, "the second 402 carried a nonce nobody signed"
    lines = capsys.readouterr().out.splitlines()
    data = lines[3].split(":", 1)[1].strip()
    words = data[len(TRANSFER_WITH_AUTHORIZATION_SELECTOR):]
    word = [words[i * 64:(i + 1) * 64] for i in range(9)]
    assert "0x" + word[5] == signed["message"]["nonce"] != quote()["nonce"]
    assert int(word[4], 16) == int(signed["message"]["validBefore"]) == 1_800_003_600
    assert data == calldata(signed, signature), "byte for byte what was signed"
    # A token holds the signature to these arguments, and takes them.
    tx = chain.send(data)
    assert chain.receipts[tx]["status"] == "0x1"
    # The second 402's secret opens the second nonce, which nobody paid under.
    assert second not in "\n".join(lines)
    assert lines[-1] == (
        f"    hestia-agents call json-canonical --hearth {HEARTH} --tx <tx hash> "
        "--secret <payment secret from step 1>"
    )


def test_calldata_from_a_fresh_nonce_or_a_fresh_deadline_is_what_a_token_reverts(
    chain, wallet
) -> None:
    """Why the fix matters, on the fake token the pin above relies on: change the
    nonce or the deadline under a signature and the transaction does not pay."""
    signed = typed_data(quote(), sender=BUYER, valid_before=int(time.time()) + 3600)
    signature = wallet.sign(signed)
    fresh_nonce = typed_data(
        quote(), sender=BUYER, valid_before=int(signed["message"]["validBefore"]),
        nonce="0x" + "cd" * 32,
    )
    fresh_clock = typed_data(quote(), sender=BUYER, valid_before=int(time.time()) + 3601)
    for typed in (fresh_nonce, fresh_clock):
        assert chain.receipts[chain.send(calldata(typed, signature))]["status"] == "0x0"
    assert chain.receipts[chain.send(calldata(signed, signature))]["status"] == "0x1"


def test_the_call_step_two_prints_presents_the_secret(network, capsys) -> None:
    network.handler = answering(402, quote())

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *STEP_TWO]) == 0

    assert capsys.readouterr().out.splitlines()[-1] == (
        f"    hestia-agents call json-canonical --hearth {HEARTH} --tx <tx hash> "
        "--secret <payment secret from step 1>"
    )


@pytest.mark.parametrize(
    ("body", "why"),
    [(quote(binding="none"), UNBOUND), (quote(payment_secret=None), NO_SECRET)],
    ids=["unbound", "older-hearth-without-a-secret"],
)
@pytest.mark.parametrize("step", [(), tuple(STEP_TWO)], ids=["step-one", "step-two"])
def test_pay_builds_nothing_anyone_could_redeem(network, capsys, body, why, step) -> None:
    network.handler = answering(402, body)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *step]) == 1

    assert capsys.readouterr().out == f"  cannot build a payment: {why}\n"


def test_step_one_refuses_a_secret_that_does_not_open_the_nonce(network, capsys) -> None:
    network.handler = answering(402, quote(payment_secret=WATCHER))

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 1

    assert capsys.readouterr().out == (
        "  cannot build a payment: the 402's payment_secret does not open its nonce: "
        "a payment signed over that nonce could never be redeemed\n"
    )


NEEDS_ALL_FOUR = (
    "--signature needs the --nonce, --valid-before, --amount and --pay-to step 1 printed: "
    "the signature covers all four, and every 402 carries a new nonce"
)
STEP_TWO_ONLY = (
    "--nonce, --amount and --pay-to are step 2's, with --signature: step 1 signs the terms "
    "of a fresh 402"
)


def step_two(**over) -> list[str]:
    """STEP_TWO with flags changed; None leaves one out."""
    flags = dict(zip(STEP_TWO[::2], STEP_TWO[1::2], strict=True))
    for name, value in over.items():
        flags[f"--{name.replace('_', '-')}"] = value
    return [part for name, value in flags.items() if value is not None for part in (name, value)]


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        (["--signature", SIGNATURE], NEEDS_ALL_FOUR),
        (step_two(valid_before=None), NEEDS_ALL_FOUR),
        (step_two(nonce=None), NEEDS_ALL_FOUR),
        (step_two(amount=None), NEEDS_ALL_FOUR),
        (step_two(pay_to=None), NEEDS_ALL_FOUR),
        (["--nonce", NONCE], STEP_TWO_ONLY),
        (["--amount", "1000"], STEP_TWO_ONLY),
        (["--pay-to", PAY_TO], STEP_TWO_ONLY),
        (step_two(nonce=NONCE[:-2]), "--nonce is not 0x followed by 64 hex digits"),
        *[
            (step_two(amount=amount), "--amount is not a positive whole number of base units")
            for amount in ("0", "-5", "1e3", "10.5", " 1000", "\u0661\u0660\u0660\u0660")
        ],
        *[
            (step_two(pay_to=pay_to),
             "--pay-to is not an address (0x followed by 40 hex digits)")
            for pay_to in ("0xYOURADDRESS", PAY_TO[:-1], PAY_TO[2:])
        ],
    ],
    ids=["signature-alone", "no-deadline", "no-nonce", "no-amount", "no-pay-to",
         "nonce-without-signature", "amount-without-signature", "pay-to-without-signature",
         "short-nonce", "zero-amount", "negative-amount", "exponent-amount",
         "fractional-amount", "padded-amount", "non-ascii-amount", "template-pay-to",
         "short-pay-to", "unprefixed-pay-to"],
)
def test_pay_refuses_a_step_it_cannot_take_before_asking_the_hearth(
    network, capsys, flags, reason
) -> None:
    network.handler = answering(402, quote())

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *flags]) == 1

    assert capsys.readouterr().out == f"  cannot build a payment: {reason}\n"
    assert network.requests == []


def test_pay_refuses_a_deadline_that_is_not_a_unix_time(network, capsys) -> None:
    network.handler = answering(402, quote())

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, "--valid-before", "-5"]
    ) == 1

    assert capsys.readouterr().out == (
        "  cannot build a payment: --valid-before is not a unix time "
        "(whole seconds, not negative)\n"
    )


def test_pay_for_a_free_agent_needs_no_payment(network, capsys) -> None:
    network.handler = answering(200, {"result": {}})

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 0

    assert capsys.readouterr().out == "  json-canonical is free right now — no payment needed\n"


def test_pay_reports_a_hearth_that_neither_serves_nor_quotes(network, capsys) -> None:
    network.handler = answering(404, text="no such tenant " + "z" * 400)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 1

    assert capsys.readouterr().out == f"  HTTP 404: {('no such tenant ' + 'z' * 400)[:300]}\n"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"nonce": None}, "402 carried no payment nonce; this hearth is unbound"),
        ({"accepts": []}, "402 carried no 'accepts' entry"),
    ],
    ids=["no-nonce", "no-accepts"],
)
def test_pay_refuses_a_quote_it_cannot_turn_into_a_payment(network, capsys, change, reason) -> None:
    network.handler = answering(402, quote(**change))

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 1

    assert capsys.readouterr().out == f"  cannot build a payment: {reason}\n"


def test_pay_refuses_a_signature_of_the_wrong_length(network, capsys) -> None:
    network.handler = answering(402, quote())

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER,
         *STEP_TWO[:-1], "0xdeadbeef"]
    ) == 1

    assert capsys.readouterr().out == (
        "  bad signature: signature must be 65 bytes (132 chars with 0x)\n"
    )


@pytest.mark.parametrize(
    ("signature", "reason"),
    [
        ("0x" + "zz" * 32 + "22" * 32 + "1b", "signature r is not hex"),
        ("0x" + "11" * 32 + "22" * 31 + "2g" + "1b", "signature s is not hex"),
        ("0x" + "11" * 64 + "zz", "signature v is not hex"),
        # int(..., 16) takes a sign and surrounding spaces: both of these used to be v = 28.
        ("0x" + "11" * 64 + "+1", "signature v is not hex"),
        ("0x" + "11" * 64 + " 1", "signature v is not hex"),
        ("0x" + "11" * 64 + "1d", "signature v is 29: a recovery id is 27 or 28 (or 0 or 1)"),
        ("0x" + "11" * 64 + "02", "signature v is 2: a recovery id is 27 or 28 (or 0 or 1)"),
    ],
    ids=["non-hex-r", "non-hex-s", "non-hex-v", "signed-v", "padded-v", "v-29", "v-2"],
)
def test_pay_refuses_a_signature_that_is_not_hex(network, capsys, signature, reason) -> None:
    network.handler = answering(402, quote())

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *STEP_TWO[:-1], signature]
    ) == 1

    # One line and no calldata: nothing a buyer could paste into a wallet by mistake.
    assert capsys.readouterr().out == f"  bad signature: {reason}\n"


@pytest.mark.parametrize(
    ("v_byte", "v"),
    [("00", 27), ("01", 28), ("1b", 27), ("1c", 28), ("1C", 28)],
)
def test_pay_accepts_either_spelling_of_the_recovery_id(network, capsys, v_byte, v) -> None:
    network.handler = answering(402, quote())
    signature = "0x" + "11" * 32 + "2A" * 32 + v_byte

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *STEP_TWO[:-1], signature]
    ) == 0

    data = next(
        line.split(":", 1)[1].strip()
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("    data     :")
    )
    words = data[len(TRANSFER_WITH_AUTHORIZATION_SELECTOR):]
    assert [words[i * 64:(i + 1) * 64] for i in (6, 7, 8)] == [
        format(v, "064x"), "11" * 32, "2a" * 32
    ]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (spoiled(accept={"payTo": None}),
         "402 'accepts' entry names no address to pay (payTo)"),
        (spoiled(accept={"payTo": ""}),
         "402 'accepts' entry names no address to pay (payTo)"),
        (spoiled(accept={"payTo": "tenant owner"}),
         "402 'accepts' entry names no address to pay (payTo)"),
        (spoiled(accept={"payTo": PAY_TO[:-1]}),
         "402 'accepts' entry names no address to pay (payTo)"),
        (spoiled(accept={"maxAmountRequired": None}),
         "402 'accepts' entry names no amount to pay "
         "(maxAmountRequired, a positive whole number of base units)"),
        *[
            (spoiled(accept={"maxAmountRequired": amount}),
             "402 'accepts' entry names no amount to pay "
             "(maxAmountRequired, a positive whole number of base units)")
            # The last is 1000 in Arabic-Indic digits: str.isdigit() says yes to it, and
            # an amount a buyer cannot read at a glance is not one to sign for.
            for amount in ("", "0", 0, "-5", "1e3", "10.5", 1000.0, True,
                           "\u0661\u0660\u0660\u0660")
        ],
        (spoiled(extra={"chainId": "base"}), "402 'extra' chainId is not a positive whole number"),
        (spoiled(extra={"verifyingContract": "USDC"}),
         "402 'extra' verifyingContract is not an address"),
        (spoiled(accept={"extra": "USD Coin"}),
         "402 'extra' is missing the EIP-712 domain field 'name'"),
        (quote(accepts={"payTo": PAY_TO}), "402 'accepts' is not a list of payment options"),
        (quote(accepts=["exact"]), "402 'accepts' is not a list of payment options"),
    ],
    ids=["no-pay-to", "empty-pay-to", "pay-to-not-an-address", "pay-to-short", "no-amount",
         "empty-amount", "zero-amount-text", "zero-amount", "negative-amount", "exponent-amount",
         "fractional-amount", "float-amount", "bool-amount", "non-ascii-digits",
         "chain-id-a-name", "contract-a-symbol", "extra-not-an-object", "accepts-an-object",
         "accepts-of-strings"],
)
@pytest.mark.parametrize("step", [[], STEP_TWO], ids=["step-1", "step-2"])
def test_pay_refuses_a_quote_that_does_not_say_whom_or_how_much(
    network, capsys, body, reason, step
) -> None:
    # Step 2 asks again for the terms, and checks them again: they may have changed.
    network.handler = answering(402, body)

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER, *step]) == 1

    assert capsys.readouterr().out == f"  cannot build a payment: {reason}\n"


@pytest.mark.parametrize(
    "nonce",
    ["0x1234", "ab" * 32,
     # The right length, but only "0x" is stripped before the nonce becomes a word.
     "0X" + "ab" * 32],
    ids=["short-nonce", "unprefixed-nonce", "capital-x-nonce"],
)
def test_pay_refuses_a_402_whose_nonce_is_not_32_bytes(network, capsys, nonce) -> None:
    # Step 1 only: step 2 signs the nonce step 1 printed, whatever a fresh 402 says.
    network.handler = answering(402, spoiled(nonce=nonce))

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 1

    assert capsys.readouterr().out == (
        "  cannot build a payment: 402 payment nonce is not 32 bytes of 0x-prefixed hex\n"
    )


def test_pay_refuses_a_402_that_is_not_json(network, capsys) -> None:
    network.handler = answering(402, text="<html>pay up</html>")

    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 1

    assert capsys.readouterr().out == "  cannot build a payment: the 402 is not a JSON object\n"


def test_pay_takes_whole_numbers_written_as_numbers_or_as_digits(network, capsys) -> None:
    network.handler = answering(
        402, spoiled(accept={"maxAmountRequired": 1000}, extra={"chainId": "8453"})
    )

    assert cli.main(
        ["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER,
         "--valid-before", "1800000000"]
    ) == 0

    out = capsys.readouterr().out
    printed, _end = json.JSONDecoder().raw_decode(out[out.index("{"):])
    assert printed == typed_data(quote(), sender=BUYER, valid_before=1800000000)
    assert (printed["message"]["value"], printed["domain"]["chainId"]) == ("1000", 8453)


def test_pay_needs_the_paying_address(network) -> None:
    with pytest.raises(SystemExit) as refused:
        cli.main(["pay", "json-canonical", "--hearth", HEARTH])
    assert refused.value.code == 2
    assert network.requests == []


# -------------------------------------------------------------------- call


def test_call_without_a_payment_sends_no_payment_headers(network, capsys) -> None:
    network.handler = served

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH]) == 0

    (request,) = network.requests
    assert (request.method, str(request.url)) == ("POST", f"{HEARTH}/t/json-canonical/invoke")
    assert sent(request) == cli.PROBES["json-canonical"]
    assert "x-payment" not in request.headers
    assert "x-payment-nonce" not in request.headers
    assert "x-payment-secret" not in request.headers
    assert network.timeouts == [30.0]
    assert capsys.readouterr().out.splitlines() == [
        "  result   : {'canonical': '{}'}",
        "  receipt  : " + "S" * 44 + " ...",
        "  provider : " + "P" * 44 + " ...",
    ]


def test_call_presents_the_payment_and_the_nonce_it_settles(network) -> None:
    network.handler = served

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed"]) == 0
    assert cli.main(
        ["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed", "--nonce", NONCE]
    ) == 0

    assert cli.main(
        ["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed", "--secret", SECRET]
    ) == 0

    unbound, bound, by_secret = network.requests
    assert unbound.headers["x-payment"] == "0xfeed"
    assert "x-payment-nonce" not in unbound.headers
    assert bound.headers["x-payment"] == "0xfeed"
    assert bound.headers["x-payment-nonce"] == NONCE
    assert "x-payment-secret" not in bound.headers
    # The secret alone names the nonce: the hearth derives it.
    assert by_secret.headers["x-payment-secret"] == SECRET
    assert "x-payment-nonce" not in by_secret.headers


GUESSED = (
    "is guessable (fewer than 16 distinct bytes): anyone could open its nonce; "
    "use 32 random bytes"
)


@pytest.mark.parametrize(
    ("flags", "refusal"),
    [
        (["--secret", SECRET], "  --secret redeems a payment: give it with --tx <tx hash>"),
        (["--tx", "0xfeed", "--secret", SECRET[:-1]],
         "  --secret is not 0x followed by 64 hex digits"),
        (["--tx", "0xfeed", "--secret", SECRET[2:]],
         "  --secret is not 0x followed by 64 hex digits"),
        # Well formed, and refused by the hearth's own rule before anything is sent.
        (["--tx", "0xfeed", "--secret", GUESSABLE], f"  --secret {GUESSED}"),
        (["--tx", "0xfeed", "--secret", "0x" + "00" * 32], f"  --secret {GUESSED}"),
        (["--tx", "0xfeed", "--secret", "0x" + bytes(range(15)).hex() + "00" * 17],
         f"  --secret {GUESSED}"),
    ],
    ids=["no-transaction", "short", "unprefixed", "one-byte-repeated", "zeros",
         "fifteen-distinct"],
)
def test_a_call_with_a_secret_it_cannot_use_sends_nothing(network, capsys, flags, refusal) -> None:
    network.handler = served

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH, *flags]) == 1

    assert capsys.readouterr().out == refusal + "\n"
    assert network.requests == []


def test_sixteen_distinct_bytes_are_enough_to_present(network) -> None:
    network.handler = served
    secret = "0x" + bytes(range(16)).hex() + "00" * 16

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed",
                     "--secret", secret]) == 0

    assert network.requests[0].headers["x-payment-secret"] == secret


def test_the_secret_can_come_from_a_file_or_the_environment(
    network, monkeypatch, tmp_path
) -> None:
    """Off the command line, so out of shell history and `ps`."""
    network.handler = served
    kept = tmp_path / "secret"
    kept.write_text(SECRET + "\n", encoding="utf-8")
    argv = ["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed"]

    assert cli.main([*argv, "--secret", f"@{kept}"]) == 0
    monkeypatch.setenv("HESTIA_PAYMENT_SECRET", f"  {SECRET}\n")
    assert cli.main(argv) == 0
    # Given on the command line, the argument is the one meant.
    assert cli.main([*argv, "--secret", WATCHER]) == 0

    from_file, from_env, from_argument = network.requests
    assert from_file.headers["x-payment-secret"] == SECRET
    assert from_env.headers["x-payment-secret"] == SECRET
    assert from_argument.headers["x-payment-secret"] == WATCHER


def test_a_secret_in_the_environment_is_not_sent_without_a_payment(
    network, monkeypatch, capsys
) -> None:
    # A free call with a secret left over from an earlier payment is still a free call.
    network.handler = served
    monkeypatch.setenv("HESTIA_PAYMENT_SECRET", SECRET)

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH]) == 0

    assert "x-payment-secret" not in network.requests[0].headers
    assert capsys.readouterr().out.startswith("  result   : ")


@pytest.mark.parametrize(
    ("setup", "refusal"),
    [
        (lambda env, path: env.setenv("HESTIA_PAYMENT_SECRET", GUESSABLE),
         f"  HESTIA_PAYMENT_SECRET {GUESSED}"),
        (lambda env, path: env.setenv("HESTIA_PAYMENT_SECRET", "0xYOURSECRET"),
         "  HESTIA_PAYMENT_SECRET is not 0x followed by 64 hex digits"),
        (lambda env, path: None, "  --secret cannot read {path}: No such file or directory"),
        (lambda env, path: path.write_text("my secret\n", encoding="utf-8"),
         "  --secret @{path} is not 0x followed by 64 hex digits"),
        (lambda env, path: path.write_bytes(b"\xff" * 32), "  --secret {path} is not UTF-8 text"),
    ],
    ids=["env-guessable", "env-template", "file-missing", "file-not-a-secret", "file-binary"],
)
def test_a_secret_from_a_file_or_the_environment_is_held_to_the_same_rules(
    network, monkeypatch, capsys, tmp_path, setup, refusal
) -> None:
    network.handler = served
    path = tmp_path / "secret"
    setup(monkeypatch, path)
    by_file = ["--secret", f"@{path}"] if "HESTIA" not in refusal else []

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed",
                     *by_file]) == 1

    out = capsys.readouterr().out
    assert out == refusal.format(path=path) + "\n"
    assert "my secret" not in out, "what was read is never echoed"
    assert network.requests == []


def test_a_call_that_still_needs_payment_exits_2_with_the_terms(network, capsys) -> None:
    network.handler = answering(402, quote())

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH]) == 2

    assert capsys.readouterr().out.splitlines() == [
        "  402 payment required: 0.001 USDC",
        f"  pay 0.001 USDC to {PAY_TO} on base",
        "  build the payment with  hestia-agents pay json-canonical --from 0xYOU",
    ]


@pytest.mark.parametrize(
    ("body", "why"),
    [(quote(binding="none"), UNBOUND), (quote(payment_secret=None), NO_SECRET)],
    ids=["unbound", "older-hearth-without-a-secret"],
)
def test_a_call_to_a_hearth_anyone_could_redeem_says_not_to_pay(network, capsys, body, why) -> None:
    network.handler = answering(402, body)

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH]) == 2

    out = capsys.readouterr().out
    assert out.splitlines() == ["  402 payment required: 0.001 USDC", f"  {why}"]
    assert "pay 0.001" not in out


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (answering(402, quote(detail="that payment nonce has already been spent")),
         "that payment nonce has already been spent"),
        (answering(402, quote(binding="none", detail="transfer not found")),
         "transfer not found"),
        # No terms at all: after a payment the refusal is still the news.
        (answering(402, {"detail": "that payment secret does not open this payment nonce"}),
         "that payment secret does not open this payment nonce"),
        (answering(402, text="payment required " + "p" * 300), "payment required " + "p" * 183),
    ],
    ids=["spent", "unbound", "no-terms", "not-json"],
)
def test_a_payment_refused_prints_the_refusal_and_not_how_to_pay_again(
    network, capsys, answer, said
) -> None:
    """The defect: a 402 after a payment was presented printed the terms and "build
    one with hestia-agents pay", inviting a second payment for the same call."""
    network.handler = answer

    assert cli.main(
        ["call", "json-canonical", "--hearth", HEARTH, "--tx", "0xfeed", "--secret", SECRET]
    ) == 2

    assert capsys.readouterr().out == f"  402 {said}\n"


@pytest.mark.parametrize("status", [401, 404, 409, 500])
def test_a_call_the_hearth_refuses_exits_1_with_its_answer(network, capsys, status) -> None:
    network.handler = answering(status, text="x" * 400)

    assert cli.main(["call", "json-canonical", "--hearth", HEARTH]) == 1

    assert capsys.readouterr().out == f"  HTTP {status}: " + "x" * 300 + "\n"


def test_a_call_to_an_agent_that_is_not_shipped_is_refused_before_sending(network) -> None:
    with pytest.raises(SystemExit) as refused:
        cli.main(["call", "no-such-agent", "--hearth", HEARTH])
    assert refused.value.code == 2
    assert network.requests == []


# ----------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "argv",
    [
        ["call", "json-canonical"],
        ["quote", "--only", "json-canonical"],
        ["verify", "--only", "json-canonical"],
    ],
    ids=["call", "quote", "verify"],
)
def test_the_hearth_defaults_to_hestia_public_base_then_to_localhost(
    network, monkeypatch, argv
) -> None:
    network.handler = lambda _request: httpx.Response(
        200, json={"result": {}, "signature": "s", "provider_pubkey": "p"}
    )
    monkeypatch.setenv("HESTIA_PUBLIC_BASE", "https://hearth.example/")
    cli.main(argv)
    monkeypatch.delenv("HESTIA_PUBLIC_BASE")
    cli.main(argv)

    assert str(network.requests[0].url) == "https://hearth.example/t/json-canonical/invoke"
    assert str(network.requests[-1].url) == f"{cli.DEFAULT_HEARTH}/t/json-canonical/invoke"
    assert cli.DEFAULT_HEARTH == "http://127.0.0.1:9480"


def test_a_command_is_required(network) -> None:
    with pytest.raises(SystemExit) as refused:
        cli.main([])
    assert refused.value.code == 2
    assert network.requests == []


# -------------------------------------------- the same class of crash, three more doors


def test_pay_refuses_the_template_address_quote_prints(network, capsys) -> None:
    """quote tells the buyer `--from 0xYOURADDRESS`. Pasted as it stands, that became the
    first word of the typed data and of the calldata, and pay exited 0."""
    network.handler = answering(402, quote())
    for sender in ("0xYOURADDRESS", BUYER[:-1], "1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"):
        assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", sender,
                         "--valid-before", "1800000000"]) == 1, sender
        out = capsys.readouterr().out
        assert "--from is not an address" in out and "{" not in out, sender
    assert network.requests == [], "refused before the hearth was asked for anything"


@pytest.mark.parametrize("answer", [
    answering(402, text="payment required"),
    answering(402, {"detail": "pay first"}),
    answering(402, quote(pay_to="")),
], ids=["not-json", "no-terms", "empty-payee"])
def test_a_call_answered_402_without_terms_says_so(network, capsys, answer) -> None:
    network.handler = answer
    assert cli.main(["call", "json-canonical", "--hearth", HEARTH]) == 1
    assert "402 without payment terms" in capsys.readouterr().out


@pytest.mark.parametrize("expires", ["soon", None, True, [1]], ids=["text", "null", "bool", "list"])
def test_a_bound_quote_whose_expiry_is_not_a_time_is_refused(network, capsys, expires) -> None:
    network.handler = answering(402, quote(expires_at=expires))
    assert cli.main(["quote", "--hearth", HEARTH, "--only", "json-canonical"]) == 1
    assert "402 without payment terms" in capsys.readouterr().out


def test_pay_writes_an_amount_with_a_leading_zero_as_the_number(network, capsys) -> None:
    network.handler = answering(402, spoiled(accept={"maxAmountRequired": "01000"}))
    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER,
                     "--valid-before", "1800000000"]) == 0
    out = capsys.readouterr().out
    printed, _end = json.JSONDecoder().raw_decode(out[out.index("{"):])
    assert printed["message"]["value"] == "1000"


# ------------------------------------------- against a hearth that binds payments


class Through:
    """The `httpx` the CLI imports, answered by an in-process hearth."""

    def __init__(self, api) -> None:
        self.api = api

    def post(self, url, *, json=None, headers=None, timeout=None):
        return self.api.post(url, json=json, headers=headers or {})


def binding_hearth(tmp_path, hestia_parts):
    TestClient, build_app, Settings = hestia_parts
    base = Settings.for_test(tmp_path / "hearth")
    settings = Settings(**{
        **base.__dict__,
        "payments_enabled": True,
        "payment_rpc_url": "http://rpc.invalid",
    })
    api = TestClient(build_app(settings), base_url=HEARTH)
    deployed = api.post(
        "/v1/tenants", json=deploy_body("json-canonical"),
        headers={"Authorization": "Bearer test-token"},
    )
    assert deployed.status_code == 200, deployed.text
    return api


def test_a_payment_pay_builds_is_redeemed_by_its_secret_and_by_nobody_watching(
    tmp_path, monkeypatch, capsys, chain, wallet, hestia_parts
) -> None:
    """End to end on a real hearth and a token that holds signatures to their
    arguments: quote nothing, pay in two steps, send what step 2 printed, call.
    Once the payment is mined its hash and nonce are public; with those alone a
    watcher gets a 402, and the buyer, with the secret, gets the call — once."""
    api = binding_hearth(tmp_path, hestia_parts)
    monkeypatch.setattr(cli, "_client", lambda: Through(api))

    asked_at = time.time()
    assert cli.main(["pay", "json-canonical", "--hearth", HEARTH, "--from", BUYER]) == 0
    out = capsys.readouterr().out
    signed = printed_typed_data(out)
    rest = after_typed_data(out)
    secret = said(rest, "payment secret")
    nonce = signed["message"]["nonce"]
    assert "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest() == nonce
    # The hearth's invoice lives 900 s, not the hour a deadline defaults to: signed for
    # longer, the payment could be mined after the nonce had stopped being redeemable.
    redeem_by = int(said(rest, "redeem by"))
    # Bounded by the clock AFTER the quote: the hearth minted the invoice at some moment
    # between asked_at and now.
    deadline = int(signed["message"]["validBefore"])
    assert asked_at + 900 - 1 <= deadline == redeem_by <= time.time() + 900
    step_two = rest[-1].replace("0x<65-byte signature>", wallet.sign(signed))
    assert cli.main(shlex.split(step_two)[1:]) == 0
    lines = capsys.readouterr().out.splitlines()
    tx = chain.send(lines[3].split(":", 1)[1].strip())
    assert chain.receipts[tx]["status"] == "0x1"
    assert lines[-1].endswith(" --secret <payment secret from step 1>")
    call = shlex.split(
        lines[-1].replace("<tx hash>", tx).replace("<payment secret from step 1>", secret)
    )[1:]

    watched = ["call", "json-canonical", "--hearth", HEARTH, "--tx", tx]
    for attempt in ([], ["--nonce", nonce], ["--secret", nonce], ["--secret", WATCHER]):
        assert cli.main(watched + attempt) == 2, attempt
        # Refused, and told why: not how to pay, which would read as "pay again".
        (refusal,) = capsys.readouterr().out.splitlines()
        assert refusal.startswith("  402 ") and "hestia-agents pay" not in refusal, refusal

    assert cli.main(call) == 0
    assert capsys.readouterr().out.startswith("  result   : ")
    assert cli.main(call) == 2, "one payment, one call"
    assert capsys.readouterr().out == "  402 that payment nonce has already been spent\n"
