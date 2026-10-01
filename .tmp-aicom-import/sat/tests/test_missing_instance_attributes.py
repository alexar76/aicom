"""The same blind spot as missing symbols, one level further in: the instance.

    app/config.py:  class Settings(BaseSettings):   # 19 fields, none of them cors_origins
                    settings = Settings()
    app/main.py:19: allow_origins=settings.cors_origins

``AttributeError: 'Settings' object has no attribute 'cors_origins'`` before the first route is
registered, so the app never starts and every endpoint is unreachable. Nothing static had an
opinion: the module imports cleanly, every name resolves, the class exists. It reached the repair
round only as a uvicorn traceback in the demo-journey log.

The same pass found the reason the product's only feature returned no data:

    app/services/atlas_client.py:  def invoke_capability(self, capability_id, input_data)
    app/routers/advisory.py:53:    brief = await atlas_client.invoke("atlas.situation.brief@v1", …)

Three call sites for a method the class does not have, inside a `try/except Exception` that turns
every AttributeError into ``{"level": "UNKNOWN"}`` — the endpoint answers 200 forever and the honesty
policy makes the bug look like a truthful answer.

Precision matters more than reach here, because this reports ``critical`` and criticals decide
whether a round's work is kept. The first version defaulted "class not found" to "declares nothing"
and produced fourteen false criticals in one pass — ``app.get``, ``client.post``,
``pwd_context.hash`` — every one of them a library object we do not own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import find_missing_instance_attributes


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


SETTINGS = (
    "from pydantic_settings import BaseSettings\n\n"
    "class Settings(BaseSettings):\n"
    '    app_name: str = "Sentinel"\n'
    '    api_prefix: str = "/api"\n'
    "    class Config:\n"
    '        extra = "ignore"\n\n'
    "settings = Settings()\n"
)


def test_the_live_import_time_crash_is_reported(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS,
            "backend/app/main.py": (
                "from .config import settings\n\n"
                "app_name = settings.app_name\n"
                "origins = settings.cors_origins\n"
            ),
        },
    )
    found = {f"{i['singleton']}.{i['attribute']}" for i in find_missing_instance_attributes(code)}
    assert found == {"settings.cors_origins"}, found


def test_a_pydantic_base_does_not_make_the_class_opaque(tmp_path):
    """The first version was silent on the exact case it was written for.

    `BaseSettings` is third-party, and "unknown base -> unanalysable" swallowed it. But pydantic's
    fields *are* the class body, so a BaseSettings subclass is as readable as one with no base.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS,
            "backend/app/main.py": "from .config import settings\nx = settings.nope\n",
        },
    )
    assert [i["attribute"] for i in find_missing_instance_attributes(code)] == ["nope"]


def test_library_objects_are_never_accused(tmp_path):
    """One wrong default produced fourteen false criticals in a single pass."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": (
                "from fastapi import FastAPI\n"
                "from passlib.context import CryptContext\n\n"
                "app = FastAPI()\n"
                'pwd_context = CryptContext(schemes=["bcrypt"])\n'
                "app.include_router(None)\n"
                "app.state.thing = 1\n"
                'h = pwd_context.hash("x")\n'
            )
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_a_short_alias_for_a_longer_method_is_suggested(tmp_path):
    """`invoke` against `invoke_capability` scores below any sane difflib cutoff."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": (
                "class AtlasClient:\n"
                "    def invoke_capability(self, capability_id, input_data):\n"
                "        return {}\n"
            ),
            "backend/app/routers/advisory.py": (
                "from ..services.atlas_client import AtlasClient\n\n"
                "atlas_client = AtlasClient()\n"
                'brief = atlas_client.invoke("atlas.situation.brief@v1")\n'
            ),
        },
    )
    finding = find_missing_instance_attributes(code)[0]
    assert finding["attribute"] == "invoke"
    assert finding["did_you_mean"] == ["invoke_capability"], finding
    assert finding["file"] == "backend/app/services/atlas_client.py"
    assert "backend/app/routers/advisory.py:4" in finding["detail"]


