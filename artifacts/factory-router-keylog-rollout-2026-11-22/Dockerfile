# Factory app: owner-routing-v1 image (on router-select) with the provider key preview removed from the debug log (aicom main logs only
# whether a key is configured, febbc9fe2); the running router.py with that one hunk.
FROM aicom-security:aicom-app-1-owner-routing-v1
COPY --chown=0:0 --chmod=644 files/llm/router.py /app/llm/router.py
LABEL aicom.factory.overlay="router-keylog-20261122"
