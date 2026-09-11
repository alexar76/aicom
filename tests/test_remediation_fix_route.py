"""POST /api/remediation/fix — the Factory's patch-authoring endpoint.

The route exists to hand SKOPOS a reviewable diff. These tests pin the properties that make that
safe, and the first one is the most important: this service **reimplements** MOMUS's signature
verification, because ``momus.findings`` imports ``oracle_core``, which is not a Factory dependency.
Two independent implementations of one canonical form is exactly how the AWR int-vs-float split
happened, so they are checked against each other here rather than assumed to agree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "oracles" / "core"))
sys.path.insert(0, str(REPO / "momus"))

from web.backend.services import remediation_fix as rf  # noqa: E402


@pytest.fixture
def momus_signer(tmp_path):
    from momus.findings import FindingSigner
    return FindingSigner(str(tmp_path / "momus.key"))


def _signed_ticket(signer, *, finding_id="mom-1", component="momus-canary"):
    from momus.findings import Blame
    blame = signer.sign_blame(Blame(finding_id=finding_id, component=component, severity="high",
                                    hop=f"{component}:free_tier_ceiling_bypass",
                                    summary="free-tier ceiling can be bypassed"))
    return {"finding_id": finding_id, "component": component, "target": component,
            "probe": "free_tier_ceiling_bypass", "severity": "high",
            "reproducer": "POST /invoke 11 times; the 11th succeeds",
            "blame": {**blame.canonical(), "signature": blame.signature}}


# ── 1. the two verifiers must agree ───────────────────────────────────────────
def test_the_factory_verifier_agrees_with_momus_on_the_same_document(momus_signer):
    """The drift guard. If either canonical form changes, this fails here instead of silently
    rejecting every real ticket in production."""
    from momus.findings import verify_document_signature

    ticket = _signed_ticket(momus_signer)
    blame = ticket["blame"]
    body = {k: v for k, v in blame.items() if k != "signature"}

    assert verify_document_signature(body, blame["signature"], momus_signer.pubkey) is True
    ok, why = rf.verify_blame(blame, momus_signer.pubkey)
    assert ok, why


def test_both_verifiers_reject_the_same_tampered_document(momus_signer):
    from momus.findings import verify_document_signature

    ticket = _signed_ticket(momus_signer)
    blame = dict(ticket["blame"])
    blame["severity"] = "low"                      # tamper
    body = {k: v for k, v in blame.items() if k != "signature"}
    assert verify_document_signature(body, blame["signature"], momus_signer.pubkey) is False
    assert rf.verify_blame(blame, momus_signer.pubkey)[0] is False


def test_a_post_quantum_signature_is_refused_rather_than_half_checked(momus_signer):
    """oracle_core fails closed when it cannot check a PQ signature. Verifying only the classical
    half here would silently downgrade the guarantee for anyone who turns PQ on."""
    ticket = _signed_ticket(momus_signer)
    blame = dict(ticket["blame"])
    blame["signature"] = {**blame["signature"], "pq_value": "AAAA", "pq_algorithm": "ml-dsa-65"}
    ok, why = rf.verify_blame(blame, momus_signer.pubkey)
    assert not ok and "post-quantum" in why


def test_an_unsigned_or_unkeyed_ticket_is_refused(momus_signer):
    assert rf.verify_blame({}, momus_signer.pubkey)[0] is False
    assert rf.verify_blame(_signed_ticket(momus_signer)["blame"], "")[0] is False


# ── 2. the capability is OFF until an operator turns it on ────────────────────
@pytest.mark.asyncio
async def test_disabled_by_default(monkeypatch, momus_signer):
    """Merging the code must not enable autonomous patch authoring."""
    monkeypatch.delenv(rf.ENABLED_ENV, raising=False)
    with pytest.raises(rf.FixRefused) as exc:
        await rf.author_fix(_signed_ticket(momus_signer), llm_router=object())
    assert exc.value.config_error and rf.ENABLED_ENV in exc.value.reason


@pytest.mark.asyncio
async def test_the_factory_hold_is_honoured(monkeypatch, momus_signer):
    """No web/backend code consulted the hold before this route existed, so an operator who had
    stopped the factory would still have watched it spend LLM budget writing patches."""
    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr("core.factory_hold.is_factory_hard_stopped", lambda: True)
    with pytest.raises(rf.FixRefused) as exc:
        await rf.author_fix(_signed_ticket(momus_signer), llm_router=object())
    assert exc.value.config_error and "hard-stopped" in exc.value.reason


@pytest.mark.asyncio
async def test_a_component_with_no_scope_is_refused(monkeypatch, momus_signer):
    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setenv(rf.MOMUS_PUBKEY_ENV, momus_signer.pubkey)
    monkeypatch.setattr("core.factory_hold.is_factory_hard_stopped", lambda: False)
    # A component nobody has scoped. "oracles" used to stand in for this and no longer can —
    # the scope now covers every service MOMUS actually probes, which is the point.
    ticket = _signed_ticket(momus_signer, component="some-unscoped-service")
    with pytest.raises(rf.FixRefused) as exc:
        await rf.author_fix(ticket, llm_router=object())
    assert exc.value.config_error and "no patch scope" in exc.value.reason


# ── 3. the scope is the host's, not the model's ───────────────────────────────
def test_a_reply_touching_a_file_outside_the_scope_is_refused():
    reply = json.dumps({"summary": "s", "files": {"web/backend/main.py": "import os\n"}})
    with pytest.raises(rf.FixRefused) as exc:
        rf.parse_reply(reply, {"momus/canary/canary.py"})
    assert "outside the patch scope" in exc.value.reason


def test_a_reply_that_is_not_json_is_refused():
    with pytest.raises(rf.FixRefused):
        rf.parse_reply("I would fix it by adding a check.", {"a.py"})


def test_a_fenced_json_reply_is_still_read():
    reply = '```json\n{"summary": "fix it", "files": {"a.py": "x = 1\\n"}}\n```'
    summary, files = rf.parse_reply(reply, {"a.py"})
    assert summary == "fix it" and files == {"a.py": "x = 1\n"}


def test_an_empty_replacement_is_refused():
    with pytest.raises(rf.FixRefused):
        rf.parse_reply(json.dumps({"summary": "s", "files": {"a.py": "   "}}), {"a.py"})


def test_a_scope_entry_escaping_the_app_root_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_APP_ROOT", str(tmp_path))
    monkeypatch.setenv(rf.SCOPE_ENV, json.dumps({"svc": ["../../etc/passwd"]}))
    with pytest.raises(rf.FixRefused) as exc:
        rf._read_scope("svc")
    assert "escapes the application root" in exc.value.reason


# ── 4. the diff is real, and it applies ──────────────────────────────────────
def test_the_produced_diff_actually_applies(tmp_path):
    """The model returns file CONTENTS and git computes the diff, precisely so the result is one
    `git apply` can be trusted with. This proves the round trip."""
    before = {"pkg/mod.py": "def f():\n    return 1\n"}
    after = {"pkg/mod.py": "def f():\n    return 2\n"}
    diff = rf.diff_from_rewrites(before, after)
    assert "--- a/pkg/mod.py" in diff and "+    return 2" in diff

    # Apply it to a fresh tree laid out from `before`, the way the conductor's worktree will.
    target = tmp_path / "repo"
    (target / "pkg").mkdir(parents=True)
    (target / "pkg" / "mod.py").write_text(before["pkg/mod.py"], encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    applied = subprocess.run(["git", "apply", "-"], cwd=target, input=diff, text=True,
                             capture_output=True)
    assert applied.returncode == 0, applied.stderr
    assert (target / "pkg" / "mod.py").read_text(encoding="utf-8") == after["pkg/mod.py"]


def test_an_unchanged_file_produces_no_diff(tmp_path):
    """A model that returned the file verbatim has fixed nothing. Reporting success would push an
    empty branch and have MOMUS gate the unpatched build as if it were a fix."""
    same = {"a.py": "x = 1\n"}
    assert rf.diff_from_rewrites(same, dict(same)).strip() == ""


@pytest.mark.asyncio
async def test_a_no_op_reply_is_refused_end_to_end(monkeypatch, momus_signer, tmp_path):
    (tmp_path / "momus" / "canary").mkdir(parents=True)
    src = "STATE = {'fixed': False}\n"
    (tmp_path / "momus" / "canary" / "canary.py").write_text(src, encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_APP_ROOT", str(tmp_path))
    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setenv(rf.MOMUS_PUBKEY_ENV, momus_signer.pubkey)
    monkeypatch.setattr("core.factory_hold.is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr("core.pipeline_cost_guard.assert_product_within_budget", lambda pid: None)

    class Router:
        async def generate(self, prompt, task_type="code_generation", config=None):
            return json.dumps({"summary": "no change", "files": {"momus/canary/canary.py": src}})

    with pytest.raises(rf.FixRefused) as exc:
        await rf.author_fix(_signed_ticket(momus_signer), llm_router=Router())
    assert "no actual change" in exc.value.reason


@pytest.mark.asyncio
async def test_a_real_patch_comes_back_as_a_diff_and_never_an_image(monkeypatch, momus_signer,
                                                                   tmp_path):
    (tmp_path / "momus" / "canary").mkdir(parents=True)
    (tmp_path / "momus" / "canary" / "canary.py").write_text(
        "LIMIT = None\n\n\ndef allow(n):\n    return True\n", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_APP_ROOT", str(tmp_path))
    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setenv(rf.MOMUS_PUBKEY_ENV, momus_signer.pubkey)
    monkeypatch.setattr("core.factory_hold.is_factory_hard_stopped", lambda: False)
    seen: dict = {}
    monkeypatch.setattr("core.pipeline_cost_guard.assert_product_within_budget",
                        lambda pid: seen.setdefault("product_id", pid))

    class Router:
        async def generate(self, prompt, task_type="code_generation", config=None):
            seen["config"] = config
            seen["prompt"] = prompt
            return json.dumps({"summary": "enforce the free-tier ceiling",
                               "files": {"momus/canary/canary.py":
                                         "LIMIT = 10\n\n\ndef allow(n):\n    return n < LIMIT\n"}})

    patch = await rf.author_fix(_signed_ticket(momus_signer), llm_router=Router())
    body = patch.to_dict()
    assert "image" not in body, "the Factory authors source; the fleet builds images"
    assert body["deployable"] is False
    assert body["files"] == ["momus/canary/canary.py"]
    assert "+LIMIT = 10" in body["diff"] and body["summary"].startswith("enforce")
    # The cost guard is a no-op for an empty product_id, and the router only books spend when one is
    # set — so a missing id would make the per-product cap silently inert.
    assert seen["product_id"] == rf.COST_PRODUCT_ID
    assert seen["config"].product_id == rf.COST_PRODUCT_ID
    assert seen["config"].temperature == 0.0
    # The reproducer has to reach the model, or it is guessing at the bug.
    assert "the 11th succeeds" in seen["prompt"]


# ── 5. the HTTP surface ──────────────────────────────────────────────────────
def _client(monkeypatch, **env):
    from web.backend.api import remediation as api
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    app = FastAPI()
    app.include_router(api.router)
    app.state.llm_router = None
    return TestClient(app, raise_server_exceptions=False)


def test_production_without_a_key_refuses_rather_than_opening(monkeypatch):
    """Fail-closed: an unset shared secret in production makes the route unavailable, not public.
    It is reachable from the internet through the Next.js /api/:path* rewrite."""
    client = _client(monkeypatch, AIFACTORY_PROD="1", AIFACTORY_REMEDIATION_KEY="")
    r = client.post("/api/remediation/fix", json={"ticket": {}})
    assert r.status_code == 503 and rf.KEY_ENV in r.json()["detail"]


def test_enabled_development_route_without_a_key_also_refuses(monkeypatch):
    """Environment labels do not authenticate a costly, publicly rewritten control route."""
    client = _client(
        monkeypatch,
        AIFACTORY_PROD="",
        AIFACTORY_REMEDIATION_KEY="",
        AIFACTORY_REMEDIATION_FIX_ENABLED="1",
    )
    r = client.post("/api/remediation/fix", json={"ticket": {}})
    assert r.status_code == 503 and rf.KEY_ENV in r.json()["detail"]


def test_a_wrong_key_is_rejected(monkeypatch):
    client = _client(monkeypatch, AIFACTORY_REMEDIATION_KEY="s3cret")
    assert client.post("/api/remediation/fix", json={"ticket": {}},
                       headers={"x-remediation-key": "nope"}).status_code == 401
    assert client.post("/api/remediation/fix", json={"ticket": {}}).status_code == 401


def test_a_refusal_answers_200_so_the_conductor_can_read_config_error(monkeypatch):
    """The conductor distinguishes "retry the patch" from "a human must fix something" by reading
    `config_error` out of the body. An HTTP error code would flatten both into a retry loop."""
    client = _client(monkeypatch, AIFACTORY_REMEDIATION_KEY="s3cret", AIFACTORY_PROD="")
    monkeypatch.delenv(rf.ENABLED_ENV, raising=False)
    r = client.post("/api/remediation/fix", json={"ticket": {"finding_id": "x"}},
                    headers={"x-remediation-key": "s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["config_error"] is True


def test_the_status_route_tells_an_operator_what_is_enabled(monkeypatch):
    client = _client(monkeypatch, AIFACTORY_REMEDIATION_KEY="s3cret",
                     AIFACTORY_REMEDIATION_FIX_ENABLED="1")
    body = client.get("/api/remediation/fix/status",
                      headers={"x-remediation-key": "s3cret"}).json()
    assert body["enabled"] is True and body["authenticated"] is True
    assert "momus-canary" in body["scope"]
    assert "canary" in body["scope"]
    assert "hub" in body["scope"]
    assert "aimarket-hub" in body["scope"]


def test_a_body_without_a_ticket_is_a_client_error(monkeypatch):
    client = _client(monkeypatch, AIFACTORY_REMEDIATION_KEY="")
    assert client.post("/api/remediation/fix", json={"nope": 1}).status_code == 400
    assert client.post("/api/remediation/fix", content=b"not json").status_code == 400


def test_default_scope_includes_hub_and_files_fit_the_scratch_cap():
    """Hub is the first real service on the loop. api.py is too large to patch; the
    unpaid-invoke gate is the file MOMUS re-runs. Both MOMUS names and compose names resolve."""
    scope = rf.DEFAULT_SCOPE
    assert scope["hub"] == scope["aimarket-hub"]
    assert scope["canary"] == scope["momus-canary"]
    root = REPO
    for rel in scope["hub"] + scope["canary"]:
        path = root / rel
        assert path.is_file(), rel
        assert path.stat().st_size <= rf.MAX_FILE_BYTES, rel
    assert "unpaid_invoke.py" in scope["hub"][0]
    assert "momus" not in scope and "treasury" not in scope


# ── conflict of interest ──────────────────────────────────────────────────────


class TestTheLoopCannotPatchItself:
    """The owner's rule: fix everything in the ecosystem you can — but not yourself, not the
    Treasury, and not the conductor.

    Leaving those out of the scope map is not enough. Omission is a default, and a default is
    what an operator widening `AIFACTORY_REMEDIATION_SCOPE` overrides without noticing. So the
    refusal is in code, checked against the env map AND against whatever the model answers,
    because those two fail differently: one is an operator's mistake, the other a model's.
    """

    def _mod(self):
        from web.backend.services import remediation_fix

        return remediation_fix

    def test_the_auditor_is_denied(self):
        """A loop that can patch what decides a finding is real can decide it is not."""
        assert self._mod().path_is_denied("momus/momus/findings.py")
        assert self._mod().path_is_denied("momus/momus/engine/remediation.py")

    def test_the_canary_is_not_denied(self):
        """It is the deliberate test subject — proving the loop on it is why it exists."""
        assert not self._mod().path_is_denied("momus/canary/canary.py")

    def test_the_payer_is_denied(self):
        """MOMUS finds and signs; it must not reach the thing that pays it."""
        assert self._mod().path_is_denied("treasury/app.py")

    def test_the_conductor_is_denied(self):
        """SKOPOS decides whether a fix ships and calls MOMUS back to re-test. Patching your
        own gatekeeper is patching yourself, one step removed."""
        assert self._mod().path_is_denied("skopos/conductor.py")

    def test_this_gate_is_denied(self):
        assert self._mod().path_is_denied("web/backend/services/remediation_fix.py")

    def test_an_operator_cannot_widen_the_scope_into_them(self, monkeypatch):
        mod = self._mod()
        monkeypatch.setenv(mod.SCOPE_ENV, json.dumps({
            "momus": ["momus/momus/findings.py"],
            "treasury": ["treasury/app.py"],
            "skopos": ["skopos/conductor.py"],
            "hub": ["aimarket-hub/aimarket_hub/unpaid_invoke.py"],
        }))
        scope = mod.scope_map()
        assert sorted(scope) == ["hub"], f"a denied component survived the env: {sorted(scope)}"

    def test_a_component_left_with_nothing_disappears_rather_than_becoming_empty(self, monkeypatch):
        """An empty path list would read as "this component is configured", and the next
        reader would wonder why its patches never apply."""
        mod = self._mod()
        monkeypatch.setenv(mod.SCOPE_ENV, json.dumps({"treasury": ["treasury/app.py"]}))
        assert mod.scope_map() == {}

    def test_a_relative_spelling_does_not_slip_past(self, monkeypatch):
        mod = self._mod()
        assert mod.path_is_denied("./treasury/app.py")
        assert mod.path_is_denied("skopos/")


class TestTheScopeCoversWhatMomusActuallyProbes:
    """Scope wider than the probes would let a ticket rewrite a file nothing re-tests — and the
    signed re-run of the probe is the only thing between a patch and production."""

    def _mod(self):
        from web.backend.services import remediation_fix

        return remediation_fix

    def test_the_services_momus_probes_are_all_fixable(self, monkeypatch):
        mod = self._mod()
        monkeypatch.delenv(mod.SCOPE_ENV, raising=False)
        scope = mod.scope_map()
        for component in ("canary", "hub", "oracles", "gaia"):
            assert component in scope, f"{component} is probed but not fixable"
            assert scope[component], f"{component} has an empty scope"

    def test_gaia_cannot_rewrite_the_shared_oracle_core(self, monkeypatch):
        """A GAIA ticket that could reach oracle_core would change every oracle in the fleet
        to fix one relay."""
        mod = self._mod()
        monkeypatch.delenv(mod.SCOPE_ENV, raising=False)
        assert not [p for p in mod.scope_map()["gaia"] if p.startswith("oracles/")]

    def test_every_scoped_path_exists_in_the_tree(self, monkeypatch):
        """A scope entry naming a file nobody wrote is a component that silently cannot be
        fixed — the failure is a refusal at patch time, long after anyone is watching."""
        mod = self._mod()
        monkeypatch.delenv(mod.SCOPE_ENV, raising=False)
        root = Path(__file__).resolve().parents[1]
        missing = [p for paths in mod.scope_map().values() for p in paths
                   if not (root / p).is_file()]
        assert not missing, f"scoped paths that do not exist: {sorted(set(missing))}"


# ── the generation config is not a detail: it was the loop's top cause of giving up ──


def _captured_cfg(monkeypatch):
    """Run author_patch far enough to capture the GenerationConfig it builds."""
    import asyncio

    from web.backend.services import remediation_fix as rf

    seen = {}

    async def _fake_generate(router, prompt, cfg):
        seen["cfg"] = cfg
        raise rf.FixRefused("stop here — we only wanted the config")

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda component: {"a.py": "print(1)\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda ticket: ("canary", "mom-1"))
    try:
        asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object()))
    except rf.FixRefused:
        pass
    return seen.get("cfg")


def test_the_fixer_asks_the_provider_for_json(monkeypatch):
    """The prompt says "return a single JSON object and nothing else" — so must the config.

    Live evidence: escalations reading "the model did not return a JSON object" were this.
    """
    cfg = _captured_cfg(monkeypatch)
    assert cfg is not None
    assert cfg.json_mode is True


def test_the_fixer_gives_the_model_the_code_generation_budget(monkeypatch):
    """GenerationConfig defaults to 30s and providers pass it to the HTTP client.

    The function declares a 600s budget in _generate; a 30s transport timeout made that
    outer budget unreachable for a call that asks for complete file contents.
    """
    from llm.factory_defaults import FACTORY_TIMEOUT_CODE_GENERATION_SEC

    cfg = _captured_cfg(monkeypatch)
    assert cfg is not None
    assert cfg.timeout_sec == FACTORY_TIMEOUT_CODE_GENERATION_SEC
    assert cfg.timeout_sec >= 600


def test_the_transport_timeout_is_not_shorter_than_the_declared_budget(monkeypatch):
    """Whatever the numbers become, the inner timeout must never undercut the outer one."""
    from web.backend.services import remediation_fix as rf

    cfg = _captured_cfg(monkeypatch)
    assert cfg.timeout_sec >= rf.LLM_BUDGET_S


# ── a patch may not invent a dependency the runtime image does not have ──────────
# Live: a canary patch imported `cryptography`, built cleanly (a Docker build only copies
# source) and the container died at import. The candidate gate caught it — after a full
# author → commit → push → build → start cycle, with the attempt spent.


def _deps(before, after):
    from web.backend.services.remediation_fix import new_third_party_imports

    return new_third_party_imports(before, after)


def test_a_new_third_party_import_is_refused():
    before = {"canary/canary.py": "import json\nimport os\n"}
    after = {"canary/canary.py": "import json\nfrom cryptography.hazmat.primitives import x\n"}
    assert _deps(before, after) == {"cryptography"}


def test_stdlib_is_never_a_new_dependency():
    before = {"canary/canary.py": "import os\n"}
    after = {"canary/canary.py": "import os\nimport hmac\nimport hashlib\nimport secrets\n"}
    assert _deps(before, after) == set()


def test_a_package_the_component_already_imports_is_not_new():
    before = {"canary/a.py": "import httpx\n", "canary/b.py": "import os\n"}
    after = {"canary/b.py": "import os\nimport httpx\n"}
    assert _deps(before, after) == set()


def test_a_local_module_is_not_a_dependency():
    before = {"canary/canary.py": "import os\n", "canary/helpers.py": "X = 1\n"}
    after = {"canary/canary.py": "import os\nimport helpers\nfrom canary import helpers as h\n"}
    assert _deps(before, after) == set()


def test_a_relative_import_is_never_third_party():
    before = {"canary/canary.py": "import os\n"}
    after = {"canary/canary.py": "import os\nfrom .util import thing\n"}
    assert _deps(before, after) == set()


def test_unparseable_replacement_reports_no_imports():
    """A syntax error is the build's job to catch; guessing imports out of it is worse."""
    before = {"canary/canary.py": "import os\n"}
    after = {"canary/canary.py": "def broken(:\n"}
    assert _deps(before, after) == set()


