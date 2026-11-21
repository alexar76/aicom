"""esim.price.history@v1 against the public price history as it was on 2026-11-20.

`esim_prices_vectors.json` holds what https://esim.modelmarket.dev/price-history/v1/ served at
2026-11-20 ~20:35Z (last read 20:32:26Z): index.json, countries/JP.json and countries/DE.json.
The 46 rises of 16 November (the DEV.to article "Wholesale eSIM prices don't drift, they jump")
are in them: Japan 20 GB / 30 days +40.2 %.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hestia_agents.manifests import deploy_body, handler_source

V = json.loads((Path(__file__).parent / "esim_prices_vectors.json").read_text(encoding="utf-8"))
BASE = "https://esim.modelmarket.dev/price-history/v1/"


class Reply:
    def __init__(self, doc, status=200):
        self.status, self.error, self.headers = status, None, {}
        self.text = json.dumps(doc)

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.text)


def load(v=V):
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        asked.append(url)
        assert url.startswith(BASE) and method == "GET"
        doc = v.get(url[len(BASE):])
        return Reply(doc) if doc is not None else Reply({"error": "not found"}, 404)

    namespace = {"fetch": fetch}
    exec(compile(handler_source("esim-prices"), "esim-prices", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked


def test_overview_lists_the_batches_and_the_coverage() -> None:
    handle, asked = load()
    out = handle({})
    assert out["mode"] == "overview" and asked == [BASE + "index.json"]
    assert out["plans_now"] == 1828 and out["countries"] == len(V["index.json"]["countries"])
    rises = [b for b in out["batches"] if b["rises"]]
    assert any(b["at"] == "2026-11-16T02:54:44.483Z" and b["rises"] == 46 for b in rises)
    assert out["source"]["backup_copies"] == {"count": 18, "first": "2026-10-19T02:54:30.362Z",
                                               "last": "2026-11-18T02:40:52.242Z"}
    assert out["source"]["live_from"] == "2026-11-18T14:29:24.407Z"
    assert 0 < out["window"]["chance_a_plan_changes_pct"] < 0.05 and out["window"]["seconds"] == 600


def test_japan_twenty_gigabytes_thirty_days_rose_forty_percent_on_16_november() -> None:
    handle, asked = load()
    out = handle({"country": "jp", "data_gb": 20, "days": 30, "regional": False})
    assert asked == [BASE + "index.json", BASE + "countries/JP.json"]
    assert out["country"] == "JP" and out["rises"] >= 1
    plan = next(p for p in out["plans"] if p["id"] == "JP_20_30")
    (rise,) = [e for e in plan["events"] if e["event"] == "price"]
    assert rise["change_pct"] == 40.2 and rise["resolution"] == "daily"
    assert rise["prev_at"] == "2026-11-15T03:17:43.218Z"
    assert rise["at"] == "2026-11-16T02:54:44.483Z"
    assert all(p["kind"] != "region" for p in out["plans"])
    text = json.dumps(out)
    assert "cost_usd" not in text and "cost_before" not in text  # percent only


def test_regional_plans_are_included_by_default_and_counted() -> None:
    handle, _ = load()
    every = handle({"country": "DE"})
    only = handle({"country": "DE", "regional": False})
    assert every["plans_matched"] > only["plans_matched"]
    assert any(p["kind"] == "region" and p["covers"] > 1 for p in every["plans"])
    assert every["price_changes"] == every["rises"] + every["falls"]
    assert every["price_change_dates"] == sorted(every["price_change_dates"])


def test_one_plan_and_a_plan_that_does_not_cover_the_country() -> None:
    handle, _ = load()
    out = handle({"country": "JP", "plan": "JP_50_30"})
    assert out["plans_matched"] == 1 and out["largest_rise_pct"] == 58.8
    with pytest.raises(ValueError, match="no plan XX_1_1 covers JP"):
        handle({"country": "JP", "plan": "XX_1_1"})
    with pytest.raises(ValueError, match="country the plan covers"):
        handle({"plan": "JP_50_30"})


def test_unknown_country_and_bad_input() -> None:
    handle, asked = load()
    out = handle({"country": "AQ"})
    assert out["plans_matched"] == 0 and "covers AQ" in out["detail"] and len(asked) == 1
    for bad in ({"country": "JPN"}, {"country": "J1"}, {"country": "JP", "data_gb": "3"},
                {"country": "JP", "days": 0}, {"window_seconds": True}):
        with pytest.raises(ValueError):
            handle(bad)
    with pytest.raises(ValueError):
        handle(["JP"])


def test_window_estimate_scales_and_index_problems_are_errors() -> None:
    handle, _ = load()
    short = handle({"window_seconds": 60})["window"]["chance_a_plan_changes_pct"]
    day = handle({"window_seconds": 86400})["window"]["chance_a_plan_changes_pct"]
    assert 0 < short < day < 100
    rate = V["index.json"]["live_rate"]["per_plan_second"]
    assert abs(day - 100 * (1 - 2.718281828459045 ** (-rate * 86400))) < 1e-3
    broken = copy.deepcopy(V)
    broken["index.json"]["version"] = 2
    with pytest.raises(RuntimeError, match="unknown version"):
        load(broken)[0]({})
    missing = copy.deepcopy(V)
    del missing["countries/JP.json"]
    with pytest.raises(RuntimeError, match="file is missing"):
        load(missing)[0]({"country": "JP"})


def test_deterministic_and_declared_egress() -> None:
    handle, _ = load()
    assert json.dumps(handle({"country": "JP"})) == json.dumps(load()[0]({"country": "JP"}))
    body = deploy_body("esim-prices")
    assert body["egress_hosts"] == ["esim.modelmarket.dev"]
    assert body["capability"]["price_per_call_usd"] == 0
