"""
Finance / Billing domain methodology pack.

Finance/billing is judged by data immutability (posted invoices are never
silently mutated), a complete audit trail of monetary actions, and explicit
linkage between invoices and payments. Lifecycle covers
draft → issued → partially paid → paid (or overdue / void / refunded).
Anchored to IFRS / GAAP general principles, PCI DSS for payment data, and
SOX section 404 internal control.
"""

from web.backend.services.domain_methodology.base import (
    AcceptanceScenario,
    ApiEndpoint,
    Capability,
    DomainEntity,
    DomainPack,
    DomainRole,
    EntityField,
    LifecycleState,
    LifecycleTransition,
    ProcessMetric,
    RedFlagPattern,
    Reference,
)


FINANCE_BILLING = DomainPack(
    domain_id="finance_billing",
    label="Finance / Billing",
    description=(
        "Invoices, payments, reconciliation and immutable audit trail. "
        "Honest finance/billing products use double-entry-style records "
        "and never silently mutate posted documents."
    ),
    keywords=(
        "billing", "invoice", "invoicing", "payments", "subscription billing",
        "accounting", "bookkeeping", "reconciliation", "expense tracker", "ledger",
    ),
    categories=("finance", "billing", "accounting"),
    entities=(
        DomainEntity(
            name="invoice",
            fields=(
                EntityField(name="number"),
                EntityField(name="customer"),
                EntityField(name="status"),
                EntityField(name="line_items"),
                EntityField(name="total"),
                EntityField(name="currency"),
                EntityField(name="issued_at"),
                EntityField(name="due_at"),
            ),
        ),
        DomainEntity(
            name="line item",
            aliases=("invoice line",),
            fields=(
                EntityField(name="description"),
                EntityField(name="quantity"),
                EntityField(name="unit_price"),
                EntityField(name="tax", required=False),
            ),
        ),
        DomainEntity(
            name="payment",
            fields=(
                EntityField(name="invoice_id"),
                EntityField(name="amount"),
                EntityField(name="currency"),
                EntityField(name="captured_at"),
                EntityField(name="provider", required=False),
            ),
        ),
        DomainEntity(
            name="customer",
            fields=(EntityField(name="name"), EntityField(name="billing_email")),
        ),
        DomainEntity(
            name="audit log",
            description="Append-only record of monetary changes.",
            aliases=("ledger entry", "audit entry"),
            fields=(
                EntityField(name="entity_type"),
                EntityField(name="entity_id"),
                EntityField(name="actor"),
                EntityField(name="action"),
                EntityField(name="created_at"),
            ),
        ),
        DomainEntity(
            name="tax",
            required=False,
            fields=(EntityField(name="rate"), EntityField(name="jurisdiction"))
        ),
    ),
    roles=(
        DomainRole(name="finance admin", aliases=("billing admin",)),
        DomainRole(name="customer", aliases=("payer",)),
        DomainRole(name="auditor"),
    ),
    capabilities=(
        Capability(id="issue_invoice", label="issue invoice"),
        Capability(id="record_payment", label="record payment"),
        Capability(id="reconcile", label="reconcile invoice with payment"),
        Capability(id="report", label="produce financial report"),
        Capability(id="export_ledger", label="export ledger"),
        Capability(id="audit_log", label="audit log of changes"),
        Capability(id="refund", label="refund", severity="medium"),
    ),
    lifecycle_states=(
        LifecycleState(name="draft", is_initial=True),
        LifecycleState(name="issued", aliases=("posted", "open")),
        LifecycleState(name="partially paid", aliases=("partially_paid",)),
        LifecycleState(name="paid"),
        LifecycleState(name="overdue"),
        LifecycleState(name="void", is_terminal=True, aliases=("voided", "cancelled")),
        LifecycleState(name="refunded", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="draft", to_state="issued"),
        LifecycleTransition(from_state="issued", to_state="partially paid"),
        LifecycleTransition(from_state="issued", to_state="paid"),
        LifecycleTransition(from_state="partially paid", to_state="paid"),
        LifecycleTransition(from_state="issued", to_state="overdue"),
        LifecycleTransition(from_state="paid", to_state="refunded"),
        LifecycleTransition(from_state="issued", to_state="void"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="issue-pay",
            title="Issue invoice and record payment",
            journey_type="core_action",
            steps=(
                "Finance admin issues an invoice with line items",
                "Customer pays full amount",
                "Payment recorded; invoice status='paid'",
                "Audit log captures issue + payment events",
            ),
            expected_outcome="Invoice/payment linked; audit trail complete.",
        ),
        AcceptanceScenario(
            id="partial",
            title="Partial payment leads to 'partially paid'",
            journey_type="edge_case",
            steps=(
                "Customer pays half of invoice",
                "Status moves to 'partially paid'",
                "Remaining balance visible",
            ),
            expected_outcome="Partial payment reflected without overwriting prior records.",
        ),
        AcceptanceScenario(
            id="overdue",
            title="Past due moves invoice to 'overdue'",
            journey_type="operational",
            steps=(
                "Due date passes",
                "Invoice flagged 'overdue'",
                "Reminder sent (or visible on dashboard)",
            ),
            expected_outcome="Overdue handling reportable as DSO contributor.",
        ),
        AcceptanceScenario(
            id="audit",
            title="Auditor exports ledger",
            journey_type="compliance",
            steps=(
                "Auditor signs in",
                "Auditor exports ledger / audit log for a period",
                "Export includes all monetary transitions",
            ),
            expected_outcome="Append-only audit log is exportable.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="POST", path_pattern="/api/invoices", purpose="create invoice"),
        ApiEndpoint(method="POST", path_pattern="/api/invoices/{id}/issue", purpose="issue invoice"),
        ApiEndpoint(method="POST", path_pattern="/api/invoices/{id}/payments", purpose="record payment"),
        ApiEndpoint(method="POST", path_pattern="/api/invoices/{id}/refund", purpose="refund"),
        ApiEndpoint(method="GET", path_pattern="/api/reports/ledger", purpose="ledger export"),
        ApiEndpoint(method="GET", path_pattern="/api/audit/logs", purpose="audit log"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="dso",
            label="days sales outstanding",
            formula="(accounts_receivable / total_credit_sales) * days",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="overdue_balance",
            label="overdue balance",
            formula="sum(invoices where status='overdue')",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="collection_rate",
            label="collection rate",
            formula="paid_amount / issued_amount",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="audit_findings",
            label="audit findings",
            formula="count(audit_findings)",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="mutable_invoices",
            severity="high",
            description="Posted invoices can be silently edited/deleted.",
            keywords=("delete invoice", "edit posted invoice"),
            regex=(r"DELETE\s+/api/invoices/\{id\}",),
            fix_hint="Posted invoices must be append-only; corrections via credit notes / void.",
        ),
        RedFlagPattern(
            id="no_audit",
            severity="high",
            description="No audit log of monetary changes.",
            keywords=("no audit log",),
            fix_hint="Persist append-only audit entries on every monetary action.",
        ),
        RedFlagPattern(
            id="no_payment_link",
            severity="high",
            description="Payments are not linked to invoices.",
            fix_hint="Always link payment records to specific invoices.",
        ),
    ),
    references=(
        Reference(title="IFRS / GAAP general principles"),
        Reference(title="PCI DSS for payment data"),
        Reference(title="SOX Section 404 internal control"),
    ),
    methodology_notes=(
        "Finance/billing is judged by data immutability, audit trail, and "
        "explicit linkage between invoices and payments."
    ),
)
