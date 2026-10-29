"""Host-local build recipes for the self-healing loop.

The agent still refuses anything not on ``SKOPOS_AGENT_SERVICE_ALLOWLIST``.
Unset, that list is ``DEFAULT_SERVICE_ALLOWLIST`` — the services MOMUS actually
probes, with their compose aliases. Empty string parks the hand. Env
``SKOPOS_AGENT_BUILD_MAP`` overrides per service, including ``compose_file`` for a
service that lives in its own compose project.

MOMUS / Treasury / SKOPOS / the gate are deliberately absent, and that is not a
matter of tidiness: an agent that could rebuild the auditor could rebuild the thing
that decides whether its own deploy was any good. The same exclusions are enforced
in the Factory's patch scope, one layer up.
"""

from __future__ import annotations

_CANARY = {
    "dockerfile": "momus/canary/Dockerfile",
    "context": ".",
    "image_ref": "momus-canary:latest",
    "compose_service": "momus-canary",
}
_HUB = {
    "dockerfile": "aimarket-hub/Dockerfile",
    "context": ".",
    "image_ref": "modelmarket-hub:latest",
    "compose_service": "hub",
}

#: The oracle family and GAIA are the other two services MOMUS probes, and they live in
#: their own compose projects on the same host — hence `compose_file` per service. Both are
#: built from this repo, so a fix branch is buildable in place.
#: No ``image_ref`` here on purpose. GAIA's compose project builds without an ``image:`` key, so
#: the tag compose resolves is the project-derived ``<project>-<service>`` — which differs per
#: host and is not knowable from the repo. The executor falls back to what the RUNNING container
#: was created from, which is the truth; a guessed tag would promote the digest onto a name
#: compose never looks at, and the deploy would succeed while changing nothing.
#:
#: The oracle FAMILY is deliberately absent even though MOMUS probes it: on the live host it is
#: built from a separate checkout (`/root/oracles/oracles`), not from this repository, so an
#: agent that clones this repo cannot produce its image. A recipe here would be a promise the
#: build step could not keep — and the failure would arrive as "dockerfile not found" in the
#: middle of a remediation, not at configuration time.
#: ``test_target`` / ``test_paths`` are the component's OWN suite, run against the candidate
#: image before it is gated or promoted. Targeted at the modules the patch scope allows —
#: running 268 test files inside a fifteen-minute loop is not a gate, it is a queue — and
#: deliberately excluding ``test_live_*``, which reach the network the test container does
#: not have. A component with no ``test_target`` reports "no suite" rather than silently
#: appearing to pass.
_GAIA = {
    "dockerfile": "gaia/Dockerfile",
    "context": ".",
    "compose_service": "gaia-backend",
    "test_target": "test",
    "test_paths": " ".join((
        # The pinned canonical-form vector goes FIRST: it is the only test in this suite that
        # catches a self-consistent reimplementation of the wire contract. Measured — mounting
        # `json.dumps` over `reading_canonical` left the other 39 tests green.
        "/app/gaia/tests/test_reading_canonical_vector.py",
        "/app/gaia/tests/test_attestation_and_plausibility.py",
        "/app/gaia/tests/test_verifier_envelope.py",
        "/app/gaia/tests/test_app_and_wot.py",
        "/app/gaia/tests/test_gnss_integrity.py",
        "/app/gaia/tests/test_security.py",
    )),
}

#: The practice target. Its whole purpose is to be repaired, so it declares a test stage from
#: the start — the suite fails while a drill is running and passes when the loop has finished,
#: which makes the gate the thing that decides whether the repair was real.
_PRAXIS = {
    "dockerfile": "praxis/Dockerfile",
    "context": ".",
    "image_ref": "praxis:latest",
    "compose_service": "praxis",
    "test_target": "test",
    "test_paths": "/app/praxis/tests",
}

DEFAULT_BUILD_RECIPES: dict[str, dict[str, str]] = {
    "praxis": dict(_PRAXIS),
    "canary": dict(_CANARY),
    "momus-canary": dict(_CANARY),
    "hub": dict(_HUB),
    "aimarket-hub": dict(_HUB),
    "gaia": dict(_GAIA),
    "gaia-backend": dict(_GAIA),
}

#: Live by default. An operator parks with ``SKOPOS_AGENT_SERVICE_ALLOWLIST=`` (empty)
#: or ``SKOPOS_AGENT_DRY_RUN=1``. MOMUS / Treasury / the gate are not on this list.
DEFAULT_SERVICE_ALLOWLIST: tuple[str, ...] = tuple(DEFAULT_BUILD_RECIPES.keys())


def merge_build_map(overrides: dict | None) -> dict[str, dict[str, str]]:
    """Built-in recipes, with operator JSON winning per service."""
    merged = {k: dict(v) for k, v in DEFAULT_BUILD_RECIPES.items()}
    for key, value in (overrides or {}).items():
        if isinstance(value, dict):
            merged[str(key)] = {**merged.get(str(key), {}), **{str(a): (b if a == "env" and isinstance(b, dict) else str(b)) for a, b in value.items()}}
        elif value:
            merged[str(key)] = value  # type: ignore[assignment]
    return merged
