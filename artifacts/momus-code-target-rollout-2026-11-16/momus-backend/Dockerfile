# MOMUS reads code (main 37b010c34 + per-finding dedup for code, findings.py): the live momus-backend-hc-live-20261031 plus git (read-only use) and the code
# target. config.py, capabilities.py, targets/__init__.py and engine/remediation.py equalled main before the change.
FROM aicom-security:momus-backend-hc-live-20261031
USER 0:0
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git >/dev/null && rm -rf /var/lib/apt/lists/*
COPY momus/codescan/ /app/momus/momus/codescan/
COPY momus/targets/code.py momus/targets/__init__.py /app/momus/momus/targets/
COPY momus/config.py momus/capabilities.py momus/findings.py /app/momus/momus/
COPY momus/engine/remediation.py /app/momus/momus/engine/
RUN chown -R 0:0 /app/momus/momus/codescan && chmod 755 /app/momus/momus/codescan && chmod 644 /app/momus/momus/codescan/*.py \
    /app/momus/momus/targets/code.py /app/momus/momus/targets/__init__.py /app/momus/momus/config.py \
    /app/momus/momus/capabilities.py /app/momus/momus/findings.py /app/momus/momus/engine/remediation.py
USER 10001:10001
RUN python -c "import momus.capabilities; from momus.targets.code import CodeTarget; import subprocess; subprocess.run(['git','--version'],check=True)"
LABEL aicom.momus.overlay="code-target-20261116" aicom.momus.overlay.commit="37b010c34"
