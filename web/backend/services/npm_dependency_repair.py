"""Factory-owned npm dependency repair after the Developer's manifest/code edits.

npm generates real locks and applies compatible advisory fixes on metadata-only
copies. Validated changes return to the product; ordinary QA and Security still
decide whether it can advance. Major upgrades remain the Developer's task.
"""

from __future__ import annotations

import hashlib
import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files
from core.json_state import write_text_atomic
from web.backend.services.npm_dependency_check import (
    AUDIT_ARGS,
    DEPENDENCY_SECTIONS,
    LOCK_CHECK_ARGS,
    _audit_report,
    _validate_locked_tree,
    _validate_manifest,
)

_NETWORK_ARGS = ("--registry=https://registry.npmjs.org", "--fetch-retries=0", "--fetch-timeout=20000")
GENERATE_ARGS = (
    "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund",
    "--include=dev", "--lockfile-version=3", "--json", *_NETWORK_ARGS,
)
FIX_ARGS = (
    "audit", "fix", "--package-lock-only", "--ignore-scripts", "--include=dev",
    "--audit-level=high", "--json", *_NETWORK_ARGS,
)
REPAIR_BUDGET_SECONDS = 180
_REGISTRY_SPEC = re.compile(r"^[a-zA-Z0-9.*^~<>=|+ _-]+$")
_ALIAS_SPEC = re.compile(r"^npm:(?:@[a-z0-9._-]+/)?[a-z0-9._-]+@[a-zA-Z0-9.*^~<>=|+ _-]+$")
_REPAIRABLE = {"npm_lockfile_missing", "npm_lockfile_stale", "npm_manifest_invalid", "npm_vulnerability"}


def _target_directories(root: Path, feedback: dict) -> list[Path]:
    targets: set[Path] = set()
    risks = [r for r in feedback.get("dependency_risks", []) if isinstance(r, dict)]
    for check in feedback.get("checks", []):
        if not isinstance(check, dict) or check.get("passed") is True:
            continue
        related = [r for r in risks if r.get("file") in {check.get("lockfile"), check.get("manifest")}]
        if check.get("code") not in _REPAIRABLE and not any(r.get("code") == "npm_vulnerability" for r in related):
            continue
        rel = str(check.get("manifest") or "")
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts or path.name != "package.json":
            raise ValueError("npm repair feedback contains an invalid manifest path")
        directory = (root / path).parent
        if not directory.resolve().is_relative_to(root.resolve()):
            raise ValueError("npm repair target points outside the product")
        targets.add(directory)
    return sorted(targets)


def _snapshot(root: Path) -> dict[Path, bytes]:
    snapshot: dict[Path, bytes] = {}
    for path in iter_product_files(root):
        if path.name not in {"package.json", "package-lock.json", "npm-shrinkwrap.json"}:
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Dependency input points outside the product")
        snapshot[path.relative_to(root)] = path.read_bytes()
    return snapshot


def _project_inputs(root: Path, original: dict[Path, bytes], directory: Path) -> dict[Path, bytes]:
    """Only the requested root and its workspace/local package metadata enter npm."""
    selected: dict[Path, bytes] = {}
    pending = [directory.relative_to(root)]
    visited: set[Path] = set()
    while pending:
        rel_dir = pending.pop()
        if rel_dir in visited:
            continue
        visited.add(rel_dir)
        manifest_path = rel_dir / "package.json"
        if manifest_path not in original:
            raise ValueError(f"{manifest_path}: Developer must supply a valid package.json")
        manifest = json.loads(original[manifest_path])
        if not isinstance(manifest, dict):
            raise ValueError(f"{manifest_path}: Developer must supply a JSON object")
        selected[manifest_path] = original[manifest_path]
        if rel_dir / "npm-shrinkwrap.json" in original:
            raise ValueError("npm-shrinkwrap.json must be migrated before this repair")
        lock_path = rel_dir / "package-lock.json"
        if lock_path in original:
            try:
                lock = json.loads(original[lock_path])
            except ValueError:
                lock = None
            # Preserve malformed/legacy lock bytes in the original snapshot for
            # rollback, but generate a real current lock from the manifest in staging.
            if (isinstance(lock, dict) and lock.get("lockfileVersion") in (2, 3)
                    and isinstance(lock.get("packages"), dict)):
                selected[lock_path] = original[lock_path]
        workspaces = manifest.get("workspaces") or []
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        if not isinstance(workspaces, list) or any(not isinstance(p, str) for p in workspaces):
            raise ValueError(f"{manifest_path}: invalid workspace definitions")
        for pattern in workspaces:
            if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                raise ValueError(f"{manifest_path}: workspace points outside its project")
            for path in original:
                if path.name == "package.json" and path.parent != rel_dir and path.parent.is_relative_to(rel_dir):
                    if fnmatch.fnmatchcase(path.parent.relative_to(rel_dir).as_posix(), pattern):
                        pending.append(path.parent)
        for section in DEPENDENCY_SECTIONS:
            declared = manifest.get(section, {})
            if not isinstance(declared, dict):
                raise ValueError(f"{manifest_path}: invalid dependency declarations")
            for spec in declared.values():
                if isinstance(spec, str) and spec.startswith("file:"):
                    local = Path(spec[5:])
                    target = (root / rel_dir / local).resolve()
                    if local.is_absolute() or not target.is_relative_to(root):
                        raise ValueError(f"{manifest_path}: local dependency points outside the product")
                    pending.append(target.relative_to(root))
    return selected


