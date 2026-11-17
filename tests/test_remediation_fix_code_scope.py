"""Code findings (MOMUS's `code` target) reach the fixer as `code:<area>` with one file to patch.

The fixer never takes a path from a ticket — except this one path, and only from the part MOMUS signed (the Blame
summary carries the finding title `<path>: <rule> in <function>`), only inside the ticket's own area, only for an
area the host enabled, and never past the denylist."""

from __future__ import annotations

import pytest

from web.backend.services import remediation_fix as rf


def ticket(component="code:ai-service-mesh", path="ai-service-mesh/backend/ai_service_mesh/security.py",
           rule="VX-FWD-HEADER-TRUST", function="client_ip"):
    return {"finding_id": "mom-c1", "component": component,
            "blame": {"finding_id": "mom-c1", "component": component,
                      "summary": f"{path}: {rule} in {function} — auto remediation"},
            "evidence": {"reference_artifacts": ["skopos/skopos/app_auth.py"]}}  # unsigned: never used


@pytest.fixture(autouse=True)
def areas(monkeypatch):
    monkeypatch.setenv(rf.CODE_AREAS_ENV, "ai-service-mesh,web")


def test_the_signed_title_names_the_one_file():
    assert rf.code_scope(ticket()) == ["ai-service-mesh/backend/ai_service_mesh/security.py"]


@pytest.mark.parametrize("bad", [
    ticket(component="code:metis"),                                        # area not enabled here
    ticket(path="web/backend/x.py"),                                       # file outside the ticket's area
    ticket(path="ai-service-mesh/../skopos/skopos/app_auth.py"),           # escape
    ticket(component="oracles"),                                           # not a code component
    {**ticket(), "blame": {"summary": "free-form text"}},                  # no title to read
])
def test_anything_else_gets_no_scope(bad):
    assert rf.code_scope(bad) == []


def test_the_denylist_still_wins(monkeypatch):
    monkeypatch.setenv(rf.CODE_AREAS_ENV, "momus,skopos")
    assert rf.code_scope(ticket(component="code:momus", path="momus/momus/app.py")) == []
    assert rf.code_scope(ticket(component="code:skopos", path="skopos/skopos/remediation/a2a_ingress.py")) == []


def test_check_ticket_admits_an_enabled_code_component(monkeypatch):
    monkeypatch.setattr(rf, "verify_blame", lambda blame, key: (True, "test"))
    assert rf.check_ticket(ticket()) == ("code:ai-service-mesh", "mom-c1")
    with pytest.raises(rf.FixRefused):
        rf.check_ticket(ticket(component="code:metis"))


def test_read_scope_reads_only_that_file(tmp_path, monkeypatch):
    f = tmp_path / "ai-service-mesh" / "backend" / "ai_service_mesh" / "security.py"
    f.parent.mkdir(parents=True)
    f.write_text("def client_ip(request):\n    return request.client.host\n")
    (tmp_path / "ai-service-mesh" / "other.py").write_text("x = 1\n")
    monkeypatch.setenv("AIFACTORY_APP_ROOT", str(tmp_path))
    monkeypatch.setattr(rf, "_audit_once", lambda: None)
    assert list(rf._read_scope("code:ai-service-mesh", ticket())) == [
        "ai-service-mesh/backend/ai_service_mesh/security.py"]


def test_code_findings_read_the_code_root_not_the_service_tree(tmp_path, monkeypatch):
    stale, fresh = tmp_path / "stale", tmp_path / "fresh"
    for root, text in ((stale, "OLD\n"), (fresh, "NEW\n")):
        f = root / "ai-service-mesh" / "backend" / "ai_service_mesh" / "security.py"
        f.parent.mkdir(parents=True)
        f.write_text(text)
    monkeypatch.setenv("AIFACTORY_APP_ROOT", str(stale))
    monkeypatch.setenv(rf.CODE_ROOT_ENV, str(fresh))
    monkeypatch.setattr(rf, "_audit_once", lambda: None)
    got = rf._read_scope("code:ai-service-mesh", ticket())
    assert list(got.values()) == ["NEW\n"]