def test_a_class_that_synthesises_attributes_is_left_alone(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/dyn.py": (
                "class Bag:\n"
                "    def __getattr__(self, name):\n"
                "        return name\n\n"
                "bag = Bag()\n"
                "x = bag.anything\n"
            )
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_pydantic_extra_allow_is_left_alone(tmp_path):
    """With extras allowed the read may legitimately succeed."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS.replace('extra = "ignore"', 'extra = "allow"'),
            "backend/app/main.py": "from .config import settings\nx = settings.whatever\n",
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_an_attribute_assigned_somewhere_counts_as_declared(tmp_path):
    """`settings.runtime_flag = True` at startup is unusual but legal."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS,
            "backend/app/boot.py": "from .config import settings\nsettings.runtime_flag = True\n",
            "backend/app/main.py": "from .config import settings\nx = settings.runtime_flag\n",
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_the_inherited_api_is_not_a_finding(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS,
            "backend/app/main.py": (
                "from .config import settings\n"
                "d = settings.model_dump()\n"
                "f = settings.model_fields\n"
                "j = settings.dict()\n"
            ),
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_a_singleton_out_of_scope_is_not_attributed(tmp_path):
    """A local `settings` in another module is a different object."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS,
            "backend/app/other.py": "settings = object()\nx = settings.anything\n",
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_methods_and_properties_of_our_own_class_are_declared(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/svc.py": (
                "class Svc:\n"
                "    LIMIT = 5\n"
                "    @property\n"
                "    def ready(self):\n"
                "        return True\n"
                "    def go(self):\n"
                "        return 1\n\n"
                "svc = Svc()\n"
                "x = (svc.LIMIT, svc.ready, svc.go())\n"
            )
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_an_attribute_from_a_product_defined_base_is_declared(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/base.py": "class Base:\n    shared = 1\n",
            "backend/app/impl.py": (
                "from .base import Base\n\n"
                "class Impl(Base):\n"
                "    own = 2\n\n"
                "impl = Impl()\n"
                "x = (impl.shared, impl.own)\n"
            ),
        },
    )
    assert find_missing_instance_attributes(code) == []


def test_it_is_wired_where_it_can_act():
    """A detector nothing consumes changes nothing."""
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(
        encoding="utf-8"
    )
    assert "absent_attributes = find_missing_instance_attributes(code_dir)" in check
    assert '"code": "missing_attribute"' in check

    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    head = qa[: qa.index("# Deletions next")]
    assert '"missing_attribute"' in head, "it never reaches the round as a blocking defect"

    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "find_missing_instance_attributes" in dev, (
        "the developer's own coherence check cannot see it, so a round may introduce one for free"
    )

    executor = (root / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    assert "find_missing_instance_attributes" in executor, (
        "a revert would hand the next round a diagnosis without it"
    )


# --- the weights have to agree about what "fatal" means ----------------------------------------


def test_import_time_defects_all_weigh_the_same():
    """Watched live, and it let a round buy nine ImportErrors with one fix.

        before: missing_attribute 2, duplicate_tablename 1                 -> 30
        after:  missing_symbol 9, missing_attribute 1, duplicate_tablename 1 -> 29   ACCEPTED

    The round fixed one attribute (-10) and introduced nine missing symbols (+9), so it measured as
    an improvement. Every one of those nine is `from x import y` for a name nothing defines — an
    ImportError at boot, exactly as fatal as a missing module or two models on one table, and it was
    the only member of that family weighted 1 instead of 10.
    """
    src = (
        Path(__file__).resolve().parents[1] / "agents" / "dev.py"
    ).read_text(encoding="utf-8")
    score = src[src.index("def _tree_defect_score(") :]
    score = score[: score.index("def _revert_out_of_scope_writes")]
    for fatal in (
        "find_missing_symbols",
        "find_missing_modules",
        "find_missing_instance_attributes",
        "find_duplicate_tablenames",
        "find_hallucinated_imports",
    ):
        assert f"10 * len({fatal}(" in score, (
            f"{fatal} is not weighted like the rest of the import-time family"
        )


def test_the_health_gate_calls_a_missing_symbol_critical():
    """The round guard weighs severity, so `high` under-counted it against a duplicate table."""
    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "duplicate_module_check.py"
    ).read_text(encoding="utf-8")
    block = src[src.index('"code": "missing_symbol"') :][:400]
    assert '"severity": "critical"' in block, block


# --- the suggestion has to see the commonest mistake --------------------------------------------


def test_a_case_difference_is_suggested(tmp_path):
    """Watched live: a round wrote settings.ATLAS_BASE_URL for a field declared atlas_base_url.

    difflib is case-sensitive, so every character differs and the score lands far below any usable
    cutoff — the finding named the attribute and suggested nothing, though the fix is one token. The
    round was rejected for it and had no way to know that from the finding.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS.replace(
                '    api_prefix: str = "/api"\n', '    atlas_base_url: str = "x"\n'
            ),
            "backend/app/main.py": "from .config import settings\nu = settings.ATLAS_BASE_URL\n",
        },
    )
    finding = find_missing_instance_attributes(code)[0]
    assert finding["attribute"] == "ATLAS_BASE_URL"
    assert finding["did_you_mean"] == ["atlas_base_url"], finding


