from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING

from core.logging_utils import log_suppressed
from core.paths import resolve_data_root
from core.quality_settings import quality_constitution_pipeline_enabled
from web.backend.services.benchmark_gate import evaluate_benchmark_gate

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class RuntimeGuards:
    """Isolated runtime gate checks used by PipelineWorker."""

    def __init__(self, data_root: str | Path | None = None):
        self.data_root = resolve_data_root(data_root)

    def load_spec(self, product_id: str) -> dict:
        spec_file = self.data_root / "specs" / product_id / "specification.json"
        if spec_file.exists():
            try:
                with open(spec_file) as f:
                    data = json.load(f)
                inner = data.get("specification")
                if isinstance(inner, dict):
                    return inner
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (orchestrator/runtime_guards.py)", exc_info=_suppressed_exc)
        return {}

    def load_arch(self, product_id: str) -> dict:
        arch_file = self.data_root / "arch" / product_id / "architecture.json"
        if arch_file.exists():
            try:
                with open(arch_file) as f:
                    data = json.load(f)
                inner = data.get("architecture")
                if isinstance(inner, dict):
                    return inner
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (orchestrator/runtime_guards.py)", exc_info=_suppressed_exc)
        return {}

    def architecture_gate(self, product_id: str, *, delivery_profile: str | None = None) -> tuple[bool, list[str]]:
        issues: list[str] = []
        arch = self.load_arch(product_id)
        if not isinstance(arch, dict) or not arch:
            return False, ["architecture artifact missing"]

        try:
            from core.delivery_profile import MARKETING_LANDING, normalize_delivery_profile

            if normalize_delivery_profile(delivery_profile) == MARKETING_LANDING:
                return True, []
        except ImportError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (orchestrator/runtime_guards.py)", exc_info=_suppressed_exc)

        modules = arch.get("modules") or arch.get("components") or []
        if not isinstance(modules, list) or len(modules) < 3:
            issues.append("insufficient architecture modules/layers")

        blob = json.dumps(arch, ensure_ascii=False).lower()
        if not any(k in blob for k in ("service", "repository", "route", "api", "model")):
            issues.append("missing explicit boundaries/layer vocabulary")
        if not any(k in blob for k in ("migration", "schema evolution", "backward compatibility")):
            issues.append("missing migration discipline guidance")
        if not any(k in blob for k in ("ownership", "boundary", "contract", "interface")):
            issues.append("missing module boundary contracts")
        return len(issues) == 0, issues

    def release_critic(self, product_id: str, product: dict) -> tuple[bool, list[str]]:
        if not bool(product.get("production_mode")):
            return True, []
        issues: list[str] = []
        spec = self.load_spec(product_id)
        arch = self.load_arch(product_id)
        if not isinstance(spec, dict) or not spec:
            issues.append("missing specification")
        if not isinstance(arch, dict) or not arch:
            issues.append("missing architecture")

        ds_file = self.data_root / "arch" / product_id / "design_system.json"
        if not ds_file.exists():
            issues.append("missing design_system.json")
        else:
            try:
                raw = json.loads(ds_file.read_text(encoding="utf-8"))
                ds = raw.get("design_system", raw) if isinstance(raw, dict) else {}
                tokens = ds.get("tokens") if isinstance(ds, dict) else None
                if not isinstance(tokens, dict) or len(tokens) < 6:
                    issues.append("design system tokens incomplete")
            except Exception:
                issues.append("design_system.json invalid")

        features = spec.get("core_features") if isinstance(spec, dict) else []
        if not isinstance(features, list) or len(features) < 3:
            issues.append("need at least 3 differentiated USP/core_features")

        # Real-user validation gate: shipped products must have minimum real feedback evidence.
        min_feedback = int(os.environ.get("AIFACTORY_RELEASE_MIN_REAL_FEEDBACK", "1"))
        if min_feedback > 0:
            fb_dir = self.data_root / "feedback"
            count = 0
            if fb_dir.exists():
                for fp in fb_dir.glob("fb-*.json"):
                    try:
                        row = json.loads(fp.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if str(row.get("product_id") or "") == product_id:
                        count += 1
            if count < min_feedback:
                issues.append(f"real_user_validation_failed (feedback<{min_feedback})")

        if quality_constitution_pipeline_enabled():
            try:
                from web.backend.services.quality_constitution import evaluate_quality_constitution

                constitution = evaluate_quality_constitution(product_id, str(self.data_root))
                if not constitution.get("passed", False):
                    issues.extend([f"quality_constitution: {x}" for x in (constitution.get("issues") or [])])
            except Exception:
                issues.append("quality_constitution: evaluation_error")

        require_release_cockpit = os.environ.get("AIFACTORY_RELEASE_REQUIRE_COCKPIT", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if require_release_cockpit:
            try:
                from web.backend.services.release_cockpit import evaluate_release_cockpit

                cockpit = evaluate_release_cockpit(product_id, str(self.data_root))
                if cockpit.get("go_no_go") != "go":
                    rc_issues = cockpit.get("issues") or []
                    issues.extend([f"release_cockpit: {x}" for x in rc_issues] if rc_issues else ["release_cockpit: no_go"])
            except Exception:
                issues.append("release_cockpit: evaluation_error")

        # Built-in benchmark gate (hard policy, no env override).
        scorecard_path = self.data_root / "reports" / "benchmark_scorecard.json"
        if scorecard_path.exists():
            gate = evaluate_benchmark_gate(str(self.data_root))
            if not gate.get("passed", False):
                issues.append(str(gate.get("reason") or "benchmark_gate: unknown"))

        review_mode = os.environ.get("AIFACTORY_HUMAN_REVIEW_MODE", "optional").strip().lower()
        if review_mode not in ("off", "optional", "required"):
            review_mode = "optional"
        if review_mode != "off":
            decision = self._latest_human_review_decision(product_id)
            if decision == "block":
                issues.append("human_review_blocked")
            elif decision != "approve" and review_mode == "required":
                issues.append("human_review_required_pending")

        return len(issues) == 0, issues

    def _latest_human_review_decision(self, product_id: str) -> str:
        """
        Human review decision from feedback stream.

        Supported markers:
        - source == "human_review"
        - review_decision in {"approve","block"}
        - tags contain "human_review" + ("approve"|"block")
        """
        fb_dir = self.data_root / "feedback"
        if not fb_dir.exists():
            return "none"
        latest_ts = -1.0
        latest_decision = "none"
        for fp in fb_dir.glob("fb-*.json"):
            try:
                row = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(row.get("product_id") or "") != product_id:
                continue
            decision = str(row.get("review_decision") or "").strip().lower()
            if decision not in ("approve", "block"):
                tags = [str(x).strip().lower() for x in (row.get("tags") or []) if isinstance(x, (str, int, float))]
                src = str(row.get("source") or "").strip().lower()
                if src == "human_review" or "human_review" in tags:
                    if "block" in tags:
                        decision = "block"
                    elif "approve" in tags:
                        decision = "approve"
            if decision not in ("approve", "block"):
                continue
            ts = float(row.get("created_at") or fp.stat().st_mtime or time.time())
            if ts >= latest_ts:
                latest_ts = ts
                latest_decision = decision
        return latest_decision
