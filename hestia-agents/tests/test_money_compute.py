"""money.compute@v1: decimal all the way, every split sums, every rounding is named."""

from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal

import pytest

from hestia_agents.manifests import handler_source


@pytest.fixture(scope="module")
def handle():
    namespace: dict = {}
    exec(compile(handler_source("money-compute"), "money-compute", "exec"), namespace)  # noqa: S102
    return namespace["handle"]


def invoice(handle, lines, **extra):
    return handle({"op": "invoice", "lines": lines, **extra})


# ------------------------------------------------------------------ invoice


def test_point_one_plus_point_two_is_point_three(handle) -> None:
    out = invoice(handle, [{"unit_price": "0.10"}, {"unit_price": 0.2}])
    assert out["totals"] == {"net": "0.30", "tax": "0.00", "gross": "0.30"}


def test_vat_rounded_per_line_or_per_rate(handle) -> None:
    lines = [{"unit_price": "0.33", "tax_rate": "19"}] * 3
    per_line = invoice(handle, lines)
    per_rate = invoice(handle, lines, rounding_level="rate")
    assert per_line["totals"] == {"net": "0.99", "tax": "0.18", "gross": "1.17"}
    assert per_rate["totals"] == {"net": "0.99", "tax": "0.19", "gross": "1.18"}
    assert per_rate["tax_breakdown"] == [{"tax_rate": "19", "net": "0.99", "tax": "0.19",
                                          "gross": "1.18"}]
    assert "net" not in per_rate["lines"][0], "per-rate rounding has no rounded line values"


def test_mixed_rates_and_discounts(handle) -> None:
    out = invoice(handle, [
        {"description": "book", "quantity": "2", "unit_price": "12.50", "tax_rate": "7",
         "discount": {"percent": "10"}},
        {"description": "lamp", "quantity": 1, "unit_price": "40.00", "tax_rate": "19",
         "discount": {"amount": "5.00"}},
        {"description": "postage", "unit_price": "4.90"},
    ])
    book, lamp, postage = out["lines"]
    assert (book["subtotal"], book["discount"], book["net"], book["tax"]) == (
        "25.00", "2.50", "22.50", "1.58")
    assert (lamp["net"], lamp["tax"], lamp["gross"]) == ("35.00", "6.65", "41.65")
    assert postage["tax_rate"] == "0" and postage["gross"] == "4.90"
    assert [b["tax_rate"] for b in out["tax_breakdown"]] == ["0", "7", "19"]
    assert out["totals"] == {"net": "62.40", "tax": "8.23", "gross": "70.63"}


def test_tax_inclusive_prices(handle) -> None:
    out = invoice(handle, [{"unit_price": "119.00", "tax_rate": "19"}], tax_inclusive=True)
    assert out["totals"] == {"net": "100.00", "tax": "19.00", "gross": "119.00"}


def test_currencies_without_and_with_three_decimals(handle) -> None:
    jpy = invoice(handle, [{"quantity": 3, "unit_price": "1999", "tax_rate": "10"}],
                  currency="JPY")
    assert jpy["decimals"] == 0 and jpy["totals"] == {"net": "5997", "tax": "600", "gross": "6597"}
    kwd = invoice(handle, [{"unit_price": "1.2345", "tax_rate": "0"}], currency="KWD")
    assert kwd["totals"]["gross"] == "1.235"
    usdc = invoice(handle, [{"quantity": "3", "unit_price": "0.0333333"}], currency="usdc")
    assert usdc["totals"]["gross"] == "0.100000"


@pytest.mark.parametrize(("mode", "expected"), [("half_up", "0.13"), ("half_even", "0.12"),
                                                ("down", "0.12"), ("up", "0.13")])
def test_rounding_modes_are_named_and_applied(handle, mode, expected) -> None:
    out = invoice(handle, [{"unit_price": "0.125"}], rounding=mode)
    assert out["totals"]["gross"] == expected and out["rounding"] == mode


# ------------------------------------------------------------------ split


