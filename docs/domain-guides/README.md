# Domain guides (playbooks)

Two layers:

1. **Built-in methodology packs (canonical)** — ten declarative profiles in code (entities, lifecycles, capabilities, API expectations). Full table: **[methodology-agent.md](../methodology-agent.md)** — modules under `web/backend/services/domain_methodology/packs/`.
2. **Narrative guides (this folder)** — short owner/operator notes. They do **not** replace the machine-readable pack; use the Admin API for the full schema.

## `domain_id` ↔ narrative file

| `domain_id` | Pack label | Playbook |
|-------------|------------|----------|
| `crm_sales` | CRM / Sales pipeline | [crm-sales.md](./crm-sales.md) |
| `helpdesk_support` | Helpdesk / IT support | [helpdesk.md](./helpdesk.md) |
| `ecommerce` | E-commerce | [ecommerce.md](./ecommerce.md) |
| `lms_education` | LMS / Education | [lms-education.md](./lms-education.md) |
| `hr_recruiting` | HR / Recruiting (ATS) | [hr-recruiting.md](./hr-recruiting.md) |
| `project_management` | Project / Task management | [project-management.md](./project-management.md) |
| `finance_billing` | Finance / Billing | [fintech.md](./fintech.md) *(filename legacy)* |
| `healthcare_wellness` | Healthcare / Wellness | [healthcare.md](./healthcare.md) |
| `analytics_bi` | Analytics / BI | [analytics-bi.md](./analytics-bi.md) |
| `devtools_ops` | DevTools / Ops platform | [devtools-ops.md](./devtools-ops.md) |

## Admin API

With admin auth:

- `GET /api/admin/methodology/domains` — compact catalog  
- `GET /api/admin/methodology/domains/{domain_id}` — full pack JSON  
- `POST /api/admin/methodology/domains/match` — heuristic pack match from idea/spec  
