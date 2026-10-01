# Almacén persistente de seguridad (H-3 / H-5)

> **English:** [security-persistence.md](./security-persistence.md) · **Русский:** [security-persistence.ru.md](./security-persistence.ru.md) · **Español** · **Français:** [security-persistence.fr.md](./security-persistence.fr.md) · **中文:** [security-persistence.zh.md](./security-persistence.zh.md)

SQLite para **límite de intentos de inicio de sesión** y **protección contra replay de nonce OIDC** — sin Redis en el stack de contenedor único.

Implementación: `core/persistent_security_store.py`, integrado en `web/backend/core/security.py` y `web/backend/core/oidc_auth.py`.

---

## Base de datos

| Ajuste | Por defecto |
|--------|---------|
| Ruta | `data/state/security_store.db` |
| Override | `AIFACTORY_SECURITY_STORE_DB` |
| Modo | WAL + bloqueo de hilo |
| Fallback | FS de solo lectura → en memoria, **sin caída** |

---

## H-5 — Rate-limit sobrevive al reinicio

`SecurityManager` guarda intentos fallidos en SQLite. Tras reiniciar el contenedor, los contadores de fuerza bruta **no se resetean**.

| Método | Comportamiento |
|--------|----------------|
| `check_login_attempts(ip)` | Cuenta los intentos en la ventana de bloqueo desde SQLite |
| `record_login_attempt(ip, success=False)` | Registra intento |
| `reset_login_attempts(ip)` | Limpia tras inicio de sesión correcto |

Dict en memoria como respaldo si el almacén no está disponible.

---

## H-3 — Replay de nonce OIDC

Tras validar el nonce en `verify_id_token`, el nonce se **consume** en el almacén (TTL = min(vida del id_token, 1 h)).

| Caso | Comportamiento |
|------|----------------|
| Primer uso | Login OK |
| Replay en TTL | `ValueError("nonce already used")` |
| Almacén no disponible | **Fail-open** — advertencia en el registro, no bloquea todos los inicios de sesión |

---

## Tests

| Archivo | Cubre |
|---------|-------|
| `tests/test_persistent_security_store.py` | Ventana rate-limit, reinicio, TTL nonce, SecurityManager |
| `tests/test_oidc_nonce_replay.py` | First-use, replay, mismatch |

---

## Relacionado

Guía de seguridad completa: [security.md](./security.md) (middleware HTTP, CSRF, cadena de auditoría, sandbox).