def test_the_refusal_names_the_module(monkeypatch, tmp_path):
    import asyncio

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard
    from web.backend.services import remediation_fix as rf

    # Pin the application root. The import guard reads what the component's BUILD declares, so
    # with the real repository as root it finds a manifest declaring `cryptography` and there is
    # nothing to refuse — the test then passes or fails on where pytest happened to be run from.
    monkeypatch.setattr(rf, "app_root", lambda: str(tmp_path))

    reply = ('{"summary": "fix it", "files": {"canary/canary.py": '
             '"import os\\nfrom cryptography.hazmat.primitives import x\\nY = 2\\n"}}')

    async def _fake_generate(router, prompt, cfg):
        return reply

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda component: {"canary/canary.py": "import os\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda ticket: ("canary", "mom-1"))

    with pytest.raises(rf.FixRefused) as err:
        asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object()))
    assert "cryptography" in str(err.value)


# ── a retry that does not know why the last one failed is a repeat ───────────────
# Live: three attempts produced the identical rejected patch in eight seconds, each refused
# for the same reason, and the job escalated having learned nothing it had already been told.


def test_the_prompt_carries_the_previous_refusal():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "mom-1", "component": "canary"},
                          {"a.py": "x = 1\n"},
                          "the patch adds 'cryptography' — a dependency the image lacks")
    assert "PREVIOUS ATTEMPT WAS REFUSED" in prompt
    assert "cryptography" in prompt
    assert "Do not produce that patch again" in prompt


