"""Security report file layout (SecurityAgent writes under data/security/)."""

from __future__ import annotations

import json

from web.backend.services.security_report_loader import load_security_report, unwrap_security_artifact


def test_unwrap_nested_report():
    raw = {
        "report": {"security_score": 88, "grade": "B", "vulnerabilities": []},
        "scanned_at": 1.0,
    }
    out = unwrap_security_artifact(raw)
    assert out["security_score"] == 88
    assert out["grade"] == "B"


def test_load_from_security_dir(tmp_path):
    pid = "prod-loader-test"
    p = tmp_path / "data" / "security" / pid / "security_report.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "report": {
                    "security_score": 90,
                    "grade": "A",
                    "vulnerabilities": [{"severity": "low", "category": "x", "file": "a.js"}],
                }
            }
        ),
        encoding="utf-8",
    )
    r = load_security_report(pid, data_root=str(tmp_path / "data"))
    assert r is not None
    assert r["security_score"] == 90
    assert len(r["vulnerabilities"]) == 1
