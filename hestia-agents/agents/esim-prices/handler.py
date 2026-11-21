"""esim.price.history@v1: how has the wholesale price of eSIM plans for a country moved?

The data is our own record: the modelmarket.dev demo node reads the eSIM Access wholesale catalogue
(about 1,800 plans), a recorder on its host compares every read with the one before (every 15
minutes since 2026-11-18 14:29 UTC), and copies from the host's nightly backups go back to
2026-10-19. The public copy is https://esim.modelmarket.dev/price-history/v1/: index.json and one
file per country. It gives each change of a plan's wholesale cost in percent and never the cost
itself; the node's sell price is its quote (POST https://esim.modelmarket.dev/agents/quote).

Give `country` (ISO 3166 alpha-2, e.g. "JP"): every plan that covers it, country plans and
regional ones, optionally narrowed by `data_gb`, `days`, `plan` (a plan id) or
`regional: false`. With no country: the overview, every batch of changes so far. `window_seconds`
(default 600, the eSIM kit's quote window) asks how likely a plan's price is to move inside it,
estimated from the 15-minute reads.

One supplier, catalogue costs, not orders: what the node read, not what anyone paid. Before the
15-minute reads a change is dated only to the gap between two backup copies.
"""

BASE = "https://esim.modelmarket.dev/price-history/v1/"
GB = 1 << 30
DAY = 24 * 3600


def _get(path):
    reply = fetch(BASE + path)  # noqa: F821 — the sandbox provides fetch()
    if reply.status == 404:
        return None
    if not reply.ok:
        raise RuntimeError("the price history answered HTTP " + str(reply.status) + " for " + path)
    return reply.json()


def _number(payload, name, low, high):
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(name + " must be a number from " + str(low) + " to " + str(high))
    return value


def _window(index, seconds):
    rate = (index.get("live_rate") or {}).get("per_plan_second")
    if rate is None:
        return {"seconds": seconds, "note": "no 15-minute reads to estimate from yet"}
    # 1 - exp(-x) without math: the series converges fast for the small x seen here.
    x, term, chance = rate * seconds, 1.0, 0.0
    for n in range(1, 30):
        term *= x / n
        chance += term if n % 2 else -term
    return {
        "seconds": seconds,
        "chance_a_plan_changes_pct": round(100 * chance, 4),
        "based_on": str(index["live_rate"]["price_changes"]) + " price changes in "
        + str(index["live_rate"]["plan_days_observed"]) + " plan-days of 15-minute reads",
        "note": "a Poisson estimate from the average rate; changes come in batches, so the real "
                "chance is near zero most of the time and high in the minutes a batch lands",
    }


def _source(index):
    coverage = index["coverage"]
    copies = coverage.get("daily_copies") or []
    return {
        "url": BASE,
        "supplier": index.get("supplier"),
        "unit": index.get("unit"),
        "generated_at": index.get("generated_at"),
        "last_read_at": coverage.get("last_read_at"),
        "backup_copies": {"count": len(copies), "first": copies[0] if copies else None,
                          "last": copies[-1] if copies else None},
        "live_from": coverage.get("live_from"),
        "live_reads": coverage.get("live_reads"),
        "median_read_interval_minutes": coverage.get("median_interval_minutes"),
        "longest_read_gap_minutes": coverage.get("longest_gap_minutes"),
        "note": coverage.get("note"),
    }


def _prices(events):
    return [e for e in events if e.get("event") == "price" and e.get("change_pct") is not None]


def handle(payload):
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("send an object: country (e.g. \"JP\"), or nothing for the overview")
    seconds = _number(payload, "window_seconds", 1, 7 * DAY)
    seconds = 600 if seconds is None else int(seconds)
    index = _get("index.json")
    if not index or index.get("version") != 1:
        raise RuntimeError("the price history index is missing or of an unknown version")
    out = {"source": _source(index), "window": _window(index, seconds)}

    country = payload.get("country")
    if country is None:
        if payload.get("plan"):
            raise ValueError("give the country the plan covers too, e.g. country \"JP\"")
        batches = index.get("batches") or []
        out.update(
            mode="overview",
            plans_now=index.get("plans_now"),
            price_changes=index.get("price_changes"),
            rises=index.get("rises"),
            falls=index.get("falls"),
            per_1000_plans_per_day=(index.get("live_rate") or {}).get("per_1000_plans_per_day"),
            batches=batches,
            countries=len(index.get("countries") or {}),
            next="give country (ISO alpha-2) for its plans and their changes",
        )
        return out

    code = str(country).strip().upper()
    if len(code) != 2 or not code.isalpha() or not code.isascii():
        raise ValueError("country must be an ISO 3166 alpha-2 code such as JP")
    out.update(mode="country", country=code)
    if code not in (index.get("countries") or {}):
        out.update(plans_matched=0, plans=[], detail="no plan in this catalogue covers " + code)
        return out
    doc = _get("countries/" + code + ".json")
    if not doc:
        raise RuntimeError("the index lists " + code + " but its file is missing; "
                           "try again shortly")

    data_gb = _number(payload, "data_gb", 0, 1000)
    days = _number(payload, "days", 1, 3650)
    wanted = str(payload.get("plan") or "").strip()
    regional = payload.get("regional", True) is not False
    plans = []
    for plan in doc.get("plans") or []:
        if wanted and plan.get("id") != wanted:
            continue
        if not regional and plan.get("kind") == "region":
            continue
        size = plan.get("data_bytes")
        if data_gb is not None and (not isinstance(size, int) or abs(size / GB - data_gb) > 0.05):
            continue
        if days is not None and plan.get("days") != days:
            continue
        plans.append(plan)
    if wanted and not plans:
        raise ValueError("no plan " + wanted + " covers " + code + " in this catalogue")

    changed, unchanged, all_prices = [], 0, []
    for plan in plans:
        events = plan.get("events") or []
        prices = _prices(events)
        all_prices += prices
        if not events:
            unchanged += 1
            continue
        size = plan.get("data_bytes")
        entry = {"id": plan.get("id"), "name": plan.get("name"), "kind": plan.get("kind"),
                 "covers": plan.get("covers"), "days": plan.get("days"),
                 "data_gb": round(size / GB, 2) if isinstance(size, int) else None,
                 "listed": plan.get("listed"), "events": events}
        if prices:
            entry["last_price_change_at"] = prices[-1]["at"]
        changed.append(entry)
    changed.sort(key=lambda e: e.get("last_price_change_at") or "", reverse=True)
    pct = [e["change_pct"] for e in all_prices]
    rises = [x for x in pct if x > 0]
    falls = [x for x in pct if x < 0]
    out.update(
        plans_matched=len(plans),
        plans_unchanged=unchanged,
        price_changes=len(pct),
        rises=len(rises),
        falls=len(falls),
        largest_rise_pct=max(rises) if rises else None,
        largest_fall_pct=min(falls) if falls else None,
        last_price_change_at=max((e["at"] for e in all_prices), default=None),
        price_change_dates=sorted({e["at"] for e in all_prices}),
        plans=changed,
    )
    return out
