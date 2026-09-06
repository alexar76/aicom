"""Autonomous patch authoring — the Factory's half of the self-healing loop.

SKOPOS's conductor posts a signed MOMUS remediation ticket here and gets back a **unified diff**.
It never gets an image, and this module never touches the deployed tree: the diff goes onto a
``momus/fix-*`` branch, a node agent builds THAT commit, MOMUS gates the resulting image, and only
then does anything ship. This file's whole job is to produce a reviewable artifact.

Five refusals shape it, and each one is a bug this codebase has already produced once:

1. **Never through ``BaseAgent``.** ``agents/base_agent.py`` catches every exception from the router
   and falls back to hard-coded JSON. A *cost-guard refusal* would therefore come back as a
   plausible-looking patch, which would then be committed and reviewed as if a model had written it.
   So this calls ``llm_router.generate`` directly and lets budget errors propagate.
2. **Never ``stream()``.** The streaming path skips both the per-product budget check and the
   output-token clamp.
3. **A non-empty ``product_id``, always.** ``assert_product_within_budget`` returns silently for an
   empty id, and the router only books spend when one is set — so without it the cap is inert.
4. **Scope is LOCAL.** Which files may be rewritten comes from this host's own map, keyed by
   component. The ticket names a component, never a path; a model that answers with a file outside
   the map is refused rather than trusted.
5. **The model never writes the diff.** It returns full file contents; the diff is computed here with
   git, in a scratch tree. Hand-written unified diffs from an LLM are unreliable in exactly the way
   that matters — a subtly malformed hunk that applies to the wrong lines.

The deployed tree is never opened for writing. ``/app`` is not even a git repository (``.dockerignore``
excludes ``.git``), which is why the diff is produced from a scratch snapshot rather than ``git diff``.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

#: Explicit opt-in. Merging this module must not enable the capability — turning autonomous patch
#: authoring on is a deliberate operator decision, per momus/docs/fix-provenance.md.
ENABLED_ENV = "AIFACTORY_REMEDIATION_FIX_ENABLED"
#: Shared secret with the conductor. Required in production.
KEY_ENV = "AIFACTORY_REMEDIATION_KEY"
#: MOMUS's public signing key, so a ticket cannot simply be asserted by whoever can reach the route.
MOMUS_PUBKEY_ENV = "AIFACTORY_REMEDIATION_MOMUS_PUBKEY"
#: component → the ONLY paths a patch for it may touch. Local by design (see refusal 4).
SCOPE_ENV = "AIFACTORY_REMEDIATION_SCOPE"
#: A synthetic product id so the per-product cost guard is not a no-op (see refusal 3).
COST_PRODUCT_ID = "__remediation__"

logger = logging.getLogger(__name__)

#: Paths no patch may EVER touch, whatever the scope map says. This is not a tidier way of
#: leaving a component out of `DEFAULT_SCOPE` — omission is a default, and a default is
#: exactly what an operator widening the env var overrides without noticing. A conflict of
#: interest has to be refused by code.
#:
#: * ``momus/momus`` — the auditor. A loop that can patch what decides a finding is real can
#:   decide it is not. (``momus/canary`` is deliberately NOT here: the canary is the test
#:   subject, and proving the loop on it is the whole reason it exists.)
#: * ``treasury`` — the payer, holding the one key MOMUS never sees. MOMUS finds and signs;
#:   it must not be able to reach the thing that pays it.
#: * ``skopos`` — the conductor. It decides whether a fix ships and calls MOMUS back to
#:   re-test. Patching your own gatekeeper is patching yourself, one step removed.
#: * this file and the deploy path — the gate itself.
DENIED_PATH_PREFIXES: tuple[str, ...] = (
    "momus/momus/",
    "momus/scripts/",
    "treasury/",
    "skopos/",
    "web/backend/services/remediation_fix.py",
    "web/backend/services/remediation_deploy",
)

#: The canary proved the loop. Everything else here is a service MOMUS actually PROBES —
#: scope wider than the probes would let a ticket rewrite a file nothing re-tests, and the
#: signed re-run of the probe is the only thing standing between a patch and production.
#: Each entry is the file whose behaviour the probe asserts, and nothing else: ``api.py`` and
#: the big capability modules are over the scratch-tree cap anyway.
#: MOMUS names targets ``canary`` / ``hub`` / ``oracles`` / ``gaia``; compose and tickets also
#: use the longer service names — both must resolve.
_CANARY_PATHS = ["momus/canary/canary.py"]
#: hub: the unpaid-invoke gate MOMUS re-runs, and the free-tier ceiling it probes.
_HUB_PATHS = [
    "aimarket-hub/aimarket_hub/unpaid_invoke.py",
    "aimarket-hub/aimarket_hub/sandbox_trials.py",
]
#: oracle family: the three modules the oracle-kind probes assert against — the declared
#: free-tier ceiling, the manifest/receipt signatures, and the rate limiter.
_ORACLE_PATHS = [
    "oracles/core/oracle_core/tiers.py",
    "oracles/core/oracle_core/signing.py",
    "oracles/core/oracle_core/ratelimit.py",
]
#: GAIA is built on oracle_core but gets its OWN files only. A GAIA ticket that could rewrite
#: the shared core would change every oracle in the fleet to fix one relay.
_GAIA_PATHS = ["gaia/gaia/attestation.py", "gaia/gaia/clock.py", "gaia/gaia/fleet.py"]
#: PRAXIS is the practice target: one file, a genuine source-level defect, no consumers, and a
#: docstring that says repairing it is the intended outcome. The canary cannot serve this role —
#: its repair is a runtime toggle, and a source repair would end its usefulness as a fixture.
_PRAXIS_PATHS = ["praxis/praxis.py"]
DEFAULT_SCOPE: dict[str, list[str]] = {
    "canary": list(_CANARY_PATHS),
    "momus-canary": list(_CANARY_PATHS),
    "hub": list(_HUB_PATHS),
    "aimarket-hub": list(_HUB_PATHS),
    "oracles": list(_ORACLE_PATHS),
    "oracle-family": list(_ORACLE_PATHS),
    "oracles-oracle-family-1": list(_ORACLE_PATHS),
    "gaia": list(_GAIA_PATHS),
    "gaia-backend": list(_GAIA_PATHS),
    "gaia-gaia-backend-1": list(_GAIA_PATHS),
    "praxis": list(_PRAXIS_PATHS),
}


def path_is_denied(rel_path: str) -> str:
    """The prefix that forbids this path, or "" if it is allowed.

    Checked against the scope map AND against whatever the model answers, because the two
    fail differently: a widened env var is an operator mistake, a path outside the map is a
    model's.
    """
    normalised = str(rel_path or "").strip().lstrip("./").replace("\\", "/")
    for prefix in DENIED_PATH_PREFIXES:
        if normalised == prefix or normalised.startswith(prefix):
            return prefix
    return ""

MAX_DIFF_BYTES = 200_000
MAX_FILE_BYTES = 120_000
#: How long the model gets. Raised from 90s after a live ticket timed out: the route asks for FULL
#: file contents (so the diff can be computed by git rather than written by the model, which is what
#: makes it trustworthy), and a few hundred lines from a mid-tier model takes minutes, not seconds.
#: This loop is not interactive — a patch that takes three minutes is fine. Must stay BELOW the
#: conductor's client timeout, or both ends give up and only one of them says why.
#: Measured on the live deployment: this prompt takes the configured model 79-119 seconds, which
#: made a 240s budget marginal — and it failed twice in a row on the first real autonomous
#: dispatch, which is exactly when marginal shows up. The comment above already records a rise
#: from 90 to 240 for the same reason; the lesson is that this number wants headroom, not a
#: tighter fit. Whatever it is set to, the conductor's FactoryClient timeout
#: (SKOPOS_FACTORY_TIMEOUT_S) must EXCEED it, or the client gives up first and the job escalates
#: blaming a patch that was still being written.
LLM_BUDGET_S = float(os.environ.get("AIFACTORY_REMEDIATION_LLM_BUDGET_S", "600") or 600)


class FixRefused(Exception):
    """A refusal that is the CALLER's or the operator's to fix, never something to retry."""

    def __init__(self, reason: str, *, config_error: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.config_error = config_error


@dataclass
class AuthoredPatch:
    diff: str
    summary: str
    files: list[str] = field(default_factory=list)
    component: str = ""
    finding_id: str = ""
    #: Never an image. The Factory authors source; the fleet builds images. Sending an image name
    #: from here is precisely how the old loop pretended a patch had been produced.
    def to_dict(self) -> dict[str, Any]:
        return {"diff": self.diff, "summary": self.summary, "files": list(self.files),
                "component": self.component, "finding_id": self.finding_id,
                "deployable": False}


# ── configuration ─────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    return str(os.environ.get(ENABLED_ENV, "")).strip().lower() in ("1", "true", "yes", "on")


def _strip_denied(scope: dict[str, list[str]]) -> dict[str, list[str]]:
    """Drop conflict-of-interest paths from a scope map, wherever the map came from.

    Applied to the operator's env AND to the built-in default, because the point of the
    denylist is that no configuration can grant these — including a future edit to the
    default that forgets why they were absent.
    """
    out: dict[str, list[str]] = {}
    for component, paths in scope.items():
        kept = []
        for path in paths:
            denied = path_is_denied(path)
            if denied:
                logger.warning(
                    "remediation scope for %r names %r, which is under the conflict-of-interest "
                    "denylist (%s) — dropped", component, path, denied,
                )
                continue
            kept.append(path)
        if kept:
            out[component] = kept
    return out


def scope_map() -> dict[str, list[str]]:
    raw = str(os.environ.get(SCOPE_ENV, "")).strip()
    if not raw:
        return _strip_denied(DEFAULT_SCOPE)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # A malformed scope map must leave the route unable to patch anything, never able to patch
        # everything. Falling back to the default is the conservative direction.
        return _strip_denied(DEFAULT_SCOPE)
    if not isinstance(parsed, dict):
        return _strip_denied(DEFAULT_SCOPE)
    return _strip_denied(
        {str(k): [str(p) for p in (v or []) if str(p).strip()] for k, v in parsed.items()}
    )


def app_root() -> str:
    return os.environ.get("AIFACTORY_APP_ROOT", "/app")


# ── ticket authenticity ───────────────────────────────────────────────────────
def _canonical(body: dict[str, Any]) -> str:
    """Byte-identical to momus.findings.FindingSigner._canon_str."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verify_blame(blame: dict[str, Any], momus_pubkey: str) -> tuple[bool, str]:
    """Check MOMUS's Blame attestation with `cryptography` directly.

    Reimplemented rather than imported: ``momus.findings`` imports ``oracle_core``, which is not a
    Factory dependency, so ``import momus.findings`` fails inside this container even though the
    source is on disk. The canonical form and the signature-object shape are therefore duplicated
    here, and ``tests/test_remediation_fix_route.py`` pins them against the real implementation so
    the two cannot drift silently — the same int-vs-float class of split the AWR work already hit."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not momus_pubkey:
        return False, "no MOMUS public key configured — cannot verify the ticket"
    sig = (blame or {}).get("signature") or {}
    value = str(sig.get("value") or "")
    if not value:
        return False, "ticket carries no signed Blame attestation"
    if sig.get("pq_value"):
        # oracle_core refuses a post-quantum signature it cannot check rather than ignoring it, and
        # so must this: silently verifying only the classical half would downgrade the guarantee.
        return False, "Blame carries a post-quantum signature this service cannot verify"
    body = {k: v for k, v in (blame or {}).items() if k != "signature"}
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(momus_pubkey))
        pub.verify(base64.b64decode(value), _canonical(body).encode())
    except (InvalidSignature, ValueError, TypeError):
        return False, "Blame signature does not verify under the configured MOMUS key"
    return True, "Blame verified"


def check_ticket(ticket: dict[str, Any]) -> tuple[str, str]:
    """(component, finding_id) for a ticket that is authentic and in scope. Raises FixRefused."""
    finding_id = str((ticket or {}).get("finding_id") or "").strip()
    component = str((ticket or {}).get("component") or "").strip()
    if not finding_id or not component:
        raise FixRefused("ticket must carry finding_id and component")
    momus_pubkey = str(os.environ.get(MOMUS_PUBKEY_ENV, "")).strip()
    ok, why = verify_blame((ticket or {}).get("blame") or {}, momus_pubkey)
    if not ok:
        raise FixRefused(f"unverified ticket: {why}",
                         config_error=("no MOMUS public key" in why))
    blame = (ticket or {}).get("blame") or {}
    # The signature proves the document; these two checks prove it is a document about THIS ticket.
    if blame.get("finding_id") != finding_id:
        raise FixRefused("Blame finding_id disagrees with the ticket")
    if blame.get("component") != component:
        raise FixRefused("Blame component disagrees with the ticket")
    if component not in scope_map():
        raise FixRefused(
            f"'{component}' has no patch scope on this host — autonomous authoring is enabled "
            f"per component, and this one was never enabled", config_error=True)
    return component, finding_id


# ── the scratch tree ──────────────────────────────────────────────────────────
_credential_audit_done = False


def audit_visible_credentials(root: str | None = None, *, limit: int = 20) -> list[str]:
    """Log every credential-looking file the fixer can still SEE. Returns what it found.

    The read policy refuses these by path, and the container masks the highest-value ones out
    of the mount entirely. Neither is a reason to stop looking: masks are a hand-maintained
    list in a compose file, and the next `.env.something` to appear in the tree will not be on
    it. Two already were not — `.env.demo` and `signal-hunt/.env.ci` — and only turned up
    because someone went looking.

    So the fixer counts what it can reach and says so once per process. A number that grows is
    a mask that needs updating; a number that is zero is a claim you can check.
    """
    base = os.path.realpath(root or app_root())
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        # Do not descend into dependency trees: they are full of test fixtures and CA bundles
        # that match on name and are nobody's secret.
        dirnames[:] = [d for d in dirnames
                       if d not in ("node_modules", ".git", "__pycache__", "site-packages")
                       and not d.startswith(".venv")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), base)
            if "example" in name or name == "cacert.pem":
                continue
            if not path_is_secret(rel):
                continue
            try:
                if os.path.getsize(os.path.join(dirpath, name)) == 0:
                    continue          # masked with /dev/null
            except OSError:
                continue
            found.append(rel)
            if len(found) >= limit:
                return found
    return found


def _audit_once() -> None:
    global _credential_audit_done
    if _credential_audit_done:
        return
    _credential_audit_done = True
    try:
        found = audit_visible_credentials()
    except OSError:
        return
    if found:
        logger.warning(
            "%d credential-looking file(s) are still readable inside this container; the read "
            "policy refuses them, but they should be masked out of the mount too: %s",
            len(found), ", ".join(found[:8]))
    else:
        logger.info("no credential-looking file is readable inside this container")


def _read_scope(component: str) -> dict[str, str]:
    _audit_once()
    root = os.path.realpath(app_root())
    out: dict[str, str] = {}
    for rel in scope_map()[component]:
        path = os.path.realpath(os.path.join(root, rel))
        if not (path == root or path.startswith(root + os.sep)):
            raise FixRefused(f"scope entry '{rel}' escapes the application root", config_error=True)
        if not os.path.isfile(path):
            raise FixRefused(f"scope entry '{rel}' does not exist in this build", config_error=True)
        # The scope map is operator-declared, so a credential in it is a configuration mistake,
        # not a model's overreach — and a mistake that would put the key in the prompt AND make
        # the model rewrite the file. Refuse loudly instead of redacting quietly.
        refused = read_is_denied(rel)
        if refused:
            raise FixRefused(f"scope entry '{rel}' may not be read: {refused}", config_error=True)
        with open(path, encoding="utf-8") as fh:
            out[rel] = fh.read(MAX_FILE_BYTES + 1)
        if len(out[rel]) > MAX_FILE_BYTES:
            raise FixRefused(f"scope entry '{rel}' is too large to patch safely", config_error=True)
        # A source file with a pasted token is not hypothetical here: a live prod.yaml once
        # carried one. Redacting the copy the model sees costs the patch nothing — the value
        # is never what the fix is about — and keeps it out of every downstream transcript.
        out[rel], hits = redact_secrets(out[rel])
        if hits:
            logger.warning("scope file %s carried %d secret-looking value(s) — redacted", rel, hits)
    if not out:
        raise FixRefused(f"'{component}' has an empty patch scope", config_error=True)
    return out


def _run(argv: list[str], cwd: str) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60, check=False)
        return p.returncode, p.stdout, p.stderr
    except (subprocess.SubprocessError, OSError) as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"


def diff_from_rewrites(before: dict[str, str], after: dict[str, str]) -> str:
    """A unified diff, computed by git in a throwaway tree.

    Not asked of the model: an LLM-written hunk that is subtly wrong applies to the wrong lines, and
    the whole point of shipping a diff is that a human and ``git apply`` can both trust it. Paths are
    repo-relative on both sides, so the result applies at the monorepo root."""
    scratch = tempfile.mkdtemp(prefix="remediation-fix-")
    try:
        for rel, text in before.items():
            dest = os.path.join(scratch, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(text)
        for argv in (["git", "init", "-q"],
                     ["git", "-c", "user.email=fix@localhost", "-c", "user.name=factory",
                      "add", "-A"],
                     ["git", "-c", "user.email=fix@localhost", "-c", "user.name=factory",
                      "commit", "-q", "--no-verify", "-m", "base"]):
            rc, _, err = _run(argv, scratch)
            if rc != 0:
                raise FixRefused(f"could not snapshot the base tree: {err.strip()[:200]}",
                                 config_error=True)
        for rel, text in after.items():
            with open(os.path.join(scratch, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        rc, out, err = _run(["git", "diff", "--unified=3"], scratch)
        if rc != 0:
            raise FixRefused(f"could not compute the diff: {err.strip()[:200]}", config_error=True)
        return out
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ── the prompt ────────────────────────────────────────────────────────────────
MAX_PREVIOUS_FAILURE_CHARS = 1200
MAX_EVIDENCE_CHARS = 900


def _evidence_lines(ticket: dict[str, Any]) -> str:
    """What the probe actually observed, when it recorded anything.

    Several probes have no reproducer by nature — a signature check has nothing to curl — and
    a ticket that carries only the probe's NAME left the model inferring the defect from the
    string "manifest_signature_integrity". Three autonomous attempts in a row then authored
    patches the pre-promotion gate rejected, each a different guess at what conforming meant.
    """
    evidence = ticket.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        return ""
    # The probe's own words first, and unlabelled — a criterion filed under "response_snippet"
    # beneath two digests reads like diagnostic noise. Measured: the manifest probe published
    # exactly what to sign, the text reached the prompt, and three more attempts still signed
    # something else because it arrived looking like telemetry.
    rows = []
    criterion = evidence.get("response_snippet") or ""
    if criterion:
        rows.append(f"  {str(criterion)[:MAX_EVIDENCE_CHARS]}")
    context = []
    for key in ("status_code", "request_digest", "response_digest", "request_snippet"):
        value = evidence.get(key)
        if value in (None, "", {}):
            continue
        context.append(f"    {key}: {str(value)[:MAX_EVIDENCE_CHARS]}")
    if context:
        rows.append("  observed:\n" + "\n".join(context))
    return "\n".join(rows)


def _previous_failure_block(previous_failure: str) -> str:
    """What the last attempt got wrong, put in front of the model.

    Without this the retry ladder is not a ladder. At temperature 0 the same prompt yields
    the same patch, so a refused attempt is re-derived verbatim: measured on a live run,
    three attempts produced the identical rejected patch in eight seconds and the job
    escalated having learned nothing. A refusal is the most useful thing we know.
    """
    text = " ".join(str(previous_failure or "").split())[:MAX_PREVIOUS_FAILURE_CHARS]
    if not text:
        return ""
    return f"""
