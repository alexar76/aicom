"""README assets must exist so GitHub does not render alt text as a link."""

from pathlib import Path

from web.backend.services.github_house_assets import (
    apply_github_house_asset_autofix,
    extract_readme_local_assets,
    missing_readme_assets,
)


def test_extract_readme_local_assets():
    text = (
        '<img src="docs/badges/coverage.svg" alt="coverage" />\n'
        '<img src="docs/gallery/hero.svg" alt="Sentinel hero" />\n'
        "| ![w](docs/gallery/01-widget.png) | widget |\n"
    )
    assert extract_readme_local_assets(text) == [
        "docs/badges/coverage.svg",
        "docs/gallery/hero.svg",
        "docs/gallery/01-widget.png",
    ]


def test_missing_readme_assets(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        '<img src="docs/badges/ci.svg" alt="CI" />\n'
        '<img src="docs/badges/coverage.svg" alt="coverage" />\n'
        '<img src="docs/gallery/hero.svg" alt="Sentinel hero" />\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "badges").mkdir(parents=True)
    (tmp_path / "docs" / "badges" / "ci.svg").write_text("<svg/>\n", encoding="utf-8")
    assert missing_readme_assets(tmp_path) == [
        "docs/badges/coverage.svg",
        "docs/gallery/hero.svg",
    ]


def test_autofix_writes_badge_svgs_not_a_fake_hero(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        '<img src="docs/badges/coverage.svg" alt="coverage" />\n'
        '<img src="docs/badges/tests.svg" alt="tests" />\n'
        '<img src="docs/gallery/hero.svg" alt="Sentinel hero" />\n'
        "| Still | Caption |\n| --- | --- |\n| docs/gallery/01.svg | widget |\n",
        encoding="utf-8",
    )
    notes = apply_github_house_asset_autofix(tmp_path)
    assert "docs/badges/coverage.svg" in notes
    assert "docs/badges/tests.svg" in notes
    assert (tmp_path / "docs" / "badges" / "coverage.svg").is_file()
    assert (tmp_path / "docs" / "badges" / "tests.svg").is_file()
    assert not (tmp_path / "docs" / "gallery" / "hero.svg").exists()
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "![01](docs/gallery/01.svg)" in readme
    assert missing_readme_assets(tmp_path) == [
        "docs/gallery/hero.svg",
        "docs/gallery/01.svg",
    ]
