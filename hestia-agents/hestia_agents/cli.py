"""Build the deploy manifests, or deploy them onto a hearth.

    python -m hestia_agents.cli build
    python -m hestia_agents.cli deploy --hearth http://127.0.0.1:9480
    python -m hestia_agents.cli verify --hearth http://127.0.0.1:9480
    python -m hestia_agents.cli compute json-canonical --input '{"document": {"b": 1}}'
    python -m hestia_agents.cli cross-verify json-canonical --hearth A --hearth B --input @doc.json
    python -m hestia_agents.cli quote | pay <slug> | call <slug>          (a tenant's own till)
    python -m hestia_agents.cli pay-compute <slug> | compute <slug> --tx  (the compute door)

The deploy token comes from HESTIA_DEPLOY_TOKEN and is never printed, not even
in an error. `announce` stays off unless it is asked for on the command line:
putting a row in the Hub catalogue is an outward-facing act, not a side effect
of deploying. A compute key (HESTIA_COMPUTE_API_KEY) is treated the same way.

A payment secret is printed, because the buyer has to present it, but only ever
to the buyer's own terminal: a hearth redeems a mined payment only for whoever
shows the secret its nonce commits to, and the nonce itself is public on chain.
Handing it back need not put it on a command line (shell history, `ps`):
`--secret @file` reads it from a file, and where a payment is being rebuilt or
redeemed HESTIA_PAYMENT_SECRET stands in for a --secret that is not given.
"""

from __future__ import annotations

import argparse
import math
import os
import shlex
import sys
from typing import Any

from hestia_agents.manifests import AGENTS, deploy_body, write_manifests

DEFAULT_HEARTH = "http://127.0.0.1:9480"


def _client():
    try:
        import httpx
    except ImportError:  # pragma: no cover - dev extra not installed
        raise SystemExit("deploy needs httpx: uv sync --extra dev --project .") from None
    return httpx


