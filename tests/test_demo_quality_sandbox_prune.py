"""Storefront product detail must not hang on huge .aicom_sandbox trees."""

from __future__ import annotations

import time
from pathlib import Path

from web.backend.services.demo_quality import _detect_loopback_artifact_urls, _iter_text_artifacts


def test_iter_text_artifacts_prunes_aicom_sandbox(tmp_path: Path):
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    junk = tmp_path / ".aicom_sandbox" / "sandbox-x" / "node_modules" / "pkg"
    junk.mkdir(parents=True)
    for i in range(200):
        (junk / f"f{i}.js").write_text("// http://localhost:1\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.ts").write_text('const u = "http://127.0.0.1:3000";\n', encoding="utf-8")

    t0 = time.perf_counter()
    arts = list(_iter_text_artifacts(tmp_path))
    elapsed = time.perf_counter() - t0

    rels = [a[0] for a in arts]
    assert all(".aicom_sandbox" not in r for r in rels)
    assert "src/main.ts" in rels
    assert elapsed < 2.0

    offenders = _detect_loopback_artifact_urls(tmp_path)
    assert "src/main.ts" in offenders
    assert not any(".aicom_sandbox" in o for o in offenders)
