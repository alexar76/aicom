"""scripts/fill_production_env.py — append-only .env patching."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_fill_appends_only_missing(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO=1\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "fill_production_env.py"
    r = subprocess.run(
        [sys.executable, str(script), "--env-file", str(env), "--public-url", "https://x.example"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    text = env.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_SITE_URL=https://x.example" in text
    assert "AIFACTORY_CORS_ORIGINS=https://x.example" in text
    assert "FOO=1" in text

    r2 = subprocess.run(
        [sys.executable, str(script), "--env-file", str(env), "--public-url", "https://other.example"],
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0
    text2 = env.read_text(encoding="utf-8")
    assert text2.count("NEXT_PUBLIC_SITE_URL=") == 1
    assert "https://other.example" not in text2 or "https://x.example" in text2
