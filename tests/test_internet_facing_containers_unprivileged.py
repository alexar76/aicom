"""An internet-facing container runs as a non-root user with no capabilities.

The public Alien Monitor shares the host's network namespace and holds LLM keys; as root
with default capabilities, a bug in any of its public read APIs is a root shell in the
host's network stack. Its image ends on a non-root USER, and every way it is started —
compose and the bare `docker run` recipe the live containers actually come from — drops
every capability and forbids privilege escalation.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _final_user(dockerfile: Path) -> str | None:
    """The USER in effect for the final stage, or None when the stage never sets one."""
    stage_user = None
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if re.match(r"(?i)^FROM\s", s):
            stage_user = None
        m = re.match(r"(?i)^USER\s+(\S+)", s)
        if m:
            stage_user = m.group(1)
    return stage_user


def _is_root(user: str | None) -> bool:
    return user is None or user.split(":")[0] in ("root", "0")


# (Dockerfile, compose file, service) for every internet-facing service image.
SERVICES = [
    ("alien-monitor/Dockerfile", "alien-monitor/docker-compose.prod.yml", "alien-monitor"),
    ("atlas/Dockerfile", "atlas/docker-compose.yml", "atlas"),
    ("argus/Dockerfile", "argus/docker-compose.yml", "argus"),
    ("argus/Dockerfile", "argus/docker-compose.yml", "argus-uni"),
    ("momus/Dockerfile", "momus/docker-compose.yml", "momus-backend"),
    ("treasury/Dockerfile", "momus/docker-compose.yml", "momus-treasury"),
    ("treasury/Dockerfile", "treasury/docker-compose.yml", "momus-treasury"),
    ("oracles/oracles/chronos/Dockerfile", "oracles/docker-compose.yml", "chronos"),
    ("oracles/oracles/oracle-family/Dockerfile", "oracles/docker-compose.yml", "oracle-family"),
    ("platon/backend/Dockerfile", "platon/docker-compose.yml", "platon-backend"),
    ("gaia/Dockerfile", "gaia/docker-compose.yml", "gaia-backend"),
    ("skopos/Dockerfile", "skopos/docker-compose.yml", "skopos"),
    ("Dockerfile.remediation-fix", "docker-compose.remediation-fix.yml", "remediation-fixer"),
    ("cite-desks/kernel/Dockerfile", "cite-desks/tideline/docker-compose.yml", "api"),
    ("cite-desks/kernel/Dockerfile", "cite-desks/seamark/docker-compose.yml", "api"),
    ("cite-desks/kernel/Dockerfile", "cite-desks/solrecord/docker-compose.yml", "api"),
    ("cite-desks/kernel/Dockerfile", "cite-desks/plinth/docker-compose.yml", "api"),
    ("cite-desks/kernel/Dockerfile", "cite-desks/smokeproof/docker-compose.yml", "api"),
    ("cite-desks/emberline/backend/Dockerfile", "cite-desks/emberline/docker-compose.yml", "api"),
]
# Images without a compose service of their own in the tree (built by the MOMUS deploy).
EXTRA_IMAGES = ["praxis/Dockerfile", "momus/canary/Dockerfile", "skopos/Dockerfile.remediation"]


@pytest.mark.parametrize("dockerfile", sorted({d for d, _, _ in SERVICES} | set(EXTRA_IMAGES)))
def test_the_image_ends_on_a_non_root_user(dockerfile):
    assert not _is_root(_final_user(ROOT / dockerfile)), f"{dockerfile} runs its service as root"


@pytest.mark.parametrize("compose,service", [(c, s) for _, c, s in SERVICES])
def test_compose_drops_every_capability(compose, service):
    doc = yaml.safe_load((ROOT / compose).read_text(encoding="utf-8"))
    svc = doc["services"][service]
    assert not _is_root(str(svc.get("user") or "") or None), f"{compose}:{service} runs as root"
    assert svc.get("cap_drop") == ["ALL"], f"{compose}:{service} keeps default capabilities"
    assert "no-new-privileges:true" in (svc.get("security_opt") or []), f"{compose}:{service}"


def test_the_live_recipe_drops_every_capability():
    text = (ROOT / "scripts" / "redeploy_alien_monitor_live.sh").read_text(encoding="utf-8")
    run = text[text.index("docker run -d"):]
    run = run[: run.index('"$TAG"')]
    assert "--cap-drop ALL" in run
    assert "--security-opt no-new-privileges:true" in run
    m = re.search(r"--user (\S+)", run)
    assert m and not _is_root(m.group(1))
