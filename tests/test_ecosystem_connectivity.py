"""Ecosystem component connectivity — offline contracts + live stack probes.

Live probes hit the production-local fleet (Factory, Hub, Mesh, ARGUS, Monitor,
Pulse, Lottery relayer). Enable with::

    ECOSYSTEM_INTEGRATION=1 pytest tests/test_ecosystem_connectivity.py -v

Contract tests in this module always run in CI — they pin cross-service schemas
and metric-key contracts so producer/consumer drift fails before deploy.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]

# Load fleet tokens/URLs the same way verify_ecosystem_full.sh does.
_ENV_FILE = os.environ.get("ENV_FILE", str(ROOT / ".env"))
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            if _k and _k not in os.environ:
                os.environ[_k] = _v.strip().strip('"').strip("'")

RUN_LIVE = os.environ.get("ECOSYSTEM_INTEGRATION", "").strip().lower() in ("1", "true", "yes")

pytestmark = pytest.mark.integration


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or default).rstrip("/")


@pytest.fixture(scope="module")
def eco() -> dict[str, str]:
    return {
        "factory": _env("FACTORY_URL", "http://127.0.0.1:9081"),
        "frontend": _env("FRONTEND_URL", "http://127.0.0.1:9080"),
        "hub": _env("HUB_URL", "http://127.0.0.1:9083"),
        "mesh": _env("MESH_URL", "http://127.0.0.1:8090"),
        "argus": _env("ARGUS_URL", "http://127.0.0.1:8787"),
        "argus_uni": _env("ARGUS_UNI_URL", "http://127.0.0.1:8788"),
        "monitor": _env("MONITOR_URL", "http://127.0.0.1:9100"),
        "pulse": _env("PULSE_URL", "http://127.0.0.1:5199"),
        "lottery": _env("LOTTERY_RELAYER_URL", "http://127.0.0.1:9195"),
        "skopos": _env("SKOPOS_URL", "http://127.0.0.1:8502"),
        "skopos_public": _env("SKOPOS_PUBLIC_URL", "https://skopos.modelmarket.dev"),
    }


def _mesh_headers() -> dict[str, str]:
    token = (os.environ.get("MESH_API_TOKEN") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _monitor_headers() -> dict[str, str]:
    token = (os.environ.get("ALIEN_API_TOKEN") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _get_json(client: httpx.Client, url: str, **kwargs: Any) -> dict[str, Any]:
    r = client.get(url, **kwargs)
    r.raise_for_status()
    data = r.json()
    assert isinstance(data, dict), data
    return data


def _get_json_retry(client: httpx.Client, url: str, attempts: int = 3, pause: float = 5.0, **kwargs: Any) -> dict[str, Any]:
    last: Exception | None = None
    for n in range(attempts):
        try:
            return _get_json(client, url, **kwargs)
        except Exception as exc:
            last = exc
            if n + 1 < attempts:
                time.sleep(pause)
    raise last  # type: ignore[misc]


def _skopos_path() -> None:
    p = str(ROOT / "skopos")
    if p not in sys.path:
        sys.path.insert(0, p)


def _monitor_backend_path() -> None:
    p = str(ROOT / "alien-monitor" / "backend")
    if p not in sys.path:
        sys.path.insert(0, p)


def _factory_get(client: httpx.Client, path: str, eco: dict[str, str]) -> dict[str, Any]:
    """Factory API from host, with docker-internal fallback (matches verify script)."""
    url = f"{eco['factory']}{path}"
    try:
        return _get_json_retry(client, url, attempts=2, pause=3.0)
    except Exception:
        import subprocess

        proc = subprocess.run(
            ["docker", "exec", "aicom-app-1", "curl", "-sf", "--max-time", "120", f"http://127.0.0.1:8081{path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"factory {path} unreachable via host and container")
        data = json.loads(proc.stdout)
        assert isinstance(data, dict), data
        return data


# ── Offline contracts (always run) ───────────────────────────────────────────


def test_lottery_relayer_monitor_metric_key_contract():
    """Relayer PUSH keys must match Monitor CONSUME keys (live feed contract)."""
    relayer_root = ROOT / "lottery" / "relayer"
    monitor_backend = ROOT / "alien-monitor" / "backend"
    sys.path.insert(0, str(relayer_root))
    sys.path.insert(0, str(monitor_backend))
    from ailottery_relayer.monitor import MONITOR_METRIC_KEYS  # noqa: E402
    from live_lottery_feed import _LIVE_METRIC_KEYS  # noqa: E402

    assert tuple(MONITOR_METRIC_KEYS) == tuple(_LIVE_METRIC_KEYS)


def test_argus_health_vs_status_schema_contract():
    """Document the split: /health is public; wallet lives on authenticated /status."""
    public_keys = {"status", "agent", "version", "model", "economy", "mode", "uptimeSec"}
    sensitive_keys = {"wallet", "chain", "chainNetwork", "chainId", "walletExplorer"}
    assert not public_keys & sensitive_keys
    # Monitor merges /status wallet fields when ALIEN_ARGUS_HTTP_TOKEN is configured.
    assert "wallet" in sensitive_keys


def test_monitor_argus_status_merge_contract():
    """Monitor must overlay wallet from /status without exposing it on public /health."""
    _monitor_backend_path()
    from argus_status import merge_argus_runtime  # noqa: E402

    health = {"status": "ok", "economy": "on", "model": "deepseek/deepseek-chat", "uptimeSec": 10}
    status = {
        "status": "ok",
        "wallet": "0x3520b679c998EE01B0d5EB0458CB9abf4e7Bb9e7",
        "chainNetwork": "Base",
        "chainId": 8453,
    }
    merged = merge_argus_runtime(health, status)
    assert "wallet" not in health
    assert merged["wallet"] == status["wallet"]
    assert merged["model"] == health["model"]


def test_skopos_healthz_producer_consumer_contract():
    """SKOPOS /healthz keys must match Alien Monitor skopos_status consumer."""
    _skopos_path()
    from skopos.public_status import build_status  # noqa: E402

    monitor_consumed = frozenset(
        {
            "ok",
            "servers_monitored",
            "requests_total",
            "database",
            "log_parsers",
            "version",
        }
    )
    status = build_status(config_path=str(ROOT / "skopos" / "nonexistent.yaml"))
    assert status.get("ok") is True
    assert status.get("service") == "skopos"
    for key in monitor_consumed:
        assert key in status, key
    # security_score is optional until the first security snapshot exists


def test_skopos_capabilities_handlers_manifest_contract():
    """Every billable capability must have a handler and appear in v2 manifest."""
    _skopos_path()
    from skopos.economy.capabilities import CAPABILITY_BY_ID  # noqa: E402
    from skopos.economy.config import EconomyConfig  # noqa: E402
    from skopos.economy.handlers import HANDLERS  # noqa: E402
    from skopos.economy.manifest import build_prices, build_supply_manifest, build_v2_manifest  # noqa: E402

    assert set(HANDLERS) == set(CAPABILITY_BY_ID)
    cfg = EconomyConfig(
        enabled=True,
        public_base_url="https://skopos.test",
        product_id="prod-skopos",
        publisher_id="skopos-fleet",
        invoke_path="/aimarket/invoke",
        api_key=None,
        hub_url=None,
        auto_register=False,
        publish_token=None,
        agent_yaml_path="./agent.yaml",
        config_path="./servers.yaml",
    )
    manifest = build_v2_manifest(cfg)
    manifest_ids = {tool["capability_id"] for tool in manifest["tools"]}
    assert manifest_ids == set(CAPABILITY_BY_ID)
    assert manifest["capabilities_count"] == len(CAPABILITY_BY_ID)
    supply = build_supply_manifest(cfg)
    assert {item["capability_id"] for item in supply} == set(CAPABILITY_BY_ID)
    prices = build_prices(cfg)
    assert prices["count"] == len(CAPABILITY_BY_ID)


def test_skopos_ecosystem_segment_contract():
    """Traffic segment tags must classify hub/factory/oracle/monitor paths."""
    _skopos_path()
    from skopos.ecosystem import ecosystem_segment  # noqa: E402

    assert ecosystem_segment("/.well-known/ai-market.json") == "hub-federation"
    assert ecosystem_segment("/api/products") == "api"
    assert ecosystem_segment("/platon") == "oracles"
    assert ecosystem_segment("/monitor/api/state") == "monitor"
    assert ecosystem_segment("/lottery/round") == "lottery"
    assert ecosystem_segment("/x", host="magic-ai-factory.com") == "factory"
    assert ecosystem_segment("/x", host="metis.modelmarket.dev") == "metis"


def test_monitor_skopos_topology_contract():
    """Monitor graph must include SKOPOS node wired to factory, metis, and hub."""
    _monitor_backend_path()
    from skopos_layers import skopos_node_spec, skopos_topology_links  # noqa: E402
    from skopos_status import apply_skopos_to_nodes  # noqa: E402

    spec = skopos_node_spec()
    assert spec["id"] == "skopos"
    assert spec["group"] == "observability"
    links = {(link["source"], link["target"]) for link in skopos_topology_links()}
    assert ("factory", "skopos") in links
    assert ("skopos", "metis") in links
    assert ("skopos", "hub") in links

    nodes = [dict(spec)]
    apply_skopos_to_nodes(
        nodes,
        {
            "ok": True,
            "servers_monitored": 2,
            "requests_total": 100,
            "security_score": 72,
            "database": "postgresql",
            "log_parsers": ["nginx"],
            "version": "0.1.0",
        },
    )
    assert nodes[0]["status"] == "active"
    live = nodes[0]["skopos_live"]
    assert live["servers_monitored"] == 2
    assert live["requests_total"] == 100
    assert live["security_score"] == 72


def test_skopos_agent_portal_fab_overlay_contract():
    """Floating agent FAB must portal overlay to document.body (factory-style)."""
    _skopos_path()
    from skopos.agent_portal import _portal_script  # noqa: E402

    script = _portal_script()
    assert "skopos-agent-fab-overlay" in script
    assert "findChatButton" in script
    assert "doc.body.appendChild" in script


# ── Live probes (ECOSYSTEM_INTEGRATION=1) ──────────────────────────────────


@pytest.fixture(scope="module")
def live_client() -> httpx.Client:
    if not RUN_LIVE:
        pytest.skip("set ECOSYSTEM_INTEGRATION=1 for live ecosystem probes")
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        yield client


class TestFactoryBlock:
    def test_health_and_products(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json_retry(live_client, f"{eco['factory']}/api/health")
        assert health.get("status") in ("ok", "healthy", "up")
        products = _factory_get(live_client, "/api/products", eco)
        assert "products" in products

    def test_frontend_reachable(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        r = live_client.get(f"{eco['frontend']}/")
        r.raise_for_status()


class TestHubBlock:
    def test_well_known_and_stats(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        wk = _get_json(live_client, f"{eco['hub']}/.well-known/ai-market.json")
        assert wk.get("hub_url") or wk.get("name")
        assert "signer_public_key" in wk or "public_key" in wk
        stats = _get_json(live_client, f"{eco['hub']}/ai-market/v2/stats/live?limit=3")
        assert "summary" in stats

    def test_capital_pricing(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        pricing = _get_json(live_client, f"{eco['hub']}/api/v2/capital/pricing?limit=1")
        assert isinstance(pricing, dict)


class TestMeshBlock:
    def test_stats_endpoint(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        stats = _get_json(live_client, f"{eco['mesh']}/v1/stats", headers=_mesh_headers())
        assert isinstance(stats, dict)


class TestArgusBlock:
    def test_health_public_no_wallet(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json(live_client, f"{eco['argus']}/health")
        assert health.get("status") == "ok"
        assert health.get("agent") == "argus"
        assert "wallet" not in health
        assert "chainId" not in health

    def test_status_requires_token(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        r = live_client.get(f"{eco['argus']}/status")
        assert r.status_code in (401, 403)

    def test_uni_health(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json(live_client, f"{eco['argus_uni']}/health")
        assert health.get("status") == "ok"
        assert health.get("mode") == "uni"


class TestMonitorBlock:
    def test_universe_health_and_state(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json(live_client, f"{eco['monitor']}/api/health")
        assert health.get("status") == "ok"
        assert health.get("mode") == "universe"
        assert health.get("blockchain_ready") is True
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        nodes = state.get("nodes") or []
        assert len(nodes) > 0

    def test_argus_node_linked(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        nodes = state.get("nodes") or []
        argus = next((n for n in nodes if n.get("id") == "argus"), None)
        assert argus is not None, [n.get("id") for n in nodes[:20]]
        assert argus.get("group") == "argus"
        links = state.get("links") or []
        assert any(l.get("source") == "argus" for l in links)
        # argus_run appears only after Argus pushes a completed run (not the TEST demo).
        if argus.get("argus_run"):
            assert (argus["argus_run"].get("beats") or []) != []

    def test_oracle_family_present(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        family = [
            n for n in (state.get("nodes") or [])
            if str(n.get("id", "")).startswith("oracle-")
            and not str(n.get("id", "")).startswith("oracle-cave")
        ]
        expected = {
            "oracle-platon", "oracle-chronos", "oracle-lattice", "oracle-murmuration",
            "oracle-lumen", "oracle-colony", "oracle-turing", "oracle-ablation",
            "oracle-fermat", "oracle-landauer", "oracle-percola",
        }
        ids = {n.get("id") for n in family}
        assert expected <= ids, sorted(expected - ids)


class TestLotteryBlock:
    def test_relayer_healthz(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        r = live_client.get(f"{eco['lottery']}/healthz")
        r.raise_for_status()

    def test_monitor_lottery_metrics(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        lot = next((n for n in (state.get("nodes") or []) if n.get("id") == "lottery"), None)
        assert lot is not None
        metrics = lot.get("metrics") or {}
        assert int(metrics.get("round") or 0) > 0


class TestPulseBlock:
    def test_shell_and_assets(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        r = live_client.get(f"{eco['pulse']}/pulse/")
        r.raise_for_status()
        assert "/assets/" in r.text or "assets/" in r.text


class TestSkoposBlock:
    def test_healthz(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json_retry(live_client, f"{eco['skopos']}/healthz")
        assert health.get("ok") is True
        assert health.get("service") == "skopos"
        assert "servers_monitored" in health
        assert "requests_total" in health
        assert "economy_enabled" in health

    def test_economy_manifest_when_enabled(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json(live_client, f"{eco['skopos']}/healthz")
        if not health.get("economy_enabled"):
            pytest.skip("SKOPOS AIMarket economy disabled on target")
        wk = _get_json(live_client, f"{eco['skopos']}/.well-known/ai-market.json")
        assert wk.get("service") == "skopos"
        assert "v2" in (wk.get("protocol_versions") or [])
        manifest = _get_json(live_client, f"{eco['skopos']}/ai-market/v2/manifest")
        tools = manifest.get("tools") or []
        assert len(tools) >= 4
        cap_ids = {tool.get("capability_id") for tool in tools}
        assert "skopos.fleet.status@v1" in cap_ids
        assert "skopos.security.posture@v1" in cap_ids

    def test_invoke_fleet_status_when_key_configured(
        self, live_client: httpx.Client, eco: dict[str, str]
    ) -> None:
        health = _get_json(live_client, f"{eco['skopos']}/healthz")
        if not health.get("economy_enabled"):
            pytest.skip("SKOPOS AIMarket economy disabled on target")
        api_key = (os.environ.get("SKOPOS_AIMARKET_API_KEY") or "").strip()
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        r = live_client.post(
            f"{eco['skopos']}/aimarket/invoke",
            json={"capability_id": "skopos.fleet.status@v1", "input": {}},
            headers=headers,
        )
        if r.status_code == 401 and not api_key:
            pytest.skip("SKOPOS invoke requires SKOPOS_AIMARKET_API_KEY")
        r.raise_for_status()
        payload = r.json()
        assert payload.get("capability_id") == "skopos.fleet.status@v1"
        assert payload.get("provider") == "skopos"
        assert isinstance(payload.get("result"), dict)


class TestCrossBlockConnectivity:
    """Cross-component edges — the wiring between blocks."""

    def test_factory_trust_metrics_reachable(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        r = live_client.get(f"{eco['factory']}/api/marketing/trust-metrics")
        if r.status_code >= 500:
            r = live_client.get(f"{eco['factory']}/api/marketing/trust-metrics")
        r.raise_for_status()

    def test_well_known_has_chain_context(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        wk = _get_json(live_client, f"{eco['hub']}/.well-known/ai-market.json")
        assert wk.get("chain") or wk.get("chains") or wk.get("hub_url") or wk.get("name")

    def test_monitor_sees_live_argus_from_health_poll(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        argus_health = _get_json(live_client, f"{eco['argus']}/health")
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        argus = next((n for n in (state.get("nodes") or []) if n.get("id") == "argus"), None)
        assert argus is not None
        live = argus.get("argus_live") or {}
        if argus_health.get("status") == "ok":
            assert argus.get("status") == "active"
            assert live.get("model") == argus_health.get("model")

    def test_monitor_evm_lottery_contract_in_health(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        health = _get_json(live_client, f"{eco['monitor']}/api/health")
        contracts = health.get("contracts") or {}
        assert contracts.get("evm_lottery")

    def test_monitor_sees_skopos_node(self, live_client: httpx.Client, eco: dict[str, str]) -> None:
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        nodes = state.get("nodes") or []
        skopos = next((n for n in nodes if n.get("id") == "skopos"), None)
        assert skopos is not None, [n.get("id") for n in nodes[:25]]
        assert skopos.get("group") == "observability"
        links = state.get("links") or []
        assert any(l.get("source") == "factory" and l.get("target") == "skopos" for l in links)
        assert any(l.get("source") == "skopos" and l.get("target") == "metis" for l in links)

    def test_skopos_healthz_matches_monitor_skopos_live(
        self, live_client: httpx.Client, eco: dict[str, str]
    ) -> None:
        health = _get_json_retry(live_client, f"{eco['skopos']}/healthz")
        state = _get_json(live_client, f"{eco['monitor']}/monitor/api/state", headers=_monitor_headers())
        skopos = next((n for n in (state.get("nodes") or []) if n.get("id") == "skopos"), None)
        assert skopos is not None
        if not health.get("ok"):
            assert skopos.get("status") in ("offline", "error", "idle")
            return
        live = skopos.get("skopos_live") or {}
        if health.get("servers_monitored", 0) > 0 or health.get("requests_total", 0) > 0:
            assert skopos.get("status") == "active"
        assert live.get("servers_monitored") == health.get("servers_monitored")
        assert live.get("requests_total") == health.get("requests_total")
        if health.get("security_score") is not None:
            assert live.get("security_score") == health.get("security_score")
