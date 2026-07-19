"""Admin Metis status snapshot."""

from __future__ import annotations

import json

from web.backend.services import metis_status as ms


def test_build_metis_admin_status_active(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "on")
    monkeypatch.setattr(
        ms,
        "probe_metis_health",
        lambda **_: (True, {"status": "ok", "version": "0.2.0", "knowledge_entries": 3}),
    )
    products = {
        "p1": {"metis_gate": {"at": 1.0, "ok": True, "verify_score": 0.9}},
        "p2": {"metis_gate": {"at": 2.0, "ok": False, "verify_score": 0.2}},
        "p3": {},
    }
    out = ms.build_metis_admin_status(products=products)
    assert out["status"] == "active"
    assert out["ecosystem"]["deployed"] is True
    assert out["factory"]["uses_metis"] is True
    assert out["usage"]["checked"] == 2
    assert out["usage"]["approved"] == 1
    assert out["usage"]["flagged"] == 1
    assert out["usage"]["pending"] == 1
    assert out["usage"]["avg_verify_score"] == 0.55


def test_build_metis_admin_status_inactive_when_metis_down(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "auto")
    monkeypatch.setattr(ms, "probe_metis_health", lambda **_: (False, {}))
    out = ms.build_metis_admin_status(products={})
    assert out["status"] == "inactive"
    assert out["factory"]["uses_metis"] is False


def test_probe_metis_health_parses_body(monkeypatch):
    payload = {"status": "ok", "version": "1.0"}

    class Resp:
        status = 200

        def getcode(self):
            return 200

        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ms.urllib.request, "urlopen", lambda *a, **k: Resp())
    ok, body = ms.probe_metis_health()
    assert ok is True
    assert body["version"] == "1.0"
