"""A file the diagnosis asks for by name is in scope, even when it does not exist yet.

Measured: a round created `.github/workflows/ci.yml`, `.github/workflows/release.yml`,
`CHANGELOG.md`, `LICENSE` and `README.md` — exactly what the finding "GITHUB_HOUSE_CONTRACT not
satisfied: missing required repository files" asks for — and all five were reverted as sprawl,
because the scope read `["frontend/src/components/UI/Toast.tsx"]`. The finding survived to the next
round, which created them again. A requirement whose fulfilment is structurally undoable is a
treadmill, and this product spent rounds on it.

The scope is derived from files the blocking defects name in the TREE, so a missing file can never
appear in it. The findings' own text is the other half of the scope.
"""

from __future__ import annotations

from pathlib import Path

from agents.dev import _revert_out_of_scope_writes

FINDINGS = (
    '[{"title": "GITHUB_HOUSE_CONTRACT not satisfied: missing required repository files", '
    '"description": "Add LICENSE, CHANGELOG.md and .github/workflows/ci.yml"}]'
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_a_new_file_the_findings_name_survives(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/App.tsx": "export const A = 1\n",
            "LICENSE": "MIT\n",
            ".github/workflows/ci.yml": "on: push\n",
        },
    )
    reverted = _revert_out_of_scope_writes(
        code,
        {"frontend/src/App.tsx": "export const A = 0\n"},   # only App.tsx existed before
        ["frontend/src/App.tsx", "LICENSE", ".github/workflows/ci.yml"],
        ["frontend/src/App.tsx"],
        log=lambda *a, **k: None,
        product_id="p",
        findings_text=FINDINGS,
    )
    assert reverted == set(), reverted
    assert (code / "LICENSE").is_file()
    assert (code / ".github" / "workflows" / "ci.yml").is_file()


def test_a_new_file_nobody_asked_for_is_still_removed(tmp_path):
    """The guard exists because rounds accrete files. Only NAMED files get the exemption."""
    code = _tree(
        tmp_path / "code",
        {"frontend/src/App.tsx": "export const A = 1\n", "backend/app/seed_v5.py": "x = 1\n"},
    )
    reverted = _revert_out_of_scope_writes(
        code,
        {"frontend/src/App.tsx": "export const A = 0\n"},
        ["frontend/src/App.tsx", "backend/app/seed_v5.py"],
        ["frontend/src/App.tsx"],
        log=lambda *a, **k: None,
        product_id="p",
        findings_text=FINDINGS,
    )
    assert "backend/app/seed_v5.py" in reverted
    assert not (code / "backend" / "app" / "seed_v5.py").exists()


def test_a_rewrite_of_an_existing_file_gets_no_exemption(tmp_path):
    """Naming a file in a finding does not license retyping it: sprawl is a property of rewrites,
    and a rewritten file can lose anything already in it."""
    code = _tree(tmp_path / "code", {"README.md": "new text\n", "a.py": "x = 1\n"})
    reverted = _revert_out_of_scope_writes(
        code,
        {"README.md": "old text\n", "a.py": "x = 0\n"},   # README existed already
        ["README.md", "a.py"],
        ["a.py"],
        log=lambda *a, **k: None,
        product_id="p",
        findings_text='[{"title": "README.md is missing badges"}]',
    )
    assert "README.md" in reverted
    assert (code / "README.md").read_text(encoding="utf-8") == "old text\n"


def test_the_developer_passes_the_findings_in():
    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    call = dev[dev.index("out_of_scope = _revert_out_of_scope_writes(") :][:600]
    assert "findings_text=_findings_text," in call
    setup = dev[dev.index("_findings_text = json.dumps(") :][:300]
    assert 'agent_input.data.get("qa_findings")' in setup, "must read the key that actually arrives"
