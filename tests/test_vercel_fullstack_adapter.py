"""Full-stack → Vercel bundle: the public link must run the same app as the sandbox."""

import json
from pathlib import Path

from web.backend.services.vercel_fullstack_adapter import (
    build_vercel_bundle,
    collect_requirements,
    find_backend_app,
    find_frontend_dist,
)


def _product(tmp_path: Path) -> Path:
    root = tmp_path / "code" / "prod-x"
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "frontend" / "dist" / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (root / "frontend" / "dist" / "assets" / "index-abc.js").write_text("//js", encoding="utf-8")
    (root / "backend" / "app" / "core").mkdir(parents=True)
    (root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "core" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (root / "backend" / "requirements.txt").write_text(
        "fastapi==0.110.0\npsycopg2-binary==2.9.9\n# comment\nsqlalchemy\n", encoding="utf-8"
    )
    return root


def test_finds_dist_and_app(tmp_path):
    root = _product(tmp_path)
    assert find_frontend_dist(root) == root / "frontend" / "dist"
    backend_root, module, var = find_backend_app(root)
    assert backend_root == root / "backend"
    assert module == "app.main"
    assert var == "app"


def test_requirements_drop_native_postgres_drivers(tmp_path):
    root = _product(tmp_path)
    reqs = collect_requirements(root, root / "backend")
    assert "fastapi==0.110.0" in reqs
    assert "sqlalchemy" in reqs
    assert not any("psycopg" in r for r in reqs)


def test_bundle_layout_and_routing(tmp_path):
    root = _product(tmp_path)
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report

    assert (out / "public" / "index.html").is_file()
    assert (out / "public" / "assets" / "index-abc.js").is_file()
    assert (out / "api" / "app" / "main.py").is_file()
    assert (out / "requirements.txt").is_file()

    entry = (out / "api" / "index.py").read_text(encoding="utf-8")
    assert "from app.main import app as app" in entry
    assert "/tmp/product.db" in entry  # serverless disks are read-only elsewhere

    cfg = json.loads((out / "vercel.json").read_text(encoding="utf-8"))
    routes = cfg["routes"]
    assert routes[0] == {"src": "/api/(.*)", "dest": "api/index.py"}
    assert routes[-1] == {"src": "/(.*)", "dest": "/public/index.html"}
    assert cfg["env"]["DATABASE_URL"].startswith("sqlite:////tmp")
    assert cfg["env"]["SANDBOX_DEMO_EMAIL"]
    assert cfg["env"]["SANDBOX_DEMO_PASSWORD"]
    assert "SANDBOX_DEMO_EMAIL" in entry
    assert "SANDBOX_DEMO_PASSWORD" in entry
    assert 'os.environ["SANDBOX_DEMO_EMAIL"]' in entry or "os.environ['SANDBOX_DEMO_EMAIL']" in entry
    assert report.get("demo_auth_injected") is True
    assert report.get("mesh_env_injected") is True
    assert cfg["env"]["ATLAS_BASE_URL"].startswith("https://")
    assert "localhost" not in cfg["env"]["ATLAS_BASE_URL"]
    assert "ATLAS_BASE_URL" in entry
    # Non-demo keys still use setdefault (sqlite path etc.).
    assert "setdefault" in entry


def test_bundle_rewrites_legacy_aimarket_invoke_path(tmp_path):
    root = _product(tmp_path)
    client = root / "backend" / "app" / "atlas_client.py"
    client.write_text(
        'url = f"{base}/aimarket/invoke"\n',
        encoding="utf-8",
    )
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    vendored = (out / "api" / "app" / "atlas_client.py").read_text(encoding="utf-8")
    assert "/ai-market/v2/invoke" in vendored
    assert "/aimarket/invoke" not in vendored
    assert any(p.endswith("atlas_client.py") for p in (report.get("mesh_invoke_rewrites") or []))


def test_bundle_exports_settings_singleton_for_broken_imports(tmp_path):
    """Sentinel seed does ``from .config import settings`` while config only has get_settings()."""
    root = _product(tmp_path)
    cfg = root / "backend" / "app" / "config.py"
    cfg.write_text(
        "from functools import lru_cache\n\n"
        "class Settings:\n"
        "    atlas_base_url = 'http://localhost:8001'\n"
        "    sandbox_demo_email = 'x@y.z'\n\n"
        "@lru_cache()\n"
        "def get_settings():\n"
        "    return Settings()\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "seed.py").write_text(
        "from .config import settings\nemail = settings.SANDBOX_DEMO_EMAIL\n",
        encoding="utf-8",
    )
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    vendored = (out / "api" / "app" / "config.py").read_text(encoding="utf-8")
    assert "aicom-factory-settings-export" in vendored
    assert "settings = _AicomSettingsView(get_settings())" in vendored
    assert any(p.endswith("config.py") for p in (report.get("settings_exports") or []))

    # Execute just the shim against a tiny Settings stand-in (no pydantic needed).
    ns: dict = {}
    exec(
        "class Settings:\n"
        "    atlas_base_url = 'http://localhost:8001'\n"
        "    sandbox_demo_email = 'x@y.z'\n"
        "def get_settings():\n"
        "    return Settings()\n"
        + vendored[vendored.index("# aicom-factory-settings-export") :],
        ns,
        ns,
    )
    assert ns["settings"].SANDBOX_DEMO_EMAIL == "x@y.z"
    assert ns["settings"].atlas_base_url == "http://localhost:8001"


def test_bundle_widens_bbox_and_replaces_stub_rule_engine(tmp_path):
    root = _product(tmp_path)
    (root / "backend" / "app" / "services").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "app" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "services" / "atlas_client.py").write_text(
        'return {"north": lat + 0.1, "south": lat - 0.1, "east": lon + 0.1, "west": lon - 0.1}\n',
        encoding="utf-8",
    )
    (root / "backend" / "app" / "services" / "rule_engine.py").write_text(
        "class RuleEngine:\n"
        "    def _evaluate_weather(self, data):\n"
        "        wind = data.get('wind_speed_kmh', 0)\n"
        "        return ('UNKNOWN', None, [{'name': 'Weather data', 'condition': 'mesh response unavailable', 'fired': False}])\n",
        encoding="utf-8",
    )
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    client = (out / "api" / "app" / "services" / "atlas_client.py").read_text(encoding="utf-8")
    assert "lat + 5.0" in client and "lat + 0.1" not in client and "lat + 1.0" not in client
    engine = (out / "api" / "app" / "services" / "rule_engine.py").read_text(encoding="utf-8")
    assert "aicom-factory-atlas-rule-engine" in engine
    assert "wind_speed_kmh" in engine  # still handles legacy fields when present
    assert "_score_level" in engine



