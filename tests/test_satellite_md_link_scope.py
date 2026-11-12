"""Keep the publication-link audit on source, including new unsaved-to-Git docs."""
import importlib.util
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_satellite_md_links.py"
spec = importlib.util.spec_from_file_location("satellite_md_links", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_source_scope_includes_new_docs_without_scanning_evidence_or_dependencies(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    files = ("README.md", "docs/new.md", "artifacts/receipt.md",
             "output/preview.md", "app/node_modules/vendor/README.md",
             ".venv-quality/README.md", "ignored/README.md")
    for filename in files:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[link](../satellite/README.md)")
    (tmp_path / ".gitignore").write_text("ignored/\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md", "artifacts/receipt.md"], check=True)
    monkeypatch.setattr(audit, "ROOT", tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in audit.source_markdown_paths()] == [
        "README.md", "docs/new.md",
    ]


def test_source_archive_fallback_prunes_nested_dependencies(tmp_path, monkeypatch):
    for filename in ("docs/new.md", "app/node_modules/vendor/README.md", "output/preview.md"):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Example")
    monkeypatch.setattr(audit, "ROOT", tmp_path)

    assert audit.source_markdown_paths() == [tmp_path / "docs/new.md"]
