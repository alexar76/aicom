from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_finished_tutorial_repository_matches_the_monorepo_contract():
    repository = ROOT / "themis"
    required_files = (
        "agent.py",
        "auditor.py",
        "models.py",
        "metis_advisor.py",
        "provider_signing.py",
        "capability.json",
        "Dockerfile",
        "SECURITY.md",
        "examples/safe_candidate.json",
        "uv.lock",
    )
    assert repository.is_dir()
    assert all((repository / relative).is_file() for relative in required_files)


def test_five_language_tutorial_links_to_the_finished_repository():
    tutorial_root = ROOT / "create-aimarket-agent" / "docs" / "tutorials"
    reference_url = "https://github.com/alexar76/themis"
    tutorials = sorted(tutorial_root.glob("themis.*.md"))
    assert len(tutorials) == 5
    assert all(reference_url in path.read_text(encoding="utf-8") for path in tutorials)