def _validate_sources(root: Path, snapshot: dict[Path, bytes]) -> None:
    """Metadata-only resolution must not fetch arbitrary URLs or consult host paths."""
    for rel, blob in snapshot.items():
        obj = json.loads(blob)
        if rel.name == "package.json":
            for section in DEPENDENCY_SECTIONS:
                for name, spec in obj.get(section, {}).items():
                    if not isinstance(spec, str):
                        raise ValueError(f"{rel}: invalid dependency specification for {name}")
                    if _REGISTRY_SPEC.fullmatch(spec) or _ALIAS_SPEC.fullmatch(spec):
                        continue
                    if spec.startswith("file:"):
                        local = Path(spec[5:])
                        target = (root / rel.parent / local).resolve()
                        if not local.is_absolute() and target.is_relative_to(root.resolve()):
                            if target.relative_to(root.resolve()) / "package.json" in snapshot:
                                continue
                    raise ValueError(f"{rel}: {name} needs dependency resolution in an isolated build worker")
        else:
            for package in obj.get("packages", {}).values():
                resolved = package.get("resolved", "") if isinstance(package, dict) else ""
                if not resolved or resolved.startswith("https://registry.npmjs.org/"):
                    continue
                if isinstance(resolved, str) and ":" not in resolved and not Path(resolved).is_absolute():
                    target = (root / rel.parent / resolved).resolve()
                    if target.is_relative_to(root.resolve()):
                        continue
                raise ValueError(f"{rel}: non-registry lockfile source needs an isolated build worker")


def _environment(tmp: Path) -> dict[str, str]:
    for filename in ("user.npmrc", "global.npmrc"):
        (tmp / filename).touch()
    return {
        "PATH": os.environ.get("PATH", os.defpath), "HOME": str(tmp), "CI": "1",
        "npm_config_cache": str(tmp / "cache"), "npm_config_userconfig": str(tmp / "user.npmrc"),
        "npm_config_globalconfig": str(tmp / "global.npmrc"), "npm_config_update_notifier": "false",
    }


