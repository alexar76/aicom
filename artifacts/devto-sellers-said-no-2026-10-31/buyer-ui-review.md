# Buyer evidence display review — 2026-10-31

API separates observed offers from admitted catalog matches (`hub_routes/catalog.py`, `_observed_matches` and search response). MCP carries `observed` and an explanatory note (`mcp_gateway.py`).

The terminal currently reads only `d.matches` in `terminal-home.html` and renders them through `renderSearchResults`; it does not render `d.observed`. Thus the next improvement is more than two badges: observed-only results must not be reported as no matches, and observed offers need a separate seller-direct action rather than the sandbox/invoke action used by catalog entries.

Recommended buyer presentation: signed-catalog versus hub-observed evidence; observation time and observer; payment recipient, currency and network; explicit quote-only limit. A signature establishes the signer and signed bytes, not delivery. Do not mark every catalog match as seller-signed without carrying verified per-row evidence: some are local or aggregated by a hub.

No buyer behavior measurement exists for this presentation yet. Avoid promising higher conversion or trust as an established result.

This turn inspected the implementation to answer the user's usefulness question. No hub code or production behavior changed; the separately requested blog publication is complete.