def test_bundle_is_rebuilt_idempotently(tmp_path):
    root = _product(tmp_path)
    out = tmp_path / "bundle"
    build_vercel_bundle(root, out, build_frontend=False)
    (out / "public" / "stale.txt").write_text("old", encoding="utf-8")
    build_vercel_bundle(root, out, build_frontend=False)
    assert not (out / "public" / "stale.txt").exists()


def test_missing_frontend_build_is_reported(tmp_path):
    root = tmp_path / "code" / "prod-y"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    report = build_vercel_bundle(root, tmp_path / "bundle", build_frontend=False)
    assert report["ok"] is False
    assert report["error"] == "no_frontend_build"


def test_namespace_package_layout_resolves_to_the_importable_root(tmp_path):
    """backend/app/ with no __init__.py, and main.py doing `from app.db import ...`.

    Stopping at __init__.py resolved this to `main` rooted at backend/app, so
    vendoring the contents of app/ would break every `from app.…` import in the
    deployed function.
    """
    root = tmp_path / "code" / "prod-ns"
    (root / "backend" / "app" / "core").mkdir(parents=True)
    (root / "backend" / "app" / "db.py").write_text("engine = 1\n", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\nfrom app.db import engine\napp = FastAPI()\n",
        encoding="utf-8",
    )
    backend_root, module, var = find_backend_app(root)
    assert backend_root == root / "backend"
    assert module == "app.main"
    assert var == "app"


def test_relative_imports_vendor_the_package_not_its_guts(tmp_path):
    """Sentinel: backend/app/main.py does `from .db import` and has no __init__.py.

    The bundle used to copy the contents of app/ into api/ and emit
    `from main import app`. Relative imports then fail at cold start —
    FUNCTION_INVOCATION_FAILED on /api/health of an otherwise successful deploy.
    """
    root = tmp_path / "code" / "prod-rel"
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "frontend" / "dist" / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (root / "frontend" / "dist" / "assets" / "index-abc.js").write_text("//js", encoding="utf-8")
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "db.py").write_text("engine = 1\n", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\nfrom .db import engine\nfrom . import models\napp = FastAPI()\n",
        encoding="utf-8",
    )
    backend_root, module, var = find_backend_app(root)
    assert backend_root == root / "backend"
    assert module == "app.main"
    assert var == "app"

    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    assert (out / "api" / "app" / "main.py").is_file()
    assert (out / "api" / "app" / "__init__.py").is_file()
    assert "from app.main import app as app" in (out / "api" / "index.py").read_text()
    assert not (out / "api" / "main.py").exists()


