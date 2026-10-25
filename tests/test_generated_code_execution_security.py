"""Generated Python/JS must not run with the factory host's privileges by default."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from core.generated_code_execution import (
    LOCAL_HOST_OPT_IN,
    GeneratedCodeIsolationRequired,
    require_host_execution_opt_in,
)


@pytest.fixture(autouse=True)
def secure_default(monkeypatch, tmp_path):
    for name in (LOCAL_HOST_OPT_IN, "AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_DEMO_READONLY",
                 "AIFACTORY_SANDBOX_REQUIRE_CONTAINER", "AIFACTORY_ENV"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))


def test_private_host_execution_requires_explicit_opt_in(monkeypatch):
    with pytest.raises(GeneratedCodeIsolationRequired):
        require_host_execution_opt_in()
    monkeypatch.setenv(LOCAL_HOST_OPT_IN, "1")
    require_host_execution_opt_in()


@pytest.mark.parametrize("flag", ["AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_DEMO_READONLY",
                                  "AIFACTORY_SANDBOX_REQUIRE_CONTAINER"])
def test_protected_deployments_cannot_enable_unsafe_host_execution(monkeypatch, flag):
    monkeypatch.setenv(LOCAL_HOST_OPT_IN, "1")
    monkeypatch.setenv(flag, "true")
    with pytest.raises(GeneratedCodeIsolationRequired):
        require_host_execution_opt_in()


@pytest.mark.parametrize("tag", ["production", "prod", "live"])
def test_all_production_environment_tags_refuse_unsafe_execution(monkeypatch, tag):
    monkeypatch.setenv(LOCAL_HOST_OPT_IN, "1")
    monkeypatch.setenv("AIFACTORY_ENV", tag)
    with pytest.raises(GeneratedCodeIsolationRequired):
        require_host_execution_opt_in()


def _no_execution(*args, **kwargs):
    raise AssertionError("Untrusted execution reached a factory-host subprocess")


@pytest.fixture
def malicious_product(tmp_path):
    code = tmp_path / "data" / "code" / "evil-product"
    code.mkdir(parents=True)
    marker = tmp_path / "executed"
    payload = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    (code / "test_attack.py").write_text(payload + "def test_attack(): pass\n")
    (code / "main.py").write_text(payload + "from fastapi import FastAPI\napp = FastAPI()\n")
    (code / "requirements.txt").write_text("-e .\n")
    (code / "setup.py").write_text(payload)
    (code / "package.json").write_text('{"scripts":{"build":"touch ../executed","postinstall":"touch ../executed"}}')
    return code, marker


def test_pytest_static_plugins_and_import_checks_never_execute_or_mutate_factory_imports(monkeypatch, malicious_product):
    from agents.qa_checks.tooling import ToolingMixin
    code, marker = malicious_product
    monkeypatch.setattr(subprocess, "run", _no_execution)
    files = [{"path": str(code / "test_attack.py"), "content": (code / "test_attack.py").read_text()}]
    mixin = ToolingMixin()
    assert mixin._run_static_analysis(files) == []  # compile() remains a safe syntax check.
    result = mixin._run_tests(files)
    assert result["failed"] == 1
    assert "isolation_required" in result["failures"][0]["name"]
    before = list(sys.path)
    assert mixin._check_imports(files) == []
    assert sys.path == before
    assert not marker.exists()


def test_backend_and_preview_refuse_before_pip_npm_or_uvicorn(monkeypatch, malicious_product):
    from web.backend.services import backend_runtime_e2e, sandbox_preview_api
    code, marker = malicious_product
    monkeypatch.setattr(subprocess, "run", _no_execution)
    monkeypatch.setattr(subprocess, "Popen", _no_execution)
    monkeypatch.setattr(sandbox_preview_api, "ensure_frontend_dist", _no_execution)
    monkeypatch.setattr(sandbox_preview_api, "build_fastapi_preview_env", _no_execution)
    port, proc, reason = sandbox_preview_api.start_fastapi_preview(sandbox_id="test", code_dir=code)
    assert port is None and proc is None and "isolation_required" in reason
    result = backend_runtime_e2e.run_backend_runtime_e2e("evil-product", code.parents[1])
    assert not result["passed"] and "isolation_required" in result["issues"][0]
    assert not marker.exists()


def test_python_properties_and_automated_pytest_cannot_import_payload(monkeypatch, malicious_product):
    from web.backend.services.product_automated_verify import _run_pytest_if_present
    from web.backend.services.property_contract_gate import run_properties
    code, marker = malicious_product
    monkeypatch.setattr(subprocess, "run", _no_execution)
    monkeypatch.setattr(subprocess, "Popen", _no_execution)
    result = run_properties(code, [{"kind": "deterministic", "target": "test_attack:test_attack", "args": {}}])
    assert result["skipped"] is False and "isolation_required" in result["reason"]
    result = _run_pytest_if_present(code)
    assert result["passed"] is False and result["reason"] == "generated_code_isolation_required"
    assert not marker.exists()


def test_frontend_builds_refuse_before_npm_lifecycle_scripts(monkeypatch, malicious_product):
    from web.backend.services.frontend_build_check import npm_env, run_frontend_build_check
    from web.backend.services.vercel_bundle.discovery import _try_build_frontend
    code, marker = malicious_product
    monkeypatch.setattr(subprocess, "run", _no_execution)
    with pytest.raises(GeneratedCodeIsolationRequired):
        npm_env()
    result = run_frontend_build_check("evil-product", code.parents[1])
    assert not result["passed"] and "isolation_required" in result["issues"][0]
    assert _try_build_frontend(code)["error"] == "generated_code_isolation_required"
    assert not marker.exists()


@pytest.mark.parametrize("entry", ["pip_env", "_preview_venv_python", "_pip_install_one", "_pip_install_requirements",
                                  "_run_alembic_if_present", "_run_seed_script", "build_fastapi_preview_env"])
def test_each_python_setup_boundary_checks_policy_before_execution(monkeypatch, malicious_product, entry):
    from web.backend.services import sandbox_preview_env as module
    code, marker = malicious_product
    monkeypatch.setattr(subprocess, "run", _no_execution)
    python = Path(sys.executable)
    calls = {
        "pip_env": lambda: module.pip_env(),
        "_preview_venv_python": lambda: module._preview_venv_python(code, "attack"),
        "_pip_install_one": lambda: module._pip_install_one(python, str(code)),
        "_pip_install_requirements": lambda: module._pip_install_requirements(code, code, python),
        "_run_alembic_if_present": lambda: module._run_alembic_if_present(code, {}, python),
        "_run_seed_script": lambda: module._run_seed_script(code, {}, python),
        "build_fastapi_preview_env": lambda: module.build_fastapi_preview_env(sandbox_id="attack", code_dir=code, cwd=code),
    }
    with pytest.raises(GeneratedCodeIsolationRequired):
        calls[entry]()
    assert not marker.exists()


def test_real_payload_cannot_read_a_host_secret_without_production_marker(tmp_path, monkeypatch):
    from agents.qa_checks.tooling import ToolingMixin
    secret = tmp_path / "private-factory-secret"
    secret.write_text("test-canary-only")
    leaked = tmp_path / "leaked"
    attack = tmp_path / "test_exfiltration.py"
    attack.write_text(f"from pathlib import Path\nPath({str(leaked)!r}).write_text(Path({str(secret)!r}).read_text())\n")
    # Do not mock subprocess: if the boundary regresses, this canary is copied by
    # real malicious Python with an otherwise perfectly scrubbed environment.
    result = ToolingMixin()._run_tests([{"path": str(attack), "content": attack.read_text()}])
    assert result["failed"] == 1 and not leaked.exists()


def test_public_customer_creation_cannot_feed_a_private_unsafe_worker(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from web.backend.api import customer
    monkeypatch.setenv(LOCAL_HOST_OPT_IN, "1")
    app = FastAPI()
    app.include_router(customer.router)
    app.dependency_overrides[customer._get_token_payload] = lambda: {"sub": "cust-public", "email": "test@example.com"}
    monkeypatch.setattr(customer.commerce, "get_customer", _no_execution)
    monkeypatch.setattr(customer, "append_product_to_pipeline_state", _no_execution)
    with TestClient(app) as client:
        response = client.post("/api/customer/pipeline/run", json={"idea": "Build attacker-controlled code"})
    assert response.status_code == 503
    assert "isolated worker" in response.json()["detail"]


def test_anonymous_guest_creation_cannot_feed_a_private_unsafe_worker(monkeypatch):
    from fastapi.testclient import TestClient

    from web.backend import main

    monkeypatch.setenv(LOCAL_HOST_OPT_IN, "1")
    monkeypatch.setattr(main, "_append_product_to_pipeline", _no_execution)
    client = TestClient(main.app)
    response = client.post("/api/public/generate-landing", json={"phrase": "Build attacker-controlled code"})
    assert response.status_code == 503
    assert "isolated worker" in response.json()["detail"]


def test_anonymous_support_cannot_trigger_a_private_host_worker(monkeypatch):
    from web.backend.services.support_pipeline import support_auto_repair_enabled

    monkeypatch.setenv(LOCAL_HOST_OPT_IN, "1")
    monkeypatch.setenv("AIFACTORY_SUPPORT_AUTO_REPAIR", "1")
    assert support_auto_repair_enabled() is False


@pytest.mark.parametrize("manifest_commands", [[], ["python3 -m pytest test_attack.py"]])
def test_pipeline_runtime_gate_refuses_manifest_and_inferred_host_execution(monkeypatch, malicious_product, manifest_commands):
    import json
    from types import SimpleNamespace

    from orchestrator.pipeline_worker_sidecars import PipelineWorkerSidecarMixin

    code, marker = malicious_product
    (code / "code_manifest.json").write_text(json.dumps({"test_commands": manifest_commands}))
    monkeypatch.setattr(subprocess, "run", _no_execution)
    host = SimpleNamespace(data_root=code.parents[1])
    result = PipelineWorkerSidecarMixin._run_runtime_tests(host, code.name, [])
    assert result["passed"] is False and result["error"] == "generated_code_isolation_required"
    assert not marker.exists()


def test_production_rejects_weak_persisted_customer_jwt_key(monkeypatch, tmp_path):
    from core import paths
    from web.backend.services.commerce import _resolve_customer_jwt_secret
    key = tmp_path / "customer-jwt.key"
    key.write_text("weak-known-key")
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("CUSTOMER_JWT_SECRET", raising=False)
    monkeypatch.setattr(paths, "customer_jwt_secret_path", lambda: key)
    with pytest.raises(RuntimeError, match="too weak"):
        _resolve_customer_jwt_secret()
