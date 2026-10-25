"""Reverts that keep a repair round from making the tree worse: out-of-scope writes, a worse
score, new undefined names, symbol regressions.
"""

from __future__ import annotations

from pathlib import Path

from .defects import _tree_defect_identities, _tree_defect_score
from .paths import _resolve_safe_code_path
from .salvage import _record_salvage_notes


def _revert_out_of_scope_writes(
    code_root: Path,
    previous_content: dict[str, str],
    written: list[str],
    scope: list[str],
    *,
    log,
    product_id: str,
    findings_text: str = "",
) -> set[str]:
    """Undo edits outside the half of the product that actually needs repair.

    A round rewrites the whole tree whatever the prompt says. When the backend is
    green and only the frontend fails, that is forty-odd chances to lose a working
    backend while fixing a page — and it happened repeatedly. Writes outside the
    scope are restored to their previous content; genuinely new files outside it
    are removed.
    """
    if not scope:
        return set()
    # A scope entry is either a directory ("backend/") or an exact file
    # ("backend/app/services/atlas_client.py"). Treating both as prefixes turned a file entry
    # into "…atlas_client.py/", which matches nothing — so a file-level scope would have
    # reverted every write including the one file it was meant to allow, i.e. every round would
    # land empty. QA now emits file-level scopes when the blocking defects name few enough
    # files, so this distinction is load-bearing rather than theoretical.
    scope_text = str(findings_text or "")
    exact = {s.strip("/") for s in scope if s and Path(s).suffix}
    prefixes = tuple(s.strip("/") + "/" for s in scope if s and not Path(s).suffix)
    if not exact and not prefixes:
        return set()

    # A scope limit that makes the tree worse is not a limit, it is a bug. Watched live, twice in
    # a row with identical numbers: QA scoped a round to audit.py, advisory.py and cache.py; the
    # round wrote those three and also deps.py and Dashboard.tsx, which import the symbols it had
    # just moved. Reverting the two importers left the definitions in place and their callers
    # rolled back, so static defects rose 16 → 24, the developer's own check rejected the round,
    # and the next attempt reproduced it exactly. Every attempt burned that way.
    #
    # So each candidate revert is measured. A file whose revert makes the tree worse is a
    # necessary companion of the in-scope change and its write is kept; a file whose revert costs
    # nothing is out-of-scope sprawl and goes. Greedy and in sorted order, so the same round always
    # produces the same answer.
    # A file the DIAGNOSIS asked for is in scope by definition. The scope is built from the files
    # blocking defects name, and a finding like "GITHUB_HOUSE_CONTRACT not satisfied: missing
    # required repository files" names files that do not exist yet — so they can never appear in a
    # scope derived from the tree. Measured: a round created .github/workflows/ci.yml,
    # release.yml, CHANGELOG.md, LICENSE and README.md, exactly as instructed, and all five were
    # reverted as sprawl because the scope read ["frontend/src/components/UI/Toast.tsx"]. The
    # finding then survived to the next round, which created them again. A requirement whose
    # fulfilment is structurally undoable is a treadmill.
    wanted_by_findings = {
        rel
        for rel in written
        if rel not in previous_content and rel in scope_text
    }

    candidates = [
        rel
        for rel in written
        if not (
            rel in exact
            or (prefixes and rel.startswith(prefixes))
            or rel in wanted_by_findings
        )
    ]
    if wanted_by_findings:
        log(
            "INFO",
            f"Keeping {len(wanted_by_findings)} new file(s) for {product_id} that the findings ask "
            f"for by name: {', '.join(sorted(wanted_by_findings)[:6])}",
        )
    current = _tree_defect_score(code_root) if candidates else None

    reverted: set[str] = set()
    kept_for_coherence: list[str] = []
    for rel in sorted(candidates):
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            continue
        was_new = rel not in previous_content
        try:
            written_back = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
        except OSError:
            written_back = None
        try:
            if not was_new:
                target.write_text(previous_content[rel], encoding="utf-8")
            elif target.is_file():
                target.unlink()
            else:
                continue
        except OSError:
            continue

        after = _tree_defect_score(code_root) if current is not None else None
        if current is not None and after is not None and after > current:
            # Undo the revert: this write is load-bearing for the in-scope repair.
            try:
                if written_back is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(written_back, encoding="utf-8")
                    kept_for_coherence.append(rel)
                    continue
            except OSError:
                pass
        if after is not None:
            current = after
        reverted.add(rel)
    if kept_for_coherence:
        log(
            "INFO",
            f"Kept {len(kept_for_coherence)} out-of-scope edit(s) for {product_id} because "
            f"reverting them made the tree worse: {', '.join(sorted(kept_for_coherence)[:6])}",
        )
    if reverted:
        log(
            "WARNING",
            f"Reverted {len(reverted)} out-of-scope edit(s) for {product_id} "
            f"(round scoped to {', '.join(scope)}): {', '.join(sorted(reverted)[:6])}",
        )
    return reverted

