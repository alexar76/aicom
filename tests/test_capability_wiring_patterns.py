"""A detector that cannot see the idiomatic fix undoes every correct round.

Sentinel (prod-bdb1634806de) sat on one blocking finding for twelve days:
`capability_never_invoked` on `aimarket_participant.py`. The developer eventually wired the
advisory endpoint correctly — `participant = get_participant()` and three `.invoke(...)` calls —
but the constructor had moved inside `get_participant`, and this check only ever looked for a
direct `AimarketParticipant(` in a router file. So:

  * the critical finding survived a round that had actually fixed it;
  * the round therefore removed no defects while its own transient ones added
    (`api_route_shadows_spa`, `missing_symbol` — the latter weighs 10);
  * the salvage step read that as a pure regression and gave the file back.

Every correct fix was undone by a detector that could not recognise it. Reproduced on a synthetic
four-file tree, which is what the first test below is.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from web.backend.services.duplicate_module_check import find_capabilities_never_invoked

HOLDER_WITH_FACTORY = '''
CAPS = ["atlas.situation.brief@v1"]


class AimarketParticipant:
    def invoke(self, cap, payload): ...


_default = None


def get_participant():
    global _default
    if _default is None:
        _default = AimarketParticipant()
    return _default
'''

HOLDER_PLAIN = '''
CAPS = ["atlas.situation.brief@v1"]


class AimarketParticipant:
    def invoke(self, cap, payload): ...
'''


def _tree(tmp_path: Path, holder: str, router: str) -> Path:
    (tmp_path / "services").mkdir(parents=True, exist_ok=True)
    (tmp_path / "routers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "services" / "participant.py").write_text(textwrap.dedent(holder), encoding="utf-8")
    (tmp_path / "routers" / "advisory.py").write_text(textwrap.dedent(router), encoding="utf-8")
    return tmp_path


ROUTER_VIA_FACTORY = '''
from fastapi import APIRouter
from ..services.participant import get_participant

router = APIRouter(prefix="/api/advisory")


@router.get("")
async def advisory():
    p = get_participant()
    return await p.invoke("atlas.situation.brief@v1", {})
'''

ROUTER_VIA_CONSTRUCTOR = '''
from fastapi import APIRouter
from ..services.participant import AimarketParticipant

router = APIRouter(prefix="/api/advisory")


@router.get("")
async def advisory():
    return await AimarketParticipant().invoke("atlas.situation.brief@v1", {})
'''

ROUTER_PLACEHOLDER = '''
from fastapi import APIRouter

router = APIRouter(prefix="/api/advisory")


@router.get("")
async def advisory():
    # The placeholder that silenced the crash and deleted the product's reason to exist.
    return {"overall": {"level": "UNKNOWN", "reason": "mesh response unavailable"}}
'''


def test_factory_wiring_is_recognised(tmp_path):
    """THE regression. `get_participant()` is the idiomatic wiring and was read as no wiring."""
    tree = _tree(tmp_path, HOLDER_WITH_FACTORY, ROUTER_VIA_FACTORY)
    assert find_capabilities_never_invoked(tree) == []


def test_direct_construction_is_still_recognised(tmp_path):
    tree = _tree(tmp_path, HOLDER_PLAIN, ROUTER_VIA_CONSTRUCTOR)
    assert find_capabilities_never_invoked(tree) == []


def test_a_placeholder_endpoint_is_still_caught(tmp_path):
    """The whole point of the check: an endpoint that answers without invoking anything."""
    tree = _tree(tmp_path, HOLDER_WITH_FACTORY, ROUTER_PLACEHOLDER)
    findings = find_capabilities_never_invoked(tree)
    assert len(findings) == 1
    assert findings[0]["code"] == "capability_never_invoked"
    assert "atlas.situation.brief@v1" in findings[0]["detail"]


def test_an_unrelated_helper_does_not_count_as_wiring(tmp_path):
    """Otherwise the check becomes vacuous: any module-level function in the holder module would
    satisfy it, and a placeholder endpoint calling a logging helper would read as wired."""
    holder = HOLDER_WITH_FACTORY + '''

def describe_capabilities():
    """Touches no holder class — must not count as an entry point."""
    return list(CAPS)
'''
    router = '''
from fastapi import APIRouter
from ..services.participant import describe_capabilities

router = APIRouter(prefix="/api/advisory")


@router.get("")
async def advisory():
    return {"caps": describe_capabilities(), "level": "UNKNOWN"}
'''
    findings = find_capabilities_never_invoked(_tree(tmp_path, holder, router))
    assert len(findings) == 1, "calling a helper that never touches the holder is not wiring"


def test_a_private_accessor_does_not_count(tmp_path):
    """`_get()` is module-internal; a router importing it would be reaching past the API."""
    holder = HOLDER_PLAIN + '''

def _get():
    return AimarketParticipant()
'''
    router = '''
from fastapi import APIRouter
from ..services.participant import _get

router = APIRouter(prefix="/api/advisory")


@router.get("")
async def advisory():
    return await _get().invoke("atlas.situation.brief@v1", {})
'''
    assert len(find_capabilities_never_invoked(_tree(tmp_path, holder, router))) == 1


def test_a_product_with_no_capabilities_is_not_this_checks_business(tmp_path):
    tree = _tree(tmp_path, "class Thing:\n    pass\n", "router = None\n")
    assert find_capabilities_never_invoked(tree) == []
