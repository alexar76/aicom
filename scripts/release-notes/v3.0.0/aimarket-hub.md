# aimarket-hub v3.0.0 — PyPI + GHCR

## PyPI

- Package: `aimarket-hub` 3.0.0
- Install: `pip install aimarket-hub`
- With core plugins: `pip install "aimarket-hub[plugins]"`

## GHCR (satellite)

- Hub-only image: `ghcr.io/alexar76/aimarket-hub:v3.0.0`
- Full image (all plugins): built from monorepo `aimarket-hub/Dockerfile` → `ghcr.io/alexar76/aimarket-hub` via `aicom` publish-ghcr workflow

## Trusted publishing

Configure PyPI trusted publisher: repository `alexar76/aimarket-hub`, workflow `publish-pypi.yml`.
