# SKOPOS conductor (main 6dbfb7fb3): fixer refusals/patches counted for the alerter, and a reviewer's rejection
# recorded (POST /remediation/jobs/{id}/review). The three live files equalled main 37ebe613f before.
FROM aicom-security:skopos-remediation-code-20261116
USER 0:0
COPY --chown=0:0 --chmod=644 conductor.py health.py a2a_ingress.py /app/skopos/remediation/
USER 10001:10001
RUN python -c "from skopos.remediation.health import FLAG_FIXER_REFUSED, FLAG_REVIEW_REJECTED; import skopos.remediation.a2a_ingress; from skopos.remediation.conductor import Conductor; assert hasattr(Conductor, 'reject_branch')"
LABEL aicom.skopos.overlay="code-path-20261116b" aicom.skopos.overlay.commit="6dbfb7fb3"
