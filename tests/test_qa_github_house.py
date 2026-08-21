"""QA GitHub-house file scan."""

from pathlib import Path
from unittest.mock import MagicMock

from agents.qa import QAAgent
from core.delivery_profile import FULL_SOFTWARE, MARKETING_LANDING


def _mk(tmp_path: Path) -> QAAgent:
    return QAAgent(llm_router=MagicMock(), data_root=str(tmp_path))


def test_github_house_flags_missing_readme(tmp_path: Path):
    qa = _mk(tmp_path)
    issues = qa._assess_github_house(
        "prod-x",
        [{"path": "index.html", "content": "<html lang='en'>"}],
        delivery_profile=MARKETING_LANDING,
        content_language="en",
    )
    titles = {i["title"] for i in issues}
    assert "GitHub house: missing README.md" in titles


def test_github_house_locale_readme_and_full_software_ci(tmp_path: Path):
    qa = _mk(tmp_path)
    issues = qa._assess_github_house(
        "prod-ru",
        [
            {
                "path": "README.md",
                "content": "# App\n<!-- aicom-readme-badges -->\n<img src='docs/badges/ci.svg' />\n",
            },
            {"path": "app.py", "content": "print(1)\n"},
        ],
        delivery_profile=FULL_SOFTWARE,
        content_language="ru",
    )
    titles = {i["title"] for i in issues}
    assert "GitHub house: missing README.ru.md" in titles
    assert "GitHub house: missing docs/en.md" in titles
    assert "GitHub house: missing CI workflow" in titles
    assert "GitHub house: missing release workflow" in titles
    assert "GitHub house: missing automated tests" in titles


def test_github_house_accepts_complete_tree(tmp_path: Path):
    qa = _mk(tmp_path)
    files = [
        {
            "path": "README.md",
            "content": (
                "# App\n<!-- aicom-readme-badges -->\n<img src='docs/badges/ci.svg' alt='CI' />\n"
                "```mermaid\nflowchart LR\nA-->B\n```\n"
            ),
        },
        {"path": "README.ru.md", "content": "# Приложение\n"},
        {"path": "docs/en.md", "content": "Guide\n"},
        {"path": "docs/ru.md", "content": "Гид\n"},
        {"path": ".github/workflows/ci.yml", "content": "name: ci\n"},
        {"path": ".github/workflows/release.yml", "content": "name: release\n"},
        {"path": "CHANGELOG.md", "content": "## [0.1.0]\n"},
        {"path": "LICENSE", "content": "MIT\n"},
        {"path": "tests/test_app.py", "content": "def test_ok():\n    assert True\n"},
    ]
    issues = qa._assess_github_house(
        "prod-ok",
        files,
        delivery_profile=FULL_SOFTWARE,
        content_language="ru",
    )
    assert issues == []
