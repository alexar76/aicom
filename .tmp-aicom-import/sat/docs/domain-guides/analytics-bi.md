# Analytics / BI — playbook

> **Built-in pack:** `analytics_bi` — see [README.md](./README.md) and [methodology-agent.md](../methodology-agent.md).

- **Metric definitions** should be versioned and documented (single source of truth).
- Dashboards need **filters**, **drill-down**, and **export** without leaking raw PII.
- Track **data freshness** and **query latency**; surface stale data to users.
- Role-based **sharing**: view vs edit vs admin on datasets and dashboards.
- Prefer consistent **time zones** and **grain** (day vs hour) in charts.
