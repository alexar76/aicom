"""Reading a product's tree for QA: code files, files that parse, and the file a finding
belongs to.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.logging_utils import log_suppressed

from .helpers import logger


class TreeReadingMixin:
    """Find a product's files and the file each kind of finding names."""

    def _discover_code_files(self, product_id: str) -> list[dict]:
        """Discover Python code files for this product."""
        files = []
        from core.code_discovery import iter_product_files, should_skip_code_path
        from core.paths import agent_artifact_dir, code_dir

        search_dirs = [
            code_dir(product_id),
            agent_artifact_dir("dev", product_id),
        ]
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for fpath in iter_product_files(search_dir, "*.py"):
                if should_skip_code_path(fpath):
                    continue
                try:
                    content = fpath.read_text()
                    files.append({
                        "path": str(fpath),
                        "content": content,
                        "size": len(content),
                        "lines": content.count("\n") + 1,
                    })
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)
        return files

    @staticmethod
    def _py_file_parses(code_root: Path, rel: str) -> bool:
        """True when the named Python file exists and ast.parse succeeds."""
        from core.product_paths import resolve_product_path

        resolved = resolve_product_path(code_root, rel) or rel
        path = code_root / resolved
        if not path.is_file() or path.suffix != ".py":
            return False
        import ast

        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            return False
        return True

    @staticmethod
    def _spa_surface_file(code_dir: Path, text: str = "") -> str | None:
        """The React page the visitor actually sees, not the Vite index.html shell."""
        low = (text or "").lower()
        prefer: tuple[str, ...] = ()
        if "/operator" in low or "operator dashboard" in low or "operator console" in low:
            prefer = (
                "frontend/src/pages/OperatorDashboard.tsx",
                "frontend/src/pages/Operator.tsx",
                "frontend/src/App.tsx",
            )
        elif "/analytics" in low or "analytics dashboard" in low:
            prefer = (
                "frontend/src/pages/AnalyticsDashboard.tsx",
                "frontend/src/pages/Analytics.tsx",
                "frontend/src/App.tsx",
            )
        elif "/login" in low or "operator login" in low:
            prefer = (
                "frontend/src/pages/Login.tsx",
                "frontend/src/pages/OperatorLogin.tsx",
                "frontend/src/App.tsx",
            )
        for rel in prefer:
            if (code_dir / rel).is_file():
                return rel
        for rel in (
            "frontend/src/pages/PublicWidget.tsx",
            "frontend/src/pages/Home.tsx",
            "frontend/src/pages/Landing.tsx",
            "frontend/src/App.tsx",
            "src/pages/PublicWidget.tsx",
            "src/pages/Home.tsx",
            "src/App.tsx",
        ):
            if (code_dir / rel).is_file():
                return rel
        pages = code_dir / "frontend" / "src" / "pages"
        if pages.is_dir():
            for path in sorted(pages.glob("*.tsx")):
                return path.relative_to(code_dir).as_posix()
        return None

    @staticmethod
    def _demo_issue_file(code_dir: Path, issue: dict | str) -> str | None:
        """CSS or the public widget, not the Vite index.html shell.

        Demo/TZ findings were hardcoded to index.html. After E2E went green the only leftover
        was ux_low_contrast_cta — a static CSS ratio — and the round still edited the shell.
        Contrast and empty/toast live in styles + PublicWidget.
        """
        if isinstance(issue, dict):
            blob = f"{issue.get('code') or ''} {issue.get('detail') or ''}"
        else:
            blob = str(issue)
        low = blob.lower()
        visual = (
            "ux_low_contrast" in low
            or "visual_" in low
            or "empty_state" in low
            or "toast" in low
            or "cta" in low
        )
        if visual:
            for rel in (
                "frontend/src/styles/index.css",
                "frontend/src/index.css",
                "frontend/src/App.css",
                "frontend/style.css",
                "style.css",
                "frontend/src/pages/PublicWidget.tsx",
                "frontend/src/App.tsx",
            ):
                if (code_dir / rel).is_file():
                    return rel
        return TreeReadingMixin._spa_surface_file(code_dir, blob)

    @staticmethod
    def _auth_dependency_file(code_dir: Path) -> str | None:
        """The shared get_current_user (or equivalent), not the router that returned 401.

        Mapping auth_rejected:/api/analytics/dashboards to analytics.py is how six rounds
        flip-flopped two routers between cookie-only and Bearer-only. The fix belongs in
        one dependency both routers already use.
        """
        hits: list[Path] = []
        for path in code_dir.rglob("*.py"):
            if any(
                part in path.parts
                for part in (
                    ".aicom_sandbox",
                    "node_modules",
                    "__pycache__",
                    ".venv",
                    "tests",
                    "test",
                )
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"^def get_current_user\b", text, re.M):
                hits.append(path)
        if not hits:
            return None

        def _rank(path: Path) -> tuple[int, str]:
            name = path.name.lower()
            if name == "deps.py":
                return (0, path.as_posix())
            if name in {"security.py", "auth_deps.py"}:
                return (1, path.as_posix())
            return (2, path.as_posix())

        hits.sort(key=_rank)
        try:
            return hits[0].relative_to(code_dir).as_posix()
        except ValueError:
            return None

    @staticmethod
    def _journey_issue_file(code_dir, text: str) -> str | None:
        """The file behind a runtime journey finding, via the route table.

        `demo_login_failed:/login` carried `file: code/<product>` — a directory, not a file — so the
        scope stayed empty, nothing was attached, and the round guessed. Measured guess, from the log:
        it edited test_rule_engine.py and test_advisory_api.py while the defect lived in the login
        handler. The route table already knows `/login` -> routers/auth.py; this is the missing wire.
        """
        import re as _re

        try:
            from core.product_paths import resolve_product_path
            from web.backend.services.api_contract_check import route_handler_file

            # A python path in the line (boot tracebacks carry one) beats endpoint inference.
            m = _re.search(r"\(?([\w./-]+\.py)(?::\d+)?\)?", text)
            if m:
                resolved = resolve_product_path(code_dir, m.group(1))
                if resolved:
                    return resolved
            # A 401 is a dependency problem, not a router problem. Mapping
            # auth_rejected:/api/analytics/dashboards to analytics.py is how six rounds
            # rewrote two routers in alternation and never touched get_current_user.
            if "auth_rejected" in text:
                dep = TreeReadingMixin._auth_dependency_file(code_dir)
                if dep:
                    return dep
            # Browser a11y / spec-alignment findings were filed against index.html, the Vite
            # shell. The heading lives in the route component (PublicWidget.tsx already had
            # <h1>Sentinel</h1> while a11y_missing_h1 stayed red). When the crawl names
            # /operator or /analytics, that route's page — not the public widget.
            low = text.lower()
            if (
                "a11y_missing_h1" in low
                or "a11y_preview_served_api_json" in low
                or "spec_alignment_llm_failed" in low
                or "blank_or_tiny_ui" in low
                or "pageerror" in low
                or "console_error" in low
                or "/operator" in low
                or "/analytics" in low
            ):
                spa = TreeReadingMixin._spa_surface_file(code_dir, text)
                if spa:
                    return spa
            ep = _re.search(r":(/[^\s:,)]+)", text)
            if ep:
                return route_handler_file(code_dir, ep.group(1))
        except Exception:
            return None
        return None

    def _charter_from_store(self, product_id: str, fallback: str) -> str:
        """Idea, spec and admin instructions as recorded for the product.

        Read straight from the pipeline store rather than the task payload, because the payload is
        assembled per stage and does not always carry them — and a charter check that silently sees an
        empty charter reports "nothing foreign here", which is the wrong answer wearing the right face.
        """
        import sqlite3

        db = self.data_root / "state" / "pipeline.db"
        if not db.is_file():
            return fallback
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "select idea, spec, extras from products where id=?", (product_id,)
                ).fetchone()
        except Exception:
            return fallback
        if not row:
            return fallback
        idea, spec, extras = row
        try:
            admin = (json.loads(extras or "{}") or {}).get("admin_instructions") or ""
        except (ValueError, TypeError):
            admin = ""
        text = " ".join([str(idea or ""), str(spec or ""), str(admin)])
        return text if len(text.strip()) > len(fallback.strip()) else fallback
