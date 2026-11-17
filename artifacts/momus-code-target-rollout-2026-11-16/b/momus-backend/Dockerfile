# MOMUS code target, rule update (main 6dbfb7fb3): VX-918-CHECK-THEN-CONNECT also fires on a second, unchecked DNS
# lookup after the check. Only codescan/vulnetix_classes.py changes; the live file equalled main 37ebe613f before.
FROM aicom-security:momus-backend-code-20261116
USER 0:0
COPY --chown=0:0 --chmod=644 vulnetix_classes.py /app/momus/momus/codescan/vulnetix_classes.py
USER 10001:10001
RUN python -c "from momus.codescan.vulnetix_classes import unchecked_resolvers; from momus.targets.code import CodeTarget"
LABEL aicom.momus.overlay="code-target-20261116b" aicom.momus.overlay.commit="6dbfb7fb3"
