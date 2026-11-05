# attested hub: the running image plus the routed-call fix for X-AIMarket-Buyer-Ref (2026-11-05).
# provider_buyer_ref.py = repo bbe3dad45 (live file was the repo's bbe3dad45^); invoke.py = the LIVE file plus
# two edits (the _Call field and its value), because the live invoke.py differs from the repo.
FROM attested-memory-hub:cf-20261104
USER root
COPY provider_buyer_ref.py /app/aimarket_hub/provider_buyer_ref.py
COPY invoke.py /app/aimarket_hub/hub_routes/invoke.py
RUN chmod 644 /app/aimarket_hub/provider_buyer_ref.py /app/aimarket_hub/hub_routes/invoke.py
USER hub:hub
