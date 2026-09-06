"""One repo, one group — the rule the profile README lacked.

DOLOS was listed three times: under "AIMarket", under "Community & broadcast", and under
"Observability & visualization". THEMIS, BASANOS, DIOSCURI, THEOROS, HELIOS and use-cases-portal
were each listed twice. Nothing caught it, because nothing asserted the taxonomy — the duplicates
were added for FINDABILITY, one row at a time, each individually reasonable.

Findability is now the A–Z index's job. These tests enforce the invariant that makes the index
sufficient:

  * every repo is a catalogue entry in exactly ONE role group;
  * every catalogue entry appears in the A–Z index, and the index invents nothing;
  * a security agent is never filed under Community or Observability, in ANY language.

The last one is the specific regression: a red team is not a community bot, and a tool that
*changes* a contract's state under attack is not an observability tool.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROFILE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "profile-readme"
EN = PROFILE_DIR / "README.md"
TRANSLATIONS = {lang: PROFILE_DIR / f"README.{lang}.md" for lang in ("ru", "es", "fr", "zh")}

#: Agents whose role is adversarial or gatekeeping. None of them belongs to a people-facing or
#: read-only-measurement group, however convenient the cross-listing looks.
SECURITY_AGENTS = ("themis", "basanos", "dolos", "momus", "treasury", "warden")


def _sections(text: str) -> dict[str, str]:
    """`### ` heading -> body, for the catalogue portion only."""
    parts = re.split(r"^### ", text, flags=re.M)[1:]
    out = {}
    for part in parts:
        head, _, body = part.partition("\n")
        out[head.strip()] = body
    return out


def _catalogue_groups(text: str) -> dict[str, list[str]]:
    """Role group -> repos listed as ENTRIES in it (bold-linked first cell)."""
    groups = {}
    for head, body in _sections(text).items():
        if head.startswith(("How it fits", "A–Z", "Next,", "Use it", "Run the")):
            continue
        repos = re.findall(r"^\| \[\*\*([a-z0-9-]+)\*\*\]", body, flags=re.M)
        if repos:
            groups[head] = repos
    return groups


def _index_entries(text: str) -> dict[str, str]:
    """repo -> the group name the A–Z index claims for it."""
    body = next(b for h, b in _sections(text).items() if h.startswith("A–Z"))
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^\| \[([a-z0-9-]+)\]\([^)]+\) \| ([^|]+) \|", body, flags=re.M)}


def test_every_repo_is_catalogued_exactly_once():
    seen: dict[str, list[str]] = {}
    for group, repos in _catalogue_groups(EN.read_text(encoding="utf-8")).items():
        for repo in repos:
            seen.setdefault(repo, []).append(group)
    duplicated = {r: g for r, g in seen.items() if len(g) > 1}
    assert not duplicated, f"repos listed in more than one group: {duplicated}"


def test_the_index_covers_the_catalogue_and_invents_nothing():
    text = EN.read_text(encoding="utf-8")
    catalogued = {r for repos in _catalogue_groups(text).values() for r in repos}
    indexed = set(_index_entries(text))
    assert not catalogued - indexed, f"catalogued but not in the A–Z index: {catalogued - indexed}"
    assert not indexed - catalogued, f"in the index but in no group: {indexed - catalogued}"


def test_the_index_anchor_exists_because_the_link_is_explicit():
    """A slug derived from an em-dash heading is fragile; the anchor is declared, not guessed."""
    text = EN.read_text(encoding="utf-8")
    assert '<a id="az"></a>' in text
    assert "(#az)" in text


@pytest.mark.parametrize("repo", SECURITY_AGENTS)
def test_security_agents_are_not_filed_under_community_or_observability(repo):
    for group, repos in _catalogue_groups(EN.read_text(encoding="utf-8")).items():
        if repo in repos:
            low = group.lower()
            assert "community" not in low and "observability" not in low, (repo, group)


def test_dolos_is_a_red_team_not_a_community_or_observability_tool():
    """The exact complaint, asserted by name so the fix cannot silently regress."""
    groups = _catalogue_groups(EN.read_text(encoding="utf-8"))
    homes = [g for g, repos in groups.items() if "dolos" in repos]
    assert len(homes) == 1, f"dolos appears in {homes}"
    assert "Trust & security" in homes[0], homes[0]


def test_observability_group_is_only_read_only_tools():
    """MOMUS/DOLOS/Treasury/GAIA/ATLAS used to sit here; they act, they do not merely measure."""
    groups = _catalogue_groups(EN.read_text(encoding="utf-8"))
    observability = next(repos for head, repos in groups.items() if "Observability" in head)
    assert set(observability) == {"alien-monitor", "logos", "skopos"}, observability


def test_community_group_is_only_people_facing():
    groups = _catalogue_groups(EN.read_text(encoding="utf-8"))
    community = next(repos for head, repos in groups.items() if "Community" in head)
    assert set(community) == {"dioscuri", "theoros", "helios"}, community


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_translations_use_the_same_grouping(lang):
    """The short versions carried ONE flat 'Agents' table mixing all four roles.

    They are summaries, so they list fewer repos — but a reader must not learn a different
    taxonomy from their own language.
    """
    text = TRANSLATIONS[lang].read_text(encoding="utf-8")
    # Four groups, keyed by the emoji rather than the translated words.
    for emoji in ("🛡", "🧮", "👤", "💬"):
        assert emoji in text, (lang, emoji)

    blocks = re.split(r"^#### ", text, flags=re.M)[1:]
    home = {}
    for block in blocks:
        head, _, body = block.partition("\n")
        for m in re.finditer(r"^\| \*\*([A-Za-z0-9-]+)\*\*", body, flags=re.M):
            home.setdefault(m.group(1).upper(), []).append(head.strip())

    for agent in ("THEMIS", "BASANOS", "DOLOS", "WARDEN", "MOMUS", "TREASURY"):
        assert home.get(agent), (lang, agent, "missing from every group")
        assert len(home[agent]) == 1, (lang, agent, home[agent])
        assert home[agent][0].startswith("🛡"), (lang, agent, home[agent])

    assert home["ARGUS-3"][0].startswith("👤"), (lang, home["ARGUS-3"])
    assert home["METIS"][0].startswith("🧮"), (lang, home["METIS"])
    for agent in ("DIOSCURI", "THEOROS", "HELIOS"):
        assert home[agent][0].startswith("💬"), (lang, agent, home[agent])


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_translations_point_at_the_english_index(lang):
    """A summary must say where the full catalogue is, and land on the declared anchor."""
    text = TRANSLATIONS[lang].read_text(encoding="utf-8")
    assert "README.md#az" in text, lang


def test_no_repo_link_was_lost_in_the_restructure():
    """The catalogue IS the sitemap: a repo linked in prose but in no group cannot be found.

    Currently every one of the 41 linked repos is catalogued, so this holds with no exemptions —
    if a future edit needs one, that is the signal the repo belongs in a group.
    """
    text = EN.read_text(encoding="utf-8")
    linked = set(re.findall(r"github\.com/alexar76/([a-z0-9-]+)", text))
    catalogued = {r for repos in _catalogue_groups(text).values() for r in repos}
    assert not linked - catalogued, f"linked but not catalogued: {sorted(linked - catalogued)}"
