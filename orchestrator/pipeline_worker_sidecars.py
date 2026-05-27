"""
Pipeline worker sidecars (SRP split)
====================================
Storefront readiness enforcement and __runtime_test__ command inference live here
so ``pipeline_worker.py`` stays focused on the main orchestration loop and agent dispatch.

See ``docs/architecture-orchestrator.md``.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from core.quality_settings import max_pipeline_repair_rounds_for_delivery_profile, gate_failing_model
from orchestrator.worker_utils import env_truthy
from web.backend.services.marketplace_quality import evaluate_marketplace_quality

logger = logging.getLogger("pipeline-worker")


class PipelineWorkerSidecarMixin:
    """Mixin for ``PipelineWorker`` — marketplace gates + runtime test harness."""

    data_root: Path  # set on concrete class

    def _marketplace_readiness(self, product_id: str, *, delivery_profile: str | None = None) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        code_dir = self.data_root / "code" / product_id
        manifest_path = code_dir / "code_manifest.json"
        has_code = False
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                files = manifest.get("files") if isinstance(manifest, dict) else []
                if isinstance(files, list):
                    for entry in files:
                        rel = ""
                        if isinstance(entry, dict):
                            rel = str(entry.get("path") or entry.get("file_path") or "").strip()
                        if rel and (code_dir / rel).exists():
                            has_code = True
                            break
            except Exception:
                logger.debug("Failed to parse code_manifest.json for %s", product_id, exc_info=True)
                has_code = False
        if not has_code:
            reasons.append("missing generated code artifacts (code_manifest/files)")
        spec = self._load_spec(product_id)
        mq = evaluate_marketplace_quality(
            product_id, specification=spec, delivery_profile=delivery_profile
        )
        if not bool(mq.get("eligible")):
            mq_reasons = mq.get("reasons")
            if isinstance(mq_reasons, list) and mq_reasons:
                reasons.extend(str(x) for x in mq_reasons[:6])
            else:
                reasons.append("marketplace quality gate failed")
        return len(reasons) == 0, reasons

    def _enforce_marketplace_readiness(self, products: dict, task_queue: list, now: float) -> bool:
        if not env_truthy("AIFACTORY_STOREFRONT_REMEDIATION_ENABLED", "1"):
            return False

        mode_raw = os.environ.get("AIFACTORY_STOREFRONT_REMEDIATION_MODE", "full").strip().lower().replace("-", "_")
        if mode_raw == "annotate_only":
            remediation_mode = "annotate_only"
        elif mode_raw in ("full", "remediate", "repair", ""):
            remediation_mode = "full"
        else:
            logger.warning(
                "Unknown AIFACTORY_STOREFRONT_REMEDIATION_MODE=%r — using full",
                os.environ.get("AIFACTORY_STOREFRONT_REMEDIATION_MODE"),
            )
            remediation_mode = "full"

        try:
            max_per_cycle = int(os.environ.get("AIFACTORY_STOREFRONT_REMEDIATION_MAX_PER_CYCLE", "8"))
        except ValueError:
            max_per_cycle = 8
        max_per_cycle = max(1, max_per_cycle)

        from web.backend.services.product_followup import (
            admin_force_list_enabled,
            annotate_automated_storefront_backlog,
            is_product_improvement_on_hold,
            storefront_followup_not_pursuing,
        )

        def _pending_completion_task(product_id: str) -> bool:
            return any(
                t.get("product_id") == product_id
                and t.get("agent_type") == "__complete__"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )

        candidates: list[tuple[str, dict, list[str]]] = []
        changed = False
        for pid, product in products.items():
            state_upper = str(product.get("state") or "").upper()
            if state_upper not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
                continue
            if _pending_completion_task(pid):
                continue
            if storefront_followup_not_pursuing(pid):
                continue
            if is_product_improvement_on_hold(pid):
                continue
            if admin_force_list_enabled(pid):
                continue
            ready, reasons = self._marketplace_readiness(
                pid, delivery_profile=product.get("delivery_profile")
            )
            if ready:
                try:
                    from web.backend.services.product_followup import (
                        merge_mark_storefront_established_listing,
                    )

                    if merge_mark_storefront_established_listing(pid):
                        product["updated_at"] = now
                        changed = True
                except Exception:
                    logger.debug("merge_mark_storefront_established_listing failed for %s", pid, exc_info=True)
                continue
            candidates.append((pid, product, reasons))

        candidates.sort(key=lambda row: float(row[1].get("updated_at") or row[1].get("created_at") or 0))

        scheduled = 0
        for pid, product, reasons in candidates:
            if scheduled >= max_per_cycle:
                break

            max_quality_loops = max_pipeline_repair_rounds_for_delivery_profile(product.get("delivery_profile"))

            has_dev_fix = any(
                t.get("product_id") == pid
                and t.get("agent_type") == "developer"
                and t.get("state") == "DEV_FIXING"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )
            if has_dev_fix:
                continue

            if remediation_mode == "annotate_only":
                try:
                    annotate_automated_storefront_backlog(pid, reasons)
                except Exception:
                    logger.exception("annotate_automated_storefront_backlog failed for %s", pid)
                scheduled += 1
                logger.info(
                    "storefront remediation annotate_only for %s (no DEV_FIXING): %s",
                    pid,
                    reasons[:3],
                )
                continue

            next_round = int(product.get("quality_repair_round") or 0) + 1
            if next_round > max_quality_loops:
                product["state"] = "FAILED"
                product["failure_reason"] = (
                    "Product could not satisfy storefront readiness gates after "
                    f"{max_quality_loops} remediation cycles."
                )
                product["updated_at"] = now
                try:
                    from web.backend.services.pipeline_failed_notify import (
                        notify_pipeline_product_failed,
                    )

                    notify_pipeline_product_failed(
                        pid,
                        product=product,
                        failure_reason=product["failure_reason"],
                    )
                except Exception:
                    logger.debug(
                        "pipeline_failed_notify failed for %s (marketplace readiness exhausted)",
                        pid,
                        exc_info=True,
                    )
                changed = True
                logger.error(
                    "Marketplace readiness failed for %s and repair budget exhausted (%s/%s): %s",
                    pid,
                    next_round,
                    max_quality_loops,
                    reasons[:3],
                )
                scheduled += 1
                continue

            try:
                annotate_automated_storefront_backlog(pid, reasons)
            except Exception:
                logger.exception("annotate_automated_storefront_backlog failed for %s", pid)

            product["state"] = "BUG_FOUND"
            product["quality_repair_round"] = next_round
            product["updated_at"] = now
            product["last_bug_context"] = {
                "source": "marketplace_readiness",
                "issues": reasons,
            }
            task_queue.append(
                {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "developer",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "marketplace_readiness_feedback": {
                            "passed": False,
                            "reasons": reasons,
                        },
                        "quality_repair_round": next_round,
                        "quality_repair_max": max_quality_loops,
                        "admin_instructions": (
                            "Storefront readiness remediation. Fix demo/code quality so the product appears "
                            "in marketplace listing (code artifacts present + marketplace quality eligible)."
                        ),
                        **({"gate_failing_model": gfm} if (gfm := gate_failing_model()) and next_round >= 1 else {}),
                    },
                    "created_at": now,
                    "priority": self._get_priority("developer"),
                }
            )
            changed = True
            scheduled += 1
            logger.warning(
                "Reopened COMPLETED product %s for storefront remediation (%s/%s): %s",
                pid,
                next_round,
                max_quality_loops,
                reasons[:3],
            )
        return changed

    def _run_runtime_tests(self, product_id: str, task_queue: list) -> dict[str, Any]:
        code_dir = self.data_root / "code" / product_id
        if not code_dir.exists():
            return {"passed": False, "error": "code directory missing", "results": []}
        manifest: dict[str, Any] = {}
        manifest_path = code_dir / "code_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                logger.debug("Failed to parse code_manifest.json for %s", product_id, exc_info=True)
                manifest = {}
        test_commands = manifest.get("test_commands") or []
        if not isinstance(test_commands, list):
            test_commands = []
        results: list[dict[str, Any]] = []
        passed = True
        with tempfile.TemporaryDirectory(prefix=f"aifactory-{product_id}-") as td:
            workdir = Path(td) / "workspace"
            shutil.copytree(code_dir, workdir, dirs_exist_ok=True)
            if not test_commands:
                test_commands = self._infer_default_test_commands(workdir)
            if not test_commands:
                return {"passed": True, "results": [{"command": "default_sanity", "exit_code": 0}], "commands": []}
            for cmd in test_commands:
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                try:
                    argv = shlex.split(cmd, posix=os.name != "nt")
                    if not argv:
                        continue
                    proc = subprocess.run(
                        argv,
                        shell=False,
                        cwd=str(workdir),
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    item = {
                        "command": cmd,
                        "exit_code": proc.returncode,
                        "stdout": (proc.stdout or "")[:4000],
                        "stderr": (proc.stderr or "")[:4000],
                    }
                    if proc.returncode != 0:
                        passed = False
                except Exception as e:
                    item = {"command": cmd, "exit_code": -1, "stdout": "", "stderr": str(e)}
                    passed = False
                results.append(item)
        return {"passed": passed, "results": results, "commands": test_commands}

    def _infer_default_test_commands(self, workdir: Path) -> list[str]:
        commands: list[str] = []
        py_files = [p for p in workdir.rglob("*.py") if p.is_file()]
        js_files = [p for p in workdir.rglob("*.js") if p.is_file()]

        if py_files:
            for pyf in py_files:
                rel = pyf.relative_to(workdir)
                commands.append(
                    f"{sys.executable} -c \"import py_compile; py_compile.compile(r'{rel}', doraise=True)\""
                )
            if (workdir / "tests").exists() or any("test_" in p.name for p in py_files):
                commands.append(f"{sys.executable} -m pytest -q --maxfail=1")

        pkg_json = workdir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            except Exception:
                logger.debug("Failed to parse package.json for %s", product_id, exc_info=True)
                pkg = {}
            scripts = pkg.get("scripts") if isinstance(pkg, dict) else {}
            test_script = scripts.get("test") if isinstance(scripts, dict) else None
            placeholder = isinstance(test_script, str) and "no test specified" in test_script.lower()
            if isinstance(test_script, str) and test_script.strip() and not placeholder:
                commands.append("npm run -s test -- --watch=false")
            elif js_files:
                for jsf in js_files[:25]:
                    rel = jsf.relative_to(workdir)
                    commands.append(f"node --check \"{rel}\"")

        return commands
