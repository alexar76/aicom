"""Money arithmetic that adds up: invoices, splits, conversions, to the last minor unit.

Floating point cannot hold 0.10, and a language model asked to add a column of prices
guesses. Everything here is decimal (the `decimal` module, never float), every rounding
names its mode and where it happened, and a split always sums to exactly the amount it
split — the remainder goes to the largest fractional shares, ties to the earlier share.

  invoice   lines of quantity x unit price, line discounts, tax per rate (exclusive or
            inclusive prices), rounded per line or per tax rate; totals and a tax breakdown
  split     an amount by weights / percents / basis points, exact to the minor unit
  convert   an amount at a rate you supply (no live prices here), rounded to the target

Amounts travel as decimal strings ("19.99"); a JSON number is read through its shortest
decimal form. Minor units follow ISO 4217 (JPY 0, KWD 3, ...) or `decimals` you give;
USDC is 6, BTC 8, ETH 18.
"""

import decimal

D = decimal.Decimal
MAX_LINES = 1000
MAX_SHARES = 1000

ROUNDING = {
    "half_up": decimal.ROUND_HALF_UP,
    "half_even": decimal.ROUND_HALF_EVEN,
    "half_down": decimal.ROUND_HALF_DOWN,
    "up": decimal.ROUND_UP,
    "down": decimal.ROUND_DOWN,
    "ceiling": decimal.ROUND_CEILING,
    "floor": decimal.ROUND_FLOOR,
}

_EXPONENT = {}
for _code in ("BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF").split():
    _EXPONENT[_code] = 0
for _code in ("BHD IQD JOD KWD LYD OMR TND").split():
    _EXPONENT[_code] = 3
for _code, _places in (("CLF", 4), ("UYW", 4), ("USDC", 6), ("USDT", 6), ("BTC", 8),
                       ("ETH", 18)):
    _EXPONENT[_code] = _places


def _decimals(payload, key="currency", override="decimals"):
    if override in payload:
        places = payload.get(override)
        if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 18:
            raise ValueError("'" + override + "' must be an integer from 0 to 18")
        return places
    code = payload.get(key)
    if code is None:
        return 2
    if not isinstance(code, str) or not (3 <= len(code) <= 5) or not code.isalpha():
        raise ValueError("'" + key + "' must be a currency code like EUR, JPY or USDC")
    return _EXPONENT.get(code.upper(), 2)


def _amount(value, where, allow_negative=False):
    if isinstance(value, bool) or value is None:
        raise ValueError(where + " must be a decimal string like \"19.99\"")
    if isinstance(value, (int, float)):
        value = str(value)  # a float's str is its shortest round-trip decimal: 0.2 -> "0.2"
    if not isinstance(value, str):
        raise ValueError(where + " must be a decimal string like \"19.99\"")
    text = value.strip()
    if "," in text or "_" in text or " " in text:
        raise ValueError(where + " must use a dot for decimals and no thousands separators")
    try:
        number = D(text)
    except decimal.InvalidOperation:
        raise ValueError(where + " is not a number: " + text[:40]) from None
    if not number.is_finite():
        raise ValueError(where + " must be finite")
    if number < 0 and not allow_negative:
        raise ValueError(where + " must not be negative")
    return number


def _rounding(payload):
    mode = payload.get("rounding", "half_up")
    if mode not in ROUNDING:
        raise ValueError("rounding must be one of " + ", ".join(sorted(ROUNDING)))
    return mode


def _q(value, places, mode):
    out = value.quantize(D(1).scaleb(-places), rounding=ROUNDING[mode])
    return out if out != 0 else abs(out)


def _s(value, places):
    """A fixed-point string with exactly `places` decimals."""
    return format(_q(value, places, "half_even") if value.as_tuple().exponent < -places else
                  value.quantize(D(1).scaleb(-places)), "f")


# ------------------------------------------------------------------ invoice


