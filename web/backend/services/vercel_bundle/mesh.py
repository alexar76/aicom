"""The AIMarket mesh client a product calls: legacy invoke paths rewritten, the participant
module vendored, mesh headers added.
"""

from __future__ import annotations

import re
from pathlib import Path


def rewrite_legacy_mesh_invoke_paths(api_dir: Path) -> list[str]:
    """Products often POST ``{ATLAS_BASE_URL}/aimarket/invoke``; ATLAS serves v2.

    Measured live: ``https://atlas.modelmarket.dev/aimarket/invoke`` → 404, while
    ``/ai-market/v2/invoke`` returns the capability. Rewrite only inside the
    vendored Vercel function copy — product tree under ``data/code`` stays untouched.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new = text.replace("/aimarket/invoke", "/ai-market/v2/invoke")
        new = new.replace("/api/aimarket/invoke", "/ai-market/v2/invoke")
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_MESH_HEADERS_MARKER = "# aicom-factory-mesh-participant-headers"

_MESH_HEADERS_METHOD = '''
    def _mesh_headers(self) -> dict:
        """AI-market participant headers (factory autofix). Visitor = trial; channel = paid.

        X-Agent-Key is legacy identity only — ATLAS/Hub do not bill against it.
        ''' + _MESH_HEADERS_MARKER + '''
        """
        import os
        headers: dict = {}
        visitor = (
            os.environ.get("AIMARKET_SANDBOX_VISITOR")
            or os.environ.get("X_AIMARKET_SANDBOX_VISITOR")
            or ""
        ).strip()
        if visitor:
            headers["X-AIMarket-Sandbox-Visitor"] = visitor
        channel = (
            os.environ.get("AIMARKET_PAYMENT_CHANNEL")
            or os.environ.get("X_PAYMENT_CHANNEL")
            or ""
        ).strip()
        if channel:
            headers["X-Payment-Channel"] = channel
            secret = (
                os.environ.get("AIMARKET_PAYMENT_CHANNEL_SECRET")
                or os.environ.get("X_PAYMENT_CHANNEL_SECRET")
                or ""
            ).strip()
            if secret:
                headers["X-Payment-Channel-Secret"] = secret
        key = getattr(self, "agent_key", None) or os.environ.get("ATLAS_AGENT_KEY") or ""
        if key:
            headers["X-Agent-Key"] = str(key)
        return headers
'''


def vendor_aimarket_participant_module(api_dir: Path) -> list[str]:
    """Copy ``core/aimarket_participant.py`` into the function tree for runtime sessions."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    src = Path(__file__).resolve().parents[3] / "core" / "aimarket_participant.py"
    if not src.is_file():
        return notes
    # Prefer next to backend app package when present; else api root.
    targets: list[Path] = []
    for cand in (
        root / "app" / "services" / "aimarket_participant.py",
        root / "backend" / "app" / "services" / "aimarket_participant.py",
        root / "aimarket_participant.py",
    ):
        if cand.parent.is_dir() or cand.parent == root:
            targets.append(cand)
            break
    if not targets:
        targets = [root / "aimarket_participant.py"]
    text = src.read_text(encoding="utf-8")
    for dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and dest.read_text(encoding="utf-8") == text:
            continue
        dest.write_text(text, encoding="utf-8")
        notes.append(dest.relative_to(root).as_posix())
    return notes


