"""A route handler FastAPI cannot call is invisible to every other static check.

The tree imports cleanly. Every symbol resolves. The frontend builds. And the endpoint returns
500 on every single request. A weather product carried exactly this for roughly ninety
developer/QA rounds:

    @router.get("", response_model=AdvisoryResponse)
    @rate_limited(max_calls=..., period=60)
    async def get_advisory(lat=Query(...), lon=Query(...), db=Depends(get_db)):

    def rate_limited(...):
        def decorator(func):
            @wraps(func)
            async def wrapper(request: Request, *args, **kwargs):
                return await func(request, *args, **kwargs)

``@wraps`` sets ``__wrapped__``, so FastAPI's ``inspect.signature`` follows it to the handler,
sees no ``request``, and never supplies one — then calls the wrapper, which requires it
positionally:

    TypeError: get_advisory() missing 1 required positional argument: 'request'

The error names the *handler* because ``@wraps`` copied ``__name__``, which sends whoever reads
it to the wrong function. And had FastAPI supplied the request, ``func(request, ...)`` would
have passed it into ``lat``.

The detector resolves the decorator rather than flagging every decorated route, because most
decorators are harmless and a gate that cries wolf gets switched off. Only a wrapper that
demands a parameter the handler does not declare can break the call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import (
    find_route_handlers_with_broken_injection,
)

BROKEN_DECORATOR = '''
from functools import wraps
from fastapi import Request

def rate_limited(max_calls: int, period: int = 60):
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
'''

HARMLESS_DECORATOR = '''
from functools import wraps

def audited(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    return wrapper
'''


def _tree(root: Path, router_src: str, util_src: str = BROKEN_DECORATOR) -> Path:
    code = root / "code" / "prod-x"
    (code / "backend" / "app" / "routers").mkdir(parents=True, exist_ok=True)
    (code / "backend" / "app" / "utils").mkdir(parents=True, exist_ok=True)
    (code / "backend" / "app" / "utils" / "rate_limit.py").write_text(util_src, encoding="utf-8")
    (code / "backend" / "app" / "routers" / "advisory.py").write_text(router_src, encoding="utf-8")
    return code


def test_the_real_shape_is_caught(tmp_path):
    code = _tree(tmp_path, '''
from fastapi import APIRouter, Query, Depends
from app.utils.rate_limit import rate_limited

router = APIRouter(prefix="/advisory")

@router.get("", response_model=dict)
@rate_limited(max_calls=30, period=60)
async def get_advisory(lat: float = Query(...), lon: float = Query(...)):
    return {"lat": lat, "lon": lon}
''')
    found = find_route_handlers_with_broken_injection(code)
    assert len(found) == 1, found
    assert found[0]["handler"] == "get_advisory"
    assert found[0]["decorator"] == "rate_limited"
    assert "request" in found[0]["detail"]
    # The slowapi branch predicts a BOOT failure, not a per-call TypeError: slowapi
    # raises `No "request" or "websocket" argument on function "..."` while the module
    # is importing, so the whole app is dead. These assertions named the generic
    # branch's wording ("TypeError", "Fix by declaring") and went stale the moment the
    # detector learned the difference — a gate whose test pins prose nobody reads.
    assert 'No "request" or "websocket" argument' in found[0]["detail"], (
        "the detail must name the failure it predicts"
    )
    assert "import time" in found[0]["detail"], "and say that it is boot-fatal, not per-call"
    assert "must declare `request: Request`" in found[0]["detail"], (
        "a finding without a remedy is a nag"
    )
    assert "do not remove the decorator" in found[0]["detail"], (
        "the tempting wrong fix must be named as wrong, or that is what the round will do"
    )


def test_a_handler_that_declares_the_parameter_is_fine(tmp_path):
    """The fix must read as fixed, or the next round is told to repair working code."""
    code = _tree(tmp_path, '''
from fastapi import APIRouter, Query, Request
from app.utils.rate_limit import rate_limited

router = APIRouter()

@router.get("/advisory")
@rate_limited(max_calls=30, period=60)
async def get_advisory(request: Request, lat: float = Query(...)):
    return {"lat": lat}
''')
    assert find_route_handlers_with_broken_injection(code) == []


def test_a_wrapper_taking_only_varargs_is_not_flagged(tmp_path):
    """The common, correct decorator shape must not be reported."""
    code = _tree(tmp_path, '''
from fastapi import APIRouter, Query
from app.utils.rate_limit import audited

router = APIRouter()

@router.get("/advisory")
@audited
async def get_advisory(lat: float = Query(...)):
    return {"lat": lat}
''', util_src=HARMLESS_DECORATOR)
    assert find_route_handlers_with_broken_injection(code) == []


def test_an_undecorated_route_is_not_flagged(tmp_path):
    code = _tree(tmp_path, '''
from fastapi import APIRouter, Query

router = APIRouter()

@router.get("/advisory")
async def get_advisory(lat: float = Query(...)):
    return {"lat": lat}
''')
    assert find_route_handlers_with_broken_injection(code) == []


def test_a_plain_decorated_function_is_not_a_route(tmp_path):
    """Only handlers reachable over HTTP matter; a decorated helper is nobody's business."""
    code = _tree(tmp_path, '''
from app.utils.rate_limit import rate_limited

@rate_limited(max_calls=5)
async def helper(x: int):
    return x
''')
    assert find_route_handlers_with_broken_injection(code) == []


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
def test_every_http_method_is_covered(tmp_path, method):
    code = _tree(tmp_path, f'''
from fastapi import APIRouter, Query
from app.utils.rate_limit import rate_limited

router = APIRouter()

@router.{method}("/advisory")
@rate_limited(max_calls=30)
async def handler(lat: float = Query(...)):
    return {{}}
''')
    assert len(find_route_handlers_with_broken_injection(code)) == 1, method