def test_an_underscore_difference_is_suggested(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS.replace(
                '    api_prefix: str = "/api"\n', '    api_prefix: str = "/api"\n    cache_ttl: int = 1\n'
            ),
            "backend/app/main.py": "from .config import settings\nu = settings.cachettl\n",
        },
    )
    assert find_missing_instance_attributes(code)[0]["did_you_mean"] == ["cache_ttl"]


def test_the_symbol_detector_gets_the_same_treatment(tmp_path):
    """`from .cache import cache_service` for a class named CacheService — the same shape."""
    from web.backend.services.duplicate_module_check import find_missing_symbols

    code = _tree(
        tmp_path / "code",
        {
            "backend/app/cache.py": "class CacheService:\n    pass\n",
            "backend/app/use.py": "from .cache import cache_service\n",
        },
    )
    finding = find_missing_symbols(code)[0]
    assert finding["symbol"] == "cache_service"
    assert finding["did_you_mean"] == ["CacheService"], finding


def test_an_unrelated_name_still_gets_no_false_suggestion(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/config.py": SETTINGS,
            "backend/app/main.py": "from .config import settings\nu = settings.totally_unrelated\n",
        },
    )
    assert find_missing_instance_attributes(code)[0]["did_you_mean"] == []


def test_a_missing_attribute_fails_the_health_gate(tmp_path):
    """It was reported as critical and the gate went green anyway.

    Caught on the live product at the moment every other defect closed: `module_health: PASSED` with one
    `missing_attribute` — `rule_engine.compute_advisory`, read by `routers/advisory.py:62`, gone because
    a round had renamed it. A critical that does not fail its own gate is one line in a list the round
    may or may not act on.
    """
    from web.backend.services.duplicate_module_check import run_duplicate_module_check

    code = tmp_path / "data" / "code" / "prod-x"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "config.py").write_text(SETTINGS, encoding="utf-8")
    (code / "backend" / "app" / "main.py").write_text(
        "from .config import settings\nx = settings.nope\n", encoding="utf-8"
    )
    result = run_duplicate_module_check("prod-x", str(tmp_path / "data"))
    assert result["passed"] is False, result
    assert any(i.get("code") == "missing_attribute" for i in result["issues"])


def test_a_missing_module_fails_it_too(tmp_path):
    from web.backend.services.duplicate_module_check import run_duplicate_module_check

    code = tmp_path / "data" / "code" / "prod-y"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "main.py").write_text(
        "from .nowhere import thing\n", encoding="utf-8"
    )
    result = run_duplicate_module_check("prod-y", str(tmp_path / "data"))
    assert result["passed"] is False, result


