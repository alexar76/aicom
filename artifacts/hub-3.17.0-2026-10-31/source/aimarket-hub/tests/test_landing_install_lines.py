"""The landing page must never tell a stranger to `pip install` a name we do not own.

On 2026-07-30 https://modelmarket.dev/examples was public, returned 200, and handed visitors 18
`pip install <name>` commands. Ten of those names were unregistered on PyPI:

    aimarket-provenance  aimarket-auction     aimarket-personas   aimarket-data-cap
    aimarket-nft         aimarket-orchestrator aimarket-streaming aimarket-promo
    aimarket-dataset     aimarket-zk

Anyone could have registered any of them — the `aimarket-*` prefix is now a coherent, visible
namespace with a live marketplace behind it, which is exactly what makes it worth squatting — and
every visitor following our own documentation would then have executed their setup.py. The page also
claimed "All 15 plugins installable via pip", which was false: 8 of the 18 were.

This repo has already been on the receiving end of the same class of bug from the other direction:
`pip install oracles/chronos` in a clean environment fetched a stranger's `oracle-core`. That was
the benign version — the stranger's package was harmless and the import failed loudly. A claimed
`aimarket-*` name would not fail loudly.

So the rule this file enforces is: an install command in customer-facing HTML names either a
distribution we have published, or a path in the repository. Nothing else. It is a static check —
no network — so it cannot flake, and it is deliberately about the HTML rather than about PyPI: the
question is not "is this name free today" but "are we telling people to fetch something we do not
control".
"""

from __future__ import annotations

import pathlib
import re

import pytest

LANDING = pathlib.Path(__file__).resolve().parents[1] / "aimarket_hub" / "landing.py"

#: Distributions this project has published and therefore controls. Verified against PyPI on
#: 2026-07-30; the ten plugin names above were registered by this project on 2026-07-31..08-02
#: (author AI-Factory, repository alexar76/aimarket-plugins) and verified again on 2026-10-21.
#: Adding a name here is a claim that we own it — check before you add, because the whole point
#: of the list is that it is not aspirational.
PUBLISHED = {
    "aimarket-agent",
    "aimarket-auction",
    "aimarket-channels",
    "aimarket-data-cap",
    "aimarket-dataset",
    "aimarket-hub",
    "aimarket-mcp",
    "aimarket-mcp-packager",
    "aimarket-metis",
    "aimarket-nft",
    "aimarket-oracle-core",
    "aimarket-oracle-gateway",
    "aimarket-orchestrator",
    "aimarket-personas",
    "aimarket-platon",
    "aimarket-promo",
    "aimarket-provenance",
    "aimarket-reputation",
    "aimarket-safety",
    "aimarket-streaming",
    "aimarket-tee",
    "aimarket-zk",
}

_INSTALL = re.compile(r"pip install\s+(?:-e\s+)?([^\s<`'\"]+)")


def _install_targets() -> list[str]:
    return _INSTALL.findall(LANDING.read_text())


def test_the_landing_page_has_install_lines_to_check():
    """If this file stops finding any, the regex has drifted and every check below is vacuous."""
    targets = _install_targets()
    assert len(targets) >= 15, f"only found {len(targets)} install targets in {LANDING}"


@pytest.mark.parametrize("target", sorted(set(_install_targets())))
def test_every_advertised_install_names_something_we_control(target):
    if target.startswith((".", "/", "plugins/", "oracles/", "aimarket-hub", "aimarket-agent")):
        # A path in the repository. `pip install -e plugins/x` cannot be hijacked by anyone.
        # (The two bare dist names in this branch are also published — asserted below.)
        if "/" in target:
            return
    dist = target.split("[", 1)[0].split("==", 1)[0].split(">=", 1)[0].lower()
    assert dist in PUBLISHED, (
        f"the landing page tells visitors to `pip install {target}`, but {dist!r} is not in the "
        f"published set. Either publish it first, or point the command at a repository path "
        f"(`pip install -e plugins/{dist}`). Advertising an unowned name invites someone to "
        f"register it and have their code run by people following our documentation."
    )


def test_no_unqualified_claim_that_every_plugin_is_on_pypi():
    """The old copy said 'All 15 plugins installable via pip' while 10 of them were not published.
    A count in prose drifts silently; the specific false claim is what this guards."""
    text = LANDING.read_text()
    assert "plugins installable via pip" not in text, (
        "the page claims every plugin is pip-installable. Say which ones are, or say neither."
    )


def test_unpublished_plugins_are_labelled_as_such():
    """A repo-path install with no explanation reads like a mistake; the label is what stops a
    reader from 'fixing' it back to `pip install <name>`."""
    text = LANDING.read_text()
    repo_installs = [t for t in _install_targets() if t.startswith("plugins/")]
    if not repo_installs:
        pytest.skip("no repo-path installs on the page")
    assert "not on PyPI yet" in text, (
        f"{len(repo_installs)} plugins install from the repo but the page does not say why"
    )