def test_an_unresolvable_decorator_is_not_guessed_about(tmp_path):
    """A decorator imported from a library cannot be inspected, so it must not be flagged.

    Guessing here would fire on every third-party decorator in the ecosystem.
    """
    code = _tree(tmp_path, '''
from fastapi import APIRouter, Query
from some_library import magic

router = APIRouter()

@router.get("/advisory")
@magic(option=1)
async def get_advisory(lat: float = Query(...)):
    return {"lat": lat}
''')
    assert find_route_handlers_with_broken_injection(code) == []


def test_it_reaches_the_module_health_gate_and_the_round_score():
    """Structural: a detector nothing consumes changes nothing."""
    root = Path(__file__).resolve().parents[1]
    dmc = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "route_handler_broken_injection" in dmc, "not reported as an issue"
    assert '"severity": "critical"' in dmc.split("route_handler_broken_injection")[1][:200]
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "find_route_handlers_with_broken_injection(code_root)" in dev, (
        "the round-regression guard cannot see this defect, so a round that introduces one "
        "still reads as an improvement"
    )


def test_the_finding_blocks_the_gate(tmp_path, monkeypatch):
    """Reported-but-passing makes it one line in a list the round may ignore.

    This class costs a 500 on every request to the endpoint. A product whose only feature is
    that endpoint is dead while the gate is green, so blocking is what turns the finding into
    the round's work rather than a note.
    """
    from web.backend.services.duplicate_module_check import run_duplicate_module_check

    code = _tree(tmp_path, '''
from fastapi import APIRouter, Query
from app.utils.rate_limit import rate_limited

router = APIRouter()

@router.get("/advisory")
@rate_limited(max_calls=30, period=60)
async def get_advisory(lat: float = Query(...)):
    return {"lat": lat}
''')
    monkeypatch.setattr(
        "core.paths.code_dir", lambda pid, data_root=None: code, raising=False
    )
    result = run_duplicate_module_check("prod-x", data_root=tmp_path)
    codes = [i.get("code") for i in result.get("issues") or []]
    assert "route_handler_broken_injection" in codes, result
    assert result["passed"] is False, "a dead endpoint must fail the gate, not merely warn"


# --- the second member of the same family: invisible until the app boots ---------------

DUP_MODEL_A = '''
from sqlalchemy import Column, Integer
from app.db import Base

class InvokeAuditLog(Base):
    __tablename__ = "invoke_audit_logs"
    id = Column(Integer, primary_key=True)
'''

