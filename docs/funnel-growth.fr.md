# Couche de croissance de l'entonnoir (Funnel growth)

> **English:** [funnel-growth.md](./funnel-growth.md) · **Русский:** [funnel-growth.ru.md](./funnel-growth.ru.md) · **Español:** [funnel-growth.es.md](./funnel-growth.es.md) · **Français** · **中文:** [funnel-growth.zh.md](./funnel-growth.zh.md)

Capture publique de leads, démarrage automatique du pipeline, suivi de statut, analytique et distribution après livraison. Implémenté sous `web/backend/services/funnel_*` et `web/backend/api/marketing.py`.

---

## Aperçu

| Surface | Chemin / API | Objectif |
|---------|--------------|----------|
| Formulaire de lead | `/lead` | Brief public → auto-pipeline optionnel |
| Page de statut | `/status/{token}` | Interroger l'état du produit (15 s) |
| Métriques de confiance | `TrustMetricsStrip` (page d'accueil) | Shipped / in-pipeline / leads en direct |
| Widget admin | Dashboard → carte Funnel | `GET /api/admin/funnel/dashboard` |
| Waitlist embed | `GET /api/marketing/waitlist.js` | Formulaires sur les landings générés |

À l'état **COMPLETED** du pipeline, `orchestrator/task_executor_agent.py` appelle `funnel_distribute` (auto-listing hub + blog) et `notify_lead_product_completed` (email).

---

## API publiques

### `POST /api/marketing/lead`

```json
{
  "email": "owner@example.com",
  "idea": "Marketing landing for AI scheduling assistant with waitlist",
  "name": "",
  "company": "",
  "source": "lead_page",
  "referral": null
}
```

La réponse inclut `status_token`, `status_url`, `product_id`, `pipeline_started`.

### `GET /api/marketing/lead/status/{token}`

Public (sans authentification). Renvoie l'email masqué, `product_state`, `storefront_url`, `sandbox_ready`.

### `POST /api/marketing/waitlist`

Pour les pages de landing générées. Corps : `{ "product_id", "email", "name?", "meta?" }`.

### Intégration sur un landing généré

```html
<script src="/api/marketing/waitlist.js" data-product-id="prod-xxx"></script>
<form data-aifactory-waitlist>
  <input type="email" name="email" required />
  <button type="submit">Join waitlist</button>
</form>
```

Ou injectez le script via **Admin → Settings → published site head HTML**.

---

## Environnement

| Variable | Par défaut | Rôle |
|----------|------------|------|
| `AIFACTORY_LEAD_AUTO_PIPELINE` | `1` | Mettre en file le produit `marketing_landing` à la soumission du lead |
| `AIFACTORY_FUNNEL_AUTO_HUB_LIST` | `1` | Lister le produit sur le hub à l'état COMPLETED |
| `AIFACTORY_FUNNEL_NOTIFY_DISABLE` | non défini | Ignorer l'email de fin quand `1` |
| `AIFACTORY_FUNNEL_DIR` | `data/funnel/` | Persistance des leads et de la waitlist |
| `OUTREACH_SMTP_*` / `AIFACTORY_FUNNEL_SMTP_*` | — | Email de fin (réutilise le SMTP outreach) |

Docker `data-init` et `entrypoint.sh` créent `data/funnel/` et `data/logs/marketing/` détenus par l'UID `10001`.

---

## Persistance

| Fichier | Contenu |
|---------|---------|
| `data/funnel/leads.json` | Enregistrements de leads, tokens de statut, liaison au produit |
| `data/funnel/waitlist.jsonl` | Inscriptions waitlist (append-only) |
| `data/logs/marketing/events.jsonl` | Événements d'analytique (aussi utilisés par les métriques de l'entonnoir) |

---

## Admin

- **`GET /api/admin/funnel/dashboard?window_hours=168`** — étapes de l'entonnoir, leads sur 7 j, commandes payées, leads récents.
- Nécessite le RBAC admin (`Depends(require_admin_with_rbac)`).

---

## Tests

`tests/test_funnel_growth.py` — auto-pipeline des leads, statut public, étapes d'analytique.

---

## Hors périmètre (à venir)

- Paiement Stripe one-shot pour les CTA des landings
- Récupération de panier abandonné
- Capture d'email dans le hero (le hero utilise encore `/api/public/generate-landing`)

Voir aussi : [marketing.md](./marketing.md) (analytique du storefront), [pipeline-operations.md](./pipeline-operations.md).
