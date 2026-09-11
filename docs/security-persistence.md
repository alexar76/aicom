# Persistent security store (H-3 / H-5)

> **English** · **Русский:** [security-persistence.ru.md](./security-persistence.ru.md) · **Español:** [security-persistence.es.md](./security-persistence.es.md) · **Français:** [security-persistence.fr.md](./security-persistence.fr.md) · **中文:** [security-persistence.zh.md](./security-persistence.zh.md)

SQLite-backed persistence for **login rate limits** and **OIDC nonce replay protection** — no Redis required in the single-container stack.

Implementation: `core/persistent_security_store.py`, wired from `web/backend/core/security.py` and `web/backend/core/oidc_auth.py`.

---

## Database

| Setting | Default |
|---------|---------|
| Path | `data/state/security_store.db` |
| Override | `AIFACTORY_SECURITY_STORE_DB` |
| Mode | WAL + thread lock |
| Fallback | If the DB cannot be opened (read-only FS), callers use in-memory behavior — **no crash** |

---

## H-5 — Login rate limit survives restart

`SecurityManager` records failed admin logins in SQLite. After container restart, brute-force counters are **not** reset.

| Method | Behavior |
|--------|----------|
| `check_login_attempts(ip)` | Counts attempts in the ban window from SQLite |
| `record_login_attempt(ip, success=False)` | Appends attempt |
| `reset_login_attempts(ip)` | Clears on successful login |

In-memory dict remains as fallback when the store is unavailable.

---

## H-3 — OIDC nonce replay

After `verify_id_token` validates the JWT nonce claim, the nonce is **claimed** in the store (TTL = min(id_token lifetime, 1 hour)).

| Outcome | Behavior |
|---------|----------|
| First use | Login proceeds |
| Replay within TTL | `ValueError("nonce already used")` |
| Store unavailable | **Fail-open** — log warning, do not block all logins |

---

## Tests

| File | Covers |
|------|--------|
| `tests/test_persistent_security_store.py` | Rate limit window, restart persistence, nonce TTL, SecurityManager |
| `tests/test_oidc_nonce_replay.py` | First-use OK, replay rejected, mismatch |

---

## Related

Full security guide: [security.md](./security.md) (HTTP middleware, CSRF, audit chain, sandbox).
