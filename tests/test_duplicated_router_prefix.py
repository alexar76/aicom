"""A prefix applied twice, and three gates blamed the product for it without naming the cause.

Found on the live product in four of five routers:

    app/routers/advisory.py:9   router = APIRouter(prefix="/api/advisory", tags=["advisory"])
    app/main.py:22              app.include_router(advisory.router, prefix="/api/advisory", …)

FastAPI applies both, so the real path is `/api/advisory/api/advisory/…` and nothing reaches the path
the app documents. What the gates reported instead:

* the seeded demo login POSTed `/api/auth/login`, which did not exist, and the catch-all route answered
  `500` — read as a broken login handler for four rounds;
* the same catch-all swallowed `/`, so the browser crawl saw API JSON where the widget should be;
* `api_contract` reported **agreement**, because the frontend had learned the doubled paths too — the
  right answer to the wrong question, from the one component positioned to catch this first.

Two detections on purpose. The source shape names the line to delete; the effective path catches the
same fault arriving through nested routers or through route paths that already carry the prefix, where
no single line looks wrong. `embed.py` was found only by the second: `APIRouter()` with no prefix at all,
included under `/api`, and its own routes written as `/api/embed.js`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import (
    _repeated_segment_run,
    find_duplicated_router_prefix,
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/auth/api/auth/login", "/api/auth"),
        ("/v1/users/v1/users", "/v1/users"),
        ("/api/api/thing", "/api"),
        # Not repeats: a segment that merely starts with the same letters is a different segment.
        ("/api/api-keys", None),
        ("/api/advisory", None),
        ("/api/v1/users/profile", None),
        ("/", None),
    ],
)
def test_the_segment_run_check_is_exact(path, expected):
    assert _repeated_segment_run(path) == expected


def test_the_live_source_shape_is_found(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/advisory.py": (
                "from fastapi import APIRouter\n"
                'router = APIRouter(prefix="/api/advisory", tags=["advisory"])\n'
                '@router.get("/")\n'
                "def get_advisory():\n    return {}\n"
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\n"
                "from app.routers import advisory\n"
                "app = FastAPI()\n"
                'app.include_router(advisory.router, prefix="/api/advisory", tags=["advisory"])\n'
            ),
        },
    )
    found = find_duplicated_router_prefix(code)
    assert len(found) == 1, found
    assert found[0]["file"] == "backend/app/routers/advisory.py"
    assert found[0]["prefix"] == "/api/advisory"
    assert found[0]["included_in"] == "backend/app/main.py"
    assert found[0]["severity"] == "critical"
    assert "REMOVE THE PREFIX FROM EXACTLY ONE PLACE" in found[0]["detail"]
    assert "500" in found[0]["detail"], "the finding does not connect itself to the symptom"


def test_a_prefix_in_one_place_only_is_fine(tmp_path):
    """Both correct spellings must stay silent, or every product trips this."""
    on_include = _tree(
        tmp_path / "a",
        {
            "backend/app/routers/auth.py": (
                "from fastapi import APIRouter\nrouter = APIRouter()\n"
                '@router.post("/login")\ndef login():\n    return {}\n'
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import auth\napp = FastAPI()\n"
                'app.include_router(auth.router, prefix="/api/auth")\n'
            ),
        },
    )
    assert find_duplicated_router_prefix(on_include) == []

    on_router = _tree(
        tmp_path / "b",
        {
            "backend/app/routers/auth.py": (
                "from fastapi import APIRouter\n"
                'router = APIRouter(prefix="/api/auth")\n'
                '@router.post("/login")\ndef login():\n    return {}\n'
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import auth\napp = FastAPI()\n"
                "app.include_router(auth.router)\n"
            ),
        },
    )
    assert find_duplicated_router_prefix(on_router) == []


def test_different_prefixes_are_not_a_duplicate(tmp_path):
    """`/api` on the include and `/auth` on the router compose correctly."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/auth.py": (
                "from fastapi import APIRouter\n"
                'router = APIRouter(prefix="/auth")\n'
                '@router.post("/login")\ndef login():\n    return {}\n'
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import auth\napp = FastAPI()\n"
                'app.include_router(auth.router, prefix="/api")\n'
            ),
        },
    )
    assert find_duplicated_router_prefix(code) == []


