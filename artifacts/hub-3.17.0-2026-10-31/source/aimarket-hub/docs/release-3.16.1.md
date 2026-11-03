# aimarket-hub 3.16.1

A paid hub call could pass the oracle's signed-admission check but still receive
402 above `free_tier_max`: the hub never supplied `X-AIMarket-Paid-Tier`. This
release addresses goal 6 in the Vulnetix advisory-database issue 5 review.

The hub now selects a separate paid-tier credential for each configured exact
invoke URL after payment or reservation. It supports local providers and paid
federated sales/resales. Free calls, trials and routing-only calls receive no
grant. HTTPS is the default; plaintext routes require an explicit per-endpoint
exception. Credentials do not follow redirects or environment proxies, and
buyer-supplied tier headers are discarded.

Operator setup: [paid-tier credentials](oracle-paid-tier.md). Both the hub and
oracle must be configured; no credentials are bundled with this release.
