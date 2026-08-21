# Magasin de sécurité persistant (H-3 / H-5)

> **English:** [security-persistence.md](./security-persistence.md) · **Русский:** [security-persistence.ru.md](./security-persistence.ru.md) · **Español:** [security-persistence.es.md](./security-persistence.es.md) · **Français** · **中文:** [security-persistence.zh.md](./security-persistence.zh.md)

Persistance adossée à SQLite pour les **limites de tentatives de connexion** et la **protection contre le rejeu de nonce OIDC** — pas de Redis requis dans le stack à conteneur unique.

Implémentation : `core/persistent_security_store.py`, câblé depuis `web/backend/core/security.py` et `web/backend/core/oidc_auth.py`.

---

## Base de données

| Paramètre | Par défaut |
|-----------|------------|
| Chemin | `data/state/security_store.db` |
| Override | `AIFACTORY_SECURITY_STORE_DB` |
| Mode | WAL + verrou de thread |
| Fallback | Si la BD ne peut pas être ouverte (FS en lecture seule), les appelants utilisent un comportement en mémoire — **aucun crash** |

---

## H-5 — La limite de tentatives de connexion survit au redémarrage

`SecurityManager` enregistre les connexions admin échouées dans SQLite. Après le redémarrage du conteneur, les compteurs de force brute ne sont **pas** réinitialisés.

| Méthode | Comportement |
|---------|--------------|
| `check_login_attempts(ip)` | Compte les tentatives dans la fenêtre de bannissement depuis SQLite |
| `record_login_attempt(ip, success=False)` | Ajoute une tentative |
| `reset_login_attempts(ip)` | Réinitialise après une connexion réussie |

Le dict en mémoire reste le fallback lorsque le magasin est indisponible.

---

## H-3 — Rejeu de nonce OIDC

Après que `verify_id_token` a validé la revendication nonce du JWT, le nonce est **réservé** dans le magasin (TTL = min(durée de vie de l'id_token, 1 heure)).

| Résultat | Comportement |
|----------|--------------|
| Première utilisation | La connexion se poursuit |
| Rejeu dans le TTL | `ValueError("nonce already used")` |
| Magasin indisponible | **Fail-open** — avertissement dans le journal, ne bloque pas toutes les connexions |

---

## Tests

| Fichier | Couvre |
|---------|--------|
| `tests/test_persistent_security_store.py` | Fenêtre de limite de débit, persistance au redémarrage, TTL du nonce, SecurityManager |
| `tests/test_oidc_nonce_replay.py` | Première utilisation OK, rejeu rejeté, incohérence |

---

## Associé

Guide de sécurité complet : [security.md](./security.md) (middleware HTTP, CSRF, chaîne d'audit, sandbox).
