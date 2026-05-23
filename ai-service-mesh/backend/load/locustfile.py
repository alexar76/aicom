"""Load test — run: locust -f load/locustfile.py --host http://127.0.0.1:8090"""

from __future__ import annotations

import os

from locust import HttpUser, between, task


class MeshDashboardUser(HttpUser):
    wait_time = between(0.2, 0.8)
    token = os.environ.get("MESH_API_TOKEN", "")

    @task(5)
    def stats(self):
        self.client.get("/v1/stats")

    @task(4)
    def activity(self):
        self.client.get("/v1/activity?limit=50")

    @task(3)
    def agents(self):
        self.client.get("/v1/agents?verified_only=true")

    @task(2)
    def create_task(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client.post(
            "/v1/tasks",
            json={
                "intent": "load test mesh orchestration",
                "budget_usd": 2.5,
                "preferred_capabilities": ["research"],
            },
            headers=headers,
        )

    @task(1)
    def health(self):
        self.client.get("/health")
