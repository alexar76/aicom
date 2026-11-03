"""The operator path, as a stranger walks it: quickstart, add, doctor.

Walked from a clean machine on 2026-10-12 with the published package and the docs open:
quickstart printed five `export` lines that a new shell forgot, minted no admin token, and
listed only a priced sample, so the federation's sandbox had nothing of the newcomer's to
run; listing one's own API on one's own hub demanded a $10 stake paid to oneself. These pin
what replaced each of those.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from aimarket_hub import cli, envfile
from aimarket_hub.database import HubDatabase

_ENV_KEYS = (
    "AIMARKET_ENV_FILE", "AIMARKET_DB_PATH", "AIMARKET_SIGNING_KEY_PATH", "AIMARKET_HUB_NAME",
    "AIMARKET_HUB_URL", "AIMARKET_CREDITS_ENABLED", "AIMARKET_ORACLE_FAMILY_URL",
    "AIMARKET_PQC", "AIMARKET_ADMIN_TOKEN", "AIFACTORY_PROD",
    "AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "AIMARKET_X402_PAY_TO", "AIMARKET_PAYMENT_RECIPIENT",
)


@pytest.fixture
def stranger(tmp_path, monkeypatch):
    """A clean working directory and an environment with none of the hub's settings.

    The commands under test write `os.environ` themselves (that is how `serve` gets the saved
    settings), so the whole environment is restored afterwards: `monkeypatch.delenv` of an
    absent key records nothing, and a leaked AIMARKET_CREDITS_ENABLED=1 changed the outcome
    of thirty unrelated invoke tests that ran later in the same process.
    """
    saved = dict(os.environ)
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


def _db(root) -> HubDatabase:
    return HubDatabase(root / "data" / "hub.db")


# ── envfile ──────────────────────────────────────────────────────────────────────


def test_parse_reads_the_usual_dotenv_shapes():
    text = "# c\n\nA=1\nexport B=two\nC=\"three words\"\nD='4'\nbad line\nlower=x\nE=\n"
    assert envfile.parse(text) == {"A": "1", "B": "two", "C": "three words", "D": "4", "E": ""}


def test_the_environment_wins_over_the_file(stranger, monkeypatch):
    path = stranger / "data" / "aimarket.env"
    path.parent.mkdir()
    path.write_text("AIMARKET_HUB_NAME=from file\nAIMARKET_CREDITS_ENABLED=1\n")
    monkeypatch.setenv("AIMARKET_HUB_NAME", "from env")
    assert envfile.load().resolve() == path.resolve()
    assert os.environ["AIMARKET_HUB_NAME"] == "from env"
    assert os.environ["AIMARKET_CREDITS_ENABLED"] == "1"


def test_merge_never_changes_a_saved_value_and_update_does(stranger):
    path = stranger / "data" / "aimarket.env"
    assert envfile.merge(path, {"A": "1", "B": "2"}) == {"A": "1", "B": "2"}
    assert envfile.merge(path, {"A": "changed", "C": "3"}) == {"C": "3"}
    assert envfile.read(path) == {"A": "1", "B": "2", "C": "3"}
    envfile.update(path, {"A": "new", "D": "4"})
    assert envfile.read(path) == {"A": "new", "B": "2", "C": "3", "D": "4"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ── quickstart ───────────────────────────────────────────────────────────────────


def test_quickstart_saves_what_serve_needs_and_a_new_shell_gets_it_back(stranger, capsys):
    assert cli.main(["quickstart", "--name", "Stranger Hub", "--grant", "0"]) == 0
    path = stranger / "data" / "aimarket.env"
    saved = envfile.read(path)
    assert saved["AIMARKET_HUB_NAME"] == "Stranger Hub"
    assert saved["AIMARKET_CREDITS_ENABLED"] == "1"
    assert saved["AIMARKET_ORACLE_FAMILY_URL"] == "off"
    assert len(saved["AIMARKET_ADMIN_TOKEN"]) >= 40
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    out = capsys.readouterr().out
    assert saved["AIMARKET_ADMIN_TOKEN"] not in out  # a secret goes to the 0600 file, not the screen

    # "A new shell": nothing exported, and every command reads the file again. Plain pops:
    # monkeypatch.delenv would record the values quickstart just set and put them back after
    # the test, leaking them into the rest of the session; the fixture restores everything.
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    envfile.load()
    assert os.environ["AIMARKET_HUB_NAME"] == "Stranger Hub"
    assert os.environ["AIMARKET_ADMIN_TOKEN"] == saved["AIMARKET_ADMIN_TOKEN"]


def test_quickstart_lists_a_free_ping_for_the_sandbox_and_a_priced_hello(stranger):
    assert cli.main(["quickstart", "--grant", "0"]) == 0
    db = _db(stranger)
    ping = db.get_capability("hub-hello", "hub.ping@v1", source_hub="local")
    hello = db.get_capability("hub-hello", "hub.hello@v1", source_hub="local")
    assert ping is not None and ping.price_per_call_usd == 0.0
    assert hello is not None and hello.price_per_call_usd > 0
    # Static packs carry no URL: it would go stale on a move, and a private one fails the gate.
    assert "localhost" not in ping.prompt_template and "localhost" not in hello.prompt_template


def test_quickstart_is_idempotent_but_obeys_an_explicit_name(stranger):
    assert cli.main(["quickstart", "--grant", "0"]) == 0
    path = stranger / "data" / "aimarket.env"
    first = envfile.read(path)
    assert first["AIMARKET_HUB_NAME"] == "Unnamed hub"  # never "AIMarket Hub" by default
    assert cli.main(["quickstart", "--grant", "0"]) == 0
    assert envfile.read(path) == first  # same token, same name
    assert cli.main(["quickstart", "--grant", "0", "--name", "Renamed"]) == 0
    second = envfile.read(path)
    assert second["AIMARKET_HUB_NAME"] == "Renamed"
    assert second["AIMARKET_ADMIN_TOKEN"] == first["AIMARKET_ADMIN_TOKEN"]


def test_quickstart_names_a_public_hub_after_its_host(stranger):
    assert cli.main(["quickstart", "--grant", "0", "--url", "https://hub.example.org/"]) == 0
    saved = envfile.read(stranger / "data" / "aimarket.env")
    assert saved["AIMARKET_HUB_URL"] == "https://hub.example.org"
    assert saved["AIMARKET_HUB_NAME"] == "hub.example.org"


def test_quickstart_does_not_save_a_token_the_operator_already_set(stranger, monkeypatch):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "operator-managed-token-from-systemd")
    assert cli.main(["quickstart", "--grant", "0"]) == 0
    assert "AIMARKET_ADMIN_TOKEN" not in envfile.read(stranger / "data" / "aimarket.env")


# ── add ──────────────────────────────────────────────────────────────────────────


def test_add_lists_the_operators_api_with_no_stake(stranger, capsys):
    rc = cli.main([
        "add", "weather.now@v1", "--url", "https://api.example.org/weather",
        "--price", "0.002", "--pay-to", "0x000000000000000000000000000000000000dEaD",
        "--name", "Weather now", "--description", "Current weather for a city",
        "--input-schema", '{"type":"object","required":["city"],"properties":{"city":{"type":"string"}}}',
    ])
    assert rc == 0
    cap = _db(stranger).get_capability("weather", "weather.now@v1", source_hub="local")
    assert cap is not None
    assert cap.invoke_url == "https://api.example.org/weather"
    assert cap.payout_address == "0x000000000000000000000000000000000000dEaD"
    assert cap.publisher_id == ""  # operator-owned, like the quickstart samples
    assert cap.input_schema["required"] == ["city"]
    assert "the hub never holds it" in capsys.readouterr().out


def test_add_twice_updates_in_place(stranger, capsys):
    args = ["add", "echo.run@v1", "--url", "https://api.example.org/echo"]
    assert cli.main(args) == 0
    assert cli.main(args + ["--price", "0.01"]) == 0
    assert "updated" in capsys.readouterr().out
    assert _db(stranger).get_capability("echo", "echo.run@v1", source_hub="local").price_per_call_usd == 0.01


def test_add_warns_when_nobody_routed_from_another_hub_could_pay(stranger, monkeypatch, capsys):
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    assert cli.main(["add", "paid.thing@v1", "--url", "https://api.example.org/x", "--price", "0.05"]) == 0
    assert "A buyer routed from another hub cannot" in capsys.readouterr().out


@pytest.mark.parametrize("argv,needle", [
    (["add", "no-version", "--url", "https://a.example/x"], "must look like"),
    (["add", "ok.id@v1", "--url", "ftp://a.example/x"], "--url must be"),
    (["add", "ok.id@v1", "--url", "https://a.example/x", "--pay-to", "0x123"], "--pay-to must be"),
    (["add", "ok.id@v1", "--url", "https://a.example/x", "--price", "-1"], "--price must be"),
    (["add", "ok.id@v1", "--url", "https://a.example/x", "--provider-pubkey", "abc"], "32 bytes"),
    (["add", "ok.id@v1", "--url", "https://a.example/x", "--input-schema", "[1]"], "JSON object"),
])
def test_add_refuses_what_it_cannot_list(stranger, capsys, argv, needle):
    assert cli.main(argv) == 1
    assert needle in capsys.readouterr().out


def test_add_in_production_requires_the_provider_key(stranger, monkeypatch, capsys):
    monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "1")
    assert cli.main(["add", "ok.id@v1", "--url", "https://a.example/x"]) == 1
    assert "--provider-pubkey" in capsys.readouterr().out
    assert _db(stranger).get_capability("ok", "ok.id@v1", source_hub="local") is None


# ── doctor ───────────────────────────────────────────────────────────────────────


def _answers(monkeypatch):
    """The doctor's reachability check sees a hub at the made-up URL these tests use."""
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: httpx.Response(200, json={}))