YOUR PREVIOUS ATTEMPT WAS REFUSED
  {text}

Do not produce that patch again. Address the refusal explicitly: if it says a dependency is
unavailable, solve the finding with what the files below already import. If you cannot fix it
within that constraint, return a JSON object with an empty "files" object and put the reason in
"summary" — an honest refusal is worth more than a patch that will be rejected again.
"""


#: Noise floor for the "what you may import" line: everything a Python service has anyway.
_UNINTERESTING_DEPS = frozenset({
    "python", "pip", "setuptools", "wheel", "from", "run", "cmd", "copy", "workdir", "expose",
    "app", "slim", "no", "cache", "dir", "true", "false", "usr", "local", "bin", "src", "etc",
})


def available_libraries(declared: set[str] | None) -> str:
    """The line that answers "what may I import?" — because nothing else in the prompt does.

    The patch scope is source files; the model never sees the Dockerfile. Told only that
    "a library the build already declares is available", it has no way to learn WHICH, and it
    concluded there were none: measured, in its own words — "Cannot compute ed25519 signature
    without a crypto library; no dependency available" — while `cryptography` and
    `aimarket-oracle-core` were both installed in that very image.
    """
    names = sorted(
        n for n in importable_names(declared)
        if n and not n.startswith("_") and n not in _UNINTERESTING_DEPS and not n.isdigit()
        and len(n) > 2
    )
    if not names:
        return ""
    return ("\nALREADY INSTALLED, IMPORT FREELY\n  " + ", ".join(names[:60])
            + "\n  These are declared by this component's own build, so importing one is not "
              "adding a dependency. Anything NOT in this list is.\n")


# ── the read policy ────────────────────────────────────────────────────────────────
#
# The fixer runs with the WHOLE monorepo bind-mounted read-only, so its filesystem reach
# has always been total: `.env`, `data/secrets/*.key`, satellite provider keys, all of it.
# Nothing decided what a model was allowed to see — the write side had `DENIED_PATH_PREFIXES`
# and a scope map, and the read side had a regular expression.
#
# That asymmetry is the whole bug. A patch is reviewed by a gate; a disclosure is reviewed
# by nobody, and once a secret is in a prompt it has left the building.

#: Never read, never quote, never put in a prompt. Matched on the path, before any open().
#: Split by HOW each is matched, because guessing the kind from the string is how `.env`
#: was refused while `.env.production` sailed through: a leading-dot strip had already
#: eaten the dot the rule was looking for.

#: File extensions. Matched on the basename's suffix, so `keys.py` stays readable.
_SECRET_SUFFIXES: tuple[str, ...] = (
    ".key", ".pem", ".p12", ".pfx", ".jks", ".keystore", ".asc", ".ppk",
)
#: Dotfile stems. Matched as the whole basename or as `<stem>.<anything>`, so `.env`,
#: `.env.local` and `.env.production` all refuse while `environment.py` does not.
_SECRET_DOTFILES: tuple[str, ...] = (
    ".env", ".npmrc", ".pypirc", ".netrc", ".htpasswd", ".dockercfg",
)
#: Whole path segments. Everything beneath one of these directories is credential space.
_SECRET_SEGMENTS: tuple[str, ...] = (
    "secrets", "secret", ".ssh", ".gnupg", ".aimarket", ".aws", ".docker",
)
#: Basenames that are keys, whatever they are called next.
_SECRET_KEY_BASENAMES: tuple[str, ...] = ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")

#: Basenames that name a SUBJECT, not necessarily a secret: `wallet.json` is a wallet,
#: `wallet.ts` is the code that reads one. Refusing both looked thorough and was simply
#: wrong — a live audit of the container turned up twenty "credentials", nineteen of which
#: were ARGUS source and its build output. A guard that cries wolf at source is a guard that
#: gets widened until it protects nothing, and it would have refused the fixer a legitimate
#: reference file on the way.
_SECRET_DATA_STEMS: tuple[str, ...] = ("credentials", "wallet", "keystore", "secrets")
#: …but only when the extension says data rather than code.
_DATA_SUFFIXES: tuple[str, ...] = (
    "", ".json", ".txt", ".yaml", ".yml", ".ini", ".conf", ".cfg", ".dat", ".enc", ".b64",
)

#: Content that looks like live key material even in a file whose NAME is innocent. A source
#: file with a pasted token is exactly how the METIS outage happened, so the content is
#: checked as well as the path.
_SECRET_CONTENT = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)"
    r"|(\bsk-[A-Za-z0-9_\-]{16,})"                       # OpenAI-style and its many imitators
    r"|(\bghp_[A-Za-z0-9]{20,})|(\bgithub_pat_[A-Za-z0-9_]{20,})"
    r"|(\bxox[baprs]-[A-Za-z0-9\-]{10,})"                 # Slack
    r"|(\bAKIA[0-9A-Z]{16}\b)"                           # AWS access key id
    r"|(\b0x[0-9a-fA-F]{64}\b)"                          # a bare 32-byte hex key (EVM private key)
    r"|((?i:api[_-]?key|secret|passwd|password|token)\s*[:=]\s*[\"\']?[A-Za-z0-9_\-]{16,})",
)

_REDACTED = "«redacted by the read policy»"


def path_is_secret(rel_path: str) -> str:
    """The marker that forbids reading this path, or "" if it is readable.

    Deliberately blunt: a file that merely LOOKS like key material is refused. A false
    refusal costs the model one reference file; a false permit costs a key.
    """
    normalised = str(rel_path or "").strip().replace("\\", "/").lower()
    while normalised.startswith("./"):
        normalised = normalised[2:]
    normalised = normalised.lstrip("/")
    if not normalised:
        return ""
    parts = normalised.split("/")
    base = parts[-1]

    for segment in _SECRET_SEGMENTS:
        if segment in parts[:-1] or base == segment:
            return f"{segment}/"
    for suffix in _SECRET_SUFFIXES:
        if base.endswith(suffix):
            return suffix
    for stem in _SECRET_DOTFILES:
        if base == stem or base.startswith(stem + "."):
            return stem
    for name in _SECRET_KEY_BASENAMES:
        if base == name or base.startswith(name + "."):
            return name
    stem, _, ext = base.partition(".")
    if stem in _SECRET_DATA_STEMS and ("." + ext if ext else "") in _DATA_SUFFIXES:
        return stem
    return ""


def redact_secrets(text: str) -> tuple[str, int]:
    """Blank anything that reads as live key material. Returns (text, number of redactions)."""
    if not text:
        return text, 0
    redacted, n = _SECRET_CONTENT.subn(_REDACTED, text)
    return redacted, n


def read_is_denied(rel_path: str) -> str:
    """Why this file may not be shown to the model, or "" if it may.

    Two independent reasons, and they are not the same reason:
      * it holds credentials — disclosure;
      * it belongs to the auditor, the conductor or the payer — conflict of interest. The
        write side already refuses these; a fixer shown SKOPOS's deploy-chain verifier is
        being handed the source of the thing that judges its own patch.
    """
    secret = path_is_secret(rel_path)
    if secret:
        return f"credential material ({secret})"
    denied = path_is_denied(rel_path)
    if denied:
        return f"conflict of interest ({denied})"
    return ""


#: How much of a referenced module to show. Enough for a contract, not a whole subsystem.
MAX_REFERENCE_CHARS = 9000

#: A dotted path named in a criterion — `oracle_core.signing.Signer`, `aimarket_hub.signing`.
_DOTTED_PATH = re.compile(r"\b([a-z][a-z0-9_]{2,}(?:\.[a-z][a-z0-9_]*)+)")

#: Where a module named in a criterion might live in this monorepo.
_MODULE_ROOTS = ("", "oracles/core", "aimarket-hub", "momus", "skopos", "metis", "gaia")


def reference_sources(criterion: str, already_shown: set[str]) -> dict[str, str]:
    """Read-only source for modules the criterion tells the patch to IMPORT.

    "Import `oracle_core.signing.Signer`, do not reimplement it" is an instruction to use
    something the model has never seen: the patch scope is the component's own files. Told to
    call a function whose contract is invisible, it wrote its own — five different times, each
    a plausible canonicalisation, each rejected. A definition it can read is not scope: these
    files are shown and explicitly NOT patchable.
    """
    root = os.path.realpath(app_root())
    out: dict[str, str] = {}
    for dotted in dict.fromkeys(_DOTTED_PATH.findall(criterion or "")):
        parts = dotted.split(".")
        for depth in (len(parts), len(parts) - 1):
            if depth < 2:
                continue
            rel = os.path.join(*parts[:depth]) + ".py"
            for base in _MODULE_ROOTS:
                candidate = os.path.realpath(os.path.join(root, base, rel))
                if not candidate.startswith(root + os.sep) or not os.path.isfile(candidate):
                    continue
                shown = os.path.relpath(candidate, root)
                if shown in already_shown or shown in out:
                    continue
                refused = read_is_denied(shown)
                if refused:
                    # Not silent: a criterion that names a forbidden module is either a mistake
                    # worth seeing or an attempt worth seeing, and both look identical from here.
                    logger.warning("reference refused: %s — %s", shown, refused)
                    continue
                try:
                    with open(candidate, encoding="utf-8") as fh:
                        text = fh.read(MAX_REFERENCE_CHARS)
                except OSError:
                    continue
                text, hits = redact_secrets(text)
                if hits:
                    logger.warning("reference %s carried %d secret-looking value(s) — redacted",
                                   shown, hits)
                out[shown] = text
                break
            if out:
                break
    return out


def named_reference_sources(paths, already_shown: set[str]) -> dict[str, str]:
    """Serve the files the PROBE named, through the same policy as everything else.

    The regex over a criterion's prose works — measured, it pulls the right 8kB file for the
    manifest probe — and it works by luck: it fires only when a probe happens to phrase a
    contract as `package.module.Class`. A probe knows which file defines what it asserts, so
    it can say so. This reads what it named.

    Every path still goes through `read_is_denied`: a probe is not a principal, and "MOMUS
    asked for it" is not an entitlement. A named credential is refused exactly as a guessed
    one would be.
    """
    root = os.path.realpath(app_root())
    out: dict[str, str] = {}
    for raw in (paths or []):
        rel = str(raw or "").strip().lstrip("./")
        if not rel or rel in already_shown or rel in out:
            continue
        refused = read_is_denied(rel)
        if refused:
            logger.warning("probe named a file it may not have: %s — %s", rel, refused)
            continue
        candidate = os.path.realpath(os.path.join(root, rel))
        if not candidate.startswith(root + os.sep) or not os.path.isfile(candidate):
            logger.warning("probe named a file that is not in this build: %s", rel)
            continue
        try:
            with open(candidate, encoding="utf-8") as fh:
                text = fh.read(MAX_REFERENCE_CHARS)
        except OSError:
            continue
        text, hits = redact_secrets(text)
        if hits:
            logger.warning("named reference %s carried %d secret-looking value(s) — redacted",
                           rel, hits)
        out[rel] = text
    return out


def _reference_block(criterion: str, already_shown: set[str], named=None) -> str:
    # Named first: an explicit request beats a lucky parse, and a probe that names its
    # contract file should not also have to phrase it so a regex finds it.
    refs = named_reference_sources(named, already_shown)
    refs.update({k: v for k, v in reference_sources(criterion, already_shown).items()
                 if k not in refs})
    if not refs:
        return ""
    body = "\n\n".join(f"=== REFERENCE (read-only): {rel} ===\n{text}"
                         for rel, text in sorted(refs.items()))
    return ("\nTHE CODE THE CHECK ACTUALLY RUNS\n"
            "  The criterion above tells you to import something. Here it is. Read it, call it,\n"
            "  and do NOT copy its logic into your patch — you may not edit these files, and a\n"
            "  second copy of a shared contract is exactly what the criterion forbids.\n\n"
            + body + "\n")


def build_prompt(ticket: dict[str, Any], files: dict[str, str], previous_failure: str = "",
                 attempt: int = 1, max_attempts: int = 3,
                 declared: set[str] | None = None) -> str:
    listing = "\n\n".join(
        f"=== FILE: {rel} ===\n{text}" for rel, text in sorted(files.items()))
    ladder = (f"\nThis is ATTEMPT {attempt} of {max_attempts}. After the last one the finding "
              f"goes to a human.\n" if attempt > 1 else "")
    return f"""You are fixing ONE confirmed security finding in a production service.
{ladder}{_previous_failure_block(previous_failure)}{available_libraries(declared)}

