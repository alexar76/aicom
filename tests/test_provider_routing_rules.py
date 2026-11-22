from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.api.admin.dashboard import router
from web.backend.core.admin_roles import require_admin_with_rbac


def test_admin_can_save_all_shipped_routing_rules(tmp_path, monkeypatch):
    example_path = Path(__file__).resolve().parents[1] / "data/config/model_providers.example.yaml"
    config_path = tmp_path / "data/config/model_providers.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_bytes(example_path.read_bytes())
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_MODEL_PROVIDERS", str(config_path))
    original_rules = yaml.safe_load(config_path.read_text(encoding="utf-8"))["routing_rules"]

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_with_rbac] = lambda: {}
    url = "/api/admin/providers/routing-rules"
    with TestClient(app) as client:
        response = client.get(url)
        assert response.status_code == 200
        rules = response.json()["routing_rules"]
        assert rules == original_rules
        next(rule for rule in rules if rule["task_type"] == "design_critic")["timeout_sec"] += 1

        response = client.put(url, json={"routing_rules": rules})
        assert response.status_code == 200, response.text
        assert client.get(url).json()["routing_rules"] == rules

    saved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved_config["routing_rules"] == rules