DUP_MODEL_B = '''
from sqlalchemy import Column, Integer, String
from app.db import Base

class InvokeAuditLog(Base):
    __tablename__ = "invoke_audit_logs"
    id = Column(Integer, primary_key=True)
    note = Column(String)
'''


def _models(root: Path, *sources: str) -> Path:
    code = root / "code" / "prod-x"
    (code / "backend" / "app" / "models").mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(sources):
        (code / "backend" / "app" / "models" / f"m{i}.py").write_text(src, encoding="utf-8")
    return code


def test_two_models_on_one_table_are_caught(tmp_path):
    """A boot-blocker no import check sees: each module is fine on its own.

    Found after the route handler was fixed — a round had rewritten models/advisory.py and
    inlined copies of models already living in models/audit.py, three collisions at once. The
    endpoint that had just been repaired was unreachable because nothing started.
    """
    from web.backend.services.duplicate_module_check import find_duplicate_tablenames

    found = find_duplicate_tablenames(_models(tmp_path, DUP_MODEL_A, DUP_MODEL_B))
    assert len(found) == 1, found
    assert found[0]["table"] == "invoke_audit_logs"
    assert len(found[0]["models"]) == 2
    assert "InvalidRequestError" in found[0]["detail"], "name the failure it predicts"
    # The remedy is now specific — "KEEP the declaration in <file> and DELETE <model>
    # from <file>" — rather than the old, unactionable "delete the other".
    detail = found[0]["detail"]
    assert "KEEP the declaration in" in detail, "a finding without a remedy is a nag"
    assert "DELETE" in detail and "re-pointing whatever imported it at" in detail, detail
    assert "extend_existing=True" in found[0]["detail"], (
        "the tempting wrong fix must be named as wrong, or that is what the round will do"
    )


def test_one_model_per_table_is_fine(tmp_path):
    from web.backend.services.duplicate_module_check import find_duplicate_tablenames

    other = DUP_MODEL_B.replace("invoke_audit_logs", "heartbeat_logs").replace(
        "InvokeAuditLog", "HeartbeatLog"
    )
    assert find_duplicate_tablenames(_models(tmp_path, DUP_MODEL_A, other)) == []


def test_extend_existing_is_a_deliberate_redefinition(tmp_path):
    """Declared intent must not be reported, or the gate blocks a legitimate pattern."""
    from web.backend.services.duplicate_module_check import find_duplicate_tablenames

    deliberate = '''
from sqlalchemy import Column, Integer
from app.db import Base

class InvokeAuditLogExtra(Base):
    __tablename__ = "invoke_audit_logs"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True)
'''
    assert find_duplicate_tablenames(_models(tmp_path, DUP_MODEL_A, deliberate)) == []


def test_a_duplicate_table_blocks_the_gate_and_the_score():
    """Structural: reported-but-passing leaves the app unbootable with a green gate."""
    root = Path(__file__).resolve().parents[1]
    dmc = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "duplicate_tablename" in dmc
    assert "not dup_tables" in dmc, "the verdict ignores it"
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "find_duplicate_tablenames(code_root)" in dev, (
        "a round that introduces one would still read as an improvement"
    )


# --- third member of the family: the product miscalls our own economy -------------------

MESH_CLIENT = '''
import httpx
from app.config import settings

class AtlasClient:
    def __init__(self):
        self.invoke_url = "https://atlas.modelmarket.dev/ai-market/v2/invoke"

    async def _invoke(self, capability, payload):
        data = {
            "capability": capability,
            "payload": payload
        }
        async with httpx.AsyncClient() as c:
            return await c.post(self.invoke_url, json=data)

    async def invoke_situation(self, lat, lon):
        payload = {"bbox": [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]}
        return await self._invoke("atlas.situation.brief@v1", payload)
'''


def test_the_wrong_envelope_is_caught_without_the_network(tmp_path):
    """Envelope keys are checkable offline, so this finding never depends on reachability."""
    from web.backend.services.duplicate_module_check import find_mesh_contract_violations

    code = tmp_path / "code" / "prod-x" / "backend" / "app" / "services"
    code.mkdir(parents=True)
    (code / "atlas_client.py").write_text(MESH_CLIENT, encoding="utf-8")
    root = tmp_path / "code" / "prod-x"

    found = find_mesh_contract_violations(root)
    envelope = [f for f in found if f["kind"] == "envelope"]
    assert envelope, found
    assert "capability_id" in envelope[0]["detail"]
    assert "input" in envelope[0]["detail"]
    assert "answers" in envelope[0]["detail"] and "200" in envelope[0]["detail"], (
        "the detail must say why this hides: the app still answers 200 with no data"
    )


