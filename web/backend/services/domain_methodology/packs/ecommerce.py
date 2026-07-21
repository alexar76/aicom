"""
E-commerce domain methodology pack.

Operationally honest e-commerce tracks inventory, captures money, and ships
orders against a state machine (draft → pending payment → paid → fulfilling →
shipped → delivered, with cancelled/refunded as terminal exits). Red flags
include "no cart", "no payment step" and "infinite stock". Grounded in
Stripe / Shopify checkout patterns and OWASP ASVS for payment data.
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


ECOMMERCE = DomainPack(
    domain_id="ecommerce",
    label="E-commerce",
    description=(
        "Storefront with catalog, cart, checkout, orders, payments and refunds. "
        "Operationally honest e-commerce tracks inventory, captures money, and "
        "ships orders against a state machine."
    ),
    keywords=(
        "ecommerce", "e-commerce", "online store", "shop", "storefront", "cart",
        "checkout", "marketplace seller", "product catalog", "order management",
    ),
    categories=("ecommerce", "retail", "marketplace"),
    entities=(
        DomainEntity(
            name="product",
            description="Item offered for sale.",
            aliases=("sku", "listing", "item"),
            fields=(
                EntityField(name="title", aliases=("name",)),
                EntityField(name="price"),
                EntityField(name="currency"),
                EntityField(name="stock", aliases=("inventory", "quantity")),
                EntityField(name="status"),
                EntityField(name="images", required=False),
            ),
        ),
        DomainEntity(
            name="category",
            aliases=("collection",),
            fields=(EntityField(name="name"), EntityField(name="slug")),
        ),
        DomainEntity(
            name="cart",
            description="Active shopping cart linked to a buyer / session.",
            fields=(
                EntityField(name="buyer_id", aliases=("customer_id", "user_id")),
                EntityField(name="items", aliases=("line_items",)),
                EntityField(name="subtotal"),
            ),
        ),
        DomainEntity(
            name="order",
            description="Captured intent to purchase, with payment + fulfilment.",
            fields=(
                EntityField(name="status", aliases=("state",)),
                EntityField(name="customer"),
                EntityField(name="line_items"),
                EntityField(name="total"),
                EntityField(name="currency"),
                EntityField(name="payment_id", required=False),
                EntityField(name="shipping_address", required=False),
            ),
        ),
        DomainEntity(
            name="payment",
            description="Money capture/refund record.",
            aliases=("transaction",),
            fields=(
                EntityField(name="order_id"),
                EntityField(name="amount"),
                EntityField(name="status"),
                EntityField(name="provider", required=False),
            ),
        ),
        DomainEntity(
            name="customer",
            aliases=("buyer", "user"),
            fields=(EntityField(name="email"), EntityField(name="addresses", required=False)),
        ),
    ),
    roles=(
        DomainRole(name="buyer", aliases=("customer", "shopper")),
        DomainRole(name="merchant", aliases=("seller", "store admin", "merchant admin")),
        DomainRole(name="admin", required=False, aliases=("platform admin",)),
    ),
    capabilities=(
        Capability(id="browse", label="browse and search catalog", aliases=("filter products",)),
        Capability(id="add_to_cart", label="add to cart"),
        Capability(id="checkout", label="checkout"),
        Capability(id="place_order", label="place order"),
        Capability(id="track_status", label="track order status"),
        Capability(id="manage_inventory", label="manage inventory", aliases=("update stock",)),
        Capability(id="refund", label="issue refund"),
        Capability(id="cancel_order", label="cancel order", severity="medium"),
    ),
    lifecycle_states=(
        LifecycleState(name="draft", is_initial=True, aliases=("cart",)),
        LifecycleState(name="pending payment", aliases=("awaiting payment", "pending_payment")),
        LifecycleState(name="paid"),
        LifecycleState(name="fulfilling", aliases=("processing", "in_fulfilment")),
        LifecycleState(name="shipped"),
        LifecycleState(name="delivered", is_terminal=True),
        LifecycleState(name="refunded", is_terminal=True),
        LifecycleState(name="cancelled", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="draft", to_state="pending payment", label="checkout"),
        LifecycleTransition(from_state="pending payment", to_state="paid"),
        LifecycleTransition(from_state="pending payment", to_state="cancelled"),
        LifecycleTransition(from_state="paid", to_state="fulfilling"),
        LifecycleTransition(from_state="paid", to_state="refunded"),
        LifecycleTransition(from_state="fulfilling", to_state="shipped"),
        LifecycleTransition(from_state="shipped", to_state="delivered"),
        LifecycleTransition(from_state="shipped", to_state="refunded"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="buy-flow",
            title="Buyer purchases an in-stock product",
            journey_type="core_action",
            steps=(
                "Buyer browses catalog and opens product",
                "Buyer adds product to cart",
                "Buyer checks out and pays",
                "Order moves through paid -> shipped -> delivered",
            ),
            expected_outcome="Order persisted with payment, inventory decremented.",
        ),
        AcceptanceScenario(
            id="out-of-stock",
            title="Out-of-stock product blocks purchase",
            journey_type="edge_case",
            steps=(
                "Catalog shows product as out of stock",
                "Add to cart is disabled or order is rejected",
            ),
            expected_outcome="Inventory rule prevents overselling.",
        ),
        AcceptanceScenario(
            id="refund",
            title="Merchant refunds a delivered order",
            journey_type="recovery",
            steps=(
                "Merchant opens order and triggers refund",
                "Payment record reflects refund",
                "Order status moves to 'refunded'",
            ),
            expected_outcome="Refund tracked end-to-end with order + payment update.",
        ),
        AcceptanceScenario(
            id="cancel-pending",
            title="Cancel an unpaid order",
            journey_type="edge_case",
            steps=(
                "Buyer or merchant cancels an order in 'pending payment'",
                "Inventory is released",
                "Order status moves to 'cancelled'",
            ),
            expected_outcome="No payment captured; inventory restored.",
        ),
        AcceptanceScenario(
            id="report",
            title="Merchant sees daily revenue and order status mix",
            journey_type="reporting",
            severity="medium",
            steps=(
                "Merchant opens dashboard",
                "Dashboard shows revenue, AOV, refunds, status breakdown",
            ),
            expected_outcome="KPIs are present and reflect the order data.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="GET", path_pattern="/api/products", purpose="list catalog"),
        ApiEndpoint(method="POST", path_pattern="/api/cart/items", purpose="add to cart"),
        ApiEndpoint(method="POST", path_pattern="/api/checkout", purpose="checkout"),
        ApiEndpoint(method="POST", path_pattern="/api/orders", purpose="place order"),
        ApiEndpoint(method="GET", path_pattern="/api/orders/{id}", purpose="order details"),
        ApiEndpoint(method="POST", path_pattern="/api/orders/{id}/refund", purpose="refund order"),
        ApiEndpoint(method="POST", path_pattern="/api/payments", purpose="capture payment", severity="high"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="conv_rate",
            label="conversion rate",
            formula="orders / sessions",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="cart_abandon",
            label="cart abandonment",
            formula="abandoned_carts / total_carts",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="aov",
            label="average order value",
            formula="sum(order_total) / count(orders)",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="refund_rate",
            label="refund rate",
            formula="refunded_orders / total_orders",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="no_cart",
            severity="high",
            description="Storefront with no cart or order entity.",
            keywords=("contact us to buy", "request quote",),
            regex=(r"\bno\s+cart\b",),
            fix_hint="Add cart and order entities with line items.",
        ),
        RedFlagPattern(
            id="no_payment_step",
            severity="high",
            description="No payment capture step before order is fulfilled.",
            keywords=("free demo only", "no payments"),
            regex=(r"\bno\s+payment\b",),
            fix_hint="Add a payment step that gates fulfilment.",
        ),
        RedFlagPattern(
            id="no_inventory",
            severity="medium",
            description="No inventory / stock concept; products always orderable.",
            keywords=("infinite stock", "no inventory"),
            fix_hint="Track stock per product / variant and respect it on checkout.",
        ),
    ),
    references=(
        Reference(title="Stripe / Shopify checkout best practices"),
        Reference(title="ISO 8601 / RFC 7159 — order/payment data interop"),
        Reference(title="OWASP ASVS — payment / PII handling"),
    ),
    methodology_notes=(
        "E-commerce is judged on real cart / order lifecycle, payment capture, "
        "inventory honesty, and refund / cancel pathways."
    ),
)
