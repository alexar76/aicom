"""The update advisor's security properties, and the conflation that made its first answer wrong.

Two kinds of test here, and the second kind is the point.

**Correctness.** The first version of this checker compared `pyproject.toml` against the version a
service serves on the wire and reported "six of seven components are behind". Those are different
numbers in this tree, so every row was a conflation and the real state was zero drift. The
coherence tests pin the distinction so the comparison cannot silently go back to comparing a
packaging version with a runtime one.

**Refusal.** The rest assert what the checker will NOT do. A version string arrives from a network
response and ends up in a terminal and a chat message, and the recipe line ends up in a root
shell, so the interesting assertions are all negative: no non-https fetch, no cross-host redirect,
no echoing a string that failed the version gate, no command text derived from a response, and no
signing key created by a process whose whole job is reading.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_fleet_version_drift.py"


def _code_only(path: Path) -> str:
    """Source with comments and docstrings removed.

    These assertions are about what the code DOES. Scanning raw text instead makes a docstring
    that says "there is deliberately no enforce path" fail the test forbidding `enforce` — which
    is how the first run of this file failed three times on its own explanations.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _load():
    spec = importlib.util.spec_from_file_location("fleet_drift", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


# ── the conflation that made the first measurement wrong ─────────────────────────────────────


def test_packaging_and_runtime_versions_are_read_from_different_files(mod):
    """The bug in one assertion: these must never be the same source.

    `/health` and `.well-known` serve `__version__`; `pyproject.toml` is what gets published.
    Comparing a service's wire version against the packaging version measures nothing about
    deployment.
    """
    for probe in mod.FLEET:
        assert probe.pyproject.endswith("pyproject.toml")
        assert not probe.runtime_source.endswith("pyproject.toml"), probe.cid


def test_coherence_separates_tree_disagreement_from_fleet_drift(mod):
    assert mod.coherence("3.3.0", "3.2.1")[0] == "incoherent"
    assert mod.coherence("0.1.0", "0.1.0")[0] == "coherent"
    assert mod.coherence(None, "0.1.0")[0] == "unknown"
    # And drift is judged against the RUNTIME version, never the packaging one.
    assert mod.drift("3.2.1", "3.2.1")[0] == "match"
    assert mod.drift("3.3.0", "3.2.1")[0] == "behind"


def test_a_node_ahead_of_the_tree_is_not_reported_as_an_update(mod):
    state, reason = mod.drift("1.0.0", "1.1.0")
    assert state == "AHEAD"
    assert "not in this tree" in reason


def test_numeric_ordering_not_string_ordering(mod):
    """`"0.9.0" > "0.10.0"` is true as strings. It must not be true here."""
    assert mod.drift("0.10.0", "0.9.0")[0] == "behind"
    assert mod.drift("0.9.0", "0.10.0")[0] == "AHEAD"


# ── refusals: what reaches a terminal and a chat message ─────────────────────────────────────


@pytest.mark.parametrize("hostile", [
    "1.0.0\nsystemctl stop everything",          # forged line in the notifier's own voice
    "1.0.0\r\nfake: line",
    "1.0.0\x1b[2K\x1b[1A overwritten",           # ANSI: redraw the line above
    "1.0.0‮evissergeR",                      # bidi override
    "1.0.0​",                                # zero-width
    "1" * 100_000,                                # int() on this is a quadratic hang
    "1.0.0; rm -rf /",
    "<b>1.0.0</b>",
    "",
    "latest",
])
def test_hostile_version_strings_are_never_displayed(mod, hostile):
    assert not mod._SAFE_VERSION.match(hostile), hostile
    state, reason = mod.drift("1.0.0", hostile)
    assert state == "suspect"
    if hostile:                      # `"" in anything` is True; nothing to assert for it
        assert hostile not in reason, "the refused string must not be echoed in the reason"


@pytest.mark.parametrize("ok", ["1.0.0", "3.2.1", "0.1.0", "1.2.3.4", "1.0.0-rc.1", "2.0.0+build.5"])
def test_plain_versions_are_accepted(mod, ok):
    assert mod._SAFE_VERSION.match(ok), ok


def test_a_suspect_version_is_dropped_from_the_report_body(mod, monkeypatch):
    """Not merely unformatted — absent. `served_version` must be None when the gate refused it."""
    monkeypatch.setattr(mod, "observe", lambda p: {"served": "9.9.9\x1b[1A", "authority": "unsigned",
                                                   "detail": ""})
    report = mod.collect(["basanos"])
    row = report["components"][0]
    assert row["drift"] == "suspect"
    assert row["served_version"] is None
    assert "\x1b" not in json.dumps(report)


# ── refusals: the network ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [
    "http://modelmarket.dev/health",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
])
def test_only_https_is_fetched(mod, url):
    body, reason = mod._fetch_json(url)
    assert body is None
    assert "refused scheme" in reason


