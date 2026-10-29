"""Git on a product's code: init, push and status, ref-name validation, and whether a product
has code or HTML to show.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from fastapi import HTTPException

from core.logging_utils import log_suppressed
from core.product_git import ProductGit, UnsafeProductGit
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
        if safe_remote:
            safe_remote = validate_git_remote_url(safe_remote)
        with ProductGit(product_code_dir) as git:
            result = git.init()
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail="git init failed")
            git.run(["config", "user.email", "ai-factory@aicom.local"], timeout=5)
            git.run(["config", "user.name", "AI-Factory"], timeout=5)
            staged = git.run(["add", "-A"])
            if staged.returncode:
                raise HTTPException(status_code=500, detail="git add failed")
            git.run(["commit", "-m", "Initial commit - AI-Factory generated code"])
            if safe_remote:
                git.run(["remote", "add", "origin", safe_remote], timeout=5)

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
    except (UnsafeProductGit, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Unsafe product Git metadata; manual review required") from exc


def _git_push_blocking(product_code_dir: Path, product_id: str, remote: str, branch: str) -> dict:
    """Blocking git push body — run via ``asyncio.to_thread`` so a slow remote never blocks the loop."""
    try:
        remote = _validate_git_ref_name(remote, "remote")
        branch = _validate_git_ref_name(branch, "branch")
        with ProductGit(product_code_dir) as git:
            # Validate every push URL, including pushurl overrides; no URL
            # rewrites, transport helpers or inherited credentials are accepted.
            remote_check = git.run(["remote", "get-url", "--push", "--all", remote], timeout=5)
            if remote_check.returncode != 0:
                raise HTTPException(status_code=400, detail="Remote not configured")
            for configured_url in remote_check.stdout.splitlines():
                validate_git_remote_url(configured_url)
            staged = git.run(["add", "-A"])
            if staged.returncode:
                raise HTTPException(status_code=500, detail="git add failed")
            status = git.run(["status", "--porcelain"], timeout=5)
            if status.returncode:
                raise HTTPException(status_code=500, detail="git status failed")
            if status.stdout.strip():
                committed = git.run(["commit", "-m", "Auto-commit: AI-Factory update"])
                if committed.returncode:
                    raise HTTPException(status_code=500, detail="git commit failed")
            push_result = git.run(["push", "--", remote, branch], timeout=30)
            if push_result.returncode != 0:
                raise HTTPException(status_code=500, detail="git push failed")

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
    except (UnsafeProductGit, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Unsafe product Git metadata; manual review required") from exc


def _git_status_blocking(product_code_dir: Path, product_id: str) -> dict:
    """Blocking git status body — run via ``asyncio.to_thread`` to keep the event loop free."""
    try:
        with ProductGit(product_code_dir) as git:
            remote_result = git.run(["remote", "-v"], timeout=5)
            branch_result = git.run(["branch", "--show-current"], timeout=5)
            status_result = git.run(["status", "--porcelain"], timeout=5)
            log_result = git.run(["log", "--oneline", "-10"], timeout=5)
        if status_result.returncode:
            raise HTTPException(status_code=400, detail="Git repository cannot be read safely")
        remotes = [
            sanitize_git_remote_line(line)
            for line in remote_result.stdout.strip().split("\n")
            if line.strip()
        ]

        branch = branch_result.stdout.strip()
        changes = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []
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
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="git status timed out") from exc
    except (UnsafeProductGit, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Unsafe product Git metadata; manual review required") from exc


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