FINDING
  id:        {ticket.get('finding_id')}
  component: {ticket.get('component')}
  probe:     {ticket.get('probe')}
  severity:  {ticket.get('severity')}
  what is wrong: {str(ticket.get('title') or '(only the probe name is known)')[:300]}
  why it matters: {str(ticket.get('detail') or '(not stated)')[:800]}
  reproducer:
{str(ticket.get('reproducer') or '(none — this probe has nothing to curl; read the check below)')[:2000]}

THE CHECK YOUR PATCH MUST PASS
  This exact probe is re-run against your patched build before anything ships, and it alone
  decides whether the fix counts. What it reports below is the ACCEPTANCE CRITERION.
  It is a requirement, not background reading — satisfy it literally.
{_evidence_lines(ticket)}
RULES
- Fix the ROOT CAUSE. A change that only makes the probe pass (special-casing its inputs, a flag, a
  hard-coded exception) is a worse outcome than no patch at all: it will be gated as fixed and the
  bug will still be there.
- Change as little as possible. Do not reformat, do not rename.
- Do not add a dependency the component's build does not already declare — that check reads the
  Dockerfile / requirements / pyproject, so a library ALREADY listed there is available to you and
  importing it is not "adding a dependency". If the check above names a module to import, import it:
  a rule against new dependencies is not a rule against using the ones the service already has.