def test_every_probe_url_is_an_https_literal_in_the_registry(mod):
    """Structural: a URL that came from a response would make this an SSRF primitive."""
    source = SCRIPT.read_text(encoding="utf-8")
    for probe in mod.FLEET:
        assert probe.url.startswith("https://"), probe.cid
        assert f'"{probe.url}"' in source, f"{probe.cid}: url is not a literal in the registry"


def test_redirects_may_change_neither_host_nor_scheme(mod):
    """The handler is built per fetch, so exercise it the way urllib would."""
    import urllib.request

    captured = {}
    real_build = urllib.request.build_opener

    def spy(handler_cls):
        captured["handler"] = handler_cls
        return real_build(handler_cls)

    mod.urllib.request.build_opener = spy
    try:
        mod._fetch_json("https://example.invalid/nothing", timeout=0.01)
    finally:
        mod.urllib.request.build_opener = real_build

    handler = captured["handler"]()
    for bad in ("https://evil.example/x", "http://example.invalid/x", "file:///etc/passwd"):
        assert handler.redirect_request(_Req("https://example.invalid/nothing"), None, 302, "",
                                        {}, bad) is None, bad


class _Req:
    def __init__(self, url: str) -> None:
        self.full_url = url
        self.data = None

    def get_full_url(self) -> str:
        return self.full_url

    def get_method(self) -> str:
        return "GET"