def repair_npm_dependencies(code_dir: Path | str, feedback: dict[str, Any]) -> dict[str, Any]:
    """Generate matching locks and compatible fixes, then leave release validation to QA."""
    root = Path(code_dir).resolve()
    result: dict[str, Any] = {
        "attempted": False, "passed": False, "changed_files": [], "issues": [],
        "checks": [], "requires_qa": True, "repaired_at": time.time(),
    }
    if not isinstance(feedback, dict) or feedback.get("passed") is True:
        return result
    try:
        targets = _target_directories(root, feedback)
    except (ValueError, TypeError) as exc:
        result["issues"].append(str(exc))
        return result
    if not targets:
        result["issues"].append("No dependency changes requested; retry unavailable audits without speculative updates")
        return result
    npm = shutil.which("npm")
    if not npm:
        result["issues"].append("npm is unavailable; the factory could not regenerate dependencies")
        return result
    result["attempted"] = True
    deadline = time.monotonic() + REPAIR_BUDGET_SECONDS
    for directory in targets:
        rel_dir = directory.relative_to(root)
        check: dict[str, Any] = {"directory": rel_dir.as_posix(), "passed": False, "changed_files": [], "issues": []}
        result["checks"].append(check)
        try:
            original = _snapshot(root)
            manifest_rel, lock_rel = rel_dir / "package.json", rel_dir / "package-lock.json"
            if manifest_rel not in original:
                raise ValueError(f"{manifest_rel}: Developer must supply a valid package.json")
            inputs = _project_inputs(root, original, directory)
            _validate_sources(root, inputs)
            baseline = {r.get("package"): r.get("severity") for r in feedback.get("dependency_risks", [])
                        if isinstance(r, dict) and r.get("code") == "npm_vulnerability"
                        and r.get("file") in {manifest_rel.as_posix(), lock_rel.as_posix()}}
            with tempfile.TemporaryDirectory(prefix="aicom-npm-repair-") as tmp_dir:
                tmp = Path(tmp_dir)
                stage = tmp / "product"
                for rel, blob in inputs.items():
                    dest = stage / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(blob)
                env = _environment(tmp)
                workdir = stage / rel_dir

                def run(args: tuple[str, ...]) -> subprocess.CompletedProcess:
                    remaining = min(45, deadline - time.monotonic())
                    if remaining <= 0:
                        raise ValueError("npm repair time budget exhausted")
                    return subprocess.run([npm, *args], cwd=workdir, env=env,
                                          capture_output=True, text=True, timeout=remaining)

                generated = run(GENERATE_ARGS)
                if generated.returncode != 0:
                    raise ValueError(f"npm could not generate the lockfile (exit {generated.returncode})")
                fixed = run(FIX_ARGS)
                if fixed.returncode not in (0, 1):
                    raise ValueError(f"npm compatible advisory repair failed (exit {fixed.returncode})")
                tree = run(LOCK_CHECK_ARGS)
                _validate_locked_tree(tree.stdout, tree.returncode)
                audited = run(AUDIT_ARGS)
                report = _audit_report(audited.stdout, audited.returncode)
                check["audit"] = report
                candidate = _snapshot(stage)
                _validate_sources(stage, candidate)
                lock = json.loads(candidate[lock_rel])
                if lock.get("lockfileVersion") not in (2, 3):
                    raise ValueError("npm did not produce a current lockfile")
                _validate_manifest(json.loads(candidate[manifest_rel]), lock["packages"][""], manifest_rel.as_posix())
                remaining = {name: item["severity"] for name, item in report["vulnerabilities"].items()
                             if item["severity"] in {"high", "critical"}}
                if any(name not in baseline or (severity == "critical" and baseline[name] != "critical")
                       for name, severity in remaining.items()):
                    raise ValueError("Candidate still has new high/critical findings; revise dependency declarations")
                changes = {rel: blob for rel, blob in candidate.items() if original.get(rel) != blob}
                if any(not rel.is_relative_to(rel_dir) or rel.name not in {"package.json", "package-lock.json"}
                       for rel in changes):
                    raise ValueError("npm attempted a change outside the requested dependency project")
                for rel in changes:
                    if rel.name == "package.json":
                        before = json.loads(original[rel])
                        after = json.loads(candidate[rel])
                        if {k: v for k, v in before.items() if k not in DEPENDENCY_SECTIONS} != {
                            k: v for k, v in after.items() if k not in DEPENDENCY_SECTIONS
                        }:
                            raise ValueError("npm attempted to change non-dependency package metadata")
                if _snapshot(root) != original:
                    raise ValueError("Product dependency files changed during repair; current files were preserved")
                written: list[Path] = []
                try:
                    for rel, blob in sorted(changes.items()):
                        target = root / rel
                        if not target.resolve().is_relative_to(root):
                            raise ValueError("Dependency output points outside the product")
                        write_text_atomic(target, blob.decode("utf-8"))
                        written.append(rel)
                except (OSError, ValueError):
                    for rel in reversed(written):
                        if rel in original:
                            write_text_atomic(root / rel, original[rel].decode("utf-8"))
                        else:
                            (root / rel).unlink(missing_ok=True)
                    raise
                check["changed_files"] = [p.as_posix() for p in sorted(changes)]
                check["sha256"] = {p.as_posix(): hashlib.sha256(blob).hexdigest() for p, blob in changes.items()}
                check["passed"] = not remaining
                if remaining:
                    check["issues"].append("High/critical findings remain; Developer must choose compatible parent/major upgrades")
        except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.TimeoutExpired) as exc:
            check["issues"].append(str(exc)[:1000])
        result["issues"].extend(f"{rel_dir}: {issue}" for issue in check["issues"])
        result["changed_files"].extend(p for p in check["changed_files"] if p not in result["changed_files"])
    result["passed"] = bool(result["checks"]) and all(c["passed"] for c in result["checks"])
    return result
