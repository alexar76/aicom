"""The live-DB rewrite must stay dry-run by default and fail closed without a probe."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reclassify_incomplete_input.py"


def _load():
    spec = importlib.util.spec_from_file_location("reclassify_incomplete_input", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE invocation_stats ("
        "capability_id TEXT, outcome TEXT, price_usd REAL, timestamp TEXT)"
    )
    conn.execute(
        "INSERT INTO invocation_stats VALUES "
        "('atlas.watchbox.check@v1', 'fail', 0, '2026-09-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()


def _outcomes(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    rows = [r[0] for r in conn.execute("SELECT outcome FROM invocation_stats")]
    conn.close()
    return rows


def test_apply_without_a_probe_url_changes_nothing(tmp_path, capsys, monkeypatch):
    db = tmp_path / "hub.db"
    _seed(db)
    mod = _load()
    monkeypatch.setattr(
        "sys.argv",
        ["reclassify_incomplete_input.py", "--db", str(db),
         "--capability", "atlas.watchbox.check@v1", "--apply"],
    )
    assert mod.main() == 2
    assert _outcomes(db) == ["fail"]
    err = capsys.readouterr().err
    assert "REFUSED" in err
    assert "--probe-url" in err


def test_dry_run_without_a_probe_url_still_prints_the_plan(tmp_path, capsys, monkeypatch):
    db = tmp_path / "hub.db"
    _seed(db)
    mod = _load()
    monkeypatch.setattr(
        "sys.argv",
        ["reclassify_incomplete_input.py", "--db", str(db),
         "--capability", "atlas.watchbox.check@v1"],
    )
    assert mod.main() == 0
    assert _outcomes(db) == ["fail"]
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "1 row" in out


def test_apply_skips_when_the_live_probe_is_not_incomplete(tmp_path, capsys, monkeypatch):
    db = tmp_path / "hub.db"
    _seed(db)
    mod = _load()

    def _nope(peer_url, capability_id, product_id, timeout):
        return False, "sensor offline"

    monkeypatch.setattr(mod, "probe", _nope)
    monkeypatch.setattr(
        "sys.argv",
        ["reclassify_incomplete_input.py", "--db", str(db),
         "--capability", "atlas.watchbox.check@v1",
         "--probe-url", "https://atlas.example", "--apply"],
    )
    assert mod.main() == 0
    assert _outcomes(db) == ["fail"]
    out = capsys.readouterr().out
    assert "SKIP" in out
    assert "APPLIED: 0" in out