def test_a_first_attempt_carries_no_refusal_block():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "mom-1"}, {"a.py": "x = 1\n"})
    assert "PREVIOUS ATTEMPT WAS REFUSED" not in prompt


def test_the_refusal_is_bounded_and_flattened():
    from web.backend.services.remediation_fix import MAX_PREVIOUS_FAILURE_CHARS, build_prompt

    prompt = build_prompt({"finding_id": "mom-1"}, {"a.py": "x = 1\n"}, "boom\n\n" + "y" * 9000)
    assert len(prompt) < 20_000
    assert "y" * (MAX_PREVIOUS_FAILURE_CHARS + 1) not in prompt


def test_author_fix_forwards_the_refusal(monkeypatch):
    import asyncio

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard
    from web.backend.services import remediation_fix as rf

    seen = {}

    async def _fake_generate(router, prompt, cfg):
        seen["prompt"] = prompt
        raise rf.FixRefused("stop")

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda component: {"a.py": "import os\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda ticket: ("canary", "mom-1"))
    try:
        asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object(),
                                  previous_failure="branch push was rejected"))
    except rf.FixRefused:
        pass
    assert "branch push was rejected" in seen["prompt"]


# ── the guard must read the BUILD, not only the imports ──────────────────────────


def test_a_package_the_build_declares_is_not_a_new_dependency(tmp_path, monkeypatch):
    """"Not imported by the files I may patch" is not "not installed"."""
    from web.backend.services import remediation_fix as rf

    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "app.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "svc" / "Dockerfile").write_text(
        'FROM python:3.11-slim\nRUN pip install --no-cache-dir "fastapi>=0.115" "cryptography>=42"\n',
        encoding="utf-8")
    monkeypatch.setattr(rf, "app_root", lambda: str(tmp_path))

    declared = rf._declared_dependencies(["svc/app.py"])
    assert "cryptography" in declared and "fastapi" in declared

    before = {"svc/app.py": "import os\n"}
    after = {"svc/app.py": "import os\nfrom cryptography.hazmat.primitives import x\n"}
    assert rf.new_third_party_imports(before, after, declared) == set()
    # And a package nobody declared is still refused.
    rogue = {"svc/app.py": "import os\nimport requests\n"}
    assert rf.new_third_party_imports(before, rogue, declared) == {"requests"}


