from fastapi.testclient import TestClient

from relay_scout.api import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_devtools_ops_flow() -> None:
    proj = client.post("/api/projects", json={"name": "relay-scout", "repo": "aicom"}).json()
    pid = proj["id"]
    dep = client.post(
        f"/api/projects/{pid}/deployments",
        json={"version": "0.1.0", "environment": "staging"},
    ).json()
    did = dep["id"]
    assert client.get(f"/api/deployments/{did}").json()["status"] == "succeeded"
    logs = client.get(f"/api/projects/{pid}/logs").json()
    assert logs["logs"]
    alert = client.post("/api/alerts", json={"name": "down", "severity": "high"}).json()
    ack = client.post(f"/api/alerts/{alert['id']}/ack", json={"note": "seen"}).json()
    assert ack["state"] == "acknowledged"
    rb = client.post(f"/api/deployments/{did}/rollback").json()
    assert rb["status"] == "rolled back"
