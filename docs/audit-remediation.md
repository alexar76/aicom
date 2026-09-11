# Audit remediation tracker

Status of recommendations from the **alexar76 ecosystem audit** (2026-05).  
Grants / bounty programs are **out of scope** per operator decision.

Legend: ✅ implemented · 🟡 partial / documented · ⬜ roadmap

---

## Security — CI/CD

| Item | Status | Where |
|------|--------|-------|
| Python SAST (Bandit, fail on High) | ✅ | `.github/workflows/security-scan.yml`, `scripts/run_dependency_audit.sh` |
| Python dependency audit (pip-audit) | ✅ | same (report artifact; upgrades tracked below) |
| npm audit (frontend + TS SDK) | ✅ | same (`--audit-level=high`, soft-fail until upgrades land) |
| EVM static analysis (Slither) | ✅ | `.github/workflows/contracts-ci.yml` (AIMarket + ACEX) |
| Dependabot | ✅ | `.github/dependabot.yml` (pip, npm×2, actions, cargo) |
| Contract audit script + disposition template | ✅ | `scripts/run_contract_audit.sh`, `contracts/audits/audit-response.md` |

Local run:

```bash
chmod +x scripts/run_dependency_audit.sh scripts/run_contract_audit.sh
./scripts/run_dependency_audit.sh
./scripts/run_contract_audit.sh
```

---

## Dependencies — known CVE backlog

`pip-audit` currently reports open advisories on pinned packages (langchain-core, starlette, python-multipart, etc.).  
**Policy:** Bandit **High** blocks merge; pip-audit/npm audit upload reports and are tracked here until upgraded in dedicated PRs (avoid drive-by major bumps).

| Package | Action |
|---------|--------|
| `starlette` / `fastapi` | Upgrade FastAPI stack when E2E green |
| `langchain-core` / `langgraph-checkpoint` | Upgrade agent stack in isolated PR |
| `python-multipart` | Bump to ≥0.0.18 |
| `cryptography` / `pyopenssl` | Bump to patched releases |

---

## Production guard (`AIFACTORY_PROD=1`)

| Item | Status | Where |
|------|--------|-------|
| Weak admin passwords | ✅ | `security/prod_startup_guard.py` |
| Demo + prod flag conflict | ✅ | same |
| Payment stub / testnet / zero recipient | ✅ | same |
| ZK simulation off in prod | ✅ | same |
| **SQLite blocked in prod** | ✅ | same + `docs/architecture/scaling.md` |
| **LLM API key required** | ✅ | `llm/startup_validation.py` |
| Mandatory admin 2FA in prod | ✅ | `AIFACTORY_REQUIRE_ADMIN_2FA=1` + guard check |
| Groth16 artifact validation | ✅ | `security/zk_artifacts.py`, `scripts/verify_zk_artifacts.sh` |

Enable production mode only after:

```bash
AIFACTORY_PROD=1
PIPELINE_DB_BACKEND=postgres
USE_SQLITE=false
AIFACTORY_PAYMENT_VERIFY_STUB=0
AIFACTORY_PAYMENT_TESTNET=0
AIMARKET_ZK_SIMULATED=0
AIMARKET_ZK_BACKEND=groth16
# + valid AIMARKET_PAYMENT_RECIPIENT, LLM keys, strong admin password, ZK ceremony artifacts
# + optional AIFACTORY_REQUIRE_ADMIN_2FA=1 after TOTP/WebAuthn enabled
```

---

## Smart contracts (ACEX / AIMarket escrow)

| Item | Status | Notes |
|------|--------|-------|
| Ownable2Step on capability NFT | ✅ | `contracts/evm/src/AIMarketCapabilityNFT.sol` |
| Multisig for contract owner (Safe) | 🟡 | **Required before mainnet** — transfer `owner` to Gnosis Safe; document in `contracts/DEPLOY.md` |
| External audit (OpenZeppelin / Trail of Bits) | 🟡 | CI Slither + `contracts/audits/audit-response.md` disposition template; vendor audit pre-mainnet |

---

## Secrets management

| Item | Status | Where |
|------|--------|-------|
| Keys in `data/secrets/llm/*` (gitignored) | ✅ | `docs/security-secrets.md` |
| Docker secrets overlay | ✅ | `docker-compose.secrets.yml` |
| HashiCorp Vault / unified resolver | ✅ | `security/secret_resolver.py`, `security/bootstrap_secrets.py`, `.env.example` |
| Boot sync files → Fernet vault | ✅ | `entrypoint.sh`, `AIFACTORY_SECRETS_SYNC_FROM_FILES` |

---

## Access control

| Item | Status | Where |
|------|--------|-------|
| JWT admin auth | ✅ | `web/backend/` |
| TOTP 2FA | ✅ | Admin settings |
| WebAuthn passkeys | ✅ | `docs/security.md` |
| OIDC SSO (native) | ✅ | `web/backend/core/oidc_auth.py`, admin login SSO button |
| Trusted-header SSO (Authelia / oauth2-proxy) | ✅ | `AIFACTORY_SSO_TRUSTED_HEADER`, `get_current_admin()` |

**Production recommendation:** enable 2FA for all admin accounts; prefer WebAuthn where available.

---

## Observability

| Item | Status | Where |
|------|--------|-------|
| Prometheus scrape | ✅ | `prometheus.yml`, `/metrics` |
| Grafana dashboards | ✅ | `grafana/dashboards/` |
| Grafana alert rules (pipeline/API) | ✅ | `grafana/alerting/rules.yml` |
| OpenTelemetry tracing | 🟡 | Optional OTLP env vars in `.env.example`; full instrumentation roadmap |

---

## Federation / ACEX

| Item | Status | Notes |
|------|--------|-------|
| Hub reputation scoring | ✅ | `aimarket-hub` plugins |
| ZK proofs for federation trust | 🟡 | Ceremony coordinator + prod guard; run `scripts/zk_ceremony_coordinator.sh` before mainnet |
| Monorepo canonical for `acex/` + `ai-service-mesh/` | ✅ | `docs/repository-canonical-policy.md` |

---

## Community (no grants)

| Item | Status | Where |
|------|--------|-------|
| Issue templates (bug, feature, good first issue) | ✅ | `.github/ISSUE_TEMPLATE/` |
| Pull request template | ✅ | `.github/pull_request_template.md` |
| CONTRIBUTING.md | ✅ | root |
| External contributor grants | ⬜ | **Explicitly excluded** |

---

## License compatibility

MIT (factory, SDKs, protocol) and Apache 2.0 (hub, ACEX) are compatible for combined deployment.  
Satellite mirrors inherit per-repo LICENSE; see `scripts/mirror_satellites.sh` governance copy step.
