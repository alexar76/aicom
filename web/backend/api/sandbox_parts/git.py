"""Git on a product's code: init, push and status, ref-name validation, and whether a product
has code or HTML to show.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import HTTPException

from core.logging_utils import log_suppressed
from web.backend.services.sandbox_preview_auth import sanitize_git_remote_line
from web.backend.services.url_safety import validate_git_remote_url

# Logged under the sandbox module's own name, whatever package path it was imported by.
logger = logging.getLogger(__name__.rsplit(".", 2)[0] + ".sandbox")


_GIT_REF_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._/@+-]*$')


def _validate_git_ref_name(value: str, label: str = "ref") -> str:
    """Reject git CLI argument injection: no leading ``-``, whitelist chars only."""
    v = (value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail=f"git {label} is required")
    if v.startswith("-"):
        raise HTTPException(status_code=400, detail=f"git {label} must not start with '-'")
    if not sandbox_api._GIT_REF_RE.match(v):
        raise HTTPException(status_code=400, detail=f"git {label} contains invalid characters: {v!r}")
    return v


# ── Git Integration ──────────────────────────────────────────────────────


def _git_init_blocking(product_code_dir: Path, product_id: str, safe_remote: str) -> dict:
    """Blocking git init body — run via ``asyncio.to_thread`` to keep the event loop free."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "init"],
            cwd=str(product_code_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git init failed: {result.stderr}")

        # Configure basic git user
        subprocess.run(
            ["git", "config", "user.email", "ai-factory@aicom.local"],
            cwd=str(product_code_dir), capture_output=True, timeout=5
        )
        subprocess.run(
            ["git", "config", "user.name", "AI-Factory"],
            cwd=str(product_code_dir), capture_output=True, timeout=5
        )

        # Initial commit of existing code
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(product_code_dir), capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit - AI-Factory generated code"],
            cwd=str(product_code_dir), capture_output=True, timeout=10
        )

        # Set remote if provided
        if safe_remote:
            subprocess.run(
                ["git", "remote", "add", "origin", safe_remote],
                cwd=str(product_code_dir), capture_output=True, timeout=5
            )

        logger.info(f"Git repository initialized for product {product_id}")
        return {
            "status": "initialized",
            "product_id": product_id,
            "code_dir": str(product_code_dir),
            "remote": safe_remote or None,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git init timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git executable not found in container")


def _git_push_blocking(product_code_dir: Path, product_id: str, remote: str, branch: str) -> dict:
    """Blocking git push body — run via ``asyncio.to_thread`` so a slow remote never blocks the loop."""
    try:
        import subprocess

        # Check if remote is configured
        remote_check = subprocess.run(
            ["git", "remote", "get-url", remote],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        if remote_check.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Remote '{remote}' not configured. Set a remote URL first.")
        configured_url = (remote_check.stdout or "").strip()
        try:
            validate_git_remote_url(configured_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsafe git remote: {exc}") from exc

        # Add all changes
        subprocess.run(["git", "add", "-A"], cwd=str(product_code_dir), capture_output=True, timeout=10)

        # Commit if there are changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        if status.stdout.strip():
            subprocess.run(
                ["git", "commit", "-m", f"Auto-commit: AI-Factory update"],
                cwd=str(product_code_dir), capture_output=True, timeout=10
            )

        # Push to remote
        push_result = subprocess.run(
            ["git", "push", remote, branch],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=30
        )
        if push_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git push failed: {push_result.stderr}")

        return {
            "status": "pushed",
            "product_id": product_id,
            "remote": remote,
            "branch": branch,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git operation timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git executable not found in container")


def _git_status_blocking(product_code_dir: Path, product_id: str) -> dict:
    """Blocking git status body — run via ``asyncio.to_thread`` to keep the event loop free."""
    try:
        import subprocess

        # Check remote
        remote_result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        remotes = [
            sanitize_git_remote_line(line)
            for line in remote_result.stdout.strip().split("\n")
            if line.strip()
        ]

        # Check branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        branch = branch_result.stdout.strip()

        # Check status
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        changes = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []

        # Check log
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        commits = log_result.stdout.strip().split("\n") if log_result.stdout.strip() else []

        return {
            "status": "initialized",
            "product_id": product_id,
            "branch": branch,
            "remotes": remotes,
            "uncommitted_changes": len(changes),
            "change_list": changes[:20],
            "recent_commits": commits,
        }
    except FileNotFoundError:
        return {"status": "error", "detail": "git executable not found"}


# ── Helpers to check product code readiness ─────────────────────────────────


def _product_has_code(product_id: str) -> bool:
    """Check if a product has actual generated code files on disk."""
    from web.backend.services.product_code_presence import product_has_code

    return product_has_code(sandbox_api.resolve_product_code_dir(product_id))


def _product_has_html_files(product_id: str) -> bool:
    """Check if a product has at least one .html file in its code directory."""
    product_code_dir = sandbox_api.resolve_product_code_dir(product_id)
    if not product_code_dir.exists():
        return False
    try:
        for _ in product_code_dir.rglob("*.html"):
            return True
    except Exception as _suppressed_exc:
        log_suppressed(logger, "non-fatal (web/backend/api/sandbox.py)", exc_info=_suppressed_exc)
    return False


# Imported last on purpose: this code reads sandbox's state, settings and helpers at
# call time (where tests patch them), and either module may load first.
from .. import sandbox as sandbox_api  # noqa: E402
