# Almacén persistente de seguridad (H-3 / H-5)

> **English:** [security-persistence.md](./security-persistence.md) · **Русский:** [security-persistence.ru.md](./security-persistence.ru.md)

SQLite para **límite de intentos de login** y **protección contra replay de nonce OIDC** — sin Redis en el stack single-container.

Implementación: `core/persistent_security_store.py`, integrado en `web/backend/core/security.py` y `web/backend/core/oidc_auth.py`.

---

## Base de datos

| Ajuste | Default |
|--------|---------|
| Ruta | `data/state/security_store.db` |
| Override | `AIFACTORY_SECURITY_STORE_DB` |
| Modo | WAL + lock |
| Fallback | FS solo lectura → in-memory, **sin caída** |

---

## H-5 — Rate-limit sobrevive al reinicio

`SecurityManager` guarda intentos fallidos en SQLite. Tras reiniciar el contenedor, los contadores de fuerza bruta **no se resetean**.

| Método | Comportamiento |
|--------|----------------|
| `check_login_attempts(ip)` | Cuenta en ventana ban desde SQLite |
| `record_login_attempt(ip, success=False)` | Registra intento |
| `reset_login_attempts(ip)` | Limpia tras login OK |

Dict in-memory como fallback si el store no está disponible.

---

## H-3 — Replay de nonce OIDC

Tras validar el nonce en `verify_id_token`, el nonce se **consume** en el store (TTL = min(vida del id_token, 1 h)).

| Caso | Comportamiento |
|------|----------------|
| Primer uso | Login OK |
| Replay en TTL | `ValueError("nonce already used")` |
| Store no disponible | **Fail-open** — warning en log, no bloquea todos los logins |

---

## Tests

| Archivo | Cubre |
|---------|-------|
| `tests/test_persistent_security_store.py` | Ventana rate-limit, reinicio, TTL nonce, SecurityManager |
| `tests/test_oidc_nonce_replay.py` | First-use, replay, mismatch |

---

## Relacionado

[security.md](./security.md) — CSRF, firewall, audit chain, sandbox.
