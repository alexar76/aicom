"""Deleting the call is the cheapest way to satisfy a finding about that call.

Watched live, over three rounds. The advisory endpoint called `atlas.get_advisory(...)`, a method
AtlasClient never declared, so every request answered 500 and the finding kept coming back. Then a
round found the cheap way out:

    return construct_unknown_advisory("ATLAS sensor mesh integration pending", lat, lon)

The AttributeError was gone. The 500 was gone. module_health got happier. And Sentinel — whose entire
premise is "it reasons by invoking the ATLAS sensor-mesh capabilities over the AI-market protocol" —
stopped asking anything at all. A product that answers UNKNOWN without a question is a placeholder
with a landing page, and every gate approved of it.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_capabilities_never_invoked

CLIENT = '''import httpx

SITUATION_BRIEF = "atlas.situation.brief@v1"


class AtlasClient:
    FIRE_WEATHER = "atlas.fire.weather@v1"

    async def get_situation_brief(self, lat, lon):
        return {}
'''


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_a_hollowed_out_endpoint_is_reported(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": CLIENT,
            "backend/app/routers/advisory.py": (
                "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n"
                '@router.get("/advisory")\n'
                'async def advisory():\n    return {"level": "UNKNOWN", "reason": "pending"}\n'
            ),
        },
    )
    found = find_capabilities_never_invoked(code)
    assert len(found) == 1
    assert found[0]["file"].endswith("atlas_client.py")
    assert "atlas.situation.brief@v1" in found[0]["capabilities"]
    assert "NO request handler constructs AtlasClient" in found[0]["detail"]
    assert "Deleting a call is the cheapest way" in found[0]["detail"]


def test_a_handler_that_uses_the_client_is_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": CLIENT,
            "backend/app/routers/advisory.py": (
                "from fastapi import APIRouter\n"
                "from ..services.atlas_client import AtlasClient\n\n"
                "router = APIRouter()\n\n\n"
                '@router.get("/advisory")\n'
                "async def advisory():\n"
                "    atlas = AtlasClient()\n"
                "    return await atlas.get_situation_brief(1, 2)\n"
            ),
        },
    )
    assert find_capabilities_never_invoked(code) == []


def test_a_product_with_no_capabilities_is_silent(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/routers/x.py": 'router = APIRouter()\n\n\n@router.get("/x")\ndef x():\n    return {}\n'},
    )
    assert find_capabilities_never_invoked(code) == []


def test_tests_do_not_count_as_a_request_path(tmp_path):
    """A unit test exercising the client is not the product serving it."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": CLIENT,
            "backend/app/routers/advisory.py": (
                'router = APIRouter()\n\n\n@router.get("/advisory")\ndef advisory():\n    return {}\n'
            ),
            "backend/tests/unit/test_atlas.py": "from app.services.atlas_client import AtlasClient\n\n\ndef test_x():\n    AtlasClient()\n",
        },
    )
    assert len(find_capabilities_never_invoked(code)) == 1


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not hollow" in passed
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "find_capabilities_never_invoked(code_root, limit=200)" in score
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"capability_never_invoked"' in qa[: qa.index("# Deletions next")]
