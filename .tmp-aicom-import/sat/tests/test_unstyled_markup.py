""""Where is the design?" — asked by a person looking at a deploy with nine green gates.

The published product rendered as bare HTML: a heading, some links, two tiny inputs, no layout. The
build compiled, the type checker passed, the browser E2E passed, the demo-quality gate counted its
sections and CTAs. Nothing asked whether the class names in the markup mean anything, and they did
not:

* 47 Tailwind utilities (`bg-slate-800`, `flex`, `gap-2`, `focus:ring-2`) in a product with no
  tailwindcss dependency, no config and no @tailwind directives — every one of them styling nothing;
* 29 semantic class names with no rule anywhere: 64 used in JSX against 21 defined in CSS.

Class names are strings, so a type checker cannot see this, and unstyled markup renders fine, so a
browser cannot fail on it. It has to be compared.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import (
    ensure_markup_classes_have_rules,
    find_unstyled_classes,
    strip_orphan_tailwind_classnames,
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


TAILWIND_MARKUP = (
    '<div className="flex gap-2 bg-slate-800 focus:ring-2">'
    '<span className="text-sm font-semibold">x</span></div>'
)


def test_tailwind_utilities_without_tailwind_are_critical(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": '{"dependencies": {"react": "18.2.0"}}',
            "frontend/src/App.tsx": TAILWIND_MARKUP,
            "frontend/src/styles/index.css": ":root { --bg: #000; }\n",
        },
    )
    found = [f for f in find_unstyled_classes(code) if f["code"] == "tailwind_utilities_without_tailwind"]
    assert len(found) == 1
    assert found[0]["severity"] == "critical"
    assert "no tailwindcss dependency" in found[0]["detail"].lower() or "NO tailwindcss" in found[0]["detail"]
    assert "Pick ONE" in found[0]["detail"], "the fix must name a decision, not a complaint"


def test_a_product_with_tailwind_is_silent_about_utilities(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": '{"devDependencies": {"tailwindcss": "3.4.0"}}',
            "frontend/src/App.tsx": TAILWIND_MARKUP,
            "frontend/src/styles/index.css": "@tailwind base;\n@tailwind utilities;\n",
        },
    )
    assert [f for f in find_unstyled_classes(code) if "tailwind" in f["code"]] == []


def test_semantic_classes_without_rules_are_reported(tmp_path):
    used = " ".join(f"widget-{i}" for i in range(10))
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": "{}",
            "frontend/src/App.tsx": f'<div className="{used}" />',
            "frontend/src/styles/index.css": ".widget-0 { color: red; }\n",
        },
    )
    found = [f for f in find_unstyled_classes(code) if f["code"] == "unstyled_classes"]
    assert len(found) == 1
    assert found[0]["file"].endswith("index.css"), "the fix belongs in the stylesheet"
    assert "widget-1" in " ".join(found[0]["classes"])
    assert "widget-0" not in found[0]["classes"], "a class that IS styled must not be listed"


def test_a_couple_of_stragglers_is_not_a_finding(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": "{}",
            "frontend/src/App.tsx": '<div className="alpha beta" />',
            "frontend/src/styles/index.css": ".alpha { color: red; }\n",
        },
    )
    assert [f for f in find_unstyled_classes(code) if f["code"] == "unstyled_classes"] == []


def test_a_product_with_no_markup_is_silent(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": "app = 1\n"})
    assert find_unstyled_classes(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not unstyled" in passed
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    breakdown = dev[dev.index("def _tree_defect_breakdown(") : dev.index("def _tree_defect_identities(")]
    assert "find_unstyled_classes" in breakdown
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "+ 5 * len(find_unstyled_classes" not in score
    assert "strip_orphan_tailwind_classnames" in dev
    assert "ensure_markup_classes_have_rules" in dev
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"tailwind_utilities_without_tailwind"' in qa[: qa.index("# Deletions next")]


def test_orphan_tailwind_tokens_are_stripped_when_product_has_no_tailwind(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": '{"dependencies": {"react": "18.2.0"}}',
            "frontend/src/pages/PublicWidget.tsx": (
                '<div className="widget flex gap-2 text-muted">'
                '<button className="btn-primary">Go</button></div>'
            ),
            "frontend/src/styles/index.css": ".widget { color: #fff; }\n.btn-primary { color: #0f0; }\n",
        },
    )
    changed = strip_orphan_tailwind_classnames(code, ["frontend/src/pages/PublicWidget.tsx"])
    assert changed == ["frontend/src/pages/PublicWidget.tsx"]
    body = (code / "frontend" / "src" / "pages" / "PublicWidget.tsx").read_text(encoding="utf-8")
    assert "flex" not in body and "gap-2" not in body and "text-muted" not in body
    assert "widget" in body and "btn-primary" in body
    assert find_unstyled_classes(code) == []


def test_tailwind_tokens_are_kept_when_the_product_has_tailwind(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": '{"devDependencies": {"tailwindcss": "3.4.0"}}',
            "frontend/src/App.tsx": '<div className="flex gap-2">x</div>\n',
            "frontend/src/styles/index.css": "@tailwind utilities;\n",
        },
    )
    assert strip_orphan_tailwind_classnames(code, ["frontend/src/App.tsx"]) == []
    assert "flex gap-2" in (code / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")


def test_missing_semantic_classes_get_stylesheet_selectors(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/package.json": "{}",
            "frontend/src/App.tsx": (
                '<div className="skeleton empty-state toast alert-box '
                'status-chip loading-row vacant-list hint-banner">'
                "x</div>"
            ),
            "frontend/src/styles/index.css": ":root { --bg: #000; }\n",
        },
    )
    assert find_unstyled_classes(code)
    added = ensure_markup_classes_have_rules(code, ["frontend/src/App.tsx"])
    assert "skeleton" in added
    css = (code / "frontend" / "src" / "styles" / "index.css").read_text(encoding="utf-8")
    assert ".skeleton {" in css
    assert [f for f in find_unstyled_classes(code) if f["code"] == "unstyled_classes"] == []