def _fake_assay(verdict_checks):
    async def run_assay(url, **_kwargs):
        from aimarket_hub.federation_assay import score_verdict

        checks = [dict(c) for c in verdict_checks]
        return {"url": url, "verdict": score_verdict(checks), "checks": checks,
                "sandbox": {"attempted": True, "capability_id": "hub.ping@v1",
                            "probe_kind": "free", "http_status": 200}}
    return run_assay


_GOOD = [{"id": i, "ok": True} for i in (
    "url_public", "well_known_schema", "advertised_key", "manifest_schema", "manifest_signed",
    "manifest_fresh", "invoke_same_origin", "sandbox_probe", "sandbox_receipt_signed",
)]


def test_doctor_on_a_local_hub_says_what_it_would_be_once_public(stranger, monkeypatch, capsys):
    from aimarket_hub import federation_assay

    monkeypatch.setattr(federation_assay, "run_assay", _fake_assay(_GOOD))
    _answers(monkeypatch)
    assert cli.main(["doctor", "--url", "http://localhost:9083"]) == 1
    out = capsys.readouterr().out
    assert "url_public" in out and "once it is public" in out and "pass" in out
    # The guard it bypasses for a local dry run is put back.
    from aimarket_hub import crawler
    assert not crawler._url_is_safe("http://localhost:9083")


