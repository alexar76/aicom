# FROM the image HISTOR's tag `latest` points to (the running application's image plus the peer-check modules of
# 2026-11-27); the six files of aicom bd0e37996: the handshake reading kept beside the log, /check same-other-revision.
ARG BASE
FROM ${BASE}
COPY overlay/histor/check.py overlay/histor/config.py overlay/histor/crawler.py overlay/histor/mcpclient.py overlay/histor/migrations.py overlay/histor/store.py /app/histor/
