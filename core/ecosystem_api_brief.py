"""What the factory knows about its own ecosystem, phrased so a repair round can use it.

The factory builds products that pay for capabilities from its own mesh, and the knowledge of how to
call those capabilities lived in exactly two places, neither of which reached the agent writing the
code:

* ``atlas/atlas/products.py`` — the real catalogue, with every capability id and input schema;
* a detector that compares a product's calls against it and reports the differences.

So a round would be told "input for atlas.fire.weather@v1 does not match its published schema — field
'bbox' is not in it" and had to guess what the schema DOES accept. Measured on the live product: three
mesh_contract violations survived six rounds, and the round that finally satisfied them did so by
deleting the call.

A generated product should never have to guess the API of the factory that generated it. This module
renders the catalogue as a short briefing the developer agent gets whenever the product touches the
mesh: the canonical invoke envelope, then every capability with its accepted and required fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The AI-market envelope. Getting this wrong is silent: the hub rejects the call on validation, so
# the product sees a refusal rather than an error, and the round sees nothing at all.
#
# Canonical path is Hub v2 — NOT the legacy ``/aimarket/invoke`` (404 on public ATLAS) and NOT
# ``X-Agent-Key`` (factory agent-registry auth; ATLAS does not bill against it).
INVOKE_ENVELOPE = (
    "POST {hub}/ai-market/v2/invoke  with body {\"capability_id\": \"<id>\", \"input\": {...}}\n"
    "  - hub default: https://modelmarket.dev  (env AIMARKET_HUB_URL); ATLAS origin is for sensors, not billing\n"
    "  - the ONLY two top-level fields the protocol accepts: capability_id and input\n"
    "  - not 'capability', not 'payload', not 'params' — anything else fails validation\n"
    "  - the response carries a receipt digest; keep it, it is the product's evidence trail\n"
    "  - NEVER POST /aimarket/invoke (legacy; public mesh returns 404)"
)

# How a generated product becomes a paying demand-side participant in this ecosystem.
# Measured gap: products shipped hand-rolled AtlasClient + demo-atlas-key + localhost:8001 and
# never opened a payment channel, so they were not economy participants — only broken HTTP clients.
PARTICIPANT_CONTRACT = (
    "=== AI-MARKET NATIVE PARTICIPANT (required when this product invokes mesh capabilities) ===\n"
    "Factory products that call ATLAS / Hub SKUs MUST be demand-side AI-market agents, not demo stubs.\n"
    "\n"
    "Preferred implementation (highest level):\n"
    "  Use the factory runtime module `aimarket_participant.AimarketParticipant` / `get_participant()`\n"
    "  (vendored next to atlas_client) OR pip `aimarket-agent`. Lifecycle at RUNTIME:\n"
    "    trial visitor headers by default;\n"
    "    when AIMARKET_WALLET_KEY (and/or AIMARKET_PAYMENT_CHANNEL) is set → paid channel session;\n"
    "    invoke via POST {hub}/ai-market/v2/invoke; optional channel/close on shutdown.\n"
    "  Do NOT invent a one-off X-Agent-Key client.\n"
    "\n"
    "1. Endpoint\n"
    "   - Prefer Hub: AIMARKET_HUB_URL (default https://modelmarket.dev) + /ai-market/v2/invoke\n"
    "   - Direct ATLAS is trial-only when payment is enforced; 402 → open channel at the hub.\n"
    "   - Do not hardcode http://localhost:8001; read AIMARKET_HUB_URL / ATLAS_BASE_URL.\n"
    "\n"
    "2. Auth that actually pays\n"
    "   - Free trial: X-AIMarket-Sandbox-Visitor (AIMARKET_SANDBOX_VISITOR).\n"
    "   - Paid: runtime channel (open → invoke → close) or injected AIMARKET_PAYMENT_CHANNEL +\n"
    "     AIMARKET_PAYMENT_CHANNEL_SECRET, sent as the headers X-Payment-Channel and\n"
    "     X-Payment-Channel-Secret — the hub refuses a paid invoke with exactly\n"
    "     'X-Payment-Channel required for paid capability invoke'. Naming only the env vars\n"
    "     left the trial header spelled out and the paid one not, so a product that read this\n"
    "     brief could construct the free call and not the one that pays.\n"
    "     Wallet private key stays on the server, never in the widget.\n"
    "   - Escrow MIN_DEPOSIT on Base is $1 USDC — budgets below that cannot open an escrow channel.\n"
    "   - X-Agent-Key / demo-atlas-key is NOT payment.\n"
    "\n"
    "3. Config surface\n"
    "   AIMARKET_HUB_URL, AIMARKET_SANDBOX_VISITOR, optional AIMARKET_WALLET_KEY /\n"
    "   AIMARKET_PAYMENT_CHANNEL (+ secret). Soft daily ceilings are product policy, not billing."
)


# Live first, and this is the whole point of the redesign: the monorepo inside the image is a
# snapshot taken when the image was built, and a container cannot update it. The hub's federated
# manifest is the ecosystem describing itself right now — 76 capabilities across six hubs at the time
# of writing, against the 6 the bundled ATLAS file knows about. GitHub is the second source because
# it is the only thing a container CAN pull when the hub is unreachable; the bundled file is the last
# resort, and being last is correct: it is the only one that can be stale without anyone noticing.
LIVE_MANIFEST_URLS = (
    "https://modelmarket.dev/ai-market/v2/manifest",
    "https://atlas.modelmarket.dev/ai-market/v2/manifest",
)
GITHUB_CATALOGUE_URL = (
    "https://raw.githubusercontent.com/alexar76/atlas/main/atlas/products.py"
)
CACHE_TTL_SEC = 6 * 3600


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _cache_path() -> Path:
    try:
        from core.paths import resolve_data_root

        root = Path(resolve_data_root())
    except Exception:
        root = _repo_root() / "data"
    return root / "cache" / "ecosystem_capabilities.json"


def _read_cache() -> list[dict[str, Any]]:
    path = _cache_path()
    try:
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    caps = payload.get("capabilities")
    if not isinstance(caps, list):
        return []
    import time as _time

    if float(payload.get("fetched_at") or 0) + CACHE_TTL_SEC < _time.time():
        return []  # expired: worth another look at the live ecosystem
    return [c for c in caps if isinstance(c, dict)]


def _write_cache(caps: list[dict[str, Any]], *, source: str) -> None:
    import time as _time

    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"fetched_at": _time.time(), "source": source, "capabilities": caps},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _fetch_json(url: str, *, timeout: float = 15.0) -> Any:
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _live_capabilities() -> list[dict[str, Any]]:
    """Capabilities as the running ecosystem describes them, hub manifest first."""
    for url in LIVE_MANIFEST_URLS:
        payload = _fetch_json(url)
        if not isinstance(payload, dict):
            continue
        tools = payload.get("tools")
        if not isinstance(tools, list) or not tools:
            tools = payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else []
        caps = [
            t
            for t in tools
            if isinstance(t, dict) and t.get("capability_id") and t.get("input_schema")
        ]
        if caps:
            _write_cache(caps, source=url)
            return caps
    return []


def _github_capabilities() -> list[dict[str, Any]]:
    """The catalogue source on GitHub — the one thing a container can pull when the hub is down."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            urllib.request.Request(GITHUB_CATALOGUE_URL), timeout=15
        ) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception:
        return []
    caps = _parse_product_caps(text)
    if caps:
        _write_cache(caps, source=GITHUB_CATALOGUE_URL)
    return caps


