"""Keep a repair round only if QA's own count says it helped.

Measured on one product across eight consecutive QA rounds:

===========  =======  ========  ======
round        total    fixed     NEW
===========  =======  ========  ======
20:37        20       18        17
05:47        17       18        15
06:05        15       15        13
06:25        10       10        5
06:45        16       9         15
07:02        15       10        9
09:17        26       14        25
===========  =======  ========  ======

114 distinct defects appeared over those rounds and **101 of them existed in exactly one
round**. Exactly one defect persisted across seven or more — and that one was an
unsatisfiable gate reading a spec that did not exist. So the plateau at 12–16 was never a
stubborn core the loop could not crack: the loop fixed almost everything it was told about
and broke almost as much again, every round. ``fixed ≈ new``, so the count stood still.

There *was* already a guard against this in the developer: snapshot the tree, score it, roll
the round back if the score got worse. It could not work, because its score was static —
unresolved imports, unbound names, unparseable files — while QA blocks on a frontend
TypeScript build, a booted app answering 5xx, a browser crawl and module health. Its
docstring claimed it measured "the same signal QA blocks on"; it did not. A round could
resolve one import and break the TS build, drop a DB column and 500 the demo journey, and
score as an improvement.

The fix is not a better proxy. QA already performs the real measurement every round — it
installs, builds, boots the app and sweeps it — so the accept/revert decision belongs at the
QA boundary, where the true number is, and costs nothing extra to obtain.

Two deliberate choices:

* **Equal is accepted.** Reverting on equality would discard rounds that traded one defect
  for another of the same weight, and some of those trades are real progress (a fixed feature
  for a new lint). Only a strictly worse round is thrown away.
* **Severity-weighted.** A round that turns one critical into three lows is an improvement,
  and a plain count would call it a regression and revert it.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# What a defect costs in the score. A crash outranks a lint by more than 4:1 in reality, but
# a steeper curve makes the guard revert rounds that fixed several small things while touching
# one big one — and those rounds are how a tree gets tidy enough to fix the big thing.
SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_DEFAULT_WEIGHT = 2

# Never archived, and never deleted by a restore. Installed or generated output is not the
# product: the first version of this guard tarred the whole tree and produced a **151 MB**
# archive for 58 source files, because ``frontend/node_modules`` alone is 150 MB+ of a 592 MB
# tree. Per round, per product, on a disk this project has already filled to 98% once.
# Excluding them is only half the fix — a restore that wipes what it did not archive would
# force a full ``npm install`` on every revert — so the restore merges instead of swapping.
EXCLUDED_DIRS = frozenset(
    {
        # The sandbox preview environments the QA tooling builds INSIDE the product tree:
        # two of them, 161 MB each, were 321 MB of a 592 MB "product". They are rebuilt on
        # demand and are not the product. (Excluding node_modules alone still left an 85 MB
        # archive, which is how these were found.)
        ".aicom_sandbox",
        "preview-venv",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "coverage",
        ".git",
    }
)


def _is_excluded(rel_parts: tuple[str, ...]) -> bool:
    return any(part in EXCLUDED_DIRS for part in rel_parts)


# Bumped whenever anything that produces the number changes: the gate whitelist, the severity
# weights, the dedup rules, or a detector's reported severity. A stored baseline was measured under
# the rules of its day, and comparing today's number to it is comparing two different units.
#
# This cost the best round of the evening. A round brought missing symbols from 9 down to 2 — the
# largest real improvement all day — and the guard reverted it at 7 -> 64 and put the nine back. The
# 64 was honest; the 7 was measured hours earlier, before `missing_symbol` became critical and before
# two dedup rules landed. Every round after a rules change loses to a number that no longer means
# what it meant, and the more the detectors improve the more work gets destroyed — the exact opposite
# of the intent.
#
# The tree fingerprint already handles "same tree, different measurement". This is its other half:
# same measurement machinery required, or re-anchor instead of judging.
# 5: the class-body forward-reference detector joined the developer's tree score. Bumping this is not
# optional bookkeeping — it is the whole mechanism, and forgetting it cost the best round of the night
# a second time. The backend E2E gate had just reported backend_e2e=True, meaning the app BOOTED, and
# the guard reverted that round on "7 -> 12" because the 7 was measured before the new term existed.
# 28: unstyled markup left the rollback score. A UI round that added one Tailwind
# token and eight semantic class names scored +5/+10, salvage could not keep any
# landing file, and three attempts restored a tree QA had already asked to restyle.
SCORING_RULES_VERSION = 28

# Only these gates vote on keeping a round. A whitelist rather than a blacklist, because a new
# gate must default to NOT deciding whether work is thrown away until someone shows it repeats.
#
# Established by measurement, not by taste. The same tree was measured twice — identical hash
# before and after — and these gates returned identical numbers both times (module_health 2,
# frontend_build 3, demo_journey 3; weight 26 and 26). Meanwhile the guard's stored baseline for
# that tree was 41, so fifteen points — over a third — came from terms outside that set: a browser
# crawl whose visual findings depend on render timing, an LLM spec-alignment judgement, a
# maintainability review and a methodology gate. Thirteen consecutive rounds were reverted on a
# number that was a third unrepeatable, including a ONE-file round that scored 71 against a
# baseline of 41.
#
# Everything else still reaches the developer as work. It simply does not get a vote.
GUARD_SCORED_GATES = frozenset(
    {
        "module health",       # static: missing symbols, duplicate tables, mesh contract, undefined names
        "frontend build",      # tsc/vite: deterministic for a given tree
        "demo journey",        # boots the app and sweeps declared endpoints
        "api contract",        # frontend call sites vs the route table
        "backend realism",     # deterministic inspection of responses
    }
)


def _gate_of(bug: Any) -> str:
    """The gate a finding came from, read off its title prefix (``Module health: …``)."""
    if not isinstance(bug, dict):
        return ""
    title = str(bug.get("title") or "")
    return title.split(":", 1)[0].strip().lower() if ":" in title else ""


# One broken import produces a finding in every gate that trips over it. Measured on a rejected
# round scoring 34 against a baseline of 26:
#
#   Module health: missing_symbol            CachedMeshReading      3
#   Demo journey: import_error               CachedMeshReading      3   <- same defect
#   Demo journey: demo_journey_boot_failed   …'CachedMeshReading'   3   <- same defect
#   Frontend build: Dashboard.tsx(2,10)                             3
#   Frontend build: Dashboard.tsx(3,10)                             3   <- same import block
#   Frontend build: Dashboard.tsx(4,10)                             3   <- same import block
#
# Two thirds of that weight is one symbol and one file's imports counted over and over. It makes
# the score a count of symptom LINES rather than of defects, and it lands unevenly: a round that
# fixes two missing symbols and breaks one new import can come out net-worse while being net-better,
# which is precisely how work that improved the product got thrown away.
#
# So the score counts root causes. The static gate that names the file to fix is the one that keeps
# its vote; the downstream observation of the same identifier does not vote twice.
_IDENT_RE = re.compile(r"'([A-Za-z_][A-Za-z0-9_.]*)'")
_FRONTEND_FILE_RE = re.compile(r"([\w./-]+\.(?:tsx?|jsx?|vue|svelte))")


def _text_of(bug: Any) -> str:
    if not isinstance(bug, dict):
        return ""
    return " ".join(str(bug.get(k) or "") for k in ("title", "detail", "description"))


def _identifiers_in(bug: Any) -> set[str]:
    """Names a finding is about: quoted symbols, missing modules, "never defines X"."""
    if not isinstance(bug, dict):
        return set()
    text = " ".join(
        str(bug.get(k) or "") for k in ("title", "detail", "description", "file", "module")
    )
    out = set(_IDENT_RE.findall(text))
    out |= set(re.findall(r"never defines (\w+)", text))
    out |= set(re.findall(r"No module named '([\w.]+)'", text))
    return {n for n in out if len(n) > 2}


def dedupe_root_causes(bugs: list[Any]) -> list[Any]:
    """Collapse findings that are the same defect seen through a different gate.

    Conservative on purpose: a downstream finding is dropped only when it names an identifier a
    static gate already reported, or when it is another compiler line about a file already counted.
    Anything with no such link keeps its vote — a missing module the static gates never saw is a
    real second defect, not a duplicate.
    """
    static_names: set[str] = set()
    has_duplicate_table = False
    for bug in bugs:
        if _gate_of(bug) == "module health":
            static_names |= _identifiers_in(bug)
            if "duplicate_tablename" in str((bug or {}).get("title") or ""):
                has_duplicate_table = True

    kept: list[Any] = []
    seen_frontend_files: set[str] = set()
    for bug in bugs:
        gate = _gate_of(bug)
        if gate == "frontend build":
            text = " ".join(
                str(bug.get(k) or "") for k in ("title", "detail", "description")
            ) if isinstance(bug, dict) else ""
            match = _FRONTEND_FILE_RE.search(text)
            if match:
                if match.group(1) in seen_frontend_files:
                    continue
                seen_frontend_files.add(match.group(1))
            kept.append(bug)
            continue
        if gate and gate != "module health" and static_names & _identifiers_in(bug):
            continue
        # SQLAlchemy's MetaData is global to the app, so ONE duplicate declaration breaks the whole
        # model import — and the table it names in the error is decided by import order, not by a
        # second defect. Observed: the detector reports 'allowance_state' declared twice, while the
        # boot error says "Table 'invoke_audit_logs' is already defined", because the first pass
        # registered that table before failing and the retry tripped over its own leftovers.
        # Matching on the table name could never collapse these, so the rule is the error kind.
        if (
            has_duplicate_table
            and gate
            and gate != "module health"
            and "already defined" in _text_of(bug)
            and "invalidrequesterror" in _text_of(bug).lower()
        ):
            continue
        kept.append(bug)
    return kept


def critical_pressure(qa_result: Any) -> int | None:
    """How many CRITICAL findings the trusted gates report, or ``None`` if unreadable.

    Its own axis because the total is a blunt instrument at the end of a repair. Measured: a round was
    reverted at 14 -> 15 — one severity point — having closed two of the three missing attributes and
    introduced one lesser finding. Discarding it threw away the two fixes to avoid the one, and the
    next round started from the same tree and made the same trade, sixty-six times over.

    A critical is what stops the product working: a missing symbol, an attribute that is never
    declared, a broken contract with the mesh. If a round reduces the count of those, it moved the
    product forward even when the severity-weighted total ticked up, and the smaller findings it left
    behind are the next round's work.
    """
    if not isinstance(qa_result, dict):
        return None
    bugs = qa_result.get("bugs_found")
    if not isinstance(bugs, list):
        return None
    total = 0
    for bug in dedupe_root_causes(bugs):
        if not isinstance(bug, dict):
            continue
        gate = _gate_of(bug)
        if not gate or gate not in GUARD_SCORED_GATES:
            continue
        if str(bug.get("severity") or "").strip().lower() == "critical":
            total += 1
    return total


def backend_boots(qa_result: Any) -> bool | None:
    """Did the product's own backend start? ``None`` when the gate did not run.

    Its own axis for the same reason journey depth is: a round can make the static tree cleaner and
    the product deader in the same breath, and the defect score only sees the tree. Measured — the
    round that finished closing the ATLAS contract violations also broke a constructor call:

        demo_journey_boot_failed: TypeError: HeartbeatService.__init__() takes 1 positional argument
        backend_e2e: True -> False

    Defects fell from 32 to 27 because the tree really was cleaner, so the guard accepted a round
    that left the application unable to start. A product that does not boot has no qualities at all;
    no reduction in static findings can compensate for it.
    """
    if not isinstance(qa_result, dict):
        return None
    report = qa_result.get("backend_runtime_e2e")
    if not isinstance(report, dict) or report.get("skipped"):
        return None
    passed = report.get("passed")
    return bool(passed) if passed is not None else None


def preview_crashed(qa_result: Any) -> bool | None:
    """Did the headless browser see an uncaught exception? ``None`` if the gate did not run.

    Browser E2E is kept out of ``GUARD_SCORED_GATES`` because crawl noise is unrepeatable. The
    *throw* is not noise. Measured on Sentinel: a tree with E2E green and demo 76 B was replaced
    by demo 86 A that threw ``pageerror: Error`` twelve times. The demo-quality axis we added
    *accepted* that round (score rose) and later *reverted* the working tree (score fell). The
    page never painted; empty/toast in source still scored A. A product that throws before paint
    has no UI to grade.

    ``spec_alignment_llm`` and a11y-without-throw do not flip this bit — those are the next
    round's work on a page that actually loaded.
    """
    if not isinstance(qa_result, dict):
        return None
    report = qa_result.get("browser_preview_e2e")
    if not isinstance(report, dict):
        nested = qa_result.get("quality_gates")
        if isinstance(nested, dict):
            report = nested.get("browser_preview_e2e")
    if not isinstance(report, dict) or report.get("skipped"):
        return None
    issues = report.get("issues") or []
    if any("pageerror" in str(i).lower() for i in issues):
        return True
    page_errors = report.get("page_errors") or []
    if page_errors:
        return True
    if report.get("passed") is None and not issues:
        return None
    return False


def demo_quality_score(qa_result: Any) -> int | None:
    """The demo-quality integer, or ``None`` when the gate did not run.

    Its own axis because visual work and the defect total move in opposite directions on
    Sentinel. A round that added the mobile nav, empty/error/toast states — demo 66 C → 86 A —
    was reverted 3 → 9 for two unused TypeScript locals (TS6133). The successor deleted those
    locals by rewriting App.tsx back to an 18-line router, demo fell to 66 C, and the guard
    *accepted* it because the weighted total improved. Oscillation: visuals land, unused-var
    compile errors vote them off, the "fix" restores the stub.

    Demo/TZ findings are intentionally absent from ``GUARD_SCORED_GATES`` (render-timed crawl
    noise). The *score* of the static demo_quality gate is repeatable for a given tree, and
    a round that raises it while the backend still boots is the product getting a UI. A round
    that lowers it while the backend still boots is the product losing that UI, even when tsc
    got quieter.
    """
    if not isinstance(qa_result, dict):
        return None
    report = qa_result.get("demo_quality")
    if not isinstance(report, dict) or report.get("skipped"):
        return None
    score = report.get("score")
    try:
        return int(score)
    except (TypeError, ValueError):
        return None


def journey_depth(qa_result: Any) -> int | None:
    """How far the demo journey physically got, on its own axis: 2 = a token was obtained,
    1 = login answered 2xx without one, 0 = login was attempted and failed. ``None`` = no opinion
    (no journey ran, or the product has no login endpoint).

    This exists because depth and defect count move in opposite directions at a breakthrough.
    The round that finally made login return a token was reverted 14 -> 32 for six 401s, and its
    successor 14 -> 35 for six 500s — findings on endpoints that were unreachable one round
    earlier. A journey that gets strictly deeper cannot be a regression, whatever it finds there.
    """
    if not isinstance(qa_result, dict):
        return None
    journey = qa_result.get("demo_journey")
    if not isinstance(journey, dict):
        return None
    login = journey.get("login")
    attempts = login.get("attempts") if isinstance(login, dict) else None
    if not isinstance(attempts, list) or not attempts:
        return None
    if any(a.get("token") for a in attempts if isinstance(a, dict)):
        return 2
    if any(200 <= int(a.get("status") or 0) < 300 for a in attempts if isinstance(a, dict)):
        return 1
    return 0


def qa_defect_score(qa_result: Any) -> int | None:
    """Severity-weighted defect total from QA's own report, or ``None`` if unreadable.

    ``None`` means "no opinion" and must be treated as accept: a guard that cannot measure
    has no business throwing work away.
    """
    if not isinstance(qa_result, dict):
        return None
    bugs = qa_result.get("bugs_found")
    if not isinstance(bugs, list):
        return None
    total = 0
    for bug in dedupe_root_causes(bugs):
        gate = _gate_of(bug)
        if not gate:
            # A finding with no gate prefix came from the LLM reviewer, and its output differs
            # between two runs over identical code. Measured — a revert log finally named them:
            #
            #   9 new finding(s) this round did not have before —
            #   Generic exception handler hides all errors; Integration tests are flaky;
            #   Login test is too permissive; Missing required repository files…
            #
            # Three rounds in a row were reverted 14 -> 18, 20, 22 on that kind of arrival while the
            # static tree got BETTER (missing_attribute 3 -> 1). Opinions that appear and vanish
            # between runs cannot answer "is this round better than the last": they make the answer a
            # coin flip, and the coin was landing against every round that touched anything. They
            # still reach the developer as work; they just do not get a vote on the revert.
            continue
        if gate not in GUARD_SCORED_GATES:
            # Reported, not scored: this gate has not been shown to return the same number twice
            # for the same tree, and a term that does not repeat cannot answer "is this round
            # better than the last".
            continue
        if isinstance(bug, dict) and bug.get("scored_by_guard") is False:
            # A finding that does not repeat cannot be compared. The LLM reviewer's output
            # differs between two runs over identical code, and this score exists solely to ask
            # "is this round better than the last" — so an unrepeatable term makes the answer a
            # coin flip. Measured from one baseline tree: 67, 71, 84 and 106 for rounds touching
            # 21, 1 and 21 files; a one-file round outscored a twenty-one-file round. The finding
            # still reaches the developer as work, it just does not get a vote on the revert.
            continue
        sev = str((bug or {}).get("severity") or "").strip().lower() if isinstance(bug, dict) else ""
        total += SEVERITY_WEIGHTS.get(sev, _DEFAULT_WEIGHT)
    return total


def guard_enabled() -> bool:
    """On by default; ``AIFACTORY_ROUND_REGRESSION_GUARD=0`` turns it off."""
    return os.environ.get("AIFACTORY_ROUND_REGRESSION_GUARD", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _snapshot_path(product_id: str, data_root: Path) -> Path:
    return Path(data_root) / "backups" / "round-guard" / f"{product_id}.tar.gz"


def save_snapshot(product_id: str, code_dir: Path, data_root: Path) -> bool:
    """Store the tree as it stands — the state QA last measured. One slot per product.

    One slot, not a history: the only tree worth restoring is the last one with a known
    score, and keeping every round of an 85-file product filled a production disk to 98%
    once already.
    """
    src = Path(code_dir)
    if not src.is_dir():
        return False
    dest = _snapshot_path(product_id, data_root)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory and replace, so an interrupted snapshot
        # cannot leave a truncated archive that a later restore would unpack over good code.
        with tempfile.NamedTemporaryFile(
            dir=str(dest.parent), suffix=".partial", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
        with tarfile.open(tmp_path, "w:gz") as tar:
            for path in sorted(src.rglob("*")):
                rel = path.relative_to(src)
                if _is_excluded(rel.parts):
                    continue
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    continue
                tar.add(path, arcname=str(rel), recursive=False)
        tmp_path.replace(dest)
        return True
    except (OSError, tarfile.TarError) as exc:
        logger.warning("round guard: snapshot of %s failed: %s", product_id, exc)
        return False


def has_snapshot(product_id: str, data_root: Path) -> bool:
    return _snapshot_path(product_id, data_root).is_file()


def restore_snapshot(product_id: str, code_dir: Path, data_root: Path) -> bool:
    """Put the last measured tree back, without touching installed dependencies.

    A merge, not a swap. The archive deliberately omits ``node_modules`` and friends (see
    ``EXCLUDED_DIRS``), so replacing the directory wholesale would delete a 150 MB install and
    make every revert pay for a fresh ``npm install`` — QA's build would then be the slowest
    part of a round that produced nothing. Instead: overwrite what the snapshot holds, and
    delete only product files the snapshot does not have (which is how a duplicate module the
    round invented gets removed), leaving excluded trees exactly as they are.
    """
    archive = _snapshot_path(product_id, data_root)
    if not archive.is_file():
        return False
    target = Path(code_dir)
    staging = target.with_name(f"{target.name}.restoring")
    try:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                name = member.name.lstrip("./")
                # The archive is ours, but an extract that can escape its directory is a
                # foot-gun waiting for the day it is not.
                if name.startswith("/") or ".." in Path(name).parts:
                    logger.warning("round guard: refusing archive member %r", member.name)
                    return False
            tar.extractall(staging)  # noqa: S202 - members validated above

        kept: set[Path] = set()
        for path in sorted(staging.rglob("*")):
            rel = path.relative_to(staging)
            dest = target / rel
            if path.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            kept.add(rel)

        # Remove what the round added. Directories are pruned bottom-up afterwards so an
        # emptied package folder does not linger and read as a module.
        for path in sorted(target.rglob("*"), reverse=True):
            rel = path.relative_to(target)
            if _is_excluded(rel.parts):
                continue
            if path.is_file() and rel not in kept:
                path.unlink(missing_ok=True)
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        return True
    except (OSError, tarfile.TarError) as exc:
        logger.error("round guard: restore of %s failed: %s", product_id, exc)
        return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def tree_fingerprint(code_dir: Path) -> str | None:
    """A cheap, stable digest of the product's own files.

    The point is to recognise *the tree we already measured*. A round can end without changing
    anything — the developer's own coherence check rejects its attempts and restores the tree — and
    then QA measures the accepted tree again. Comparing that measurement to a stored number is
    comparing a tree to itself, and the only way it can differ is if the stored number came from a
    different measurement: an older set of detectors, or a diagnosis rather than the code.

    That is not hypothetical, it is what happened. The baseline had been re-anchored by rescoring a
    stored diagnosis that predated the missing-symbol fix, so it read 20 while today's gates measure
    the very same tree at 29 — six missing symbols the older diagnosis never contained. Two rounds
    in a row were then reverted with identical numbers, 20 -> 29, for a tree neither of them had
    touched. Every round was losing to a phantom.

    Same exclusions as the snapshot, so a 150 MB virtualenv or node_modules cannot dominate the
    digest or the cost.
    """
    import hashlib

    if not code_dir.is_dir():
        return None
    digest = hashlib.sha256()
    try:
        for path in sorted(code_dir.rglob("*")):
            rel = path.relative_to(code_dir)
            if _is_excluded(rel.parts):
                continue
            if not path.is_file():
                continue
            # Runtime artifacts are not code. The backend E2E gate boots the app inside the product
            # tree with sqlite:///./sentinel.db, so every QA run rewrites the database file — and a
            # fingerprint that includes it can never match the accepted print, which switches off the
            # same-tree re-anchor exactly when it is needed. Measured: two identical reverts (2 -> 5)
            # on a tree whose code had not changed.
            if rel.suffix.lower() in (".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".coverage"):
                continue
            digest.update(rel.as_posix().encode("utf-8", "replace"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    except OSError:
        return None
    return digest.hexdigest()[:16]


def verdict(previous_score: Any, current_score: Any) -> str:
    """``"accept"`` or ``"revert"``. Anything unmeasurable accepts."""
    if not guard_enabled():
        return "accept"
    try:
        prev = int(previous_score)
        cur = int(current_score)
    except (TypeError, ValueError):
        return "accept"
    return "revert" if cur > prev else "accept"


def revert_hint(previous_score: int, current_score: int, kept_defects: list[str]) -> str:
    """What the next round needs to know, so it does not simply repeat the reverted edit."""
    lines = [
        "The previous repair round was REVERTED and the tree you are looking at is the one "
        f"from before it. Measured by QA's own findings it made the product worse: "
        f"{previous_score} → {current_score} (severity-weighted). Whatever it fixed, it broke "
        "more.",
        "Do not re-apply that approach. Change one thing at a time and prefer the smallest "
        "edit that addresses a single finding; a round that rewrites several files to fix one "
        "defect is how the regression happened.",
    ]
    if kept_defects:
        # Explicitly NOT a work list. These were seen in the tree that was thrown away, so
        # some of them do not exist in the restored tree at all. Labelling them as outstanding
        # work is exactly the mistake that produced a monotone 72 → 99 → 113: the code was
        # reverted correctly while the next round kept being handed the rejected round's
        # diagnosis, and edited against a tree that no longer existed. Your work list is the
        # findings supplied separately with this task.
        lines.append(
            "For context only — what QA saw in the DISCARDED tree, which may not be present "
            "in the one you have: " + "; ".join(kept_defects[:12])
        )
    return "\n".join(lines)
