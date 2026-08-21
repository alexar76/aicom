"""Delivery mode is a property of the product, not of one round's write list.

This was the root cause of the plateau, and it is the most expensive kind: two rules in direct
contradiction where the one nobody was looking at won.

The developer prompt says "return only the files you actually modified", with the measurement
attached. ``validate_saved_files`` then checked that write list for an ``.html`` file — so a
repair round that edits three backend modules was told *"Web stack requires at least one .html
file (e.g. index.html)"* and the entire round was discarded after three attempts. Only a round
that rewrote the whole tree could pass. The check was therefore **forcing** the sprawling rounds
that then measured worse than the baseline and were reverted by the round guard.

Measured on production: eight such rejections in two hours, including every batched round after
batching went live. The baseline sat at 41 through ten reverts because the focused rounds never
reached QA at all.

The split that fixes it: **presence** is judged against the write list plus the tree (an
``.html`` that already exists still exists), while **forbidden** files are judged against the
write list alone — a round must not introduce a banned file, but holding it responsible for one
that was already there would make an unrelated repair unlandable, which is the same trap one
level down.
"""

from __future__ import annotations

import pytest

from agents.dev_delivery import DeliveryMode, validate_saved_files

FOCUSED_BACKEND = [
    "backend/app/services/atlas_client.py",
    "backend/app/models/audit.py",
]
TREE = FOCUSED_BACKEND + ["frontend/index.html", "frontend/src/App.tsx", "package.json"]


def test_a_focused_repair_round_is_legal():
    """The exact rejection seen eight times on production."""
    ok, msg = validate_saved_files(DeliveryMode.WEB_APP, FOCUSED_BACKEND, TREE)
    assert ok, msg


def test_a_product_with_no_html_is_still_rejected():
    """The check must keep doing its job — a web product does need an entry document."""
    ok, msg = validate_saved_files(DeliveryMode.WEB_APP, FOCUSED_BACKEND, FOCUSED_BACKEND)
    assert not ok
    assert ".html" in msg


def test_the_old_behaviour_without_a_tree_is_preserved():
    """Callers that pass no tree get the previous semantics, so nothing else shifts silently."""
    ok, _ = validate_saved_files(DeliveryMode.WEB_APP, FOCUSED_BACKEND)
    assert not ok
    ok, _ = validate_saved_files(DeliveryMode.WEB_APP, ["frontend/index.html"])
    assert ok


def test_forbidden_files_are_still_judged_on_this_round_alone():
    """Presence widened; prohibition did not.

    A CLI product that already contains a stray .html must not make every later repair round
    illegal — that is the same trap this fix exists to remove. But a round that *adds* one is
    still refused.
    """
    ok, _ = validate_saved_files(
        DeliveryMode.PYTHON_CLI, ["cli/main.py"], ["cli/main.py", "docs/legacy.html"]
    )
    assert ok, "a pre-existing stray file blocked an unrelated repair"

    ok, msg = validate_saved_files(
        DeliveryMode.PYTHON_CLI, ["cli/main.py", "cli/ui.html"], ["cli/main.py"]
    )
    assert not ok and "forbids web markup" in msg


def test_a_cli_round_touching_no_python_is_legal_when_the_tree_has_some():
    """Editing only a README in a CLI product is a legitimate round."""
    ok, msg = validate_saved_files(
        DeliveryMode.PYTHON_CLI, ["README.md"], ["cli/main.py", "README.md"]
    )
    assert ok, msg


@pytest.mark.parametrize(
    "tree",
    [
        ["src-tauri/Cargo.toml", "ui/index.html"],
        ["pubspec.yaml", "lib/main.dart"],
        ["package.json", "public/index.html"],
    ],
)
def test_desktop_presence_also_reads_the_tree(tree):
    """All three desktop stacks are presence checks and had the same defect."""
    ok, msg = validate_saved_files(DeliveryMode.DESKTOP_APP, ["lib/service.dart"], tree)
    assert ok, msg


def test_the_developer_passes_the_tree():
    """Structural: the fix is inert unless the call site supplies what is on disk."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "validate_saved_files(\n                    mode, saved_relative_paths, existing_on_disk\n                )" in src, (
        "the developer still validates against its own write list only"
    )
    assert "iter_product_files(code_root" in src


# --- the other two halves of the same vicious circle -------------------------------------


def test_a_repair_retry_does_not_order_a_rebuild():
    """The circle that produced ten reverts with the baseline never moving.

    A focused round failed delivery validation for having no .html; the retry said "Regenerate
    the entire JSON output"; the full rebuild then passed validation, reached QA, measured worse
    than the baseline and was reverted. Every part of that loop was a rule, not a model choice.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    # Slice the whole retry-note region: anchoring on the message text itself lands inside the
    # comment that explains the fix, which puts the branch above it outside the window.
    start = src.index("correction_note = \"\"")
    circle = src[start : src.index("system_prompt = build_developer_system_prompt", start)]
    assert "if patch_mode:" in circle, "the retry note does not distinguish a repair"
    assert "ONLY" in circle and "the files this repair touches" in circle
    assert "Do not rebuild the product to " in circle
    # A first build legitimately regenerates everything, so that branch must survive.
    assert "Regenerate the entire JSON output" in circle


def test_the_house_contract_is_not_demanded_on_every_repair():
    """"always" plus "emit those files" is a dozen-plus files on every response.

    It contradicted "return only the files you actually modified" three paragraphs above, and the
    unscoped batch returned 21 files while its siblings returned 3 and 1 — it was obeying this.
    """
    from pathlib import Path

    prompt = (
        Path(__file__).resolve().parents[1] / "agents" / "prompts" / "developer_core_prompt.md"
    ).read_text(encoding="utf-8")
    assert "=== GITHUB HOUSE (always" not in prompt, "the house is still demanded every round"
    assert "In a repair round this section does not apply" in prompt
    assert "Missing required house-contract files" in prompt, (
        "the round is not told what does ask for a house file, so it will guess"
    )
    # The initial build still has to produce them.
    assert "GITHUB_HOUSE_CONTRACT" in prompt
