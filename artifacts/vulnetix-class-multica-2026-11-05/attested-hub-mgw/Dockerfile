# attested hub: the running image plus the public-manifest address fix (published_invoke_url), 2026-11-05.
# catalog.py = the LIVE file (sha256 a4b259587d17…) plus the function from repo bbe3dad45 and one manifest line.
FROM attested-memory-hub:rbh-20261105
USER root
COPY catalog.py /app/aimarket_hub/hub_routes/catalog.py
RUN chmod 644 /app/aimarket_hub/hub_routes/catalog.py
USER hub:hub
