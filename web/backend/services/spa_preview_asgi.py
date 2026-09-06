"""ASGI overlay: serve a Vite/React dist for non-API paths.

Copied into ``.aicom_sandbox/<id>/spa_overlay/`` and loaded by the product
preview venv — this module must not import factory packages.

Generated FastAPI apps often answer ``GET /`` with JSON (``{"message":"... API"}``).
QA Playwright then scores every route as that stub instead of the widget in
``frontend/dist``. The overlay matches how Vercel serves the same tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

from starlette.responses import FileResponse


def should_passthrough_to_api(path: str) -> bool:
    if not path:
        path = "/"
    if path in ("/docs", "/redoc", "/openapi.json", "/openapi.yaml"):
        return True
    if path.startswith("/docs/") or path.startswith("/redoc/"):
        return True
    if path == "/api" or path.startswith("/api/"):
        return True
    if path == "/health" or path.startswith("/health/"):
        return True
    return False


def resolve_spa_file(dist_dir: Path, url_path: str) -> Optional[Path]:
    dist_dir = dist_dir.resolve()
    raw = (url_path or "/").split("?", 1)[0]
    rel = unquote(raw).lstrip("/")
    index = dist_dir / "index.html"
    if not rel or rel.endswith("/"):
        return index if index.is_file() else None
    candidate = dist_dir / rel
    try:
        resolved = candidate.resolve()
        resolved.relative_to(dist_dir)
    except ValueError:
        return index if index.is_file() else None
    if resolved.is_file():
        return resolved
    if Path(rel).suffix:
        return None
    return index if index.is_file() else None


class SpaDistFallback:
    def __init__(self, app: Any, dist_dir: Path) -> None:
        self.app = app
        self.dist_dir = Path(dist_dir)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            path = scope.get("path") or "/"
            if not should_passthrough_to_api(path):
                target = resolve_spa_file(self.dist_dir, path)
                if target is not None:
                    await FileResponse(target)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def wrap_asgi(app: Any, dist_dir: Path) -> SpaDistFallback:
    return SpaDistFallback(app, dist_dir)
