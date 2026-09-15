#!/usr/bin/env python3
"""Audit desktop reference SKUs under desktop-integrations/ (and optional coach/)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Recommended review order (flagship → marketplace tools → stubs)
AUDIT_ORDER: list[str] = [
    "interview-prep-coach",
    "personal-finance-coach",
    "capability-composer",
    "cold-outreach-coach",
    "creator-algorithm-coach",
    "discovery-prospector",
    "freelance-contract-reviewer",
    "reputation-dashboard",
    "local-security-audit",
    "ai-stack-migration-assistant",
]

LAUNCH_HINTS: dict[str, str] = {
    "interview-prep-coach": "cd desktop-integrations/interview-prep-coach && flutter pub get && flutter run -d linux",
    "personal-finance-coach": "cd desktop-integrations/personal-finance-coach && flutter pub get && flutter run -d linux",
    "capability-composer": "cd desktop-integrations/capability-composer && flutter pub get && flutter run -d linux",
    "cold-outreach-coach": "cd desktop-integrations/cold-outreach-coach && flutter pub get && flutter run -d linux",
    "creator-algorithm-coach": "cd desktop-integrations/creator-algorithm-coach && flutter pub get && flutter run -d linux",
    "discovery-prospector": "cd desktop-integrations/discovery-prospector && flutter pub get && flutter run -d linux",
    "freelance-contract-reviewer": "cd desktop-integrations/freelance-contract-reviewer && flutter pub get && flutter run -d linux",
    "reputation-dashboard": "cd desktop-integrations/reputation-dashboard && flutter pub get && flutter run -d linux",
    "local-security-audit": "cd desktop-integrations/local-security-audit && cargo tauri dev  # needs src-tauri/Cargo.toml fix",
    "ai-stack-migration-assistant": "cd desktop-integrations/ai-stack-migration-assistant && npm ci && npm run build && code --extensionDevelopmentPath=.",
}


def _detect_kind(root: Path) -> str:
    from web.backend.services.desktop_product import detect_desktop_framework

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            text = pkg.read_text(encoding="utf-8", errors="ignore")
            pkg_data = json.loads(text)
            if isinstance(pkg_data.get("engines"), dict) and "vscode" in pkg_data["engines"]:
                return "vscode_extension"
        except (OSError, json.JSONDecodeError):
            pass
    fw = detect_desktop_framework(root)
    if fw:
        return fw
    if (root / "src-tauri").is_dir() or (root / "Cargo.toml").is_file():
        return "tauri_incomplete"
    return "unknown"


def _audit_one(name: str, *, base: Path) -> dict:
    from web.backend.services.desktop_product import desktop_storefront_ready

    root = base / name
    kind = _detect_kind(root) if root.is_dir() else "missing"
    ok, blockers = desktop_storefront_ready(f"desktop-{name}", code_root=root) if root.is_dir() else (False, ["missing_dir"])
    pubspec = (root / "pubspec.yaml").is_file()
    tests = list((root / "test").glob("*.dart")) if (root / "test").is_dir() else []
    screenshots = list((root / "assets" / "screenshots").glob("*")) if (root / "assets" / "screenshots").is_dir() else []
    return {
        "slug": name,
        "path": str(root.relative_to(ROOT)),
        "kind": kind,
        "storefront_ready": ok,
        "blockers": blockers,
        "has_pubspec": pubspec,
        "test_files": len(tests),
        "screenshots": len(screenshots),
        "launch": LAUNCH_HINTS.get(name, ""),
    }


def _write_manifest(root: Path) -> int:
    files: list[dict[str, str]] = []
    skip = {".dart_tool", "build", ".git", "node_modules", "target", ".idea"}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in skip for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith("."):
            continue
        files.append({"path": rel})
    manifest = {"files": files[:500]}
    (root / "code_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit desktop-integrations reference SKUs")
    parser.add_argument("--index", type=int, default=0, help="1-based index in AUDIT_ORDER (0 = summary all)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-manifests", action="store_true", help="Generate code_manifest.json for each app")
    parser.add_argument("--include-coach", action="store_true", help="Also audit coach/ submodule")
    args = parser.parse_args()

    base = ROOT / "desktop-integrations"
    order = list(AUDIT_ORDER)
    if args.include_coach and (ROOT / "coach" / "pubspec.yaml").is_file():
        order.append("coach (submodule → coach/)")

    if args.write_manifests:
        for name in AUDIT_ORDER:
            root = base / name
            if root.is_dir():
                n = _write_manifest(root)
                print(f"manifest {name}: {n} files")

    rows = []
    for name in AUDIT_ORDER:
        if not (base / name).is_dir():
            continue
        rows.append(_audit_one(name, base=base))

    if args.include_coach:
        coach_root = ROOT / "coach"
        if coach_root.is_dir():
            from web.backend.services.desktop_product import desktop_storefront_ready

            ok, blockers = desktop_storefront_ready("coach", code_root=coach_root)
            rows.append(
                {
                    "slug": "coach",
                    "path": "coach",
                    "kind": "flutter",
                    "storefront_ready": ok,
                    "blockers": blockers,
                    "has_pubspec": True,
                    "test_files": len(list((coach_root / "test").glob("*.dart"))) if (coach_root / "test").is_dir() else 0,
                    "screenshots": 0,
                    "launch": "cd coach && flutter pub get && flutter run -d linux",
                }
            )

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if args.index <= 0:
        print(f"Desktop audit queue ({len(rows)} apps)\n")
        for i, row in enumerate(rows, start=1):
            flag = "OK" if row["storefront_ready"] else "BLOCKED"
            print(f"  {i:2}. [{flag}] {row['slug']} ({row['kind']}) — {', '.join(row['blockers'][:2])}")
        print("\nNext: python3 scripts/audit_desktop_integrations.py --index 1")
        return 0

    idx = args.index - 1
    if idx < 0 or idx >= len(rows):
        print(f"Index out of range (1..{len(rows)})", file=sys.stderr)
        return 1

    row = rows[idx]
    print(f"=== #{args.index} {row['slug']} ===")
    print(f"path:      {row['path']}")
    print(f"kind:      {row['kind']}")
    print(f"ready:     {row['storefront_ready']}")
    print(f"blockers:  {', '.join(row['blockers']) or '—'}")
    print(f"tests:     {row['test_files']} dart test file(s)")
    print(f"shots:     {row['screenshots']} in assets/screenshots")
    print(f"\nLaunch:\n  {row['launch']}")
    print("\nReview checklist:")
    print("  • App boots without crash; navigation works")
    print("  • Hub / aimarket_agent wiring (search, channel, invoke)")
    print("  • Privacy copy matches behavior (on-device vs network)")
    print("  • README build steps match your OS")
    print("  • Storefront: download story + desktop capability makes sense")
    if idx + 1 < len(rows):
        print(f"\nAfter review → python3 scripts/audit_desktop_integrations.py --index {args.index + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
