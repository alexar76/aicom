"""The product catalog uses the factory's shared npm dependency security gate.

Sentinel and Relay reached alexar76/aicom-products with vite <=6.4.3, an old vitest and axios, and the
catalog's npm-dependency-audit CI turned red after publication (2026-10-21 audit). The publish script
now runs the same product check first. These tests drive the real shell function with a stand-in `npm`, so
they need no network.
"""

from __future__ import annotations

import json
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from web.backend.services.npm_dependency_check import AUDIT_ARGS, LOCK_CHECK_ARGS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "publish_factory_product_catalog.sh").read_text(encoding="utf-8")
FUNCTION = re.search(r"^audit_product_npm\(\) \{\n.*?^\}\n", SCRIPT, re.S | re.M).group(0)


def _report(**counts: int) -> str:
    severities = dict.fromkeys(("info", "low", "moderate", "high", "critical"), 0)
    severities.update(counts)
    vulnerabilities = {
        f"package-{severity}-{index}": {"severity": severity}
        for severity, count in severities.items()
        for index in range(count)
    }
    return json.dumps({
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {"vulnerabilities": {**severities, "total": sum(severities.values())}},
    })


def _run(
    tmp_path: Path,
    npm_exit: int,
    npm_out: str,
    *,
    allow: bool = False,
    npm_available: bool = True,
    has_lock: bool = True,
    has_manifest: bool = True,
    stale_manifest: bool = False,
    source_npmrc: bool = False,
    tree_exit: int = 0,
    tree_out: str = "{}",
) -> subprocess.CompletedProcess:
    product = tmp_path / "product with spaces"
    (product / "frontend").mkdir(parents=True)
    if has_manifest:
        manifest = {"dependencies": {"vite": "1.0.0"}} if stale_manifest else {}
        (product / "frontend" / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    if has_lock:
        (product / "frontend" / "package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {"": {}}}), encoding="utf-8"
        )
    if source_npmrc:
        (product / "frontend" / ".npmrc").write_text(
            "registry=https://registry.invalid\nomit=dev\naudit=false\n", encoding="utf-8"
        )
    (product / "frontend" / "node_modules" / "dep").mkdir(parents=True)
    (product / "frontend" / "node_modules" / "dep" / "package-lock.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # A closed PATH makes missing-npm behavior independent of the developer machine.
    for name, source in {"python3": sys.executable}.items():
        (bin_dir / name).symlink_to(source)
    if npm_available:
        npm = bin_dir / "npm"
        npm.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$PWD\" \"$*\" >> {shlex.quote(str(tmp_path / 'calls'))}\n"
            '[ -f package.json ] && [ -f package-lock.json ] || exit 97\n'
            '[ ! -e .npmrc ] || exit 98\n'
            'case "$1" in\n'
            f"  ls) printf '%s\\n' {shlex.quote(tree_out)}; exit {tree_exit} ;;\n"
            f"  audit) printf '%s\\n' {shlex.quote(npm_out)}; exit {npm_exit} ;;\n"
            '  *) exit 99 ;;\nesac\n'
        )
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": str(bin_dir)}
    if allow:
        env["AICOM_CATALOG_ALLOW_NPM_HIGH"] = "1"
    shell = f"ROOT={shlex.quote(str(ROOT))}\n" + FUNCTION
    return subprocess.run(["/bin/bash", "-c", shell + f"\naudit_product_npm {shlex.quote(str(product))}"],
                          capture_output=True, text=True, env=env)


def test_a_clean_lockfile_passes_and_node_modules_is_not_audited(tmp_path):
    result = _run(tmp_path, 0, _report())
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls").read_text().splitlines()
    assert len(calls) == 4
    assert calls[0] == calls[2]
    assert "aicom-npm-audit-" in calls[0] and calls[0].endswith("/project")
    assert calls[1].split() == list(LOCK_CHECK_ARGS)
    assert calls[3].split() == list(AUDIT_ARGS)


@pytest.mark.parametrize("npm_exit", [0, 1])
@pytest.mark.parametrize("severity", ["high", "critical"])
def test_high_or_critical_advisories_refuse_the_product(tmp_path, npm_exit, severity):
    result = _run(tmp_path, npm_exit, _report(**{severity: 1}))
    assert result.returncode == 1
    assert "npm dependency security check failed" in result.stderr
    assert f"frontend/package-lock.json: package-{severity}-0" in result.stderr
    assert f"({severity})" in result.stderr


@pytest.mark.parametrize("npm_out", [
    "npm error code ENOTFOUND registry.npmjs.org",
    '{"error": {"code": "ENOTFOUND", "summary": "registry unavailable"}}',
    "{}",
    "[]",
    '{"metadata":{"vulnerabilities":{"high":0,"critical":0}}}',
])
def test_unavailable_or_incomplete_audit_blocks_the_product(tmp_path, npm_out):
    result = _run(tmp_path, 1, npm_out)
    assert result.returncode == 1
    assert "npm audit incomplete" in result.stderr


def test_inconsistent_report_cannot_hide_a_high_advisory(tmp_path):
    report = json.loads(_report(high=1))
    report["metadata"]["vulnerabilities"].update(high=0, total=0)
    result = _run(tmp_path, 0, json.dumps(report))
    assert result.returncode == 1
    assert "npm audit counts do not match its findings" in result.stderr


def test_low_and_moderate_advisories_pass_the_high_threshold(tmp_path):
    result = _run(tmp_path, 0, _report(low=2, moderate=3))
    assert result.returncode == 0, result.stderr


def test_nonzero_exit_cannot_pass_with_a_clean_report(tmp_path):
    result = _run(tmp_path, 1, _report())
    assert result.returncode == 1
    assert "npm audit did not complete successfully" in result.stderr


def test_missing_npm_blocks_a_product_with_a_lockfile(tmp_path):
    result = _run(tmp_path, 0, "", npm_available=False)
    assert result.returncode == 1
    assert "npm is unavailable" in result.stderr


def test_non_npm_product_does_not_require_npm(tmp_path):
    result = _run(tmp_path, 0, "", npm_available=False, has_lock=False, has_manifest=False)
    assert result.returncode == 0, result.stderr


def test_legacy_override_cannot_bypass_advisories(tmp_path):
    result = _run(tmp_path, 1, _report(high=1), allow=True)
    assert result.returncode == 1
    assert "frontend/package-lock.json: package-high-0" in result.stderr


def test_package_without_a_lockfile_blocks_before_audit(tmp_path):
    result = _run(tmp_path, 0, _report(), has_lock=False)
    assert result.returncode == 1
    assert "frontend/package.json: matching package-lock.json is missing" in result.stderr
    assert not (tmp_path / "calls").exists()


def test_lockfile_without_a_manifest_blocks_before_audit(tmp_path):
    result = _run(tmp_path, 0, _report(), has_manifest=False)
    assert result.returncode == 1
    assert "package-lock.json has no adjacent package.json" in result.stderr
    assert not (tmp_path / "calls").exists()


def test_manifest_lock_drift_blocks_before_audit(tmp_path):
    result = _run(tmp_path, 0, _report(), stale_manifest=True)
    assert result.returncode == 1
    assert "dependencies differs from package-lock.json" in result.stderr
    assert not (tmp_path / "calls").exists()


def test_source_npm_config_cannot_disable_dev_auditing(tmp_path):
    result = _run(tmp_path, 1, _report(high=1), source_npmrc=True)
    assert result.returncode == 1
    assert "frontend/package-lock.json: package-high-0" in result.stderr
    assert len((tmp_path / "calls").read_text().splitlines()) == 4


def test_an_incomplete_resolved_tree_blocks_before_the_advisory_audit(tmp_path):
    result = _run(tmp_path, 0, _report(), tree_exit=1, tree_out='{"problems":["missing vite"]}')
    assert result.returncode == 1
    assert "resolved dependency tree is incomplete or invalid" in result.stderr
    calls = (tmp_path / "calls").read_text().splitlines()
    assert len(calls) == 2
    assert calls[1].split() == list(LOCK_CHECK_ARGS)