def _invoice(payload):
    places = _decimals(payload)
    mode = _rounding(payload)
    level = payload.get("rounding_level", "line")
    if level not in ("line", "rate"):
        raise ValueError("rounding_level must be line (round each line) or rate (round each "
                         "tax-rate total)")
    inclusive = payload.get("tax_inclusive", False)
    if not isinstance(inclusive, bool):
        raise ValueError("tax_inclusive must be true or false")
    default_rate = payload.get("tax_rate", "0")
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("send 'lines': [{quantity, unit_price, tax_rate?, discount?}, ...]")
    if len(lines) > MAX_LINES:
        raise ValueError("at most " + str(MAX_LINES) + " lines")
    hundred = D(100)
    out_lines, groups = [], {}
    for i, line in enumerate(lines):
        where = "lines[" + str(i) + "]"
        if not isinstance(line, dict):
            raise ValueError(where + " must be an object")
        qty = _amount(line.get("quantity", "1"), where + ".quantity")
        price = _amount(line.get("unit_price"), where + ".unit_price")
        rate = _amount(line.get("tax_rate", default_rate), where + ".tax_rate")
        if rate > 1000:
            raise ValueError(where + ".tax_rate is a percent; " + str(rate) + " is not plausible")
        base = qty * price
        disc = line.get("discount")
        if disc is None:
            discount = D(0)
        elif isinstance(disc, dict) and "percent" in disc:
            pct = _amount(disc.get("percent"), where + ".discount.percent")
            if pct > hundred:
                raise ValueError(where + ".discount.percent is above 100")
            discount = base * pct / hundred
        elif isinstance(disc, dict) and "amount" in disc:
            discount = _amount(disc.get("amount"), where + ".discount.amount")
            if discount > base:
                raise ValueError(where + ".discount.amount is more than the line")
        else:
            raise ValueError(where + ".discount must be {percent} or {amount}")
        after = base - discount
        if inclusive:
            gross = _q(after, places, mode) if level == "line" else after
            tax = gross * rate / (hundred + rate)
            tax = _q(tax, places, mode) if level == "line" else tax
            net = gross - tax
        else:
            net = _q(after, places, mode) if level == "line" else after
            tax = net * rate / hundred
            tax = _q(tax, places, mode) if level == "line" else tax
            gross = net + tax
        key = format(rate.normalize(), "f")
        group = groups.setdefault(key, {"rate": rate, "net": D(0), "tax": D(0), "gross": D(0)})
        group["net"] += net
        group["tax"] += tax
        group["gross"] += gross
        entry = {"line": i, "quantity": format(qty.normalize(), "f"),
                 "unit_price": format(price, "f"), "subtotal": _s(_q(base, places, mode), places),
                 "discount": _s(_q(discount, places, mode), places), "tax_rate": key}
        if "description" in line:
            entry["description"] = str(line.get("description"))[:200]
        if level == "line":
            entry.update({"net": _s(net, places), "tax": _s(tax, places),
                          "gross": _s(gross, places)})
        out_lines.append(entry)
    breakdown = []
    total_net = total_tax = total_gross = D(0)
    for key in sorted(groups, key=lambda k: groups[k]["rate"]):
        g = groups[key]
        if level == "rate":
            if inclusive:
                gross = _q(g["gross"], places, mode)
                tax = _q(gross * g["rate"] / (hundred + g["rate"]), places, mode)
                net = gross - tax
            else:
                net = _q(g["net"], places, mode)
                tax = _q(net * g["rate"] / hundred, places, mode)
                gross = net + tax
        else:
            net, tax, gross = g["net"], g["tax"], g["gross"]
        total_net += net
        total_tax += tax
        total_gross += gross
        breakdown.append({"tax_rate": key, "net": _s(net, places), "tax": _s(tax, places),
                          "gross": _s(gross, places)})
    return {
        "op": "invoice", "decimals": places, "rounding": mode, "rounding_level": level,
        "tax_inclusive": inclusive, "lines": out_lines, "tax_breakdown": breakdown,
        "totals": {"net": _s(total_net, places), "tax": _s(total_tax, places),
                   "gross": _s(total_gross, places)},
    }


