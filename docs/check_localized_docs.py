#!/usr/bin/env python3
"""Check the user-facing SaaS documentation matrix."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
LOCALES = ("en", "ru", "es", "pt-BR", "de", "fr", "ja", "ko", "zh-CN", "tr")
REQUIRED = (
    "README.md",
    "USER_GUIDE.md",
    "USE_CASES.md",
    "GLOSSARY.md",
    "TRIAL.md",
    "KOVA_CAPABILITIES.md",
    "DEVELOPER_GUIDE.md",
    "screenshots/dashboard.svg",
)
GUIDE_MARKERS = (
    "/billing",
    "/memory/api/memories",
    "/teams/api/teams",
    "/v1/keys/rotate",
    "/v1/keys/revoke",
    "/v1/trials",
    "X-SaaS-Key",
    "X-Actor-ID",
    "checkout",
    "48",
)
USE_CASE_MARKERS = ("KOVA", "USDC", "Base", "Gateway")
KOVA_MARKERS = (
    "/ai-market/v2/invoke",
    "X-AIMarket-Internal-Token",
    "X-Provider-Signature",
    "service-to-service",
    "kova.network.status@v1",
    "kova.usdc.invoice.create@v1",
)
DEVELOPER_MARKERS = (
    "did:actor:",
    "X-Actor-Signature",
    "/ai-market/v2/manifest",
    "/ai-market/v2/supply/register",
    "publisher token",
    "PostgreSQL",
    "SQLite",
)
GLOSSARY_TERMS = (
    "API key",
    "Actor identity",
    "Memory Unit",
    "Provenance",
    "Invoice",
    "Tx hash",
    "Confirmation",
    "Entitlement",
    "Namespace",
    "Rate limit",
    "Trial",
)


def main() -> int:
    failures: list[str] = []
    screenshot_hashes: set[bytes] = set()
    for locale in LOCALES:
        base = ROOT / "i18n" / locale
        for relative in REQUIRED:
            if not (base / relative).is_file():
                failures.append(f"{locale}: missing {relative}")

        readme_path = base / "README.md"
        readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
        if "screenshots/dashboard.svg" not in readme:
            failures.append(f"{locale}: README does not embed dashboard preview")
        if "GLOSSARY.md" not in readme:
            failures.append(f"{locale}: README does not link localized glossary")
        if "TRIAL.md" not in readme:
            failures.append(f"{locale}: README does not link localized trial guide")
        if "KOVA_CAPABILITIES.md" not in readme:
            failures.append(f"{locale}: README does not link localized KOVA capability guide")
        if "DEVELOPER_GUIDE.md" not in readme:
            failures.append(f"{locale}: README does not link localized developer guide")

        guide_path = base / "USER_GUIDE.md"
        guide = guide_path.read_text(encoding="utf-8") if guide_path.is_file() else ""
        for marker in GUIDE_MARKERS:
            if marker.lower() not in guide.lower():
                failures.append(f"{locale}: USER_GUIDE missing {marker}")
        if "KOVA_CAPABILITIES.md" not in guide:
            failures.append(f"{locale}: USER_GUIDE does not link KOVA capability guide")

        kova_path = base / "KOVA_CAPABILITIES.md"
        kova = kova_path.read_text(encoding="utf-8") if kova_path.is_file() else ""
        for marker in KOVA_MARKERS:
            if marker.lower() not in kova.lower():
                failures.append(f"{locale}: KOVA_CAPABILITIES missing {marker}")

        developer_path = base / "DEVELOPER_GUIDE.md"
        developer = developer_path.read_text(encoding="utf-8") if developer_path.is_file() else ""
        for marker in DEVELOPER_MARKERS:
            if marker.lower() not in developer.lower():
                failures.append(f"{locale}: DEVELOPER_GUIDE missing {marker}")

        use_cases_path = base / "USE_CASES.md"
        use_cases = use_cases_path.read_text(encoding="utf-8") if use_cases_path.is_file() else ""
        for marker in USE_CASE_MARKERS:
            if marker.lower() not in use_cases.lower():
                failures.append(f"{locale}: USE_CASES missing {marker}")

        glossary_path = base / "GLOSSARY.md"
        glossary = glossary_path.read_text(encoding="utf-8") if glossary_path.is_file() else ""
        for term in GLOSSARY_TERMS:
            if term.lower() not in glossary.lower():
                failures.append(f"{locale}: GLOSSARY missing {term}")

        screenshot_path = base / "screenshots" / "dashboard.svg"
        if screenshot_path.is_file():
            screenshot = screenshot_path.read_bytes()
            if len(screenshot) < 500 or b"<svg" not in screenshot:
                failures.append(f"{locale}: dashboard preview is not a complete SVG")
            screenshot_hashes.add(screenshot)

    if len(screenshot_hashes) != len(LOCALES):
        failures.append("localized dashboard previews must be unique for every locale")

    if failures:
        print("Documentation check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    print(f"Documentation check passed: {len(LOCALES)} locales, {len(REQUIRED)} required artifacts each.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