def test_a_correct_envelope_is_not_flagged(tmp_path):
    from web.backend.services.duplicate_module_check import find_mesh_contract_violations

    code = tmp_path / "code" / "prod-x" / "backend"
    code.mkdir(parents=True)
    (code / "client.py").write_text('''
data = {"capability_id": "atlas.situation.brief@v1", "input": {"west": 1}}
''', encoding="utf-8")
    found = find_mesh_contract_violations(tmp_path / "code" / "prod-x")
    assert [f for f in found if f["kind"] == "envelope"] == []


def test_an_unreachable_manifest_means_no_opinion(tmp_path, monkeypatch):
    """A network problem must never fail someone's build."""
    import web.backend.services.duplicate_module_check as dmc

    monkeypatch.setattr(dmc, "_fetch_manifest_schemas", lambda bases: {})
    code = tmp_path / "code" / "prod-x" / "backend"
    code.mkdir(parents=True)
    (code / "client.py").write_text('''
payload = {"bbox": [1, 2, 3, 4]}
cap = "atlas.situation.brief@v1"
''', encoding="utf-8")
    found = dmc.find_mesh_contract_violations(tmp_path / "code" / "prod-x")
    assert [f for f in found if f["kind"] == "input_schema"] == []


def test_input_mismatches_are_reported_once_per_capability(tmp_path, monkeypatch):
    """Six findings for three defects teaches people to skim the list."""
    import web.backend.services.duplicate_module_check as dmc

    monkeypatch.setattr(
        dmc, "_fetch_manifest_schemas",
        lambda bases: {
            "atlas.situation.brief@v1": {
                "required": ["west", "south", "east", "north"],
                "properties": {k: {} for k in ("west", "south", "east", "north", "layers")},
            }
        },
    )
    code = tmp_path / "code" / "prod-x" / "backend"
    code.mkdir(parents=True)
    (code / "client.py").write_text('''
class C:
    async def a(self, lat, lon):
        payload = {"bbox": [1, 2, 3, 4]}
        return await self._invoke("atlas.situation.brief@v1", payload)

COSTS = {"atlas.situation.brief@v1": 0.06}
''', encoding="utf-8")
    found = [f for f in dmc.find_mesh_contract_violations(tmp_path / "code" / "prod-x")
             if f["kind"] == "input_schema"]
    assert len(found) == 1, found
    assert "west" in found[0]["detail"] and "bbox" in found[0]["detail"]


def test_top_level_async_def_does_not_inherit_a_sibling_items_key(tmp_path, monkeypatch):
    """Relay: previous handler returns ``{"items": ...}``; advisory is module-level ``async def``.

    The input-schema window used to start at the earlier ``def``, so ``items`` was
    attributed to ``atlas.situation.brief@v1`` even though advisory only sends the bbox.
    """
    import web.backend.services.duplicate_module_check as dmc

    monkeypatch.setattr(
        dmc,
        "_fetch_manifest_schemas",
        lambda bases: {
            "atlas.situation.brief@v1": {
                "required": ["west", "south", "east", "north"],
                "properties": {
                    k: {} for k in ("west", "south", "east", "north", "layers", "locale", "max_citations")
                },
            }
        },
    )
    code = tmp_path / "code" / "prod-x" / "backend" / "app" / "routers"
    code.mkdir(parents=True)
    (code / "handoffs.py").write_text(
        '''
def list_audit_route():
    return {"items": serialize_audit(entries, email_by_id)}


@router.post("/advisory")
async def advisory():
    input_data = {"east": 1, "north": 2, "south": 3, "west": 4}
    return participant.invoke("atlas.situation.brief@v1", input_data)
''',
        encoding="utf-8",
    )
    found = [
        f
        for f in dmc.find_mesh_contract_violations(tmp_path / "code" / "prod-x")
        if f["kind"] == "input_schema"
    ]
    assert found == [], found


