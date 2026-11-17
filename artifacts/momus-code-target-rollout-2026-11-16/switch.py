#!/usr/bin/env python3
"""Switch admin-vps to MOMUS-reads-code (2026-11-16). `switch.py` applies, `switch.py rollback` restores the backups.

Edits, each asserted to match exactly once:
  /root/momus-deploy/docker-compose.prod.yml   momus-backend: image, Gitea repo mounted read-only at /code/aicom.git,
                                               MOMUS_EXTRA_TARGETS += aicom-source|file:///code/aicom.git|code;
                                               skopos-remediation: image
  /root/aicom/docker-compose.remediation-fix.yml  remediation-fixer: image, code areas, code root (/code-src = fresh main)
  /etc/skopos-autopilot.env                     policy += aicom-source (high, medium; 2 sightings); per-component cap 3 -> 7
                                               and daily cap 8 -> 14 FOR THE PROVING RUN (restore with `caps-restore`)
Then recreates the three containers (--no-deps) and restarts skopos-autopilot."""
import json, re, shutil, subprocess, sys, time
from pathlib import Path

KIT = Path("/root/momus-code-rollout-20261116")
MOMUS_COMPOSE = Path("/root/momus-deploy/docker-compose.prod.yml")
FIX_COMPOSE = Path("/root/aicom/docker-compose.remediation-fix.yml")
AUTOPILOT_ENV = Path("/etc/skopos-autopilot.env")
REPO = "/var/lib/docker/volumes/gitea_gitea-data/_data/git/repositories/alexar76/aicom.git"
FILES = [MOMUS_COMPOSE, FIX_COMPOSE, AUTOPILOT_ENV]


def bak(p: Path) -> Path:
    return KIT / (p.name + ".pre")


def once(text: str, old: str, new: str, where: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"{where}: expected 1 match, found {n}: {old[:80]!r}")
    return text.replace(old, new)


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def recreate() -> None:
    run("docker", "compose", "-p", "momus-deploy", "-f", str(MOMUS_COMPOSE), "up", "-d", "--no-deps",
        "momus-backend", "skopos-remediation")
    run("docker", "compose", "-p", "aicom", "-f", str(FIX_COMPOSE), "up", "-d", "--no-deps", "remediation-fixer")
    run("systemctl", "restart", "skopos-autopilot.service")


def apply() -> None:
    for p in FILES:
        if bak(p).exists():
            sys.exit(f"backup {bak(p)} exists — already switched? (rollback first)")
    for p in FILES:
        shutil.copy2(p, bak(p))
    m = MOMUS_COMPOSE.read_text()
    m = once(m, "    image: aicom-security:momus-backend-hc-live-20261031  # Verified security rollout 2026-10-31",
             "    image: aicom-security:momus-backend-code-20261116  # MOMUS reads code (main 37b010c34); "
             f"rollback: {KIT}/switch.py rollback", "momus image")
    m = once(m, "      MOMUS_EXTRA_TARGETS: canary|http://momus-canary:9450|oracle,praxis|http://praxis:9460|oracle,"
                "warden|https://histor.modelmarket.dev|quality\n",
             "      MOMUS_EXTRA_TARGETS: canary|http://momus-canary:9450|oracle,praxis|http://praxis:9460|oracle,"
             "warden|https://histor.modelmarket.dev|quality,aicom-source|file:///code/aicom.git|code\n", "targets")
    m = once(m, "    - momus-scanner-keys:/data\n",
             f"    - momus-scanner-keys:/data\n    - {REPO}:/code/aicom.git:ro\n", "momus volume")
    m = once(m, "    image: aicom-security:skopos-remediation-hc-live-20261031  # Verified security rollout 2026-10-31",
             "    image: aicom-security:skopos-remediation-code-20261116  # code findings path (main 37b010c34); "
             f"rollback: {KIT}/switch.py rollback", "skopos image")
    MOMUS_COMPOSE.write_text(m)
    f = FIX_COMPOSE.read_text()
    f = once(f, "    image: aicom-security:remediation-fixer-hc-live-20261031  # Verified security rollout 2026-10-31",
             "    image: aicom-security:remediation-fixer-code-20261116  # code scope (main 57e61c8cd); "
             f"rollback: {KIT}/switch.py rollback", "fixer image")
    f = once(f, "      AIFACTORY_REMEDIATION_SCOPE: ${AIFACTORY_REMEDIATION_SCOPE:-}\n",
             "      AIFACTORY_REMEDIATION_SCOPE: ${AIFACTORY_REMEDIATION_SCOPE:-}\n"
             "      AIFACTORY_REMEDIATION_CODE_AREAS: ai-service-mesh,plugins,metis,web\n"
             "      AIFACTORY_REMEDIATION_CODE_ROOT: /code-src\n", "fixer env")
    f = once(f, "    - /root/aicom:/app-src:ro\n",
             "    - /root/aicom:/app-src:ro\n    - /srv/momus-code/aicom:/code-src:ro\n", "fixer volume")
    FIX_COMPOSE.write_text(f)
    a = AUTOPILOT_ENV.read_text()
    pol = re.search(r"^AUTOPILOT_POLICY=(.*)$", a, re.M)
    policy = json.loads(pol.group(1))
    policy["aicom-source"] = {"severities": ["critical", "high", "medium"], "min_sightings": 2}
    a = a.replace(pol.group(0), "AUTOPILOT_POLICY=" + json.dumps(policy))
    a = once(a, "AUTOPILOT_MAX_PER_COMPONENT_PER_DAY=3\n", "AUTOPILOT_MAX_PER_COMPONENT_PER_DAY=7\n", "cap/component")
    a = once(a, "AUTOPILOT_MAX_PER_DAY=8\n", "AUTOPILOT_MAX_PER_DAY=14\n", "cap/day")
    a = once(a, "AUTOPILOT_SCAN_ROTA=praxis,canary,gaia,hub,oracles,warden\n",
             "AUTOPILOT_SCAN_ROTA=praxis,canary,gaia,hub,oracles,warden,aicom-source\n", "scan rota")
    AUTOPILOT_ENV.write_text(a)
    recreate()


def rollback() -> None:
    for p in FILES:
        if bak(p).exists():
            shutil.copy2(bak(p), p)
            bak(p).rename(bak(p).with_suffix(f".rolledback-{int(time.time())}"))
    recreate()


def caps_restore() -> None:
    a = AUTOPILOT_ENV.read_text()
    a = once(a, "AUTOPILOT_MAX_PER_COMPONENT_PER_DAY=7\n", "AUTOPILOT_MAX_PER_COMPONENT_PER_DAY=3\n", "cap/component")
    a = once(a, "AUTOPILOT_MAX_PER_DAY=14\n", "AUTOPILOT_MAX_PER_DAY=8\n", "cap/day")
    AUTOPILOT_ENV.write_text(a)
    run("systemctl", "restart", "skopos-autopilot.service")


if __name__ == "__main__":
    {"rollback": rollback, "caps-restore": caps_restore}.get(sys.argv[1] if len(sys.argv) > 1 else "", apply)()