def _token() -> str:
    token = (os.environ.get("HESTIA_DEPLOY_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "HESTIA_DEPLOY_TOKEN is empty. The hearth refuses every write without it — "
            "that is the intended default, not a fault."
        )
    return token


def cmd_build(_args: argparse.Namespace) -> int:
    for path in write_manifests():
        print("wrote", path.relative_to(path.parent.parent.parent))
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    httpx = _client()
    token = _token()
    slugs = args.only or list(AGENTS)
    failures = 0
    for slug in slugs:
        body = deploy_body(slug, announce=args.announce)
        response = httpx.post(
            f"{args.hearth.rstrip('/')}/v1/tenants",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        if response.status_code != 200:
            # Never echo the request: it carries the token header.
            print(f"  {slug}: FAILED {response.status_code} {response.text[:300]}")
            failures += 1
            continue
        out = response.json()
        print(f"  {slug}: {out['status']} -> {out['invoke_url']}")
    return 1 if failures else 0


PROBES: dict[str, dict[str, Any]] = {
    "rules-decide": {
        "policy": {
            "id": "probe@v1",
            "rules": [
                {
                    "id": "R1",
                    "when": [{"fact": "amount", "op": "<=", "value": 100}],
                    "then": {"decision": "approve", "reason": "under the limit"},
                }
            ],
            "default": {"decision": "deny", "reason": "over the limit"},
        },
        "facts": {"amount": 42},
    },
    "json-canonical": {"document": {"b": 1, "a": [1, 2]}},
    "commit-referee": {
        "commitment": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "value": "",
        "layout": "value",
    },
}


def cmd_verify(args: argparse.Namespace) -> int:
    """Invoke each deployed agent twice and prove the answer is reproducible."""
    httpx = _client()
    failures = 0
    for slug in args.only or list(AGENTS):
        url = f"{args.hearth.rstrip('/')}/t/{slug}/invoke"
        seen = []
        for _ in range(2):
            response = httpx.post(url, json=PROBES[slug], timeout=30.0)
            if response.status_code != 200:
                print(f"  {slug}: FAILED {response.status_code} {response.text[:200]}")
                failures += 1
                break
            seen.append(response.json())
        if len(seen) != 2:
            continue
        same_result = seen[0]["result"] == seen[1]["result"]
        same_signature = seen[0]["signature"] == seen[1]["signature"]
        mark = "ok" if same_result and same_signature else "NOT DETERMINISTIC"
        print(f"  {slug}: {mark} (signature repeats: {same_signature})")
        if not (same_result and same_signature):
            failures += 1
    return 1 if failures else 0


QUOTE_TERMS = ("amount_usd", "token", "amount_units", "pay_to", "chain", "token_contract")


def _quoted_terms(response: Any) -> dict[str, Any] | None:
    """The price in a 402, or None when the 402 does not state one."""
    try:
        terms = response.json()
    except ValueError:
        return None
    if not isinstance(terms, dict) or any(terms.get(name) in (None, "") for name in QUOTE_TERMS):
        return None
    if terms.get("binding") == "eip3009":
        if not terms.get("nonce"):
            return None
        expires = terms.get("expires_at", 0)
        if isinstance(expires, bool) or not isinstance(expires, (int, float)):
            return None
        if not math.isfinite(expires):
            return None
    return terms


DOES_NOT_OPEN = (
    "the 402's payment_secret does not open its nonce: a payment signed over that "
    "nonce could never be redeemed"
)
GUESSABLE_402 = (
    "the 402's payment_secret is guessable (fewer than 16 distinct bytes): anyone "
    "could open its nonce and redeem the payment before you"
)
KEEP_PRIVATE = "(keep private: whoever holds it redeems the payment)"
UNBOUND_402 = (
    "this hearth does not bind payments (binding {binding!r}): a plain transfer's hash "
    "is public once mined, so whoever presents it first takes the call you paid for. "
    "Do not pay it"
)
NONCE_ONLY_402 = (
    "this 402 hands over no payment_secret (a hearth from before commit-reveal): the "
    "nonce alone redeems, so whoever presents the mined payment first takes the call "
    "you paid for. Do not pay it"
)
SECRET_ENV = "HESTIA_PAYMENT_SECRET"  # noqa: S105 - the variable's name, not a secret


def _unsafe_to_pay(quote: dict[str, Any]) -> str:
    """Why a payment made against this 402 could be taken by someone else; '' when not.

    Only a nonce committed to a secret the buyer alone received says who paid. A plain
    transfer (no binding) and a nonce with no secret (a hearth from before commit-reveal)
    are both redeemed by whoever presents the mined transaction first, so this tool
    builds neither."""
    if quote.get("binding") != "eip3009":
        return UNBOUND_402.format(binding=str(quote.get("binding") or "none"))
    if quote.get("payment_secret") in (None, ""):
        return NONCE_ONLY_402
    return ""


def _secret_problem(quote: dict[str, Any], nonce: Any) -> str:
    """Why this 402 could not safely redeem a payment over `nonce`; '' when it could.

    Checked rather than believed: sha256 is all it takes, and the alternative is
    finding out after paying. A guessable secret is refused as well, because
    `call --secret` refuses to present one."""
    from hestia_agents.x402 import is_guessable, opens

    unsafe = _unsafe_to_pay(quote)
    if unsafe:
        return unsafe
    secret = quote.get("payment_secret")
    if not opens(secret, nonce):
        return DOES_NOT_OPEN
    return GUESSABLE_402 if is_guessable(secret) else ""


def _secret(raw: str, *, env: bool) -> tuple[str, str, str]:
    """(secret, what to call it in a refusal, the ` --secret …` a printed command repeats).

    `--secret` takes the secret itself, or `@file` holding it; with `env`, a
    --secret that is not given falls back to HESTIA_PAYMENT_SECRET. A command
    printed for the next step names the secret the way it was given — a file
    as the file, the environment not at all — so it is not written out where
    it was kept out. A ValueError carries a one-line reason, never the secret.
    """
    if raw.startswith("@"):
        path = raw[1:]
        try:
            with open(path, encoding="utf-8") as handle:
                value = handle.read().strip()
        except OSError as exc:
            raise ValueError(f"--secret cannot read {path}: {exc.strerror or exc}") from None
        except UnicodeDecodeError:
            raise ValueError(f"--secret {path} is not UTF-8 text") from None
        return value, f"--secret {raw}", f" --secret {shlex.quote(raw)}"
    if raw:
        return raw, "--secret", f" --secret {shlex.quote(raw)}"
    value = (os.environ.get(SECRET_ENV) or "").strip() if env else ""
    return value, SECRET_ENV, ""


def cmd_quote(args: argparse.Namespace) -> int:
    """Ask a priced agent what it costs. Prints the exact transaction to send.

    Nothing here signs anything: the buyer pays the tenant owner from their own
    wallet, and the hearth only reads the chain afterwards. Only a 200 is free
    and only a 402 that states its terms is a price; any other answer is a
    failure, because calling a broken hearth "free" sends the buyer to it.
    """
    httpx = _client()
    failures = 0
    for slug in args.only or list(AGENTS):
        cap = AGENTS[slug]["capability_id"]
        res = httpx.post(
            f"{args.hearth.rstrip('/')}/t/{slug}/invoke",
            json=PROBES[slug], timeout=30.0,
        )
        if res.status_code == 200:
            print(f"  {slug}: free right now (HTTP {res.status_code})")
            continue
        if res.status_code != 402:
            print(f"  {slug}: FAILED {res.status_code} {res.text[:200]}")
            failures += 1
            continue
        q = _quoted_terms(res)
        if q is None:
            print(f"  {slug}: FAILED 402 without payment terms: {res.text[:200]}")
            failures += 1
            continue
        problem = _secret_problem(q, q.get("nonce"))
        if problem:
            print(f"  {slug}: FAILED {problem}")
            failures += 1
            continue
        print(f"  {slug}  [{cap}]")
        print(f"    send      : {q['amount_usd']} {q['token']}  ({q['amount_units']} base units)")
        print(f"    to        : {q['pay_to']}")
        print(f"    on        : {q['chain']}   token {q['token_contract']}")
        # This nonce and secret are for a buyer who signs with their own tools. `pay`
        # asks for a 402 of its own — every 402 mints a new pair — so a payment it
        # builds is redeemed with what it prints, never with these.
        print(f"    nonce     : {q['nonce']}   (expires {int(q.get('expires_at', 0))})")
        print(f"    secret    : {q['payment_secret']}   {KEEP_PRIVATE}")
        print("    pay with  : transferWithAuthorization signed over that nonce")
        print(f"    build it  : hestia-agents pay {slug} --from 0xYOURADDRESS")
        print(
            "    note      : pay asks for a 402 of its own, with a new nonce and secret: "
            "redeem what it builds with the secret pay prints, not the one above"
        )
        print(
            f"    then      : hestia-agents call {slug} --tx <tx hash> "
            "--secret <the secret pay printed>"
        )
    return 1 if failures else 0


def _print_to_sign(typed: dict[str, Any]) -> None:
    import json as _json

    print("  Sign this with the wallet that holds your key (eth_signTypedData_v4):")
    print(_json.dumps(typed, indent=2))
    print()


def _print_transaction(typed: dict[str, Any], data: str) -> None:
    print("  Send this transaction from the address you signed with:")
    print(f"    to       : {typed['domain']['verifyingContract']}   (the token contract)")
    print("    value    : 0")
    print(f"    data     : {data}")
    print()


def _deadline(given: int, expires: int | None, now: int) -> int:
    """Step 1's validBefore: the one given, or an hour from now — never past the
    last second the 402's nonce can be redeemed.

    The authorization and the invoice expire separately. Signed for an hour
    against a 900 s invoice, a payment could be mined, and the money moved, when
    the hearth already answers "that payment nonce has expired"."""
    from hestia_agents.x402 import QuoteError

    if expires is None:
        return given or now + 3600
    if expires <= now:
        raise QuoteError(
            f"this 402's nonce expired at {expires}: nothing signed over it could be redeemed"
        )
    if given > expires:
        raise QuoteError(
            f"--valid-before {given} is later than this 402's nonce can be redeemed "
            f"({expires}): a payment mined after that would pay for nothing"
        )
    return given or min(now + 3600, expires)


def _same_terms(typed: dict[str, Any], args: argparse.Namespace) -> None:
    """Step 2's fresh 402 must still ask what step 1 signed: this payee, this amount.

    The signature covers both, so calldata rebuilt from changed terms is one the
    token reverts, and calldata for the old terms pays what the hearth no longer
    takes for the call (a redeploy between the steps changes either)."""
    from hestia_agents.x402 import QuoteError, whole_number

    asked_to, asked = typed["message"]["to"], int(typed["message"]["value"])
    signed = whole_number(args.amount)
    if asked_to.lower() != args.pay_to.lower() or asked != signed:
        raise QuoteError(
            f"the hearth now asks {asked} base units to {asked_to}, not the {signed} to "
            f"{args.pay_to} step 1 printed to sign: that payment would not buy the call. "
            "Run step 1 again"
        )


def cmd_pay(args: argparse.Namespace) -> int:
    """Build the payment a bound hearth will accept. Signs nothing.

    Step 1 prints EIP-712 typed data — sign it with the wallet that holds your
    key — with the nonce, deadline, payee, amount and payment secret it was built
    from, and when the hearth stops redeeming that nonce. Step 2 (`--signature`)
    is handed the nonce, deadline, payee and amount back and prints the calldata
    for exactly what was signed. It used to rebuild them from a fresh 402 and the
    clock; but every 402 mints a new nonce and the signature covers all four, so
    that calldata was a transaction the token contract reverts. The fresh 402
    still has to ask the same payee and amount, or step 2 refuses.
    The key never comes near this process.
    """
    import time as _time

    from hestia_agents.x402 import (
        QuoteError,
        calldata,
        is_address,
        is_nonce,
        redeem_by,
        typed_data,
        whole_number,
    )

    step_two = (args.nonce, args.amount, args.pay_to)
    refusal = ""
    if any(step_two) and not args.signature:
        refusal = (
            "--nonce, --amount and --pay-to are step 2's, with --signature: step 1 "
            "signs the terms of a fresh 402"
        )
    elif args.signature and not (all(step_two) and args.valid_before):
        refusal = (
            "--signature needs the --nonce, --valid-before, --amount and --pay-to step 1 "
            "printed: the signature covers all four, and every 402 carries a new nonce"
        )
    elif args.nonce and not is_nonce(args.nonce):
        refusal = "--nonce is not 0x followed by 64 hex digits"
    elif args.amount and whole_number(args.amount) is None:
        refusal = "--amount is not a positive whole number of base units"
    elif args.pay_to and not is_address(args.pay_to):
        refusal = "--pay-to is not an address (0x followed by 40 hex digits)"
    elif not is_address(args.sender):
        refusal = "--from is not an address (0x followed by 40 hex digits)"
    if refusal:
        print(f"  cannot build a payment: {refusal}")
        return 1

    httpx = _client()
    slug = args.slug
    res = httpx.post(
        f"{args.hearth.rstrip('/')}/t/{slug}/invoke",
        json=PROBES[slug], timeout=30.0,
    )
    if res.status_code != 200 and res.status_code != 402:
        print(f"  HTTP {res.status_code}: {res.text[:300]}")
        return 1
    if res.status_code == 200:
        print(f"  {slug} is free right now — no payment needed")
        return 0
    try:
        quote = res.json()
    except ValueError:
        quote = None
    expires = None
    try:
        if not isinstance(quote, dict):
            raise QuoteError("the 402 is not a JSON object")
        # Step 2 too: its 402 supplies the terms, and a hearth that could hand the
        # payment to someone else is not one to send it to.
        unsafe = _unsafe_to_pay(quote)
        if unsafe:
            raise QuoteError(unsafe)
        if args.signature:
            valid_before = args.valid_before
        else:
            expires = redeem_by(quote)
            valid_before = _deadline(args.valid_before, expires, int(_time.time()))
        # In step 2 this 402 supplies the terms only. Its own nonce is a new
        # invoice nobody signed; step 1's nonce is the one the signature covers.
        typed = typed_data(
            quote, sender=args.sender, valid_before=valid_before, nonce=args.nonce
        )
        if args.signature:
            _same_terms(typed, args)
        else:
            problem = _secret_problem(quote, typed["message"]["nonce"])
            if problem:
                raise QuoteError(problem)
    except QuoteError as exc:
        print(f"  cannot build a payment: {exc}")
        return 1
    message = typed["message"]
    nonce = message["nonce"]
    secret = quote["payment_secret"]
    hearth = shlex.quote(args.hearth)
    if not args.signature:
        _print_to_sign(typed)
        print(f"  nonce          : {nonce}")
        print(f"  valid before   : {valid_before}")
        if expires is not None:
            print(f"  redeem by      : {expires}   (the hearth refuses this nonce after that)")
        print(f"  payment secret : {secret}   {KEEP_PRIVATE}")
        print()
        by = "" if expires is None else f"; send it and call before {expires}"
        print(f"  Then re-run with the signature to get the calldata{by}:")
        print(
            f"    hestia-agents pay {slug} --hearth {hearth} --from {args.sender} "
            f"--nonce {nonce} --valid-before {valid_before} --amount {message['value']} "
            f"--pay-to {message['to']} --signature 0x<65-byte signature>"
        )
        return 0
    try:
        data = calldata(typed, args.signature)
    except QuoteError as exc:
        print(f"  bad signature: {exc}")
        return 1
    _print_transaction(typed, data)
    # This 402's secret opens this 402's nonce, not step 1's, so it is never printed
    # here. This 402's expiry is its own invoice's; step 1's nonce expires when step 1 said.
    by = ", before the redeem-by time step 1 printed" if "expires_at" in quote else ""
    print(f"  Then present it to the hearth{by}:")
    print(
        f"    hestia-agents call {slug} --hearth {hearth} --tx <tx hash> "
        "--secret <payment secret from step 1>"
    )
    return 0


def _refusal(response: Any) -> str:
    """What a 402 says was wrong with the payment presented."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("detail"):
        return str(body["detail"])
    return response.text[:200]


def cmd_call(args: argparse.Namespace) -> int:
    """Invoke an agent, presenting a payment transaction hash if one is given."""
    from hestia_agents.x402 import secret_refusal

    if args.secret and not args.tx:
        print("  --secret redeems a payment: give it with --tx <tx hash>")
        return 1
    try:
        # Without --tx nothing is redeemed, so a secret left in the environment
        # must not turn a free call into a refused one.
        secret, name, _again = _secret(args.secret, env=bool(args.tx))
    except ValueError as exc:
        print(f"  {exc}")
        return 1
    problem = secret_refusal(secret) if secret else ""
    if problem:
        print(f"  {name} {problem}")
        return 1
    httpx = _client()
    slug = args.slug
    headers = {}
    if args.tx:
        headers["X-Payment"] = args.tx
    if args.nonce:
        # A bound hearth needs to know WHICH quote this payment settles.
        headers["X-Payment-Nonce"] = args.nonce
    if secret:
        # And that this caller is the one who paid: the nonce is public once mined.
        headers["X-Payment-Secret"] = secret
    res = httpx.post(
        f"{args.hearth.rstrip('/')}/t/{slug}/invoke",
        json=PROBES[slug], headers=headers, timeout=30.0,
    )
    if res.status_code == 402 and args.tx:
        # A payment was presented and refused. Why is the news; how to pay is not —
        # printed here, it reads as "pay again" to a buyer who already has.
        print(f"  402 {_refusal(res)}")
        return 2
    if res.status_code == 402:
        q = _quoted_terms(res)
        if q is None:
            print(f"  402 without payment terms: {res.text[:200]}")
            return 1
        print(f"  402 {q.get('detail')}")
        unsafe = _unsafe_to_pay(q)
        if unsafe:
            print(f"  {unsafe}")
            return 2
        print(f"  pay {q['amount_usd']} {q['token']} to {q['pay_to']} on {q['chain']}")
        print(f"  build the payment with  hestia-agents pay {slug} --from 0xYOU")
        return 2
    if res.status_code != 200:
        print(f"  HTTP {res.status_code}: {res.text[:300]}")
        return 1
    body = res.json()
    print("  result   :", body["result"])
    print("  receipt  :", body["signature"][:44], "...")
    print("  provider :", body["provider_pubkey"][:44], "...")
    return 0


def _http():
    # One client for both hearths: a replicated call can take seconds, and the
    # chain lookup in front of a paid one more.
    return _client().Client(timeout=40.0)


def _compute_input(raw: str) -> dict[str, Any]:
    import json as _json

    text = raw
    if raw.startswith("@"):
        path = raw[1:]
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            raise SystemExit(f"--input cannot read {path}: {exc.strerror or exc}") from None
        except UnicodeDecodeError:
            raise SystemExit(f"--input {path} is not UTF-8 text") from None
    try:
        value = _json.loads(text)
    except ValueError as exc:
        raise SystemExit(f"--input is not JSON: {exc}") from None
    if not isinstance(value, dict):
        raise SystemExit("--input must be a JSON object: it is what handle(payload) receives")
    return value


def _api_key(args: argparse.Namespace) -> str:
    return (args.api_key or os.environ.get("HESTIA_COMPUTE_API_KEY") or "").strip()


def _print_receipt(checked) -> None:
    receipt = checked.receipt
    print(f"  hearth    : {checked.hearth}")
    print(f"  key       : {checked.public_key[:44]}...")
    print(f"  method    : {receipt.get('method')}  replicas={receipt.get('replicas')}")
    print(f"  function  : {receipt.get('function_sha256')}")
    print(f"  input     : {receipt.get('input_sha256')}")
    print(f"  output    : {receipt.get('output_sha256')}")
    print(
        f"  measured  : cpu_ms={receipt.get('cpu_ms')} max_rss_kb={receipt.get('max_rss_kb')} "
        f"wall_ms={receipt.get('wall_ms')}"
    )
    print(
        f"  runtime   : {receipt.get('runtime')} python {receipt.get('python_version')} "
        f"on {receipt.get('platform')}  same_operator={receipt.get('same_operator')}"
    )


def cmd_compute(args: argparse.Namespace) -> int:
    """Run a published function on a hearth and check the receipt that comes back."""
    import json as _json

    from hestia_agents.compute import RUN, VERIFY, ComputeClientError, PaymentRequired, call

    payload = _compute_input(args.input)
    try:
        # As with call: the environment's secret is read only when a payment is presented.
        secret, _name, _again = _secret(args.secret, env=bool(args.tx))
    except ValueError as exc:
        print(f"  refused   : {exc}")
        return 1
    try:
        with _http() as client:
            checked = call(
                client,
                args.hearth,
                args.slug,
                payload,
                capability_id=VERIFY if args.replicated else RUN,
                function_sha256=args.pin,
                api_key=_api_key(args),
                tx_hash=args.tx,
                payment_secret=secret,
            )
    except PaymentRequired as exc:
        quote = exc.quote
        print(f"  402 {quote.get('detail')}")
        # After a payment was presented the refusal is all there is to say: the
        # terms and a build-it line would read as "pay again" for the same call.
        if quote.get("pay_to") and not args.tx:
            print(f"  pay       : {quote['amount_usd']} {quote['token']} on {quote['chain']}")
            if quote.get("binding") == "secret":
                # The door mints no nonce; the buyer's own secret is the binding.
                replicated = " --replicated" if args.replicated else ""
                print(f"  to        : {quote['pay_to']}  (compute payments only)")
                print("  bound by  : a secret you choose; the nonce you sign is its sha256")
                print(
                    f"  build it  : hestia-agents pay-compute {shlex.quote(args.slug)} "
                    f"--hearth {shlex.quote(args.hearth)}{replicated} --from 0xYOURADDRESS"
                )
                print("  then      : compute ... --tx <tx hash> --secret <secret>")
            else:
                print(f"  to        : {quote['pay_to']}  (compute payments only; no nonce)")
                print("  then      : compute ... --tx <tx hash>")
        return 2
    except ComputeClientError as exc:
        print(f"  refused   : {exc}")
        return 1
    print("  result    :", _json.dumps(checked.output, sort_keys=True)[:500])
    _print_receipt(checked)
    for problem in checked.problems:
        print(f"  PROBLEM   : {problem}")
    return 1 if checked.problems else 0


def cmd_pay_compute(args: argparse.Namespace) -> int:
    """Build a direct compute payment that only you can redeem. Signs nothing.

    The compute door mints no nonce: on the production rail the hub is the till,
    and a second nonce from the hearth would be a second till that one
    authorization cannot satisfy. A direct buyer picks the nonce instead, as
    sha256 of a secret (`--secret`, or 32 random bytes made up here). The chain
    shows the nonce once the payment is mined, never the secret, and the key-less
    door redeems the payment only for whoever presents it. Step 1 prints the typed
    data to sign; step 2 (`--signature`, with the same `--secret` and
    `--valid-before`) prints the calldata.

    A secret given is held to the hearth's own rule before anything is asked or
    signed: one with fewer than 16 distinct bytes is refused at the door as
    guessable, after the buyer has paid under it. Step 1 never reads
    HESTIA_PAYMENT_SECRET: a secret left in the environment would sign every new
    payment over one nonce, which the token accepts only once. Step 2 does, so the
    secret step 1 printed need not be typed back.
    """
    import time as _time

    from hestia_agents.compute import RUN, VERIFY, ComputeClientError, payment_terms
    from hestia_agents.x402 import (
        QuoteError,
        calldata,
        is_address,
        mint_secret,
        nonce_for_secret,
        secret_refusal,
        typed_data,
    )

    try:
        given, name, again = _secret(args.secret, env=bool(args.signature))
    except ValueError as exc:
        print(f"  cannot build a payment: {exc}")
        return 1
    problem = secret_refusal(given) if given else ""
    refusal = ""
    if args.signature and not (given and args.valid_before):
        refusal = (
            "--signature needs the --secret and --valid-before step 1 printed: the "
            "signature covers the nonce the secret makes and the deadline"
        )
    elif bool(args.amount) != bool(args.pay_to):
        refusal = "--amount and --pay-to go together: both are what step 1 printed"
    elif problem:
        refusal = f"{name} {problem}"
    elif not is_address(args.sender):
        refusal = "--from is not an address (0x followed by 40 hex digits)"
    if refusal:
        print(f"  cannot build a payment: {refusal}")
        return 1
    try:
        with _http() as client:
            quote = payment_terms(
                client, args.hearth, args.slug, capability_id=VERIFY if args.replicated else RUN
            )
    except ComputeClientError as exc:
        print(f"  refused   : {exc}")
        return 1
    if quote.get("binding") != "secret":
        print(
            "  cannot build a payment: this hearth binds compute payments by "
            f"{quote.get('binding')!r}, not by a secret, and pay-compute builds only "
            "a payment redeemed with your own secret"
        )
        return 1
    if quote.get("nonce_rule") != "sha256(secret)":
        print(
            "  cannot build a payment: this hearth derives the nonce by "
            f"{quote.get('nonce_rule')!r}; pay-compute knows only sha256(secret)"
        )
        return 1
    secret = given
    if not secret:
        secret = mint_secret()
        again = f" --secret {secret}"
    valid_before = args.valid_before or int(_time.time()) + 3600
    try:
        typed = typed_data(
            quote, sender=args.sender, valid_before=valid_before, nonce=nonce_for_secret(secret)
        )
    except QuoteError as exc:
        print(f"  cannot build a payment: {exc}")
        return 1
    where = f"{shlex.quote(args.slug)} --hearth {shlex.quote(args.hearth)}" + (
        " --replicated" if args.replicated else ""
    )
    if not args.signature:
        _print_to_sign(typed)
        # A secret kept in a file stays there; one made up here has nowhere else to be.
        shown = f"in {args.secret[1:]}" if args.secret.startswith("@") else secret
        print(f"  secret         : {shown}   {KEEP_PRIVATE}")
        print(f"  nonce          : {typed['message']['nonce']}   (its sha256; public once mined)")
        print(f"  valid before   : {valid_before}")
        print()
        if not given:
            print(
                f"  Or export {SECRET_ENV}=<the secret above> and leave --secret out of the "
                "commands below: it then stays out of your shell history."
            )
        print("  Then re-run with the signature to get the calldata:")
        print(
            f"    hestia-agents pay-compute {where} --from {args.sender}{again} "
            f"--valid-before {valid_before} --amount {typed['message']['value']} "
            f"--pay-to {typed['message']['to']} --signature 0x<65-byte signature>"
        )
        return 0
    if args.amount:
        # Step 1 prints both, so the usual flow always carries them: a price or payee that
        # changed between the steps gives calldata the token would revert, after gas.
        try:
            _same_terms(typed, args)
        except QuoteError as exc:
            print(f"  cannot build a payment: {exc}")
            return 1
    try:
        data = calldata(typed, args.signature)
    except QuoteError as exc:
        print(f"  bad signature: {exc}")
        return 1
    _print_transaction(typed, data)
    max_age = quote.get("max_age_s")
    fresh = (
        f" within {max_age}s of it being mined"
        if isinstance(max_age, int) and not isinstance(max_age, bool) and max_age > 0
        else ""
    )
    kept = "" if again else f", with {SECRET_ENV} still set"
    print(f"  Then present it to the hearth{fresh}{kept}:")
    print(
        f"    hestia-agents compute {where} --input <JSON object or @file> "
        f"--tx <tx hash>{again}"
    )
    return 0


def cmd_cross_verify(args: argparse.Namespace) -> int:
    """The same function on two independently keyed hearths; compare the outputs."""
    import json as _json

    from hestia_agents.compute import RUN, VERIFY, ComputeClientError, awr_verdict, cross_verify

    if not args.hearth or len(args.hearth) != 2:
        raise SystemExit("cross-verify needs exactly two --hearth URLs")
    payload = _compute_input(args.input)
    try:
        with _http() as client:
            check = cross_verify(
                client,
                (args.hearth[0], args.hearth[1]),
                args.slug,
                payload,
                capability_id=VERIFY if args.replicated else RUN,
                function_sha256=args.pin,
                api_key=_api_key(args),
            )
    except ComputeClientError as exc:
        print(f"  refused   : {exc}")
        return 1
    print(f"  function  : {check.function_sha256}")
    print(f"  input     : {check.input_sha256}")
    for checked in (check.first, check.second):
        print(f"  {checked.hearth}")
        print(f"    output  : {checked.receipt.get('output_sha256')}")
        print(f"    key     : {checked.public_key[:44]}...")
    for note in check.notes:
        print(f"  note      : {note}")
    print(f"  verdict   : {'AGREE' if check.agree else 'DISAGREE'}")
    if args.verdict_out:
        try:
            import awr
        except ImportError:
            print("  no AWR verdict written: the awr package is not installed")
            return 0 if check.agree else 1
        if args.awr_key:
            key = awr.load_key_file(args.awr_key)
        else:
            key = awr.SigningKey.generate()
            print(f"  awr key   : ephemeral {key.did} (pass --awr-key to sign as yourself)")
        document = awr_verdict(check, key)
        with open(args.verdict_out, "w", encoding="utf-8") as handle:
            handle.write(_json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        print(f"  wrote     : {args.verdict_out} ({document['credentialSubject']['verdict']})")
    return 0 if check.agree else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hestia-agents")
    sub = parser.add_subparsers(dest="command", required=True)

    compute = sub.add_parser(
        "compute", help="run a published function on a hearth and check its signed receipt"
    )
    cross = sub.add_parser(
        "cross-verify",
        help="run the same function on two independently keyed hearths and compare",
    )
    for node in (compute, cross):
        node.add_argument("slug", help="a function listed by GET /v1/compute")
        node.add_argument("--input", required=True, help="JSON object, or @file")
        node.add_argument(
            "--replicated",
            action="store_true",
            help="use hestia.compute.verify@v1 (two replicas per hearth) instead of run",
        )
        node.add_argument("--pin", default="", help="function_sha256 to require")
        node.add_argument(
            "--api-key", default="", help="hub key (default: HESTIA_COMPUTE_API_KEY)"
        )
    compute.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
    compute.add_argument("--tx", default="", help="payment transaction hash")
    compute.add_argument(
        "--secret",
        default="",
        help=(
            "with --tx at the key-less door: the secret whose sha256 the payment signed, "
            f"or @file holding it (with --tx, default: {SECRET_ENV})"
        ),
    )
    compute.set_defaults(func=cmd_compute)

    pay_compute = sub.add_parser(
        "pay-compute",
        help="build a direct compute payment bound to your own secret (signs nothing)",
    )
    pay_compute.add_argument("slug", help="a function listed by GET /v1/compute")
    pay_compute.add_argument(
        "--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH)
    )
    pay_compute.add_argument(
        "--replicated",
        action="store_true",
        help="pay for hestia.compute.verify@v1 (two replicas) instead of run",
    )
    pay_compute.add_argument("--from", dest="sender", required=True, help="your paying address")
    pay_compute.add_argument(
        "--secret",
        default="",
        help=(
            "0x + 64 hex, or @file holding it (default: made up in step 1; step 2 needs "
            f"it, and reads {SECRET_ENV} when it is not given)"
        ),
    )
    pay_compute.add_argument(
        "--valid-before", type=int, default=0, help="unix deadline (default +1h; step 2 needs it)"
    )
    pay_compute.add_argument(
        "--amount", default="", help="step 2: the amount step 1 printed (base units it signed)"
    )
    pay_compute.add_argument(
        "--pay-to", default="", help="step 2: the payee step 1 printed (the address it signed)"
    )
    pay_compute.add_argument(
        "--signature", default="", help="the signed typed data, to get calldata"
    )
    pay_compute.set_defaults(func=cmd_pay_compute)
    cross.add_argument("--hearth", action="append", default=[], help="give it twice")
    cross.add_argument("--verdict-out", default="", help="write an AWR VerificationVerdict here")
    cross.add_argument("--awr-key", default="", help="AWR JWK key file to sign the verdict with")
    cross.set_defaults(func=cmd_cross_verify)

    sub.add_parser("build", help="regenerate agents/*/deploy.json").set_defaults(func=cmd_build)

    call = sub.add_parser("call", help="invoke one agent, optionally presenting a payment")
    call.add_argument("slug", choices=sorted(AGENTS))
    call.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
    call.add_argument("--tx", default="", help="payment transaction hash")
    call.add_argument(
        "--nonce", default="", help="payment nonce from the 402 (optional with --secret)"
    )
    call.add_argument(
        "--secret",
        default="",
        help=(
            "the payment secret pay printed, or @file holding it: shows you are the one "
            f"who paid (with --tx, default: {SECRET_ENV})"
        ),
    )
    call.set_defaults(func=cmd_call)

    pay = sub.add_parser(
        "pay", help="build the EIP-3009 payment a bound hearth accepts (signs nothing)"
    )
    pay.add_argument("slug", choices=sorted(AGENTS))
    pay.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
    pay.add_argument("--from", dest="sender", required=True, help="your paying address")
    pay.add_argument("--signature", default="", help="the signed typed data, to get calldata")
    pay.add_argument(
        "--nonce", default="", help="step 2: the nonce step 1 printed (the one you signed)"
    )
    pay.add_argument(
        "--valid-before",
        type=int,
        default=0,
        help="unix deadline (default +1h, never past the nonce's expiry; step 2 needs it)",
    )
    pay.add_argument(
        "--amount", default="", help="step 2: the amount step 1 printed (base units it signed)"
    )
    pay.add_argument(
        "--pay-to", default="", help="step 2: the payee step 1 printed (the address it signed)"
    )
    pay.set_defaults(func=cmd_pay)

    for name, func, helptext in (
        ("deploy", cmd_deploy, "deploy every agent onto a hearth"),
        ("verify", cmd_verify, "invoke each agent twice and compare the receipts"),
        ("quote", cmd_quote, "ask what each agent costs and how to pay it"),
    ):
        node = sub.add_parser(name, help=helptext)
        node.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
        node.add_argument("--only", action="append", choices=sorted(AGENTS))
        if name == "deploy":
            node.add_argument(
                "--announce",
                action="store_true",
                help="also announce to the Hub catalogue (off by default)",
            )
        node.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