def test_a_registry_heartbeat_is_not_an_invoke(tmp_path, monkeypatch):
    """SKU strings in capabilities_used are advertising, not atlas.situation.brief input."""
    import web.backend.services.duplicate_module_check as dmc

    monkeypatch.setattr(
        dmc,
        "_fetch_manifest_schemas",
        lambda bases: {
            "atlas.situation.brief@v1": {
                "required": ["west", "south", "east", "north"],
                "properties": {k: {} for k in ("west", "south", "east", "north", "layers")},
            },
            "atlas.fire.weather@v1": {
                "required": [],
                "properties": {"north": {}, "south": {}, "east": {}, "west": {}},
            },
            "atlas.nearest.read@v1": {
                "required": ["lat", "lon"],
                "properties": {"lat": {}, "lon": {}, "layers": {}},
            },
        },
    )
    code = tmp_path / "code" / "prod-x" / "backend" / "app" / "services"
    code.mkdir(parents=True)
    (code / "heartbeat.py").write_text(
        '''
async def send_heartbeat():
    payload = {
        "agent_id": "x",
        "name": "Sentinel",
        "product_id": "p",
        "sdk": "aimarket-agent",
        "capabilities_used": [
            "atlas.situation.brief@v1",
            "atlas.fire.weather@v1",
            "atlas.nearest.read@v1",
        ],
    }
    await client.post("/api/agents/heartbeat", json=payload)
''',
        encoding="utf-8",
    )
    (code / "atlas_client.py").write_text(
        '''
class AtlasClient:
    async def invoke_situation_brief(self, lat, lon):
        return await self._invoke(
            "atlas.situation.brief@v1",
            {"north": lat, "south": lat, "east": lon, "west": lon, "layers": ["flood"]},
        )
''',
        encoding="utf-8",
    )
    found = [
        f
        for f in dmc.find_mesh_contract_violations(tmp_path / "code" / "prod-x")
        if f["kind"] == "input_schema"
    ]
    assert found == [], found


def test_the_mesh_finding_blocks_and_is_scored():
    root = Path(__file__).resolve().parents[1]
    dmc = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "mesh_contract_violation" in dmc
    assert "mesh_participant_violation" in dmc
    assert "not mesh_contract" in dmc, "the verdict ignores it"
    assert "not mesh_participant" in dmc
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "find_mesh_contract_violations(code_root)" in dev
    assert "find_mesh_participant_violations(code_root)" in dev


def test_mesh_participant_flags_agent_key_only_client(tmp_path):
    from web.backend.services.duplicate_module_check import find_mesh_participant_violations

    code = tmp_path / "code" / "prod-x" / "backend" / "app" / "services"
    code.mkdir(parents=True)
    (code / "atlas_client.py").write_text(
        '''
import httpx
class AtlasClient:
    async def _invoke(self, capability_id, input_data):
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.base_url}/aimarket/invoke",
                json={"capability_id": capability_id, "input": input_data},
                headers={"X-Agent-Key": self.agent_key},
            )
    async def brief(self):
        return await self._invoke("atlas.situation.brief@v1", {"west": 1})
''',
        encoding="utf-8",
    )
    found = find_mesh_participant_violations(tmp_path / "code" / "prod-x")
    kinds = {f["kind"] for f in found}
    assert "legacy_invoke_path" in kinds
    assert "missing_participant_headers" in kinds


def test_mesh_participant_accepts_visitor_or_channel(tmp_path):
    from web.backend.services.duplicate_module_check import find_mesh_participant_violations

    code = tmp_path / "code" / "prod-x" / "backend"
    code.mkdir(parents=True)
    (code / "client.py").write_text(
        '''
import httpx, os
async def call():
    h = {"X-AIMarket-Sandbox-Visitor": os.environ["AIMARKET_SANDBOX_VISITOR"]}
    await httpx.AsyncClient().post(
        "https://modelmarket.dev/ai-market/v2/invoke",
        json={"capability_id": "atlas.situation.brief@v1", "input": {"west": 1}},
        headers=h,
    )
''',
        encoding="utf-8",
    )
    assert find_mesh_participant_violations(tmp_path / "code" / "prod-x") == []