def test_oversized_and_non_json_responses_are_refused_not_raised(mod, monkeypatch):
    class _Resp:
        def __init__(self, payload: bytes) -> None:
            self._p = payload

        def read(self, n: int) -> bytes:
            return self._p[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener_for(payload: bytes):
        class _O:
            def open(self, req, timeout=None):
                return _Resp(payload)
        return _O()

    monkeypatch.setattr(mod.urllib.request, "build_opener",
                        lambda *_a: opener_for(b"x" * (mod.MAX_BYTES + 1)))
    body, reason = mod._fetch_json("https://example.test/x")
    assert body is None and "over" in reason

    monkeypatch.setattr(mod.urllib.request, "build_opener", lambda *_a: opener_for(b"not json"))
    body, reason = mod._fetch_json("https://example.test/x")
    assert body is None and reason == "not JSON"

    monkeypatch.setattr(mod.urllib.request, "build_opener", lambda *_a: opener_for(b"[1,2,3]"))
    body, reason = mod._fetch_json("https://example.test/x")
    assert body is None and "not a JSON object" in reason


def test_no_credential_is_ever_attached(mod):
    """The stdlib re-sends `Authorization` across a cross-host redirect, so the safe answer is to
    have no credential on this path at all — the fleet's own endpoints are public."""
    code = _code_only(SCRIPT)
    for token in ("Authorization", "Bearer", "GITHUB_TOKEN", "api_key", "getenv", "environ",
                  "netrc", "auth="):
        assert token not in code, f"{token} appears in a checker that needs no credential"


# ── refusals: the recipe an operator will run ────────────────────────────────────────────────


def test_recipes_are_constants_in_the_registry(mod):
    source = SCRIPT.read_text(encoding="utf-8")
    for probe in mod.FLEET:
        assert f'recipe="{probe.recipe}"' in source, probe.cid


def test_every_recipe_naming_a_script_names_one_that_exists(mod):
    """A notification that tells an operator to run a missing script trains them to ignore it."""
    for probe in mod.FLEET:
        for word in probe.recipe.split():
            if word.startswith("scripts/") and word.endswith(".sh"):
                assert (ROOT / word).is_file(), f"{probe.cid}: {word} does not exist"


def test_advisory_output_never_contains_a_served_string_verbatim(mod, monkeypatch):
    monkeypatch.setattr(mod, "observe", lambda p: {"served": "0.0.1", "authority": "unsigned",
                                                   "detail": ""})
    report = mod.collect(["basanos"])
    text = mod.render(report, advisory=True)
    # The version may appear (it passed the gate); the point is that the RECIPE beside it is the
    # registry constant and not something assembled from the observation.
    assert "scripts/deploy_basanos.sh" in text
    assert "0.0.1" in text


# ── refusals: privilege ──────────────────────────────────────────────────────────────────────


def test_verification_is_keyless(mod):
    """An earlier version constructed a hub `Signer`, which GENERATES a keypair — and wrote one
    into `.git`. A read-only checker must not create key material."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Signer(" not in source, "constructing a Signer creates a private key"
    assert "verify_object_signature" in source


def test_the_signed_path_uses_object_canonical_not_manifest_canonical(mod):
    """`.well-known` is signed with `sign_object`. Verifying it with `manifest_canonical` returns a
    confident False that reads exactly like a bad signature — which is how the first run
    mis-reported all four hubs as unverified."""
    sig_source = (ROOT / "aimarket-hub" / "aimarket_hub" / "signing.py").read_text(encoding="utf-8")
    assert "def verify_object_signature" in sig_source
    assert "Signer.object_canonical(obj)" in sig_source
    assert "verify_manifest_signature" not in SCRIPT.read_text(encoding="utf-8")


def test_a_pin_is_required_and_a_mismatched_signer_is_distinguished(mod):
    ok, why = mod._verify_signed({"signature": {"value": "x", "public_key": "A"}}, "")
    assert ok is False and "no pin" in why
    ok, why = mod._verify_signed({"signature": {"value": "x", "public_key": "OTHER"}}, "MINE")
    assert ok is False and "does not match the pin" in why


def test_every_hub_probe_carries_a_pin(mod):
    for probe in mod.FLEET:
        if probe.kind == "signed_manifest":
            assert probe.pinned_key, probe.cid


# ── the level model ──────────────────────────────────────────────────────────────────────────


def test_there_is_no_apply_path(mod):
    """`enforce` is absent, not disabled. Nothing here may execute or schedule an update."""
    code = _code_only(SCRIPT)
    # Words like "docker" and "systemctl" DO appear — inside `recipe` and `note` strings, which is
    # the whole point of an advisory: it names the command for a human. What must be absent is any
    # means of running one.
    for forbidden in ("os.system", "check_call", "check_output", "Popen", "paramiko",
                      "os.execv", "eval(", "exec("):
        assert forbidden not in code, f"{forbidden} appears in a notification-only tier"
    # Exactly one subprocess call, and it only reads the tree's own revision.
    assert code.count("subprocess.run") == 1
    assert 'rev-parse' in code

    # And the recipes stay inert data: no f-string, concatenation or .format() builds one.
    for probe in mod.FLEET:
        assert f"recipe={probe.recipe!r}" in code or f'recipe="{probe.recipe}"' in code, probe.cid


def test_offline_mode_makes_no_request(mod, monkeypatch):
    def boom(*_a, **_kw):
        raise AssertionError("--offline must not touch the network")

    monkeypatch.setattr(mod, "_fetch_json", boom)
    report = mod.collect(offline=True)
    assert report["components"]
    assert all(r["authority"] == "not probed" for r in report["components"])


def test_exit_status_gates_on_findings(mod, monkeypatch):
    monkeypatch.setattr(mod, "observe", lambda p: {"served": None, "authority": "unreachable",
                                                   "detail": "x"})
    # basanos is the one coherent component, so with no observation there is nothing to report.
    assert mod.main(["--component", "basanos", "--offline"]) == 0
    # A hub is incoherent in the tree today, which is a finding on its own.
    assert mod.main(["--component", "hub-apex", "--offline"]) == 1