def _revert_until_not_worse(
    code_root: Path,
    previous_content: dict[str, str],
    written: list[str],
    *,
    before_score: int,
    log,
    product_id: str,
    already: set[str],
) -> set[str]:
    """Give back the fewest files that stop the round being a regression.

    A round is judged whole, and that is why a good round kept being thrown away. Measured twice in six
    minutes on a tree that had reached zero defects:

        Applied 9 edit(s) across 6 file(s): advisory.ts, Dashboard.tsx, AnalyticsDashboard.tsx,
                                            PublicWidget.tsx, test_cache.py, test_atlas_client.py
        Rejected: what moved — missing_attribute 0→1 | added: missing_attribute: atlas_client.invoke
        Rejected: static defects would rise 0 → 10; tree restored

    Three of those edits are the three tsc errors the round was sent to fix. They score **nothing** in
    this measure — type errors come from an npm build, far too slow to run twice a round — while the one
    backend attribute it broke scores ten. So a round doing exactly the work it was asked for cannot
    come out ahead, and the frontend can never be fixed by a round that touches the backend at all.

    Reverting file by file, keeping each revert only while it helps, salvages the work that was right.
    Greedy and in sorted order so one round always produces one answer, and it stops as soon as the tree
    is no longer worse than it was — the goal is to land the round, not to find a minimum.

    Mesh wiring files are never candidates: salvage kept giving back ``routers/advisory.py`` /
    ``atlas_client.py`` because unrelated static noise outweighed the invoke edge, and the next
    round rediscovered ``capability_never_invoked``. Prefer rejecting the whole round over
    undoing the product's reason to exist.
    """
    mesh_wiring_names = frozenset(
        {
            "advisory.py",
            "atlas_client.py",
            "aimarket_participant.py",
            "participant.py",
        }
    )

    def _is_mesh_wiring(rel: str) -> bool:
        name = Path(rel).name.lower()
        if name in mesh_wiring_names:
            return True
        norm = rel.replace("\\", "/").lower()
        return norm.endswith("/routers/advisory.py") or "/services/atlas_client.py" in norm

    candidates = [
        rel for rel in sorted(set(written)) if rel not in already and not _is_mesh_wiring(rel)
    ]
    if not candidates:
        return set()
    current = _tree_defect_score(code_root)
    if current is None or current <= before_score:
        return set()

    reverted: set[str] = set()
    introduced: dict[str, list[str]] = {}
    try:
        ids_with_edit = _tree_defect_identities(code_root)
    except Exception:  # pragma: no cover
        ids_with_edit = set()
    for rel in candidates:
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            continue
        was_new = rel not in previous_content
        try:
            kept = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
            if was_new:
                if target.is_file():
                    target.unlink()
            else:
                target.write_text(previous_content[rel], encoding="utf-8")
        except OSError:
            continue

        after = _tree_defect_score(code_root)
        if after is None or after >= current:
            # This file was not the problem: put it back and keep looking.
            try:
                if kept is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(kept, encoding="utf-8")
            except OSError:
                pass
            continue
        # WHAT the edit introduced, not just that it was given back. Identities present with the
        # edit and absent without it are exactly the defects it added, and they are the only
        # actionable thing about a revert. Without this the next round is told nothing and makes
        # the same one-sided edit again — measured on Sentinel: the developer edited the right
        # file (aimarket_participant.py) in round after round, each edit raised the static score
        # because it referenced a client method that does not exist yet, each was silently given
        # back, and the round reported "0 files" so the repair budget was never even charged. A
        # loop that costs nothing and progresses nothing runs until someone reads the logs.
        try:
            introduced.setdefault(rel, sorted(set(ids_with_edit) - set(_tree_defect_identities(code_root)))[:8])
        except Exception:  # pragma: no cover - identity probe is diagnostic only
            introduced.setdefault(rel, [])
        current = after
        reverted.add(rel)
        if current <= before_score:
            break

    if reverted:
        log(
            "INFO",
            f"Salvaged the repair round for {product_id} by giving back {len(reverted)} file(s): "
            f"{', '.join(sorted(reverted)[:6])} — the rest of the round stands ({current} vs "
            f"{before_score} before). What those edits introduced: "
            + "; ".join(
                f"{rel}: {', '.join(defs) or 'nothing this score can name'}"
                for rel, defs in sorted(introduced.items())
            )[:600],
        )
    _record_salvage_notes(code_root, product_id, introduced, log=log)
    return reverted


