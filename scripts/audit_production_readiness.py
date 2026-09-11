#!/usr/bin/env python3
"""Production readiness checklist for split repos."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from desktop_sku_manifest import MANIFEST, expected_pngs  # noqa: E402

CHECKS = [
    "LICENSE",
    "CONTRIBUTORS.md",
    "SECURITY.md",
    "README.md",
    "docs/value.md",
    "docs/user-guide.md",
    "docs/sdk-integration.md",
    "docs/user-cases.md",
]

DESKTOP = [
    "interview-prep-coach", "personal-finance-coach", "capability-composer",
    "cold-outreach-coach", "creator-algorithm-coach", "discovery-prospector",
    "freelance-contract-reviewer", "reputation-dashboard",
]

PLUGINS = [
    "aimarket-safety", "aimarket-reputation", "aimarket-channels", "aimarket-tee",
    "aimarket-auction", "aimarket-personas", "aimarket-streaming", "aimarket-nft",
    "aimarket-mcp-packager", "aimarket-orchestrator", "aimarket-data-cap",
    "aimarket-promo", "aimarket-dataset", "aimarket-zk",
]


def status(root: Path, files: list[str]) -> dict[str, bool]:
    return {f: (root / f).is_file() for f in files}


PACKAGES = [
    "aicom_desktop_core",
    "aicom_platform_init",
]

SDKS = ["aimarket-sdks/dart"]
INFRA = ["aimarket-hub", "aimarket-protocol", "aimarket-widget"]


def main() -> None:
    print("=== DESKTOP APPS ===")
    desktop_missing = 0
    screenshot_gaps = 0
    for slug in DESKTOP:
        root = ROOT / "desktop-integrations" / slug
        s = status(root, CHECKS[:4] + ["docs/localization.md"])
        missing = [k for k, v in s.items() if not v]
        shot_missing = []
        if slug in MANIFEST:
            shots = root / "assets" / "screenshots"
            for png in expected_pngs(slug):
                if not (shots / png).is_file():
                    shot_missing.append(png)
        if missing or shot_missing:
            desktop_missing += 1
        if shot_missing:
            screenshot_gaps += len(shot_missing)
        parts = []
        if missing:
            parts.append("MISSING " + ", ".join(missing))
        if shot_missing:
            parts.append("screenshots: " + ", ".join(shot_missing))
        print(f"{slug}: {'OK' if not parts else ' | '.join(parts)}")

    print("\n=== HUB PLUGINS ===")
    plugin_checks = ["LICENSE", "CONTRIBUTORS.md", "SECURITY.md", "README.md",
                     "docs/value.md", "docs/user-guide.md", "docs/sdk-integration.md", "docs/user-cases.md"]
    plugin_missing = 0
    for slug in PLUGINS + ["aimarket-provenance"]:
        root = ROOT / ("aimarket-hub/plugins/" + slug if slug == "aimarket-provenance" else "plugins/" + slug)
        s = status(root, plugin_checks)
        missing = [k for k, v in s.items() if not v]
        if missing:
            plugin_missing += 1
        print(f"{slug}: {'OK' if not missing else 'MISSING ' + ', '.join(missing)}")

    print("\n=== PACKAGES / SDK / INFRA ===")
    infra_missing = 0
    for slug in PACKAGES:
        root = ROOT / "desktop-integrations" / "packages" / slug
        s = status(root, CHECKS[:4])
        missing = [k for k, v in s.items() if not v]
        if missing:
            infra_missing += 1
        print(f"{slug}: {'OK' if not missing else 'MISSING ' + ', '.join(missing)}")
    for rel in SDKS + INFRA:
        root = ROOT / rel
        s = status(root, CHECKS[:4])
        missing = [k for k, v in s.items() if not v]
        if missing:
            infra_missing += 1
        print(f"{rel}: {'OK' if not missing else 'MISSING ' + ', '.join(missing)}")

    print(
        f"\nSUMMARY: desktop={desktop_missing} missing, screenshot_gaps={screenshot_gaps}, "
        f"plugins={plugin_missing} missing, infra={infra_missing} missing"
    )


if __name__ == "__main__":
    main()
