#!/usr/bin/env python3
"""Write docs/localization.md for each desktop SKU."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop-integrations"

TEMPLATE = """# Localization (en / ru / es + language packs)

## Built-in locales

| Code | Language |
|------|----------|
| `en` | English |
| `ru` | Русский |
| `es` | Español |

Strings live in `lib/l10n/app_strings.dart` (generated from `scripts/bootstrap_desktop_l10n.py`).
Shared UI (wallet, backup, economics bar) comes from `aicom_desktop_core` ARB files.

## Switch language in the app

1. Open **Settings** (gear icon)
2. Pick **English**, **Русский**, or **Español**
3. UI updates immediately; choice is persisted per app

## Add a new language pack (extensible)

1. Create JSON in one of these folders:
   - `~/Documents/AICOM/language-packs/{app_id}/xx.json` (desktop)
   - `language-packs/{app_id}/xx.json` (next to the app / repo root for dev)

2. Format:

```json
{{
  "@@locale": "de",
  "appTitle": "My Product Title",
  "navDashboard": "Dashboard"
}}
```

3. Copy keys from `lib/l10n/app_strings.dart` (`en` section)
4. In app **Settings → Reload language packs**
5. Select the new locale from the list

Example: see `language-packs/{app_id}/de.json` in this repo.

## Regenerate built-in catalogs

```bash
python3 scripts/bootstrap_desktop_l10n.py
```

Edit the `CATALOG` dict in that script, then re-run for all 8 apps.

## Backup user data

Settings → **Export user data to file** saves a versioned JSON backup:

```json
{{
  "format": "aicom-user-backup",
  "version": 1,
  "app_id": "{app_id}",
  "exported_at": "2026-05-20T12:00:00Z",
  "data": {{ "preferences": {{ ... }} }}
}}
```

Import restores preferences scoped to this app. Desktop: native file picker. Web: JSON preview dialog.
"""

for slug in [
    "interview-prep-coach",
    "personal-finance-coach",
    "capability-composer",
    "cold-outreach-coach",
    "creator-algorithm-coach",
    "discovery-prospector",
    "freelance-contract-reviewer",
    "reputation-dashboard",
]:
    path = DESKTOP / slug / "docs" / "localization.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(TEMPLATE.format(app_id=slug), encoding="utf-8")
    print(f"OK {path}")
