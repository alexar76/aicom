"""warden.scan@v1: WARDEN's static scan in HESTIA's JavaScript sandbox, held against Node.

`warden_scan_expected.json` is what the same entry point (agents/warden-scan/src/entry.ts)
returned on 2026-11-20 when esbuild bundled it for Node with the real node:crypto, Buffer and
TextDecoder, for the six cases in `warden_scan_cases.json`: a clean tool, the classic
<IMPORTANT> poisoning, an instruction hidden in base64url (Buffer and TextDecoder), fullwidth
look-alikes with a fractional number (no canonical digest), a readOnlyHint tool, and (WARDEN
0.35.0, added the same day) hints their own descriptions contradict, with a look-alike sentence
that must not match. The
committed handler.js runs here in QuickJS-ng for WASI, through hestia.sandbox, and must give
the same answers byte for byte: the ruleset digest and the tool-set digests come from the
sha256 shim, the hidden payload from the base64 and UTF-8 shims.
"""
# ruff: noqa: E501 — long literal lines (recorded headers, generated glue)

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hestia_agents.manifests import AGENTS, AGENTS_DIR, deploy_body, handler_source

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASES = json.loads((HERE / "warden_scan_cases.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((HERE / "warden_scan_expected.json").read_text(encoding="utf-8"))
WARDEN_PACKAGE = ROOT.parent / "warden" / "package.json"
QJS = Path(os.environ.get("HESTIA_QJS_WASM", "/opt/qjs-wasi/qjs-wasi.wasm"))


@pytest.fixture(scope="module")
def box():
    if not QJS.is_file():
        pytest.skip("QuickJS for WASI is not installed (HESTIA_QJS_WASM)")
    try:
        from hestia.sandbox import Sandbox
    except ImportError:  # pragma: no cover - standalone checkout
        pytest.skip("sibling hestia/ sources are not on the path")
    sandbox = Sandbox(Path("/nonexistent/python.wasm"), Path("/nonexistent/lib"), qjs_wasm=QJS,
                      memory_mb=256, timeout_s=10.0)
    yield sandbox
    sandbox.close()


def test_the_manifest_ships_the_handler_as_javascript() -> None:
    body = deploy_body("warden-scan")
    assert body["source"] == {"kind": "template", "handler": handler_source("warden-scan"),
                              "language": "javascript"}
    assert "egress_hosts" not in body                  # the scan needs no network
    assert AGENTS["warden-scan"]["capability_id"] == "warden.scan@v1"


def test_the_bundle_names_the_warden_it_was_built_from() -> None:
    version = json.loads(WARDEN_PACKAGE.read_text(encoding="utf-8"))["version"] if WARDEN_PACKAGE.is_file() else None
    head = handler_source("warden-scan").splitlines()[0]
    assert head.startswith("// warden.scan@v1 for HESTIA: @aimarket/warden ")
    if version:
        assert f"@aimarket/warden {version} " in head


@pytest.mark.parametrize("index", range(len(CASES)))
def test_quickjs_answers_exactly_what_node_answers(box, index) -> None:
    out = box.run(handler_source("warden-scan"), CASES[index], language="javascript")
    assert out.kind == "ok", out
    answer = dict(out.result)
    assert answer.pop("warden") == handler_source("warden-scan").split("@aimarket/warden ")[1].split(" ")[0]
    assert answer == EXPECTED[index]


def test_what_the_cases_show(box) -> None:
    verdicts = [(e["verdict"], [f["code"] for f in e["findings"]]) for e in EXPECTED]
    assert verdicts[0] == ("allow", [])
    assert verdicts[1] == ("block", ["TOOL_DEF_INJECTION"])
    assert verdicts[2][0] == "block"                   # found only after decoding the base64url
    assert EXPECTED[3]["tools_sha256"] is None and "non-integer" in EXPECTED[3]["tools_sha256_note"]
    assert {e["ruleset"]["version"] for e in EXPECTED} == {"23"}
    hints = [(f["tool"], f["code"], f["advisory"]) for f in EXPECTED[5]["findings"]]
    assert EXPECTED[5]["verdict"] == "allow"            # advisory: reported, never blocking
    assert hints == [("update_issue_labels", "TOOL_HINT_CONTRADICTS_DESCRIPTION", True),
                     ("remove_file", "TOOL_HINT_CONTRADICTS_DESCRIPTION", True)]


def test_the_probe_is_blocked_and_bad_input_is_refused(box) -> None:
    source = handler_source("warden-scan")
    out = box.run(source, AGENTS["warden-scan"]["probe"], language="javascript")
    assert out.kind == "ok" and out.result["verdict"] == "block"
    for payload, says in (({}, "send tools"), ({"tools": []}, "send tools"),
                          ({"tools": [{"description": "x"}]}, "has no name"),
                          ({"tools": [{"name": "a"}], "block_at": "severe"}, "block_at")):
        bad = box.run(source, payload, language="javascript")
        assert bad.kind == "error" and says in bad.error, (payload, bad)
    many = {"tools": [{"name": f"t{i}", "description": "d"} for i in range(501)]}
    assert "at most 500" in box.run(source, many, language="javascript").error


def test_a_whole_tools_list_result_is_accepted(box) -> None:
    wrapped = {"tools": {"tools": CASES[1]["tools"], "nextCursor": None}}
    out = box.run(handler_source("warden-scan"), wrapped, language="javascript")
    assert out.result["verdict"] == "block"


def test_the_committed_bundle_is_what_the_build_script_makes(tmp_path) -> None:
    esbuild = os.environ.get("ESBUILD") or shutil.which("esbuild")
    if not esbuild or not WARDEN_PACKAGE.is_file():
        pytest.skip("no esbuild (set ESBUILD) or no warden/ sources beside this package")
    out = tmp_path / "handler.js"
    subprocess.run([str(ROOT / "scripts" / "build_warden_scan.sh"), str(out)], check=True,
                   env={**os.environ, "ESBUILD": esbuild}, capture_output=True)
    assert out.read_text(encoding="utf-8") == (AGENTS_DIR / "warden-scan" / "handler.js").read_text(encoding="utf-8")
