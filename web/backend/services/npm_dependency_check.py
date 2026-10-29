"""Audit generated products' resolved npm trees before the security handoff.

Read the actual files, including development dependencies, on every scan. A missing
lockfile or unavailable advisory registry is an incomplete check, never a clean one.
Only manifests and locks enter a temporary audit directory: npm cannot read a
product's .npmrc, execute its lifecycle scripts, or reuse its node_modules.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

AUDIT_ARGS = (
    "audit", "--package-lock-only", "--include=dev", "--ignore-scripts",
    "--audit-level=high", "--json", "--registry=https://registry.npmjs.org",
    "--fetch-retries=0", "--fetch-timeout=20000",
)
LOCK_CHECK_ARGS = (
    "ls", "--package-lock-only", "--all", "--json", "--offline",
    "--ignore-scripts", "--include=dev",
)
AUDIT_BUDGET_SECONDS = 120
DEPENDENCY_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
SEVERITIES = ("info", "low", "moderate", "high", "critical")


def _read_object(path: Path, root: Path) -> dict[str, Any]:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"{path.name} points outside the product")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    return obj


def _validate_manifest(manifest: dict, locked: dict, path: str) -> None:
    for section in DEPENDENCY_SECTIONS:
        declared = manifest.get(section, {})
        if not isinstance(declared, dict) or declared != locked.get(section, {}):
            raise ValueError(f"{path}: {section} differs from package-lock.json; regenerate the lockfile")


def _audit_report(stdout: str, returncode: int) -> dict[str, Any]:
    report = json.loads(stdout)
    if not isinstance(report, dict) or report.get("error"):
        raise ValueError("npm audit returned an error or invalid report")
    counts = (report.get("metadata") or {}).get("vulnerabilities")
    findings = report.get("vulnerabilities")
    if not isinstance(counts, dict) or not isinstance(findings, dict):
        raise ValueError("npm audit report has no vulnerability counts/findings")
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in (*SEVERITIES, "total")):
        raise ValueError("npm audit report has invalid severity counts")
    actual = dict.fromkeys(SEVERITIES, 0)
    for finding in findings.values():
        if not isinstance(finding, dict) or finding.get("severity") not in actual:
            raise ValueError("npm audit report has an invalid vulnerability")
        actual[finding["severity"]] += 1
    if any(actual[k] != counts[k] for k in SEVERITIES) or sum(actual.values()) != counts["total"]:
        raise ValueError("npm audit counts do not match its findings")
    if returncode not in (0, 1) or (returncode and not (counts["high"] or counts["critical"])):
        raise ValueError(f"npm audit did not complete successfully (exit {returncode})")
    return report


def _validate_locked_tree(stdout: str, returncode: int) -> None:
    """npm audit alone accepts truncated locks; npm ls verifies their dependency graph offline."""
    report = json.loads(stdout)
    if returncode != 0 or not isinstance(report, dict):
        raise ValueError("resolved dependency tree is incomplete or invalid; regenerate package-lock.json")
    pending = [report]
    while pending:
        node = pending.pop()
        if node.get("error") or node.get("problems") or node.get("missing") or node.get("invalid"):
            raise ValueError("resolved dependency tree is incomplete or invalid; regenerate package-lock.json")
        children = node.get("dependencies", {})
        if not isinstance(children, dict) or any(not isinstance(child, dict) for child in children.values()):
            raise ValueError("npm lockfile validation returned an invalid dependency tree")
        pending.extend(children.values())


def _incomplete(result: dict, check: dict, code: str, issue: str) -> None:
    check["passed"] = False
    check["code"] = code
    check["issues"].append(issue)
    result["issues"].append(issue)
    result["dependency_risks"].append({
        "code": code, "severity": "high", "package": "npm audit",
        "file": check.get("lockfile") or check["manifest"], "issue": issue,
        "recommendation": "Resolve this incomplete check and rerun the security scan. "
        "Generate a matching npm lockfile when missing or stale; retry registry/tooling failures. "
        "Do not disable the audit, omit development dependencies, or mark an unchecked product clean.",
    })


def _new_check(directory: Path, root: Path) -> dict[str, Any]:
    return {
        "directory": directory.relative_to(root).as_posix(),
        "manifest": (directory / "package.json").relative_to(root).as_posix(),
        "lockfile": (directory / "package-lock.json").relative_to(root).as_posix(),
        "passed": True, "issues": [], "sha256": {},
    }


def run_npm_dependency_check(code_dir: Path | str) -> dict[str, Any]:
    """Fail on high/critical advisories or incomplete coverage; never modify product files."""
    root = Path(code_dir)
    result: dict[str, Any] = {
        "passed": True, "skipped": False, "checks": [], "dependency_risks": [],
        "issues": [], "checked_at": time.time(), "manifest_sha256": {},
        "command": ["npm", *AUDIT_ARGS],
    }
    if not root.is_dir():
        check = {"manifest": ".", "passed": False, "issues": []}
        result["checks"].append(check)
        _incomplete(result, check, "npm_product_missing", "Product source directory is unavailable")
        result["passed"] = False
        return result

    files = sorted(p for p in iter_product_files(root)
                   if p.name in {"package.json", "package-lock.json", "npm-shrinkwrap.json"})
    if not files:
        result.update(skipped=True, reason="no_npm_projects")
        return result
    manifests: dict[Path, dict] = {}
    locks: dict[Path, dict] = {}
    invalid: set[Path] = set()
    for path in files:
        if path.name == "npm-shrinkwrap.json":
            check = _new_check(path.parent, root)
            result["checks"].append(check)
            _incomplete(result, check, "npm_shrinkwrap_unsupported",
                        f"{path.relative_to(root)} overrides package-lock.json; migrate to an audited package-lock.json first")
            invalid.add(path.parent)
            continue
        try:
            obj = _read_object(path, root)
            (manifests if path.name == "package.json" else locks)[path.parent] = obj
            result["manifest_sha256"][path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError) as exc:
            check = _new_check(path.parent, root)
            result["checks"].append(check)
            _incomplete(result, check, "npm_manifest_invalid", f"{path.relative_to(root)}: {exc}")
            invalid.add(path.parent)

    # Workspace members use their ancestor's lock. An unrelated nested package
    # still needs its own lock; being under a workspace directory is insufficient.
    covered: set[Path] = set()
    for directory, lock in sorted(locks.items()):
        check = _new_check(directory, root)
        result["checks"].append(check)
        covered.add(directory)
        if directory in invalid:
            _incomplete(result, check, "npm_manifest_invalid", f"{check['directory']}: invalid npm inputs")
            continue
        audit_inputs = {directory / "package.json", directory / "package-lock.json"}
        try:
            if directory not in manifests:
                raise ValueError("package-lock.json has no adjacent package.json")
            packages = lock.get("packages")
            if lock.get("lockfileVersion") not in (2, 3) or not isinstance(packages, dict):
                raise ValueError("use an npm lockfileVersion 2 or 3 lockfile with a packages map")
            if not isinstance(packages.get(""), dict):
                raise ValueError("package-lock.json has no root package metadata")
            _validate_manifest(manifests[directory], packages[""], check["manifest"])
            for member, manifest in sorted(manifests.items()):
                if member == directory or member in locks or not member.is_relative_to(directory):
                    continue
                member_rel = member.relative_to(directory).as_posix()
                if member_rel in packages and isinstance(packages[member_rel], dict):
                    _validate_manifest(manifest, packages[member_rel], member_rel + "/package.json")
                    audit_inputs.add(member / "package.json")
                    covered.add(member)
            check["sha256"] = {
                p.relative_to(root).as_posix(): result["manifest_sha256"][p.relative_to(root).as_posix()]
                for p in sorted(audit_inputs)
            }
            check["_inputs"] = audit_inputs
        except (KeyError, ValueError) as exc:
            _incomplete(result, check, "npm_lockfile_stale", f"{check['directory']}: {exc}")

    for directory in sorted(manifests.keys() - covered - invalid):
        check = _new_check(directory, root)
        result["checks"].append(check)
        _incomplete(result, check, "npm_lockfile_missing", f"{check['manifest']}: matching package-lock.json is missing")

    npm = shutil.which("npm")
    deadline = time.monotonic() + AUDIT_BUDGET_SECONDS
    for check in result["checks"]:
        inputs = check.pop("_inputs", None)
        if not inputs or not check["passed"]:
            continue
        if not npm:
            _incomplete(result, check, "npm_audit_incomplete", "npm is unavailable; dependency security was not checked")
            continue
        directory = root / check["directory"]
        try:
            remaining = min(35, deadline - time.monotonic())
            if remaining <= 0:
                raise ValueError("npm audit time budget exhausted")
            with tempfile.TemporaryDirectory(prefix="aicom-npm-audit-") as tmp:
                stage = Path(tmp) / "project"
                for path in inputs:
                    target = stage / path.relative_to(directory)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
                for name in ("user.npmrc", "global.npmrc"):
                    (Path(tmp) / name).touch()
                env = {
                    "PATH": os.environ.get("PATH", os.defpath), "HOME": tmp, "CI": "1",
                    "npm_config_cache": str(Path(tmp) / "cache"),
                    "npm_config_userconfig": str(Path(tmp) / "user.npmrc"),
                    "npm_config_globalconfig": str(Path(tmp) / "global.npmrc"),
                    "npm_config_update_notifier": "false",
                }
                tree = subprocess.run([npm, *LOCK_CHECK_ARGS], cwd=stage, env=env,
                                      capture_output=True, text=True, timeout=remaining)
                try:
                    _validate_locked_tree(tree.stdout, tree.returncode)
                except (ValueError, TypeError) as exc:
                    _incomplete(result, check, "npm_lockfile_stale", f"{check['directory']}: {exc}")
                    continue
                remaining = min(35, deadline - time.monotonic())
                if remaining <= 0:
                    raise ValueError("npm audit time budget exhausted")
                proc = subprocess.run([npm, *AUDIT_ARGS], cwd=stage, env=env,
                                      capture_output=True, text=True, timeout=remaining)
                report = _audit_report(proc.stdout, proc.returncode)
            # Bind the result to the bytes actually checked, including workspace
            # manifests. A concurrent Developer edit invalidates this scan.
            if any(hashlib.sha256(path.read_bytes()).hexdigest() != check["sha256"][path.relative_to(root).as_posix()]
                   for path in inputs):
                raise ValueError("npm inputs changed during the audit; rescan the current files")
            check["report"] = report
            for name, finding in report["vulnerabilities"].items():
                if finding["severity"] not in ("high", "critical"):
                    continue
                check["passed"] = False
                issue = f"{check['lockfile']}: {name} {finding.get('range', '')} ({finding['severity']})"
                check["issues"].append(issue)
                result["issues"].append(issue)
                result["dependency_risks"].append({
                    "code": "npm_vulnerability", "file": check["lockfile"], "manifest": check["manifest"],
                    "package": name, "severity": finding["severity"], "issue": issue,
                    "range": finding.get("range"), "fix_available": finding.get("fixAvailable"),
                    "recommendation": "Upgrade the affected package or its parent dependency, regenerate package-lock.json, "
                    "and rerun audit, build and tests. Review major upgrades; never use npm audit fix --force "
                    "or omit dev dependencies to bypass the gate.",
                })
        except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired) as exc:
            _incomplete(result, check, "npm_audit_incomplete", f"{check['directory']}: npm audit incomplete ({exc})")

    result["passed"] = all(check["passed"] for check in result["checks"])
    return result
