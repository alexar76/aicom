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
            {"path": "README.md", "content": "# App\n<!-- aicom-readme-badges -->\n<img src='docs/badges/ci.svg' />\n"},
            {"path": "docs/badges/ci.svg", "content": "<svg/>\n"},
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
        {"path": "docs/badges/ci.svg", "content": "<svg/>\n"},
        {"path": ".github/workflows/ci.yml", "content": "name: ci\n"},
        {"path": ".github/workflows/release.yml", "content": "name: release\n"},
        {"path": "CHANGELOG.md", "content": "## [0.1.0]\n"},
        {"path": "LICENSE", "content": "MIT\n"},
        {"path": "CONTRIBUTING.md", "content": "# Contributing\n"},
        {"path": "tests/test_app.py", "content": "def test_ok():\n    assert True\n"},
    ]
    issues = qa._assess_github_house(
        "prod-ok",
        files,
        delivery_profile=FULL_SOFTWARE,
        content_language="ru",
    )
    assert issues == []


def test_github_house_flags_missing_contributing(tmp_path: Path):
    qa = _mk(tmp_path)
    issues = qa._assess_github_house(
        "prod-c",
        [
            {
                "path": "README.md",
                "content": "# App\n<!-- aicom-readme-badges -->\n<img src='docs/badges/ci.svg' />\n",
            },
            {"path": "index.html", "content": "<html lang='en'>"},
        ],
        delivery_profile=MARKETING_LANDING,
        content_language="en",
    )
    titles = {i["title"] for i in issues}
    assert "GitHub house: missing CONTRIBUTING.md" in titles


def test_github_house_ui_requires_admin_user_usecases_and_badge_files(tmp_path: Path):
    qa = _mk(tmp_path)
    issues = qa._assess_github_house(
        "prod-ui",
        [
            {
                "path": "README.md",
                "content": (
                    "# App\n<!-- aicom-readme-badges -->\n<img src='docs/badges/ci.svg' />\n"
                    "## Gallery\n| Still | Caption |\n| --- | --- |\n| docs/gallery/01.svg | x |\n"
                ),
            },
            {"path": "frontend/src/App.tsx", "content": "export default function App(){return null}\n"},
            {"path": "docs/en.md", "content": "Guide\n"},
            {"path": "docs/gallery/hero.svg", "content": "<svg/>\n"},
            {"path": "docs/gallery/01.svg", "content": "<svg/>\n"},
            {"path": "docs/gallery/02.svg", "content": "<svg/>\n"},
            {"path": ".github/workflows/ci.yml", "content": "name: ci\n"},
            {"path": ".github/workflows/release.yml", "content": "name: release\n"},
            {"path": "CHANGELOG.md", "content": "## [0.1.0]\n"},
            {"path": "LICENSE", "content": "MIT\n"},
            {"path": "CONTRIBUTING.md", "content": "# Contributing\n"},
            {"path": "tests/test_app.py", "content": "def test_ok():\n    assert True\n"},
        ],
        delivery_profile=FULL_SOFTWARE,
        content_language="en",
    )
    titles = {i["title"] for i in issues}
    assert "GitHub house: missing docs/admin.md" in titles
    assert "GitHub house: missing docs/user-guide.md" in titles
    assert "GitHub house: missing docs/use-cases.md" in titles
    assert "GitHub house: missing docs/badges/ci.svg" in titles
    assert "GitHub house: gallery table has no embedded images" in titles
    assert "GitHub house: README Docs section incomplete" in titles


def test_github_house_flags_dead_coverage_and_hero(tmp_path: Path):
    qa = _mk(tmp_path)
    issues = qa._assess_github_house(
        "prod-dead-img",
        [
            {
                "path": "README.md",
                "content": (
                    "# App\n<!-- aicom-readme-badges -->\n"
                    "<img src='docs/badges/ci.svg' alt='CI' />\n"
                    "<img src='docs/badges/coverage.svg' alt='coverage' />\n"
                    "<img src='docs/gallery/hero.svg' alt='Sentinel hero' />\n"
                ),
            },
            {"path": "docs/badges/ci.svg", "content": "<svg/>\n"},
            {"path": "CONTRIBUTING.md", "content": "# Contributing\n"},
            {"path": "index.html", "content": "<html lang='en'>"},
        ],
        delivery_profile=MARKETING_LANDING,
        content_language="en",
    )
    titles = {i["title"] for i in issues}
    assert "GitHub house: dead README image docs/badges/coverage.svg" in titles
    assert "GitHub house: dead README image docs/gallery/hero.svg" in titles
    assert "GitHub house: dead README image docs/badges/ci.svg" not in titles


def test_github_house_accepts_ui_packaging_complete(tmp_path: Path):
    qa = _mk(tmp_path)
    files = [
        {
            "path": "README.md",
            "content": (
                "# App\n<!-- aicom-readme-badges -->\n<img src='docs/badges/ci.svg' alt='CI' />\n"
                "<p align='center'><img src='docs/gallery/hero.svg' /></p>\n"
                "## Gallery\n| Still | Caption |\n| --- | --- |\n"
                "| ![w](docs/gallery/01.svg) | widget |\n"
                "## Docs\n- [Admin](docs/admin.md) · [User](docs/user-guide.md) · "
                "[Use cases](docs/use-cases.md) · [en](docs/en.md)\n"
            ),
        },
        {"path": "frontend/src/App.tsx", "content": "export default function App(){return null}\n"},
        {"path": "docs/en.md", "content": "Guide\n"},
        {"path": "docs/admin.md", "content": "Admin\n"},
        {"path": "docs/user-guide.md", "content": "User\n"},
        {"path": "docs/use-cases.md", "content": "Cases\n"},
        {"path": "docs/badges/ci.svg", "content": "<svg/>\n"},
        {"path": "docs/badges/license.svg", "content": "<svg/>\n"},
        {"path": "docs/gallery/hero.svg", "content": "<svg/>\n"},
        {"path": "docs/gallery/01.svg", "content": "<svg/>\n"},
        {"path": "docs/gallery/02.svg", "content": "<svg/>\n"},
        {"path": ".github/workflows/ci.yml", "content": "name: ci\n"},
        {"path": ".github/workflows/release.yml", "content": "name: release\n"},
        {"path": "CHANGELOG.md", "content": "## [0.1.0]\n"},
        {"path": "LICENSE", "content": "MIT\n"},
        {"path": "CONTRIBUTING.md", "content": "# Contributing\n"},
        {"path": "tests/test_app.py", "content": "def test_ok():\n    assert True\n"},
    ]
    issues = qa._assess_github_house(
        "prod-ui-ok",
        files,
        delivery_profile=FULL_SOFTWARE,
        content_language="en",
    )
    assert issues == []
