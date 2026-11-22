"""The public catalogue the hearth serves at /agents/: hestia/docs/agents, built by
scripts/build_catalog.py and committed next to HESTIA so the image carries it.

These tests fail when it is no longer what the script builds from this repository now, or when
what it says about an agent's code is not that code.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_catalog  # noqa: E402

from hestia_agents.manifests import AGENTS, handler_source  # noqa: E402

COMMITTED = build_catalog.OUT


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(scope="module")
def fresh(tmp_path_factory) -> Path:
    if not (ROOT.parent / "hestia" / "hestia" / "sandbox.py").is_file():
        pytest.skip("the catalogue reads the hearth's limits from the sibling hestia/ checkout")
    out = tmp_path_factory.mktemp("catalogue") / "agents"
    assert build_catalog.build(out) == len(AGENTS)
    return out


def test_the_committed_catalogue_is_what_the_script_builds_now(fresh) -> None:
    if not COMMITTED.is_dir():
        pytest.skip("no committed catalogue next to this checkout")
    built, committed = _tree(fresh), _tree(COMMITTED)
    assert sorted(built) == sorted(committed), "files differ: run python3 scripts/build_catalog.py"
    stale = [name for name in built if built[name] != committed[name]]
    assert not stale, f"out of date: {stale}; run python3 scripts/build_catalog.py"


def test_the_same_tree_builds_the_same_bytes(fresh, tmp_path) -> None:
    build_catalog.build(tmp_path / "again")
    assert _tree(tmp_path / "again") == _tree(fresh)


def test_every_handler_is_published_byte_for_byte_with_its_digest(fresh) -> None:
    catalog = json.loads((fresh / "catalog.json").read_text(encoding="utf-8"))
    sums = dict(
        reversed(line.split("  ", 1)) for line in (fresh / "SHA256SUMS").read_text().splitlines()
    )
    assert [a["slug"] for a in catalog["agents"]] == list(AGENTS)
    for agent in catalog["agents"]:
        raw = (fresh / agent["source_file"]).read_bytes()
        assert raw == handler_source(agent["slug"]).encode("utf-8")
        assert (
            agent["handler_sha256"] == hashlib.sha256(raw).hexdigest() == sums[agent["source_file"]]
        )
        assert agent["handler_bytes"] == len(raw)


def test_sha256sums_covers_every_published_source_test_and_document(fresh) -> None:
    listed = {}
    for line in (fresh / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        listed[name] = digest
    on_disk = {name for name in _tree(fresh) if name.split("/", 1)[0] in {"src", "tests", "docs"}}
    assert set(listed) == on_disk
    for name, digest in listed.items():
        assert hashlib.sha256((fresh / name).read_bytes()).hexdigest() == digest, name


def test_every_page_links_only_to_files_it_publishes(fresh) -> None:
    for page in sorted(fresh.glob("index*.html")):
        text = page.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"#]+)"', text):
            # Outside links, the roster, and the hearth's own landing and fonts (served by HESTIA,
            # not by the catalogue; hestia's test_agent_catalogue checks they answer).
            if href.startswith(("https://", "/v1/", "/fonts/")) or href == "/":
                continue
            assert (fresh / href).is_file(), f"{page.name} links to {href}, which is not published"
        assert '<script src="live.js"></script>' in text


def test_the_live_check_has_its_words_in_every_language(fresh) -> None:
    keys = set(build_catalog.T_LIVE[""])
    for lang in build_catalog.LANGS:
        assert set(build_catalog.T_LIVE[lang]) == keys, lang
        text = (fresh / f"index{lang}.html").read_text(encoding="utf-8")
        words = json.loads(
            re.search(
                r'<script type="application/json" id="live-text">(.*?)</script>', text, re.S
            ).group(1)
        )
        used = set(re.findall(r"text\.(\w+)", build_catalog.LIVE_JS))
        assert {"live_summary", "live_failed", "owner_other", "owner_operator"} <= used
        for state in ("same", "differs", "absent", "nohash", "error"):
            assert f"live_{state}" in words, (lang, state)
        assert used <= set(words), (lang, used - set(words))
        # Every card carries the digest live.js compares the roster's handler_sha256 with.
        for slug in AGENTS:
            assert re.search(rf'data-agent="{re.escape(slug)}" data-sha="[0-9a-f]{{64}}"', text), (
                lang,
                slug,
            )


def test_recorded_replies_are_published_without_addresses_or_local_paths(fresh) -> None:
    catalog = json.loads((fresh / "catalog.json").read_text(encoding="utf-8"))
    removed = catalog["removed_from_recorded_data"]
    for name in (n for n in _tree(fresh) if n.startswith("tests/") and n.endswith(".json")):
        raw = (fresh / name).read_bytes()
        assert not build_catalog.EMAIL.search(raw), name
        assert not build_catalog.LOCAL_PATH.search(raw), name
        original = (ROOT / name).read_bytes()
        assert (raw == original) == (name not in removed), name
    # The tests themselves, the sources and the documents are published unedited.
    for name in (
        n
        for n in _tree(fresh)
        if not n.endswith(".json") and n.split("/", 1)[0] in {"tests", "docs"}
    ):
        assert (fresh / name).read_bytes() == (ROOT / name).read_bytes(), name


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        (b'"maintainers":[{"email":"someone@example.org"}]', False),
        (b"mailto:joe@ex.org>", False),
        (b"\\n\\n@mcp.tool()\\ndef add(a, b):", True),  # a decorator in a README, not n@mcp.tool
        (b"\\nfoo@bar.com", False),
        (b"capability x402@v1 and npm@10.2.0 and @scope/pkg@1.2.3", True),
    ],
)
def test_what_counts_as_an_address(raw: bytes, kept: bool) -> None:
    out, counts = build_catalog.redacted(raw)
    assert (out == raw) is kept and bool(counts) is not kept


def test_local_build_paths_are_removed_whole() -> None:
    raw = b'"_resolved":"/Users/someone/src/pkg/pkg-1.0.0.tgz","_from":"file:/home/ci/build/x.tgz"'
    out, counts = build_catalog.redacted(raw)
    assert counts == {"local_paths": 2}
    assert (
        b"someone" not in out and b"/home/" not in out and out.count(b"[local path removed]") == 2
    )
