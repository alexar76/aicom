# Remediation fixer: code findings may patch the one file named in the MOMUS-signed Blame title, for enabled areas,
# reading source from AIFACTORY_REMEDIATION_CODE_ROOT (main 05857acb7, 57e61c8cd). The live file equalled main before.
FROM aicom-security:remediation-fixer-hc-live-20261031
USER 0:0
COPY --chown=0:0 --chmod=644 remediation_fix.py /app/web/backend/services/remediation_fix.py
USER 10001:10001
RUN cd /app && python -c "from web.backend.services import remediation_fix as r; assert r.code_scope({'component':'code:x'}) == []"
LABEL aicom.fixer.overlay="code-scope-20261116" aicom.fixer.overlay.commit="57e61c8cd"
