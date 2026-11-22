# Factory app: the image the host compose pins (routing-rules save fix 8242d71dc, on search20) with llm/router.py
# selecting the routing rule's provider before the default provider (aicom 4f86b3819, applied to the running file:
# the same hunks; the running router is older than main and is otherwise unchanged).
FROM aicom-security:aicom-app-1-routing-save-8242d71dc
COPY --chown=0:0 --chmod=644 files/llm/router.py /app/llm/router.py
LABEL aicom.factory.overlay="router-provider-select-20261122" skopos.source.commit="4f86b3819"
