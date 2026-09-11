#!/usr/bin/env python3
"""Enqueue KLEROTERION (provable random sampling desk) — PAUSED on arrival.

Deliberately different from ``enqueue_relay_focus.py``: that script focused the factory on its
product and paused everything else. This one does the opposite. The product is created and then
immediately put on a per-product pipeline hold, so it sits in the queue without competing for
worker rounds. Focus mode is not touched at all, because Sentinel is mid-repair and switching
the factory's focus is what this script must NOT do.

Unpause with:

    python3 -c "from web.backend.services.product_followup import set_product_pipeline_on_hold; \\
                set_product_pipeline_on_hold('<product_id>', False)"

BLOCKING PREREQUISITE before unpausing: the charter pins ``sortes.vrf``, which reaches a
generated product only through the ``aimarket-oracle-sortes`` distribution
(``oracles/oracles/sortes/pyproject.toml``, ``packages = ["sortes"]``). If that distribution is
not on PyPI the pin cannot be satisfied and ``pinned_dependency_gate`` will correctly block every
round. Check with ``pip index versions aimarket-oracle-sortes`` and publish it first.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KLEROTERION_IDEA = """Build **KLEROTERION** — a provable-sampling desk for anyone who is required to select at
random and may be asked to prove it: internal audit pulling 20 of 500 contracts, QA pulling 30 units from a
batch, a committee drawing reviewers, an allocator handing out scarce slots.

The product is not "a random number generator". It is the certificate that ends the argument
"you picked the records that suited you". Core flow: the operator uploads or pastes a population,
the desk FREEZES it and publishes a commitment (digest of the population + the pinned oracle public key
+ k + the method id) BEFORE any randomness exists; the draw is then requested from the Sortes VRF oracle,
bound to that commitment; the desk renders a certificate containing the commitment, the VRF proof, the
selection and the verification recipe; and a standalone verifier page recomputes the whole thing in the
browser from a pasted certificate, with no call back to our server.

Core screens: operator login, population upload + freeze/commit, draw, certificate view and download,
public verifier page, and a draw history list. Product name in UI: **KLEROTERION**."""

ADMIN_INSTRUCTIONS = """Engineering charter — greenfield full_software, Vercel deploy required.

Stack:
- Python 3.12 + FastAPI backend, SQLite (`kleroterion.db`), session auth for operators (Argon2/bcrypt).
- React + Vite SPA in `frontend/` (operator console + public verifier route).
- Ship for **Vercel fullstack**: `public/` dist + `api/index.py` ASGI mount; relative asset paths only.

WHAT MAKES THIS PRODUCT CORRECT, AND WHERE THE LINE IS.
The value of this product is that a losing party can check the draw. That property is destroyed by
plausible-looking wrong code, so two things are gated mechanically and are not matters of judgement:
see the `pinned dependency` and `executable property` blocks below, and
docs/factory-charter-contracts.md for what they do.

Do NOT implement, wrap, "optimise" or re-derive any part of the VRF. It is an RFC 9381
ECVRF-EDWARDS25519-SHA512-TAI implementation that is byte-exact against the published Appendix B.3
test vectors in both directions, and a fresh implementation that merely looks self-consistent passes
every test you would think to write while being interoperable with nobody. Import it.

====== pinned dependency ======
module: sortes.vrf
symbols: prove, verify, proof_to_hash
requires: aimarket-oracle-sortes
why: RFC 9381 ECVRF-EDWARDS25519-SHA512-TAI, byte-exact against the Appendix B.3 vectors in both
     directions. Two earlier implementations in this ecosystem shipped proofs that verified
     anything, and one shipped a prover/verifier pair that rejected every honest proof.

Product flows (implement fully, not stubs):
1. Operator uploads or pastes a population (CSV or newline list, up to 100k rows). The desk stores it
   and computes `roster_digest` = sha256 over the canonical newline-joined rows.
2. FREEZE/COMMIT, and it must happen before any randomness exists: `POST /api/commitments` returns
   {commitment_id, roster_digest, k, method_id, oracle_public_key, created_at}. `alpha` for the draw is
   DERIVED from commitment_id — never chosen by the operator, never chosen after seeing the population.
   A commitment is immutable; a second draw against it returns the first draw.
3. DRAW: request the proof from the pinned VRF for the derived alpha, then select k of n from the frozen
   population using `app.sampling:select` (below). Store pi, beta, public_key and the selection.
4. CERTIFICATE: one JSON document carrying the commitment, alpha, pi, beta, the selection, the
   method_id, AND the algorithm identifier plus a reference to the public key INSIDE the document.
   Nothing may be added to the document after it is signed or rendered — a route that appends a field
   after signing is a defect this ecosystem has already shipped.
