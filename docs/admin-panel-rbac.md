# Admin panel RBAC (human operator accounts)

This document describes **roles for people who sign in to `/admin`** (JWT claim `role`).  
It is **not** about pipeline agents (PM, Developer, QA, …) — those are documented in [agents.md](./agents.md).

## Where roles are defined

| Layer | Location |
|-------|----------|
| Enum, descriptions, path rules | `web/backend/core/admin_roles.py` |
| HTTP enforcement | `require_admin_with_rbac` → `check_admin_rbac()` on each admin API request |
| Per-user stored role | `data/state/admin_users.json` (via `web/backend/services/admin_users_store.py`) |
| Users UI | `web/frontend/components/admin/tabs/UsersTab.tsx` (tab visible only to `super_admin`) |
| Role list API | `GET /api/admin/users/roles/meta` (same RBAC as other `/api/admin/users/*` routes) |

Legacy installs: JWTs **without** a `role` claim are treated as **`super_admin`** so existing single-admin setups keep working (`normalize_role` in `admin_roles.py`).

## Roles (least → most privilege)

### 1. `viewer`

- **Purpose:** read-only monitoring.
- **Can:** `GET` on most admin APIs — dashboard, pipeline, agents, logs, metrics, chat read, etc.
- **Cannot:** change data (`POST`/`PATCH`/`DELETE`), or open sensitive config endpoints (LLM providers, security audit, platform settings, methodology admin, release tools, chat settings, etc. — see `VIEWER_BLOCKED_GET_PREFIXES` in `admin_roles.py`).

### 2. `operator`

- **Purpose:** run the factory day-to-day.
- **Can:** pipeline actions, queue products, discovery triggers, and other writes **except** those blocked for operators (providers, security, settings, user management, etc. — see `OPERATOR_WRITE_DENIED_PREFIXES`).
- **Cannot:** manage admin users (`/api/admin/users`), edit providers/settings/security, or privileged auth flows (2FA setup) reserved for `admin+`.

### 3. `admin`

- **Purpose:** platform configuration without account administration.
- **Can:** providers, settings, methodology, Director triggers, security pages, etc.
- **Cannot:** create/delete/patch **admin panel accounts** (`/api/admin/users/*` is `super_admin` only).

### 4. `super_admin`

- **Purpose:** full control of the admin panel, including **Users & access**.
- **Can:** everything `admin` can, plus `GET/POST/PATCH/DELETE /api/admin/users` and role assignment.

## API reference (users)

All under `/api/admin/users`, **`super_admin` only**:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/users` | List accounts (no password hashes) |
| `GET` | `/api/admin/users/roles/meta` | `{ "roles": [ { "id", "label", "description" } ] }` in stable order |
| `POST` | `/api/admin/users` | Create user (`username`, `password`, `role`) |
| `PATCH` | `/api/admin/users/{user_id}` | Update `role` and/or `enabled` |
| `DELETE` | `/api/admin/users/{user_id}` | Remove account |

## UI notes

- The **Users & access** sidebar entry is shown only when the signed-in user’s JWT role is `super_admin` (`web/frontend/app/admin/page.tsx`).
- Role labels in the UI are **localized** (EN/RU/ES) in `web/frontend/lib/adminI18n.ts`; the API descriptions are English reference text.

## Related

- [admin-guide.md](./admin-guide.md) — full admin tab reference  
- [api-integration-guide.md](./api-integration-guide.md) — REST patterns and auth  
