# language-packs (legacy root)

**Deprecated.** Language pack JSON files now live **inside each desktop app**:

```
desktop-integrations/<app-id>/language-packs/de.json
```

When mirroring to `aimarket-desktop`, export maps to:

```
apps/<app-id>/language-packs/
```

The mirror script also picks up any remaining files under this root folder (`language-packs/<app-id>/`) for backward compatibility during migration.