- Keep the module's existing style and comment density.
- You may only modify the files listed below. There is no way to create or delete files.

OUTPUT
Return a single JSON object and nothing else:
{{"summary": "<one line, imperative, <=72 chars>",
  "files": {{"<path>": "<the COMPLETE new contents of that file>"}}}}
Include a file only if you actually changed it. Do not return a diff.

{listing}
{_reference_block(str((ticket.get("evidence") or {}).get("response_snippet") or ""), set(files), named=(ticket.get("evidence") or {}).get("reference_artifacts"))}
"""


def parse_reply(text: str, allowed: set[str]) -> tuple[str, dict[str, str]]:
    """Read the model's JSON, and refuse anything outside the declared scope."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("```", 2)[1] if body.count("```") >= 2 else body
        body = body[body.index("\n") + 1:] if body.lower().startswith(("json\n", "json\r")) else body
        body = body.strip().removeprefix("json").strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise FixRefused("the model did not return a JSON object")
    try:
        parsed = json.loads(body[start:end + 1])
    except json.JSONDecodeError as exc:
        raise FixRefused(f"the model's JSON did not parse: {exc}") from exc
    files = parsed.get("files")
    if not isinstance(files, dict) or not files:
        # The prompt OFFERS an honest refusal — empty `files`, the reason in `summary` — because
        # a patch that will be rejected again is worth less than being told why. Then this line
        # threw the reason away and reported "no file contents", so the one thing the loop asked
        # for arrived and was discarded. It is the most useful sentence in the whole exchange:
        # it is what the human who picks this up needs to read first.
        stated = str(parsed.get("summary") or "").strip()
        if stated:
            raise FixRefused(f"the model declined to patch and said why: {stated[:600]}")
        raise FixRefused("the model returned no file contents, and gave no reason")
    rewrites: dict[str, str] = {}
    for rel, text_ in files.items():
        rel = str(rel)
        denied = path_is_denied(rel)
        if denied:
            # Conflict of interest, refused before the scope is even consulted: the auditor,
            # the payer, the conductor and this gate are never patchable by the loop they run.
            raise FixRefused(
                f"the model tried to modify '{rel}', which is under '{denied}' — the "
                "remediation loop may not patch its own auditor, payer, conductor or gate"
            )
        if rel not in allowed:
            # The scope is the host's, not the model's. A path outside it is refused rather than
            # written, whatever the model's reasoning was.
            raise FixRefused(f"the model tried to modify '{rel}', which is outside the patch scope")
        if not isinstance(text_, str) or not text_.strip():
            raise FixRefused(f"the model returned empty contents for '{rel}'")
        if len(text_) > MAX_FILE_BYTES:
            raise FixRefused(f"the model's replacement for '{rel}' is implausibly large")
        rewrites[rel] = text_
    return str(parsed.get("summary") or "").strip()[:200], rewrites