5. VERIFIER PAGE at `/verify` (no auth): paste a certificate and check, in the browser, without
   calling any API of ours:
     a. `roster_digest` equals sha256 of the pasted population (WebCrypto `SHA-256`);
     b. `alpha` is the value derived from `commitment_id` — recompute the derivation;
     c. the selection reproduces from `beta` — reimplement the same rejection sampling in
        TypeScript and show that it returns the identical indices.

   It must NOT attempt to verify the ECVRF proof itself, and must not pretend to. There is no
   ECVRF primitive in WebCrypto (its Ed25519 verifies signatures; ECVRF is a different
   construction — hash-to-curve, cofactor clearing, its own challenge), there is no ECVRF
   implementation in this repo's TypeScript, and the pinned `sortes.vrf` is Python and cannot be
   reached from a browser. So writing edwards25519 field arithmetic in TypeScript is the ONLY way
   to do step (d) in the page, and that is exactly the prohibition at the top of this charter —
   an unaudited curve implementation that looks self-consistent and interoperates with nobody.
   An earlier draft of this charter demanded "proof valid" here and was therefore impossible to
   satisfy honestly; this is the correction.

   Instead, for the proof, the page states the verification recipe and points OUTWARD: the suite
   is `ECVRF-EDWARDS25519-SHA512-TAI` (RFC 9381), the proof is the 80-byte `pi`, the public key
   is in the certificate, and ANY conformant implementation verifies it. Name at least one the
   reader can actually run, and say plainly that we are not asking them to trust our verifier.
   That is not a gap in the product — it is the reason byte-conformance to the RFC was worth the
   effort: `oracles/oracles/sortes/tests/test_sortes.py` proves our proofs match the published
   Appendix B.3 bytes AND that the RFC's own published proofs verify under our verifier, so a
   third party's checker and ours cannot disagree.

   Step (c) being a SECOND, independent implementation of the sampling is deliberate: two
   implementations agreeing is the check. Ship a committed vector file (population, alpha, k,
   expected indices) that both the Python `app.sampling:select` and the TypeScript one must
   reproduce, and a test on each side that reads it. If they ever disagree, the certificate is
   worthless and the product must say so rather than round the difference away.

`app.sampling:select(roster_digest, alpha, k, population)` is the one piece of new mathematics you
write. Requirements: derive bytes deterministically from the VRF output; select k WITHOUT replacement;
use rejection sampling so there is NO modulo bias; return indices in a deterministic order. It must be
a pure function with no I/O, importable as `app.sampling`, because the properties below execute it
directly.

====== executable property ======
name: the selection is reproducible
kind: deterministic
target: app.sampling:select
trials: 32
args: {"roster_digest": "a3f1c2", "alpha": "hex:00", "k": 1, "population": 50}

====== executable property ======
name: the selection depends on the randomness
kind: sensitive
target: app.sampling:select
vary: alpha
trials: 64
args: {"roster_digest": "a3f1c2", "alpha": "hex:00", "k": 1, "population": 50}

====== executable property ======
name: the selection depends on the frozen population
kind: sensitive
target: app.sampling:select
vary: roster_digest
trials: 64
args: {"roster_digest": "a3f1c2", "alpha": "hex:00", "k": 5, "population": 50}

====== executable property ======
name: no seat is drawn twice
kind: distinct
target: app.sampling:select
trials: 64
args: {"roster_digest": "a3f1c2", "alpha": "hex:00", "k": 12, "population": 50}

====== executable property ======
name: every seat is equally likely
kind: uniform
target: app.sampling:select
vary: alpha
buckets: 50
trials: 20000
alpha: 0.001
args: {"roster_digest": "a3f1c2", "alpha": "hex:00", "k": 1, "population": 50}

Note on that last property: 20000 trials is chosen, not guessed. Single-byte modulo bias over 50
buckets is Cohen's w = 0.0635, and detecting it at 95% power with alpha=0.001 needs 16902
observations. If you change `population`, recompute — the gate will tell you the number it needs and
will REFUSE to pass an underpowered run rather than report it as uniform.

Quality / gates:
- Distinct art direction: the kleroterion was the stone slab Athenians used to draw juries — carved
  stone, bronze tokens, allotment. Warm limestone + oxidised bronze, engraved type. NOT another
  dark-glass-cyan AI product, and NOT casino or lottery imagery: this is an instrument of procedure.
- `data-testid` on primary buttons; responsive; `prefers-reduced-motion`.
- Seed data: 1 operator account, a 500-row sample population, 2 completed draws with certificates.
- pytest for: commitment immutability, alpha derivation, certificate shape, verifier acceptance of a
  known-good certificate and rejection of a tampered one.
