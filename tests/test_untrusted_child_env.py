"""Untrusted generated code must not inherit the factory's credentials.

The factory runs the code it generates: the sandbox preview pip-installs a product's
requirements (build hooks execute) and imports its modules under uvicorn, and the
pipeline worker runs the product's runtime test commands. Both used to hand the child
``os.environ`` -- the factory's LLM keys, JWT signing secret, publish tokens, database
credentials and Docker socket. These tests pin the scrub.

See core/child_env.py and docs/sandbox-trust-model.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.child_env import is_sensitive, scrub_child_env

FACTORY_SECRETS = [
    "JWT_SECRET_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "AIMARKET_ADMIN_TOKEN",
    "ALIEN_API_TOKEN",
    "POSTGRES_PASSWORD",
    "VERCEL_TOKEN",
    "GH_PAT",
    "GITHUB_TOKEN",
    "AIMARKET_ESCROW_PRIVATE_KEY",
    "DOCKER_HOST",
    "DOCKER_CERT_PATH",
    "MESH_ADMIN_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "AIFACTORY_DEV_BOOTSTRAP_PASSWORD",
]

INNOCENT = ["PATH", "HOME", "LANG", "TZ", "PYTHONPATH", "PYTHONUNBUFFERED", "ENVIRONMENT"]


def test_every_known_factory_secret_is_classified_sensitive() -> None:
    for key in FACTORY_SECRETS:
        assert is_sensitive(key), f"{key} would leak into an untrusted child"


def test_scrub_keeps_what_a_child_actually_needs() -> None:
    src = {k: "x" for k in INNOCENT} | {k: "secret" for k in FACTORY_SECRETS}
    out = scrub_child_env(src)
    assert set(out) == set(INNOCENT)


def test_scrub_drops_database_url_so_generated_code_cannot_reach_the_factory_db() -> None:
    src = {"DATABASE_URL": "postgresql://aicom:pw@postgres:5432/aicom", "PATH": "/usr/bin"}
    assert "DATABASE_URL" not in scrub_child_env(src)


def test_keep_re_admits_an_explicit_exception() -> None:
    src = {"SANDBOX_DEMO_PASSWORD": "demo", "JWT_SECRET_KEY": "k"}
    out = scrub_child_env(src, keep=["SANDBOX_DEMO_PASSWORD"])
    assert out == {"SANDBOX_DEMO_PASSWORD": "demo"}


def test_preview_env_carries_no_factory_secret(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: the env handed to the uvicorn preview child."""
    from web.backend.services.sandbox_preview_env import build_fastapi_preview_env

    code_dir = tmp_path / "code"
    (code_dir / "backend").mkdir(parents=True)
    (code_dir / "backend" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "web.backend.services.sandbox_preview_env._pip_install_requirements",
        lambda *a, **k: {"status": "skipped"},
    )

    base = {k: "leaked" for k in FACTORY_SECRETS} | {"PATH": "/usr/bin"}
    env, _meta = build_fastapi_preview_env(
        sandbox_id="sbx-child-env",
        code_dir=code_dir,
        cwd=code_dir / "backend",
        base_env=base,
    )

    leaked = [k for k in FACTORY_SECRETS if env.get(k) == "leaked"]
    assert not leaked, f"factory secrets reached the preview child: {leaked}"
    # The sandbox's own values replace the ones that were dropped.
    assert env["SECRET_KEY"] == "sandbox-dev-secret"
    assert "sqlite" in env["DATABASE_URL"].lower()


def test_npm_build_env_carries_no_factory_secret(monkeypatch, tmp_path) -> None:
    """`npm install` runs the product's own preinstall/postinstall scripts.

    Both the QA frontend gate and the Vercel publish path build a model-authored
    package.json, so this env reaches lifecycle scripts written by the model.
    """
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    for key in FACTORY_SECRETS:
        monkeypatch.setenv(key, "leaked")

    from web.backend.services.frontend_build_check import npm_env

    env = npm_env()
    leaked = [k for k in FACTORY_SECRETS if env.get(k) == "leaked"]
    assert not leaked, f"factory secrets reached an npm lifecycle script: {leaked}"
    # The writable-path setup npm actually needs is untouched.
    assert env["CI"] == "1"
    assert env["HOME"] and env["npm_config_cache"]


