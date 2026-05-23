#!/usr/bin/env python3
"""Add MIT/Apache LICENSE, CONTRIBUTORS.md, SECURITY.md for split-repo products."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MIT = ROOT / "LICENSE"
APACHE = ROOT / "aimarket-hub" / "LICENSE"

REPOS: list[tuple[str, str, str]] = [
    # (relative path, display name, license: mit|apache)
    *[(f"plugins/{p}", p, "mit") for p in [
        "aimarket-safety", "aimarket-reputation", "aimarket-channels", "aimarket-tee",
        "aimarket-auction", "aimarket-personas", "aimarket-streaming", "aimarket-nft",
        "aimarket-mcp-packager", "aimarket-orchestrator", "aimarket-data-cap",
        "aimarket-promo", "aimarket-dataset", "aimarket-zk",
    ]],
    ("aimarket-hub/plugins/aimarket-provenance", "aimarket-provenance", "apache"),
    *[(f"desktop-integrations/{p}", p, "mit") for p in [
        "interview-prep-coach", "personal-finance-coach", "capability-composer",
        "cold-outreach-coach", "creator-algorithm-coach", "discovery-prospector",
        "freelance-contract-reviewer", "reputation-dashboard",
    ]],
    ("desktop-integrations/packages/aicom_desktop_core", "aicom_desktop_core", "mit"),
    ("desktop-integrations/packages/aicom_platform_init", "aicom_platform_init", "mit"),
    # Desktop monorepo root (entire satellite)
    ("desktop-integrations", "aimarket-desktop", "mit"),
    ("aimarket-sdks/dart", "aimarket_agent_dart", "mit"),
    ("aimarket-hub", "aimarket-hub", "apache"),
    ("aimarket-protocol", "aimarket-protocol", "mit"),
    ("aimarket-widget", "aimarket-widget", "mit"),
    ("apps/pulse-terminal", "pulse-terminal", "mit"),
    ("aimarket-sdks", "aimarket-sdks", "mit"),
    ("ai-service-mesh", "ai-service-mesh", "mit"),
    ("acex", "acex", "apache"),
    ("aimarket-agent", "aimarket-agent", "mit"),
]


def contributors(name: str) -> str:
    return f"""# Contributors — {name}

## Maintainers

- **AI Commons / AI-Factory** — primary maintainers ([security@aicom.io](mailto:security@aicom.io))

## Contributing

1. Fork the repository (when published as a standalone repo)
2. Open a PR with tests and documentation updates
3. Sign off commits (`Signed-off-by:`) for DCO traceability

## Recognition

Contributors are listed in git history. For release notes, see the monorepo tag or GitHub Releases page.
"""


def security(name: str, kind: str) -> str:
    scope = {
        "plugin": f"- `{name}` hub plugin routes and invoke hooks\n- Ed25519 signing and payment channel interactions",
        "desktop": f"- `{name}` Flutter desktop/web application\n- Local data storage and wallet key handling\n- `aimarket_agent` SDK integration",
        "package": f"- `{name}` shared library\n- API surface exported to desktop SKUs",
        "hub": "- AIMarket Hub core API, plugins loader, payment channels, federation",
        "widget": (
            f"- `{name}` embed script (`widget.js`), themes, and demo pages\n"
            "- DOM XSS safety, hub v2 API calls, payment channel / affiliate headers\n"
            "- Unsafe `data-hub-url` or fetch targets"
        ),
        "pulse-terminal": (
            f"- `{name}` ACEX dashboard (Vite/React)\n"
            "- WebSocket/SSE pricing feed, API proxy config\n"
            "- XSS via hub pricing payloads rendered in DOM"
        ),
        "sdks": (
            f"- `{name}` consumer SDKs (Dart, TypeScript, Rust)\n"
            "- Wallet key handling, hub HTTP client, TEE verification helpers"
        ),
        "desktop-monorepo": (
            f"- `{name}` Flutter desktop/web applications\n"
            "- Local SQLite, wallet keys, language pack JSON loading"
        ),
        "mesh": (
            f"- `{name}` AI Service Mesh control plane\n"
            "- Agent discovery, task routing, escrow, SSRF protection\n"
            "- MESH_API_TOKEN / MESH_ADMIN_TOKEN authentication"
        ),
        "acex": (
            f"- `{name}` Arbitrary Code Execution contracts and verification\n"
            "- EVM/Solana smart contracts, TEE attestations\n"
            "- Zero-trust execution verification"
        ),
    }.get(kind, f"- `{name}`")

    return f"""# Security Policy — {name}

## Reporting a Vulnerability

**Do not open a public issue for security bugs.**

Email: **security@aicom.io**

We acknowledge within 48 hours and share a fix timeline.

## Scope

{scope}

## Out of Scope

- Third-party dependencies (report upstream)
- Issues requiring physical access to user hardware
- Social engineering

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest main | yes |
| older tags | best effort |

## Disclosure

Coordinated disclosure preferred. We credit researchers in release notes when permitted.
"""


def kind_for(path: str) -> str:
    if path.startswith("plugins/") or "provenance" in path:
        return "plugin"
    if path.startswith("desktop-integrations/") and "/packages/" not in path:
        return "desktop"
    if path == "desktop-integrations":
        return "desktop-monorepo"
    if path == "aimarket-hub":
        return "hub"
    if path == "aimarket-widget":
        return "widget"
    if path == "apps/pulse-terminal":
        return "pulse-terminal"
    if path == "aimarket-sdks":
        return "sdks"
    if path == "ai-service-mesh":
        return "mesh"
    if path == "acex":
        return "acex"
    return "package"


def main() -> None:
    for rel, name, lic in REPOS:
        root = ROOT / rel
        if not root.is_dir():
            print(f"SKIP missing {rel}")
            continue
        lic_src = APACHE if lic == "apache" else MIT
        if not lic_src.is_file():
            print(f"SKIP missing license template: {lic_src}")
            continue
        lic_dst = root / "LICENSE"
        if lic_src.resolve() != lic_dst.resolve():
            shutil.copy2(lic_src, lic_dst)
        (root / "CONTRIBUTORS.md").write_text(contributors(name), encoding="utf-8")
        (root / "SECURITY.md").write_text(security(name, kind_for(rel)), encoding="utf-8")
        print(f"OK {rel}")


if __name__ == "__main__":
    main()
