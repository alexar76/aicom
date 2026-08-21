"""`./start.sh` must work for someone who cloned the PUBLIC repo.

The mirror at github.com/alexar76/aicom ships start.sh and docker-compose.core.yml but
strips the satellite build contexts those files reference, because each satellite is
published as its own repository. For a while the headline command in the README therefore
failed for every stranger who ran it — `docker compose build` could not find
aimarket-hub/Dockerfile — while working perfectly in the monorepo, so the operator never
saw it.

The guard in start.sh degrades to the tier that is actually present. These tests pin the
part that rots: the guard and the compose file have to stay in agreement, and a fourth
service added to the core tier must not silently reintroduce the hard failure.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from aicom_publish_config import factory_exclude_paths  # noqa: E402

START_SH = ROOT / "start.sh"
CORE_COMPOSE = ROOT / "docker-compose.core.yml"
BASE_COMPOSE = ROOT / "docker-compose.yml"


def _build_dockerfiles(compose_path: Path) -> set[str]:
    """Every Dockerfile a compose file needs, as a repo-relative path.

    Deliberately a regex rather than a YAML load: this must run in the root suite with no
    third-party imports, and the shapes in use are only `context:` + `dockerfile:`.
    """
    text = compose_path.read_text(encoding="utf-8")
    found: set[str] = set()
    for block in re.finditer(
        r"build:\s*\n\s+context:\s*(\S+)\s*\n\s+dockerfile:\s*(\S+)", text
    ):
        context, dockerfile = block.group(1).strip(), block.group(2).strip()
        context = context.lstrip("./").rstrip("/")
        found.add(f"{context}/{dockerfile}" if context and context != "." else dockerfile)
    return found


def _guarded_paths() -> set[str]:
    """The Dockerfiles start.sh checks for before choosing a tier."""
    text = START_SH.read_text(encoding="utf-8")
    return set(re.findall(r'\[\[ -f "\$ROOT/(\S+?)" \]\]', text))


def test_core_compose_still_declares_the_builds_we_think_it_does():
    assert _build_dockerfiles(CORE_COMPOSE) == {
        "aimarket-hub/Dockerfile",
        "ai-service-mesh/backend/Dockerfile",
        "alien-monitor/Dockerfile",
    }


def test_every_core_build_context_is_guarded():
    """A service added to the core tier without a guard brings the hard failure back."""
    unguarded = _build_dockerfiles(CORE_COMPOSE) - _guarded_paths()
    assert not unguarded, (
        f"docker-compose.core.yml builds {sorted(unguarded)}, which start.sh never checks "
        f"for — a public clone missing it dies on 'Dockerfile not found' again"
    )


def test_the_guard_matches_what_the_public_mirror_actually_strips():
    """Guarding a path the mirror ships is dead code; not guarding a stripped one is the bug."""
    stripped = set(factory_exclude_paths())
    for dockerfile in _build_dockerfiles(CORE_COMPOSE):
        top = dockerfile.split("/", 1)[0]
        assert top in stripped, (
            f"{top} is no longer stripped from the public mirror — if it now ships, the "
            f"guard in start.sh is dead code and this test should be updated with it"
        )


def test_the_fallback_tier_only_needs_files_the_mirror_ships():
    """Falling back to a tier that is also stripped would just move the failure."""
    stripped = set(factory_exclude_paths())
    for dockerfile in _build_dockerfiles(BASE_COMPOSE):
        top = dockerfile.split("/", 1)[0]
        assert top not in stripped, (
            f"the fallback compose builds {dockerfile}, but {top} is stripped from the mirror"
        )
    assert (ROOT / "Dockerfile").is_file(), "the fallback builds the root Dockerfile"


def test_the_fallback_drops_the_core_overlay():
    """It must stop composing the overlay whose contexts are missing, not merely warn."""
    text = START_SH.read_text(encoding="utf-8")
    fallback = re.search(r"if \(\( \$\{#missing_ctx\[@\]\} \)\); then\n(.*?)\nfi\n",
                         text, re.DOTALL)
    assert fallback, "the degradation branch is gone"
    body = fallback.group(1)
    assert "COMPOSE=(docker compose -f docker-compose.yml)" in body
    assert "docker-compose.core.yml" not in body


def test_the_fallback_points_somewhere_that_works():
    """A stranger whose stack shrank should be told where the whole thing is reachable."""
    body = START_SH.read_text(encoding="utf-8")
    assert "https://modelmarket.dev/mcp" in body
    assert "hosted-mcp-endpoint.md" in body


def test_start_sh_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(START_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("doc", ["README.md", "docs/README.md"])
def test_the_hosted_endpoint_is_advertised_where_strangers_land(doc):
    """The zero-install path is the one thing that works from any clone, broken or not."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert "https://modelmarket.dev/mcp" in text, f"{doc} does not mention the hosted endpoint"
