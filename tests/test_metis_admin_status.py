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
    # An operator DID point us at a Metis; it just did not answer. Without this the
    # case under test would be "nobody configured a URL", which is a different fault.
    monkeypatch.setenv("AIFACTORY_METIS_URL", "https://metis.example.invalid")
    monkeypatch.setattr(ms, "probe_metis_health", lambda **_: (False, {}))
    out = ms.build_metis_admin_status(products={})
    assert out["status"] == "inactive"
    assert out["factory"]["uses_metis"] is False
    assert out["ecosystem"]["state"] == "unreachable"
    assert out["ecosystem"]["configured"] is True
    assert out["factory"]["blocked_reason"] == "metis-unreachable"


def test_unset_url_is_unconfigured_not_undeployed(monkeypatch):
    """The bug this distinction exists for.

    With no URL set, the probe hits the localhost fallback and fails, and the card
    used to render a flat "No" under "Metis deployed" while Metis was live and
    answering at its real address. "Not configured" is a statement about us; "not
    responding" is a statement about Metis. They must not collapse.
    """
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "auto")
    monkeypatch.delenv("AIFACTORY_METIS_URL", raising=False)
    monkeypatch.delenv("METIS_URL", raising=False)
    monkeypatch.setattr(ms, "probe_metis_health", lambda **_: (False, {}))

    out = ms.build_metis_admin_status(products={})

    assert out["status"] == "unconfigured"
    assert out["ecosystem"]["state"] == "unconfigured"
    assert out["ecosystem"]["configured"] is False
    assert out["ecosystem"]["url"] == ms.DEFAULT_METIS_URL
    assert out["ecosystem"]["url_source"] == "default"
    assert out["factory"]["blocked_reason"] == "metis-unconfigured"
    # The operator must be told what to set, not left to guess.
    assert "AIFACTORY_METIS_URL" in out["ecosystem"]["url_env_vars"]


def test_legacy_metis_url_var_counts_as_configured(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "auto")
    monkeypatch.delenv("AIFACTORY_METIS_URL", raising=False)
    monkeypatch.setenv("METIS_URL", "https://metis.example.invalid/")
    monkeypatch.setattr(ms, "probe_metis_health", lambda **_: (False, {}))
    out = ms.build_metis_admin_status(products={})
    assert out["ecosystem"]["url_source"] == "METIS_URL"
    assert out["ecosystem"]["url"] == "https://metis.example.invalid"  # trailing slash trimmed
    assert out["ecosystem"]["state"] == "unreachable"


def test_gate_off_is_reported_as_the_reason(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "off")
    monkeypatch.setenv("AIFACTORY_METIS_URL", "https://metis.example.invalid")
    monkeypatch.setattr(ms, "probe_metis_health", lambda **_: (True, {"status": "ok"}))
    out = ms.build_metis_admin_status(products={})
    assert out["ecosystem"]["state"] == "deployed"
    assert out["factory"]["uses_metis"] is False
    # Metis is up and configured — the factory is not using it because the gate is off.
    assert out["factory"]["blocked_reason"] == "gate-disabled"
    assert out["status"] == "inactive"


def test_deployed_and_used_has_no_reason(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "auto")
    monkeypatch.setenv("AIFACTORY_METIS_URL", "https://metis.example.invalid")
    monkeypatch.setattr(ms, "probe_metis_health", lambda **_: (True, {"status": "ok"}))
    out = ms.build_metis_admin_status(products={})
    assert out["status"] == "active"
    assert out["ecosystem"]["state"] == "deployed"
    assert out["factory"]["blocked_reason"] is None


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
