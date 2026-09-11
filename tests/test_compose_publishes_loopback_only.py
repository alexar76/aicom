"""No compose file may publish an unauthenticated service to every interface.

The `app` service already states the rule, and the reason:

    ports:
      # Localhost-only — public traffic via nginx :80/:443 (Docker bypasses UFW).
      - "127.0.0.1:${AICOM_PORT_FRONTEND:-9080}:8080"

"Docker bypasses UFW" is the whole point: a published port is a DNAT rule, so a host
firewall policy does not cover it and no script in scripts/ or deploy/ installs a
DOCKER-USER rule. Three services published on 0.0.0.0 anyway:

* prometheus — runs with no `--web.config.file`, so it has no authentication of its own.
  scripts/deploy_observability.sh writes /etc/nginx/.htpasswd-prometheus and patches in an
  auth_basic snippet, i.e. nginx is the ONLY access control there is; the 0.0.0.0 publish
  goes straight past it. Prometheus is world-readable metrics for the whole ecosystem.
* grafana — same publish, same reasoning.
* postgres in docker-compose.pg.yml — and docker-compose.prod.yml publishes the same
  service as `127.0.0.1:${POSTGRES_PORT:-5432}:5432`, so the two overlays disagreed on one
  decision. The app reaches postgres by service name over aicom_net; the host publish is
  not needed at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class _ComposeLoader(yaml.SafeLoader):
    """Compose files carry `!reset`-style tags in places; ignore them."""


_ComposeLoader.add_multi_constructor(
    "", lambda loader, suffix, node: None  # noqa: ARG005
)

#: Files whose publishes must all be loopback-scoped, and why they are in scope:
#: these are the ones an operator is documented to run on a public VPS.
_FILES = ["docker-compose.yml", "docker-compose.pg.yml"]

#: Services allowed to publish on every interface, with the reason. nginx/edge services
#: are the intended public door; everything else goes through them.
_PUBLIC_BY_DESIGN: set[str] = set()


def _services(name: str) -> dict:
    path = ROOT / name
    if not path.is_file():
        pytest.skip(f"{name} not present")
    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}
    return doc.get("services") or {}


@pytest.mark.parametrize("compose_file", _FILES)
def test_every_published_port_is_bound_to_loopback(compose_file):
    offenders: list[tuple[str, str]] = []
    for service, spec in _services(compose_file).items():
        if service in _PUBLIC_BY_DESIGN or not isinstance(spec, dict):
            continue
        for entry in spec.get("ports") or []:
            if not isinstance(entry, str):
                # Long-form {target, published, host_ip} — check host_ip when given.
                if isinstance(entry, dict) and entry.get("host_ip") not in (
                    "127.0.0.1", "::1", "localhost"
                ):
                    offenders.append((service, str(entry)))
                continue
            # A published mapping either starts with an interface, or it is every one.
            if not entry.startswith(("127.0.0.1:", "::1:", "localhost:", "${ECO_BIND")):
                offenders.append((service, entry))
    assert not offenders, (
        f"{compose_file} publishes these to every interface, past nginx and past UFW: "
        f"{offenders}"
    )


def test_the_two_overlays_agree_about_postgres():
    """They published the same service two different ways, which is how one gets missed."""
    pg = _services("docker-compose.pg.yml").get("postgres") or {}
    prod = _services("docker-compose.prod.yml").get("postgres") or {}
    pg_ports = [p for p in (pg.get("ports") or []) if isinstance(p, str)]
    prod_ports = [p for p in (prod.get("ports") or []) if isinstance(p, str)]
    if not pg_ports or not prod_ports:
        pytest.skip("one of the overlays no longer publishes postgres")
    assert all(p.startswith("127.0.0.1:") for p in pg_ports), pg_ports
    assert all(p.startswith("127.0.0.1:") for p in prod_ports), prod_ports