def ensure_aimarket_participant_client(api_dir: Path) -> list[str]:
    """Wire Hub v2 + AimarketParticipant into hand-rolled mesh clients.

    Prefers runtime ``get_participant().invoke`` when an ``_invoke`` method posts with
    only ``X-Agent-Key``. Falls back to visitor/channel header injection.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    vendor_aimarket_participant_module(api_dir)
    agent_key_only = re.compile(
        r'headers\s*=\s*\{\s*["\']X-Agent-Key["\']\s*:\s*[^}]+\}',
        re.M,
    )
    invoke_fn = re.compile(
        r"(async\s+def\s+_invoke\s*\([^)]*\)\s*(?:->\s*[^:\n]+)?\s*:\s*\n)"
        r"([\s\S]*?)(?=\n    async def |\n    def |\nclass |\Z)",
        re.M,
    )
    participant_invoke = (
        "    async def _invoke(self, capability_id, input_data) -> dict:\n"
        "        # aicom-factory-mesh-participant-runtime\n"
        "        try:\n"
        "            from .aimarket_participant import get_participant\n"
        "        except ImportError:\n"
        "            try:\n"
        "                from aimarket_participant import get_participant\n"
        "            except ImportError:\n"
        "                from app.services.aimarket_participant import get_participant  # type: ignore\n"
        "        return get_participant().invoke(capability_id, input_data)\n"
    )
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "ai-market" not in text and "aimarket" not in text and "@v1" not in text:
            continue
        if path.name == "aimarket_participant.py":
            continue
        new = text
        if "localhost:8001" in new:
            new = new.replace(
                '"http://localhost:8001"',
                'os.environ.get("AIMARKET_HUB_URL") or os.environ.get("ATLAS_BASE_URL") or "https://modelmarket.dev"',
            )
            new = new.replace(
                "'http://localhost:8001'",
                'os.environ.get("AIMARKET_HUB_URL") or os.environ.get("ATLAS_BASE_URL") or "https://modelmarket.dev"',
            )
            if "import os" not in new and "os.environ" in new:
                new = "import os\n" + new
        if (
            "aicom-factory-mesh-participant-runtime" not in new
            and "async def _invoke" in new
            and ("/aimarket/invoke" in new or "/ai-market/v2/invoke" in new or "X-Agent-Key" in new)
        ):
            replaced, n = invoke_fn.subn(participant_invoke + "\n", new, count=1)
            if n:
                new = replaced
        elif agent_key_only.search(new) and _MESH_HEADERS_MARKER not in new:
            if "class " in new and "def " in new:
                insert_at = new.find("\n    async def ")
                if insert_at < 0:
                    insert_at = new.find("\n    def _invoke")
                if insert_at < 0:
                    insert_at = new.find("\n    def invoke")
                if insert_at >= 0:
                    new = new[:insert_at] + "\n" + _MESH_HEADERS_METHOD + new[insert_at:]
                new = agent_key_only.sub("headers=self._mesh_headers()", new)
            else:
                inline = (
                    'headers={k: v for k, v in {'
                    '"X-AIMarket-Sandbox-Visitor": __import__("os").environ.get("AIMARKET_SANDBOX_VISITOR", ""), '
                    '"X-Payment-Channel": __import__("os").environ.get("AIMARKET_PAYMENT_CHANNEL", ""), '
                    '"X-Payment-Channel-Secret": __import__("os").environ.get("AIMARKET_PAYMENT_CHANNEL_SECRET", ""), '
                    '}.items() if v}'
                )
                new = agent_key_only.sub(inline, new)
        # Prefer Hub base when settings still point at ATLAS-only for billing.
        if "self.base_url = settings.atlas_base_url" in new:
            new = new.replace(
                "self.base_url = settings.atlas_base_url",
                'self.base_url = (__import__("os").environ.get("AIMARKET_HUB_URL") '
                'or getattr(settings, "aimarket_hub_url", None) '
                'or settings.atlas_base_url)',
            )
        if (
            "aicom-factory-mesh-participant-runtime" not in new
            and re.search(r"get_participant\(\)\._invoke\s*\(", new)
        ):
            new = re.sub(
                r"return\s+await\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            new = re.sub(
                r"return\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            if "aicom-factory-mesh-participant-runtime" not in new and "async def _invoke" in new:
                new = new.replace(
                    "async def _invoke",
                    "# aicom-factory-mesh-participant-runtime\n    async def _invoke",
                    1,
                )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes
