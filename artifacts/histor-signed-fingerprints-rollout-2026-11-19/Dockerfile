# HISTOR prod host, 2026-11-19: the running image histor-histor:warden-0.31.0-prod (sha256:2604a2f6a4e0…) plus
#   - signed publisher statements (addon_declaration.py, signed_declaration.py; migration 025),
#   - GET /api/v1/fingerprints (fingerprint_profiles.py).
# crawler.py, declared.py, store.py, registry.py, migrations.py as in main (each image file equalled main before
# the change). app.py, check.py and the landing's desk.js + i18n files = the image's own files with only this change
# applied (main's newer journey/Watch UI is not shipped). WARDEN, the observer and the sandbox are untouched.
# On start HISTOR applies migration 025 (two nullable columns on declaration_urls); older images then refuse the
# database until `switch.sh rollback` drops them again.
FROM histor-histor:warden-0.31.0-prod
USER 0:0
COPY --chown=0:0 --chmod=644 ctx/app.py ctx/check.py ctx/crawler.py ctx/declared.py ctx/store.py ctx/registry.py ctx/migrations.py ctx/addon_declaration.py ctx/signed_declaration.py ctx/fingerprint_profiles.py /app/histor/
COPY --chown=0:0 --chmod=644 ctx/desk.js ctx/i18n.js /app/docs/landing/assets/
COPY --chown=0:0 --chmod=644 ctx/i18n/es.js ctx/i18n/fr.js ctx/i18n/ru.js ctx/i18n/zh.js /app/docs/landing/assets/i18n/
LABEL aicom.histor.overlay="signed-fingerprints-20261119" aicom.histor.overlay.commits="@COMMIT@"
USER 65532:65532
RUN python -c "import histor.app, histor.crawler, histor.signed_declaration, histor.addon_declaration, histor.fingerprint_profiles; from histor.migrations import MIGRATIONS; assert MIGRATIONS[-1][0] == 25"