def test_emailstr_adds_email_validator_when_requirements_omit_it(tmp_path):
    """LoginRequest(EmailStr) 500'd the live function: email-validator was not
    in the product's requirements.txt, so collect_requirements never reached the
    default list that already named it."""
    root = tmp_path / "code" / "prod-email"
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "frontend" / "dist" / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (root / "frontend" / "dist" / "assets" / "x.js").write_text("//js", encoding="utf-8")
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\nfrom pydantic import EmailStr, BaseModel\n"
        "class LoginRequest(BaseModel):\n    email: EmailStr\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (root / "backend" / "requirements.txt").write_text(
        "fastapi==0.115.0\npydantic==2.9.2\npytest==8.3.3\nruff==0.6.9\n",
        encoding="utf-8",
    )
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    reqs = (out / "requirements.txt").read_text(encoding="utf-8")
    assert "email-validator" in reqs
    assert "pytest" not in reqs
    assert "ruff" not in reqs


def test_pydantic_settings_import_adds_the_package(tmp_path):
    root = tmp_path / "code" / "prod-settings"
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "frontend" / "dist" / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (root / "frontend" / "dist" / "assets" / "x.js").write_text("//js", encoding="utf-8")
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "config.py").write_text(
        "from pydantic_settings import BaseSettings\nclass Settings(BaseSettings):\n    x: str = 'y'\n",
        encoding="utf-8",
    )
    (root / "backend" / "requirements.txt").write_text(
        "fastapi==0.111.0\npydantic==2.7.1\n",
        encoding="utf-8",
    )
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    reqs = (out / "requirements.txt").read_text(encoding="utf-8")
    assert "pydantic-settings" in reqs


def test_plain_module_without_self_reference_keeps_its_own_root(tmp_path):
    root = tmp_path / "code" / "prod-flat"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    backend_root, module, _ = find_backend_app(root)
    assert backend_root == root / "backend"
    assert module == "main"


def test_deploys_walletless_by_default(tmp_path, monkeypatch):
    """A published product must work for a visitor with no wallet: the mesh's free
    trial allowance is what a demo actually runs on."""
    monkeypatch.delenv("AIFACTORY_PRODUCT_WALLET_ADDRESS", raising=False)
    root = _product(tmp_path)
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)

    assert report["wallet_enabled"] is False
    cfg = json.loads((out / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["env"]["WALLET_ENABLED"] == "0"
    assert "WALLET_ADDRESS" not in cfg["env"]


def test_wallet_is_bound_when_the_operator_opts_in(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PRODUCT_WALLET_ADDRESS", "0x1218000000000000000000000000000000000Ad0a")
    monkeypatch.setenv("AIFACTORY_PRODUCT_WALLET_CHAIN", "base")
    root = _product(tmp_path)
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)

    assert report["wallet_enabled"] is True
    cfg = json.loads((out / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["env"]["WALLET_ENABLED"] == "1"
    assert cfg["env"]["WALLET_ADDRESS"].startswith("0x1218")
    assert cfg["env"]["WALLET_CHAIN"] == "base"
    # The entrypoint must carry the same values, or the function and the platform disagree.
    entry = (out / "api" / "index.py").read_text(encoding="utf-8")
    assert "WALLET_ENABLED" in entry and "0x1218" in entry


def test_a_private_key_is_never_carried_into_a_deployment(tmp_path, monkeypatch):
    """An address is configuration; a key would be custody. The adapter reads neither."""
    monkeypatch.setenv("AIFACTORY_PRODUCT_WALLET_ADDRESS", "0xabc0000000000000000000000000000000000001")
    monkeypatch.setenv("AIFACTORY_PRODUCT_WALLET_PRIVATE_KEY", "0xdeadbeefcafe")
    monkeypatch.setenv("WALLET_PRIVATE_KEY", "0xdeadbeefcafe")
    root = _product(tmp_path)
    out = tmp_path / "bundle"
    build_vercel_bundle(root, out, build_frontend=False)

    blob = (out / "vercel.json").read_text(encoding="utf-8") + (out / "api" / "index.py").read_text(encoding="utf-8")
    assert "deadbeefcafe" not in blob
    assert "PRIVATE_KEY" not in blob


def test_the_default_chain_is_base_when_only_an_address_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PRODUCT_WALLET_ADDRESS", "0xabc0000000000000000000000000000000000002")
    monkeypatch.delenv("AIFACTORY_PRODUCT_WALLET_CHAIN", raising=False)
    root = _product(tmp_path)
    out = tmp_path / "bundle"
    build_vercel_bundle(root, out, build_frontend=False)
    cfg = json.loads((out / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["env"]["WALLET_CHAIN"] == "base"
