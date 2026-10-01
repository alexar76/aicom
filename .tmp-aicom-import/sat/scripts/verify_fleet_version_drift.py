#!/usr/bin/env python3
"""Is what is RUNNING the code we have? — and can that question even be asked yet?

``verify_published_dist_freshness.py`` closes one side of a three-way divergence: it proves the
published distribution matches the tree at the same version. This is the other side, the tree
against the FLEET. Nothing looked at it.

THE FIRST MEASUREMENT SAID "SIX OF SEVEN COMPONENTS ARE BEHIND". IT WAS WRONG.
------------------------------------------------------------------------------
It compared the packaging version (``pyproject.toml``) against the version the service reports on
the wire. Those are different numbers in this tree:

    component      pyproject   __version__   /health serves
    aimarket-hub   3.3.0       3.2.1         3.2.1
    momus          0.2.0       0.1.0         0.1.0
    logos          0.2.0       0.1.0         0.1.0
    gaia           0.2.0       0.1.0         0.1.0
    atlas          0.2.0       0.1.0         0.1.0
    metis          0.2.1       0.1.0         0.2.0   <- a third number, hardcoded in api/app.py
    basanos        0.1.0       0.1.0         0.1.0   <- the only coherent one

Every "behind" row was that conflation. Compared like with like — the tree's RUNTIME version
against what the fleet serves — there is currently no deployment drift at all.

So the real defect is worse than being behind: **a component declares more than one version, and
nothing says which one is authoritative.** ``aimarket-hub`` alone declares five (pyproject 3.3.0,
``__init__`` 3.2.1, ``server.json`` 3.2.1, a Dockerfile LABEL, and ``SERVER_VERSION = "1.0.0"`` in
the MCP gateway). While that holds, "is production current?" has no answer to compute — which is
exactly why drift went unnoticed rather than being noticed and tolerated.

This script therefore reports two findings, in order, because the second is meaningless without
the first:

``incoherent``  the tree disagrees with itself about this component's version
``drift``       the fleet serves something other than the tree's runtime version

WHAT THIS IS NOT
----------------
Not an updater. There is deliberately no code path that applies anything: the levels are
``inventory`` (collect and print) and ``advisory`` (say what drifted and name the recipe). There is
no ``enforce`` — not disabled, absent.

WHY THERE IS NO GITHUB POLLING
------------------------------
For our OWN components the monorepo IS the upstream: this file reads the declared version out of
the tree it lives in, so "is a newer version available" needs no external feed and no credential.
Third-party advisories are a different question with an existing answer — BASANOS already ingests
OSV/GHSA behind a host allowlist and distills them onto a closed category set
(``basanos/basanos/intel/sources.py``). A second fetcher would be a second allowlist, a second set
of rate limits, and a second place an advisory can be mishandled; DOLOS made exactly this call in
``dolos/dolos/intel.py`` and consumes BASANOS's distilled result instead. Update advisories should
be a CONSUMER of that feed, never a new source.

THE TRUST GRADIENT, STATED RATHER THAN SMOOTHED OVER
----------------------------------------------------
The baseline is always LOCAL — the tree. A version arriving over the network is an OBSERVATION
about a node, never the baseline, because a node's self-report is attacker-supplied with zero
preconditions. The observations differ in authority:

``signed``    A hub's ``/.well-known/ai-market.json`` is signed whole (``sign_object``) and
              verified here against a key PINNED IN THIS FILE. The document advertises
              ``signer_public_key`` equal to ``signature.public_key``, so a consumer that takes
              the key out of the response verifies the document against itself — which is the
              entire reason the pins are in the tree and not read from the wire.
``unsigned``  A satellite's ``/health`` states a version with no signature at all. A hint, never
              authority, and labelled so the difference stays visible.

Verification here is KEYLESS: ``Signer.verify_object_signature`` is static, so this script holds
no signing key and creates none. That is deliberate — a checker that parses network responses must
not live in the process that holds the federation identity.

Usage:
    python3 scripts/verify_fleet_version_drift.py               # coherence + drift table
    python3 scripts/verify_fleet_version_drift.py --json        # machine-readable
    python3 scripts/verify_fleet_version_drift.py --advisory     # only findings, with recipes
    python3 scripts/verify_fleet_version_drift.py --offline      # coherence only, no network
    python3 scripts/verify_fleet_version_drift.py --component hub-apex

Exit status is 1 when anything is incoherent or drifted, so the alerter and CI can gate on it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Same declaration regexes as verify_published_dist_freshness.py. Two short patterns are not worth
# coupling two standalone scripts through an import.
_NAME = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.M)
_VERSION = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.M)
_DUNDER = re.compile(r'^\s*__version__\s*=\s*"([^"]+)"', re.M)

#: A version string this script is willing to PARSE or PRINT. Bounded per segment as well as
#: overall: `int()` on a segment of a hundred thousand digits is a quadratic hang, and an
#: unbounded string is room for ANSI escapes, forged newlines and bidi overrides — all of which
#: arrive from a network response and all of which end up in a terminal and a chat message.
_SAFE_VERSION = re.compile(r"^[0-9]{1,6}(?:\.[0-9]{1,6}){0,3}(?:[-+][0-9A-Za-z.]{1,16})?$")

#: Only these two schemes are ever fetched. A redirect to anything else — `file://` included — is
#: refused before a socket is opened.
_ALLOWED_SCHEMES = ("https",)

TIMEOUT = 20
#: A manifest is a few KB. Anything larger is broken or an attempt to make the checker the
#: expensive half of the exchange.
MAX_BYTES = 512 * 1024

GREEN, RED, YELLOW, CYAN, DIM, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m")


class Probe:
    """One fleet component: what the tree says, and where the thing is running.

    Every field is fixed in this file. Nothing is ever derived from a response — not the URL (that
    would make this an SSRF primitive on whichever host schedules it), not the pinned key (that
    would make the signature self-verifying), and above all not `recipe`, which is the text an
    operator's fingers will interpret.
    """

    __slots__ = ("cid", "pyproject", "runtime_source", "url", "kind", "pinned_key", "recipe", "note")

    def __init__(self, cid: str, pyproject: str, runtime_source: str, url: str, kind: str,
                 recipe: str, pinned_key: str = "", note: str = "") -> None:
        assert kind in ("signed_manifest", "health"), kind
        self.cid = cid
        self.pyproject = pyproject
        #: The file the RUNNING service actually reads its version from. Not the packaging file —
        #: conflating the two is the bug this script's docstring exists to record.
        self.runtime_source = runtime_source
        self.url = url
        self.kind = kind
        self.pinned_key = pinned_key
        self.recipe = recipe
        self.note = note


#: The fleet. Pins recorded on first sight on 2026-09-06 and verified the same day against the
#: live documents with `Signer.verify_object_signature`, including a negative check that another
#: hub's key is refused.
FLEET: tuple[Probe, ...] = (
    Probe("hub-apex", "aimarket-hub/pyproject.toml", "aimarket-hub/aimarket_hub/__init__.py",
          "https://modelmarket.dev", "signed_manifest",
          recipe="scripts/deploy_hub.sh",
          pinned_key="lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",  # gitleaks:allow — Ed25519 pubkey pin, not a secret
          ),
    Probe("hub-uni", "aimarket-hub/pyproject.toml", "aimarket-hub/aimarket_hub/__init__.py",
          "https://uni.modelmarket.dev", "signed_manifest",
          recipe="scripts/deploy_hub.sh",
          pinned_key="jmh/t/PAQ+dFsyCQDtTioqF2lKruy35jK4OKlt1fN8Q=",  # gitleaks:allow — Ed25519 pubkey pin, not a secret
          note="same image as hub-apex; VITE_BASE_PATH is baked at build time"),
    Probe("hub-independent", "aimarket-hub/pyproject.toml", "aimarket-hub/aimarket_hub/__init__.py",
          "https://independentai.network/hub", "signed_manifest",
          recipe="install the release, then: systemctl restart independentai-hub.service",
          pinned_key="op8JQ5j0SBKjq3nmbiIjHjr3OwRgF9rKeDhRyRqRKaI=",  # gitleaks:allow — Ed25519 pubkey pin, not a secret
          note="systemd + venv, not docker; the package is on disk twice"),
    Probe("hub-hunt", "aimarket-hub/pyproject.toml", "aimarket-hub/aimarket_hub/__init__.py",
          "https://hunt.modelmarket.dev", "signed_manifest",
          recipe="scripts/deploy_hub.sh",
          pinned_key="r6+J7JEt/ZUNjMtueDJmLjFz7aBr1wH4bQZqulLvMSI=",  # gitleaks:allow — Ed25519 pubkey pin, not a secret
          ),
    Probe("momus", "momus/pyproject.toml", "momus/momus/__init__.py",
          "https://momus.modelmarket.dev", "health",
          recipe="rebuild the momus compose services on the oracle host (no deploy script exists)",
          note="compose-managed; scripts/deploy_momus.sh does not exist"),
    Probe("basanos", "basanos/pyproject.toml", "basanos/basanos/__init__.py",
          "https://basanos.modelmarket.dev", "health",
          recipe="scripts/deploy_basanos.sh"),
    Probe("logos", "logos/pyproject.toml", "logos/logos/__init__.py",
          "https://logos.modelmarket.dev", "health",
          recipe="scripts/deploy_logos.sh"),
    Probe("metis", "metis/pyproject.toml", "metis/metis/api/app.py",
          "https://metis.modelmarket.dev", "health",
          recipe="scripts/deploy_cognition.sh",
          note="/health serves a version LITERAL in api/app.py, tied to neither declared version"),
    Probe("gaia", "gaia/pyproject.toml", "gaia/gaia/__init__.py",
          "https://iot.modelmarket.dev", "health",
          recipe="scripts/deploy_gaia.sh"),
    Probe("atlas", "atlas/pyproject.toml", "atlas/atlas/__init__.py",
          "https://atlas.modelmarket.dev", "health",
          recipe="scripts/deploy_atlas.sh"),
)


# ── reading the tree ─────────────────────────────────────────────────────────────────────────


def packaging_version(rel: str) -> tuple[str | None, str | None]:
    """(distribution name, version) from a pyproject, or (None, None)."""
    path = ROOT / rel
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    name, version = _NAME.search(text), _VERSION.search(text)
    return (name.group(1) if name else None), (version.group(1) if version else None)


def runtime_version(rel: str) -> str | None:
    """The version the RUNNING service reports, read from the file it actually reads.

    Prefers `__version__`; falls back to a `"version": "x.y.z"` literal, because at least one
    component (metis) serves a hardcoded string from its API module instead of a constant.
    """
    path = ROOT / rel
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    dunder = _DUNDER.search(text)
    if dunder:
        return dunder.group(1)
    literal = re.search(r'"version"\s*:\s*"([0-9][^"]{0,31})"', text)
    return literal.group(1) if literal else None


def tree_revision() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


# ── reading the fleet ────────────────────────────────────────────────────────────────────────


def _fetch_json(url: str, *, timeout: float = TIMEOUT) -> tuple[dict[str, Any] | None, str]:
    """GET a JSON object, or (None, reason). Never raises, never leaves the host or the scheme.

    The redirect rule is load-bearing: a probed component that can be made to redirect turns this
    script into an internal port scanner running wherever it is scheduled. No credential is ever
    attached here, which also side-steps the stdlib behaviour that an `Authorization` header
    survives a cross-host redirect.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        return None, f"refused scheme {parts.scheme!r}"
    host = parts.hostname or ""

    class _SameHostOnly(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            new = urllib.parse.urlsplit(newurl)
            if new.scheme not in _ALLOWED_SCHEMES or (new.hostname or "") != host:
                return None                 # refuse: a redirect may change neither host nor scheme
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_SameHostOnly)
    req = urllib.request.Request(url, headers={"accept": "application/json",
                                               "user-agent": "aicom-fleet-drift"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return None, f"unreachable ({type(exc).__name__})"
    if len(raw) > MAX_BYTES:
        return None, f"response over {MAX_BYTES} bytes"
    try:
        body = json.loads(raw)
    except ValueError:
        return None, "not JSON"
    if not isinstance(body, dict):
        return None, "not a JSON object"
    return body, ""


def _verify_signed(body: dict[str, Any], pinned_key: str) -> tuple[bool, str]:
    """Verify a whole-document signature against the PIN. Keyless — no Signer is constructed."""
    if not pinned_key:
        return False, "no pin in the registry"
    try:
        sys.path.insert(0, str(ROOT / "aimarket-hub"))
        from aimarket_hub.signing import Signer
    except Exception as exc:                    # pragma: no cover - environment dependent
        return False, f"hub signing unavailable ({type(exc).__name__})"

    presented = (body.get("signature") or {}).get("public_key", "")
    if presented and presented != pinned_key:
        # Deliberately distinct from "bad signature": the document is correctly signed by SOMEONE
        # ELSE, which is a key-rotation or an impersonation, not corruption.
        return False, "signer key does not match the pin"
    try:
        ok = Signer.verify_object_signature(body, pinned_key)
    except Exception as exc:
        return False, f"verify raised {type(exc).__name__}"
    return bool(ok), "" if ok else "signature did not verify against the pin"


def observe(p: Probe) -> dict[str, Any]:
    """What version is this node SERVING, and how much authority does that observation carry?"""
    if p.kind == "signed_manifest":
        body, reason = _fetch_json(f"{p.url}/.well-known/ai-market.json")
        if body is None:
            return {"served": None, "authority": "unreachable", "detail": reason}
        verified, why = _verify_signed(body, p.pinned_key)
        return {"served": body.get("hub_version"),
                "authority": "signed" if verified else "signed/UNVERIFIED",
                "detail": why,
                "pq": bool((body.get("signature") or {}).get("pq_value"))}

    body, reason = _fetch_json(f"{p.url}/health")
    if body is None:
        return {"served": None, "authority": "unreachable", "detail": reason}
    return {"served": body.get("version"), "authority": "unsigned",
            "detail": "/health carries no signature"}


# ── comparing ────────────────────────────────────────────────────────────────────────────────


def _core(version: str) -> tuple[int, ...]:
    """Numeric core as integers. Only ever called on a string that passed _SAFE_VERSION."""
    return tuple(int(part) for part in re.findall(r"[0-9]+", version)[:4])


def coherence(pkg: str | None, runtime: str | None) -> tuple[str, str]:
    """Does the tree agree with itself? (state, reason)."""
    if not pkg and not runtime:
        return "unknown", "no version found in the tree"
    if not runtime:
        return "unknown", "no runtime version source found"
    if not pkg:
        return "unknown", "no packaging version found"
    if pkg == runtime:
        return "coherent", ""
    return "incoherent", f"packaging {pkg} != runtime {runtime}"


def drift(runtime: str | None, served: str | None) -> tuple[str, str]:
    """Does the fleet serve the tree's runtime version? (state, reason)."""
    if runtime is None:
        return "unknown", "no runtime version in the tree to compare against"
    if served is None:
        return "unknown", "node did not answer"
    served = str(served)
    if not _SAFE_VERSION.match(served):
        # Refused rather than echoed: this string was on its way to a terminal and a chat message.
        return "suspect", "served version is not a plain version string — not displaying it"
    if served == runtime:
        return "match", ""
    if not _SAFE_VERSION.match(runtime):
        return "unknown", "tree runtime version is not a plain version string"
    rs, rr = _core(served), _core(runtime)
    if rs < rr:
        return "behind", f"serves {served}, tree runs {runtime}"
    if rs > rr:
        # Not an update. Something is deployed that this tree does not contain — an unrecorded
        # deploy or a rollback target. An operator should look, not upgrade.
        return "AHEAD", f"serves {served} > tree {runtime} — deployed code is not in this tree"
    return "match", "same numeric version, different suffix"


def collect(components: list[str] | None = None, *, offline: bool = False) -> dict[str, Any]:
    rows = []
    for p in FLEET:
        if components and p.cid not in components:
            continue
        dist, pkg = packaging_version(p.pyproject)
        runtime = runtime_version(p.runtime_source)
        coh, coh_why = coherence(pkg, runtime)

        if offline:
            obs = {"served": None, "authority": "not probed", "detail": "--offline"}
            dstate, dwhy = "unknown", "not probed"
        else:
            obs = observe(p)
            dstate, dwhy = drift(runtime, obs.get("served"))

        rows.append({
            "component": p.cid,
            "distribution": dist,
            "packaging_version": pkg,
            "runtime_version": runtime,
            "served_version": obs.get("served") if dstate != "suspect" else None,
            "authority": obs["authority"],
            "coherence": coh,
            "coherence_reason": coh_why,
            "drift": dstate,
            "drift_reason": dwhy or obs.get("detail", ""),
            "recipe": p.recipe,
            "note": p.note,
            "pq_signed": obs.get("pq", False),
        })
    return {"tree_revision": tree_revision(), "components": rows}


# ── output ───────────────────────────────────────────────────────────────────────────────────

_C = {"coherent": GREEN, "incoherent": RED, "match": GREEN, "behind": RED,
      "AHEAD": YELLOW, "suspect": YELLOW, "unknown": DIM}


def _findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in report["components"]
            if r["coherence"] == "incoherent" or r["drift"] in ("behind", "AHEAD", "suspect")]


def render(report: dict[str, Any], *, advisory: bool) -> str:
    out = []
    if advisory:
        found = _findings(report)
        if not found:
            return "no findings"
        for r in found:
            if r["coherence"] == "incoherent":
                out.append(f"{RED}{r['component']}{OFF}: the tree disagrees with itself — "
                           f"{r['coherence_reason']}")
                out.append(f"    {CYAN}fix:{OFF} make one of them authoritative; a fleet "
                           f"comparison means nothing until then")
            if r["drift"] in ("behind", "AHEAD", "suspect"):
                out.append(f"{_C[r['drift']]}{r['component']}{OFF}: {r['drift']} — "
                           f"{r['drift_reason']}")
                out.append(f"    {CYAN}update:{OFF} {r['recipe']}")
            if r["note"]:
                out.append(f"    {DIM}{r['note']}{OFF}")
        return "\n".join(out)

    out.append(f"{DIM}tree {report['tree_revision']}{OFF}")
    out.append(f"{'component':<18}{'packaging':<11}{'runtime':<10}{'served':<10}"
               f"{'authority':<18}{'tree':<12}drift")
    for r in report["components"]:
        out.append(
            f"{r['component']:<18}"
            f"{str(r['packaging_version'] or '—'):<11}"
            f"{str(r['runtime_version'] or '—'):<10}"
            f"{str(r['served_version'] or '—'):<10}"
            f"{r['authority']:<18}"
            f"{_C[r['coherence']]}{r['coherence']:<12}{OFF}"
            f"{_C[r['drift']]}{r['drift']}{OFF}"
            + (f"  {DIM}{r['drift_reason']}{OFF}" if r["drift_reason"] else ""))
    incoherent = sum(1 for r in report["components"] if r["coherence"] == "incoherent")
    drifted = sum(1 for r in report["components"] if r["drift"] in ("behind", "AHEAD"))
    unsigned = sum(1 for r in report["components"] if r["authority"] == "unsigned")
    out.append("")
    out.append(f"{incoherent} component(s) disagree with themselves about their own version; "
               f"{drifted} drifted; {unsigned} report a version with no signature at all.")
    if incoherent:
        out.append(f"{DIM}A drift number is only as trustworthy as the coherence column beside "
                   f"it: where the tree states two versions, 'match' merely means the fleet "
                   f"agrees with one of them.{OFF}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--advisory", action="store_true",
                    help="only findings, each with the recipe that addresses it")
    ap.add_argument("--offline", action="store_true",
                    help="tree-coherence only; makes no network request")
    ap.add_argument("--component", action="append", dest="components",
                    help="limit to this component id (repeatable)")
    args = ap.parse_args(argv)

    report = collect(args.components, offline=args.offline)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json
          else render(report, advisory=args.advisory))
    return 1 if _findings(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
