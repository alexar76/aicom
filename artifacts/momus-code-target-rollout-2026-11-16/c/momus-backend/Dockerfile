# MOMUS code target, rules from outside advisories (main 443f0f422): VX-295-TLS-OFF, VX-918-FETCH-UNCHECKED,
# VX-918-REDIRECT-AFTER-CHECK, VX-306-ROUTE-NO-AUTH. Two files change; the live ones equalled main 443f0f422^.
FROM aicom-security:momus-backend-code-20261116b
USER 0:0
COPY --chown=0:0 --chmod=644 vulnetix_classes.py /app/momus/momus/codescan/vulnetix_classes.py
COPY --chown=0:0 --chmod=644 code.py /app/momus/momus/targets/code.py
USER 10001:10001
RUN python -c "from momus.codescan.vulnetix_classes import scan_file, scan_js; from momus.targets.code import CodeTarget, RULES; assert 'VX-295-TLS-OFF' in RULES; assert scan_file('a.py', 'import requests\nrequests.get(u, verify=False)\n')"
LABEL aicom.momus.overlay="code-target-20261117" aicom.momus.overlay.commit="443f0f422"
