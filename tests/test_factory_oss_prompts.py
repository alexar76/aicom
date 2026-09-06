"""GitHub-house contract is loaded into factory agent system prompts."""

from agents.prompts.load_prompt import load_prompt
from llm.agent_prompt_split import (
    build_architect_system_prompt,
    build_developer_system_prompt,
)
from llm.content_languages import LANGUAGE_SYSTEM


def test_github_house_contract_covers_readme_badges_release_docs():
    text = load_prompt("github_house_contract.md")
    for needle in (
        "GITHUB_HOUSE_CONTRACT",
        "aicom-readme-badges",
        "docs/gallery/hero.svg",
        "docs/en.md",
        "docs/admin.md",
        "docs/user-guide.md",
        "docs/use-cases.md",
        "README.<code>.md",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "≥70%",
        "GitHub Release",
        "softprops/action-gh-release",
        "--cov-fail-under=60",
        "Copy shapes",
        "CONTRIBUTING.md",
        "Badge files under `docs/badges/*.svg` must **exist on disk**",
    ):
        assert needle in text, needle


def test_language_system_docs_are_bilingual():
    assert "Docs exception" in LANGUAGE_SYSTEM
    assert "README.md` + `docs/en.md` are always English" in LANGUAGE_SYSTEM


def test_architect_system_injects_github_house():
    house = load_prompt("github_house_contract.md")
    sys = build_architect_system_prompt("ROLE: architect", github_house_contract=house)
    assert "GITHUB_HOUSE_CONTRACT" in sys
    assert "docs/gallery/hero.svg" in sys


def test_developer_system_injects_github_house():
    house = load_prompt("github_house_contract.md")
    sys = build_developer_system_prompt(
        core_prompt="DEV CORE",
        stack_rules="STACK",
        reference_shell_block="",
        fs_appendix="",
        polyglot_block="",
        patch_mode_note="",
        github_house_contract=house,
    )
    assert "DEV CORE" in sys
    assert "GITHUB_HOUSE_CONTRACT" in sys
    assert "aicom-readme-badges" in sys


def test_developer_system_injects_aimarket_native_agent():
    native = load_prompt("aimarket_native_agent.md")
    sys = build_developer_system_prompt(
        core_prompt="DEV CORE",
        stack_rules="STACK",
        reference_shell_block="",
        fs_appendix="",
        polyglot_block="",
        patch_mode_note="",
        aimarket_native_agent=native,
    )
    assert "X-Payment-Channel" in sys
    assert "/ai-market/v2/invoke" in sys
    assert "demo-atlas-key" in sys or "X-Agent-Key" in sys


def test_role_prompts_require_github_house():
    for name in (
        "developer_core_prompt.md",
        "qa_system_prompt.md",
        "devops_system_prompt.md",
        "architect_role_prompt.md",
        "pm_system_prompt_base.md",
        "pm_section_full.md",
        "pm_section_landing.md",
    ):
        text = load_prompt(name)
        assert "GITHUB_HOUSE" in text or "GitHub-house" in text or "github-house" in text, name
