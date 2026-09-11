# 持久化安全存储 (H-3 / H-5)

> **English:** [security-persistence.md](./security-persistence.md) · **Русский:** [security-persistence.ru.md](./security-persistence.ru.md) · **Español:** [security-persistence.es.md](./security-persistence.es.md) · **Français:** [security-persistence.fr.md](./security-persistence.fr.md) · **中文**

基于 SQLite 的持久化，用于**登录速率限制**和 **OIDC nonce 重放保护** —— 单容器栈中无需 Redis。

实现：`core/persistent_security_store.py`，从 `web/backend/core/security.py` 和 `web/backend/core/oidc_auth.py` 接入。

---

## 数据库

| 设置 | 默认值 |
|------|--------|
| 路径 | `data/state/security_store.db` |
| 覆盖 | `AIFACTORY_SECURITY_STORE_DB` |
| 模式 | WAL + 线程锁 |
| 回退 | 若无法打开数据库（只读文件系统），调用方使用内存内行为 —— **不崩溃** |

---

## H-5 — 登录速率限制在重启后保留

`SecurityManager` 将失败的管理员登录记录到 SQLite。容器重启后，暴力破解计数器**不会**被重置。

| 方法 | 行为 |
|------|------|
| `check_login_attempts(ip)` | 从 SQLite 统计封禁窗口内的尝试次数 |
| `record_login_attempt(ip, success=False)` | 追加一次尝试 |
| `reset_login_attempts(ip)` | 登录成功后清除 |

当存储不可用时，内存字典作为回退保留。

---

## H-3 — OIDC nonce 重放

在 `verify_id_token` 校验 JWT 的 nonce 声明后，该 nonce 会在存储中被**占用**（TTL = min(id_token 生命周期, 1 小时)）。

| 结果 | 行为 |
|------|------|
| 首次使用 | 登录继续 |
| TTL 内重放 | `ValueError("nonce already used")` |
| 存储不可用 | **Fail-open** —— 记录警告，不阻止所有登录 |

---

## 测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_persistent_security_store.py` | 速率限制窗口、重启持久化、nonce TTL、SecurityManager |
| `tests/test_oidc_nonce_replay.py` | 首次使用 OK、重放被拒、不匹配 |

---

## 相关

完整安全指南：[security.md](./security.md)（HTTP 中间件、CSRF、审计链、sandbox）。
