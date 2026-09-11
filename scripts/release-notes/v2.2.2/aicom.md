# AI-Factory v2.2.2

Factory publish hardening for live Vercel products (Sentinel path):

- Inject public ATLAS mesh env (`ATLAS_BASE_URL`) instead of localhost
- Rewrite legacy `/aimarket/invoke` → `/ai-market/v2/invoke`
- Export `settings` shim + ATLAS-aware rule engine in the vendored bundle
- Widen ATLAS bbox (±5°) and parallelize advisory invokes
- Auto-add `pydantic-settings` / bcrypt when the product imports them
- Live gate: demo-auth mismatch messaging, mesh-unreachable detection, longer advisory timeout

## Note
Trimmed force-mirror of the monorepo. Prefer Gitea for full history.

https://github.com/alexar76/aicom