def test_a_patch_that_only_silences_the_check_is_refused():
    before = {"web/x.py": "def f(url):\n    check(url)\n    return client.post(url)\n"}
    gamed = {"web/x.py": "def f(url):\n    check(url)\n    # vx-ok: connect to the address that was checked\n"
                         "    return client.post(url)\n"}
    assert "vx-ok" in rf.added_silencing_marks(before, gamed)
    assert "nosemgrep" in rf.added_silencing_marks(before, {"web/x.py": before["web/x.py"] + "x = 1  # nosemgrep\n"})
    kept = {"web/x.py": "# vx-ok: reviewed by a person in 2026-10\n" + before["web/x.py"]}
    assert rf.added_silencing_marks(kept, {"web/x.py": kept["web/x.py"] + "y = 2\n"}) == ""   # existing mark, kept


# --- guides and the rule self-check (2026-11-16: 3 of 5 verified branches were wrong) -----------------------------

from pathlib import Path  # noqa: E402

from web.backend.services import remediation_code_guides as guides  # noqa: E402

REPO = str(Path(__file__).resolve().parents[1])
WEB = "web/backend/api/ai_market_protocol_v2.py"
SEARCH = ticket(component="code:web", path=WEB, rule="VX-918-CHECK-THEN-CONNECT", function="search_v2")

BEFORE = '''
async def search_v2(intent):
    fed_url = _federation_hub_url()
    if not _federation_url_is_safe(fed_url):
        return {}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{fed_url}/ai-market/v2/search")
'''
SECOND_LOOKUP = '''
def _resolve_pinned_host(url):
    parsed = urlparse(url)
    infos = socket.getaddrinfo(parsed.hostname or "", 443, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("no answer")
    return parsed.scheme, infos[0][4][0], 443

async def search_v2(intent):
    fed_url = _federation_hub_url()
    if not _federation_url_is_safe(fed_url):
        return {}
    scheme, pinned_ip, port = _resolve_pinned_host(fed_url)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{scheme}://{pinned_ip}:{port}/ai-market/v2/search")
'''
PINNED = '''
async def search_v2(intent):
    fed_url = _federation_hub_url()
    if not _federation_url_is_safe(fed_url):
        return {}
    target, pin_headers, extensions = pin_target(fed_url + "/ai-market/v2/search")
    async with httpx.AsyncClient() as client:
        r = await client.get(target, headers=pin_headers, extensions=extensions)
'''


def test_the_rule_is_read_from_the_signed_summary_only():
    assert guides.rule_and_function(SEARCH) == ("VX-918-CHECK-THEN-CONNECT", "search_v2")
    assert guides.rule_and_function({**SEARCH, "blame": {}, "title": "x.py: VX-306-OPEN-WITHOUT-KEY in f"}) == ("", "")


def test_the_guide_shows_this_repo_s_own_fix_and_what_not_to_do():
    block = guides.guide_block(SEARCH, REPO, rf.read_is_denied, rf.redact_secrets)
    assert "def pin_target(" in block and "def _validated_ips(" in block and "sni_hostname" in block
    assert "def safe_get(" not in block                 # functions, not whole files
    assert "getaddrinfo (or a helper) again" in block and "vx-ok" in block
    assert guides.guide_block(ticket(rule="VX-NOPE"), REPO) == ""


def test_every_guide_reference_exists_in_the_checkout():
    for rule, guide in guides.GUIDES.items():
        for rel, names in guide["references"]:
            text = (Path(REPO) / rel).read_text(encoding="utf-8")
            for name in names:
                assert f"def {name}(" in text, (rule, rel, name)


def test_a_rewrite_that_still_matches_the_rule_is_caught_before_a_push():
    left = guides.still_matches(SEARCH, {WEB: BEFORE}, {WEB: SECOND_LOOKUP}, REPO)
    assert "VX-918-CHECK-THEN-CONNECT in search_v2" in left and "second lookup" in left
    assert guides.still_matches(SEARCH, {WEB: BEFORE}, {WEB: PINNED}, REPO) == ""
    marked = BEFORE.replace("        r = await", "        # vx-ok: pinned\n        r = await")
    assert guides.still_matches(SEARCH, {WEB: BEFORE}, {WEB: marked}, REPO)   # a new mark does not count


def test_the_prompt_for_a_code_finding_carries_the_guide():
    prompt = rf.build_prompt(SEARCH, {WEB: BEFORE}, guide=guides.guide_block(SEARCH, REPO))
    assert "HOW THIS CLASS OF BUG IS FIXED IN THIS REPOSITORY" in prompt and prompt.index("RULES") < prompt.index(
        "HOW THIS CLASS") < prompt.index("OUTPUT")
