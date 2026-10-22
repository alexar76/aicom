"""The product catalog refuses a product whose lockfile npm rates high or critical.

Sentinel and Relay reached alexar76/aicom-products with vite <=6.4.3, an old vitest and axios, and the
catalog's npm-dependency-audit CI turned red after publication (2026-10-21 audit). The publish script
now runs the same audit first. These tests drive the real shell function with a stand-in `npm`, so
they need no network.
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "publish_factory_product_catalog.sh").read_text(encoding="utf-8")
FUNCTION = re.search(r"^audit_product_npm\(\) \{\n.*?^\}\n", SCRIPT, re.S | re.M).group(0)


def _run(tmp_path: Path, npm_exit: int, npm_out: str, *, allow: bool = False) -> subprocess.CompletedProcess:
    product = tmp_path / "prod-x"
    (product / "frontend").mkdir(parents=True)
    (product / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    (product / "frontend" / "node_modules" / "dep").mkdir(parents=True)
    (product / "frontend" / "node_modules" / "dep" / "package-lock.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(f"#!/bin/sh\necho \"$PWD\" >> {tmp_path}/calls\nprintf '%s\\n' '{npm_out}'\nexit {npm_exit}\n")
    npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    if allow:
        env["AICOM_CATALOG_ALLOW_NPM_HIGH"] = "1"
    return subprocess.run(["bash", "-c", FUNCTION + f'\naudit_product_npm "{product}"'],
                          capture_output=True, text=True, env=env)


def test_a_clean_lockfile_passes_and_node_modules_is_not_audited(tmp_path):
    result = _run(tmp_path, 0, "found 0 vulnerabilities")
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls").read_text().split()
    assert len(calls) == 1 and calls[0].endswith("prod-x/frontend")


def test_high_or_critical_advisories_refuse_the_product(tmp_path):
    result = _run(tmp_path, 1, "vite  <=6.4.3\\nSeverity: high\\n7 vulnerabilities (4 moderate, 1 high, 2 critical)")
    assert result.returncode == 1
    assert "frontend: npm audit reports high/critical advisories" in result.stderr


def test_an_audit_that_cannot_run_warns_but_does_not_block(tmp_path):
    result = _run(tmp_path, 1, "npm error code ENOTFOUND registry.npmjs.org")
    assert result.returncode == 0
    assert "could not run" in result.stderr


def test_the_override_publishes_and_says_so(tmp_path):
    result = _run(tmp_path, 1, "1 high severity vulnerability", allow=True)
    assert result.returncode == 0
    assert "publishing despite" in result.stderr
