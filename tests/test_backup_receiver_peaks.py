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


def test_an_uncommitted_upload_is_no_peak(tmp_path):
    """Segments after the last index.<N> are a transaction that never committed (2026-11-01:
    attested's upload stopped at its quota); they leave on the next session and count for nothing."""
    repo = tmp_path / "root" / "attested"
    (repo / "data" / "0").mkdir(parents=True)
    (repo / "config").write_text("[repository]\n")
    (repo / "index.2").write_bytes(b"i" * 1000)
    for seg in (1, 2):
        (repo / "data" / "0" / str(seg)).write_bytes(b"x" * 1_000_000)
    out = tmp_path / "status.json"
    before = _run(tmp_path / "root", out)["repos"]["attested"]
    for seg in (3, 4, 5):                      # written, never committed
        (repo / "data" / "0" / str(seg)).write_bytes(b"x" * 5_000_000)
    during = _run(tmp_path / "root", out)["repos"]["attested"]
    assert during["size_mb"] == before["size_mb"] == during["size_mb_peak_7d"]
    for seg in (3, 4, 5):                      # the next session rolls them back
        (repo / "data" / "0" / str(seg)).unlink()
    (repo / "data" / "0" / "6").write_bytes(b"x" * 1_000_000)
    (repo / "index.6").write_bytes(b"i" * 1000)  # and commits one more segment
    after = _run(tmp_path / "root", out)["repos"]["attested"]
    assert after["size_mb"] == after["size_mb_peak_7d"] > before["size_mb"]
