ARG BASE
FROM ${BASE}
COPY --chown=root:root histor/subject.py histor/labels.py histor/crawler.py histor/store.py /app/histor/
COPY --chown=root:root docs/landing/assets/desk.js /app/docs/landing/assets/desk.js
LABEL aicom.histor.app.commit=8e0763168 aicom.histor.overlay=mtl11-20261031
