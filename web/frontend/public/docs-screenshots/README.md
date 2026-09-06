# Docs screenshots (bundled for `/docs`)

PNG files here are **optional**: they power inline images on the public **Documentation** page (`/docs`).

Generate or refresh from a running app:

```bash
cd web/frontend
npm run capture-docs-screenshots
```

The script writes to `docs/assets/screenshots/` (repo docs) **and** copies the same files into this folder.