def test_a_route_path_carrying_the_prefix_is_caught_by_the_effective_path(tmp_path):
    """The embed.py shape: no prefix on the router at all, and no single line looks wrong."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/embed.py": (
                "from fastapi import APIRouter\nrouter = APIRouter()\n"
                '@router.get("/api/embed.js")\ndef script():\n    return ""\n'
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import embed\napp = FastAPI()\n"
                'app.include_router(embed.router, prefix="/api")\n'
            ),
        },
    )
    found = find_duplicated_router_prefix(code)
    assert len(found) == 1, found
    assert found[0]["file"] == "backend/app/routers/embed.py"
    assert found[0]["prefix"] == "/api"


def test_one_finding_per_router_not_per_route(tmp_path):
    """A router with nine routes is one defect and one edit."""
    routes = "".join(f'@router.get("/r{i}")\ndef r{i}():\n    return {{}}\n' for i in range(9))
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/ops.py": (
                'from fastapi import APIRouter\nrouter = APIRouter(prefix="/api/ops")\n' + routes
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import ops\napp = FastAPI()\n"
                'app.include_router(ops.router, prefix="/api/ops")\n'
            ),
        },
    )
    assert len(find_duplicated_router_prefix(code)) == 1


def test_a_product_with_no_backend_is_silent(tmp_path):
    code = _tree(tmp_path / "code", {"frontend/src/App.tsx": "export const App = () => null\n"})
    assert find_duplicated_router_prefix(code) == []


def test_it_is_wired_into_gate_score_and_blocking_list():
    root = Path(__file__).resolve().parents[1]

    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "double_prefix = find_duplicated_router_prefix(code_dir)" in check
    # The property, not the punctuation — the same trap this suite already documents once: asserting
    # the trailing comma breaks the moment a term is appended after it.
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not double_prefix" in passed_expr, "a critical that does not fail its own gate"

    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "5 * len(find_duplicated_router_prefix(code_root, limit=200))" in score, (
        "the round guard cannot see it, so a round that fixes it scores no improvement"
    )
    breakdown = dev[dev.index("def _tree_defect_breakdown(") : dev.index("def _breakdown_delta(")]
    assert '"duplicated_router_prefix"' in breakdown, "a rejection could not name this class"

    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    head = qa[: qa.index("# Deletions next")]
    assert '"duplicated_router_prefix"' in head


def test_the_finding_says_the_path_must_not_change(tmp_path):
    """The first wording said "delete it from one of the two" and a round deleted it from both.

    That silences the finding and moves every route to the root, which breaks the API just as
    thoroughly — and it happened: the login endpoint ended up at `/login` instead of
    `/api/auth/login`, `api_contract` went green because the frontend followed it there, and the
    detector had nothing left to report. A fix that satisfies the checker by removing the feature is
    the failure mode every instruction here has to close by naming the intended outcome, not the edit.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/auth.py": (
                "from fastapi import APIRouter\n"
                'router = APIRouter(prefix="/api/auth")\n'
                '@router.post("/login")\ndef login():\n    return {}\n'
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import auth\napp = FastAPI()\n"
                'app.include_router(auth.router, prefix="/api/auth")\n'
            ),
        },
    )
    detail = find_duplicated_router_prefix(code)[0]["detail"]
    assert "EXACTLY ONE PLACE" in detail
    assert '"/api/auth/…"' in detail, "the intended served path is not stated"
    assert "Removing it from both" in detail
    assert "/login" in detail and "/api/auth/login" in detail, (
        "the finding does not carry the measured consequence of over-correcting"
    )


def test_the_effective_path_finding_states_the_target_too(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/embed.py": (
                "from fastapi import APIRouter\nrouter = APIRouter()\n"
                '@router.get("/api/embed.js")\ndef script():\n    return ""\n'
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\nfrom app.routers import embed\napp = FastAPI()\n"
                'app.include_router(embed.router, prefix="/api")\n'
            ),
        },
    )
    detail = find_duplicated_router_prefix(code)[0]["detail"]
    assert "ONE place only" in detail
    assert '"/api/embed.js"' in detail, "the corrected path is not spelled out"
    assert "Do not remove it from both" in detail


def test_a_prefix_passed_as_a_settings_attribute_is_resolved(tmp_path):
    """The live shape that defeated both earlier halves of this detector.

    No single line looks wrong: the routers declare no prefix, the include has one, the decorators
    carry full paths. Only the combination is visible — and it put every route at /api/api/…, so the
    demo journey POSTed /api/api/auth/login, advisory answered 500, and the entire frontend talked to
    paths that did not exist while api_contract reported agreement.
    """
    code = tmp_path / "code"
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "config.py").write_text(
        'class Settings:\n    api_prefix: str = "/api"\n', encoding="utf-8"
    )
    (code / "backend" / "app" / "main.py").write_text(
        "from app.routers import auth\n"
        "app.include_router(auth.router, prefix=settings.api_prefix)\n",
        encoding="utf-8",
    )
    (code / "backend" / "app" / "routers" / "auth.py").write_text(
        'router = APIRouter()\n\n\n@router.post("/api/auth/login")\ndef login():\n    return {}\n',
        encoding="utf-8",
    )
    found = find_duplicated_router_prefix(code)
    assert len(found) == 1, [f["file"] for f in found]
    detail = found[0]["detail"]
    assert '/api/api/auth/login' in detail, detail
    assert "in ONE place" in detail
    assert "never both" in detail, "removing it twice moves every route to the root"


def test_a_route_that_does_not_repeat_the_prefix_is_fine(tmp_path):
    code = tmp_path / "code"
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "config.py").write_text(
        'class Settings:\n    api_prefix: str = "/api"\n', encoding="utf-8"
    )
    (code / "backend" / "app" / "main.py").write_text(
        "app.include_router(auth.router, prefix=settings.api_prefix)\n", encoding="utf-8"
    )
    (code / "backend" / "app" / "routers" / "auth.py").write_text(
        'router = APIRouter()\n\n\n@router.post("/auth/login")\ndef login():\n    return {}\n',
        encoding="utf-8",
    )
    assert find_duplicated_router_prefix(code) == []