def test_qa_pytest_env_carries_no_factory_secret(monkeypatch, tmp_path: Path) -> None:
    """The legacy QA pytest path must use the same untrusted-child boundary."""
    from agents.qa import QAAgent

    test_file = tmp_path / "test_generated.py"
    test_file.write_text("def test_ok(): assert True\n", encoding="utf-8")
    for key in FACTORY_SECRETS:
        monkeypatch.setenv(key, "leaked")

    captured: dict[str, str] = {}

    def fake_run(*_args, **kwargs):
        captured.update(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr("agents.qa.subprocess.run", fake_run)
    agent = QAAgent(llm_router=MagicMock(), data_root=str(tmp_path / "factory-data"))
    result = agent._run_tests([{"path": str(test_file), "content": test_file.read_text()}])

    assert result["passed"] == 1
    assert not [key for key in FACTORY_SECRETS if captured.get(key) == "leaked"]
    assert captured["ENVIRONMENT"] == "test"


def test_automated_verify_pytest_env_carries_no_factory_secret(monkeypatch, tmp_path: Path) -> None:
    from web.backend.services.product_automated_verify import _run_pytest_if_present

    (tmp_path / "test_generated.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    for key in FACTORY_SECRETS:
        monkeypatch.setenv(key, "leaked")

    captured: dict[str, object] = {}

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr("web.backend.services.product_automated_verify.subprocess.run", fake_run)
    result = _run_pytest_if_present(tmp_path)

    assert result["passed"] is True
    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert not [key for key in FACTORY_SECRETS if child_env.get(key) == "leaked"]
    assert child_env["PYTHONPATH"] == str(tmp_path)
    assert captured["timeout"] == 120


def test_automated_verify_pytest_timeout_is_bounded(monkeypatch, tmp_path: Path) -> None:
    from web.backend.services.product_automated_verify import _run_pytest_if_present

    (tmp_path / "test_generated.py").write_text("def test_hangs(): pass\n", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_AUTOMATED_PYTEST_TIMEOUT_SEC", "99999")

    def fake_run(*_args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=kwargs["timeout"], output="partial")

    monkeypatch.setattr("web.backend.services.product_automated_verify.subprocess.run", fake_run)
    result = _run_pytest_if_present(tmp_path)

    assert result["passed"] is False
    assert result["reason"] == "pytest_timeout"
    assert result["timeout_seconds"] == 600
    assert result["stdout_tail"] == "partial"


def test_backend_direct_entrypoint_env_carries_no_factory_secret(monkeypatch, tmp_path: Path) -> None:
    from web.backend.services.backend_runtime_e2e import run_backend_runtime_e2e

    product = tmp_path / "code" / "generated"
    product.mkdir(parents=True)
    (product / "main.py").write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    for key in FACTORY_SECRETS:
        monkeypatch.setenv(key, "leaked")

    captured: dict[str, str] = {}

    class FakeProc:
        pid = 99999999

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    def fake_popen(*_args, **kwargs):
        captured.update(kwargs.get("env") or {})
        return FakeProc()

    monkeypatch.setattr("web.backend.services.backend_runtime_e2e.subprocess.Popen", fake_popen)
    monkeypatch.setattr("web.backend.services.backend_runtime_e2e._wait_for_port", lambda *_a, **_k: False)
    monkeypatch.setattr("web.backend.services.sandbox_preview_api.detect_fastapi_backend", lambda _p: None)

    result = run_backend_runtime_e2e("generated", data_root=tmp_path)

    assert result["passed"] is False
    assert not [key for key in FACTORY_SECRETS if captured.get(key) == "leaked"]
    assert captured["SECRET_KEY"] == "sandbox-dev-secret"


# --- 2026-09 re-audit: pip was the runner nobody remembered ---------------------------
#
# `npm_env()` already carried the whole argument in its docstring — "npm install on a
# model-authored package.json executes that package's preinstall/postinstall scripts" — and
# the uvicorn preview, the QA pytest runner and the automated-verify runner were all
# scrubbed. `pip install` does the identical thing (a product's requirements.txt and its
# own pyproject run setup.py / a PEP 517 backend at INSTALL time) and was left inheriting
# os.environ in full. It also runs FIRST, before the preview whose env was carefully
# scrubbed. The tests above had the same blind spot as the code: they enumerated the
# runners someone thought of.

def _child_spawns_without_env(module_path: str) -> list[tuple[int, str]]:
    """Every subprocess spawn in a module that does not pass an explicit `env=`."""
    import ast
    from pathlib import Path as _Path

    tree = ast.parse(_Path(module_path).read_text(encoding="utf-8"))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"run", "Popen", "call", "check_output", "check_call"}:
            continue
        if getattr(getattr(node.func, "value", None), "id", "") != "subprocess":
            continue
        if any(kw.arg == "env" for kw in node.keywords):
            continue
        argv = ""
        if node.args:
            try:
                argv = ast.unparse(node.args[0])
            except Exception:  # pragma: no cover - display only
                argv = "<unparseable>"
        out.append((node.lineno, argv))
    return out


def test_no_spawn_in_the_preview_builder_inherits_the_factory_environment() -> None:
    """Inventory guard: every child here handles untrusted product code, so every child is scrubbed.

    Keyed on the module, not on a list of function names, so the next runner added to this
    file cannot reintroduce the gap by being forgotten — which is how pip kept it.
    """
    offenders = _child_spawns_without_env("web/backend/services/sandbox_preview_env.py")
    assert not offenders, (
        "these spawns inherit os.environ (provider keys, JWT secret, publish tokens, "
        f"DOCKER_HOST) while handling untrusted code: {offenders}"
    )


def test_pip_env_carries_no_factory_secret(monkeypatch, tmp_path) -> None:
    """pip runs the product's build hooks; it must see none of the factory's credentials."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-reach-a-build-hook")
    monkeypatch.setenv("AIFACTORY_JWT_SECRET", "jwt-must-not-reach-a-build-hook")
    monkeypatch.setenv("VERCEL_TOKEN", "publish-must-not-reach-a-build-hook")
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:2375")
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory:pw@db/factory")

    from web.backend.services.sandbox_preview_env import pip_env

    env = pip_env()
    for leaked in ("ANTHROPIC_API_KEY", "AIFACTORY_JWT_SECRET", "VERCEL_TOKEN",
                   "DOCKER_HOST", "DATABASE_URL"):
        assert leaked not in env, f"{leaked} reaches a package build hook"
    # pip still has to be able to run: it needs a PATH and a writable HOME for its cache.
    assert env.get("PATH")
    assert env.get("HOME")
