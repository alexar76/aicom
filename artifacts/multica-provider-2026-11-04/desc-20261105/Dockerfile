# Multica provider: the running image plus the where-to-buy note in both digest descriptions (owner, 2026-11-05).
# app.py = repo multica/provider/src/multica_provider/app.py; the live file was the repo's previous version (6ce6a3aa536d…).
FROM multica-provider:20261104b
USER root
COPY app.py /usr/local/lib/python3.12/site-packages/multica_provider/app.py
RUN chmod 644 /usr/local/lib/python3.12/site-packages/multica_provider/app.py
USER app
