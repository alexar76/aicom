"""Exercise shipped plugin export filters using local synthetic files only."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_export_cannot_copy_relative_runtime_identities(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    destination.mkdir()
    files = {
        "aimarket-oracle-gateway/data/platon_signing_key": "disposable-private-canary",
        "aimarket-oracle-gateway/data/platon_signing_key_mldsa": "disposable-pq-canary",
        "aimarket-oracle-gateway/data/custom-identity-name": "disposable-unrecognized-name",
        "aimarket-provenance/data/hub_signing_key": "disposable-private-canary",
        "aimarket-provenance/data/hub.db": "disposable-db-canary",
        "aimarket-oracle-gateway/.env": "FAKE_SECRET=disposable-canary",
        "aimarket-oracle-gateway/.env.example": "FAKE_SECRET=",
        "aimarket-oracle-gateway/README.md": "public documentation",
        "aimarket-provenance/aimarket_provenance/__init__.py": "# public source",
    }
    for relative, value in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    text = (ROOT / "scripts/mirror_satellites.sh").read_text()
    first = text.index("  # BEGIN plugin export filters")
    last = text.index("  # END plugin export filters", first)
    block = text[first:last]
    # Execute only the actual filter construction and local rsync. No clone,
    # remote, commit, release or publish function enters this harness.
    harness = '''set -e
ROOT=$1
copy_local() {
''' + block + '''
  rsync "${rsync_args[@]}" "$1/" "$2/"
}
copy_local "$2" "$3"
'''
    result = subprocess.run(
        ["bash", "-c", harness, "plugin-export-test", str(ROOT), str(source), str(destination)],
        capture_output=True, text=True, check=False, env=dict(os.environ),
    )
    assert result.returncode == 0, result.stderr
    exported = sorted(str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file())
    assert exported == [
        "aimarket-oracle-gateway/.env.example",
        "aimarket-oracle-gateway/README.md",
        "aimarket-provenance/aimarket_provenance/__init__.py",
    ]


def test_plugin_local_ignore_rules_work_without_monorepo_ancestors(tmp_path):
    # Put each plugin's own ignore file in a fresh repository to prove it does
    # not depend on the monorepo's .gitignore or oracles/.gitignore.
    for name, relative in (
        ("gateway", "plugins/aimarket-oracle-gateway/.gitignore"),
        ("provenance", "aimarket-hub/plugins/aimarket-provenance/.gitignore"),
    ):
        folder = tmp_path / name
        folder.mkdir()
        (folder / ".gitignore").write_bytes((ROOT / relative).read_bytes())
        subprocess.run(["git", "init", "-q", str(folder)], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "-C", str(folder), "check-ignore", "data/custom-key", "data/hub_signing_key"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0
        assert result.stdout.splitlines() == ["data/custom-key", "data/hub_signing_key"]