def test_a_local_object_is_analysed_like_a_singleton(tmp_path):
    """It cost a boot, and the only difference from the module-level case is indentation.

    `heartbeat = HeartbeatService(db)` inside a lifespan function, then
    `heartbeat.scheduler.shutdown()` — on a class with start(), stop(), _thread and _stop_event and
    no scheduler at all. AttributeError inside lifespan takes the whole application down. The same
    pass also found why /api/advisory answered 500: `atlas.get_advisory(...)` on an AtlasClient that
    never declares it.
    """
    code = tmp_path / "code"
    (code / "backend" / "app" / "services").mkdir(parents=True)
    (code / "backend" / "app" / "services" / "heartbeat.py").write_text(
        "import threading\n\n\nclass HeartbeatService:\n"
        "    def __init__(self, *args, **kwargs):\n        self._stop_event = threading.Event()\n\n"
        "    def start(self):\n        pass\n\n    def stop(self):\n        pass\n",
        encoding="utf-8",
    )
    (code / "backend" / "app" / "main.py").write_text(
        "from app.services.heartbeat import HeartbeatService\n\n\n"
        "async def lifespan(app):\n"
        "    heartbeat = HeartbeatService(None)\n"
        "    heartbeat.start()\n"
        "    yield\n"
        "    heartbeat.scheduler.shutdown()\n",
        encoding="utf-8",
    )
    found = [f for f in find_missing_instance_attributes(code) if "scheduler" in str(f.get("detail"))]
    assert len(found) == 1, [f.get("detail") for f in find_missing_instance_attributes(code)]
    assert found[0]["file"].endswith("heartbeat.py")
    assert "main.py:8" in found[0]["detail"], "the read site belongs in the finding"


def test_a_name_bound_to_two_classes_in_one_module_is_left_alone(tmp_path):
    """Which class a read belongs to is no longer knowable, and a wrong critical costs a round."""
    code = tmp_path / "code"
    (code / "app").mkdir(parents=True)
    (code / "app" / "models.py").write_text(
        "class A:\n    def __init__(self):\n        self.x = 1\n\n\n"
        "class B:\n    def __init__(self):\n        self.y = 2\n",
        encoding="utf-8",
    )
    (code / "app" / "use.py").write_text(
        "from app.models import A, B\n\n\n"
        "def one():\n    obj = A()\n    return obj.x\n\n\n"
        "def two():\n    obj = B()\n    return obj.y\n",
        encoding="utf-8",
    )
    assert find_missing_instance_attributes(code) == []


def test_the_finding_names_the_methods_the_class_does_have(tmp_path):
    """"It does not declare X" is a diagnosis; "it declares these three" is an instruction.

    Without this the rounds oscillated for an hour: atlas.get_advisory(...) does not exist, so one
    round added a method, the next deleted the call, a third substituted a placeholder that removed
    the product's only purpose — while AtlasClient had get_situation_brief, get_fire_weather and
    get_nearest_read sitting right there, all async.
    """
    code = tmp_path / "code"
    (code / "backend" / "app" / "services").mkdir(parents=True)
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "services" / "atlas_client.py").write_text(
        "class AtlasClient:\n"
        "    async def get_situation_brief(self, lat, lon):\n        return {}\n\n"
        "    async def get_fire_weather(self, lat, lon):\n        return {}\n",
        encoding="utf-8",
    )
    (code / "backend" / "app" / "routers" / "advisory.py").write_text(
        "from ..services.atlas_client import AtlasClient\n\n\n"
        "async def advisory():\n"
        "    atlas = AtlasClient()\n"
        "    return await atlas.get_advisory(1, 2)\n",
        encoding="utf-8",
    )
    found = [f for f in find_missing_instance_attributes(code) if "get_advisory" in str(f["detail"])]
    assert len(found) == 1
    detail = found[0]["detail"]
    assert "DOES declare" in detail
    assert "get_situation_brief" in detail and "get_fire_weather" in detail
    assert "async — call with await" in detail, "the coroutine trap belongs in the finding"
    assert "Do NOT delete the call site" in detail, "deleting the call is the cheap wrong answer"
    assert detail.index("Do NOT delete") < detail.index("declare it on"), (
        "the prohibition must precede the alternative: a 600-char truncation once cut the\n        prohibition off and left the permission as the last thing the model read"
    )


def test_private_members_are_not_offered_as_alternatives(tmp_path):
    code = tmp_path / "code"
    (code / "app").mkdir(parents=True)
    (code / "app" / "svc.py").write_text(
        "class Svc:\n    def _internal(self):\n        return 1\n\n    def public(self):\n        return 2\n",
        encoding="utf-8",
    )
    (code / "app" / "use.py").write_text(
        "from app.svc import Svc\n\n\ndef go():\n    s = Svc()\n    return s.missing()\n",
        encoding="utf-8",
    )
    found = [f for f in find_missing_instance_attributes(code) if "missing" in str(f["detail"])]
    assert found, "the missing attribute itself must still be reported"
    assert "_internal" not in found[0]["detail"]
    assert "public" in found[0]["detail"]
