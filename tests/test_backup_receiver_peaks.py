"""receiver_status.py publishes each repo's weekly peak size next to its size, so the
alerter can see a compaction that made a mass delete final — without any key."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "backup" / "receiver_status.py"


def _run(root: Path, out: Path) -> dict:
    subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--out", str(out)], check=True)
    return json.loads(out.read_text())


def test_the_peak_survives_a_shrink(tmp_path):
    repo = tmp_path / "root" / "factory-vps"
    (repo / "data").mkdir(parents=True)
    (repo / "config").write_text("[repository]\n")
    big = repo / "data" / "seg"
    big.write_bytes(b"x" * 3_000_000)
    out = tmp_path / "status.json"
    first = _run(tmp_path / "root", out)["repos"]["factory-vps"]
    big.write_bytes(b"x" * 1_000_000)          # compacted away
    second = _run(tmp_path / "root", out)["repos"]["factory-vps"]
    assert first["size_mb"] == first["size_mb_peak_7d"]
    assert second["size_mb"] < second["size_mb_peak_7d"] == first["size_mb"]
