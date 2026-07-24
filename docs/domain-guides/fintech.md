# Fintech Best Practices

> **Built-in pack:** `finance_billing` — see [domain-guides/README.md](./README.md) and [methodology-agent.md](../methodology-agent.md).

- Treat money operations as idempotent: every transfer/charge must have an idempotency key.
- Keep immutable audit trails for balance-impacting actions.
- Use explicit state machines for payment lifecycle: pending, authorized, captured, settled, failed, reversed.
- Never trust client-side amounts or currencies; re-derive on server.
- Apply strict reconciliation jobs for ledger vs external processor state.
- Enforce least-privilege for admin/ops flows and rotate secrets frequently.