def test_hundred_three_ways(handle) -> None:
    out = handle({"op": "split", "amount": "100.00", "shares": [1, 1, 1]})
    assert [a["amount"] for a in out["allocations"]] == ["33.34", "33.33", "33.33"]
    assert out["sums_to_amount"] is True and out["remainder_units_distributed"] == 1


def test_basis_points_of_a_usdc_price(handle) -> None:
    out = handle({"op": "split", "amount": "0.05", "currency": "USDC",
                  "shares": [{"name": "publisher", "weight": 9900},
                             {"name": "hub", "weight": 100}]})
    assert [(a["name"], a["amount"], a["share"]) for a in out["allocations"]] == [
        ("publisher", "0.049500", "99.0000%"), ("hub", "0.000500", "1.0000%")]


def test_percent_weights_and_a_zero_share(handle) -> None:
    out = handle({"op": "split", "amount": "10", "shares": ["33.3", "66.7", "0"]})
    assert [a["amount"] for a in out["allocations"]] == ["3.33", "6.67", "0.00"]


def test_remainder_methods(handle) -> None:
    base = {"op": "split", "amount": "0.05", "shares": [1, 1, 1]}
    assert [a["amount"] for a in handle({**base, "method": "last"})["allocations"]] == [
        "0.01", "0.02", "0.02"]
    assert [a["amount"] for a in handle({**base, "method": "first"})["allocations"]] == [
        "0.02", "0.02", "0.01"]


def test_random_splits_always_sum_and_stay_within_a_unit(handle) -> None:
    rng = random.Random(11)
    for _ in range(300):
        cents = rng.randint(0, 10_000_000)
        weights = [rng.choice([0, 1, 2, 3, 7, 50, 9999]) for _ in range(rng.randint(1, 9))]
        if not any(weights):
            weights[0] = 1
        amount = Decimal(cents).scaleb(-2)
        out = handle({"op": "split", "amount": str(amount), "shares": weights})
        parts = [Decimal(a["amount"]) for a in out["allocations"]]
        assert sum(parts) == amount
        for part, w in zip(parts, weights, strict=True):
            exact = amount * w / sum(weights)
            assert abs(part - exact) < Decimal("0.01")


# ------------------------------------------------------------------ convert


def test_convert_names_its_rounding_error(handle) -> None:
    out = handle({"op": "convert", "amount": "100", "rate": "149.5675", "to": "JPY"})
    assert out["result"] == "14957" and out["exact"] == "14956.7500"
    assert Decimal(out["rounding_error"]) == Decimal("0.25")
    refund = handle({"op": "convert", "amount": "-12.34", "rate": "1.0835", "to": "USD"})
    exact = Decimal("-12.34") * Decimal("1.0835")
    assert refund["result"] == str(exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ refusals


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"op": "sum"}, "op must be"),
        ({"op": "invoice", "lines": [{"unit_price": "1,234.56"}]}, "no thousands separators"),
        ({"op": "invoice", "lines": [{"unit_price": "NaN"}]}, "finite"),
        ({"op": "invoice", "lines": [{"unit_price": "abc"}]}, "not a number"),
        ({"op": "invoice", "lines": [{"unit_price": "-1"}]}, "negative"),
        ({"op": "invoice", "lines": [{"unit_price": "1", "discount": {"percent": "120"}}]},
         "above 100"),
        ({"op": "invoice", "lines": [{"unit_price": "1", "discount": {"amount": "2"}}]},
         "more than the line"),
        ({"op": "invoice", "lines": [{"unit_price": "1"}], "rounding": "nearest"}, "rounding"),
        ({"op": "invoice", "lines": []}, "send 'lines'"),
        ({"op": "invoice", "lines": [{"unit_price": "1"}], "decimals": 19}, "0 to 18"),
        ({"op": "split", "amount": "1.005", "shares": [1]}, "more decimals"),
        ({"op": "split", "amount": "1", "shares": [0, 0]}, "zero"),
        ({"op": "convert", "amount": "1", "rate": "0"}, "zero"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)


def test_reproducible(handle) -> None:
    payload = {"op": "split", "amount": "1000.00", "shares": [3, 7, 11]}
    assert handle(payload) == handle(payload)
