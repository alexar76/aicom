# Remediation fixer (main 6dbfb7fb3): per-rule fix guides from the checkout of main, and the finding's rule run on the
# rewrite before a push. remediation_fix.py equalled main 37ebe613f before; remediation_code_guides.py is new.
FROM aicom-security:remediation-fixer-code-20261116
USER 0:0
COPY --chown=0:0 --chmod=644 remediation_fix.py remediation_code_guides.py /app/web/backend/services/
USER 10001:10001
RUN cd /app && python -c "from web.backend.services import remediation_code_guides as g; assert g.rule_and_function({'blame': {'summary': 'a.py: VX-FWD-HEADER-TRUST in f - x'}}) == ('VX-FWD-HEADER-TRUST', 'f')"
LABEL aicom.fixer.overlay="code-scope-20261116b" aicom.fixer.overlay.commit="6dbfb7fb3"