# ------------------------------------------------------------------ split


def _split(payload):
    places = _decimals(payload)
    amount = _amount(payload.get("amount"), "amount")
    scale = D(1).scaleb(-places)
    if amount != amount.quantize(scale, rounding=decimal.ROUND_DOWN):
        raise ValueError("amount has more decimals than " + str(places) + "; round it first or "
                         "send 'decimals'")
    units = int(amount.scaleb(places))
    shares = payload.get("shares")
    if not isinstance(shares, list) or not shares:
        raise ValueError("send 'shares': weights, or [{name, weight}] (percent or bps work too)")
    if len(shares) > MAX_SHARES:
        raise ValueError("at most " + str(MAX_SHARES) + " shares")
    names, weights = [], []
    for i, share in enumerate(shares):
        where = "shares[" + str(i) + "]"
        if isinstance(share, dict):
            names.append(str(share.get("name", i)))
            weights.append(_amount(share.get("weight"), where + ".weight"))
        else:
            names.append(str(i))
            weights.append(_amount(share, where))
    total_weight = sum(weights, D(0))
    if total_weight <= 0:
        raise ValueError("the weights must not all be zero")
    # Exact rational arithmetic on integers: weights scaled to a common integer base.
    exponent = min(min(w.as_tuple().exponent for w in weights), 0)
    ints = [int(w.scaleb(-exponent)) for w in weights]
    whole = sum(ints)
    floors, remainders = [], []
    for i, w in enumerate(ints):
        q, r = divmod(units * w, whole)
        floors.append(q)
        remainders.append((-r, i))
    leftover = units - sum(floors)
    method = payload.get("method", "largest_remainder")
    if method == "largest_remainder":
        order = [i for _, i in sorted(remainders)]
    elif method == "first":
        order = list(range(len(ints)))
    elif method == "last":
        order = list(range(len(ints) - 1, -1, -1))
    else:
        raise ValueError("method must be largest_remainder, first or last")
    order = [i for i in order if ints[i] > 0]
    for k in range(leftover):
        floors[order[k % len(order)]] += 1
    allocations = []
    for i, part in enumerate(floors):
        allocations.append({"name": names[i], "weight": format(weights[i].normalize(), "f"),
                            "amount": _s(D(part).scaleb(-places), places),
                            "share": format((weights[i] / total_weight * 100).quantize(
                                D("0.0001"), rounding=decimal.ROUND_HALF_EVEN), "f") + "%"})
    check = sum(floors)
    return {"op": "split", "decimals": places, "method": method, "amount": _s(amount, places),
            "allocations": allocations, "remainder_units_distributed": leftover,
            "sums_to_amount": check == units}


# ------------------------------------------------------------------ convert


def _convert(payload):
    amount = _amount(payload.get("amount"), "amount", allow_negative=True)
    rate = _amount(payload.get("rate"), "rate")
    if rate == 0:
        raise ValueError("rate must not be zero")
    places = _decimals(payload, "to", "to_decimals")
    mode = _rounding(payload)
    exact = amount * rate
    result = _q(exact, places, mode)
    return {"op": "convert", "amount": format(amount, "f"), "rate": format(rate, "f"),
            "inverse_rate": format((D(1) / rate).quantize(D("1E-12"),
                                                          rounding=decimal.ROUND_HALF_EVEN), "f"),
            "exact": format(exact, "f"), "result": _s(result, places), "decimals": places,
            "rounding": mode, "rounding_error": format(result - exact, "f")}


def handle(payload):
    op = payload.get("op")
    if op == "invoice":
        return _invoice(payload)
    if op == "split":
        return _split(payload)
    if op == "convert":
        return _convert(payload)
    raise ValueError("op must be invoice, split or convert")