def test_an_unreadable_build_declares_nothing(tmp_path, monkeypatch):
    """Conservative, not permissive: a missing manifest must not open the gate."""
    from web.backend.services import remediation_fix as rf

    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "app.py").write_text("import os\n", encoding="utf-8")
    monkeypatch.setattr(rf, "app_root", lambda: str(tmp_path))
    assert rf._declared_dependencies(["svc/app.py"]) == set()


def test_the_canary_image_declares_a_signing_library():
    """A conforming canary must sign its manifest for real; the image has to allow that."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1]
            / "momus" / "canary" / "Dockerfile").read_text(encoding="utf-8")
    assert "cryptography" in text


# ── a ticket that carries only a probe NAME asks the model to guess ──────────────
# Live: manifest_signature_integrity has no reproducer by nature — a signature check has
# nothing to curl — so three autonomous attempts each authored a different guess at what
# "conforming" meant, and the pre-promotion gate rejected all three.


def test_the_prompt_states_what_is_wrong_not_just_which_probe_said_so():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt(
        {"finding_id": "mom-1", "component": "canary", "probe": "manifest_signature_integrity",
         "title": "canary: manifest signature does not verify",
         "detail": "The published manifest's signature fails to verify against its declared "
                   "public key — the catalogue cannot be trusted as served."},
        {"canary.py": "x = 1\n"})
    assert "manifest signature does not verify" in prompt
    assert "fails to verify against its declared public key" in prompt


def test_an_empty_reproducer_says_so_instead_of_reading_as_nothing_to_do():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "mom-1", "title": "t", "detail": "d"}, {"a.py": "x=1\n"})
    assert "nothing to curl" in prompt


def test_the_observed_evidence_reaches_the_prompt_when_there_is_any():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt(
        {"finding_id": "mom-1", "title": "t", "detail": "d",
         "evidence": {"status_code": 200, "response_digest": "sha256-abc", "request_snippet": ""}},
        {"a.py": "x=1\n"})
    assert "observed:" in prompt
    assert "status_code: 200" in prompt
    assert "sha256-abc" in prompt
    # An empty field is not worth a line.
    assert "request_snippet" not in prompt


def test_the_probes_criterion_leads_and_is_not_filed_as_telemetry():
    """A criterion under "response_snippet:" beneath two digests reads like diagnostic noise.

    Measured: the manifest probe published exactly what to sign, the text reached the prompt,
    and three more attempts still signed something else.
    """
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt(
        {"finding_id": "mom-1", "title": "t", "detail": "d",
         "evidence": {"status_code": 200, "response_digest": "sha256-abc",
                      "response_snippet": "Ed25519 over manifest_canonical = 'a|b|c'"}},
        {"a.py": "x=1\n"})
    assert "THE CHECK YOUR PATCH MUST PASS" in prompt
    assert "ACCEPTANCE CRITERION" in prompt
    # The criterion comes BEFORE the digests, and carries no telemetry label.
    assert prompt.index("manifest_canonical") < prompt.index("sha256-abc")
    assert "response_snippet:" not in prompt


def test_no_evidence_adds_no_section():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "mom-1", "evidence": {}}, {"a.py": "x=1\n"})
    assert "observed:" not in prompt


def test_evidence_is_bounded():
    from web.backend.services.remediation_fix import MAX_EVIDENCE_CHARS, build_prompt

    prompt = build_prompt(
        {"finding_id": "mom-1", "evidence": {"response_snippet": "z" * 50_000}},
        {"a.py": "x=1\n"})
    assert "z" * (MAX_EVIDENCE_CHARS + 1) not in prompt


def test_a_missing_title_is_named_as_missing():
    """So a reader of the prompt can tell "not stated" from "nothing is wrong"."""
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "mom-1", "probe": "p"}, {"a.py": "x=1\n"})
    assert "only the probe name is known" in prompt


# ── a patch that does not parse must never reach a build ─────────────────────────
# Live: an unterminated triple-quoted string was committed, pushed, built into an image and
# launched, and only the candidate container noticed — escalating on "the candidate did not
# start", which reads like an infrastructure fault rather than a truncated file.


def test_an_unterminated_string_is_caught_before_the_build():
    from web.backend.services.remediation_fix import first_syntax_error

    broken = {"canary/canary.py": '"""a docstring that never closes\nX = 1\n'}
    err = first_syntax_error(broken)
    assert "canary/canary.py" in err
    assert "unterminated" in err.lower() or "eof" in err.lower()


