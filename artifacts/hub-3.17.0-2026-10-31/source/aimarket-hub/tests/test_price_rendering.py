"""Fractions of a cent must never render as zero.

The catalogue's real average call price is about $0.0033. A UI that prints that as `$0.00`
is not making a cosmetic mistake — it is telling a buyer the thing is free, and telling an
operator their revenue is nothing.

These tests extract the `usd()` function from the shipped page and run it under node, so
they exercise the code that actually reaches a browser rather than a Python re-implementation
of it that could agree with itself while the page disagrees with both.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "terminal-home.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _extract(name: str) -> str:
    """Pull one top-level function (and the consts it needs) out of the page."""
    source = PAGE.read_text(encoding="utf-8")
    match = re.search(rf"^  function {name}\(.*?^  }}$", source, re.S | re.M)
    assert match, f"{name}() not found in terminal-home.html — did it move or get renamed?"
    consts = re.findall(r"^  const USD_MIN_SHOWN = [^\n]+$", source, re.M)
    return "\n".join(consts) + "\n" + match.group(0)


def _run(js_functions: str, values: list) -> list[str]:
    script = (
        js_functions
        + "\nconst vals = "
        + json.dumps(values)
        + ";\nconsole.log(JSON.stringify(vals.map((v) => usd(v))));"
    )
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_sub_cent_prices_never_render_as_zero():
    usd = _extract("usd")
    values = [0.0033, 0.001, 0.0005, 0.0001, 0.00001, 0.000001]
    rendered = _run(usd, values)
    for value, shown in zip(values, rendered):
        assert shown not in ("$0.00", "$0.0", "$0."), (
            f"{value} rendered as {shown!r} — a real price shown as nothing"
        )
        assert shown.startswith("$0.0"), f"{value} rendered as {shown!r}"
        # The digits must survive: reading the rendered string back must recover the value.
        assert float(shown.lstrip("$")) == pytest.approx(value, rel=1e-9)


def test_a_price_below_the_display_floor_says_less_than_rather_than_zero():
    """Below what six decimals can show, the honest answer is "less than", not "nothing"."""
    rendered = _run(_extract("usd"), [0.0000001, 1e-12])
    for shown in rendered:
        assert shown.startswith("<$"), f"expected a less-than form, got {shown!r}"
        assert shown != "$0.00"


def test_a_truncated_dollar_sign_is_never_produced():
    """`toFixed(5)` on 0.000001 gives "0.00000", and stripping trailing zeros gave "$0." —
    a currency string with no number in it at all. It shipped."""
    rendered = _run(_extract("usd"), [1e-6, 1e-7, 1e-8, 0.0000015])
    for shown in rendered:
        assert not shown.endswith("."), f"{shown!r} has no digits after the point"
        assert re.fullmatch(r"<?-?\$\d+\.\d+", shown), f"malformed currency string {shown!r}"


def test_ordinary_amounts_are_unchanged():
    """The fix must not disturb the common case."""
    assert _run(_extract("usd"), [0, 0.01, 0.06, 1.5, 12]) == [
        "$0.00", "$0.01", "$0.06", "$1.50", "$12.00",
    ]


def test_zero_is_still_zero_and_free_is_still_a_word():
    """`usd(0)` is a legitimate zero — a summed volume of nothing really is $0.00. It is
    `priceUsd` that turns a zero PRICE into the word "free", and that split must survive."""
    assert _run(_extract("usd"), [0]) == ["$0.00"]
    page = PAGE.read_text(encoding="utf-8")
    assert "function priceUsd" in page
    assert "t('price_free')" in page.split("function priceUsd", 1)[1][:300]