def _top_level_imports(source: str) -> set[str]:
    """Root module names a file imports. Unparseable source yields nothing — the syntax
    error is caught by the build, and guessing imports out of broken code is worse."""
    import ast

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # relative import: local by construction
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


#: Where a component declares what its runtime image contains. Looked for beside each scoped
#: file and one directory up — enough for this repo's layout, and cheap to widen.
_BUILD_MANIFESTS = ("Dockerfile", "requirements.txt", "requirements.in", "pyproject.toml")


#: A PEP 508 requirement's NAME, without its version constraint, extras or environment marker.
_REQ_NAME = re.compile(r"^([A-Za-z][A-Za-z0-9._-]{1,60})")

#: Words that head a requirement-shaped token but name no package.
_MANIFEST_KEYWORDS = frozenset({
    "from", "run", "cmd", "copy", "workdir", "expose", "env", "arg", "entrypoint", "user",
    "label", "add", "python", "pip", "setuptools", "wheel", "true", "false", "usr", "local",
    "bin", "app", "src", "etc", "opt", "slim", "alpine", "bookworm", "latest",
})


def _requirement_names(filename: str, text: str) -> set[str]:
    """Distribution names a build manifest declares — the names, not every token in the file.

    Scanning a whole file for word-shaped tokens looked right against a hand-made fixture and
    produced nonsense against a real Dockerfile: version numbers, base-image tags and words out
    of comments all arrived as "libraries". Offering a model `0.115` and `against` to import is
    worse than offering it nothing, so this reads the places a requirement can actually be
    declared, and nowhere else.
    """
    found: set[str] = set()

    def _add(raw: str) -> None:
        candidate = raw.strip().strip("\"'").split(";")[0].split("[")[0].strip()
        m = _REQ_NAME.match(candidate)
        if not m:
            return
        head = m.group(1).rstrip("._-")
        if len(head) < 3 or head.lower() in _MANIFEST_KEYWORDS:
            return
        found.add(head.lower().replace("-", "_"))

    lower = filename.lower()
    if lower == "dockerfile":
        joined = re.sub(r"\\\s*\n\s*", " ", text)   # join backslash continuations
        for line in joined.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "pip install" not in stripped:
                continue
            for token in re.findall(r"\"[^\"]+\"|'[^']+'|\S+",
                                    stripped.split("pip install", 1)[1]):
                if not token.startswith("-"):
                    _add(token)
    elif lower.startswith("requirements"):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "-")):
                _add(stripped)
    elif lower == "pyproject.toml":
        for block in re.findall(r"dependencies\s*=\s*\[(.*?)\]", text, re.S):
            for a, b in re.findall(r"\"([^\"]+)\"|'([^']+)'", block):
                _add(a or b)
    return found