def test_valid_python_reports_nothing():
    from web.backend.services.remediation_fix import first_syntax_error

    assert first_syntax_error({"a.py": "import os\n\n\ndef f():\n    return os.sep\n"}) == ""


def test_non_python_files_are_not_parsed():
    from web.backend.services.remediation_fix import first_syntax_error

    assert first_syntax_error({"Dockerfile": "FROM python:3.11\nRUN pip install x\n"}) == ""


def test_the_refusal_names_the_file_and_line(monkeypatch):
    import asyncio

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard
    from web.backend.services import remediation_fix as rf

    reply = json.dumps({"summary": "fix", "files": {"canary/canary.py": '"""never closed\nX = 1\n'}})

    async def _fake_generate(router, prompt, cfg):
        return reply

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda c: {"canary/canary.py": "X = 0\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda t: ("canary", "mom-1"))

    with pytest.raises(rf.FixRefused) as err:
        asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object()))
    assert "does not parse" in str(err.value)
    assert "canary/canary.py" in str(err.value)


# ── a reply cut off by the output limit is not an answer ─────────────────────────
# Live: the provider returned a Python file whose last triple-quoted string was never
# closed. It was committed, pushed, built into an image and launched, and the job escalated
# on "the candidate did not start" — an infrastructure-shaped message for a reply that had
# simply run out of room. finish_reason was in the response all along and nobody read it.


def test_generation_config_reports_truncation():
    from llm.provider import GenerationConfig

    cfg = GenerationConfig()
    assert cfg.finish_reason == "" and cfg.was_truncated is False
    for reason in ("length", "max_tokens", "MAX_OUTPUT_TOKENS"):
        cfg.finish_reason = reason
        assert cfg.was_truncated is True, reason
    cfg.finish_reason = "stop"
    assert cfg.was_truncated is False


def test_the_fixer_refuses_a_truncated_answer(monkeypatch):
    import asyncio

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard
    from web.backend.services import remediation_fix as rf

    async def _fake_generate(router, prompt, cfg):
        cfg.finish_reason = "length"          # the provider says it ran out of room
        return '{"summary": "fix", "files": {"a.py": "X = 1\\n"}}'

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda c: {"a.py": "X = 0\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda t: ("canary", "mom-1"))

    with pytest.raises(rf.FixRefused) as err:
        asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object()))
    # Even though the JSON parsed and the file compiles — truncation is about the ANSWER,
    # not about whether what survived happens to be valid.
    assert "cut off" in str(err.value)


def test_a_complete_answer_is_not_refused(monkeypatch):
    import asyncio

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard
    from web.backend.services import remediation_fix as rf

    async def _fake_generate(router, prompt, cfg):
        cfg.finish_reason = "stop"
        return '{"summary": "fix", "files": {"a.py": "X = 1\\n"}}'

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda c: {"a.py": "X = 0\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda t: ("canary", "mom-1"))

    patch = asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object()))
    assert patch.diff.strip()


# ── a repair round the gate keeps rejecting should change the MODEL, not just the count ──
# Live: a finding the configured model could not solve was retried with that same model three
# times and escalated to a human — three failures of the same kind, and no new information.


def test_the_first_attempt_uses_the_routers_own_choice(monkeypatch):
    from web.backend.services.remediation_fix import ESCALATION_MODEL_ENV, escalation_model

    monkeypatch.setenv(ESCALATION_MODEL_ENV, "some/stronger-model")
    assert escalation_model(1) == ""


def test_later_attempts_escalate_when_an_operator_named_a_model(monkeypatch):
    from web.backend.services.remediation_fix import ESCALATION_MODEL_ENV, escalation_model

    monkeypatch.setenv(ESCALATION_MODEL_ENV, "some/stronger-model")
    assert escalation_model(2) == "some/stronger-model"
    assert escalation_model(3) == "some/stronger-model"


def test_nothing_escalates_until_an_operator_chooses(monkeypatch):
    """Which model to spend on is an operator's decision, not this file's."""
    from web.backend.services.remediation_fix import ESCALATION_MODEL_ENV, escalation_model

    monkeypatch.delenv(ESCALATION_MODEL_ENV, raising=False)
    assert escalation_model(3) == ""


def test_the_escalation_reaches_the_generation_config(monkeypatch):
    import asyncio

    import core.factory_hold as factory_hold
    import core.pipeline_cost_guard as cost_guard
    from web.backend.services import remediation_fix as rf

    seen = {}

    async def _fake_generate(router, prompt, cfg):
        seen["model"] = cfg.model_override
        raise rf.FixRefused("stop")

    monkeypatch.setenv(rf.ENABLED_ENV, "1")
    monkeypatch.setenv(rf.ESCALATION_MODEL_ENV, "some/stronger-model")
    monkeypatch.setattr(rf, "_generate", _fake_generate)
    monkeypatch.setattr(rf, "_read_scope", lambda c: {"a.py": "X = 0\n"})
    monkeypatch.setattr(cost_guard, "assert_product_within_budget", lambda pid: None)
    monkeypatch.setattr(factory_hold, "is_factory_hard_stopped", lambda: False)
    monkeypatch.setattr(rf, "check_ticket", lambda t: ("canary", "mom-1"))

    for attempt, expected in ((1, None), (2, "some/stronger-model")):
        try:
            asyncio.run(rf.author_fix({"finding_id": "mom-1"}, llm_router=object(), attempt=attempt))
        except rf.FixRefused:
            pass
        assert seen["model"] == expected, f"attempt {attempt}"


