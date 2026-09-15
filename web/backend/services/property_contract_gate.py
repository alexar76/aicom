"""Run the operator's declared properties against the built product.

Every gate in this pipeline is structural. ``api_contract_check`` asks whether the routes match,
``frontend_build_check`` whether the bundle builds, ``product_demo_journey`` whether a real
account can log in, ``duplicate_module_check`` whether the modules resolve. Not one of them can
see that a function is **wrong while being well-formed**, and that is the failure mode of every
product whose value is a claim about its own output — a verifier, a sampler, a signer, a meter,
a settlement split.

The three incidents this gate is built from are all one defect wearing different clothes:

* ``platon`` signed a randomness output that was never derived from its committed entropy, with
  the real key, so the proof verified anything you handed it. Shipped twice, in two copies.
  (``oracles/oracles/platon/backend/tests/test_randomness.py:117``)
* ``sortes`` emitted ``alpha`` as bare hex and decoded it as UTF-8, so the prover hashed 9 bytes
  and the verifier hashed 18 — **every honest proof it issued verified as false**, in a paid
  verification capability. (``oracles/oracles/sortes/tests/test_vrf.py``)
* the hub's pipeline bill of materials is signed with no algorithm and no key in the document,
  and the read route appends a field *after* signing, so a buyer's verifier cannot succeed.

None of them crash. All of them return plausible JSON. Each was found by a person staring at
the composition of two functions, which is not a thing a pipeline can be relied on to do.

So the charter may state properties, and this gate executes them. The five kinds are chosen
because each maps onto a defect above rather than onto a textbook:

``deterministic``   same inputs, same output — catches an unseeded ``random``, a clock read,
                    an iteration order leaking into a result.
``sensitive``       changing the named input must change the output. This is the vacuous-proof
                    gate in general form, and it is the one that catches "the answer does not
                    actually depend on the evidence it cites".
``roundtrip``       ``inverse(target(x)) == x`` — catches prover and verifier disagreeing on a
                    wire format, which is invisible until you compose them.
``distinct``        no duplicates in the output — a k-of-n draw without replacement that repeats
                    an element is wrong in a way no schema notices.
``uniform``         the output distribution passes a chi-square goodness-of-fit test against
                    uniform. A biased sampler is indistinguishable from a fair one on any single
                    call, which is exactly why prose review cannot catch it.

Product code is agent-written and is therefore run **out of process, with a scrubbed
environment**: the ecosystem audit already found generated code inheriting ``os.environ``, and a
gate that hands the factory's secrets to the code under test would be a worse defect than the
one it is looking for.

The blocking bar follows the house rule from ``charter_fidelity``: fail on the unambiguous case.
``sensitive`` fails only when *every* varied input produced an identical output — a result that
has exactly one explanation — and reports the distinct-output ratio otherwise without blocking.

Findings carry ``severity`` from the repair pipeline's own vocabulary (critical/high/medium/low,
since ``core.repair_batches`` maps anything else to medium and would turn a note into work) and
an explicit ``blocking`` flag, which is what decides pass/fail.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 120.0
# Trials above this make a slow target dominate the QA stage; the operator's number is honoured
# up to here and the cap is reported so a silently reduced run cannot read as the requested one.
MAX_TRIALS = 200_000

_SENTINEL = "__PROPERTY_CONTRACT_RESULT__"

# Power the uniformity check must have against the canonical bias before "did not reject" is
# allowed to mean "uniform". 0.80 is the textbook default and it is the wrong one here: at
# exactly the required sample size it lets the biased sampler through one run in five, and
# measured on the fixture the margin was chi2=32.01 against a critical value of 31.43 — a
# coin-flip away from approving modulo bias. 0.95 costs ~40% more trials (89k vs 63k for 12
# buckets, both a few seconds) and misses one run in twenty.
UNIFORM_POWER = 0.95

# Runs inside the child. Kept as a string rather than a module so the child imports nothing of
# the factory: its sys.path is the product's, not ours, and a product module named `core` or
# `agents` must not shadow ours or be shadowed by it.
_RUNNER = r'''
import json, sys, importlib, math, statistics

SENTINEL = "__PROPERTY_CONTRACT_RESULT__"
MAX_TRIALS_CAP = __MAX_TRIALS__

def emit(payload):
    sys.stdout.write("\n" + SENTINEL + json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()

def canon(value):
    """A comparable, hashable rendering of a result. json first so dict key order and
    int/float equality behave; repr as the fallback for objects json cannot reach."""
    try:
        return json.dumps(value, sort_keys=True, default=repr)
    except Exception:
        return repr(value)

def load(target):
    """Import `module:callable`, and on failure say exactly which half is wrong.

    This gate BLOCKS, so a bad target holds every round. "could not import" leaves the
    developer agent guessing between a missing module, a typo in the path and a renamed
    function, and a guess costs a whole round. Naming the miss — and listing what the module
    actually exports — turns that into a one-round fix.
    """
    mod_name, _, attr = target.partition(":")
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        raise LookupError(
            "cannot import module %r (%s). The charter's property targets this module; "
            "either create it or tell the operator the real path." % (mod_name, exc)
        ) from None
    obj = mod
    walked = []
    for part in attr.split("."):
        if not hasattr(obj, part):
            public = sorted(
                n for n in dir(obj)
                if not n.startswith("_") and callable(getattr(obj, n, None))
            )
            where = mod_name + ("." + ".".join(walked) if walked else "")
            raise LookupError(
                "module %r imported fine, but %r has no attribute %r. Callables it does "
                "export: %s. Rename yours to match the charter, or the charter to match "
                "yours — do not add a wrapper just to satisfy this." % (
                    mod_name, where, part, ", ".join(public[:15]) or "(none)")
            ) from None
        obj = getattr(obj, part)
        walked.append(part)
    if not callable(obj):
        raise LookupError(
            "%s resolves to a %s, not a callable — a property needs a function to call."
            % (target, type(obj).__name__)
        )
    return obj

def vary(value, i):
    """Deterministically produce the i-th distinct variant of an argument value.

    Deterministic on purpose: a property that fails must fail again on the next run, or the
    finding is unactionable and gets ignored.
    """
    if isinstance(value, bool):
        return not value if i % 2 else value
    if isinstance(value, int):
        return value + i + 1
    if isinstance(value, float):
        return value + (i + 1)
    if isinstance(value, str):
        return "%s-%d" % (value, i + 1)
    if isinstance(value, (list, tuple)):
        return list(value) + [i + 1]
    if isinstance(value, dict):
        out = dict(value)
        out["__vary__"] = i + 1
        return out
    return "%r-%d" % (value, i + 1)

def run(prop):
    kind = prop["kind"]
    args = dict(prop.get("args") or {})
    fn = load(prop["target"])
    trials = int(prop.get("trials") or 32)

    if kind == "deterministic":
        first = canon(fn(**args))
        for i in range(1, trials):
            if canon(fn(**args)) != first:
                return {"ok": False, "reason": "output changed between identical calls",
                        "detail": "call %d of %d differed" % (i + 1, trials)}
        return {"ok": True, "detail": "%d identical calls" % trials}

    if kind == "sensitive":
        name = prop["vary"]
        if name not in args:
            return {"ok": False, "reason": "vary argument absent",
                    "detail": "%r is not in args" % name}
        seen = set()
        for i in range(max(2, trials)):
            call = dict(args)
            call[name] = vary(args[name], i)
            seen.add(canon(fn(**call)))
        if len(seen) <= 1:
            return {"ok": False, "reason": "output does not depend on %s" % name,
                    "detail": "%d different values of %r all produced one identical output"
                              % (max(2, trials), name)}
        return {"ok": True, "detail": "%d distinct outputs over %d varied inputs"
                                      % (len(seen), max(2, trials))}

    if kind == "distinct":
        for i in range(trials):
            call = dict(args)
            out = fn(**call)
            try:
                items = list(out)
            except TypeError:
                return {"ok": False, "reason": "output is not a sequence",
                        "detail": "kind 'distinct' needs an iterable result, got %s"
                                  % type(out).__name__}
            keys = [canon(x) for x in items]
            if len(set(keys)) != len(keys):
                dupes = sorted({k for k in keys if keys.count(k) > 1})
                return {"ok": False, "reason": "duplicate elements in output",
                        "detail": "trial %d returned %d items with %d distinct; repeated: %s"
                                  % (i + 1, len(keys), len(set(keys)), ", ".join(dupes[:3]))}
        return {"ok": True, "detail": "%d trials, no duplicates" % trials}

    if kind == "uniform":
        name = prop["vary"]
        buckets = int(prop["buckets"])
        trials = min(int(prop["trials"]), MAX_TRIALS_CAP)
        alpha = float(prop.get("alpha") or 0.001)
        if name not in args:
            return {"ok": False, "reason": "vary argument absent",
                    "detail": "%r is not in args" % name}
        counts = {}
        n = 0
        for i in range(trials):
            call = dict(args)
            call[name] = vary(args[name], i)
            out = fn(**call)
            items = out if isinstance(out, (list, tuple, set, frozenset)) else [out]
            for item in items:
                counts[canon(item)] = counts.get(canon(item), 0) + 1
                n += 1
        if n == 0:
            return {"ok": False, "reason": "no observations",
                    "detail": "target produced nothing over %d trials" % trials}
        # The child MEASURES; the parent JUDGES. Every statistical decision — critical value,
        # power, required sample size — lives in the gate module where it is unit-testable,
        # because the first version of this file buried the sizing arithmetic in this string
        # and a mis-sized test that approves a biased sampler is the exact defect the gate
        # exists to prevent.
        observed_cats = len(counts)
        # The declared bucket count is what fixes the degrees of freedom, so a mismatch in
        # EITHER direction has to stop the test rather than be absorbed into it. Fewer
        # categories than declared is the interesting one — a sampler that can never emit some
        # of the population is a fairness defect, and it is also exactly what a truncated
        # index or an off-by-one range looks like. More categories than declared means the
        # charter and the target disagree about the output space, and chi-square against the
        # wrong df would turn that into a confident number about nothing.
        if observed_cats != buckets:
            direction = "only" if observed_cats < buckets else "as many as"
            return {"ok": False,
                    "reason": "output range does not match the declared %d buckets" % buckets,
                    "detail": "%s %d distinct values appeared over %d trials (n=%d). %s"
                              % (direction, observed_cats, trials, n,
                                 "A value the sampler can never produce is a fairness defect."
                                 if observed_cats < buckets else
                                 "Fix `buckets` in the charter, or the target's output space.")}
        expected = n / float(buckets)
        chi2 = sum((c - expected) ** 2 / expected for c in counts.values())
        return {"ok": None, "measurement": {"chi2": chi2, "df": buckets - 1, "n": n,
                                            "buckets": buckets, "alpha": alpha}}

    if kind == "roundtrip":
        inv = load(prop["inverse"])
        name = prop.get("vary") or (list(args)[0] if args else None)
        if name is None:
            return {"ok": False, "reason": "nothing to round-trip",
                    "detail": "declare args, and vary: <arg> for the value to recover"}
        for i in range(trials):
            call = dict(args)
            value = vary(args[name], i) if name in args else vary("seed", i)
            call[name] = value
            forward = fn(**call)
            back = inv(forward) if not isinstance(forward, dict) else inv(**forward)
            if canon(back) != canon(value):
                return {"ok": False, "reason": "round-trip did not recover the input",
                        "detail": "trial %d: %s -> %s" % (i + 1, canon(value)[:80], canon(back)[:80])}
        return {"ok": True, "detail": "%d round-trips recovered the input" % trials}

    return {"ok": False, "reason": "unsupported kind", "detail": kind}

def main():
    spec = json.loads(sys.argv[1])
    for entry in spec["properties"]:
        try:
            entry["result"] = run(entry)
        except Exception as exc:
            import traceback
            entry["result"] = {
                "ok": False,
                "reason": "property raised %s" % type(exc).__name__,
                "detail": (str(exc) or repr(exc))[:400],
                "traceback": traceback.format_exc()[-800:],
            }
    emit({"properties": spec["properties"]})

main()
'''.replace("__MAX_TRIALS__", str(MAX_TRIALS))


def chi2_upper(alpha: float, df: int) -> float:
    """Upper-tail chi-square critical value, via Wilson-Hilferty.

    No scipy in the factory image, and pulling one in for a gate would be a poor trade. The
    approximation is good for ``df >= 8``, which is why ``judge_uniform`` declines to gate below
    that instead of gating badly.
    """
    import math
    import statistics

    z = statistics.NormalDist().inv_cdf(1.0 - alpha)
    return df * (1.0 - 2.0 / (9.0 * df) + z * math.sqrt(2.0 / (9.0 * df))) ** 3


def modulo_bias_w(buckets: int, draw_bits: int = 8) -> float:
    """Cohen's *w* for the canonical bug: ``uniform_draw_of_draw_bits % buckets``.

    This is the effect size a uniformity check has to be able to see, because it is the bias
    that actually gets written. With a one-byte draw and 12 buckets, ``256 = 21*12 + 4``, so
    four buckets get 22 chances and eight get 21 — a 4.8% excess, invisible in any single draw
    and invisible to an underpowered test. Returns 0.0 when ``buckets`` divides the draw space
    exactly, i.e. when there is no modulo bias to detect.
    """
    import math

    if buckets < 2:
        return 0.0
    m = 1 << draw_bits
    base, extra = divmod(m, buckets)
    q = 1.0 / buckets
    total = 0.0
    for i in range(buckets):
        p = (base + (1 if i < extra else 0)) / float(m)
        total += (p - q) ** 2 / q
    return math.sqrt(total)


def noncentrality_for_power(crit: float, df: int, power: float = UNIFORM_POWER) -> float:
    """Smallest chi-square non-centrality detectable at ``power``, found by bisection.

    Patnaik's normal approximation to the non-central chi-square: the test rejects when the
    statistic exceeds ``crit``, and the statistic is approximately normal with mean ``df+λ`` and
    variance ``2(df+2λ)``. Bisection rather than a closed form because the closed form is
    implicit in λ, and a wrong algebraic rearrangement here would silently mis-size every run
    the gate approves — which is the failure this whole power check exists to prevent.
    """
    import math
    import statistics

    z = statistics.NormalDist().inv_cdf(power)

    def reach(lam: float) -> float:
        return (df + lam) - z * math.sqrt(2.0 * (df + 2.0 * lam)) - crit

    lo, hi = 0.0, max(4.0 * crit, 100.0)
    while reach(hi) < 0 and hi < 1e9:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if reach(mid) < 0:
            lo = mid
        else:
            hi = mid
    return hi


def judge_uniform(measurement: dict[str, Any], *, detect: float = 0.0) -> dict[str, Any]:
    """Turn a chi-square measurement into a verdict, refusing to confuse the two failures.

    **A non-significant result is not a uniform distribution.** Measured while building this
    gate: a sampler doing ``byte % 12`` — textbook modulo bias, the bug this check is for —
    produced ``chi2=19.17`` against a critical value of ``31.43`` at ``n=24000``, and the first
    version of this gate reported it as a pass. The bias was real; the test simply could not see
    it. A fairness gate that answers "probably fine" when it means "I could not tell" is worse
    than no gate, because the product it approves ships a fairness claim on its authority.

    So failing to reject only counts as uniform when the run demonstrably had the power to
    reject the canonical bias for that bucket count. Otherwise the verdict is a charter problem
    with the sample size the operator needs, which is actionable, rather than a green tick.
    """
    import math

    chi2 = float(measurement["chi2"])
    df = int(measurement["df"])
    n = int(measurement["n"])
    buckets = int(measurement["buckets"])
    alpha = float(measurement["alpha"])

    if df < 8:
        return {
            "ok": True,
            "detail": (
                f"chi2={chi2:.2f} df={df} — not judged: the critical-value approximation needs "
                f"df >= 8, so declare buckets >= 9 to gate on uniformity."
            ),
        }

    crit = chi2_upper(alpha, df)
    if chi2 > crit:
        return {
            "ok": False,
            "reason": "distribution is not uniform",
            "detail": f"chi2={chi2:.2f} exceeds the {alpha:.4g} critical value {crit:.2f} "
                      f"(df={df}, n={n})",
        }

    w_target = float(detect or 0.0)
    default_used = False
    if w_target <= 0.0:
        w_target = modulo_bias_w(buckets, 8)
        default_used = True
    if w_target <= 0.0:
        # buckets divides 256 exactly, so single-byte modulo is unbiased here and there is no
        # canonical effect to demand. Say so rather than inventing one.
        return {
            "ok": True,
            "detail": (
                f"chi2={chi2:.2f} within {crit:.2f} (df={df}, n={n}). Single-byte modulo is exact "
                f"for {buckets} buckets, so no default effect size applies — declare "
                f"`detect: <w>` to gate on a specific bias."
            ),
        }

    lam_req = noncentrality_for_power(crit, df, UNIFORM_POWER)
    n_req = int(math.ceil(lam_req / (w_target * w_target)))
    source = (
        f"single-byte modulo bias for {buckets} buckets is"
        if default_used
        else "the declared target is"
    )
    if n < n_req:
        return {
            "ok": False,
            "reason": "uniformity test is underpowered",
            "detail": (
                f"chi2={chi2:.2f} did not exceed {crit:.2f}, but at n={n} this test can only "
                f"detect a deviation of w>={math.sqrt(lam_req / n):.4f}, and {source} "
                f"w={w_target:.4f}. That is not evidence of uniformity: raise trials until there "
                f"are >={n_req} observations ({UNIFORM_POWER:.0%} power at alpha={alpha:.4g})."
            ),
        }
    return {
        "ok": True,
        "detail": (
            f"chi2={chi2:.2f} within {crit:.2f} (df={df}, n={n}); powered to detect w>="
            f"{w_target:.4f}, and {source} w={w_target:.4f}"
        ),
    }


def _sys_path_entries(code_dir: Path) -> list[str]:
    """Where a generated product's importable root actually is.

    Both layouts ship: ``app/main.py`` at the root and ``backend/app/main.py`` one level down.
    A runtime gate in this pipeline once could never pass the nested one because it assumed the
    flat layout, so both go on the path and the target's own import decides which is real.
    """
    entries = [str(code_dir)]
    for nested in ("backend", "api", "server"):
        candidate = code_dir / nested
        if candidate.is_dir():
            entries.append(str(candidate))
    return entries


def run_properties(
    code_dir: Path | str,
    properties: list[dict[str, Any]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Execute declared properties in a child process. Always returns a dict."""
    code_dir = Path(code_dir)
    if not properties:
        return {"properties": [], "skipped": True, "reason": "no properties declared"}
    if not code_dir.is_dir():
        return {
            "properties": [],
            "skipped": True,
            "reason": f"no code directory at {code_dir}",
        }

    try:
        from core.child_env import scrub_child_env

        env = scrub_child_env(os.environ)
    except Exception as exc:  # pragma: no cover
        logger.warning("property gate: scrub_child_env unavailable (%s); using a minimal env", exc)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env["PYTHONPATH"] = os.pathsep.join(_sys_path_entries(code_dir))
    env["PYTHONUNBUFFERED"] = "1"
    # Product code that reads a database or calls out is not this gate's business; the
    # properties are about pure computation, and a target that needs the network says so by
    # raising, which is reported as `property raised ...` rather than silently passing.
    env.setdefault("AIFACTORY_PROPERTY_GATE", "1")

    payload = json.dumps({"properties": properties})
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", _RUNNER, payload],
            cwd=str(code_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        return {"properties": [], "skipped": False, "error": "spawn_failed", "reason": str(exc)[:400]}

    try:
        stdout, stderr = proc.communicate(timeout=max(10.0, float(timeout_sec)))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except Exception:
            proc.kill()
        proc.communicate()
        return {
            "properties": [],
            "skipped": False,
            "error": "timeout",
            "reason": (
                f"properties did not finish in {timeout_sec:.0f}s — lower `trials`, or the target "
                f"is doing I/O a property check should not need"
            ),
        }

    marker = stdout.rfind(_SENTINEL)
    if marker < 0:
        # Product code prints freely; only the absence of the sentinel is a real failure, and
        # then the child's stderr is the only useful thing we have.
        return {
            "properties": [],
            "skipped": False,
            "error": "no_result",
            "reason": (stderr or stdout or "child produced no result").strip()[-600:],
        }
    try:
        parsed = json.loads(stdout[marker + len(_SENTINEL) :].strip())
    except ValueError as exc:
        return {"properties": [], "skipped": False, "error": "bad_result", "reason": str(exc)[:300]}

    # The child returns `ok: None` plus a raw measurement for anything whose verdict is a
    # statistical decision. Judging here keeps the sizing arithmetic out of the runner string
    # and inside tested code.
    for entry in parsed.get("properties") or []:
        result = entry.get("result") or {}
        if result.get("ok") is None and result.get("measurement"):
            try:
                entry["result"] = {
                    **judge_uniform(result["measurement"], detect=float(entry.get("detect") or 0.0)),
                    "measurement": result["measurement"],
                }
            except Exception as exc:
                logger.warning("property gate: cannot judge measurement: %s", exc)
                entry["result"] = {
                    "ok": False,
                    "reason": "measurement could not be judged",
                    "detail": str(exc)[:300],
                }

    parsed["skipped"] = False
    return parsed


def run_property_contract_check(
    product_id: str,
    data_root: str,
    charter: str,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """QA-stage entry point, shaped like the other module-health checks."""
    from core.charter_contracts import charter_contract_report

    report = charter_contract_report(charter or "")
    props = report["executable_properties"]
    malformed = [m for m in report["malformed"] if m["block"] == "executable property"]

    issues: list[dict[str, Any]] = [
        {
            "code": "executable_property_malformed",
            "severity": "critical",
            "file": "charter",
            "detail": (
                f"Charter block '{m['section']}' cannot be executed: {m['detail']}. "
                f"An unexecutable property reads as a checked guarantee and is not one."
            ),
        }
        for m in malformed
    ]

    if not props:
        return {
            "passed": not issues,
            "skipped": not issues,
            "reason": "no executable property declared" if not issues else "malformed properties",
            "declared": 0,
            "issues": issues,
        }

    code_dir = Path(data_root) / "code" / product_id
    outcome = run_properties(code_dir, props, timeout_sec=timeout_sec)

    if outcome.get("error"):
        # A property gate that cannot run is not a pass. It is the same epistemic position as
        # an unrun test suite, and this pipeline has twice mistaken one for the other.
        issues.append(
            {
                "code": "executable_property_not_run",
                "severity": "critical",
                "file": "charter",
                "detail": (
                    f"{len(props)} declared propert{'y' if len(props) == 1 else 'ies'} could not be "
                    f"executed ({outcome['error']}): {outcome.get('reason', '')}"
                ),
            }
        )
        return {"passed": False, "skipped": False, "declared": len(props), "issues": issues}

    checked = outcome.get("properties") or []
    for entry in checked:
        result = entry.get("result") or {}
        if result.get("ok"):
            continue
        issues.append(
            {
                "code": "executable_property_failed",
                "severity": "critical",
                "file": str(entry.get("target", "")).split(":")[0].replace(".", "/") + ".py",
                "detail": (
                    f"Property '{entry.get('name')}' ({entry.get('kind')}) does not hold: "
                    f"{result.get('reason', 'unknown')} — {result.get('detail', '')}"
                ),
            }
        )

    blocking = [i for i in issues if i.get("blocking", True)]
    return {
        "passed": not blocking,
        "skipped": False,
        "declared": len(props),
        "checked": len(checked),
        "issues": issues,
        "results": [
            {"name": e.get("name"), "kind": e.get("kind"), **(e.get("result") or {})}
            for e in checked
        ],
    }
