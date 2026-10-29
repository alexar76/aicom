"""Release smoke test: run with the isolated consumer Python using -I.

Uses only the installed wheel and the example extracted from the built sdist.
Never connects to a registry or public MCP endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

from histor.toolcost_cli import _Stdio

import histor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert histor.__version__ == "0.5.0"
    assert "site-packages" in str(Path(histor.__file__).resolve())
    assert not Path(histor.__file__).resolve().is_relative_to(source)
    print(f"PASS installed wheel: aimarket-histor {histor.__version__}; {histor.__file__}")
    for name in tuple(os.environ):
        if name.startswith(("HISTOR_", "AIMARKET_", "AIFACTORY_")) or name in ("DATABASE_URL", "PYTHONPATH"):
            del os.environ[name]
    os.environ["HISTOR_DATA_DIR"] = str(out / "local-data")
    bundle = source / "examples/upgrade-brief"
    helpers = runpy.run_path(str(bundle / "verify.py"), run_name="release_fixture_helpers")
    expected = helpers["load"](bundle / "expected.json")
    inputs = sorted(path for path in bundle.rglob("*") if path.is_file())
    hashes = {path: helpers["digest"](path) for path in inputs}
    baseline = None
    english = None
    for lang, watchlist in helpers["WATCHLISTS"].items():
        target = out / lang
        command = [sys.executable, "-I", "-B", "-m", "histor", "upgrade-brief",
                   "--watchlist", str(bundle / watchlist), "--out-dir", str(target), "--lang", lang]
        first = None
        for _ in range(2):
            subprocess.run(command, cwd=out, check=True, capture_output=True, text=True, timeout=30)
            generated = {name: (target / name).read_bytes() for name in ("report.json", "report.md")}
            assert first is None or first == generated, f"{lang}: output not repeatable"
            first = generated
        report = json.loads(generated["report.json"])
        assert report["language"] == lang
        assert helpers["project"](report) == expected
        normalized = helpers["without_localized_text"](report)
        assert baseline is None or baseline == normalized, f"{lang}: analysis differs"
        baseline = normalized
        heading, check = helpers["EXPECTED_LOCALE_TEXT"][lang]
        assert "### " + heading in generated["report.md"].decode()
        research = next(dep for dep in report["dependencies"] if dep["id"] == "demo:research")
        archive = next(flow for flow in research["workflows"] if flow["id"] == "archive-import")
        assert archive["retest"][0]["check"] == check
        if lang == "en":
            english = generated
        print(f"PASS {lang}: expected findings, invariant analysis, localized checklist, repeatable reports")
    target = out / "en"
    subprocess.run([sys.executable, "-I", "-B", "-m", "histor", "upgrade-brief", "--watchlist",
                    str(bundle / "watchlist.json"), "--out-dir", str(target)],
                   cwd=out, check=True, capture_output=True, text=True, timeout=30)
    assert {name: (target / name).read_bytes() for name in ("report.json", "report.md")} == english
    assert all(helpers["digest"](path) == digest for path, digest in hashes.items())
    print("PASS default: English byte-identical to --lang en; fixed fixture inputs unchanged")
    os.chdir(out)
    client = _Stdio([sys.executable, "-I", "-B", "-m", "histor", "mcp"], time.monotonic() + 20)
    try:
        tools = client.tools()
        assert client.modern and client.protocol_version == "2026-07-28"
        assert {tool["name"] for tool in tools} == {"histor_check", "histor_changes", "histor_server"}
        assert client.server_info == {"name": "histor", "version": "0.5.0"}
        print("PASS installed MCP: server/discover then tools/list, protocol 2026-07-28, three advertised tools")
    finally:
        client.close()


if __name__ == "__main__":
    main()
