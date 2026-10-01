"""Keep the five-language free-tier docs honest about the code they describe.

These docs carry operational numbers — the allowance, the window, the env var that
sets them — and a reader acts on them. They had already drifted once: every
language still promised "3 invokes per sandbox visitor" long after production had
moved to 5 per hour, so a translation was not merely stale, it was wrong in the one
detail a caller needs.

So the checks below bind prose to source rather than to a snapshot of itself:

* env var and config-key names are read out of the implementing modules, not
  retyped here, so renaming a variable fails the test instead of silently
  invalidating five documents;
* every window the code supports must be documented, so adding a fifth window to
  ``_WINDOW_FORMATS`` cannot ship undocumented;
* the allowance and window must agree *across* languages, which is what catches a
  partial update — the failure mode a per-file check misses entirely.

Deliberately not asserted: prose wording, section prose length, or that the
documented number equals today's production setting. Production is an operator
dial (see the docs themselves); a test that pinned it would fail the moment someone
legitimately turns it, which trains people to ignore the suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

LANGS = ("", ".ru", ".es", ".fr", ".zh")
DOC_PATHS = [DOCS / f"free-and-paid-tiers{suffix}.md" for suffix in LANGS]

HUB_TRIALS = ROOT / "aimarket-hub" / "aimarket_hub" / "sandbox_trials.py"
ATLAS_GATE = ROOT / "atlas" / "atlas" / "payment_gate.py"
VERCEL_ADAPTER = ROOT / "web" / "backend" / "services" / "vercel_fullstack_adapter.py"


def _docs() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in DOC_PATHS]


def _windows_declared_in(source: Path) -> set[str]:
    """The window vocabulary the module actually implements."""
    if not source.is_file():
        pytest.skip(f"satellite not in this tree: {source}")
    text = source.read_text(encoding="utf-8")
    block = re.search(r"_WINDOW_FORMATS\s*=\s*\{(.*?)\}", text, re.S)
    assert block, f"{source.name}: no _WINDOW_FORMATS mapping to read"
    return set(re.findall(r'"(\w+)"\s*:', block.group(1)))


def test_all_five_languages_exist():
    missing = [p.name for p in DOC_PATHS if not p.is_file()]
    assert not missing, f"free-tier doc missing translations: {missing}"


def test_every_supported_window_is_documented_in_every_language():
    windows = _windows_declared_in(HUB_TRIALS)
    assert {"lifetime", "hourly", "daily", "weekly"} <= windows, windows
    for path, text in _docs():
        undocumented = sorted(w for w in windows if f"`{w}`" not in text)
        assert not undocumented, f"{path.name}: windows not documented: {undocumented}"


def test_atlas_and_hub_share_one_window_vocabulary():
    """One deal, not two. A caller reads the same words at either service."""
    hub, atlas = _windows_declared_in(HUB_TRIALS), _windows_declared_in(ATLAS_GATE)
    assert hub == atlas, f"window vocabularies diverged: hub={hub} atlas={atlas}"


def test_documented_env_vars_exist_in_the_code_that_reads_them():
    pairs = [
        (HUB_TRIALS, "AIMARKET_SANDBOX_QUOTA_WINDOW"),
        (HUB_TRIALS, "AIMARKET_SANDBOX_MAX_PER_VISITOR"),
        (HUB_TRIALS, "AIMARKET_SANDBOX_MAX_PER_IP_HOUR"),
        (ATLAS_GATE, "ATLAS_PAYMENT_ENFORCED"),
        (ATLAS_GATE, "ATLAS_TRIAL_WINDOW"),
        (ATLAS_GATE, "ATLAS_TRIAL_MAX_PER_CALLER"),
        (VERCEL_ADAPTER, "AIFACTORY_PRODUCT_WALLET_ADDRESS"),
        (VERCEL_ADAPTER, "AIFACTORY_PRODUCT_WALLET_CHAIN"),
    ]
    for source, var in pairs:
        if not source.is_file():
            pytest.skip(f"not in this tree: {source}")
        assert var in source.read_text(encoding="utf-8"), f"{source.name} does not read {var}"
        documented = [p.name for p, text in _docs() if var in text]
        assert len(documented) == len(DOC_PATHS), f"{var} documented only in {documented}"


def test_allowance_and_window_agree_across_languages():
    """A partial translation update is the failure a per-file check cannot see."""
    allowances, windows = {}, {}
    for path, text in _docs():
        found = re.search(r'"max_invokes_per_visitor":\s*(\d+)', text)
        assert found, f"{path.name}: no published allowance to check"
        allowances[path.name] = found.group(1)
        found_window = re.search(r'"quota_window":\s*"(\w+)"', text)
        assert found_window, f"{path.name}: no published window to check"
        windows[path.name] = found_window.group(1)
    assert len(set(allowances.values())) == 1, f"allowance disagrees: {allowances}"
    assert len(set(windows.values())) == 1, f"window disagrees: {windows}"


def test_the_stale_lifetime_promise_is_gone():
    """The exact drift this suite exists to prevent, in each language's wording."""
    stale = [
        "3 invokes per sandbox visitor",
        "3 вызова на посетителя песочницы",
        "3 invocaciones por visitante de sandbox",
        "3 invocations par visiteur de bac à sable",
        "每个沙盒访客 3 次调用",
    ]
    for path, text in _docs():
        hit = [s for s in stale if s in text]
        assert not hit, f"{path.name} still promises the retired lifetime tier: {hit}"


def test_refusals_are_documented_as_unbilled_in_every_language():
    """The property a caller most needs to trust before spending its first call."""
    for path, text in _docs():
        assert "ok: false" in text, f"{path.name}: the unbilled-refusal rule is not shown"
        assert "settle" in text, f"{path.name}: the check/settle split is not described"


def test_walletless_default_is_documented_in_every_language():
    for path, text in _docs():
        assert "WALLET_ENABLED" in text, f"{path.name}: walletless default not documented"


def test_language_switcher_links_all_translations():
    """A reader who cannot find their language is not served by it existing."""
    header = DOC_PATHS[0].read_text(encoding="utf-8").split("---", 1)[0]
    for suffix in LANGS[1:]:
        assert f"free-and-paid-tiers{suffix}.md" in header, f"no link to {suffix} version"
