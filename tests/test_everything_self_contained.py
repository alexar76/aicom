"""The `everything` tier must not call our production.

The tier's promise is a stack that runs entirely on the operator's own machine. A container in it that
reaches `magic-ai-factory.com` fails twice: the operator sees our production instead of the thing they
just started, and we collect their traffic.

**The hole this guards.** Every `[domain-override]` in `docker-compose.everything.yml` was already
correct, and the compose files contained no production host — yet the RESOLVED config did, in two
services. The route was `env_file: .env`: compose hands such a service *every* key in the operator's
`.env`, including values left over from a production deploy or copied out of `.env.vps.example`. So
`app` and `grafana` carried our arena URL while both compose files looked clean.

**Two layers, and this file guards both because neither is sufficient alone.**

1. *Pinning* (tested here). Each service inheriting `.env` must set the risky variables explicitly, so
   the resolved config is clean whatever the operator's `.env` says. The risk set is derived from
   `.env.vps.example` — add a production variable to that template and this test immediately demands a
   pin — plus `ALSO_PINNED`, which exists because the two variables that actually leaked were never in
   the template at all. They came from a developer `.env`. Deriving the set from the template alone
   would not have caught the real bug, and pretending otherwise would make this file decorative.

2. *The rule* (existence-tested here). `scripts/everything.sh` resolves the merged config at startup and
   refuses to start if any of our hosts survive. That is what catches variable number three, the one
   nobody has thought of yet. A list of known-bad names cannot do that, which is exactly why the check
   in the launcher must not be deleted as redundant with this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

#: Hosts that belong to us. A container in this tier must never be pointed at one.
OUR_HOSTS = ("magic-ai-factory.com", "modelmarket.dev")

#: Variables that leaked in practice and are absent from every template — see the module docstring.
#: They live in developer and prod-operator `.env` files, which is precisely why no template scan
#: finds them.
ALSO_PINNED = ("ALIEN_PUBLIC_ARGUS_URL", "ARGUS_PUBLIC_URL")


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that tolerates compose's merge tags (`!override`, `!reset`).

    They are compose directives about how to merge, not data. PyYAML refuses unknown tags outright, so
    without this the whole file fails to parse and every test below errors at collection — which reads
    like a broken test file rather than a missing loader.
    """


_ComposeLoader.add_multi_constructor(
    "!", lambda loader, suffix, node: (
        loader.construct_sequence(node, deep=True) if isinstance(node, yaml.SequenceNode)
        else loader.construct_mapping(node, deep=True) if isinstance(node, yaml.MappingNode)
        else loader.construct_scalar(node)))


def _load(name: str) -> dict:
    return yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}


def _env_map(service: dict) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, list):  # both compose spellings are legal
        out = {}
        for item in env:
            k, _, v = str(item).partition("=")
            out[k] = v
        return out
    return {str(k): str(v) for k, v in env.items()}


def _inherits_dotenv(service: dict) -> bool:
    ef = service.get("env_file")
    if not ef:
        return False
    entries = [ef] if isinstance(ef, str) else ef
    for e in entries:
        path = e if isinstance(e, str) else str(e.get("path", ""))
        if Path(path).name == ".env":
            return True
    return False


def _risk_variables() -> set[str]:
    """Variable names a production `.env` is known to carry pointing at one of our hosts."""
    names = set(ALSO_PINNED)
    template = ROOT / ".env.vps.example"
    if template.is_file():
        for line in template.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if any(h in value for h in OUR_HOSTS):
                names.add(name.strip())
    return names


def _services_inheriting_dotenv() -> dict[str, dict]:
    """Merged view of base + overlay, for services that take `env_file: .env`."""
    base = _load("docker-compose.yml").get("services") or {}
    over = _load("docker-compose.everything.yml").get("services") or {}
    merged: dict[str, dict] = {}
    for name, svc in base.items():
        svc = svc or {}
        if not _inherits_dotenv(svc):
            continue
        env = _env_map(svc)
        env.update(_env_map(over.get(name) or {}))  # overlay wins, as compose merges it
        merged[name] = env
    return merged


