"""Small compatibility patches: a settings module that exports ``settings`` and an SPA fallback
that answers API misses with a 404.
"""

from __future__ import annotations

import re
from pathlib import Path


_SETTINGS_EXPORT_MARKER = "# aicom-factory-settings-export"

_SETTINGS_EXPORT_SHIM = '''
# aicom-factory-settings-export — vendored only; product tree under data/code is untouched.
# Generated apps often ``from .config import settings`` and read ``settings.SANDBOX_DEMO_EMAIL``
# while config.py only defines ``get_settings()`` + snake_case fields. Without this shim the
# Vercel function dies at import with ImportError / AttributeError (FUNCTION_INVOCATION_FAILED).
class _AicomSettingsView:
    __slots__ = ("_inner",)

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name: str):
        inner = object.__getattribute__(self, "_inner")
        if name in ("ALGORITHM", "algorithm"):
            for cand in ("algorithm", "ALGORITHM", "jwt_algorithm"):
                if hasattr(inner, cand):
                    val = getattr(inner, cand)
                    if val:
                        return val
            return "HS256"
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)


settings = _AicomSettingsView(get_settings())
'''


_SETTINGS_GETATTR_WITHOUT_ALG = '''    def __getattr__(self, name: str):
        inner = object.__getattribute__(self, "_inner")
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)
'''

_SETTINGS_GETATTR_WITH_ALG = '''    def __getattr__(self, name: str):
        inner = object.__getattribute__(self, "_inner")
        if name in ("ALGORITHM", "algorithm"):
            for cand in ("algorithm", "ALGORITHM", "jwt_algorithm"):
                if hasattr(inner, cand):
                    val = getattr(inner, cand)
                    if val:
                        return val
            return "HS256"
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)
'''


def ensure_settings_module_export(api_dir: Path) -> list[str]:
    """Make ``from .config import settings`` work (Vercel bundle and sandbox uvicorn)."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("config.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "def get_settings" not in text:
            continue
        if _SETTINGS_EXPORT_MARKER in text:
            if 'name in ("ALGORITHM"' not in text and _SETTINGS_GETATTR_WITHOUT_ALG in text:
                path.write_text(
                    text.replace(_SETTINGS_GETATTR_WITHOUT_ALG, _SETTINGS_GETATTR_WITH_ALG),
                    encoding="utf-8",
                )
                notes.append(path.relative_to(root).as_posix())
            continue
        path.write_text(text.rstrip() + "\n" + _SETTINGS_EXPORT_SHIM, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_SPA_API_404_TUPLE_RE = re.compile(
    r'return\s+\{\s*["\']detail["\']\s*:\s*["\']Not Found["\']\s*\}\s*,\s*404\b',
    re.MULTILINE,
)
_SPA_API_404_MARKER = "# aicom-factory-spa-api-404"


def patch_spa_api_not_found_tuple(api_dir: Path) -> list[str]:
    """Fix FastAPI SPA catch-alls that ``return {detail}, 404`` (tuple → HTTP 200 body).

    Live gate probes ``/api/__aicom_missing_route_probe__`` and fails when the
    status line is 200 with a serialised ``[{detail}, 404]`` body.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("main.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _SPA_API_404_TUPLE_RE.search(text):
            continue
        new = text
        if "JSONResponse" not in new:
            if "from fastapi.responses import FileResponse" in new:
                new = new.replace(
                    "from fastapi.responses import FileResponse",
                    "from fastapi.responses import FileResponse, JSONResponse",
                    1,
                )
            elif "from fastapi.responses import" in new:
                new = new.replace(
                    "from fastapi.responses import",
                    "from fastapi.responses import JSONResponse,",
                    1,
                )
            else:
                new = "from fastapi.responses import JSONResponse\n" + new
        new = _SPA_API_404_TUPLE_RE.sub(
            'return JSONResponse({"detail": "Not Found"}, status_code=404)  '
            + _SPA_API_404_MARKER,
            new,
            count=1,
        )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes
