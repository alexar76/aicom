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
import random

from locust import HttpUser, LoadTestShape, between, task

from common import bearer_header, load_env, service_url

load_env()

_ARGUS_TOKEN = (os.environ.get("ARGUS_HTTP_TOKEN") or "").strip()
_ARGUS_ASK = os.environ.get("ARGUS_LOAD_ASK", "").strip().lower() in ("1", "true", "yes")
_ARGUS_HEALTH = (os.environ.get("ARGUS_HEALTH_PATH") or "/health").strip() or "/health"
_MESH_TASKS = os.environ.get("LOAD_MESH_TASKS", "").strip().lower() in ("1", "true", "yes")
_SKIP_PULSE = os.environ.get("LOAD_SKIP_PULSE", "").strip().lower() in ("1", "true", "yes")
_PULSE_SHELL = os.environ.get("PULSE_SHELL_PATH") or "/pulse/"
if not _PULSE_SHELL.startswith("/"):
    _PULSE_SHELL = "/" + _PULSE_SHELL
if not _PULSE_SHELL.endswith("/"):
    _PULSE_SHELL += "/"
_ALIEN_TOKEN = (os.environ.get("ALIEN_API_TOKEN") or "").strip()
_METIS_VERIFY = os.environ.get("LOAD_METIS_VERIFY", "").strip().lower() in ("1", "true", "yes")
_HUB_INVOKE = os.environ.get("LOAD_HUB_INVOKE", "").strip().lower() in ("1", "true", "yes")
_HUB_AGENT_KEY = (
    os.environ.get("AIMARKET_AGENT_KEY")
    or os.environ.get("X_AGENT_KEY")
    or os.environ.get("HUB_API_TOKEN")
    or ""
).strip()
_HUB_VISITOR = (os.environ.get("AIMARKET_SANDBOX_VISITOR") or "").strip()
_PIPELINE_CREATE = os.environ.get("LOAD_PIPELINE_CREATE", "").strip().lower() in ("1", "true", "yes")
_ARGUS_ASK_PATH = (os.environ.get("ARGUS_ASK_PATH") or "/ask").strip() or "/ask"
_MODE = os.environ.get("LOAD_MODE", "smoke").strip().lower()
_SCOPE = os.environ.get("LOAD_SCOPE", "core").strip().lower()
_WANT_CORE = _MODE != "heavy"
_WANT_FLEET = _SCOPE in ("full", "fleet") or _MODE == "full"
_WANT_HEAVY = _MODE == "heavy" or os.environ.get("LOAD_HEAVY", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _accept_rate_limit(response) -> None:
    """429 = mesh rate limiter engaged — valid under load, not a hard failure."""
    if response.status_code == 429:
        response.success()


class FactoryUser(HttpUser):
    """AI Factory API — health, trust metrics, product catalog."""

    abstract = not _WANT_CORE

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

    abstract = not _WANT_CORE

    host = service_url("FRONTEND_URL", "http://127.0.0.1:9080")
    weight = 2
    wait_time = between(0.5, 2.0)

    @task(1)
    def home(self) -> None:
        self.client.get("/", name="frontend /")


class HubUser(HttpUser):
    """AIMarket Hub — discovery, stats, search (read-heavy; no paid invoke)."""

    abstract = not _WANT_CORE

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

    abstract = not _WANT_CORE

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

    abstract = not _WANT_CORE

    host = service_url("ARGUS_URL", "http://127.0.0.1:8787")
    weight = 3
    wait_time = between(0.5, 2.0)

    @task(6)
    def health(self) -> None:
        self.client.get(_ARGUS_HEALTH, name="argus health")

    @task(2)
    def arena_stats(self) -> None:
        self.client.get("/arena/stats", name="argus /arena/stats")

    @task(1)
    def ask_ping(self) -> None:
        if not _ARGUS_ASK or not _ARGUS_TOKEN:
            return
        self.client.post(
            _ARGUS_ASK_PATH,
            json={"task": "Reply with exactly the word: pong"},
            headers={"Authorization": f"Bearer {_ARGUS_TOKEN}"},
            name="argus POST /ask",
            timeout=180,
        )


class MonitorUser(HttpUser):
    """Alien Monitor — health + state graph (Bearer when ALIEN_API_TOKEN set)."""

    abstract = not _WANT_CORE

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
        with self.client.get(
            "/monitor/api/state",
            name="monitor /monitor/api/state",
            timeout=90,
            catch_response=True,
        ) as resp:
            if resp.status_code == 401 and not _ALIEN_TOKEN:
                resp.success()


class PulseUser(HttpUser):
    """Pulse Terminal — static shell under /pulse/."""

    abstract = not _WANT_CORE

    host = service_url("PULSE_URL", "http://127.0.0.1:5199")
    weight = 2
    wait_time = between(0.6, 2.0)

    @task(3)
    def pulse_shell(self) -> None:
        if _SKIP_PULSE:
            return
        self.client.get(_PULSE_SHELL, name="pulse shell")

    @task(1)
    def root(self) -> None:
        if _SKIP_PULSE or _PULSE_SHELL == "/":
            return
        self.client.get("/", name="pulse /")


# Absolute GETs so one Locust class can cover many satellite hosts.
_FLEET_READS = (
    ("METIS_URL", "https://metis.modelmarket.dev", "/health", "metis /health"),
    ("ORACLES_URL", "https://oracles.modelmarket.dev", "/health", "oracles /health"),
    ("ORACLES_URL", "https://oracles.modelmarket.dev", "/platon/umbral/", "platon umbral"),
    ("LOTTERY_URL", "https://lottery.modelmarket.dev", "/", "lottery /"),
    ("GAIA_URL", "https://iot.modelmarket.dev", "/", "gaia /"),
    ("ATLAS_URL", "https://atlas.modelmarket.dev", "/", "atlas /"),
    ("MOMUS_URL", "https://momus.modelmarket.dev", "/health", "momus /health"),
    ("SKOPOS_URL", "https://skopos.modelmarket.dev", "/health", "skopos /health"),
    ("LOGOS_URL", "https://logos.modelmarket.dev", "/", "logos /"),
    ("VERIFY_URL", "https://verify.modelmarket.dev", "/", "verify /"),
    ("FORGE_URL", "https://forge.modelmarket.dev", "/", "forge /"),
    ("THEMIS_URL", "https://themis.modelmarket.dev", "/health", "themis /health"),
    ("FACTORY_URL", "https://magic-ai-factory.com", "/api/public/ecosystem-status", "factory ecosystem-status"),
)


def _fleet_targets() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for env_name, default, path, name in _FLEET_READS:
        out.append((service_url(env_name, default) + path, name))
    return out


class FleetReadUser(HttpUser):
    """Satellites that were out of the core mix: Metis, oracles, GAIA/ATLAS, MOMUS, SKOPOS."""

    abstract = not _WANT_FLEET

    host = service_url("HUB_URL", "https://modelmarket.dev")
    weight = 4
    wait_time = between(0.6, 2.0)

    def on_start(self) -> None:
        self._targets = _fleet_targets()

    @task
    def ping(self) -> None:
        url, name = random.choice(self._targets)
        self.client.get(url, name=name, timeout=30)


class MeshTaskUser(HttpUser):
    """Rare Mesh POST /v1/tasks — real enqueue, keep VU count at 1–2."""

    abstract = not _WANT_HEAVY

    host = service_url("MESH_URL", "http://127.0.0.1:8090")
    weight = 1
    wait_time = between(8.0, 20.0)

    def on_start(self) -> None:
        self.client.headers.update(bearer_header("MESH_API_TOKEN"))

    @task
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
            timeout=30,
        ) as resp:
            _accept_rate_limit(resp)


