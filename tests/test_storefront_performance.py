"""The storefront and trust-strip optimizations after the 2026-10-23 load test.

GET /api/products took 3-7 s for 24 products (each product's demo report computed three
times, each walking node_modules), trust-metrics 4 s (every task the factory ever ran loaded
to count product states), and the pipeline worker spent ~90% of a core re-parsing YAML.
These pin what the fixes must keep true: the same answers, computed less often.
"""
from __future__ import annotations

import time

import pytest


def test_the_watermark_walk_skips_vendor_trees_but_reads_built_output(tmp_path):
    from core.public_site_url import _product_html_files

    for rel in ("index.html", "frontend/dist/index.html", "node_modules/pkg/docs/readme.html",
                ".aicom_sandbox/run/page.html", ".venv/lib/x.html", "pages/about.html", "notes.HTML"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("<html></html>", encoding="utf-8")
    found = [p.relative_to(tmp_path).as_posix() for p in _product_html_files(tmp_path)]
    assert found == ["frontend/dist/index.html", "index.html", "pages/about.html"]


def test_one_storefront_request_assesses_each_product_once(monkeypatch):
    from web.backend.services import demo_quality

    calls: list[str] = []
    monkeypatch.setattr(demo_quality, "_assess_product_demo",
                        lambda pid, spec=None, data_root=None: calls.append(pid) or {"score": 90, "issues": []})
    with demo_quality.assessment_memo():
        for _ in range(3):
            report = demo_quality.assess_product_demo("prod-a")
            report["issues"].append("a caller's own edit")
        demo_quality.assess_product_demo("prod-a", {"delivery_profile": "web"})
        demo_quality.assess_product_demo("prod-b")
    assert calls == ["prod-a", "prod-a", "prod-b"]        # spec is part of the key
    assert demo_quality.assess_product_demo("prod-a")["issues"] == []   # copies, and no memo outside
    assert calls[-1] == "prod-a" and len(calls) == 4


def test_the_storefront_grid_is_reused_until_the_catalogue_moves(monkeypatch):
    from web.backend.api import products
    from web.backend.schemas.products import ProductListQuery

    builds: list[int] = []
    stamp = ["v1"]
    monkeypatch.setattr(products, "_list_products_sync",
                        lambda q: builds.append(1) or {"products": [{"id": "p"}], "count": 1, "category": q.category})
    monkeypatch.setattr(products, "_catalog_stamp", lambda: stamp[0])
    monkeypatch.setenv("AIFACTORY_STOREFRONT_LIST_TTL_S", "30")
    products._LIST_CACHE.clear()
    q = ProductListQuery()
    first = products._list_products_cached(q)
    first["products"].append({"id": "mutated"})
    assert products._list_products_cached(q) == {"products": [{"id": "p"}], "count": 1, "category": None}
    assert len(builds) == 1
    stamp[0] = "v2"                                   # the pipeline wrote its state
    products._list_products_cached(q)
    assert len(builds) == 2
    monkeypatch.setenv("AIFACTORY_STOREFRONT_LIST_TTL_S", "0")
    products._list_products_cached(q)
    products._list_products_cached(q)
    assert len(builds) == 4                           # TTL 0 turns the cache off


def test_reading_products_never_loads_the_task_queue(monkeypatch):
    from core import pipeline_state_writer as writer

    class Store:
        tasks_loaded = 0

        def get_all_products(self):
            return [{"id": "prod-1", "state": "COMPLETED"}, {"id": "", "state": "x"}]

        def get_all_tasks(self):
            Store.tasks_loaded += 1
            return []

        def close(self):
            pass

    monkeypatch.setattr(writer, "pipeline_uses_sql_store", lambda: True)
    monkeypatch.setattr(writer, "create_sync_pipeline_manager", Store)
    assert writer.read_pipeline_products() == {"prod-1": {"id": "prod-1", "state": "COMPLETED"}}
    assert Store.tasks_loaded == 0


def test_the_trust_strip_is_built_once_a_minute(monkeypatch):
    from web.backend.services import funnel_analytics as fa

    builds: list[int] = []
    monkeypatch.setattr(fa, "_build_public_trust_metrics", lambda: builds.append(1) or {"products_shipped": 6})
    monkeypatch.setattr(fa, "_TRUST_CACHE", None)
    for _ in range(5):
        assert fa.public_trust_metrics() == {"products_shipped": 6}
    assert len(builds) == 1
    monkeypatch.setattr(fa, "_TRUST_CACHE", (time.monotonic() - 61, {"products_shipped": 6}))
    fa.public_trust_metrics()
    assert len(builds) == 2


@pytest.mark.parametrize("state, completed, in_progress", [
    ({"a": {"state": "COMPLETED"}, "b": {"state": "deployed_production"}, "c": {"state": "DEV_FIXING"},
      "d": {"state": "FAILED"}, "e": {"state": "CANCELLED"}}, 2, 1),
])
def test_pipeline_counts_from_products_only(monkeypatch, state, completed, in_progress):
    from core import pipeline_state_writer as writer
    from web.backend.services import funnel_analytics as fa

    monkeypatch.setattr(writer, "read_pipeline_products", lambda json_path=None: state)
    counts = fa._pipeline_counts()
    assert counts == {"completed": completed, "in_progress": in_progress, "failed": 1, "total": 5}
