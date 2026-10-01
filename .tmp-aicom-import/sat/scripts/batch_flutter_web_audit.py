#!/usr/bin/env python3
"""Prepare, build web, and smoke-test all desktop-integrations Flutter apps."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = ROOT / "desktop-integrations"
FLUTTER = Path("/root/flutter/bin/flutter")
PLATFORM_PKG = "aicom_platform_init:\n    path: ../packages/aicom_platform_init"

APPS = [
    "interview-prep-coach",
    "personal-finance-coach",
    "capability-composer",
    "cold-outreach-coach",
    "creator-algorithm-coach",
    "discovery-prospector",
    "freelance-contract-reviewer",
    "reputation-dashboard",
]


def run(cmd: list[str], *, cwd: Path, timeout: int = 600) -> tuple[int, str]:
    env = {**dict(**__import__("os").environ), "PATH": f"/root/flutter/bin:{__import__('os').environ.get('PATH', '')}"}
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def ensure_web(app_dir: Path) -> None:
    if not (app_dir / "web").is_dir():
        run([str(FLUTTER), "create", ".", "--platforms=web"], cwd=app_dir)


def patch_pubspec(app_dir: Path) -> list[str]:
    fixes: list[str] = []
    pub = app_dir / "pubspec.yaml"
    text = pub.read_text(encoding="utf-8")
    orig = text

    if "github.com/alexar76/aimarket-sdks" in text:
        text = re.sub(
            r"aimarket_agent:\s*\n\s*git:.*?(?=\n\S|\n\n|\Z)",
            "aimarket_agent:\n    path: ../../aimarket-sdks/dart",
            text,
            flags=re.S,
        )
        fixes.append("aimarket path")

    if "aicom_platform_init" not in text and "sqflite" in text:
        if "dependencies:" in text:
            text = text.replace(
                "dependencies:\n",
                "dependencies:\n  aicom_platform_init:\n    path: ../packages/aicom_platform_init\n",
                1,
            )
            fixes.append("platform_init dep")

    if "intl: ^0.19.0" in text:
        text = text.replace("intl: ^0.19.0", "intl: ^0.20.2")
        fixes.append("intl bump")

    branding = app_dir / "assets" / "branding"
    if "- assets/branding/" in text and not branding.is_dir():
        text = text.replace("  assets:\n    - assets/branding/\n", "")
        fixes.append("drop missing branding asset")

    fonts_block = re.search(r"\n  fonts:.*?(?=\n\S|\Z)", text, re.S)
    if fonts_block and "assets/fonts/" in fonts_block.group(0):
        fonts_dir = app_dir / "assets" / "fonts"
        if not fonts_dir.is_dir() or not any(fonts_dir.glob("*.ttf")):
            text = text[: fonts_block.start()] + text[fonts_block.end() :]
            fixes.append("drop missing fonts")

    if text != orig:
        pub.write_text(text, encoding="utf-8")
    return fixes


def patch_main(app_dir: Path) -> list[str]:
    main = app_dir / "lib" / "main.dart"
    if not main.is_file():
        return []
    text = main.read_text(encoding="utf-8")
    if "dart:io" not in text and "Platform.is" not in text:
        return []
    if "aicom_platform_init" in text:
        return []

    lines = text.splitlines()
    out: list[str] = []
    skip_io = False
    for line in lines:
        if line.strip() == "import 'dart:io';":
            skip_io = True
            continue
        if skip_io and line.startswith("import ") and "sqflite" not in line:
            skip_io = False
        if skip_io and not line.startswith("import "):
            skip_io = False
        if "sqflite_common_ffi" in line or "sqfliteFfiInit" in line:
            continue
        if re.match(r"\s*if \(Platform\.", line):
            continue
        if "databaseFactory = databaseFactoryFfi" in line:
            continue
        out.append(line)

    header = [
        "import 'package:flutter/foundation.dart' show kIsWeb;",
        "import 'package:aicom_platform_init/aicom_platform_init.dart';",
    ]
    merged: list[str] = []
    inserted = False
    for line in out:
        merged.append(line)
        if not inserted and line.strip() == "WidgetsFlutterBinding.ensureInitialized();":
            merged.append("  if (!kIsWeb) {")
            merged.append("    initDatabaseFactory();")
            merged.append("  }")
            inserted = True
    if not inserted:
        idx = next((i for i, l in enumerate(merged) if l.strip().startswith("void main")), 0)
        merged.insert(idx + 1, "  WidgetsFlutterBinding.ensureInitialized();")
        merged.insert(idx + 2, "  if (!kIsWeb) {")
        merged.insert(idx + 3, "    initDatabaseFactory();")
        merged.insert(idx + 4, "  }")

    # dedupe imports at top
    body = "\n".join(merged)
    if "package:flutter/foundation.dart" not in body:
        body = header[0] + "\n" + body
    if "aicom_platform_init" not in body:
        body = header[1] + "\n" + body

    main.write_text(body + "\n", encoding="utf-8")
    return ["main.dart web bootstrap"]


def audit_app(slug: str) -> dict:
    app_dir = APPS_DIR / slug
    result: dict = {"slug": slug, "fixes": [], "build_ok": False, "error": ""}
    if not (app_dir / "pubspec.yaml").is_file():
        result["error"] = "no pubspec"
        return result

    ensure_web(app_dir)
    result["fixes"].extend(patch_pubspec(app_dir))
    result["fixes"].extend(patch_main(app_dir))

    code, out = run([str(FLUTTER), "pub", "get"], cwd=app_dir)
    if code != 0:
        result["error"] = out[-2000:]
        return result

    code, out = run(
        [str(FLUTTER), "build", "web", "--release"],
        cwd=app_dir,
        timeout=900,
    )
    result["build_ok"] = code == 0
    if not result["build_ok"]:
        result["error"] = out[-2500:]
    return result


def main() -> int:
    rows = [audit_app(slug) for slug in APPS]
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    ok = sum(1 for r in rows if r["build_ok"])
    print(f"\nSUMMARY: {ok}/{len(rows)} web builds OK")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
