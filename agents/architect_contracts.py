"""Architect implementation-contract helpers (compose, testing, IC fill).

Split out of ``architect.py`` to keep the agent class readable.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_GITHUB_HOUSE_LAYOUT_PATHS = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "docs/en.md",
    "docs/badges/",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "tests/",
)

_GITHUB_HOUSE_SHORTCUT = (
    "Shipping without README.md, committed docs/badges, CI (.github/workflows/ci.yml), "
    "tests, CHANGELOG, LICENSE, GitHub Release workflow, or bilingual docs (GITHUB_HOUSE_CONTRACT)."
)


def _ensure_github_house_layout(arch: dict, spec: dict, *, landing_charter: bool) -> None:
    """Append GitHub-house paths the Architect omitted from repository_layout."""
    if landing_charter:
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    ic = arch.get("implementation_contract") if isinstance(arch, dict) else None
    if not isinstance(ic, dict):
        return

    rl = str(ic.get("repository_layout") or "")
    low = rl.lower()
    extras: list[str] = []
    for path in _GITHUB_HOUSE_LAYOUT_PATHS:
        key = path.lower().rstrip("/")
        if key not in low:
            extras.append(f"  {path}")

    lang = str(arch.get("content_language") or "").strip().lower().replace("_", "-")
    if lang and lang not in ("en", "auto", "default", ""):
        if f"readme.{lang}.md" not in low:
            extras.append(f"  README.{lang}.md")
        if f"docs/{lang}.md" not in low:
            extras.append(f"  docs/{lang}.md")

    ux = arch.get("ui_experience")
    ts = arch.get("tech_stack") if isinstance(arch.get("tech_stack"), dict) else {}
    fe = str((ts or {}).get("frontend") or "").lower()
    has_ui = bool(ux) or any(token in fe for token in ("html", "react", "vite", "spa", "css", "next"))
    if has_ui and "docs/gallery" not in low:
        extras.append("  docs/gallery/")

    if extras:
        ic["repository_layout"] = (rl.rstrip() + "\n" + "\n".join(extras)).strip()

    shortcuts = ic.get("forbidden_shortcuts")
    if not isinstance(shortcuts, list):
        shortcuts = []
    if _GITHUB_HOUSE_SHORTCUT not in shortcuts:
        shortcuts.append(_GITHUB_HOUSE_SHORTCUT)
    ic["forbidden_shortcuts"] = shortcuts


def _ensure_docker_compose_contract_fields(
    arch: dict,
    spec: dict,
    *,
    landing_charter: bool,
) -> None:
    """
    Merge docker-compose expectations into implementation_contract for full_software.
    Marketing / landing-first charters skip compose requirements.
    """
    if landing_charter:
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    ic = arch.get("implementation_contract")
    if not isinstance(ic, dict):
        return

    dp_raw = ic.get("data_plane")
    dp: list[dict[str, Any]] = [x for x in dp_raw if isinstance(x, dict)] if isinstance(dp_raw, list) else []

    def _store_lower(row: dict) -> str:
        return str(row.get("store", "")).lower()

    needs_db_container = False
    outline: list[str] = []
    for row in dp:
        st = _store_lower(row)
        if st in ("postgresql", "postgres", "mysql", "mariadb", "mongodb", "mongo", "redis", "elasticsearch", "elastic"):
            needs_db_container = True
            if "postgres" in st or st == "postgresql":
                outline.append("postgres")
            elif "mysql" in st or "mariadb" in st:
                outline.append("mysql")
            elif "mongo" in st:
                outline.append("mongodb")
            elif "redis" in st:
                outline.append("redis")
            elif "elastic" in st:
                outline.append("elasticsearch")

    rs = ic.get("runnable_services")
    if isinstance(rs, list):
        for svc in rs:
            if not isinstance(svc, dict):
                continue
            n = str(svc.get("name", "")).lower()
            if n in ("api", "backend"):
                outline.append("api")
            elif n in ("web", "frontend", "spa"):
                outline.append("web")
            elif n in ("worker", "notifications"):
                outline.append(n)

    outline = sorted(set(outline))
    if not outline:
        outline = ["api"]

    docker_compose = ic.get("docker_compose")
    if not isinstance(docker_compose, dict):
        docker_compose = {}

    docker_compose.setdefault("required", True)
    docker_compose.setdefault("compose_file", "docker-compose.yml")
    if not docker_compose.get("services_outline"):
        docker_compose["services_outline"] = outline
    prev_db = bool(docker_compose.get("database_in_compose"))
    docker_compose["database_in_compose"] = prev_db or bool(needs_db_container)
    docker_compose.setdefault(
        "host_ports_env_contract",
        "Map host ports with env vars (e.g. API_HOST_PORT, WEB_HOST_PORT, POSTGRES_HOST_PORT when exposing DB) "
        "so `docker compose up` works under parallel factory sandboxes.",
    )

    ic["docker_compose"] = docker_compose

    rl = str(ic.get("repository_layout", "") or "")
    low_rl = rl.lower()
    if "docker-compose" not in low_rl and "compose.yaml" not in low_rl and "compose.yml" not in low_rl:
        ic["repository_layout"] = (rl.rstrip() + "\n  docker-compose.yml # REQUIRED — orchestrates services + DB/cache from data_plane\n").strip()

    fs = ic.get("forbidden_shortcuts")
    if not isinstance(fs, list):
        fs = []
    extras = [
        "Shipping full_software without a root docker-compose.yml (or compose.yaml) that starts runnable_services and satisfies data_plane.",
        "Running PostgreSQL/MySQL/Redis/Elasticsearch as implicit host installs instead of compose services when data_plane lists them.",
        "Hard-coded published ports only — parallel sandboxes and CI cannot bind; use API_HOST_PORT / WEB_HOST_PORT style overrides.",
    ]
    for e in extras:
        if e not in fs:
            fs.append(e)
    ic["forbidden_shortcuts"] = fs
    arch["implementation_contract"] = ic


def _ensure_testing_contract_fields(
    arch: dict,
    spec: dict,
    *,
    landing_charter: bool,
) -> None:
    """
    Enforce test pyramid (component → functional → UI) and sandbox demo login when OLTP DB exists.
    """
    if landing_charter:
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    ic = arch.get("implementation_contract")
    if not isinstance(ic, dict):
        return

    dp_raw = ic.get("data_plane")
    dp: list[dict[str, Any]] = [x for x in dp_raw if isinstance(x, dict)] if isinstance(dp_raw, list) else []

    def _needs_demo_user_seed() -> bool:
        for row in dp:
            st = str(row.get("store", "")).lower()
            if any(k in st for k in ("postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongo")):
                return True
        return False

    tc = ic.get("testing_contract")
    if not isinstance(tc, dict):
        tc = {}

    tc.setdefault("layers_ordered", ["component_unit", "functional_integration", "ui_e2e"])
    tc.setdefault(
        "execution_note",
        "Run tests strictly in order: (1) component/unit in isolation, (2) functional/integration (API + DB, no browser), "
        "(3) UI/e2e last against a running stack.",
    )

    if _needs_demo_user_seed():
        demo = tc.get("sandbox_demo_credentials")
        if not isinstance(demo, dict):
            demo = {}
        demo["required"] = True
        from core.demo_identity import sandbox_demo_email

        demo.setdefault("seed_email", sandbox_demo_email())
        # Match factory `AIFACTORY_SANDBOX_DEMO_PASSWORD` docker-compose default (see demo_credentials.py).
        demo.setdefault("seed_password", "AfSc7xK9mR2nL4vP8qW1jH0fT5dB3cZyEu")  # gitleaks:allow — mirrors demo_credentials sandbox default
        demo.setdefault(
            "env_var_names",
            "SANDBOX_DEMO_EMAIL, SANDBOX_DEMO_PASSWORD; frontend mirrors VITE_SANDBOX_DEMO_EMAIL, VITE_SANDBOX_DEMO_PASSWORD when using Vite.",
        )
        demo.setdefault(
            "seed_mechanism",
            "Alembic/Flyway/sql seed or startup hook creates this user when compose boots; document in README.",
        )
        demo.setdefault(
            "ui_prefill",
            "Login (and similar) forms must initialize email/password fields from env when SANDBOX_DEMO_* is set — reviewers must not hunt passwords in sandbox.",
        )
        tc["sandbox_demo_credentials"] = demo

    ic["testing_contract"] = tc

    vc = ic.get("verification_commands")
    if not isinstance(vc, list):
        vc = []
    tier_cmds = [
        "cd backend && (pytest tests/unit -q || pytest -q -m unit || python -m pytest tests/unit -q)",
        "cd backend && (pytest tests/integration -q || pytest -q -m integration || python -m pytest tests/integration -q)",
        "cd frontend && (npm run test:e2e --if-present || npx playwright test --pass-with-no-tests || true)",
    ]
    for c in tier_cmds:
        if c not in vc:
            vc.append(c)
    ic["verification_commands"] = vc

    fs = ic.get("forbidden_shortcuts")
    if not isinstance(fs, list):
        fs = []
    for e in (
        "Skipping the test pyramid — UI/e2e before green component/unit and functional/integration suites.",
        "Login-capable app with PostgreSQL/MySQL/MongoDB but no seeded sandbox demo user + env-driven prefilled credentials on forms.",
    ):
        if e not in fs:
            fs.append(e)
    ic["forbidden_shortcuts"] = fs
    arch["implementation_contract"] = ic


def _ensure_implementation_contract(
    arch: dict,
    spec: dict,
    idea: str,
    *,
    landing_charter: bool,
) -> None:
    """
    Guarantee full_software builds carry a concrete repo/runtime contract for the Developer.
    Fills from tech_stack heuristics when the LLM omitted the block.
    """
    if not isinstance(arch, dict):
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    if landing_charter:
        return

    ic = arch.get("implementation_contract")
    if isinstance(ic, dict) and isinstance(ic.get("runnable_services"), list) and len(ic["runnable_services"]) > 0:
        fs = ic.get("forbidden_shortcuts")
        if not isinstance(fs, list) or len(fs) < 1:
            ic = dict(ic)
            ic["forbidden_shortcuts"] = [
                "Shipping only a root index.html without the backend processes listed in runnable_services.",
                "Stack prose (K8s/Elastic/RabbitMQ) without a runnable local path (docker-compose or README) matching data_plane.",
            ]
            arch["implementation_contract"] = ic
        _ensure_docker_compose_contract_fields(arch, spec, landing_charter=landing_charter)
        _ensure_testing_contract_fields(arch, spec, landing_charter=landing_charter)
        _ensure_github_house_layout(arch, spec, landing_charter=landing_charter)
        return

    ts = arch.get("tech_stack") if isinstance(arch.get("tech_stack"), dict) else {}
    fe = str(ts.get("frontend", "")).lower()
    be = str(ts.get("backend", "")).lower()
    db = str(ts.get("database", "")).lower()

    services: list[dict[str, Any]] = []
    if any(x in be for x in ("fastapi", "python", "django", "flask", "uvicorn")):
        services.append(
            {
                "name": "api",
                "runtime": "python",
                "framework": "FastAPI",
                "entrypoint": "backend/app/main.py",
                "start_command": "cd backend && uvicorn app.main:app --reload --port 8000",
                "port_hint": 8000,
                "health_or_probe": "GET /health or /api/health",
            }
        )
    elif any(x in be for x in ("nestjs", "express", "node")):
        services.append(
            {
                "name": "api",
                "runtime": "nodejs",
                "framework": "NestJS or Express",
                "entrypoint": "backend/src/main.ts",
                "start_command": "cd backend && npm install && npm run start:dev",
                "port_hint": 3000,
                "health_or_probe": "GET /health",
            }
        )
    elif any(x in be for x in ("asp.net", "dotnet", "c#", ".net")):
        services.append(
            {
                "name": "api",
                "runtime": "dotnet",
                "framework": "ASP.NET Core",
                "entrypoint": "backend/Program.cs",
                "start_command": "cd backend && dotnet run",
                "port_hint": 5000,
                "health_or_probe": "GET /health",
            }
        )
    else:
        services.append(
            {
                "name": "api",
                "runtime": "python",
                "framework": "FastAPI",
                "entrypoint": "backend/app/main.py",
                "start_command": "cd backend && uvicorn app.main:app --reload --port 8000",
                "port_hint": 8000,
                "health_or_probe": "GET /health",
            }
        )

    if any(x in fe for x in ("react", "vite", "typescript", "next.js", "spa")):
        services.append(
            {
                "name": "web",
                "runtime": "nodejs",
                "framework": "React + Vite",
                "entrypoint": "frontend/package.json",
                "start_command": "cd frontend && npm install && npm run dev -- --host",
                "port_hint": 5173,
                "health_or_probe": "GET / loads SPA",
            }
        )

    data_plane: list[dict[str, str]] = []
    if "postgres" in db or "postgresql" in db:
        data_plane.append({"store": "postgresql", "role": "OLTP", "env_var_hint": "DATABASE_URL"})
    elif "sqlite" in db:
        data_plane.append({"store": "sqlite", "role": "OLTP", "env_var_hint": "SQLITE_PATH"})
    if "redis" in db:
        data_plane.append({"store": "redis", "role": "cache", "env_var_hint": "REDIS_URL"})
    if not data_plane:
        data_plane.append({"store": "sqlite", "role": "OLTP", "env_var_hint": "SQLITE_PATH"})

    snippet = (idea or "product")[:80]
    layout = (
        "repo-root/\n"
        "  backend/           # Primary API (matches tech_stack.backend)\n"
        "  frontend/          # SPA when React/Vite implied\n"
        "  tests/             # unit → integration → UI e2e\n"
        "  docs/en.md         # English operator guide\n"
        "  docs/badges/       # committed CI/coverage/license SVGs\n"
        "  docs/gallery/      # hero.svg + stills when there is a UI\n"
        "  .github/workflows/ci.yml\n"
        "  .github/workflows/release.yml  # GitHub Release on v* tags\n"
        "  docker-compose.yml # REQUIRED — api/web + Postgres/Redis/etc. from data_plane\n"
        "  README.md          # badges, hero/gallery, quick start, tests\n"
        "  LICENSE\n"
        "  CHANGELOG.md       # Keep a Changelog from 0.1.0\n"
        f"  # Charter: {snippet}\n"
    )

    dc_services = ["api"]
    if any(x in fe for x in ("react", "vite", "typescript", "next.js", "spa")):
        dc_services.append("web")
    if "postgres" in db or "postgresql" in db:
        dc_services.append("postgres")
    if "redis" in db:
        dc_services.append("redis")

    arch["implementation_contract"] = {
        "repository_layout": layout,
        "runnable_services": services,
        "data_plane": data_plane,
        "docker_compose": {
            "required": True,
            "compose_file": "docker-compose.yml",
            "services_outline": sorted(set(dc_services)),
            "database_in_compose": ("postgres" in db or "postgresql" in db or "redis" in db or "mysql" in db),
            "host_ports_env_contract": (
                "Use API_HOST_PORT and WEB_HOST_PORT (and POSTGRES_HOST_PORT if DB port is published) for host bindings."
            ),
        },
        "integration_surface": (
            "Expose API under /api from backend; frontend dev server proxies or uses VITE_* env — document CORS and URLs in README."
        ),
        "verification_commands": [
            "docker compose config",
            "docker compose up -d --build",
            "cd backend && (pytest tests/unit -q || pytest -q -m unit || python -m pytest tests/unit -q)",
            "cd backend && (pytest tests/integration -q || pytest -q -m integration || python -m pytest tests/integration -q)",
            "cd frontend && (npm run build || true)",
            "cd frontend && (npm run test:e2e --if-present || npx playwright test --pass-with-no-tests || true)",
        ],
        "testing_contract": {
            "layers_ordered": ["component_unit", "functional_integration", "ui_e2e"],
            "execution_note": (
                "Strict order: component/unit tests first, then functional/integration (API+DB), then UI e2e last."
            ),
        },
        "forbidden_shortcuts": [
            "Delivering only static index.html at repo root when runnable_services lists an API server.",
            "Listing Elasticsearch/K8s/RabbitMQ in tech_stack without a minimal runnable substitute or docker-compose service.",
        ],
    }
    logger.info(
        "implementation_contract synthesized from tech_stack for full_software build (Architect fallback)"
    )
    _ensure_docker_compose_contract_fields(arch, spec, landing_charter=landing_charter)
    _ensure_testing_contract_fields(arch, spec, landing_charter=landing_charter)
    _ensure_github_house_layout(arch, spec, landing_charter=landing_charter)