#: Vendor prefixes this monorepo publishes under. `aimarket-oracle-core` on PyPI is
#: `import oracle_core` in code, and telling a model the DISTRIBUTION name while the criterion
#: names the MODULE is a contradiction it resolves by importing neither.
_DIST_PREFIXES = ("aimarket_", "python_", "py_")


def import_names_for(distribution: str) -> set[str]:
    """Module names a distribution plausibly provides — what a patch would actually type.

    Asked properly where the package is installed here, guessed by convention where it is not:
    the fixer reads another component's build, so the library is usually absent from its own
    environment and `packages_distributions()` cannot answer.
    """
    name = distribution.strip().lower().replace("-", "_")
    if not name:
        return set()
    out = {name}
    for prefix in _DIST_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) + 2:
            out.add(name[len(prefix):])
    try:
        from importlib.metadata import packages_distributions

        for module, dists in (packages_distributions() or {}).items():
            if any(d.lower().replace("-", "_") == name for d in dists):
                out.add(module.lower())
    except Exception:  # noqa: BLE001 - convention is a fine fallback
        pass
    return out


def importable_names(declared: set[str] | None) -> set[str]:
    """Every module name the declared distributions make importable."""
    out: set[str] = set()
    for dist in declared or set():
        out |= import_names_for(dist)
    return out


def _declared_dependencies(scope_paths: list[str]) -> set[str]:
    """Packages the component's own build declares, so the guard knows what is installed.

    Without this the import check answers the wrong question. "Not imported by the files I am
    allowed to patch" is not the same as "not available at runtime": a component can perfectly
    well depend on a library none of its scoped modules happens to import yet, and refusing
    that patch tells the model to solve the problem without a tool it actually has. Read from
    the BUILD, not guessed — and an unreadable manifest declares nothing, so the guard stays
    conservative rather than silently permissive.
    """
    import re

    root = os.path.realpath(app_root())
    found: set[str] = set()
    seen_files: set[str] = set()
    for rel in scope_paths:
        directory = os.path.dirname(os.path.join(root, rel))
        for candidate_dir in (directory, os.path.dirname(directory)):
            for name in _BUILD_MANIFESTS:
                path = os.path.realpath(os.path.join(candidate_dir, name))
                if path in seen_files or not path.startswith(root + os.sep):
                    continue
                seen_files.add(path)
                try:
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read(200_000)
                except OSError:
                    continue
                found |= _requirement_names(name, text)
    return found


