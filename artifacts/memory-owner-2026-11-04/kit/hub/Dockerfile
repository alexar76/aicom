ARG BASE
FROM ${BASE}
# Buyer-owner fix 2026-11-04: X-AIMarket-Buyer-Ref to the operator's own providers (provider_buyer_ref.py).
COPY provider_buyer_ref.py /app/aimarket_hub/provider_buyer_ref.py
COPY invoke.py /app/aimarket_hub/hub_routes/invoke.py