class MetisVerifyUser(HttpUser):
    """Metis fast-route verify — LLM, same mix as metis/deploy/loadtest.k6.js."""

    abstract = not _WANT_HEAVY

    host = service_url("METIS_URL", "https://metis.modelmarket.dev")
    weight = 1
    wait_time = between(12.0, 25.0)

    @task
    def fast_verify(self) -> None:
        if not _METIS_VERIFY:
            return
        self.client.post(
            "/v1/verify",
            json={"input": "What is 12 * 12? Answer with the number.", "route": "fast"},
            name="metis POST /v1/verify",
            timeout=60,
        )


class ArgusAskUser(HttpUser):
    """ARGUS POST /ask — needs ARGUS_HTTP_TOKEN; skipped if the token is empty."""

    abstract = not _WANT_HEAVY

    host = service_url("ARGUS_URL", "http://127.0.0.1:8787")
    weight = 1
    wait_time = between(8.0, 20.0)

    @task
    def ask_ping(self) -> None:
        if not _ARGUS_ASK or not _ARGUS_TOKEN:
            return
        self.client.post(
            _ARGUS_ASK_PATH,
            json={"task": "Reply with exactly the word: pong"},
            headers={"Authorization": f"Bearer {_ARGUS_TOKEN}"},
            name="argus POST /ask",
            timeout=180,
        )