- README: local dev + Vercel notes + how a third party verifies a certificate without trusting us.

Scope: the honest vertical slice — freeze, draw, certificate, verifier — over many empty screens. A
beautiful console with an unverifiable certificate is a failed product; a plain one whose certificate
checks out is the product."""


def _preflight() -> str | None:
    """Refuse to run where the live store is unreachable. Returns an error message or None.

    Learned the hard way (docs/operations-traps.md T-12): ``core.paths.data_root()`` resolves to
    ``/app/data``, which is correct inside the container and does not exist on the factory host at
    all. Run as ``ssh my-vps 'python3 scripts/enqueue_kleroterion.py'`` this script reached a path
    that was not there, ``append_product_to_pipeline_state`` returned False, and the only signal
    was a generic "append failed" — which reads like a bug in the pipeline rather than "you are
    standing in the wrong filesystem". Nothing was written, but ten minutes went into finding out
    why. A script whose failure mode is indistinguishable from a different failure is worth this
    check.
    """
    from core.paths import data_root

    how_to_run = (
        "Run it inside the factory container, where the data root and the dependency set are the "
        "factory's own — note the script must be IN THE IMAGE, so rebuild first (T-12):\n"
        "    docker exec aicom-app-1 python /app/scripts/enqueue_kleroterion.py"
    )

    root = Path(data_root())
    if not root.is_dir():
        return (
            f"data_root() is {root} and it does not exist here, so the live pipeline store is "
            f"unreachable and nothing would be enqueued.\n\n{how_to_run}"
        )

    # The real blocker measured on the factory host: the system python3 there resolves a usable
    # data root but has no `aiosqlite`, so `append_product_to_pipeline_state` dies inside
    # `create_sync_pipeline_manager()` and reports only "append failed". Probe the exact
    # capability rather than a proxy for it.
    try:
        from core.pipeline_database import create_sync_pipeline_manager

        create_sync_pipeline_manager()
    except ImportError as exc:
        return (
            f"the SQL pipeline store is not reachable from this interpreter: {exc}.\n"
            f"This interpreter can import the factory's modules but lacks its dependencies, so "
            f"the append would fail after doing nothing.\n\n{how_to_run}"
        )
    except Exception as exc:
        return (
            f"the SQL pipeline store refused a connection: {type(exc).__name__}: {exc}\n\n"
            f"{how_to_run}"
        )
    return None


def main() -> int:
    problem = _preflight()
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 3

    from core.factory_hold import is_factory_on_hold
    from core.pipeline_product_pause import get_factory_focus_product_ids
    from core.pipeline_state_writer import append_product_to_pipeline_state
    from web.backend.services.product_followup import (
        is_product_pipeline_on_hold,
        set_product_pipeline_on_hold,
    )

    # Guard, not decoration: if focus mode is on, appending a product silently pauses nothing and
    # unpausing later would not be enough to make it run. Say so instead of leaving a surprise.
    focus_before = get_factory_focus_product_ids()

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": KLEROTERION_IDEA.strip(),
        "admin_instructions": ADMIN_INSTRUCTIONS.strip(),
        "delivery_profile": "full_software",
        "production_mode": False,
        "category": "saas",
        "tags": ["owner-request", "kleroterion", "vercel", "paused-on-arrival"],
        "on_demand": True,
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
        "metadata": {
            "delivery_profile": "full_software",
            "category": "saas",
            "source": "owner_kleroterion_enqueue",
            "paused_on_arrival": True,
            "prerequisite": (
                "aimarket-oracle-sortes must be installable from PyPI before unpausing, or the "
                "pinned-dependency gate blocks every round"
            ),
        },
    }

    if not append_product_to_pipeline_state(product):
        print("ERROR: append_product_to_pipeline_state failed", file=sys.stderr)
        return 1

    # Immediately, before the worker's next cycle can pick it up.
    set_product_pipeline_on_hold(product_id, True)
    held = is_product_pipeline_on_hold(product_id)
    if not held:
        print(
            f"ERROR: {product_id} was enqueued but the hold did not take — pause it by hand now",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "product_id": product_id,
                "pipeline_on_hold": held,
                "factory_on_hold": is_factory_on_hold(),
                "focus_ids_unchanged": focus_before == get_factory_focus_product_ids(),
                "focus_ids": get_factory_focus_product_ids(),
                "unpause": (
                    "python3 -c \"from web.backend.services.product_followup import "
                    f"set_product_pipeline_on_hold; set_product_pipeline_on_hold('{product_id}', False)\""
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