def test_doctor_explains_a_failed_check_and_exits_nonzero(stranger, monkeypatch, capsys):
    from aimarket_hub import federation_assay

    bad = [dict(c) for c in _GOOD]
    bad[-1] = {"id": "sandbox_receipt_signed", "ok": False, "detail": "no receipt"}
    bad[-2] = {"id": "sandbox_probe", "ok": False, "detail": "HTTP 500"}
    monkeypatch.setattr(federation_assay, "run_assay", _fake_assay(bad))
    _answers(monkeypatch)
    assert cli.main(["doctor", "--url", "https://hub.example.org"]) == 1
    out = capsys.readouterr().out
    assert "hub.ping@v1 for exactly this" in out
    assert "verdict" in out and "review" in out


def test_doctor_pass_prints_the_knock(stranger, monkeypatch, capsys):
    from aimarket_hub import federation_assay

    monkeypatch.setattr(federation_assay, "run_assay", _fake_assay(_GOOD))
    _answers(monkeypatch)
    assert cli.main(["doctor", "--url", "https://hub.example.org"]) == 0
    assert "/federation/announce" in capsys.readouterr().out


def test_doctor_prints_a_failed_check_in_full(stranger, monkeypatch, capsys):
    """The fix is in the second half of the detail; cut at 110 it read as a riddle."""
    from aimarket_hub import federation_assay
    from aimarket_hub.signing import signature_shape_problem

    said = signature_shape_problem("f9bhOPZYAAMm5OUZR+NLyNZ3GSNKVzY8n5F3+04P")
    bad = [dict(c) for c in _GOOD]
    bad[4] = {"id": "manifest_signed", "ok": False, "detail": said}
    monkeypatch.setattr(federation_assay, "run_assay", _fake_assay(bad))
    _answers(monkeypatch)
    assert cli.main(["doctor", "--url", "https://hub.example.org"]) == 1
    out = capsys.readouterr().out
    assert said in out and len(said) > 110
    assert "not an object (spec §7.3.1)" in out


def test_doctor_reports_an_assay_crash_as_our_bug(stranger, monkeypatch, capsys):
    """Whatever a peer publishes must come back as a failed check. If the assay raises anyway,
    the operator gets one readable line and where to report it — not a traceback."""
    from aimarket_hub import federation_assay

    async def crashes(url, **_kwargs):
        raise AttributeError("'str' object has no attribute 'get'")

    monkeypatch.setattr(federation_assay, "run_assay", crashes)
    _answers(monkeypatch)
    assert cli.main(["doctor", "--url", "https://hub.example.org"]) == 1
    out = capsys.readouterr().out
    assert "the assay itself crashed" in out and "not a verdict" in out
    assert "issues/new?template=admission.yml" in out
    assert "Traceback" not in out

    assert cli.main(["doctor", "--url", "https://hub.example.org", "--json"]) == 1
    body = json.loads(capsys.readouterr().out)
    assert body["verdict"] is None and body["assay_error"].startswith("AttributeError")


def test_doctor_with_nothing_running_says_start_it(stranger, capsys):
    assert cli.main(["doctor", "--url", "http://127.0.0.1:9"]) == 1
    out = capsys.readouterr().out
    assert "nothing answers" in out and "aimarket serve" in out
