# SKOPOS conductor: code findings are pushed as a fix branch, gated by MOMUS on that branch, closed without build,
# deploy or auto-merge (main 37b010c34). conductor.py and health.py equalled main before the change; the bundled MOMUS
# engine/remediation.py is the image's own copy with only that commit's diff applied (code:<area> routing).
FROM aicom-security:skopos-remediation-hc-live-20261031
USER 0:0
COPY --chown=0:0 --chmod=644 skopos/conductor.py skopos/health.py /app/skopos/remediation/
COPY --chown=0:0 --chmod=644 momus/remediation.py /app/momus/momus/engine/remediation.py
USER 10001:10001
RUN python -c "import skopos.remediation.conductor as c; assert c.is_code_component('code:x'); from momus.engine.remediation import escalation_for as e; assert e('code:skopos') == 'human-governance'"
LABEL aicom.skopos.overlay="code-path-20261116" aicom.skopos.overlay.commit="37b010c34"