def _revert_files_with_new_undefined_names(
    code_root: Path,
    previous_content: dict[str, str],
    *,
    log,
    product_id: str,
    already: set[str],
) -> set[str]:
    """Revert just the files this round left with an unbound name.

    Rejecting a whole round for a one-point backend regression also discards the
    frontend work that round did — and one product stalled exactly there, its
    backend clean at zero while every attempt at the remaining UI defects was
    thrown away with the bad edit. Reverting the specific offenders first keeps
    the good half.
    """
    from web.backend.services.duplicate_module_check import (
        find_undefined_names,
        undefined_names_in_source,
    )

    reverted: set[str] = set()
    try:
        undefined = find_undefined_names(code_root, limit=200)
    except Exception:
        return reverted
    for item in undefined:
        rel = str(item.get("file") or "")
        if rel not in previous_content or rel in already or rel in reverted:
            continue
        # Only a regression if the previous version bound the name. Substring
        # matching gets this exactly backwards: the old text containing the name
        # is what a binding looks like.
        was_unbound = {n for n, _ in undefined_names_in_source(previous_content[rel])}
        if item.get("name") in was_unbound:
            continue
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            continue
        try:
            target.write_text(previous_content[rel], encoding="utf-8")
        except OSError:
            continue
        reverted.add(rel)
        log(
            "WARNING",
            f"Reverted {rel} for {product_id}: the rewrite left '{item.get('name')}' unbound",
        )
    return reverted


def _revert_symbol_regressions(
    code_root: Path,
    previous_content: dict[str, str],
    *,
    log,
    product_id: str,
) -> set[str]:
    """Undo writes that removed a symbol other modules still import.

    Measured on a live rework: the developer rewrote 84-91 files per round to fix
    ten findings. Whole-file regeneration is how `hash_password` disappeared from
    security.py three separate times while five untouched modules imported it —
    each round "fixed" the finding and reintroduced it.

    A repair round is allowed to change anything except the contract other files
    depend on. When a rewritten module drops such a symbol, its previous content
    is restored and the finding is left for the next round to address honestly.
    """
    from web.backend.services.duplicate_module_check import find_missing_symbols

    reverted: set[str] = set()
    # Scan uncapped: the human-facing report stops at ten findings, but a round
    # that strips twenty symbols would then get only ten of them protected and
    # ship the rest. Re-scan after each pass — restoring one module can resolve
    # several findings at once, and can reveal others behind them.
    for _ in range(3):
        try:
            missing = find_missing_symbols(code_root, limit=500)
        except Exception as exc:
            log("WARNING", f"Regression check skipped for {product_id}: {exc}")
            return reverted

        progressed = False
        for item in missing:
            rel = str(item.get("file") or "")
            if rel not in previous_content or rel in reverted:
                continue
            # Only roll back when the symbol used to be there — a symbol that never
            # existed is a genuine new finding, not a regression.
            if item.get("symbol") not in previous_content[rel]:
                continue
            target = _resolve_safe_code_path(code_root, rel)
            if target is None:
                continue
            try:
                target.write_text(previous_content[rel], encoding="utf-8")
            except OSError as exc:
                log("WARNING", f"Could not restore {rel} for {product_id}: {exc}")
                continue
            reverted.add(rel)
            progressed = True
            log(
                "WARNING",
                f"Reverted {rel} for {product_id}: the rewrite dropped "
                f"'{item.get('symbol')}', which other modules import",
            )
        if not progressed:
            break
    return reverted