class HubInvokeUser(HttpUser):
    """Hub invoke on the factory Hub — sandbox visitor or agent key."""

    abstract = not _WANT_HEAVY

    host = service_url("HUB_URL", "http://127.0.0.1:9083")
    weight = 1
    wait_time = between(12.0, 25.0)

    @task
    def invoke(self) -> None:
        if not _HUB_INVOKE:
            return
        headers: dict[str, str] = {}
        if _HUB_VISITOR:
            headers["X-AIMarket-Sandbox-Visitor"] = _HUB_VISITOR
        elif _HUB_AGENT_KEY:
            headers["X-Agent-Key"] = _HUB_AGENT_KEY
        else:
            return
        cap = os.environ.get("LOAD_HUB_CAPABILITY", "gaia.weather.read@v1")
        with self.client.post(
            "/ai-market/v2/invoke",
            json={
                "capability_id": cap,
                "input": {"lat": 51.5074, "lon": -0.1278},
            },
            headers=headers,
            name="hub POST /invoke",
            catch_response=True,
            timeout=60,
        ) as resp:
            # 402 = trial/credit gate fired — still a real invoke path on this host.
            if resp.status_code in (200, 201, 202, 402):
                resp.success()
            elif resp.status_code in (401, 403, 404, 429):
                resp.failure(f"HTTP {resp.status_code}")


class FactoryPipelineUser(HttpUser):
    """Factory protocol pipelines — list always; create only when opted in."""

    abstract = not _WANT_HEAVY

    host = service_url("FACTORY_URL", "http://127.0.0.1:9081")
    weight = 1
    wait_time = between(8.0, 15.0)

    @task(3)
    def list_pipelines(self) -> None:
        self.client.get("/ai-market/pipelines", name="factory GET /ai-market/pipelines", timeout=30)

    @task(1)
    def create_pipeline(self) -> None:
        if not _PIPELINE_CREATE:
            return
        headers = {}
        if _HUB_VISITOR:
            headers["X-AIMarket-Sandbox-Visitor"] = _HUB_VISITOR
        self.client.post(
            "/ai-market/pipelines",
            json={"nodes": [{
                "id": "n1",
                "product_id": "gaia.weather",
                "capability_id": "gaia.weather.read@v1",
                "input": {"lat": 51.5, "lon": -0.1},
            }]},
            headers=headers,
            name="factory POST /ai-market/pipelines",
            timeout=120,
        )


if os.environ.get("LOAD_MODE", "").strip().lower() == "ramp":

    class RampToBreak(LoadTestShape):
        """Step ramp until fail-ratio trips or the user cap is held.

        Defaults match scripts/load/METHODOLOGY.md §3.3. Stop is capacity, not a
        product bug: skip known 5xx with LOAD_SKIP_PULSE=1 if Pulse is down.
        """

        start_users = int(os.environ.get("LOAD_RAMP_START", "4"))
        step_users = int(os.environ.get("LOAD_RAMP_STEP_USERS", "4"))
        step_secs = float(os.environ.get("LOAD_RAMP_STEP_SECS", "20"))
        max_users = int(os.environ.get("LOAD_RAMP_MAX", "80"))
        spawn_rate = float(os.environ.get("LOAD_SPAWN_RATE", "2"))
        fail_stop = float(os.environ.get("LOAD_RAMP_FAIL_RATIO", "0.08"))
        min_requests = int(os.environ.get("LOAD_RAMP_MIN_REQUESTS", "80"))
        hold_after_cap_secs = 60.0

        def tick(self):
            run_time = self.get_run_time()
            stats = getattr(self.runner, "stats", None) if self.runner else None
            total = getattr(stats, "total", None) if stats else None
            nreq = int(getattr(total, "num_requests", 0) or 0)
            fail_ratio = float(getattr(total, "fail_ratio", 0) or 0)
            if nreq >= self.min_requests and fail_ratio >= self.fail_stop:
                return None
            steps = int(run_time // self.step_secs)
            users = min(self.max_users, self.start_users + steps * self.step_users)
            time_to_cap = 0.0
            if self.step_users > 0:
                time_to_cap = ((self.max_users - self.start_users) / self.step_users) * self.step_secs
            if users >= self.max_users and run_time >= time_to_cap + self.hold_after_cap_secs:
                return None
            return (users, self.spawn_rate)