# ── a retry served from cache is a replay, not a retry ───────────────────────────
# Live: the branch for attempt 3 was published THREE SECONDS after attempt 2 was rejected,
# because the gate's rejection text is identical between attempts, so the prompt was
# byte-identical and no model ran at all.


def test_the_fixer_opts_out_of_the_response_cache(monkeypatch):
    cfg = _captured_cfg(monkeypatch)
    assert cfg is not None
    assert cfg.no_cache is True


def test_the_router_honours_no_cache_on_read_and_on_write():
    import inspect

    import llm.router as router

    src = inspect.getsource(router.LLMRouter.generate)
    read = src[src.index("cache_key = self._build_cache_key"):src.index("LLM cache hit")]
    assert "no_cache" in read, "a no_cache call must not be SERVED from cache"
    idx = src.index("_cache_set(cache_key, result)")
    assert "no_cache" in src[max(0, idx - 900):idx], "a no_cache call must not be STORED either"


def test_the_prompt_names_which_attempt_this_is():
    """Two purposes: the model should know the ladder is running out, and an attempt number
    makes otherwise-identical prompts distinct."""
    from web.backend.services.remediation_fix import build_prompt

    first = build_prompt({"finding_id": "m"}, {"a.py": "x=1\n"}, "", 1)
    second = build_prompt({"finding_id": "m"}, {"a.py": "x=1\n"}, "", 2)
    third = build_prompt({"finding_id": "m"}, {"a.py": "x=1\n"}, "", 3)
    assert "ATTEMPT" not in first, "the first attempt has no ladder to report"
    assert "ATTEMPT 2 of 3" in second
    assert "ATTEMPT 3 of 3" in third
    assert "goes to a human" in third
    # And, crucially, they are not the same bytes.
    assert len({first, second, third}) == 3


def test_no_cache_defaults_off_for_everyone_else():
    from llm.provider import GenerationConfig

    assert GenerationConfig().no_cache is False


def test_an_honest_refusal_keeps_the_models_reason():
    """The prompt offers empty `files` + a reason as the honest answer. Discarding the reason
    threw away the one thing the loop asked for — and the first sentence a human needs."""
    from web.backend.services.remediation_fix import FixRefused, parse_reply

    reply = ('{"summary": "the manifest signature must be produced by the hub, not by this '
             'service; no change here can make it verify", "files": {}}')
    with pytest.raises(FixRefused) as err:
        parse_reply(reply, {"a.py"})
    assert "declined to patch and said why" in str(err.value)
    assert "must be produced by the hub" in str(err.value)


def test_an_empty_answer_with_no_reason_says_that_too():
    from web.backend.services.remediation_fix import FixRefused, parse_reply

    with pytest.raises(FixRefused) as err:
        parse_reply('{"summary": "", "files": {}}', {"a.py"})
    assert "gave no reason" in str(err.value)


# ── a rewrite that drops an import parses perfectly and dies at `python -m` ───────
# Live: `NameError: name 'json' is not defined`, found by a candidate container ninety
# seconds and one image build after it could have been found here.


def test_a_dropped_import_is_caught():
    from web.backend.services.remediation_fix import first_unbound_name

    before = {"a.py": "import json\nX = json.dumps({})\n"}
    after = {"a.py": "X = json.dumps({})\n"}
    err = first_unbound_name(before, after)
    assert "a.py" in err and "'json'" in err


def test_ordinary_code_is_not_refused():
    from web.backend.services.remediation_fix import first_unbound_name

    ok = {"a.py": (
        "import json\nimport os\n\n"
        "CONST = 1\n\n"
        "def f(arg, *, kw=2):\n"
        "    local = [x for x in range(arg)]\n"
        "    try:\n        return json.dumps({'a': local, 'b': os.sep, 'c': kw, 'd': CONST})\n"
        "    except ValueError as exc:\n        return str(exc)\n\n"
        "class C:\n    def m(self):\n        return f(1)\n"
    )}
    assert first_unbound_name({}, ok) == ""


def test_builtins_are_not_flagged():
    from web.backend.services.remediation_fix import first_unbound_name

    assert first_unbound_name({}, {"a.py": "X = len(str(int('1')))\nY = isinstance(X, int)\n"}) == ""


def test_a_syntax_error_is_left_to_the_syntax_guard():
    from web.backend.services.remediation_fix import first_unbound_name

    assert first_unbound_name({}, {"a.py": "def broken(:\n"}) == ""


def test_non_python_is_ignored():
    from web.backend.services.remediation_fix import first_unbound_name

    assert first_unbound_name({}, {"Dockerfile": "FROM x\nRUN pip install y\n"}) == ""


def test_the_rules_do_not_forbid_an_already_declared_import():
    """The prompt contradicted itself: RULES said "do not add dependencies" while the
    criterion said "IMPORT oracle_core", and the model resolved it by not importing."""
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "m"}, {"a.py": "x=1\n"})
    assert "do not add dependencies." not in prompt
    assert "already declare" in prompt
    assert "is not \"adding a dependency\"" in prompt


# ── the model cannot see the Dockerfile, so the prompt has to say what is installed ──
# Live, in the model's own words: "Cannot compute ed25519 signature without a crypto library;
# no dependency available" — while `cryptography` and `aimarket-oracle-core` were both in that
# very image. The patch scope is source files; nothing in the prompt listed what may be
# imported, and "a library the build already declares is available" does not say WHICH.


def test_the_prompt_lists_what_is_installed():
    from web.backend.services.remediation_fix import build_prompt

    prompt = build_prompt({"finding_id": "m"}, {"a.py": "x=1\n"},
                          declared={"cryptography", "fastapi", "aimarket_oracle_core"})
    assert "ALREADY INSTALLED, IMPORT FREELY" in prompt
    assert "cryptography" in prompt and "aimarket_oracle_core" in prompt
    assert "Anything NOT in this list is." in prompt


def test_build_noise_is_kept_out_of_that_line():
    """A Dockerfile scan yields FROM, RUN, --no-cache-dir and friends; a list nobody can read
    is a list nobody reads."""
    from web.backend.services.remediation_fix import available_libraries

    line = available_libraries({"pip", "no", "cache", "dir", "usr", "local", "bin", "python",
                                "cryptography", "3", "ab"})
    assert "cryptography" in line
    for noise in ("pip,", "no,", "cache,", "usr,", " 3,", " ab,"):
        assert noise not in line


def test_no_declared_dependencies_adds_no_line():
    """Silence is better than an empty promise: a component whose build declares nothing
    should not be told it may import from an empty list."""
    from web.backend.services.remediation_fix import available_libraries, build_prompt

    assert available_libraries(set()) == ""
    assert available_libraries(None) == ""
    assert "ALREADY INSTALLED" not in build_prompt({"finding_id": "m"}, {"a.py": "x=1\n"})


