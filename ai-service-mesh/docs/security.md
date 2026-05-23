# Security Model

## Threat model

| Threat | Mitigation |
|--------|------------|
| SSRF via agent endpoints | DNS-resolving `url_is_safe()` blocks private/reserved IPs |
| Drive-by CSRF | CORS allowlist empty by default; require `MESH_CORS_ORIGINS` |
| Unauthorized agent registration | `MESH_ADMIN_TOKEN` + Bearer hmac compare |
| Unauthorized task spend | `MESH_API_TOKEN` on `POST /v1/tasks` in production |
| Token brute force | `hmac.compare_digest` for secrets |
| DoS | Per-IP sliding window rate limit |
| Clickjacking | `X-Frame-Options: DENY` |
| MIME sniffing | `X-Content-Type-Options: nosniff` |

## Fail-closed defaults

- No CORS origins unless explicitly configured.
- Admin federation-style endpoints reject when `MESH_ADMIN_TOKEN` unset (503).
- Production writes require API token.

## Attestation

Agents prove metadata integrity with:

```
attestation = base64url( sha256( "{name}|{endpoint}|{cap1,cap2,...}" ) )
```

This is **not** a hardware TEE attestation — production integrates `aimarket-plugins` TEE Escrow for settlement guarantees.

## Supply chain

- Pin Python deps in `pyproject.toml`.
- Docker images use `python:3.12-slim` and `node:22-alpine`.
- Run `pytest` + Slither on escrow contracts in parent monorepo CI.

## Security checklist (release)

- [ ] Set strong `MESH_API_TOKEN` and `MESH_ADMIN_TOKEN`
- [ ] Configure `MESH_CORS_ORIGINS` to dashboard origin only
- [ ] TLS termination at ingress
- [ ] Replace in-memory escrow with TEE / on-chain
- [ ] Migrate SQLite → PostgreSQL with encrypted volumes
- [ ] Enable audit log export from `activity` table

## Reporting

Report vulnerabilities through the parent monorepo security process (see `aimarket-hub/SECURITY.md`).
