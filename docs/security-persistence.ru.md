# Персистентное хранилище безопасности (H-3 / H-5)

> **English:** [security-persistence.md](./security-persistence.md) · **Русский** · **Español:** [security-persistence.es.md](./security-persistence.es.md) · **Français:** [security-persistence.fr.md](./security-persistence.fr.md) · **中文:** [security-persistence.zh.md](./security-persistence.zh.md)

SQLite для **rate-limit логина** и **защиты от replay OIDC nonce** — Redis в single-container не нужен.

Код: `core/persistent_security_store.py`, интеграция в `web/backend/core/security.py` и `web/backend/core/oidc_auth.py`.

---

## База данных

| Параметр | Значение |
|----------|----------|
| Путь | `data/state/security_store.db` |
| Override | `AIFACTORY_SECURITY_STORE_DB` |
| Режим | WAL + lock |
| Fallback | Read-only FS → in-memory, **без падения** |

---

## H-5 — Rate-limit переживает рестарт

`SecurityManager` пишет неудачные попытки входа в SQLite. После рестарта контейнера счётчики брутфорса **не сбрасываются**.

| Метод | Поведение |
|-------|-----------|
| `check_login_attempts(ip)` | Считает попытки в окне бана из SQLite |
| `record_login_attempt(ip, success=False)` | Запись попытки |
| `reset_login_attempts(ip)` | Сброс после успешного входа |

In-memory dict — fallback при недоступности хранилища.

---

## H-3 — Replay OIDC nonce

После проверки nonce в `verify_id_token` nonce **погашается** в хранилище (TTL = min(время жизни id_token, 1 ч)).

| Ситуация | Поведение |
|----------|-----------|
| Первое использование | Вход OK |
| Повтор в TTL | `ValueError("nonce already used")` |
| Хранилище недоступно | **Fail-open** — предупреждение в лог, логины не блокируются |

---

## Тесты

| Файл | Покрытие |
|------|----------|
| `tests/test_persistent_security_store.py` | Окно rate-limit, рестарт, TTL nonce, SecurityManager |
| `tests/test_oidc_nonce_replay.py` | First-use, replay, mismatch |

---

## См. также

[security.md](./security.md) — CSRF, firewall, audit chain, sandbox.