def first_unbound_name(before: dict[str, str], rewrites: dict[str, str]) -> str:
    """A module-level name the patched file uses but never defines or imports.

    A rewrite that drops an `import json` while keeping `json.dumps` PARSES perfectly and dies
    at `python -m` — measured: `NameError: name 'json' is not defined`, found by a candidate
    container, ninety seconds and one image build after it could have been found here. Only
    module scope is checked, and only names that are plainly loaded: this is a smoke test for a
    dropped import, not a linter, and it must never refuse a patch it merely does not
    understand.
    """
    import ast
    import builtins

    known_builtins = set(dir(builtins))
    for rel, text in sorted(rewrites.items()):
        if not str(rel).endswith(".py"):
            continue
        try:
            tree = ast.parse(text, filename=str(rel))
        except (SyntaxError, ValueError):
            continue  # first_syntax_error owns that case
        bound: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                bound |= {(a.asname or a.name.split(".")[0]) for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                bound |= {(a.asname or a.name) for a in node.names}
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
                bound |= {a.arg for a in getattr(node.args, "args", [])} if hasattr(node, "args") else set()
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, (ast.comprehension,)):
                for tgt in ast.walk(node.target):
                    if isinstance(tgt, ast.Name):
                        bound.add(tgt.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
            elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
                bound |= set(node.names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in bound and node.id not in known_builtins:
                    return f"{rel}:{node.lineno}: '{node.id}' is used but never defined or imported"
    return ""


def first_syntax_error(rewrites: dict[str, str]) -> str:
    """The first Python file in the patch that will not compile, described the way python does.

    The model returns COMPLETE file contents, so a reply cut short by a token limit or a
    dropped closing quote produces a file that imports nowhere. Live: an unterminated
    triple-quoted string reached a built image and died at `python -m canary.canary`.
    """
    import ast

    for rel, text in sorted(rewrites.items()):
        if not str(rel).endswith(".py"):
            continue
        try:
            ast.parse(text, filename=str(rel))
        except SyntaxError as exc:
            return f"{rel}:{exc.lineno}: {exc.msg}"
        except ValueError as exc:
            return f"{rel}: {exc}"
    return ""


def new_third_party_imports(before: dict[str, str], after: dict[str, str],
                            declared: set[str] | None = None) -> set[str]:
    """Third-party modules the patch introduces that the component does not already use.

    The prompt says "do not add dependencies" and a model added one anyway: a canary patch
    imported `cryptography`, built cleanly — a Docker build only copies source — and the
    container then died at import. The candidate gate caught it, which is the gate working,
    but only after a full author→commit→push→build→start cycle, and the attempt was spent.
    A new import is checkable before any of that.

    Stdlib is never a new dependency, and neither is a module the component already imports
    (it is installed, or the component is already broken for other reasons). Local modules
    are recognised by the scope's own filenames.
    """
    import sys

    known: set[str] = set()
    for src in before.values():
        known |= _top_level_imports(src)
    local = set()
    for path in before:
        parts = str(path).replace("\\", "/").split("/")
        local.add(parts[-1].removesuffix(".py"))
        local |= set(parts[:-1])
    added: set[str] = set()
    for path, src in after.items():
        added |= _top_level_imports(src)
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    # The same set the prompt offers, by construction: a guard that refuses the import its own
    # criterion demands is the contradiction that produced three wasted attempts.
    installed = importable_names(declared)
    return {m for m in added - known - local - set(stdlib)
            if m and not m.startswith("_") and m.lower().replace("-", "_") not in installed}


# ── the entry point ───────────────────────────────────────────────────────────
#: A stronger model for repair rounds the gate keeps rejecting. UNSET by default and
#: deliberately so: which model to spend on is an operator's decision, not this file's. The
#: product pipeline has the same lever (AIFACTORY_GATE_FAILING_MODEL); the remediation loop
#: did not, so a finding the configured model cannot solve was retried with that same model
#: three times and escalated to a human — three identical-in-kind failures, no new information.
ESCALATION_MODEL_ENV = "AIFACTORY_REMEDIATION_ESCALATION_MODEL"


def escalation_model(attempt: int) -> str:
    """Which model this attempt should use, or "" for the router's own choice."""
    if attempt < 2:
        return ""
    return str(os.environ.get(ESCALATION_MODEL_ENV, "")).strip()


#: A deliberating council for the attempt that would otherwise become a human's problem.
#: Unset means the ladder stays single-model. METIS speaks the OpenAI chat-completions shape,
#: so this needs no provider plumbing — just a URL, a key, and which of its routes to ask.
COUNCIL_URL_ENV = "AIFACTORY_REMEDIATION_COUNCIL_URL"
COUNCIL_KEY_ENV = "AIFACTORY_REMEDIATION_COUNCIL_KEY"
COUNCIL_MODEL_ENV = "AIFACTORY_REMEDIATION_COUNCIL_MODEL"
COUNCIL_FROM_ATTEMPT_ENV = "AIFACTORY_REMEDIATION_COUNCIL_FROM_ATTEMPT"
#: The council gets its own, longer budget. A dozen model calls across several roles is not a
#: single completion, and the single-model ceiling (600s) cut it off mid-deliberation —
#: measured: at 600s the run died just past the synthesizer, so we paid for the preparation
#: and threw away the part that decides. At 900s the same run reached all three proposers, the
#: refiner, the aggregator and two judge passes. Twenty minutes of machine work is a far
#: better trade than calling an operator.
#:
#: It must stay BELOW the conductor's own wait (SKOPOS_FACTORY_TIMEOUT_S). If they are equal
#: the two clocks race and the conductor reports a timeout of its own instead of the council's
#: answer — the same "inner must not undercut outer" mistake as the 30s transport timeout
#: under a 600s budget, in the other direction.
COUNCIL_TIMEOUT_ENV = "AIFACTORY_REMEDIATION_COUNCIL_TIMEOUT_S"
DEFAULT_COUNCIL_TIMEOUT_S = 1200.0


def council_timeout_s() -> float:
    try:
        return float(os.environ.get(COUNCIL_TIMEOUT_ENV, "") or DEFAULT_COUNCIL_TIMEOUT_S)
    except ValueError:
        return DEFAULT_COUNCIL_TIMEOUT_S


def council_target(attempt: int) -> tuple[str, str, str] | None:
    """(url, key, model) when this attempt should go to the council, else None.

    The last rung, not the first: a council costs several model calls per answer, and the
    ordinary ladder solves most findings on attempt one. Escalating the METHOD — deliberation
    between models — is a different lever from escalating the MODEL, and it is the one left
    when three attempts by one model have each been rejected on the same grounds.
    """
    url = str(os.environ.get(COUNCIL_URL_ENV, "")).strip().rstrip("/")
    if not url:
        return None
    try:
        first = int(os.environ.get(COUNCIL_FROM_ATTEMPT_ENV, "3") or 3)
    except ValueError:
        first = 3
    if attempt < first:
        return None
    key = str(os.environ.get(COUNCIL_KEY_ENV, "")).strip()
    model = str(os.environ.get(COUNCIL_MODEL_ENV, "")).strip() or "metis-council"
    return url, key, model


#: Prepended when the question goes to a deliberating council. A council built for people has
#: a step people expect — "this is ambiguous, what did you mean?" — and it took it every time:
#: measured, `status: needs_clarification`, in a hundred seconds, with nobody on the other end
#: to answer. Ambiguity here has to be resolved by assumption and stated, not asked about.
AUTONOMOUS_CALLER_NOTE = (
    "YOU ARE ANSWERING A MACHINE, NOT A PERSON.\n"
    "There is nobody to ask. A request for clarification is the same as no answer at all: the "
    "attempt is spent and the finding goes to a human unfixed.\n"
    "If anything is ambiguous, pick the most reasonable reading, say which reading you picked "
    "in `summary`, and produce the patch anyway. A patch made on a stated assumption can be "
    "tested — the probe below will judge it in about a minute — and a question cannot.\n"
    "Only if no reading of the task admits a fix, return the empty-files refusal described "
    "below, with the reason.\n"
)


async def _generate_via_council(url: str, key: str, model: str, prompt: str,
                                cfg: Any) -> str:
    """One non-streaming call to an OpenAI-shaped council endpoint.

    Deliberately NOT routed through LLMRouter: the council is a peer service with its own
    budget and its own failure modes, and putting it in the provider table would let ordinary
    factory traffic fall over to it.
    """
    import httpx

    headers = {"content-type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": AUTONOMOUS_CALLER_NOTE + "\n" + prompt}],
        "temperature": 0.0,
        "max_tokens": int(getattr(cfg, "max_tokens", 0) or 32000),
    }
    budget = council_timeout_s()
    try:
        async with httpx.AsyncClient(timeout=budget) as client:
            response = await client.post(f"{url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException as exc:
        raise FixRefused(
            f"the council did not answer within {int(budget)}s") from exc
    except httpx.HTTPStatusError as exc:
        raise FixRefused(
            f"the council refused the request: HTTP {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise FixRefused(f"the council is unreachable: {type(exc).__name__}") from exc

    choice = (body.get("choices") or [{}])[0]
    cfg.finish_reason = str(choice.get("finish_reason") or "")
    content = (choice.get("message") or {}).get("content")
    if cfg.finish_reason == "abstained":
        # The council deliberated and declined to answer — its own confidence gate, most often.
        # That is a verdict worth reporting as one: seventeen minutes and a hundred thousand
        # tokens reaching the ladder as "no content" told nobody anything.
        detail = str(content or "")[:400]
        raise FixRefused(f"the council deliberated and declined to answer: {detail}")
    if not content:
        raise FixRefused("the council returned no content and gave no reason")
    return str(content)


# ── the exchange log ───────────────────────────────────────────────────────────────
#
# The job record keeps the model's ANSWER — the patch and its stated summary — and nothing
# about what the model was shown. Reading a case afterwards, that is half the picture and the
# wrong half: measured on this loop, "the model got it wrong" and "the model was shown the
# wrong thing" are completely different diagnoses with identical symptoms. Five repair attempts
# were read as model failure until someone looked at the prompt and found it was asking a model
# to break a documented invariant.
#
# Append-only, one line per call, separate from `jobs.jsonl` — which is rewritten whole on every
# state change and would carry a 17KB prompt per attempt through every rewrite.

#: Where the exchanges go. Under the fixer's data volume, so they survive a redeploy.
def exchange_log_path() -> str:
    """Resolved late: the data root is env-driven and tests point it at a temp directory."""
    explicit = os.environ.get("AIFACTORY_REMEDIATION_EXCHANGE_LOG", "").strip()
    if explicit:
        return explicit
    root = os.environ.get("AIFACTORY_DATA_ROOT", "/app/data")
    return os.path.join(root, "remediation_exchanges.jsonl")

#: A prompt carries whole source files. Keep the tail rather than the head — the ticket and the
#: reference block are at the top and reconstructible, the failure feedback is at the bottom and
#: is not.
MAX_LOGGED_PROMPT = 60_000
MAX_LOGGED_REPLY = 40_000


def log_exchange(*, finding_id: str, component: str, attempt: int, model: str,
                 prompt: str, reply: str, outcome: str) -> None:
    """Record what the model was asked and what it answered. Never raises.

    The read policy already refuses credential files, and scope files are redacted on the way
    in, so a prompt should carry no key material. `redact_secrets` runs again here anyway: this
    file is the one artefact of the whole loop that is meant to be read by a person later, and
    a second pass costs nothing against the chance that something reached the prompt by a path
    the policy has not met yet.
    """
    try:
        safe_prompt, p_hits = redact_secrets(prompt or "")
        safe_reply, r_hits = redact_secrets(reply or "")
        record = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finding_id": finding_id,
            "component": component,
            "attempt": attempt,
            "model": model,
            "outcome": outcome,
            "prompt_chars": len(prompt or ""),
            "reply_chars": len(reply or ""),
            "redactions": p_hits + r_hits,
            "prompt": safe_prompt[-MAX_LOGGED_PROMPT:],
            "reply": safe_reply[:MAX_LOGGED_REPLY],
        }
        path = exchange_log_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError) as exc:  # noqa: BLE001
        # A failure to journal must never fail a repair: the patch is the product, the record
        # is the account of it.
        logger.warning("could not record the exchange for %s: %s", finding_id, type(exc).__name__)


