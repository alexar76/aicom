"""The AIMarket economy: capabilities a product advertises but never invokes, and mesh calls
with the wrong envelope or an unadvertised capability.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import MAX_FINDINGS


_CAPABILITY_ID_RE = re.compile(r"\b([a-z][\w]*(?:\.[a-z][\w]*)+@v\d+)\b")


def find_capabilities_never_invoked(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """A capability the product is built around, reachable from no request path.

    The failure this catches is not a bug — it is a round taking the cheapest route out of a hard
    finding. Watched live. The advisory endpoint called ``atlas.get_advisory(...)``, a method
    AtlasClient never declared, so every request 500'd. Two rounds later the endpoint looked like
    this::

        return construct_unknown_advisory("ATLAS sensor mesh integration pending", lat, lon)

    The AttributeError was gone, the 500 was gone, module health was happier — and the product no
    longer did the one thing it exists to do. Sentinel's whole premise is "it reasons by invoking the
    ATLAS sensor-mesh capabilities over the AI-market protocol"; a Sentinel that answers UNKNOWN
    without asking anything is a placeholder with a landing page.

    Deleting a call is always the cheapest way to satisfy a finding about that call, so something has
    to notice. This does: capability ids declared anywhere in the product must be reachable from a
    request handler, or the product is not the product.
    """
    capability_files: dict[str, list[str]] = {}   # module stem -> capability ids
    router_files: list[Path] = []
    all_py: list[tuple[Path, str, str]] = []      # (path, rel, text)

    for file in iter_product_files(code_dir, "*.py"):
        rel = file.relative_to(code_dir).as_posix()
        if any(part in ("tests", "test", "migrations", "alembic") for part in Path(rel).parts):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_py.append((file, rel, text))
        ids = sorted(set(_CAPABILITY_ID_RE.findall(text)))
        if ids:
            capability_files[file.stem] = ids
        if "APIRouter(" in text or "@app.get(" in text or "@app.post(" in text:
            router_files.append(file)

    if not capability_files:
        return []

    findings: list[dict[str, Any]] = []
    for stem, ids in sorted(capability_files.items()):
        # Which classes in that module hold the capabilities?
        holder_names: set[str] = set()
        for file, rel, text in all_py:
            if file.stem != stem:
                continue
            holder_names.update(re.findall(r"^class\s+(\w+)", text, re.M))
        if not holder_names:
            continue

        # Accessors defined in the holder module that hand the holder out: `get_participant()`,
        # `get_client()`, a cached factory. Wiring through one of these is the IDIOMATIC pattern
        # and it was not recognised — this check only ever looked for a direct constructor call
        # in a router file.
        #
        # That false negative is what kept Sentinel blocked. The developer wired the advisory
        # endpoint correctly with `participant = get_participant()` and three `.invoke(...)`
        # calls; the constructor had moved inside `get_participant`, so the detector still
        # reported "NO request handler constructs AimarketParticipant"; the critical finding
        # survived the round, so the round removed no defects while its own transient ones
        # (`api_route_shadows_spa`, `missing_symbol`) added; the salvage step therefore read the
        # round as a pure regression and gave the file back. Every correct fix was undone by a
        # detector that could not see it. Reproduced on a four-file synthetic tree before this
        # change: factory-wired product, one `capability_never_invoked`.
        accessor_names: set[str] = set()
        for file, rel, text in all_py:
            if file.stem != stem:
                continue
            for m in re.finditer(r"^(?:async\s+)?def\s+(\w+)\s*\(", text, re.M):
                fn = m.group(1)
                if fn.startswith("_"):
                    continue
                # Only functions that actually touch a holder class: a module can define
                # unrelated helpers, and treating those as wiring would make the check vacuous.
                body = text[m.end() :]
                nxt = re.search(r"^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+", body, re.M)
                body = body[: nxt.start()] if nxt else body
                if any(re.search(rf"\b{re.escape(name)}\b", body) for name in holder_names):
                    accessor_names.add(fn)

        entry_points = set(holder_names) | accessor_names
        reachable_from = ""
        for file, rel, text in all_py:
            if file in router_files or "APIRouter(" in text or "@app.get(" in text:
                if any(re.search(rf"\b{re.escape(name)}\s*\(", text) for name in entry_points):
                    reachable_from = rel
                    break
        # Wrapper clients (e.g. atlas_client.AtlasClient calling get_participant()) sit
        # between routers and the holder module. Sentinel's advisory router constructs
        # AtlasClient(), not AimarketParticipant directly — without this hop the holder
        # module still looks orphaned even though every request invokes it.
        if not reachable_from:
            wired_by: set[str] = set()
            for _file, rel, text in all_py:
                if any(re.search(rf"\b{re.escape(name)}\s*\(", text) for name in entry_points):
                    wired_by.add(rel)
            wrapper_classes: set[str] = set()
            for _file, rel, text in all_py:
                if rel not in wired_by:
                    continue
                wrapper_classes.update(re.findall(r"^class\s+(\w+)", text, re.M))
            if wrapper_classes:
                for file, rel, text in all_py:
                    if file in router_files or "APIRouter(" in text or "@app.get(" in text:
                        if any(
                            re.search(rf"\b{re.escape(name)}\s*\(", text)
                            for name in wrapper_classes
                        ):
                            reachable_from = rel
                            break
        if reachable_from:
            continue

        holder_rel = next((r for _f, r, _t in all_py if _f.stem == stem), stem)
        findings.append(
            {
                "code": "capability_never_invoked",
                "severity": "critical",
                "file": holder_rel,
                "capabilities": ids[:6],
                "detail": (
                    f"{holder_rel} declares the capabilities this product is built around "
                    f"({', '.join(ids[:4])}) and NO request handler constructs "
                    f"{' or '.join(sorted(holder_names)[:3])} — so nothing the product serves ever "
                    "invokes them. Deleting a call is the cheapest way to satisfy a finding about "
                    "that call, and that is what happened here: the advisory endpoint went from "
                    "crashing on a missing client method to returning a static placeholder, which "
                    "silenced the crash and removed the product's entire reason to exist. Restore "
                    "the invocation from the endpoint that needs it and fix the method name instead "
                    "— the client's real methods are the ones defined in "
                    f"{holder_rel}."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


# The product calls OUR OWN economy with the wrong envelope, and nothing sees it. Every gate is
# green: the tree imports, the app boots, the endpoint answers 200 — with
# ``{"level": "UNKNOWN", "reason": "Insufficient sensor data"}`` on every request, because the
# mesh rejected each call on validation. The product's honesty policy (never CALM without data)
# turns a contract bug into a truthful-looking answer, which is the worst place to hide one.
#
# Found on a weather product whose entire purpose is mesh data:
#
#     data = {"capability": capability, "payload": payload}      # protocol wants capability_id/input
#     payload = {"bbox": [w, s, e, n]}                           # schema wants flat west/south/east/north
#     payload = {"max_radius_km": 100}                           # schema calls it max_km
#
# The manifest is the ground truth and it is fetched live, so this checks against what the mesh
# actually accepts today rather than a copy that drifts. Network failure means no opinion: an
# unreachable manifest must never fail a product's build.
_AIMARKET_ENVELOPE_REQUIRED = ("capability_id", "input")
_AIMARKET_ENVELOPE_WRONG = {
    "capability": "capability_id",
    "payload": "input",
    "cap": "capability_id",
    "params": "input",
    "arguments": "input",
    "body": "input",
}
# SKU lists that advertise what an agent uses, not the input of an invoke.
# Measured: Sentinel heartbeat.py posted a registry payload with
# capabilities_used=["atlas.situation.brief@v1", ...] and mesh_contract scored
# agent_id/sdk against the ATLAS input schema — three false findings that
# occupied the repair-scope Python slot while atlas_client.py was already correct.
_ADVERTISED_CAPABILITY_KEYS = (
    "capabilities_used",
    "advertised_capabilities",
    "capability_ids",
)


def _capability_id_is_advertised(src: str, match_start: int) -> bool:
    """True when the SKU sits in a declared-capabilities list, not an invoke call."""
    before = src[:match_start]
    open_br = before.rfind("[")
    if open_br < 0:
        return False
    if before.rfind("]") > open_br:
        return False
    head = before[max(0, open_br - 120) : open_br]
    return any(k in head for k in _ADVERTISED_CAPABILITY_KEYS)


def _fetch_manifest_schemas(base_urls: set[str]) -> dict[str, dict[str, Any]]:
    """``{capability_id: input_schema}`` from every mesh endpoint the product talks to."""
    import json as _json
    import urllib.error
    import urllib.request

    out: dict[str, dict[str, Any]] = {}
    for base in sorted(base_urls):
        for suffix in ("/ai-market/v2/manifest", "/.well-known/ai-market.json"):
            try:
                with urllib.request.urlopen(base.rstrip("/") + suffix, timeout=8) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                continue
            tools = data.get("tools") or data.get("capabilities") or []
            if not isinstance(tools, list):
                continue
            for tool in tools:
                if isinstance(tool, dict) and tool.get("capability_id"):
                    out[str(tool["capability_id"])] = tool.get("input_schema") or {}
            if out:
                break
    return out


def find_mesh_contract_violations(
    code_dir: Path, limit: int = MAX_FINDINGS
) -> list[dict[str, Any]]:
    """Outbound AI-market calls whose envelope or input does not match the live manifest."""
    findings: list[dict[str, Any]] = []
    bases: set[str] = set()
    files: list[tuple[Path, str, ast.AST]] = []

    for path in iter_product_files(code_dir, "*.py"):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # A capability id is the actual signal. Requiring the words "ai-market" or
        # "capability" skipped a client that referenced SKUs and neither word — it worked on
        # the product that exposed this only by luck.
        if not re.search(r"[a-z0-9_]+\.[a-z0-9_.]+@v\d", src) and "ai-market" not in src:
            continue
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        files.append((path, src, tree))
        for m in re.finditer(r"https://[a-z0-9.\-]+\.modelmarket\.dev", src):
            bases.add(m.group(0))

    if not files:
        return findings

    # 1. Envelope keys — checkable without the network, so it is done first and always.
    for path, src, tree in files:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value
                for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            wrong = {k: _AIMARKET_ENVELOPE_WRONG[k] for k in keys & set(_AIMARKET_ENVELOPE_WRONG)}
            # Only an envelope: it carries a capability-ish key and an argument-ish key, and
            # lacks the correct names. A dict that merely has "payload" in it is not one.
            if not wrong or "capability_id" in keys:
                continue
            if not ({"capability", "cap"} & keys):
                continue
            findings.append(
                {
                    "file": str(path.relative_to(code_dir)),
                    "line": node.lineno,
                    "kind": "envelope",
                    "detail": (
                        "AI-market invoke envelope uses "
                        + ", ".join(f"'{bad}' (should be '{good}')" for bad, good in sorted(wrong.items()))
                        + ". The protocol accepts only {capability_id, input}; anything else is "
                        "rejected on validation, so every call fails while the app still answers "
                        "200 with an empty result. Verify against "
                        "https://atlas.modelmarket.dev/ai-market/v2/manifest."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings

    # 2. Input shape against the live schema. No manifest reachable -> no opinion.
    schemas = _fetch_manifest_schemas(bases or {"https://atlas.modelmarket.dev"})
    if not schemas:
        return findings

    reported: set[tuple[str, str]] = set()
    for path, src, tree in files:
        for cap_match in re.finditer(r"""["']([a-z][a-z0-9_.]*\.[a-z0-9_.]+@v\d+)["']""", src):
            cap = cap_match.group(1)
            if _capability_id_is_advertised(src, cap_match.start()):
                continue
            schema = schemas.get(cap)
            if not schema:
                continue
            required = [r for r in (schema.get("required") or []) if isinstance(r, str)]
            props = set((schema.get("properties") or {}).keys())
            if not required and not props:
                continue
            line = src[: cap_match.start()].count("\n") + 1
            if (path.name, cap) in reported:
                # One finding per capability per file. The first version scanned a fixed window
                # backwards and re-reported each capability from an unrelated cost table further
                # down: six findings for three defects, which teaches people to skim the list.
                continue
            # Only the enclosing function. A window that crosses a `def` picks up someone
            # else's dict and invents fields the call never sent.
            # Top-level `async def` must be in this list. Relay's advisory handler is
            # `async def advisory` at module scope; the previous route returns
            # `{"items": serialize_audit(...)}`. Without `\nasync def `, the window
            # started at that earlier `def` and QA reported extra field `items` on
            # `atlas.situation.brief@v1` for four plateau rounds while the invoke
            # itself sent only the bbox.
            head = src[: cap_match.start()]
            fn_start = max(
                head.rfind("\n    def "),
                head.rfind("\ndef "),
                head.rfind("\n    async def "),
                head.rfind("\nasync def "),
            )
            window = head[fn_start:] if fn_start != -1 else head[-900:]
            sent = set(re.findall(r"""["']([a-z_][a-z0-9_]*)["']\s*:""", window))
            if not sent:
                continue
            missing = [r for r in required if r not in sent]
            unknown = sorted(k for k in sent - props if k not in ("visitor_id", "capability_id", "input"))
            if not missing and not unknown:
                continue
            parts = []
            if missing:
                parts.append(f"required field(s) not sent: {', '.join(missing)}")
            if unknown:
                near = {
                    k: next((p for p in sorted(props) if p in k or k in p), None) for k in unknown
                }
                described = ", ".join(
                    f"'{k}'" + (f" (did you mean '{v}'?)" if v else "") for k, v in near.items()
                )
                parts.append(f"field(s) the schema does not have: {described}")
            reported.add((path.name, cap))
            findings.append(
                {
                    "file": str(path.relative_to(code_dir)),
                    "line": line,
                    "kind": "input_schema",
                    "capability": cap,
                    "detail": (
                        f"Input for {cap} does not match its published schema — "
                        + "; ".join(parts)
                        + f". The schema accepts: {', '.join(sorted(props))}. A rejected call "
                        "still leaves the endpoint answering 200 with no data, so this hides as "
                        "an honest 'no readings' rather than surfacing as an error."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


def find_mesh_participant_violations(
    code_dir: Path, limit: int = MAX_FINDINGS
) -> list[dict[str, Any]]:
    """Mesh clients that are not AI-market participants (legacy path / no pay-or-trial headers).

    Envelope shape is checked by ``find_mesh_contract_violations``. This gate catches the
    other half of what made Sentinel fail as an economy agent: ``/aimarket/invoke`` and
    ``X-Agent-Key`` alone with no visitor trial and no payment channel.
    """
    findings: list[dict[str, Any]] = []
    pay_markers = (
        "X-Payment-Channel",
        "AIMARKET_PAYMENT_CHANNEL",
        "X-AIMarket-Sandbox-Visitor",
        "AIMARKET_SANDBOX_VISITOR",
        "X_AIMARKET_SANDBOX_VISITOR",
        "openChannel",
        "channel/open",
        "aimarket-agent",
        "@aimarket/agent",
        "_mesh_headers",
    )

    for path in iter_product_files(code_dir, "*.py"):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if (
            not re.search(r"[a-z0-9_]+\.[a-z0-9_.]+@v\d", src)
            and "ai-market" not in src
            and "aimarket" not in src
        ):
            continue
        rel = str(path.relative_to(code_dir))
        if "/aimarket/invoke" in src and "/ai-market/v2/invoke" not in src:
            findings.append(
                {
                    "file": rel,
                    "line": src[: src.index("/aimarket/invoke")].count("\n") + 1,
                    "kind": "legacy_invoke_path",
                    "detail": (
                        f"{rel} POSTs /aimarket/invoke — public Hub/ATLAS serve "
                        "/ai-market/v2/invoke (legacy path 404s). Use AIMARKET_HUB_URL "
                        "(https://modelmarket.dev) + /ai-market/v2/invoke."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
        invokes = (
            "/ai-market/v2/invoke" in src
            or "/aimarket/invoke" in src
            or (
                "capability_id" in src
                and ("httpx" in src or "requests." in src or "aiohttp" in src)
            )
        )
        if not invokes:
            continue
        if any(m in src for m in pay_markers):
            continue
        if "capabilities_used" in src and "invoke" not in src.lower():
            continue
        line = 1
        for needle in ("/ai-market/v2/invoke", "/aimarket/invoke", "capability_id"):
            if needle in src:
                line = src[: src.index(needle)].count("\n") + 1
                break
        findings.append(
            {
                "file": rel,
                "line": line,
                "kind": "missing_participant_headers",
                "detail": (
                    f"{rel} invokes the mesh without X-AIMarket-Sandbox-Visitor (trial) or "
                    "X-Payment-Channel (paid). X-Agent-Key / demo-atlas-key is not billing. "
                    "Wire AIMARKET_SANDBOX_VISITOR and/or AIMARKET_PAYMENT_CHANNEL on every "
                    "invoke (or use aimarket-agent / @aimarket/agent)."
                ),
            }
        )
        if len(findings) >= limit:
            return findings
    return findings
