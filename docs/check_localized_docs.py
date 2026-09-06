#!/usr/bin/env python3
"""Check the user-facing SaaS documentation matrix."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
LOCALES = ("en", "ru", "es", "pt-BR", "de", "fr", "ja", "ko", "zh-CN", "tr")
REQUIRED = ("README.md", "USER_GUIDE.md", "USE_CASES.md", "GLOSSARY.md", "TRIAL.md", "screenshots/dashboard.svg")
GUIDE_MARKERS = (
    "/billing",
    "/memory/api/memories",
    "/teams/api/teams",
    "/v1/keys/rotate",
    "/v1/keys/revoke",
    "/v1/trials",
    "X-SaaS-Key",
    "X-Actor-ID",
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

        guide_path = base / "USER_GUIDE.md"
        guide = guide_path.read_text(encoding="utf-8") if guide_path.is_file() else ""
        for marker in GUIDE_MARKERS:
            if marker not in guide:
                failures.append(f"{locale}: USER_GUIDE missing {marker}")

        glossary_path = base / "GLOSSARY.md"
        glossary = glossary_path.read_text(encoding="utf-8") if glossary_path.is_file() else ""
        for term in GLOSSARY_TERMS:
            if term.lower() not in glossary.lower():
                failures.append(f"{locale}: GLOSSARY missing {term}")

    if failures:
        print("Documentation check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    print(f"Documentation check passed: {len(LOCALES)} locales, {len(REQUIRED)} required artifacts each.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
