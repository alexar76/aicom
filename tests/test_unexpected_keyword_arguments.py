"""Call-site kwargs the method does not declare.

The live Sentinel deploy answered 200 UNKNOWN because advisory.py called
`get_situation_brief(west=..., east=...)` while AtlasClient declares `(self, lat, lon)`.
missing_attribute is silent — the method exists. The honesty policy turned TypeError into
a truthful-looking UNKNOWN.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_unexpected_keyword_arguments


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_sentinel_west_kwarg_is_reported(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": (
                "class AtlasClient:\n"
                "    async def get_situation_brief(self, lat, lon):\n"
                "        return {}\n"
            ),
            "backend/app/routers/advisory.py": (
                "from ..services.atlas_client import AtlasClient\n\n\n"
                "async def get_advisory():\n"
                "    atlas = AtlasClient()\n"
                "    return await atlas.get_situation_brief(west=1, east=2, south=3, north=4)\n"
            ),
        },
    )
    found = find_unexpected_keyword_arguments(code)
    assert found, "the west= call must be a critical"
    assert any(f.get("keyword") == "west" for f in found)
    detail = found[0]["detail"]
    assert "get_situation_brief" in detail
    assert "advisory.py" in detail and "atlas_client.py" in detail
    assert "Do NOT swallow TypeError" in detail
    assert found[0]["file"].endswith("advisory.py")


def test_a_matching_call_is_silent(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": (
                "class AtlasClient:\n"
                "    async def get_situation_brief(self, lat, lon):\n"
                "        return {}\n"
            ),
            "backend/app/routers/advisory.py": (
                "from ..services.atlas_client import AtlasClient\n\n\n"
                "async def get_advisory():\n"
                "    atlas = AtlasClient()\n"
                "    return await atlas.get_situation_brief(lat=1, lon=2)\n"
            ),
        },
    )
    assert find_unexpected_keyword_arguments(code) == []


def test_kwargs_on_the_method_is_unanalysable(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "svc.py": "class Svc:\n    def go(self, **kwargs):\n        return kwargs\n",
            "use.py": (
                "from svc import Svc\n\n"
                "s = Svc()\n"
                "s.go(west=1)\n"
            ),
        },
    )
    assert find_unexpected_keyword_arguments(code) == []
