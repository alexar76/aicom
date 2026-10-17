"""Whether a product is real work: project realism, methodology and maintainability."""

from __future__ import annotations

import json
from pathlib import Path

from core.logging_utils import log_suppressed
from web.backend.services.domain_methodology import get_domain_pack, select_domain_pack
from web.backend.services.methodology_review import (
    review_implementation as _methodology_review_implementation,
)
from core.json_state import write_text_atomic

from .helpers import logger


class RealismMixin:
    """Project realism, methodology and maintainability."""

    def _assess_project_realism(self, product_id: str, code_files: list[dict]) -> list[dict]:
        """
        Flag toy backend structures that are unlikely to be sellable.

        This check is intentionally heuristic and lightweight:
        - backend-like code should ship with tests;
        - backend-like code should include minimal docs (README);
        - extremely tiny backend module count is suspicious for non-trivial products.
        """
        issues: list[dict] = []
        if not code_files:
            return issues

        py_files = [f for f in code_files if str(f.get("path", "")).endswith(".py")]
        py_count = len(py_files)
        py_blob = "\n".join(str(f.get("content", "")) for f in py_files).lower()

        backend_like = any(
            tok in py_blob
            for tok in ("fastapi", "flask", "django", "@app.", "apirouter", "http")
        )
        if not backend_like:
            return issues

        has_tests = any(
            "/tests/" in str(f.get("path", "")).replace("\\", "/").lower()
            or Path(str(f.get("path", ""))).name.startswith("test_")
            for f in py_files
        )
        if not has_tests:
            issues.append(
                {
                    "severity": "high",
                    "title": "Backend realism: missing explicit test files",
                    "description": (
                        "Backend/API project detected but no dedicated test modules were found "
                        "(expected tests/test_*.py or test_*.py)."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        code_root = Path(self.data_root) / "code" / product_id
        has_readme = (code_root / "README.md").is_file() or (code_root / "readme.md").is_file()
        if not has_readme:
            issues.append(
                {
                    "severity": "medium",
                    "title": "Backend realism: missing README",
                    "description": (
                        "No README found for generated backend package. "
                        "A sellable project should document setup, run, and test commands."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        # If API stack appears to be in a single tiny file, it is likely still a demo skeleton.
        if py_count <= 2:
            issues.append(
                {
                    "severity": "medium",
                    "title": "Backend realism: structure too thin",
                    "description": (
                        "Backend/API code appears to be very small (<=2 Python files). "
                        "Expected clearer separation (routes/services/models/tests) for production-like output."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        # Flag obvious fake API behavior often seen in demo stubs.
        saw_api_handlers = False
        saw_stateful_signal = False
        for file_info in py_files:
            path = str(file_info.get("path", ""))
            content = str(file_info.get("content", ""))
            lower = content.lower()
            api_like = any(tok in lower for tok in ("@app.", "apirouter", "def login", "def register"))
            if not api_like:
                continue
            saw_api_handlers = True

            fake_markers = (
                "mock-jwt-token",
                "mock token",
                "demo token",
                "return {'token': 'mock",
                'return {"token": "mock',
            )
            if any(m in lower for m in fake_markers):
                issues.append(
                    {
                        "severity": "high",
                        "title": "Backend realism: mocked API auth response",
                        "description": (
                            "API/login handler appears to return fake token payloads. "
                            "Replace with real auth flow and persistence-backed credential verification."
                        ),
                        "file": path,
                    }
                )

            # Heuristic: endpoints that look like static JSON stubs.
            # Example pattern:
            #   @app.get(...)
            #   def x(...):
            #       return {"ok": true}
            # This should be treated as non-sellable for non-trivial backend products.
            static_return_hits = 0
            for line in content.splitlines():
                s = line.strip().lower()
                if s.startswith(("return {", 'return {"', "return {'")):
                    static_return_hits += 1
            if "@app." in lower and static_return_hits >= 2:
                issues.append(
                    {
                        "severity": "high",
                        "title": "Backend realism: constant-only API responses",
                        "description": (
                            "Multiple API handlers appear to return static JSON stubs. "
                            "Implement real business logic, persistence-backed state, and input-driven behavior."
                        ),
                        "file": path,
                    }
                )

            # Stateful behavior hints: persistence, service/repository usage, or write operations.
            stateful_markers = (
                "sqlite",
                "sqlalchemy",
                "session",
                "repository",
                "service.",
                "crud",
                "insert ",
                "update ",
                "delete ",
                ".append(",
                ".add(",
                ".commit(",
                "save(",
                "create(",
            )
            if any(tok in lower for tok in stateful_markers):
                saw_stateful_signal = True

        if saw_api_handlers and not saw_stateful_signal:
            issues.append(
                {
                    "severity": "high",
                    "title": "Backend realism: no stateful behavior signals",
                    "description": (
                        "API handlers were detected, but no persistence/service/state-change signals were found. "
                        "Implement stateful business behavior (storage/repository/service writes), not stateless stubs."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        return issues

    def _assess_methodology(
        self,
        *,
        product_id: str,
        idea: str,
        category: str | None,
        spec_payload: dict,
    ) -> dict:
        """Domain methodology gate (post-implementation). See ``agents.methodologist``."""
        inner_spec = (
            spec_payload.get("specification")
            if isinstance(spec_payload, dict) and "specification" in spec_payload
            else spec_payload
        )
        if not isinstance(inner_spec, dict):
            inner_spec = {}

        forced = ""
        if isinstance(inner_spec, dict):
            forced = str(inner_spec.get("domain") or "").strip()
        pack = get_domain_pack(forced) if forced else None
        if pack is None:
            pack = select_domain_pack(idea or "", category=category, spec=inner_spec)
        if pack is None:
            return {
                "product_id": product_id,
                "stage": "post_implementation",
                "domain": None,
                "domain_label": "not_applicable",
                "score": None,
                "checks": {},
                "findings": [],
                "passed": True,
                "skipped": True,
                "reason": "no matching domain methodology pack",
            }

        code_dir = self.data_root / "code" / product_id
        report = _methodology_review_implementation(
            code_dir,
            pack=pack,
            spec=inner_spec,
            stage="post_implementation",
        )
        report["product_id"] = product_id
        try:
            tel_dir = self.data_root / "telemetry" / product_id
            tel_dir.mkdir(parents=True, exist_ok=True)
            write_text_atomic(tel_dir / "methodology_implementation.json", json.dumps(report, indent=2, ensure_ascii=False))
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)
        return report

    def _assess_maintainability(self, product_id: str, code_files: list[dict]) -> dict:
        """
        Lightweight maintainability review:
        - ensure architecture artifact exists;
        - ensure non-trivial backend has layered module shape.
        """
        Path(self.data_root) / "code" / product_id
        arch_path = Path(self.data_root) / "arch" / product_id / "architecture.json"
        py_paths = [str(f.get("path", "")) for f in code_files if str(f.get("path", "")).endswith(".py")]
        py_count = len(py_paths)
        has_arch = arch_path.is_file()
        has_layers = any(
            any(tok in p.lower() for tok in ("/service", "/repository", "/models", "/routes", "/api"))
            for p in py_paths
        )
        backend_like = any(
            tok in "\n".join(str(f.get("content", "")).lower() for f in code_files)
            for tok in ("fastapi", "flask", "django", "@app.", "apirouter")
        )
        issues: list[str] = []
        if not has_arch:
            issues.append("architecture artifact missing (arch/<product>/architecture.json)")
        if backend_like and py_count >= 3 and not has_layers:
            issues.append("backend files lack clear layering (expected routes/services/models/repository split)")
        passed = len(issues) == 0
        return {
            "passed": passed,
            "issues": issues,
            "summary": "Maintainability checks passed." if passed else "; ".join(issues),
            "python_file_count": py_count,
            "has_architecture_artifact": has_arch,
        }