async def author_fix(ticket: dict[str, Any], *, llm_router: Any,
                     previous_failure: str = "", attempt: int = 1) -> AuthoredPatch:
    """Ticket → unified diff. Raises FixRefused for anything a retry would not fix."""
    from core.factory_hold import is_factory_hard_stopped
    from core.pipeline_cost_guard import assert_product_within_budget

    if not is_enabled():
        raise FixRefused(
            f"autonomous patch authoring is off on this build (set {ENABLED_ENV}=1 to enable it)",
            config_error=True)
    if is_factory_hard_stopped():
        # No code under web/backend/ consulted the hold before this route existed, so an operator who
        # had stopped the factory would still have seen it spend LLM budget writing patches.
        raise FixRefused("the factory is hard-stopped — refusing to author patches",
                         config_error=True)
    component, finding_id = check_ticket(ticket)
    if llm_router is None:
        raise FixRefused("no LLM router is configured on this build", config_error=True)

    before = _read_scope(component)
    # Explicitly, BEFORE the call, mirroring the pipeline's own guard chain. Relying on the router's
    # internal check alone would book the spend first and refuse afterwards.
    assert_product_within_budget(COST_PRODUCT_ID)

    from llm.factory_defaults import FACTORY_TIMEOUT_CODE_GENERATION_SEC
    from llm.provider import GenerationConfig
    cfg = GenerationConfig(
        temperature=0.0,                 # a patch is not a place for sampling variety
        product_id=COST_PRODUCT_ID,      # without this the per-product cap is a no-op
        # The prompt below ends in "Return a single JSON object and nothing else" — and this
        # was the one JSON-expecting caller in the repo that never asked the provider for it.
        # Every escalation the live loop produced with "the model did not return a JSON
        # object" was this line missing.
        json_mode=True,
        # A retry ladder asks the same question again on purpose. Served from cache, attempt 3
        # replayed attempt 2 byte for byte — measured live: the branch for attempt 3 was
        # published three seconds after attempt 2 was rejected, because no model ran.
        no_cache=True,
        # GenerationConfig defaults to 30s, and every provider passes it straight to the HTTP
        # client. This call asks for the COMPLETE contents of whole source files under
        # task_type="code_generation" — the task the repo already budgets 600s for. The outer
        # asyncio.wait_for(LLM_BUDGET_S) below looked like the timeout and was never reached:
        # the provider had already given up at thirty seconds.
        timeout_sec=FACTORY_TIMEOUT_CODE_GENERATION_SEC,
    )
    stronger = escalation_model(attempt)
    if stronger:
        cfg.model_override = stronger
        logger.info("remediation attempt %d: escalating to %s", attempt, stronger)
    declared = _declared_dependencies(list(before))
    prompt = build_prompt(ticket, before, previous_failure, attempt, declared=declared)
    council = council_target(attempt)
    used_model = ""
    try:
        if council:
            url, key, model = council
            used_model = model
            logger.info("remediation attempt %d: asking the council at %s (%s)", attempt, url, model)
            reply = await _generate_via_council(url, key, model, prompt, cfg)
        else:
            used_model = stronger or getattr(cfg, "model_override", "") or "router-default"
            reply = await _generate(llm_router, prompt, cfg)
    except Exception as exc:  # noqa: BLE001 - logged, then re-raised unchanged
        # A refusal is the most informative exchange there is, and it was the one never written
        # down: the reason arrived as a job note and the prompt behind it was gone.
        log_exchange(finding_id=finding_id, component=component, attempt=attempt,
                     model=used_model, prompt=prompt, reply="",
                     outcome=f"raised: {type(exc).__name__}: {str(exc)[:300]}")
        raise
    log_exchange(finding_id=finding_id, component=component, attempt=attempt,
                 model=used_model, prompt=prompt, reply=reply, outcome="answered")
    if getattr(cfg, "was_truncated", False):
        # Named for what it is, so the retry knows to answer smaller rather than to answer
        # differently. Without this the truncation arrived as a syntax error and the job
        # escalated on "the candidate did not start" — an infrastructure-shaped message for a
        # reply that simply ran out of room.
        raise FixRefused(
            "the model's answer was cut off by the output limit before it finished — return "
            "ONLY the files you actually changed, and keep each one as short as the fix allows")
    summary, rewrites = parse_reply(reply, set(before))
    unbound = first_unbound_name(before, rewrites)
    if unbound:
        raise FixRefused(f"the patch uses a name it does not define — {unbound}")
    broken = first_syntax_error(rewrites)
    if broken:
        # Caught here, in milliseconds, instead of by a container that will not start. A patch
        # that does not parse cost a commit, a push, an image build and a candidate launch
        # before anything noticed — and the job then escalated on "the candidate did not start",
        # which reads like an infrastructure fault rather than what it was: a truncated file.
        raise FixRefused(f"the patch does not parse — {broken}")
    added_deps = new_third_party_imports(before, rewrites, declared)
    if added_deps:
        # Refused here rather than discovered by a container that will not start: the build
        # cannot see it (it only copies source) and the runtime image is not ours to change
        # from inside a patch.
        raise FixRefused(
            "the patch adds "
            + ", ".join(f"'{m}'" for m in sorted(added_deps))
            + " — a dependency the component's runtime image does not have; fix it with what "
              "is already imported there")
    diff = diff_from_rewrites(before, {k: v for k, v in rewrites.items()})
    if not diff.strip():
        # A model that returned the file unchanged has not fixed anything. Reporting success here
        # would push an empty branch and have MOMUS gate the unpatched build.
        raise FixRefused("the model returned no actual change — nothing to commit")
    if len(diff.encode()) > MAX_DIFF_BYTES:
        raise FixRefused("the produced diff is too large to be a targeted fix")
    return AuthoredPatch(diff=diff, summary=summary or f"remediate {finding_id}",
                         files=sorted(rewrites), component=component, finding_id=finding_id)


async def _generate(llm_router: Any, prompt: str, cfg: Any) -> str:
    """One non-streaming call, with the budget errors left to propagate.

    `stream()` is deliberately not used: it bypasses both the per-product budget check and the
    output-token clamp that `generate()` applies."""
    import asyncio
    try:
        return await asyncio.wait_for(
            llm_router.generate(prompt, task_type="code_generation", config=cfg),
            timeout=LLM_BUDGET_S)
    except asyncio.TimeoutError as exc:
        raise FixRefused(f"the model did not answer within {int(LLM_BUDGET_S)}s") from exc