def test_the_list_agrees_with_the_guard_that_refuses_imports():
    """One source of truth: what the prompt offers is exactly what the guard permits."""
    from web.backend.services.remediation_fix import available_libraries, new_third_party_imports

    declared = {"cryptography", "fastapi"}
    offered = available_libraries(declared)
    assert "cryptography" in offered
    before = {"a.py": "import os\n"}
    after = {"a.py": "import os\nimport cryptography\n"}
    assert new_third_party_imports(before, after, declared) == set()
    rogue = {"a.py": "import os\nimport requests\n"}
    assert new_third_party_imports(before, rogue, declared) == {"requests"}


# ── the list must be package NAMES, not every token in the build file ────────────
# Shipped once as a whole-file token scan: it looked right against a hand-made fixture and
# offered a live model `0.115`, `3.11_slim` and `against` to import. A list like that is worse
# than no list.


def test_a_real_dockerfile_yields_only_package_names():
    from pathlib import Path

    from web.backend.services.remediation_fix import _requirement_names

    text = (Path(__file__).resolve().parents[1] / "momus" / "canary" / "Dockerfile").read_text()
    names = _requirement_names("Dockerfile", text)
    assert names == {"aimarket_oracle_core", "cryptography", "fastapi", "uvicorn"}


def test_version_numbers_and_prose_never_appear():
    from web.backend.services.remediation_fix import _requirement_names

    text = (
        "# cryptography is here because a conforming canary must sign against a real key\n"
        "FROM python:3.11-slim\n"
        "WORKDIR /app\n"
        'RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30"\n'
        'CMD ["python", "-m", "canary.canary"]\n'
    )
    names = _requirement_names("Dockerfile", text)
    assert names == {"fastapi", "uvicorn"}
    for junk in ("0.115", "3.11_slim", "against", "python", "workdir", "app"):
        assert junk not in names


def test_a_continued_pip_line_is_read_whole():
    from web.backend.services.remediation_fix import _requirement_names

    text = 'RUN pip install --no-cache-dir "fastapi>=0.115" \\\n                "cryptography>=42"\n'
    assert _requirement_names("Dockerfile", text) == {"fastapi", "cryptography"}


def test_requirements_extras_markers_and_includes():
    from web.backend.services.remediation_fix import _requirement_names

    text = 'httpx>=0.27\n# a comment\n-r other.txt\npydantic[email]==2.5 ; python_version>"3.10"\n'
    assert _requirement_names("requirements.txt", text) == {"httpx", "pydantic"}


def test_pyproject_dependencies():
    from web.backend.services.remediation_fix import _requirement_names

    assert _requirement_names(
        "pyproject.toml", 'dependencies = ["anyio>=4", "rich"]') == {"anyio", "rich"}


def test_a_dockerfile_with_no_pip_install_declares_nothing():
    from web.backend.services.remediation_fix import _requirement_names

    assert _requirement_names("Dockerfile", "FROM scratch\nCOPY x /x\n") == set()


# ── the list must name what a patch would TYPE, not what pip installs ────────────
# `aimarket-oracle-core` on PyPI is `import oracle_core` in code. Offering the DISTRIBUTION
# name while the criterion names the MODULE is a contradiction a model resolves by importing
# neither — and the guard would have refused the very import the criterion demanded.


def test_a_vendor_prefixed_distribution_offers_its_module():
    from web.backend.services.remediation_fix import import_names_for

    names = import_names_for("aimarket-oracle-core")
    assert "oracle_core" in names
    assert "aimarket_oracle_core" in names


def test_an_ordinary_distribution_is_left_alone():
    from web.backend.services.remediation_fix import import_names_for

    assert import_names_for("cryptography") == {"cryptography"}


def test_a_short_name_is_not_mangled():
    """`py_` should not turn a two-letter package into nothing."""
    from web.backend.services.remediation_fix import import_names_for

    assert "py_ab" in import_names_for("py-ab")


def test_the_offer_and_the_guard_agree_on_the_module_name():
    from pathlib import Path

    from web.backend.services.remediation_fix import (
        _requirement_names,
        available_libraries,
        new_third_party_imports,
    )

    text = (Path(__file__).resolve().parents[1] / "momus" / "canary" / "Dockerfile").read_text()
    declared = _requirement_names("Dockerfile", text)

    offered = available_libraries(declared)
    assert "oracle_core" in offered, "the prompt must name what the patch would type"

    before = {"a.py": "import os\n"}
    after = {"a.py": "import os\nfrom oracle_core.signing import Signer\n"}
    assert new_third_party_imports(before, after, declared) == set(), \
        "the guard must permit exactly what the prompt offered"
    rogue = {"a.py": "import os\nimport requests\n"}
    assert new_third_party_imports(before, rogue, declared) == {"requests"}


# ── "import it, do not reimplement it" is an instruction to use something unseen ──
# The patch scope is the component's own files. Told to call a function whose contract is
# invisible, the model wrote its own — five times, each a plausible canonicalisation, each
# rejected by the gate. A definition it can READ is not scope: shown, and not patchable.


def test_a_module_named_in_the_criterion_is_resolved_and_shown(monkeypatch):
    from pathlib import Path

    from web.backend.services import remediation_fix as rf

    monkeypatch.setattr(rf, "app_root", lambda: str(Path(__file__).resolve().parents[1]))
    refs = rf.reference_sources(
        "Sign Ed25519 over oracle_core.signing.Signer.manifest_canonical(manifest) — IMPORT it",
        set())
    assert "oracles/core/oracle_core/signing.py" in refs
    assert "def manifest_canonical" in refs["oracles/core/oracle_core/signing.py"]


def test_a_file_already_in_the_patch_scope_is_not_repeated(monkeypatch):
    from pathlib import Path

    from web.backend.services import remediation_fix as rf

    monkeypatch.setattr(rf, "app_root", lambda: str(Path(__file__).resolve().parents[1]))
    refs = rf.reference_sources(
        "import oracle_core.signing.Signer", {"oracles/core/oracle_core/signing.py"})
    assert refs == {}


def test_a_criterion_naming_nothing_resolvable_adds_no_block(monkeypatch):
    from pathlib import Path

    from web.backend.services import remediation_fix as rf

    monkeypatch.setattr(rf, "app_root", lambda: str(Path(__file__).resolve().parents[1]))
    assert rf.reference_sources("the signature simply does not verify", set()) == {}
    assert rf.reference_sources("", set()) == {}


def test_reference_source_is_bounded(monkeypatch):
    from pathlib import Path

    from web.backend.services import remediation_fix as rf

    monkeypatch.setattr(rf, "app_root", lambda: str(Path(__file__).resolve().parents[1]))
    refs = rf.reference_sources("oracle_core.signing.Signer", set())
    for text in refs.values():
        assert len(text) <= rf.MAX_REFERENCE_CHARS


def test_the_reference_never_escapes_the_app_root(monkeypatch, tmp_path):
    """A dotted path is model-adjacent input; it must not read outside the tree."""
    from web.backend.services import remediation_fix as rf

    monkeypatch.setattr(rf, "app_root", lambda: str(tmp_path))
    assert rf.reference_sources("etc.passwd.shadow", set()) == {}


