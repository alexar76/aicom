# DevTools / Ops platform — playbook

> **Built-in pack:** `devtools_ops` — see [README.md](./README.md) and [methodology-agent.md](../methodology-agent.md).

- **Deployments** and **rollbacks** must be observable: who, what revision, when.
- **Logs** and **metrics** correlation (trace/id) beats plain text dumps alone.
- **Alerts** need ownership, escalation, and **ack** semantics; measure noise vs signal.
- Integrations: least-privilege tokens, rotation, and audit on config changes.
- DORA-style health: **lead time**, **deploy frequency**, **change fail rate**, **MTTR** — even if approximate at first.
