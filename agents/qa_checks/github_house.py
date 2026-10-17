"""Whether a product reads like a real GitHub repository: the house checks."""

from __future__ import annotations

from pathlib import Path

from core.delivery_profile import MARKETING_LANDING


class GithubHouseMixin:
    """The GitHub house assessment."""

    def _assess_github_house(
        self,
        product_id: str,
        code_files: list[dict],
        *,
        delivery_profile: str,
        content_language: str | None,
    ) -> list[dict]:
        """Flag missing GitHub-house files (README, bilingual docs, CI, tests)."""
        issues: list[dict] = []
        if not code_files:
            return issues

        rels = []
        readme_text = ""
        for file_info in code_files:
            raw = str(file_info.get("path") or "").replace("\\", "/")
            rels.append(raw.lower())
            name = Path(raw).name.lower()
            if name == "readme.md":
                readme_text = str(file_info.get("content") or "")

        try:
            from core.paths import code_dir as product_code_dir

            root = product_code_dir(product_id)
            if root.is_dir():
                for fpath in root.rglob("*"):
                    if not fpath.is_file():
                        continue
                    rel = str(fpath.relative_to(root)).replace("\\", "/")
                    rels.append(rel.lower())
                    if fpath.name.lower() == "readme.md" and not readme_text:
                        try:
                            readme_text = fpath.read_text(encoding="utf-8", errors="replace")[:20000]
                        except OSError:
                            pass
        except Exception:
            pass

        def has_suffix(suffix: str) -> bool:
            needle = suffix.lower().lstrip("/")
            return any(p == needle or p.endswith("/" + needle) for p in rels)

        if not has_suffix("readme.md"):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing README.md",
                    "description": (
                        "Every shipped product needs a root README with badges, quick start, "
                        "and a hero or architecture diagram (GITHUB_HOUSE_CONTRACT)."
                    ),
                    "file": f"code/{product_id}/README.md",
                }
            )
        elif "aicom-readme-badges" not in readme_text and "docs/badges/" not in readme_text.lower():
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: README has no badge row",
                    "description": (
                        "README.md should wrap a badge row in <!-- aicom-readme-badges --> "
                        "and link docs/badges/*.svg (not shields.io workflow-status)."
                    ),
                    "file": f"code/{product_id}/README.md",
                }
            )
        if readme_text:
            try:
                from web.backend.services.github_house_assets import extract_readme_local_assets

                for rel in extract_readme_local_assets(readme_text):
                    if not has_suffix(rel):
                        issues.append(
                            {
                                "severity": "high",
                                "title": f"GitHub house: dead README image {rel}",
                                "description": (
                                    "GitHub renders a 404 <img> as the alt text (a blue link), "
                                    "not a badge or hero. Commit the file under the path the "
                                    "README already names — do not leave coverage/tests/hero as "
                                    "caption-only links."
                                ),
                                "file": f"code/{product_id}/{rel}",
                            }
                        )
            except Exception as exc:
                self._log("WARNING", f"README asset scan failed: {exc}")

        if not has_suffix("contributing.md"):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing CONTRIBUTING.md",
                    "description": (
                        "Ship a root CONTRIBUTING.md (how to run tests, PR expectations, no secrets). "
                        "Required for the factory product catalog / GitHub house bar."
                    ),
                    "file": f"code/{product_id}/CONTRIBUTING.md",
                }
            )

        lang = (content_language or "en").strip().lower().replace("_", "-")
        if lang and lang not in ("en", "auto", "default", ""):
            loc_readme = f"readme.{lang}.md"
            if not has_suffix(loc_readme):
                issues.append(
                    {
                        "severity": "high",
                        "title": f"GitHub house: missing README.{lang}.md",
                        "description": (
                            f"Product locale is {lang}; ship README.{lang}.md alongside English README.md."
                        ),
                        "file": f"code/{product_id}/README.{lang}.md",
                    }
                )
            if delivery_profile != MARKETING_LANDING and not has_suffix(f"docs/{lang}.md"):
                issues.append(
                    {
                        "severity": "medium",
                        "title": f"GitHub house: missing docs/{lang}.md",
                        "description": (
                            f"Operator guide must exist in the product locale ({lang}) as well as docs/en.md."
                        ),
                        "file": f"code/{product_id}/docs/{lang}.md",
                    }
                )

        has_ui = any(
            p.endswith((".html", ".tsx", ".jsx", ".vue"))
            or "/frontend/" in p
            or p.startswith("frontend/")
            for p in rels
        )
        gallery_svgs = [p for p in rels if "docs/gallery/" in p and p.endswith(".svg")]
        has_tests = any(
            "/tests/" in p
            or p.startswith("tests/")
            or Path(p).name.startswith("test_")
            or p.endswith((".test.ts", ".test.js", "_test.py"))
            for p in rels
        )
        mermaid_hero = "```mermaid" in readme_text.lower()

        if has_ui and not has_suffix("docs/gallery/hero.svg"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing docs/gallery/hero.svg",
                    "description": (
                        "Browser UI products need an original SVG hero above the fold "
                        "(docs/gallery/hero.svg, linked from README)."
                    ),
                    "file": f"code/{product_id}/docs/gallery/hero.svg",
                }
            )
        if has_ui and len(gallery_svgs) < 3:
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: thin gallery",
                    "description": (
                        "Ship hero.svg plus 2–4 stills in docs/gallery/ with a README gallery table."
                    ),
                    "file": f"code/{product_id}/docs/gallery/",
                }
            )
        if readme_text and not has_ui and not mermaid_hero:
            issues.append(
                {
                    "severity": "low",
                    "title": "GitHub house: README has no hero diagram",
                    "description": "CLI/API-only README should include a mermaid architecture (or sequence) diagram.",
                    "file": f"code/{product_id}/README.md",
                }
            )

        if delivery_profile == MARKETING_LANDING:
            if not has_tests:
                issues.append(
                    {
                        "severity": "medium",
                        "title": "GitHub house: missing smoke test",
                        "description": "Landings need at least a smoke test (html lang, in-page CTA/anchors).",
                        "file": f"code/{product_id}",
                    }
                )
            return issues

        if not has_suffix("docs/en.md"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing docs/en.md",
                    "description": "full_software needs an English operator guide at docs/en.md.",
                    "file": f"code/{product_id}/docs/en.md",
                }
            )

        # Product packaging: admin + user guide + use-cases, and badges that resolve.
        if delivery_profile != MARKETING_LANDING and has_ui:
            for rel, title, why in (
                (
                    "docs/admin.md",
                    "GitHub house: missing docs/admin.md",
                    "Ship an admin/deploy guide (env, funding, republish, failure table).",
                ),
                (
                    "docs/user-guide.md",
                    "GitHub house: missing docs/user-guide.md",
                    "Ship a short end-user / operator UI walkthrough.",
                ),
                (
                    "docs/use-cases.md",
                    "GitHub house: missing docs/use-cases.md",
                    "Ship who-it-is-for / not-for and 2–3 concrete journeys.",
                ),
            ):
                if not has_suffix(rel):
                    issues.append(
                        {
                            "severity": "high",
                            "title": title,
                            "description": why + " Required for factory product-catalog packaging.",
                            "file": f"code/{product_id}/{rel}",
                        }
                    )
            for badge in ("ci.svg", "license.svg"):
                if not has_suffix(f"docs/badges/{badge}"):
                    issues.append(
                        {
                            "severity": "high",
                            "title": f"GitHub house: missing docs/badges/{badge}",
                            "description": (
                                "README badge links must resolve to committed SVG files under "
                                "docs/badges/ (dead badge images fail catalog review)."
                            ),
                            "file": f"code/{product_id}/docs/badges/{badge}",
                        }
                    )
            if readme_text and "docs/gallery/" in readme_text.lower():
                # Only the lines that actually reference the gallery count. Looking for
                # `![`/`<img` anywhere in the README meant a single badge `<img>` at the
                # top satisfied this check, so a gallery table listing bare
                # `docs/gallery/01.svg` paths passed — which is precisely the shape the
                # finding is named for, and every README the factory writes has badges.
                _gallery_lines = [
                    line
                    for line in readme_text.splitlines()
                    if "docs/gallery/" in line.lower()
                ]
                _gallery_text = "\n".join(_gallery_lines)
                if "![" not in _gallery_text and "<img" not in _gallery_text.lower():
                    issues.append(
                        {
                            "severity": "medium",
                            "title": "GitHub house: gallery table has no embedded images",
                            "description": (
                                "Gallery rows must use markdown images "
                                "![caption](docs/gallery/…) or <img src=…>, not bare paths."
                            ),
                            "file": f"code/{product_id}/README.md",
                        }
                    )
            docs_links_ok = all(
                needle in readme_text.lower()
                for needle in ("docs/admin.md", "docs/user-guide.md", "docs/use-cases.md")
            )
            if readme_text and not docs_links_ok:
                issues.append(
                    {
                        "severity": "medium",
                        "title": "GitHub house: README Docs section incomplete",
                        "description": (
                            "README must link docs/admin.md, docs/user-guide.md, and "
                            "docs/use-cases.md so the repo explains what the product is for."
                        ),
                        "file": f"code/{product_id}/README.md",
                    }
                )
        if not has_suffix(".github/workflows/ci.yml") and not has_suffix(".github/workflows/ci.yaml"):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing CI workflow",
                    "description": "Ship .github/workflows/ci.yml (tests + coverage, fail below 60%).",
                    "file": f"code/{product_id}/.github/workflows/ci.yml",
                }
            )
        if not has_suffix(".github/workflows/release.yml") and not has_suffix(
            ".github/workflows/release.yaml"
        ):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing release workflow",
                    "description": "full_software ships .github/workflows/release.yml (GitHub Release on v* tags).",
                    "file": f"code/{product_id}/.github/workflows/release.yml",
                }
            )
        if not has_suffix("changelog.md"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing CHANGELOG.md",
                    "description": "Keep a Changelog starting at 0.1.0; release.yml reads it on v* tags.",
                    "file": f"code/{product_id}/CHANGELOG.md",
                }
            )
        if not has_suffix("license") and not has_suffix("license.md"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing LICENSE",
                    "description": "Ship an OSI LICENSE at the repo root (default MIT unless the spec names another).",
                    "file": f"code/{product_id}/LICENSE",
                }
            )
        if not has_tests:
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing automated tests",
                    "description": (
                        "full_software requires unit + behavior tests (and UI e2e when there is a browser surface)."
                    ),
                    "file": f"code/{product_id}",
                }
            )
        return issues