def test_the_prompt_marks_the_reference_read_only(monkeypatch):
    from pathlib import Path

    from web.backend.services import remediation_fix as rf

    monkeypatch.setattr(rf, "app_root", lambda: str(Path(__file__).resolve().parents[1]))
    prompt = rf.build_prompt(
        {"finding_id": "m",
         "evidence": {"response_snippet": "import oracle_core.signing.Signer to sign"}},
        {"a.py": "x=1\n"})
    assert "THE CODE THE CHECK ACTUALLY RUNS" in prompt
    assert "REFERENCE (read-only)" in prompt
    assert "you may not edit these files" in prompt
    assert "def manifest_canonical" in prompt


# ── the last rung: escalate the METHOD, not just the model ───────────────────────
# Three attempts by one model, each rejected on the same grounds, is three failures of one
# kind. A deliberating council is a different lever — and it is a peer service with its own
# budget, so it is called directly and never enters the provider table.


def test_the_council_is_off_until_a_url_is_given(monkeypatch):
    from web.backend.services.remediation_fix import COUNCIL_URL_ENV, council_target

    monkeypatch.delenv(COUNCIL_URL_ENV, raising=False)
    assert council_target(1) is None and council_target(9) is None


def test_it_is_the_last_rung_not_the_first(monkeypatch):
    from web.backend.services.remediation_fix import COUNCIL_URL_ENV, council_target

    monkeypatch.setenv(COUNCIL_URL_ENV, "https://metis.example/v1")
    assert council_target(1) is None
    assert council_target(2) is None
    assert council_target(3) is not None


def test_the_first_council_attempt_is_configurable(monkeypatch):
    from web.backend.services.remediation_fix import (
        COUNCIL_FROM_ATTEMPT_ENV,
        COUNCIL_URL_ENV,
        council_target,
    )

    monkeypatch.setenv(COUNCIL_URL_ENV, "https://metis.example/v1")
    monkeypatch.setenv(COUNCIL_FROM_ATTEMPT_ENV, "2")
    assert council_target(1) is None
    assert council_target(2) is not None


def test_a_trailing_slash_does_not_double_up(monkeypatch):
    from web.backend.services.remediation_fix import COUNCIL_URL_ENV, council_target

    monkeypatch.setenv(COUNCIL_URL_ENV, "https://metis.example/v1/")
    url, _, model = council_target(3)
    assert url == "https://metis.example/v1"
    assert model == "metis-council"


@pytest.mark.asyncio
async def test_the_council_reply_is_read_and_its_finish_reason_kept(monkeypatch):
    import httpx

    from llm.provider import GenerationConfig
    from web.backend.services.remediation_fix import _generate_via_council

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": '{"summary":"s","files":{}}'}}]}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            assert url.endswith("/chat/completions")
            assert headers.get("Authorization") == "Bearer k"
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    cfg = GenerationConfig()
    out = await _generate_via_council("https://m/v1", "k", "metis-council", "prompt", cfg)
    assert "summary" in out
    assert cfg.finish_reason == "stop"


@pytest.mark.asyncio
async def test_a_council_timeout_is_named_as_the_councils(monkeypatch):
    import httpx

    from llm.provider import GenerationConfig
    from web.backend.services.remediation_fix import FixRefused, _generate_via_council

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(FixRefused) as err:
        await _generate_via_council("https://m/v1", "", "metis-council", "p", GenerationConfig())
    assert "council did not answer" in str(err.value)


@pytest.mark.asyncio
async def test_an_unreachable_council_does_not_look_like_a_bad_patch(monkeypatch):
    import httpx

    from llm.provider import GenerationConfig
    from web.backend.services.remediation_fix import FixRefused, _generate_via_council

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(FixRefused) as err:
        await _generate_via_council("https://m/v1", "", "metis-council", "p", GenerationConfig())
    assert "unreachable" in str(err.value)


def test_the_council_has_its_own_longer_budget(monkeypatch):
    """A dozen model calls across several roles is not a single completion."""
    from web.backend.services.remediation_fix import (
        COUNCIL_TIMEOUT_ENV,
        DEFAULT_COUNCIL_TIMEOUT_S,
        LLM_BUDGET_S,
        council_timeout_s,
    )

    monkeypatch.delenv(COUNCIL_TIMEOUT_ENV, raising=False)
    assert council_timeout_s() == DEFAULT_COUNCIL_TIMEOUT_S
    assert council_timeout_s() > LLM_BUDGET_S, "the single-model ceiling would cut it off"

    monkeypatch.setenv(COUNCIL_TIMEOUT_ENV, "1234")
    assert council_timeout_s() == 1234.0
    monkeypatch.setenv(COUNCIL_TIMEOUT_ENV, "not-a-number")
    assert council_timeout_s() == DEFAULT_COUNCIL_TIMEOUT_S


@pytest.mark.asyncio
async def test_the_council_timeout_message_reports_its_own_budget(monkeypatch):
    import httpx

    from llm.provider import GenerationConfig
    from web.backend.services.remediation_fix import (
        COUNCIL_TIMEOUT_ENV,
        FixRefused,
        _generate_via_council,
    )

    monkeypatch.setenv(COUNCIL_TIMEOUT_ENV, "1200")

    class _Client:
        def __init__(self, *a, **kw):
            assert kw.get("timeout") == 1200.0, "the client must use the council's budget"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(FixRefused) as err:
        await _generate_via_council("https://m/v1", "", "metis-council", "p", GenerationConfig())
    assert "within 1200s" in str(err.value)


@pytest.mark.asyncio
async def test_a_council_abstention_is_reported_as_a_verdict(monkeypatch):
    """Seventeen minutes and a hundred thousand tokens reaching the ladder as "no content"
    told nobody anything. An abstention is a decision, and it says why."""
    import httpx

    from llm.provider import GenerationConfig
    from web.backend.services.remediation_fix import FixRefused, _generate_via_council

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"finish_reason": "abstained", "message": {
                "content": '{"abstained": true, "status": "low_confidence", "verify_score": 0.41}'}}]}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(FixRefused) as err:
        await _generate_via_council("https://m/v1", "", "metis-council", "p", GenerationConfig())
    assert "declined to answer" in str(err.value)
    assert "low_confidence" in str(err.value)


@pytest.mark.asyncio
async def test_the_council_is_told_there_is_nobody_to_ask(monkeypatch):
    """A council built for people asks "what did you mean?" — and it did, every time.

    Measured: `status: needs_clarification`, decided in a hundred seconds, with no human on
    the other end. In an autonomous loop that is the same as no answer: the attempt is spent.
    """
    import httpx

    from llm.provider import GenerationConfig
    from web.backend.services.remediation_fix import (
        AUTONOMOUS_CALLER_NOTE,
        _generate_via_council,
    )

    sent = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent["content"] = json["messages"][0]["content"]
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    await _generate_via_council("https://m/v1", "", "metis-council", "THE TASK",
                                GenerationConfig())

    assert AUTONOMOUS_CALLER_NOTE in sent["content"]
    assert "THE TASK" in sent["content"], "the note must not replace the task"
    assert sent["content"].index("nobody to ask") < sent["content"].index("THE TASK"), \
        "it has to be read before the task, not after it"


def test_the_note_offers_an_assumption_instead_of_a_question():
    from web.backend.services.remediation_fix import AUTONOMOUS_CALLER_NOTE

    lowered = AUTONOMOUS_CALLER_NOTE.lower()
    assert "nobody to ask" in lowered
    assert "assumption" in lowered or "reading you picked" in lowered
    # and it must not close the honest-refusal door the rest of the prompt opens
    assert "refusal" in lowered
