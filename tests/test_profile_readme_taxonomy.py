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
SECURITY_AGENTS = ("themis", "basanos", "dolos", "momus", "treasury", "warden", "histor")


def _sections(text: str) -> dict[str, str]:
    """`### ` heading -> body, for the catalogue portion only. A repeated heading is an error:
    keyed by heading, the second copy would silently replace the first."""
    parts = re.split(r"^### ", text, flags=re.M)[1:]
    out = {}
    for part in parts:
        head, _, body = part.partition("\n")
        assert head.strip() not in out, f"duplicate heading: {head.strip()!r}"
        out[head.strip()] = body
    return out


#: A table row whose first cell is a repo or agent name in ANY emphasis — `**X**`, `[**X**](…)`,
#: `[X](…)`, any case. The catalogue's canonical form is only one of these; a misfiled row in
#: another form must not slip past the checks below.
_NAMED_ROW = re.compile(r"^\|\s*(?:\[\*\*([A-Za-z0-9-]+)\*\*\]\([^)]*\)|\*\*([A-Za-z0-9-]+)\*\*|\[([A-Za-z0-9-]+)\]\([^)]*\))\s*\|", re.M)
_CANONICAL_ROW = re.compile(r"^\| \[\*\*[a-z0-9-]+\*\*\]\(https://github\.com/alexar76/[a-z0-9-]+\) \|")
#: Where each named agent lives, by group emoji — the placements the old digest check enforced.
PLACEMENT = {**{a: "🛡" for a in SECURITY_AGENTS}, "argus": "👤", "metis": "🧮",
             "dioscuri": "💬", "theoros": "💬", "helios": "💬"}


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


def _groups_by_emoji(text: str) -> dict[str, list[str]]:
    """Role group -> repos, keyed by the heading's leading emoji so any two languages compare."""
    out: dict[str, list[str]] = {}
    for head, repos in _catalogue_groups(text).items():
        key = head.split(" ", 1)[0]
        assert key not in out, f"two catalogue groups share the key {key!r}"
        out[key] = repos
    return out


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_translations_use_the_same_grouping(lang):
    """A reader must not learn a different taxonomy from their own language.

    The translations once carried ONE flat 'Agents' table mixing all four roles, then an
    agents-only digest under `#### ` headings. Since the full locales (24ed02194) each one is
    the whole catalogue, so the check is the strongest one available: every group, keyed by its
    emoji rather than the translated words, lists exactly the repos the English group lists,
    in the same order — and the named placements below hold in every language.
    """
    text = TRANSLATIONS[lang].read_text(encoding="utf-8")
    for emoji in ("🛡", "🧮", "👤", "💬"):
        assert emoji in text, (lang, emoji)

    english = _groups_by_emoji(EN.read_text(encoding="utf-8"))
    translated = _groups_by_emoji(text)
    assert translated == english, (lang, {
        k: {"english": english.get(k), lang: translated.get(k)}
        for k in english.keys() | translated.keys() if english.get(k) != translated.get(k)
    })

    home: dict[str, list[str]] = {}
    for emoji, repos in translated.items():
        for repo in repos:
            home.setdefault(repo, []).append(emoji)

    english_home = {repo: emoji for emoji, repos in english.items() for repo in repos}
    for head, body in _sections(text).items():
        if head.startswith("A–Z"):
            continue  # the index lists every repo as [slug](…) by design
        key = head.split(" ", 1)[0]
        # A row naming a repo in ANY form — bold, linked or both, any case — is a catalogue entry:
        # it must be the canonical row and sit in the repo's English group. Rows naming anything
        # else (a Telegram channel, a stage) are not entries and are left alone.
        for m in _NAMED_ROW.finditer(body):
            name = (m.group(1) or m.group(2) or m.group(3)).lower().removesuffix("-3")
            if name not in english_home:
                continue
            row = body[m.start():].split("\n", 1)[0]
            assert _CANONICAL_ROW.match(row), (lang, head, row[:80])
            assert key == english_home[name], (lang, name, head)
            if name in PLACEMENT:
                assert key == PLACEMENT[name], (lang, name, head)
    for agent in SECURITY_AGENTS:
        assert home.get(agent) == ["🛡"], (lang, agent, home.get(agent))
    assert home.get("argus") == ["👤"], (lang, home.get("argus"))
    assert home.get("metis") == ["🧮"], (lang, home.get("metis"))
    for agent in ("dioscuri", "theoros", "helios"):
        assert home.get(agent) == ["💬"], (lang, agent, home.get(agent))


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_translation_index_covers_its_catalogue_and_invents_nothing(lang):
    """Each full locale has its own A–Z index; it obeys the same rule as the English one."""
    text = TRANSLATIONS[lang].read_text(encoding="utf-8")
    assert '<a id="az"></a>' in text and "(#az)" in text, lang
    catalogued = {r for repos in _catalogue_groups(text).values() for r in repos}
    indexed = set(_index_entries(text))
    assert not catalogued - indexed, (lang, "catalogued but not indexed", catalogued - indexed)
    assert not indexed - catalogued, (lang, "indexed but in no group", indexed - catalogued)


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_translations_point_at_the_english_index(lang):
    """The English index is the canonical one; a translation must say so and land on its anchor.

    Written for the summaries, which had no index of their own. A full locale does, but it is
    made from the English page and can lag behind it, so the pointer still earns its place.
    """
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
