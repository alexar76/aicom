import json
import subprocess
import sys
import time
from pathlib import Path


def test_benchmark_scorecard_emits_alerts_on_degradation(tmp_path: Path):
    reports = tmp_path / "benchmarks"
    reports.mkdir(parents=True, exist_ok=True)
    now = time.time()
    (reports / "run-1.json").write_text(
        json.dumps({"pass_rate": 0.6, "count": 20, "completed": 12, "failed": 8, "unresolved": 0, "generated_at": now}),
        encoding="utf-8",
    )
    out_json = tmp_path / "scorecard.json"
    out_md = tmp_path / "scorecard.md"
    alerts = tmp_path / "alerts.json"
    res = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_daily_scorecard.py",
            "--reports-dir",
            str(reports),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
            "--alerts-json",
            str(alerts),
            "--min-pass-rate-24h",
            "0.75",
            "--min-pass-rate-7d",
            "0.8",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 2
    payload = json.loads(alerts.read_text(encoding="utf-8"))
    assert payload["alerts"]
