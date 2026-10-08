"""A satellite mirror never carries the raw satellite map: its `github_published: false`
entries (attested, pingblip, protocol-v2-*, emberline …) name private components, their
paths and their exclude lists."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text(encoding="utf-8"))
UNPUBLISHED = {s["id"] for s in RAW["satellites"] if isinstance(s, dict) and s.get("github_published") is False}


def test_the_map_has_unpublished_entries_to_hide():
    assert UNPUBLISHED


def test_the_published_map_drops_every_unpublished_entry(tmp_path):
    dest = tmp_path / "scripts" / "satellite-map.yaml"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "write_published_satellite_map.py"), str(dest)],
                   check=True)
    ids = {s["id"] for s in yaml.safe_load(dest.read_text(encoding="utf-8"))["satellites"]}
    assert not ids & UNPUBLISHED
    assert ids  # the published ones are still there


def test_no_mirror_copies_the_raw_map_into_a_clone():
    for script in ("scripts/mirror_satellites.sh", "scripts/publish_all_repos.sh"):
        text = (ROOT / script).read_text(encoding="utf-8")
        assert not re.search(r'cp\s+"?\$ROOT/scripts/satellite-map\.yaml"?\s+"?\$clone', text), script
