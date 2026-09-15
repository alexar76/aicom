"""Desktop app products (Tauri / Flutter) — readiness, framework detection, storefront gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from core.delivery_profile import DESKTOP_APP, normalize_delivery_profile


def resolve_product_delivery_profile(
    product: dict[str, Any] | None,
    specification: dict[str, Any] | None = None,
) -> str:
    spec = specification if isinstance(specification, dict) else {}
    prod = product if isinstance(product, dict) else {}
    for src in (spec, prod, prod.get("metadata") if isinstance(prod.get("metadata"), dict) else {}):
        if isinstance(src, dict) and src.get("delivery_profile"):
            return normalize_delivery_profile(str(src.get("delivery_profile")))
    return normalize_delivery_profile(None)


def is_desktop_product(
    product: dict[str, Any] | None = None,
    *,
    specification: dict[str, Any] | None = None,
    delivery_profile: str | None = None,
) -> bool:
    if delivery_profile:
        return normalize_delivery_profile(delivery_profile) == DESKTOP_APP
    if resolve_product_delivery_profile(product, specification) == DESKTOP_APP:
        return True
    if isinstance(product, dict) and str(product.get("category") or "").lower() == "desktop":
        return True
    return False


def detect_desktop_framework(code_root: Path) -> str | None:
    """Return ``tauri``, ``flutter``, or None."""
    root = Path(code_root)
    if not root.is_dir():
        return None
    if (root / "src-tauri" / "Cargo.toml").is_file() or (root / "src-tauri" / "tauri.conf.json").is_file():
        return "tauri"
    if (root / "pubspec.yaml").is_file() and (root / "lib" / "main.dart").is_file():
        return "flutter"
    # Electron stub (package.json + electron main)
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
            if "electron" in deps or "electron-builder" in deps:
                return "electron"
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return None


def _readme_present(code_root: Path) -> bool:
    for name in ("README.md", "readme.md", "BUILD.md", "build.md"):
        p = code_root / name
        if p.is_file() and p.stat().st_size > 80:
            return True
    return False


def desktop_storefront_ready(
    product_id: str,
    *,
    code_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """Desktop products list when scaffold + build docs exist (no browser sandbox required)."""
    from core.paths import code_dir

    root = Path(code_root) if code_root else code_dir(product_id)
    reasons: list[str] = []
    if not root.is_dir():
        return False, ["no_code_dir"]

    framework = detect_desktop_framework(root)
    if not framework:
        return False, ["desktop_framework_not_detected"]

    if framework == "tauri":
        if not (root / "src-tauri" / "Cargo.toml").is_file():
            reasons.append("missing_src_tauri_cargo")
        ui = root / "ui" / "index.html"
        src_ui = root / "src" / "index.html"
        if not ui.is_file() and not src_ui.is_file():
            reasons.append("missing_desktop_ui_html")
    elif framework == "flutter":
        if not (root / "lib" / "main.dart").is_file():
            reasons.append("missing_flutter_main")
    elif framework == "electron":
        if not (root / "package.json").is_file():
            reasons.append("missing_electron_package_json")

    if not _readme_present(root):
        reasons.append("missing_build_readme")

    manifest = root / "code_manifest.json"
    if not manifest.is_file():
        reasons.append("missing_code_manifest")
    else:
        try:
            files = json.loads(manifest.read_text(encoding="utf-8")).get("files") or []
            if not files:
                reasons.append("empty_code_manifest")
        except (OSError, json.JSONDecodeError):
            reasons.append("invalid_code_manifest")

    if reasons:
        return False, reasons
    return True, []


def desktop_stack_label(code_root: Path | None) -> str | None:
    if not code_root:
        return None
    fw = detect_desktop_framework(Path(code_root))
    if fw == "tauri":
        return "Tauri desktop"
    if fw == "flutter":
        return "Flutter desktop"
    if fw == "electron":
        return "Electron desktop"
    return None


def desktop_product_kind_meta(product: dict[str, Any] | None, code_root: Path | None = None) -> dict[str, Any]:
    """Storefront / hub metadata for desktop SKUs."""
    fw = detect_desktop_framework(Path(code_root)) if code_root and code_root.is_dir() else None
    return {
        "product_kind": "desktop_app",
        "desktop_framework": fw,
        "platforms": ["macOS", "Windows", "Linux"],
        "delivery_profile": DESKTOP_APP,
    }


def assess_desktop_product_demo(
    product_id: str,
    *,
    spec: dict[str, Any] | None = None,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """QA/demo report for desktop_app delivery profile (no browser sandbox required)."""
    from core.paths import resolve_data_root

    root = resolve_data_root(data_root) / "code" / product_id
    issues: list[dict[str, str]] = []
    ok, gate_reasons = desktop_storefront_ready(product_id, code_root=root)
    framework = detect_desktop_framework(root) if root.is_dir() else None

    if not root.is_dir():
        return {
            "score": 0,
            "grade": "F",
            "sandbox_ready": False,
            "desktop_ready": False,
            "has_index_html": False,
            "has_code_dir": False,
            "issues": [{"code": "no_code_dir", "detail": "No generated code directory"}],
            "spec_coverage_pct": None,
            "desktop_framework": framework,
        }

    score = 72
    if framework:
        score += 12
    if _readme_present(root):
        score += 8
    if ok:
        score += 8
    else:
        for r in gate_reasons[:6]:
            issues.append({"code": "desktop_gate", "detail": r})

    if not framework:
        issues.append({"code": "desktop_framework_missing", "detail": "No Tauri, Flutter, or Electron scaffold detected"})

    score = max(0, min(100, score))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "F"
    return {
        "score": score,
        "grade": grade,
        "sandbox_ready": False,
        "desktop_ready": ok,
        "has_index_html": bool(framework == "tauri" and any(root.rglob("*.html"))),
        "has_code_dir": True,
        "issues": issues,
        "spec_coverage_pct": None,
        "desktop_framework": framework,
        "product_kind": "desktop_app",
    }


def infer_category_for_new_product(idea: str, admin_instructions: str = "", delivery_profile: str | None = None) -> str:
    from marketplace_taxonomy import infer_marketplace_category_from_signals

    if is_desktop_product(delivery_profile=delivery_profile):
        return "desktop"
    inferred = infer_marketplace_category_from_signals(
        {"idea": idea, "tags": []},
        None,
    )
    return inferred or "saas"