def test_the_tier_has_services_that_inherit_dotenv() -> None:
    """If this ever becomes empty the tests below pass vacuously, which would be worse than failing."""
    assert _services_inheriting_dotenv(), (
        "no service takes `env_file: .env` any more — good, but then the pinning tests below are "
        "asserting nothing. Delete them, or fix the discovery.")


@pytest.mark.parametrize("service", sorted(_services_inheriting_dotenv()))
def test_risky_variables_are_pinned(service: str) -> None:
    env = _services_inheriting_dotenv()[service]
    missing = sorted(v for v in _risk_variables() if v not in env)
    assert not missing, (
        f"service '{service}' takes `env_file: .env` but does not pin {missing}.\n"
        f"  An operator .env left over from a production deploy would put one of {OUR_HOSTS} into "
        f"this container, and both compose files would still look clean.\n"
        f"  Fix: set each of them in the service's `environment:` in docker-compose.everything.yml, "
        f"as ${{ECO_PUBLIC_BASE:-http://127.0.0.1}}:<port>  # [domain-override]")


@pytest.mark.parametrize("service", sorted(_services_inheriting_dotenv()))
def test_pinned_values_do_not_name_our_hosts(service: str) -> None:
    """A pin that pins the wrong value is worse than no pin — it looks handled."""
    env = _services_inheriting_dotenv()[service]
    bad = {k: v for k, v in env.items() if any(h in v for h in OUR_HOSTS)}
    assert not bad, f"service '{service}' hard-codes our production: {bad}"


def test_the_overlay_never_names_our_hosts_in_a_live_value() -> None:
    """The overlay is the tier's definition. A production host in it is unambiguously a bug — there is
    no later file to correct it."""
    name = "docker-compose.everything.yml"
    for lineno, line in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"\s*#", line):
            continue  # comments explain WHY a value is overridden; that is the documentation
        code = line.split("#", 1)[0]
        for host in OUR_HOSTS:
            assert host not in code, f"{name}:{lineno} names {host} in a live value: {line.strip()}"


def test_base_file_production_defaults_are_all_overridden() -> None:
    """The base compose file is shared with the production deploys, so a production default in it is
    legitimate — `prometheus` really does advertise `magic-ai-factory.com` when we run it. What is NOT
    legitimate is such a default surviving into this tier.

    So the rule is not "the base file may not name our hosts". It is: every service in the base file
    that carries one must be overridden by the everything overlay. That distinction matters — the
    blanket rule would either fail forever on a value production needs, or be deleted for crying wolf.
    """
    base_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    overlay_services = set((_load("docker-compose.everything.yml").get("services") or {}))

    current, offenders = None, []
    for lineno, line in enumerate(base_text, 1):
        svc = re.match(r"^  ([a-zA-Z0-9_.-]+):\s*$", line)
        if svc:
            current = svc.group(1)
        if re.match(r"\s*#", line):
            continue
        code = line.split("#", 1)[0]
        if any(h in code for h in OUR_HOSTS) and current not in overlay_services:
            offenders.append(f"docker-compose.yml:{lineno} (service '{current}'): {line.strip()}")

    assert not offenders, (
        "these base-file services point at our production and the everything overlay does not "
        "override them, so the resolved tier config would carry the address:\n  "
        + "\n  ".join(offenders))


def test_the_launcher_still_refuses_on_a_resolved_leak() -> None:
    """The pins above cover the variables we know. The launcher's resolved-config check is what covers
    the ones we do not — it is the only layer that sees the operator's actual `.env`. Deleting it
    because "the tests already check this" would remove the half that generalises."""
    launcher = (ROOT / "scripts" / "everything.sh").read_text(encoding="utf-8")
    assert "Self-containment" in launcher, "the launcher's self-containment step is gone"
    assert '"${COMPOSE[@]}" config' in launcher, (
        "the self-containment step no longer resolves the config — checking the compose FILES instead "
        "of the resolved output would miss exactly the env_file leak this whole file exists for")
    assert "ECO_ALLOW_PROD_HOSTS" in launcher, "the deliberate-federation escape hatch is gone"