def _parse_product_caps(text: str) -> list[dict[str, Any]]:
    """Pull PRODUCT_CAPS out of a products.py source, wherever it came from."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if not (isinstance(target, ast.Name) and target.id == "PRODUCT_CAPS"):
                continue
        elif isinstance(node, ast.Assign):
            if not any(isinstance(x, ast.Name) and x.id == "PRODUCT_CAPS" for x in node.targets):
                continue
        else:
            continue
        if node.value is None:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(value, list):
            out.extend(c for c in value if isinstance(c, dict) and c.get("capability_id"))
    return out


def capability_catalogue(*, allow_network: bool = True) -> list[dict[str, Any]]:
    """Every capability the ecosystem publishes, freshest source that answers.

    Order matters and is the correction this module needed: the bundled monorepo is a snapshot from
    image-build time and a container has no way to refresh it, so it is the LAST resort rather than
    the first. Cache in between, because a repair round runs every few minutes and the ecosystem does
    not change that fast.
    """
    cached = _read_cache()
    if cached:
        return cached
    if allow_network:
        live = _live_capabilities()
        if live:
            return live
        gh = _github_capabilities()
        if gh:
            return gh

    caps: list[dict[str, Any]] = []
    atlas_products = _repo_root() / "atlas" / "atlas" / "products.py"
    if not atlas_products.is_file():
        return caps
    try:
        import ast

        tree = ast.parse(atlas_products.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return caps

    for node in ast.walk(tree):
        # The catalogue is annotated — `PRODUCT_CAPS: list[dict[str, Any]] = [...]` — which is an
        # AnnAssign, not an Assign. Looking only for Assign found nothing and returned an empty
        # briefing, silently: exactly the kind of quiet zero this whole file exists to prevent.
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if not (isinstance(target, ast.Name) and target.id == "PRODUCT_CAPS"):
                continue
        elif isinstance(node, ast.Assign):
            if not any(isinstance(t, ast.Name) and t.id == "PRODUCT_CAPS" for t in node.targets):
                continue
        else:
            continue
        if node.value is None:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("capability_id"):
                    caps.append(item)
    return caps


def render_brief(*, capability_ids: list[str] | None = None, max_caps: int = 8) -> str:
    """A briefing for whoever is writing code against the mesh. Empty when nothing is known."""
    caps = capability_catalogue()
    if not caps:
        return ""
    wanted = set(capability_ids or [])
    if wanted:
        caps = [c for c in caps if str(c.get("capability_id")) in wanted] or caps

    lines = [
        "=== AI-MARKET / MESH CAPABILITIES (this factory's own ecosystem — authoritative) ===",
        INVOKE_ENVELOPE,
        "",
        PARTICIPANT_CONTRACT,
        "",
        "Capabilities and the input each one actually accepts:",
    ]
    for cap in caps[:max_caps]:
        cid = str(cap.get("capability_id"))
        schema = cap.get("input_schema") or {}
        props = sorted((schema.get("properties") or {}).keys())
        required = sorted(schema.get("required") or [])
        price = cap.get("price_per_call_usd")
        lines.append(f"- {cid}")
        if props:
            lines.append(f"    accepts: {', '.join(props)}")
        if required:
            lines.append(f"    REQUIRED: {', '.join(required)}")
        if price is not None:
            lines.append(f"    price per call: ${price}")
        desc = str(cap.get("description") or "").strip().replace("\n", " ")
        if desc:
            lines.append(f"    {desc[:220]}")
    lines.append("")
    lines.append(
        "Send only fields from the accepted list: the hub validates the input and refuses the call "
        "otherwise, which the product sees as a refusal rather than an error. A bbox is expressed as "
        "west/south/east/north, never as a single 'bbox' field."
    )
    return "\n".join(lines)


def brief_for_code(code_dir: Path) -> str:
    """The briefing narrowed to the capabilities a product actually mentions."""
    import re

    ids: set[str] = set()
    pattern = re.compile(r"\b([a-z][\w]*(?:\.[a-z][\w]*)+@v\d+)\b")
    try:
        for path in code_dir.rglob("*.py"):
            if any(p in ("node_modules", ".venv", ".aicom_sandbox") for p in path.parts):
                continue
            try:
                ids.update(pattern.findall(path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    except OSError:
        return ""
    if not ids:
        return ""
    return render_brief(capability_ids=sorted(ids))
