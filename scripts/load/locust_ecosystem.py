"""Ecosystem load test — Factory, Hub, Mesh, ARGUS, Monitor, Pulse.

Excludes lottery, Platon, and oracle-family (deployed on separate hosts).

Run (from repo root)::

    pip install -r scripts/load/requirements.txt
    ./scripts/load/run_load_smoke.sh

Interactive UI::

    locust -f scripts/load/locust_ecosystem.py

Optional env:
  LOAD_USERS, LOAD_SPAWN_RATE, LOAD_DURATION — smoke runner defaults
  ARGUS_LOAD_ASK=1 — include POST /ask (needs ARGUS_HTTP_TOKEN; heavy)
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

from common import bearer_header, load_env, service_url

load_env()

_ARGUS_TOKEN = (os.environ.get("ARGUS_HTTP_TOKEN") or "").strip()
_ARGUS_ASK = os.environ.get("ARGUS_LOAD_ASK", "").strip().lower() in ("1", "true", "yes")
_MESH_TASKS = os.environ.get("LOAD_MESH_TASKS", "").strip().lower() in ("1", "true", "yes")


def _accept_rate_limit(response) -> None:
    """429 = mesh rate limiter engaged — valid under load, not a hard failure."""
    if response.status_code == 429:
        response.success()


class FactoryUser(HttpUser):
    """AI Factory API — health, trust metrics, product catalog."""

    host = service_url("FACTORY_URL", "http://127.0.0.1:9081")
    weight = 2
    wait_time = between(1.0, 3.0)

    @task(6)
    def health(self) -> None:
        self.client.get("/api/health", name="factory /api/health")

    @task(3)
    def trust_metrics(self) -> None:
        self.client.get("/api/marketing/trust-metrics", name="factory trust-metrics")

    @task(1)
    def products(self) -> None:
        # Slow on host port — long timeout; still measures catalog pressure.
        with self.client.get(
            "/api/products",
            name="factory /api/products",
            timeout=120,
            catch_response=True,
        ) as resp:
            if resp.status_code == 0:
                resp.failure("timeout")
            elif resp.status_code >= 500:
                resp.failure(f"HTTP {resp.status_code}")


class FrontendUser(HttpUser):
    """Factory static frontend shell."""

    host = service_url("FRONTEND_URL", "http://127.0.0.1:9080")
    weight = 2
    wait_time = between(0.5, 2.0)

    @task(1)
    def home(self) -> None:
        self.client.get("/", name="frontend /")


class HubUser(HttpUser):
    """AIMarket Hub — discovery, stats, search (read-heavy; no paid invoke)."""

    host = service_url("HUB_URL", "http://127.0.0.1:9083")
    weight = 5
    wait_time = between(0.3, 1.2)

    @task(5)
    def stats_live(self) -> None:
        self.client.get("/ai-market/v2/stats/live?limit=10", name="hub stats/live")

    @task(4)
    def search(self) -> None:
        self.client.get(
            "/ai-market/v2/search?intent=translate&budget=2&limit=5",
            name="hub search",
        )

    @task(3)
    def well_known(self) -> None:
        self.client.get("/.well-known/ai-market.json", name="hub well-known")

    @task(2)
    def capital_pricing(self) -> None:
        self.client.get("/api/v2/capital/pricing?limit=5", name="hub capital/pricing")

    @task(1)
    def health(self) -> None:
        self.client.get("/ai-market/v2/health", name="hub /health")


class MeshUser(HttpUser):
    """AI Service Mesh — dashboard reads + optional task enqueue."""

    host = service_url("MESH_URL", "http://127.0.0.1:8090")
    weight = 3
    wait_time = between(0.8, 2.5)

    def on_start(self) -> None:
        self.client.headers.update(bearer_header("MESH_API_TOKEN"))

    @task(5)
    def stats(self) -> None:
        with self.client.get(
            "/v1/stats",
            name="mesh /v1/stats",
            catch_response=True,
        ) as resp:
            _accept_rate_limit(resp)

    @task(3)
    def activity(self) -> None:
        with self.client.get(
            "/v1/activity?limit=30",
            name="mesh activity",
            catch_response=True,
        ) as resp:
            _accept_rate_limit(resp)

    @task(2)
    def agents(self) -> None:
        with self.client.get(
            "/v1/agents?verified_only=true",
            name="mesh agents",
            catch_response=True,
        ) as resp:
            _accept_rate_limit(resp)

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="mesh /health")

    @task(1)
    def create_task(self) -> None:
        if not _MESH_TASKS or not os.environ.get("MESH_API_TOKEN"):
            return
        with self.client.post(
            "/v1/tasks",
            json={
                "intent": "ecosystem load test orchestration",
                "budget_usd": 1.0,
                "preferred_capabilities": ["research"],
            },
            name="mesh POST /v1/tasks",
            catch_response=True,
        ) as resp:
            _accept_rate_limit(resp)


class ArgusUser(HttpUser):
    """ARGUS HTTP channel — public health + arena; /ask only when opted in."""

    host = service_url("ARGUS_URL", "http://127.0.0.1:8787")
    weight = 3
    wait_time = between(0.5, 2.0)

    @task(6)
    def health(self) -> None:
        self.client.get("/health", name="argus /health")

    @task(2)
    def arena_stats(self) -> None:
        self.client.get("/arena/stats", name="argus /arena/stats")

    @task(1)
    def ask_ping(self) -> None:
        if not _ARGUS_ASK or not _ARGUS_TOKEN:
            return
        self.client.post(
            "/ask",
            json={"task": "Reply with exactly the word: pong"},
            headers={"Authorization": f"Bearer {_ARGUS_TOKEN}"},
            name="argus POST /ask",
            timeout=180,
        )


class MonitorUser(HttpUser):
    """Alien Monitor — health + state graph (Bearer when ALIEN_API_TOKEN set)."""

    host = service_url("MONITOR_URL", "http://127.0.0.1:9100")
    weight = 3
    wait_time = between(0.5, 2.5)

    def on_start(self) -> None:
        self.client.headers.update(bearer_header("ALIEN_API_TOKEN"))

    @task(4)
    def api_health(self) -> None:
        self.client.get("/api/health", name="monitor /api/health")

    @task(3)
    def prefixed_health(self) -> None:
        self.client.get("/monitor/api/health", name="monitor /monitor/api/health")

    @task(2)
    def state(self) -> None:
        self.client.get(
            "/monitor/api/state",
            name="monitor /monitor/api/state",
            timeout=90,
        )


class PulseUser(HttpUser):
    """Pulse Terminal — static shell under /pulse/."""

    host = service_url("PULSE_URL", "http://127.0.0.1:5199")
    weight = 2
    wait_time = between(0.6, 2.0)

    @task(3)
    def pulse_shell(self) -> None:
        self.client.get("/pulse/", name="pulse /pulse/")

    @task(1)
    def root(self) -> None:
        self.client.get("/", name="pulse /")
