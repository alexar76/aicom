"""A sealed-bubble hub must not advertise a real payment rail.

`payment_testnet` appears exactly once in the codebase — in
`/.well-known/ai-market.json`. That makes it the one field a crawler can use to tell a real
rail from a simulated one, and `uni.modelmarket.dev` was getting it wrong: it served
`payment_testnet: false` with `supported_chains: ["base"]` and the live hub's own name while
running on Anvil chain 31337 with virtual amounts. `deploy_uni_hub.sh` warns about exactly
that in its header; the env said mainnet and nothing checked it against the realm.
"""

from __future__ import annotations

import importlib

import pytest


def _fresh_config(monkeypatch, **env: str):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import aimarket_hub.config as cfg

    importlib.reload(cfg)
    return cfg


def test_uni_realm_advertises_testnet_even_when_the_env_says_mainnet(monkeypatch):
    cfg = _fresh_config(
        monkeypatch,
        AIMARKET_CHAIN_REALM="uni",
        AIFACTORY_PAYMENT_TESTNET="0",
    )
    assert cfg.HubConfig().payment_testnet is True, (
        "a UNI deployment claimed mainnet — a crawler would index simulated amounts as real"
    )


@pytest.mark.parametrize("realm_value", ["uni", "bubble", "virtual"])
def test_every_alias_of_the_bubble_realm_is_covered(monkeypatch, realm_value):
    """`realm()` accepts three spellings; the guard must not key on one of them."""
    cfg = _fresh_config(
        monkeypatch,
        AIMARKET_CHAIN_REALM=realm_value,
        AIFACTORY_PAYMENT_TESTNET="0",
    )
    assert cfg.HubConfig().payment_testnet is True


def test_live_realm_still_honours_the_env(monkeypatch):
    """The guard must not quietly turn the real hub into a testnet advertisement."""
    cfg = _fresh_config(
        monkeypatch,
        AIMARKET_CHAIN_REALM="live",
        AIFACTORY_PAYMENT_TESTNET="0",
    )
    assert cfg.HubConfig().payment_testnet is False


def test_testnet_env_wins_in_both_realms(monkeypatch):
    for realm_value in ("live", "uni"):
        cfg = _fresh_config(
            monkeypatch,
            AIMARKET_CHAIN_REALM=realm_value,
            AIFACTORY_PAYMENT_TESTNET="1",
        )
        assert cfg.HubConfig().payment_testnet is True


def _code_lines_mentioning(text: str, needle: str) -> list[int]:
    """Line numbers where `needle` appears in CODE — comments and strings excluded.

    This guard used to scan raw source lines, which made it fire on prose: a comment in
    `contracts_declaration.py` saying "read this from the network, NOT from
    `config.payment_testnet`" — a comment whose entire purpose is to record that the flag
    is deliberately unused — failed the test. A guard that can be satisfied by rewording a
    comment instead of by changing behaviour trains people to reword comments.
    """
    import io
    import tokenize

    found: list[int] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Unparseable: fall back to the blunt scan rather than silently passing.
        return [n for n, line in enumerate(text.splitlines(), 1) if needle in line]
    for token in tokens:
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        if needle in token.string:
            found.append(token.start[0])
    return found


def test_the_flag_is_advertisement_only(monkeypatch):
    """Guard the premise: if `payment_testnet` ever starts GATING a payment path, forcing it
    for UNI stops being a safe honesty fix and this needs revisiting."""
    from pathlib import Path

    pkg = Path(__file__).resolve().parents[1] / "aimarket_hub"
    uses = []
    for f in sorted(pkg.rglob("*.py")):
        text = f.read_text(errors="ignore")
        lines = text.splitlines()
        for n in _code_lines_mentioning(text, "payment_testnet"):
            if "def _advertised" in lines[n - 1]:
                continue
            uses.append(f"{f.name}:{n}")
    # config.py declares it; the well-known document (hub_routes/wellknown.py) publishes it.
    # Anything else means it acquired behaviour.
    unexpected = [u for u in uses if not u.startswith(("config.py", "wellknown.py"))]
    assert not unexpected, (
        f"payment_testnet is now read outside config/api ({unexpected}) — check it does not "
        "gate a payment path before keeping the UNI override"
    )


def test_the_guard_reads_code_and_not_comments():
    """Guard the guard: it must still catch a real read, and ignore a mention in prose."""
    prose_only = (
        '"""A docstring that mentions payment_testnet."""\n'
        "# and a comment about payment_testnet\n"
        "x = 1\n"
    )
    assert _code_lines_mentioning(prose_only, "payment_testnet") == []

    real_read = "if config.payment_testnet:\n    pass\n"
    assert _code_lines_mentioning(real_read, "payment_testnet") == [1]
