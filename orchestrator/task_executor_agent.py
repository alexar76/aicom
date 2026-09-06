"""
Real-agent pipeline task execution (success, failure, retries).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

from core.agent_roles import is_architect_agent, is_developer_agent
from core.charter_fidelity import charter_fidelity_report, feedback_for_pm
from core.spec_presence import spec_has_substance as _spec_has_substance
from core.quality_settings import (
    gate_failing_model,
    max_pipeline_repair_rounds_for_delivery_profile,
    max_pipeline_repair_rounds_for_product,
    monitoring_dev_refresh_enabled,
)
from orchestrator.task_executor_helpers import (
    PipelineTaskExecutorHost,
    build_task_context,
    record_task_lesson,
)
from orchestrator.task_queue_hygiene import requeue_pm_bounded, requeue_pm_when_spec_absent
from orchestrator.worker_utils import delivery_profile_from_product_dict, monitoring_refresh_decision
from web.backend.services.marketplace_quality import evaluate_marketplace_quality
from web.backend.services.requirements_clarifier import build_clarification_pack_llm
from web.backend.services.security_pipeline_gate import (
    build_security_gate_feedback,
    security_scan_passes_pipeline_gate,
)

logger = logging.getLogger("pipeline-worker")

_AGENT_EXECUTE_TIMEOUT_DEFAULTS = {
    # QA now also runs npm install + the product's own frontend build, boots the
    # app and sweeps it authenticated — all of which sit inside this budget.
    "qa": 900.0,
    # A repair round regenerates ~85 files, and the write-time self-check can send
    # one back for another pass. Two full generations must fit, or the round dies
    # at the timeout with its work discarded and the defect list unchanged.
    "developer": 1500.0,
    "architect": 300.0,
    "pm": 240.0,
    "security": 300.0,
}


def _agent_execute_timeout_sec(agent_type: str) -> float:
    raw = os.environ.get("AIFACTORY_AGENT_EXECUTE_TIMEOUT_SEC") or os.environ.get(
        f"AIFACTORY_{str(agent_type).upper()}_EXECUTE_TIMEOUT_SEC"
    )
    if raw:
        try:
            return max(30.0, float(raw))
        except ValueError:
            pass
    return _AGENT_EXECUTE_TIMEOUT_DEFAULTS.get(str(agent_type), 300.0)


def _guard_round_regression(product: dict, pid: str, qa_result: object, host) -> None:
    """Throw away a repair round that QA's own count says made the product worse.

    Kept out of the handler body because the decision has three outcomes and each one has to
    leave the product in a coherent state: accepted (record the new baseline), reverted
    (restore the tree AND tell the next round why, or it repeats the same edit), or
    unmeasurable (do nothing at all — a guard that cannot measure must not discard work).
    """
    from core.round_regression_guard import (
        SCORING_RULES_VERSION,
        backend_boots,
        critical_pressure,
        demo_quality_score,
        is_stuck,
        journey_depth,
        mark_stuck,
        preview_crashed,
        qa_defect_score,
        record_rejected_tree,
        restore_snapshot,
        revert_hint,
        stuck_reason,
        tree_fingerprint,
        verdict,
    )
    from core.paths import code_dir as resolve_code_dir

    score = qa_defect_score(qa_result)
    if score is None:
        return
    previous = product.get("last_qa_defect_score")
    depth = journey_depth(qa_result)
    demo = demo_quality_score(qa_result)

    # Booting is not a matter of degree, so it is checked before any number. A round that leaves the
    # application unable to start is rejected even when the static tree got cleaner — which is
    # exactly the shape that slipped through: 32 defects down to 27, backend_e2e True -> False, and
    # the round was accepted because the score only reads the tree.
    boots = backend_boots(qa_result)
    crashed = preview_crashed(qa_result)
    crits = critical_pressure(qa_result)
    was_booting = product.get("last_backend_booted")
    was_crashed = product.get("last_preview_crashed")
    if boots is False and was_booting is True:
        code_root = resolve_code_dir(pid, data_root=host.data_root)
        if restore_snapshot(pid, code_root, host.data_root):
            product["reverted_round_count"] = int(product.get("reverted_round_count") or 0) + 1
            logger.error(
                "Round guard: reverted a round for %s that stopped the backend from booting — the "
                "defect count moved %s -> %s, which is irrelevant: a product that does not start "
                "has no qualities to measure. Rounds reverted so far: %s",
                pid, previous, score, product["reverted_round_count"],
            )
            accepted_ctx = product.get("last_accepted_bug_context")
            if isinstance(accepted_ctx, dict):
                product["last_bug_context"] = accepted_ctx
            return
        logger.error(
            "Round guard: %s stopped booting and no snapshot could be restored; keeping the tree so "
            "the next round works from reality, but this is the worst outcome available.",
            pid,
        )

    # A page that throws before paint has no UI. The demo-quality axis treated empty/toast in
    # source as 86 A and accepted the throw; the working 76 B tree was then reverted as a visual
    # drop. Same shape as a dead backend: the count moved, the product did not.
    if crashed is True and was_crashed is False:
        code_root = resolve_code_dir(pid, data_root=host.data_root)
        if restore_snapshot(pid, code_root, host.data_root):
            product["reverted_round_count"] = int(product.get("reverted_round_count") or 0) + 1
            logger.error(
                "Round guard: reverted a round for %s that made the preview throw (pageerror / "
                "console Error) after a tree that did not. Demo %s and defect %s -> %s do not "
                "matter: the browser never painted. Rounds reverted so far: %s",
                pid, demo, previous, score, product["reverted_round_count"],
            )
            accepted_ctx = product.get("last_accepted_bug_context")
            if isinstance(accepted_ctx, dict):
                product["last_bug_context"] = accepted_ctx
            return
        logger.error(
            "Round guard: %s preview started throwing and no snapshot could be restored; keeping "
            "the tree so the next round works from reality.",
            pid,
        )

    # Measuring the tree we already accepted re-anchors the baseline instead of arguing with it.
    # A round can end without changing anything — the developer's own coherence check rejects its
    # attempts and restores the tree — and then this is a comparison of a tree with itself, where
    # any difference can only come from the two numbers being measured differently. Which is what
    # happened: the baseline read 20 because it had been re-derived from a stored diagnosis that
    # predated the missing-symbol detector, while today's gates measure the same tree at 29. Two
    # rounds in a row were reverted 20 -> 29 for a tree neither had touched.
    # A baseline measured under older rules is in different units, so it cannot be compared — only
    # replaced. Without this every detector improvement destroys work: the round that brought missing
    # symbols from 9 to 2, the largest real gain of the day, was reverted at 7 -> 64 because the 7
    # predated `missing_symbol` becoming critical and two dedup rules landing.
    stored_rules = product.get("last_qa_defect_score_rules")
    if previous is not None and stored_rules != SCORING_RULES_VERSION:
        # Re-anchoring exists so a sharper ruler does not read as a regression. It must not become
        # an amnesty. Measured, and it cost a working product: the rules moved 16 -> 18 in the same
        # round that a repair added `@rate_limit` without the `request` parameter slowapi needs, so
        # `app.main` stopped importing and every route died. QA reported 52 defects and
        # backend_e2e=False; the guard said "different units, not a regression" and adopted the
        # broken tree as the new baseline at 95. Nothing was left to revert to.
        #
        # The NUMBER is in new units. The IDENTITIES are not: a name that was resolvable before and
        # is not now is a regression under any ruler. So the units are re-anchored while the set of
        # defects is still compared.
        regressed_ids: list[str] = []
        try:
            from agents.dev import _tree_defect_identities

            code_root_now = resolve_code_dir(pid, data_root=host.data_root)
            current_ids = _tree_defect_identities(code_root_now)
            accepted_ids = product.get("last_accepted_defect_identities")
            if isinstance(accepted_ids, dict):
                for kind, names in current_ids.items():
                    known = set(accepted_ids.get(kind) or [])
                    for name in sorted(set(names) - known):
                        regressed_ids.append(f"{kind}:{name}")
        except Exception as ident_exc:
            logger.debug("Round guard: identity comparison unavailable for %s: %s", pid, ident_exc)

        if regressed_ids:
            code_root = resolve_code_dir(pid, data_root=host.data_root)
            if restore_snapshot(pid, code_root, host.data_root):
                product["reverted_round_count"] = int(product.get("reverted_round_count") or 0) + 1
                logger.error(
                    "Round guard: the scoring rules moved (%s -> %s) AND this round introduced %s "
                    "defect(s) the accepted tree did not have — %s. Re-anchoring the number is "
                    "right; adopting new breakage is not. Reverted; rounds reverted so far: %s",
                    stored_rules, SCORING_RULES_VERSION, len(regressed_ids),
                    ", ".join(regressed_ids[:6]), product["reverted_round_count"],
                )
                accepted_ctx = product.get("last_accepted_bug_context")
                if isinstance(accepted_ctx, dict):
                    product["last_bug_context"] = accepted_ctx
                product["last_qa_defect_score_rules"] = SCORING_RULES_VERSION
                return
            logger.error(
                "Round guard: rules moved and %s new defect(s) appeared (%s) but no snapshot could "
                "be restored — keeping the tree and re-anchoring, because a baseline that describes "
                "a tree we no longer have is worse than a high one.",
                len(regressed_ids), ", ".join(regressed_ids[:4]),
            )

        logger.warning(
            "Round guard: the baseline for %s (%s) was measured under scoring rules %s and this run "
            "uses %s, so it is re-anchored to %s rather than compared — different units, not a "
            "regression.",
            pid, previous, stored_rules, SCORING_RULES_VERSION, score,
        )
        if crits is not None:
            product["last_critical_pressure"] = crits
        if boots is not None:
            product["last_backend_booted"] = boots
        if crashed is not None:
            product["last_preview_crashed"] = crashed
        if depth is not None:
            product["last_journey_depth"] = depth
        if demo is not None:
            product["last_demo_quality_score"] = demo
        if critical_pressure(qa_result) is not None:
            product["last_critical_pressure"] = critical_pressure(qa_result)
        product["last_qa_defect_score"] = score
        product["last_qa_defect_score_rules"] = SCORING_RULES_VERSION
        accepted_ctx = product.get("last_bug_context")
        if isinstance(accepted_ctx, dict):
            product["last_accepted_bug_context"] = accepted_ctx
        fp = tree_fingerprint(resolve_code_dir(pid, data_root=host.data_root))
        if fp:
            product["last_accepted_tree_fingerprint"] = fp
        return

    fingerprint = tree_fingerprint(resolve_code_dir(pid, data_root=host.data_root))
    if fingerprint and fingerprint == product.get("last_accepted_tree_fingerprint"):
        if previous != score:
            logger.warning(
                "Round guard: re-anchored the baseline for %s (%s -> %s) — this is the tree "
                "already accepted, unchanged, so the difference is in how the two numbers were "
                "measured, not in the code.",
                pid, previous, score,
            )
        if crits is not None:
            product["last_critical_pressure"] = crits
        if boots is not None:
            product["last_backend_booted"] = boots
        if crashed is not None:
            product["last_preview_crashed"] = crashed
        if depth is not None:
            product["last_journey_depth"] = depth
        if demo is not None:
            product["last_demo_quality_score"] = demo
        if critical_pressure(qa_result) is not None:
            product["last_critical_pressure"] = critical_pressure(qa_result)
        product["last_qa_defect_score"] = score
        product["last_qa_defect_score_rules"] = SCORING_RULES_VERSION
        accepted_ctx = product.get("last_bug_context")
        if isinstance(accepted_ctx, dict):
            product["last_accepted_bug_context"] = accepted_ctx
        # Same tree as last accepted: the round wrote nothing that survived. That is not
        # progress, even when the score moved because the two measurements differed.
        _note_non_improvement(product, pid, previous, score, breakthrough=False)
        return

    # Journey depth is its own ratchet axis. A round in which the journey got STRICTLY deeper
    # — login answered for the first time, a token appeared for the first time — is accepted on
    # that fact alone, because everything it finds behind the newly opened door is by definition
    # new, and letting those findings vote makes the breakthrough round un-acceptable by
    # construction. Measured twice on one product: the token round reverted 14 -> 32 for six
    # 401s, its successor 14 -> 35 for six 500s. The depth of the accepted tree is recorded so
    # the next comparison is depth-aware too.
    stored_depth = product.get("last_journey_depth")
    if stored_depth is None:
        # Derive it from the accepted diagnosis: a baseline whose own findings say the login
        # returned no token (or failed outright) cannot have been deeper than that.
        _ctx = product.get("last_accepted_bug_context")
        _titles = " ".join(
            str(b.get("title") or "")
            for b in ((_ctx or {}).get("qa_findings") or [])
            if isinstance(b, dict)
        )
        if "demo_login_no_token" in _titles:
            stored_depth = 1
        elif "demo_login_failed" in _titles:
            stored_depth = 0
    stored_demo = product.get("last_demo_quality_score")
    if stored_demo is None:
        # First deploy of this axis: the accepted diagnosis still listing the app-like visual
        # misses IS a C-grade statement. Sentinel sat on demo 66 C with those four codes, then
        # a round reached 86 A and was reverted for unused locals. Without this, the first
        # 86 A after deploy would not be recognised (stored None) and would be thrown away again.
        _ctx = product.get("last_accepted_bug_context")
        _titles = " ".join(
            str(b.get("title") or "") + " " + str(b.get("description") or "")
            for b in ((_ctx or {}).get("qa_findings") or [])
            if isinstance(b, dict)
        )
        _visual_c = (
            "visual_no_responsive_nav_mobile",
            "visual_app_missing_empty_state",
            "visual_app_missing_error_ui",
            "visual_app_missing_toast_or_alert",
        )
        if sum(1 for code in _visual_c if code in _titles) >= 3:
            stored_demo = 66
    # Fewer criticals is progress even when the weighted total rises. A critical is what stops the
    # product working; the smaller findings a round leaves behind are the next round's work, and
    # refusing the trade means refusing both.
    crits = critical_pressure(qa_result)
    stored_crits = product.get("last_critical_pressure")
    fewer_criticals = (
        crits is not None
        and isinstance(stored_crits, int)
        and crits < stored_crits
    )
    if fewer_criticals and verdict(previous, score) != "accept":
        logger.warning(
            "Round guard: accepting %s despite the total (%s -> %s) because the criticals fell %s -> "
            "%s. A critical is what stops the product working; the lesser findings it left are the "
            "next round's work.",
            pid, previous, score, stored_crits, crits,
        )

    depth_breakthrough = (
        depth is not None and isinstance(stored_depth, int) and depth > stored_depth
    )
    visual_breakthrough = (
        demo is not None
        and isinstance(stored_demo, int)
        and demo > stored_demo
        and crashed is not True
    )
    breakthrough = depth_breakthrough or fewer_criticals or visual_breakthrough
    if visual_breakthrough and verdict(previous, score) != "accept":
        logger.warning(
            "Round guard: accepted a visual breakthrough for %s despite the score (%s -> %s): "
            "demo quality rose %s -> %s. Unused-local compile errors that arrived with the UI "
            "are the next round's work, not a reason to restore the stub.",
            pid, previous, score, stored_demo, demo,
        )
    elif depth_breakthrough and verdict(previous, score) != "accept":
        logger.warning(
            "Round guard: accepted a breakthrough round for %s despite the score (%s -> %s): the "
            "demo journey got strictly deeper (depth %s -> %s), and findings behind a newly "
            "opened door are progress made visible, not regression.",
            pid, previous, score, stored_depth, depth,
        )

    # ``was_crashed is not False`` so a missing key (this axis just landed) does not
    # visual-revert a working 76 B back onto the crashing 86 A snapshot we already kept.
    crash_cleared = crashed is False and was_crashed is not False
    visual_regression = (
        demo is not None
        and isinstance(stored_demo, int)
        and demo < stored_demo
        and not depth_breakthrough
        and not fewer_criticals
        and not crash_cleared
    )
    if visual_regression and verdict(previous, score) == "accept":
        logger.error(
            "Round guard: %s demo quality fell %s -> %s while the backend still boots; the "
            "defect total (%s -> %s) improved because tsc got quieter after the UI was deleted. "
            "That is not an improvement.",
            pid, stored_demo, demo, previous, score,
        )

    if (verdict(previous, score) == "accept" or breakthrough) and not visual_regression:
        try:
            from agents.dev import _tree_defect_identities

            ids_now = _tree_defect_identities(resolve_code_dir(pid, data_root=host.data_root))
            product["last_accepted_defect_identities"] = {
                kind: sorted(names) for kind, names in ids_now.items() if names
            }
        except Exception:
            pass
        if crits is not None:
            product["last_critical_pressure"] = crits
        if boots is not None:
            product["last_backend_booted"] = boots
        if crashed is not None:
            product["last_preview_crashed"] = crashed
        if depth is not None:
            product["last_journey_depth"] = depth
        if demo is not None:
            product["last_demo_quality_score"] = demo
        if critical_pressure(qa_result) is not None:
            product["last_critical_pressure"] = critical_pressure(qa_result)
        product["last_qa_defect_score"] = score
        product["last_qa_defect_score_rules"] = SCORING_RULES_VERSION
        # Keep the diagnosis that goes with the tree we are keeping. A revert restores the
        # code from a snapshot; the findings have to come back with it or the next round works
        # from a description of a tree that no longer exists.
        accepted_ctx = product.get("last_bug_context")
        if isinstance(accepted_ctx, dict):
            product["last_accepted_bug_context"] = accepted_ctx
        if fingerprint:
            product["last_accepted_tree_fingerprint"] = fingerprint
        _note_non_improvement(product, pid, previous, score, breakthrough=breakthrough)
        return

    # Say WHAT got worse, not just by how much. Three rounds in a row were reverted 14 -> 18, 20, 22
    # while the static tree stayed identical, and the log gave no way to tell whether the round broke
    # something real or lost to noise — so the next round repeated the same attempt. A revert that
    # cannot be learned from buys nothing but a slower plateau.
    try:
        from core.round_regression_guard import dedupe_root_causes as _dedupe

        def _keys(items) -> set[str]:
            out: set[str] = set()
            for b in _dedupe(list(items or [])):
                if isinstance(b, dict):
                    out.add(f"{str(b.get('title'))[:70]}|{b.get('file') or ''}")
            return out

        _before = _keys(((product.get("last_accepted_bug_context") or {}).get("qa_findings")) or [])
        _after = _keys((qa_result or {}).get("bugs_found") or [])
        _new = sorted(_after - _before)
        if _new:
            logger.error(
                "Round guard: %s new finding(s) this round did not have before — %s",
                len(_new), "; ".join(n.split("|")[0] for n in _new[:5]),
            )
    except Exception as diff_exc:
        logger.debug("Round guard: could not diff findings for %s: %s", pid, diff_exc)

    code_root = resolve_code_dir(pid, data_root=host.data_root)
    # Fingerprint the REJECTED tree before it is overwritten — after the restore it no longer
    # exists anywhere, and this digest is the only evidence that distinguishes "the loop is
    # slowly converging" from "the loop has produced this identical tree before". Recorded even
    # when the restore below fails, because the fact that the same edit was attempted again is
    # true either way.
    _rejected_repeats = record_rejected_tree(product, tree_fingerprint(code_root))
    if not restore_snapshot(pid, code_root, host.data_root):
        # No snapshot, or the restore failed: keep the worse tree rather than pretend, and
        # record the score so the next comparison is against reality and not a tree that is
        # no longer there.
        logger.warning(
            "Round guard: %s regressed %s -> %s but could not be reverted; keeping the round",
            pid, previous, score,
        )
        if crits is not None:
            product["last_critical_pressure"] = crits
        if boots is not None:
            product["last_backend_booted"] = boots
        if crashed is not None:
            product["last_preview_crashed"] = crashed
        if depth is not None:
            product["last_journey_depth"] = depth
        if demo is not None:
            product["last_demo_quality_score"] = demo
        if critical_pressure(qa_result) is not None:
            product["last_critical_pressure"] = critical_pressure(qa_result)
        product["last_qa_defect_score"] = score
        product["last_qa_defect_score_rules"] = SCORING_RULES_VERSION
        return

    outstanding = []
    if isinstance(qa_result, dict):
        for bug in (qa_result.get("bugs_found") or [])[:12]:
            if isinstance(bug, dict) and bug.get("title"):
                outstanding.append(str(bug["title"])[:120])
    # Restore the DIAGNOSIS as well as the code. Without this the rejected round's findings
    # stayed in last_bug_context, so the next round was told to fix 39 defects in a tree that
    # actually had 15 — it edited against a description of a tree that no longer existed, and
    # each rejected round left a more wrong list than the last. That is what produced a
    # monotone climb of 72 → 99 → 113 while the code was being correctly reverted every time:
    # a compounding feedback loop, created by reverting one half of the round and keeping the
    # other.
    accepted_ctx = product.get("last_accepted_bug_context")
    if isinstance(accepted_ctx, dict):
        accepted_ctx = _refresh_static_findings(accepted_ctx, code_root, pid)
        product["last_bug_context"] = accepted_ctx
        # The baseline for the critical-pressure axis, taken here because this is the only place the
        # deterministic gate findings for the restored tree exist. Measured the wrong way first: the
        # stored accepted context holds 25 findings and not one of them carries a gate prefix — it is
        # the LLM reviewer's half — so deriving from it recorded a baseline of 0 while the tree had
        # three critical missing attributes, and an axis with a zero baseline can never fire.
        _base_crits = critical_pressure({"bugs_found": accepted_ctx.get("qa_findings") or []})
        if _base_crits is not None and product.get("last_critical_pressure") != _base_crits:
            product["last_critical_pressure"] = _base_crits
            logger.info(
                "Round guard: baseline critical pressure for %s is %s, measured on the restored tree.",
                pid, _base_crits,
            )
        logger.info(
            "Round guard: restored the accepted diagnosis for %s (%d findings) alongside the "
            "tree, so the next round is not fixing a description of a tree that no longer "
            "exists.",
            pid,
            len(accepted_ctx.get("qa_findings") or []),
        )
    else:
        # No accepted diagnosis yet: drop the rejected one rather than pass it on. An empty
        # bug list makes the next round re-derive from the tree, which is at least true.
        product.pop("last_bug_context", None)
        logger.warning(
            "Round guard: no accepted diagnosis stored for %s; cleared the rejected findings "
            "rather than hand on a description of a discarded tree.",
            pid,
        )
    # The outstanding list in the hint is what QA saw in the REJECTED tree, so it is context
    # for "do not do that again", not a work list — the restored diagnosis above is the work.
    product["surrogate_repair_hint"] = revert_hint(
        int(previous), int(score), outstanding, repeat_count=max(1, _rejected_repeats)
    )
    product["reverted_round_count"] = int(product.get("reverted_round_count") or 0) + 1
    # The baseline stays at the score of the tree that is now on disk — the restored one.
    logger.error(
        "Round guard: reverted a repair round for %s (%s -> %s, severity-weighted); "
        "restored the tree QA last measured. Rounds reverted so far: %s%s",
        pid, previous, score, product["reverted_round_count"],
        f" — this exact rejected tree for the {_rejected_repeats}. time" if _rejected_repeats > 1 else "",
    )

    # A loop that reproduces the same rejected tree is a fixed point, not slow progress: the
    # guard restores the same tree and the same diagnosis, so identical inputs yield the
    # identical edit. Sentinel spent 38 reverted rounds here, four of them inside one five-hour
    # window with byte-identical 9 -> 12 numbers. Stopping costs one product's progress;
    # continuing costs every round from now until someone notices.
    if is_stuck(_rejected_repeats):
        reason = stuck_reason(pid, _rejected_repeats, previous, score)
        mark_stuck(product, reason)
        logger.error("Round guard: %s", reason)
        _hold_if_stuck(product, pid)


def _hold_if_stuck(product: dict, pid: str) -> None:
    """Pause the worker so a declared stuck loop cannot enqueue another round."""
    if not product.get("pipeline_stuck_reason"):
        return
    try:
        from web.backend.services.product_followup import set_product_pipeline_on_hold

        set_product_pipeline_on_hold(pid, True)
        logger.error(
            "Round guard: put %s on pipeline hold. Clear it with "
            "set_product_pipeline_on_hold('%s', False) once the blocking finding is "
            "resolved or withdrawn.",
            pid, pid,
        )
    except Exception as exc:
        # Failing to pause must not also fail the round — but it must be loud, because the
        # loop then continues and the log line above is the only warning anyone gets.
        logger.error(
            "Round guard: could not put %s on hold (%s) — the loop will CONTINUE burning "
            "rounds until an operator pauses it by hand.",
            pid, exc,
        )


def _note_non_improvement(
    product: dict, pid: str, previous, score, *, breakthrough: bool
) -> None:
    """Stop a loop that keeps accepting rounds that do not lower the defect score.

    Equal is accepted on purpose (a trade of one defect for another of the same weight). Four
    consecutive equals with QA still failing is the Sentinel shape: weighted score stuck at 21
    while the raw finding count climbed 11 → 22. That is churn, not convergence.
    """
    from core.round_regression_guard import (
        is_plateau,
        mark_stuck,
        plateau_reason,
        record_quality_round,
    )

    if previous is None:
        record_quality_round(product, improved=True)
        return
    try:
        improved = bool(breakthrough) or int(score) < int(previous)
    except (TypeError, ValueError):
        return
    streak = record_quality_round(product, improved=improved)
    if not is_plateau(streak):
        return
    reason = plateau_reason(pid, streak, score)
    mark_stuck(product, reason)
    logger.error("Round guard: %s", reason)
    _hold_if_stuck(product, pid)


def _round_produced_output(product: dict, output) -> bool:
    """Did the developer actually write anything this round?

    Asked of a DEVELOPER output only. Asking it of a QA output was the bug in the first version: a QA
    result always carries findings, the helper said "productive", and the counter climbed through the
    outage untouched.

    "0 files" from a round is the signature of a provider outage — a 402, a timeout, a refusal — and it
    is indistinguishable, from the product's point of view, from never having been attempted. The
    repair budget is there to stop a product looping forever on defects it cannot fix; spending it on
    an empty wallet is a different thing entirely, and it silently consumed twenty-five rounds.
    """
    data = getattr(output, "data", None)
    if isinstance(data, dict):
        for key in ("file_count", "files_created"):
            value = data.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return True
        files = data.get("files")
        if isinstance(files, list) and files:
            return True
        # "0 files" has a SECOND cause that did not exist when the outage rule above was
        # written: the developer's own guards — scope revert, symbol-regression revert, the
        # salvage step — took the work back. The provider answered, the round did work, and we
        # removed it. Charging nothing for that makes the loop free, so it never reaches the
        # limit that escalates a product to a human: Sentinel sat at round 31 of 40 across a
        # dozen attempts with the counter untouched, editing the right file every time and
        # having every edit given back. A round we emptied ourselves is a spent round.
        reclaimed = data.get("reclaimed_by_guard")
        if isinstance(reclaimed, (int, float)) and reclaimed > 0:
            logger.info(
                "Round produced %s file(s) that our own guards took back (%s) — charging the "
                "repair budget: the provider answered, so this is a spent round, not an outage.",
                int(reclaimed),
                ", ".join(str(x) for x in (data.get("reclaimed_paths") or [])[:4]) or "unnamed",
            )
            return True
    return False


def _refresh_static_findings(accepted_ctx: dict, code_root, pid: str) -> dict:
    """Re-measure the deterministic detectors against the tree that is actually on disk.

    The restored diagnosis is the one QA produced for this exact tree, so restoring it is right.
    But it was produced by the detectors that existed *then*, and a detector added since would
    have nothing to say about a tree it never got to measure. That is not hypothetical: the
    missing-symbol detector learned to resolve relative imports and immediately found six names
    the product imports and defines nowhere — ``MeshCache``, ``CachedMeshReading``,
    ``seed_demo_user`` — while the diagnosis handed to the next round listed none of them, because
    it predated the fix. The round would have been sent to repair a tree whose reason for not
    booting was known and withheld.

    Static findings are a pure function of the tree — measured twice on an unchanged tree they came
    back identical, which is why these gates are the ones allowed to vote — so re-deriving them
    costs one cheap pass and cannot disagree with itself. Anything an LLM or a browser produced is
    left exactly as restored; re-running those would be neither cheap nor repeatable.
    """
    try:
        from web.backend.services.duplicate_module_check import (
            find_duplicate_tablenames,
            find_mesh_contract_violations,
            find_frontend_missing_exports,
            find_api_routes_shadowing_spa,
            find_case_collisions,
            find_dead_path_rewrites,
            find_mismatched_back_populates,
            find_missing_instance_attributes,
            find_missing_modules,
            find_missing_symbols,
            find_route_handlers_with_broken_injection,
        )
    except Exception:
        return accepted_ctx

    fresh: list[dict] = []
    try:
        for item in find_missing_symbols(code_root, limit=40):
            hint = f" Did you mean {', '.join(item['did_you_mean'])}?" if item.get("did_you_mean") else ""
            fresh.append(
                {
                    "severity": "critical",
                    "title": "Module health: missing_symbol",
                    "description": (
                        f"{item['module']} never defines {item['symbol']}, imported by "
                        f"{', '.join(item.get('importers') or []) or 'the product'}. Define it in "
                        f"{item['file']} or fix the import.{hint}"
                    ),
                    "file": item["file"],
                }
            )
        for finder, code in (
            (find_missing_modules, "missing_module"),
            (find_missing_instance_attributes, "missing_attribute"),
            (find_frontend_missing_exports, "frontend_missing_export"),
            (find_mismatched_back_populates, "mismatched_back_populates"),
            (find_api_routes_shadowing_spa, "api_route_shadows_spa"),
            (find_case_collisions, "case_collision"),
            (find_dead_path_rewrites, "dead_path_rewrite"),
            (find_duplicate_tablenames, "duplicate_tablename"),
            (find_mesh_contract_violations, "mesh_contract_violation"),
            (find_route_handlers_with_broken_injection, "route_handler_broken_injection"),
        ):
            for item in finder(code_root) or []:
                fresh.append(
                    {
                        "severity": "critical",
                        "title": f"Module health: {code}",
                        "description": str(item.get("detail") or item.get("description") or code),
                        "file": str(item.get("file") or ""),
                    }
                )
    except Exception as e:
        logger.debug("Round guard: could not re-measure static findings for %s: %s", pid, e)
        return accepted_ctx

    if not fresh:
        return accepted_ctx

    restored = [
        b
        for b in (accepted_ctx.get("qa_findings") or [])
        if not str(b.get("title") or "").lower().startswith("module health:")
    ]
    added = len(fresh) - (len(accepted_ctx.get("qa_findings") or []) - len(restored))
    if added:
        logger.info(
            "Round guard: re-measured the static gates on the restored tree for %s: %+d finding(s) "
            "the stored diagnosis did not have.",
            pid,
            added,
        )
    merged = dict(accepted_ctx)
    merged["qa_findings"] = fresh + restored
    return merged


async def run_agent_task(
    host: PipelineTaskExecutorHost,
    *,
    agent_type: str,
    agent,
    task: dict,
    products: dict,
    task_queue: list,
    product: dict,
    pid: str,
    task_id: str,
) -> None:

    # Idempotency guard: only a task that is still actively running may be executed and
    # advance the product. If a concurrent runner / requeue already drove this task to a
    # terminal status, re-running it would double-process the agent and (worse) enqueue
    # the next sequential task twice. Bail out cleanly instead.
    current_status = str(task.get("status") or "").lower()
    if current_status not in ("running", "pending"):
        logger.info(
            "Skipping agent task %s for %s: already in terminal status '%s' (idempotency guard)",
            task_id,
            pid,
            current_status,
        )
        return

    try:
        from agents.base_agent import AgentInput
        from agents.product_profile import infer_delivery_profile, normalize_delivery_profile

        # Collect context from previous tasks
        context = build_task_context(task_queue, pid)

        dp_raw = product.get("delivery_profile")
        if dp_raw:
            delivery_profile = normalize_delivery_profile(str(dp_raw))
        else:
            delivery_profile = infer_delivery_profile(
                product.get("admin_instructions"),
                product.get("idea"),
            )

        agent_input_data = {
            "idea": product.get("idea", ""),
            "category": product.get("category", ""),
            "tags": product.get("tags", []),
            "specification": host._load_spec(pid),
            "architecture": host._load_arch(pid),
            "admin_instructions": product.get("admin_instructions", ""),
            "delivery_profile": delivery_profile,
            "production_mode": bool(product.get("production_mode")),
            "interface_locale": product.get("interface_locale") or "en",
            "content_locale": product.get("content_locale") or "auto",
            "surrogate_repair_hint": product.get("surrogate_repair_hint"),
            **task.get("input_data", {}),
        }
        # Gate-failing repair rounds get a stronger model when configured
        gfm = gate_failing_model()
        if gfm and isinstance(agent_input_data.get("quality_repair_round"), (int, float)) and int(agent_input_data["quality_repair_round"]) >= 1:
            agent_input_data["gate_failing_model"] = gfm

        agent_input = AgentInput(
            task_id=task_id,
            product_id=pid,
            agent_type=agent_type,
            data=agent_input_data,
            context=context,
            timestamp=time.time(),
        )

        from core.pipeline_cost_guard import PipelineCostBudgetExceeded, assert_product_within_budget
        from core.tracing import span

        try:
            assert_product_within_budget(pid)
        except PipelineCostBudgetExceeded as budget_exc:
            err = str(budget_exc)
            logger.error("Product %s pipeline LLM budget exceeded: %s", pid, err)
            task["status"] = "failed"
            task["error"] = err
            task["completed_at"] = time.time()
            task["failure_category"] = "budget_exceeded"
            if pid in products:
                # PARK, loudly, with the way back recorded — not a terminal failure. The cap once put
                # this product into FAILED silently: the worker looped "Factory on hold" every two
                # seconds, the healer skips FAILED by design, and raising the cap resumed nothing —
                # the product sat dead for 45 minutes until a human noticed and hand-edited state.
                # A money limit is a pause condition, not a verdict on the product.
                products[pid]["state_before_budget_park"] = str(
                    products[pid].get("state") or "DEV_FIXING"
                )
                products[pid]["budget_parked"] = True
                products[pid]["state"] = "FAILED"
                products[pid]["failure_reason"] = err
                products[pid]["updated_at"] = time.time()
                logger.error(
                    "PARKED ON BUDGET: %s — %s. Raise the cap and the worker resumes it "
                    "automatically; no manual state surgery needed.",
                    pid, err,
                )
            return

        logger.info(f"Calling real agent '{agent_type}' for task {task_id}")
        execute_timeout = _agent_execute_timeout_sec(agent_type)
        with span(
            "pipeline.agent_task",
            attributes={"agent.type": agent_type, "product.id": pid, "task.id": task_id},
        ):
            try:
                output = await asyncio.wait_for(agent.execute(agent_input), timeout=execute_timeout)
            except TimeoutError:
                raise TimeoutError(
                    f"agent '{agent_type}' execute exceeded {execute_timeout:.0f}s"
                ) from None

        if output.success:
            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["output_data"] = output.data
            task["metrics"] = output.metrics
            task["output_summary"] = str(output.data)[:200]
            if pid in products:
                host.peer_review_engine.register(
                    products[pid], agent_type, output.data if isinstance(output.data, dict) else {}
                )

            peer_blocked = False
            # QA failures use structured qa_gate_failed handling (repair budget + rich feedback).
            if pid in products and agent_type != "qa":
                peer_blocked = host.peer_review_engine.apply_block(
                    task, products[pid], task_queue, product
                )
            if peer_blocked:
                logger.warning("Peer review blocked progression for %s at %s", pid, agent_type)
                return

            if agent_type == "pm" and pid in products and isinstance(output.data, dict):
                dp = output.data.get("delivery_profile")
                if dp:
                    products[pid]["delivery_profile"] = dp
                    products[pid]["updated_at"] = time.time()

                # Did the spec keep what the operator actually asked for? Nothing checked
                # this before. A charter amended with two explicit requirements — free-tier
                # behaviour in the UI, an optional wallet — came back as a spec mentioning
                # neither, plus a custom chart builder, dashboard lifecycle states and a
                # "Free tier (100 invokes/mo)" that exists nowhere in this ecosystem. The
                # architect and developer then started on it. Deterministic, so it costs no
                # tokens to run and cannot itself hallucinate.
                charter_gate = charter_fidelity_report(
                    str(products[pid].get("admin_instructions") or ""),
                    host._load_spec(pid),
                )
                for invented in charter_gate.get("invented_terms") or []:
                    logger.warning(
                        "Spec for %s states a commercial term the charter does not contain: %s",
                        pid, invented.get("claim"),
                    )
                if not charter_gate.get("passed"):
                    dropped = ", ".join(
                        str(g.get("section")) for g in charter_gate.get("gaps") or []
                    )
                    logger.error(
                        "Spec for %s dropped operator requirement section(s): %s", pid, dropped
                    )
                    charter_retry = requeue_pm_bounded(
                        pid,
                        products,
                        task_queue,
                        host._get_priority,
                        reason="charter_requirement_dropped",
                        instructions=(
                            str(products[pid].get("admin_instructions") or "")
                            + "\n\n=== SPEC CORRECTION REQUIRED ===\n"
                            + feedback_for_pm(charter_gate)
                        ),
                    )
                    if charter_retry is not None:
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state="SPEC_WRITTEN",
                            next_task=charter_retry,
                            task_id=str(task.get("id") or ""),
                            reason=f"spec dropped operator requirements: {dropped}",
                        )
                        return
                    # The requeue declined — cap reached, budget spent, or a PM task already
                    # queued. Falling through would send the developer at a spec the gate has
                    # just judged deficient, which is what happened before this branch
                    # existed: the log said "leaving it for human review" while the product
                    # walked on to CODE_COMMITTED. Park it instead, and say why.
                    products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                    products[pid]["failure_reason"] = (
                        "Specification omits operator requirement section(s): "
                        f"{dropped}. Automatic PM re-runs are exhausted or blocked, so the "
                        "product is held rather than built against a spec that is missing "
                        "what was asked for."
                    )
                    products[pid]["updated_at"] = time.time()
                    logger.error(
                        "Holding %s at HUMAN_REVIEW_PENDING: spec still omits %s and PM cannot "
                        "be re-queued.",
                        pid,
                        dropped,
                    )
                    return

            if agent_type in ("architect", "landing_architect") and pid in products:
                # Last checkpoint before development: a product with no specification on
                # disk must go back for one rather than forward to the developer. Every
                # gate downstream of here judges the build against its spec, so sending it
                # on produces verdicts that cannot be satisfied by changing code.
                spec_recovery_task = requeue_pm_when_spec_absent(
                    pid,
                    products,
                    task_queue,
                    host._get_priority,
                    spec_loader=host._load_spec,
                )
                if spec_recovery_task is not None:
                    # Leave this architect row CANCELLED, as append_product_task just set it.
                    # Marking it completed was a one-line self-inflicted wound: the same
                    # cycle's reconcile_all_products_from_tasks counts completed rows, ranks
                    # the row's ARCH_DESIGNED above the MARKET_RESEARCHED we just rewound to,
                    # and puts the product back — after which the PM task is three ranks
                    # behind and queue hygiene cancels it as regressive, or archives it as
                    # superseded if PM fails. The product then healed forward into
                    # development with no specification, having already spent a recovery
                    # attempt: exactly the state this checkpoint exists to prevent, reached
                    # through the checkpoint itself. Cancelled rows are skipped by the
                    # reconciler, so the rewind stands.
                    task["error"] = (
                        "superseded at the architecture checkpoint: no specification "
                        "artifact existed, so the spec stage runs again first"
                    )
                    task["completed_at"] = time.time()
                    host._audit_agent_handoff(
                        product_id=pid,
                        from_agent=agent_type,
                        from_state="ARCH_DESIGNED",
                        next_task=spec_recovery_task,
                        task_id=str(task.get("id") or ""),
                        reason="specification artifact absent at architecture checkpoint",
                    )
                    return
                if not _spec_has_substance(host._load_spec(pid)):
                    # Same rule as the charter gate below: a declined recovery must not read
                    # as permission to continue. Without this, the cap and budget paths log
                    # "leaving for human review" and then hand the developer a product with
                    # no specification at all — the exact condition that burned ~70 rounds.
                    products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                    products[pid]["failure_reason"] = (
                        "No specification artifact exists and PM cannot be re-queued "
                        "(attempts exhausted, budget spent, or a PM task already pending). "
                        "Held rather than developed blind."
                    )
                    products[pid]["updated_at"] = time.time()
                    logger.error(
                        "Holding %s at HUMAN_REVIEW_PENDING: no specification and no PM "
                        "recovery available.",
                        pid,
                    )
                    return

                # Charter fidelity is checked HERE as well as after PM, because the check
                # after PM only runs when PM *succeeds*. A PM task that fails — "LLM
                # returned invalid/non-JSON response", an ordinary transient — is cancelled,
                # and the pipeline then heals forward through methodologist, architect and
                # design_critic to the developer, carrying whatever stale spec is still on
                # disk. That is exactly what happened: a spec missing both of the operator's
                # marked requirements reached CODE_COMMITTED because the gate guarding it was
                # attached to an event that never occurred. A gate on the last checkpoint
                # before development does not care how the spec stage ended.
                arch_charter = charter_fidelity_report(
                    str(products[pid].get("admin_instructions") or ""),
                    host._load_spec(pid),
                )
                if not arch_charter.get("passed"):
                    dropped_here = ", ".join(
                        str(g.get("section")) for g in arch_charter.get("gaps") or []
                    )
                    logger.error(
                        "Spec for %s still omits operator requirement section(s) at the "
                        "architecture checkpoint: %s",
                        pid,
                        dropped_here,
                    )
                    retry_here = requeue_pm_bounded(
                        pid,
                        products,
                        task_queue,
                        host._get_priority,
                        reason="charter_requirement_dropped_at_arch",
                        instructions=(
                            str(products[pid].get("admin_instructions") or "")
                            + "\n\n=== SPEC CORRECTION REQUIRED ===\n"
                            + feedback_for_pm(arch_charter)
                        ),
                    )
                    if retry_here is not None:
                        task["error"] = (
                            "superseded at the architecture checkpoint: the specification "
                            f"omits {dropped_here}"
                        )
                        task["completed_at"] = time.time()
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state="ARCH_DESIGNED",
                            next_task=retry_here,
                            task_id=str(task.get("id") or ""),
                            reason=f"spec omits operator requirements: {dropped_here}",
                        )
                        return
                    products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                    products[pid]["failure_reason"] = (
                        "Specification omits operator requirement section(s): "
                        f"{dropped_here}. PM cannot be re-queued, so the product is held "
                        "rather than built without what was asked for."
                    )
                    products[pid]["updated_at"] = time.time()
                    logger.error(
                        "Holding %s at HUMAN_REVIEW_PENDING: spec omits %s and PM cannot be "
                        "re-queued.",
                        pid,
                        dropped_here,
                    )
                    return

                arch_ok, arch_issues = host._architecture_gate(
                    pid, delivery_profile=delivery_profile_from_product_dict(products[pid])
                )
                if not arch_ok:
                    task["status"] = "failed"
                    task["error"] = "architecture gate failed: " + "; ".join(arch_issues)
                    task["completed_at"] = time.time()
                    products[pid]["state"] = "METHODOLOGY_REVIEWED"
                    products[pid]["updated_at"] = time.time()
                    existing = any(
                        t.get("product_id") == pid
                        and is_architect_agent(t.get("agent_type"))
                        and t.get("status") in ("pending", "running")
                        for t in task_queue
                    )
                    if not existing:
                        arch_retry_task = {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": "architect",
                            "state": "ARCH_DESIGNED",
                            "status": "pending",
                            "retry_count": 0,
                            "max_retries": 3,
                            "input_data": {
                                "product_id": pid,
                                "idea": product.get("idea", ""),
                                "architecture_gate_feedback": arch_issues,
                                "admin_instructions": (
                                    "Architecture gatekeeper failed. Fix layering, module boundaries, "
                                    "and migration discipline before developer stage."
                                ),
                            },
                            "created_at": time.time(),
                            "priority": host._get_priority("architect"),
                        }
                        task_queue.append(arch_retry_task)
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state=str(task.get("state") or ""),
                            next_task=arch_retry_task,
                            task_id=task_id,
                            reason="architecture_gate",
                            success=False,
                            output_data=output.data if isinstance(output.data, dict) else None,
                            extra={"issues": arch_issues[:8]},
                        )
                    logger.warning("Architecture gate blocked developer stage for %s: %s", pid, arch_issues)
                    return

            if agent_type in ("developer", "landing_developer") and pid in products:
                try:
                    host._apply_watermark_policy(pid, products[pid])
                except Exception as wm_exc:
                    logger.warning("Watermark policy apply failed for %s: %s", pid, wm_exc)
                try:
                    from web.backend.services.site_head_snippet import (
                        inject_published_site_head_if_configured,
                    )

                    inject_published_site_head_if_configured(host.data_root, pid)
                except Exception as head_exc:
                    logger.warning("Published site <head> inject failed for %s: %s", pid, head_exc)
                try:
                    from web.backend.services.site_badge import inject_site_badge_if_enabled

                    inject_site_badge_if_enabled(host.data_root, pid)
                except Exception as badge_exc:
                    logger.warning("Site badge inject failed for %s: %s", pid, badge_exc)
                try:
                    from web.backend.services.landing_embeds import inject_landing_embeds_for_product

                    inject_landing_embeds_for_product(host.data_root, pid, products[pid])
                except Exception as embed_exc:
                    logger.warning("Landing embed inject failed for %s: %s", pid, embed_exc)

            if agent_type == "marketing" and pid in products:
                try:
                    from web.backend.services.landing_embeds import inject_landing_embeds_for_product

                    inject_landing_embeds_for_product(host.data_root, pid, products[pid])
                except Exception as embed_exc:
                    logger.warning("Landing embed inject after marketing failed for %s: %s", pid, embed_exc)

            live_gate_failed = False
            live_gate_payload: dict = {}
            live_mesh_payment_parked = False
            if agent_type == "devops" and output.success and pid in products:
                try:
                    from web.backend.services.auto_publish import try_publish_after_devops

                    pub = await asyncio.to_thread(try_publish_after_devops, pid)
                    if isinstance(pub, dict) and pub.get("published_url"):
                        products[pid]["published_url"] = str(pub["published_url"])
                        products[pid]["updated_at"] = time.time()
                    # A full-stack product publishes twice: a live factory preview and
                    # a public Vercel deployment. Keep the public link too — it is the
                    # one anyone outside the factory can actually open.
                    if isinstance(pub, dict) and pub.get("vercel_url"):
                        products[pid]["vercel_url"] = str(pub["vercel_url"])
                        products[pid]["updated_at"] = time.time()
                    lg = (pub or {}).get("live_gate") if isinstance(pub, dict) else None
                    if isinstance(lg, dict):
                        products[pid]["live_gate"] = lg
                        if not lg.get("skipped") and lg.get("passed") is False:
                            live_gate_failed = True
                            live_gate_payload = lg
                            logger.warning(
                                "Live Vercel UI gate failed for %s: %s",
                                pid,
                                "; ".join(str(i)[:140] for i in (lg.get("issues") or [])[:3]),
                            )
                except Exception as ap_exc:
                    logger.warning("Auto-publish after DevOps failed for %s: %s", pid, ap_exc)
                try:
                    from web.backend.services.product_catalog_publish import (
                        try_publish_product_catalog,
                    )

                    cat = await asyncio.to_thread(try_publish_product_catalog, pid)
                    if isinstance(cat, dict):
                        products[pid]["product_catalog"] = cat
                        products[pid]["updated_at"] = time.time()
                except Exception as cat_exc:
                    logger.warning("Product catalog publish failed for %s: %s", pid, cat_exc)
                try:
                    from web.backend.services.railway_deploy import (
                        try_railway_deploy_after_devops,
                    )

                    rw = await asyncio.to_thread(try_railway_deploy_after_devops, pid)
                    if isinstance(rw, dict) and rw.get("recorded"):
                        logger.info(
                            "Railway deploy hook after DevOps for %s: %s",
                            pid,
                            rw.get("path", ""),
                        )
                except Exception as rw_exc:
                    logger.warning("Railway deploy hook after DevOps failed for %s: %s", pid, rw_exc)

            if (
                not live_gate_failed
                and pid in products
                and str(task.get("state") or "").upper() == "COMPLETED"
            ):
                try:
                    from web.backend.services.live_deployment_gate import (
                        live_gate_from_saved_vercel_record,
                    )

                    saved_lg = live_gate_from_saved_vercel_record(pid)
                    if saved_lg:
                        live_gate_failed = True
                        live_gate_payload = saved_lg
                        products[pid]["live_gate"] = saved_lg
                        logger.warning(
                            "Refusing COMPLETED for %s: saved Vercel --prod failed (%s)",
                            pid,
                            "; ".join(str(i)[:140] for i in (saved_lg.get("issues") or [])[:3]),
                        )
                except Exception as saved_exc:
                    logger.warning("Saved Vercel publish check failed for %s: %s", pid, saved_exc)

            source_auth_mismatch = False
            if pid in products:
                try:
                    from core.paths import code_dir as resolve_code_dir
                    from web.backend.services.vercel_fullstack_adapter import (
                        relay_source_session_mismatch,
                        relay_source_uuid_pk_mismatch,
                        relay_source_pinned_mismatch,
                    )

                    _code = resolve_code_dir(pid, data_root=host.data_root)
                    source_auth_mismatch = (
                        relay_source_session_mismatch(_code)
                        or relay_source_uuid_pk_mismatch(_code)
                        or relay_source_pinned_mismatch(_code)
                    )
                except Exception as src_exc:
                    logger.debug(
                        "source auth mismatch probe failed for %s: %s", pid, src_exc
                    )

            if (live_gate_failed or source_auth_mismatch) and pid in products:
                # Known live-auth class (401 salt, string UUID → UUID column 500):
                # the factory patches data/code and republishes. Cursor must not SSH.
                try:
                    from web.backend.services.live_deployment_gate import (
                        live_gate_is_payment_ops,
                        try_factory_live_auth_heal,
                    )

                    if not live_gate_is_payment_ops(live_gate_payload):
                        heal = await asyncio.to_thread(
                            try_factory_live_auth_heal,
                            pid,
                            products[pid],
                            live_gate_payload,
                            data_root=host.data_root,
                        )
                        if heal.get("healed"):
                            live_gate_failed = False
                            lg_ok = heal.get("live_gate")
                            if isinstance(lg_ok, dict):
                                live_gate_payload = lg_ok
                                products[pid]["live_gate"] = lg_ok
                            pub2 = heal.get("publish")
                            if isinstance(pub2, dict) and pub2.get("vercel_url"):
                                products[pid]["vercel_url"] = str(pub2["vercel_url"])
                            logger.warning(
                                "Live auth autofix healed %s — continuing as a passed live gate",
                                pid,
                            )
                        elif heal.get("applied"):
                            lg_still = heal.get("live_gate")
                            if isinstance(lg_still, dict):
                                live_gate_payload = lg_still
                                products[pid]["live_gate"] = lg_still
                except Exception as heal_exc:
                    logger.warning("Live auth autofix failed for %s: %s", pid, heal_exc)

            # Track previous state for daily revision handling
            prev_state = products[pid].get("state", "") if pid in products else ""

            # Recorded here because the budget decision is made later, on the QA output, which cannot
            # see whether the developer wrote anything. The first version asked the QA output that
            # question and it answered "yes" every time — a QA result always carries findings — so the
            # guard never fired and the counter kept climbing through the outage exactly as before.
            if agent_type == "developer" and pid in products:
                products[pid]["last_round_generated"] = _round_produced_output(products[pid], output)

            qg = output.data.get("quality_gates") if isinstance(output.data, dict) else None
            qa_gate_failed = (
                agent_type == "qa"
                and isinstance(qg, dict)
                and qg.get("passed") is False
            )

            sec_reasons: list[str] = []
            security_gate_failed = False
            if agent_type == "security" and output.success and isinstance(output.data, dict):
                ok_sec, sec_reasons = security_scan_passes_pipeline_gate(output.data)
                security_gate_failed = not ok_sec
                if ok_sec and pid in products:
                    products[pid]["security_repair_round"] = 0

            quality_gates_exhausted = False
            security_budget_exhausted = False
            auto_recovered = False
            max_quality_loops = (
                max_pipeline_repair_rounds_for_product(products[pid])
                if pid in products
                else max_pipeline_repair_rounds_for_delivery_profile(None)
            )
            sec_raw = os.environ.get("AIFACTORY_MAX_SECURITY_LOOPS")
            if sec_raw is not None and str(sec_raw).strip() != "":
                try:
                    max_security_loops = max(1, int(sec_raw))
                except ValueError:
                    max_security_loops = max_quality_loops
            else:
                max_security_loops = max_quality_loops

            # Successful QA (all gates pass): reset repair counter
            if (
                agent_type == "qa"
                and isinstance(qg, dict)
                and qg.get("passed") is True
                and pid in products
            ):
                products[pid]["quality_repair_round"] = 0
                # Gates passed — the surrogate's repair guidance is now stale; drop it.
                products[pid].pop("surrogate_repair_hint", None)

            # Advance the product state
            target_state = task.get("state", "")
            new_repair_round = 0
            if qa_gate_failed and pid in products:
                # A round the model never got to attempt must not spend the repair budget. Measured on
                # a live run: the provider began answering 402 Payment Required at 01:05, the developer
                # returned "0 files" every time, and the counter still climbed from 33 to 58 — twenty
                # five rounds of budget consumed by an outage that has nothing to do with the product's
                # quality. The budget exists to stop a product looping forever on defects it cannot
                # fix, not to punish it for an empty wallet.
                _generation_happened = bool(products[pid].get("last_round_generated", True))
                if not _generation_happened:
                    new_repair_round = int(products[pid].get("quality_repair_round", 0) or 0)
                    logger.warning(
                        "Repair budget not charged for %s: the round produced no generated output "
                        "(provider unavailable or empty response), so round %s stands.",
                        pid, new_repair_round,
                    )
                else:
                    new_repair_round = products[pid].get("quality_repair_round", 0) + 1
                    products[pid]["quality_repair_round"] = new_repair_round
                qa_result = output.data.get("qa_result") if isinstance(output.data, dict) else {}
                if isinstance(qa_result, dict):
                    products[pid]["last_bug_context"] = {
                        "source": "qa",
                        "qa_findings": qa_result.get("bugs_found") or [],
                        "test_output": qa_result.get("test_results") or {},
                        "quality_gates_feedback": dict(qg or {}),
                    }

                # Did that round actually help? QA has just performed the only measurement
                # that counts — it installed, built the frontend, booted the app and swept it
                # — so this is where a regressive round gets thrown away. Across eight
                # measured rounds on one product the loop fixed ~14 findings and introduced
                # ~15 each time: 101 of 114 distinct defects existed in exactly ONE round,
                # and only a single defect persisted (an unsatisfiable gate). The plateau at
                # 12-16 was churn, not a stubborn core, and the developer's own guard could
                # not see it because its score is static while QA's is not.
                _guard_round_regression(products[pid], pid, qa_result, host)
                products[pid]["updated_at"] = time.time()
                from orchestrator.qa_repair_policy import (
                    notify_qa_human_review_pending,
                    resolve_qa_repair_after_failure,
                )

                if products[pid].get("pipeline_stuck_reason"):
                    # Identical rejected tree, or accepted churn that never lowered the score.
                    # Either way another developer round cannot converge — do not enqueue one,
                    # and do not let auto-recovery stamp COMPLETED over a tree QA just failed.
                    quality_gates_exhausted = True
                    effective_round = new_repair_round
                    products[pid]["quality_repair_round"] = new_repair_round
                    products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                    if not products[pid].get("human_review_kind"):
                        products[pid]["human_review_kind"] = "qa_repair_stuck"
                    if not products[pid].get("human_review_reason"):
                        products[pid]["human_review_reason"] = products[pid]["pipeline_stuck_reason"]
                    notify_qa_human_review_pending(pid, products[pid])
                    logger.error(
                        "Product %s: repair loop stuck → HUMAN_REVIEW_PENDING (round %s/%s): %s",
                        pid,
                        new_repair_round,
                        max_quality_loops,
                        products[pid]["pipeline_stuck_reason"],
                    )
                else:
                    quality_gates_exhausted, effective_round, product_state = resolve_qa_repair_after_failure(
                        products[pid],
                        new_repair_round=new_repair_round,
                        max_quality_loops=max_quality_loops,
                    )
                    new_repair_round = effective_round
                    products[pid]["quality_repair_round"] = effective_round
                    products[pid]["state"] = product_state
                    from orchestrator.auto_recovery import try_auto_recovery_after_qa_failure

                    if try_auto_recovery_after_qa_failure(
                        products[pid],
                        task_queue,
                        repair_round=new_repair_round,
                        data_root=host.data_root,
                    ):
                        auto_recovered = True
                        quality_gates_exhausted = False
                        qa_gate_failed = False
                        products[pid]["state"] = "COMPLETED"
                        target_state = "COMPLETED"
                    elif quality_gates_exhausted:
                        from core.autonomy_mode import is_full_autonomy
                        from orchestrator.autonomy_bridge import resolve_human_gate_async

                        if is_full_autonomy():
                            resolved = await resolve_human_gate_async(
                                products[pid],
                                point="qa_repair_exhausted",
                                data_root=host.data_root,
                                context={"quality_gates": qg},
                                llm_router=getattr(host, "_llm_router", None),
                            )
                            if resolved:
                                products[pid]["state"] = resolved
                                logger.warning(
                                    "Product %s: QA exhaust resolved by surrogate → %s",
                                    pid,
                                    resolved,
                                )
                                quality_gates_exhausted = False
                        if quality_gates_exhausted:
                            notify_qa_human_review_pending(pid, products[pid])
                        logger.warning(
                            "Product %s: QA repair budgets exhausted → HUMAN_REVIEW_PENDING (round %s/%s)",
                            pid,
                            effective_round,
                            max_quality_loops,
                        )
                    else:
                        products[pid]["state"] = "BUG_FOUND"
            elif security_gate_failed and pid in products:
                new_sec_round = products[pid].get("security_repair_round", 0) + 1
                products[pid]["security_repair_round"] = new_sec_round
                scan_payload = output.data if isinstance(output.data, dict) else {}
                products[pid]["last_bug_context"] = {
                    "source": "security",
                    "reasons": sec_reasons,
                    "security_score": scan_payload.get("security_score"),
                }
                products[pid]["updated_at"] = time.time()
                from orchestrator.qa_repair_policy import (
                    notify_qa_human_review_pending,
                    resolve_security_repair_after_failure,
                )

                security_budget_exhausted, product_state = resolve_security_repair_after_failure(
                    products[pid],
                    new_sec_round=new_sec_round,
                    max_security_loops=max_security_loops,
                )
                products[pid]["state"] = product_state
                if security_budget_exhausted:
                    from core.autonomy_mode import is_full_autonomy
                    from orchestrator.autonomy_bridge import resolve_human_gate_async

                    if is_full_autonomy():
                        resolved = await resolve_human_gate_async(
                            products[pid],
                            point="security_repair_exhausted",
                            data_root=host.data_root,
                            context={"security_reasons": sec_reasons},
                            llm_router=getattr(host, "_llm_router", None),
                        )
                        if resolved:
                            products[pid]["state"] = resolved
                            logger.warning(
                                "Product %s: security exhaust resolved by surrogate → %s",
                                pid,
                                resolved,
                            )
                            security_budget_exhausted = False
                    if security_budget_exhausted:
                        notify_qa_human_review_pending(pid, products[pid])
                    logger.warning(
                        "Product %s: security repair budgets exhausted → HUMAN_REVIEW_PENDING",
                        pid,
                    )
                else:
                    products[pid]["state"] = "BUG_FOUND"
            elif live_gate_failed and pid in products:
                # The sandbox was green. Vercel was not. Do not walk to SALES/COMPLETED.
                from web.backend.services.live_deployment_gate import (
                    live_gate_is_payment_ops,
                    park_product_live_mesh_payment_ops,
                )

                if live_gate_is_payment_ops(live_gate_payload):
                    park_product_live_mesh_payment_ops(products[pid], live_gate_payload)
                    live_mesh_payment_parked = True
                    quality_gates_exhausted = True
                    logger.warning(
                        "Live Vercel gate is payment-ops for %s — HUMAN_REVIEW_PENDING "
                        "(no developer, repair budget not charged)",
                        pid,
                    )
                else:
                    new_repair_round = int(products[pid].get("quality_repair_round") or 0) + 1
                    products[pid]["quality_repair_round"] = new_repair_round
                    products[pid]["last_bug_context"] = {
                        "source": "live_deployment_gate",
                        "quality_gates_feedback": {
                            "passed": False,
                            "blocking_defects": list(live_gate_payload.get("issues") or []),
                            "repair_scope": list(live_gate_payload.get("repair_scope") or []),
                            "live_gate": live_gate_payload,
                            "reasons": list(live_gate_payload.get("issues") or []),
                        },
                    }
                    products[pid]["updated_at"] = time.time()
                    if new_repair_round > max_quality_loops:
                        quality_gates_exhausted = True
                        products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                        logger.warning(
                            "Live Vercel gate failed for %s — repair budgets exhausted "
                            "(round %s/%s) → HUMAN_REVIEW_PENDING",
                            pid,
                            new_repair_round,
                            max_quality_loops,
                        )
                    else:
                        products[pid]["state"] = "BUG_FOUND"
                        logger.warning(
                            "Live Vercel gate failed for %s (repair %s/%s); "
                            "BUG_FOUND → developer DEV_FIXING",
                            pid,
                            new_repair_round,
                            max_quality_loops,
                        )
            elif target_state and pid in products:
                # If product was COMPLETED and this is a revision task,
                # keep it in COMPLETED state after monitoring finishes
                if prev_state == "COMPLETED" and target_state == "EVOLUTION_ANALYZING":
                    products[pid]["state"] = "COMPLETED"
                    products[pid]["last_market_revision"] = time.time()
                else:
                    effective_state = target_state
                    if (
                        agent_type == "devops"
                        and str(target_state or "").upper() == "HUMAN_REVIEW_PENDING"
                    ):
                        from core.autonomy_mode import is_full_autonomy
                        from orchestrator.autonomy_bridge import resolve_human_gate_async
                        from web.backend.services.product_followup import (
                            post_devops_human_review_approved,
                        )

                        if is_full_autonomy():
                            resolved = await resolve_human_gate_async(
                                products[pid],
                                point="post_devops_gate",
                                data_root=host.data_root,
                                llm_router=getattr(host, "_llm_router", None),
                            )
                            if resolved:
                                effective_state = resolved
                        elif post_devops_human_review_approved(pid):
                            effective_state = "SALES_ACTIVE"
                    products[pid]["state"] = effective_state
                products[pid]["updated_at"] = time.time()
                try:
                    from core.outcome_memory import record_terminal_outcome

                    st_terminal = str(products[pid].get("state") or "").upper()
                    if st_terminal in ("COMPLETED", "FAILED"):
                        record_terminal_outcome(host.data_root, products[pid])
                except Exception as exc:
                    logger.warning("record_terminal_outcome failed for %s: %s", pid, exc)

            # Analyst periodic monitoring may request a shipped-slice refresh (shares QA repair budget)
            if (
                agent_type == "analyst"
                and isinstance(output.data, dict)
                and (task.get("input_data") or {}).get("mode") == "monitoring"
                and prev_state == "COMPLETED"
                and target_state == "EVOLUTION_ANALYZING"
                and pid in products
                and products[pid].get("state") == "COMPLETED"
                and monitoring_dev_refresh_enabled()
            ):
                from web.backend.services.policy_audit import _dev_fixing_pending

                want_r, qg_payload = monitoring_refresh_decision(output.data)
                if want_r:
                    if _dev_fixing_pending(task_queue, pid):
                        logger.info(
                            "Monitoring requested refresh for %s but developer DEV_FIXING already pending",
                            pid,
                        )
                    else:
                        mr_round = int(products[pid].get("quality_repair_round") or 0) + 1
                        if mr_round > max_quality_loops:
                            logger.warning(
                                "Monitoring refresh skipped for %s — quality repair budget exhausted (%s/%s)",
                                pid,
                                mr_round,
                                max_quality_loops,
                            )
                        else:
                            products[pid]["state"] = "BUG_FOUND"
                            products[pid]["quality_repair_round"] = mr_round
                            products[pid]["updated_at"] = time.time()
                            dev_task = {
                                "id": f"task-{uuid.uuid4().hex[:12]}",
                                "product_id": pid,
                                "agent_type": "developer",
                                "state": "DEV_FIXING",
                                "status": "pending",
                                "retry_count": 0,
                                "max_retries": 3,
                                "input_data": {
                                    "product_id": pid,
                                    "idea": product.get("idea", ""),
                                    "quality_gates_feedback": qg_payload,
                                    "quality_repair_round": mr_round,
                                    "quality_repair_max": max_quality_loops,
                                    "qa_gate_blocked": True,
                                    "monitoring_refresh_trigger": True,
                                },
                                "created_at": time.time(),
                                "priority": host._get_priority("developer"),
                            }
                            task_queue.append(dev_task)
                            host._audit_agent_handoff(
                                product_id=pid,
                                from_agent=agent_type,
                                from_state=prev_state,
                                next_task=dev_task,
                                task_id=task_id,
                                reason="monitoring_refresh",
                                output_data=output.data if isinstance(output.data, dict) else None,
                            )
                            logger.warning(
                                "Monitoring → developer refresh for %s (repair %s/%s)",
                                pid,
                                mr_round,
                                max_quality_loops,
                            )

            eff_state = products[pid].get("state", "") if pid in products else target_state
            logger.info(f"Agent '{agent_type}' completed task {task_id} -> {eff_state}")
            record_task_lesson(pid, agent_type, eff_state, output.data if isinstance(output.data, dict) else {})

            try:
                from web.backend.services.pipeline_chat_notify import (
                    notify_pipeline_task_done,
                )

                idea_snip = (product.get("idea") or "") if pid in products else ""
                notify_pipeline_task_done(
                    agent_type=agent_type,
                    product_id=pid,
                    target_state=eff_state or "",
                    idea_snippet=idea_snip,
                )
            except Exception:
                logger.debug("Corporate chat pipeline notify skipped", exc_info=False)

            # Check if product reached COMPLETED
            critic_blocked = False
            if target_state == "COMPLETED" and pid in products:
                ok_release, critic_issues = host._release_critic(pid, products[pid])
                if not ok_release:
                    critic_blocked = True
                    # Bounded repair budget with escalation (mirrors QA/security).
                    # Without a cap the product ping-pongs COMPLETED→release_critic→
                    # DEV_FIXING→… forever, burning paid heavy LLM calls — especially
                    # for issues code regen cannot fix (missing real feedback rows,
                    # architect-owned design_system.json).
                    new_critic_round = int(products[pid].get("critic_repair_round", 0) or 0) + 1
                    products[pid]["critic_repair_round"] = new_critic_round
                    products[pid]["updated_at"] = time.time()
                    products[pid]["last_bug_context"] = {
                        "source": "release_critic",
                        "issues": critic_issues,
                    }
                    critic_exhausted = new_critic_round > max_quality_loops
                    if critic_exhausted:
                        from core.autonomy_mode import is_full_autonomy
                        from orchestrator.autonomy_bridge import resolve_human_gate_async
                        from orchestrator.qa_repair_policy import notify_qa_human_review_pending

                        products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                        if is_full_autonomy():
                            resolved = await resolve_human_gate_async(
                                products[pid],
                                point="release_critic_exhausted",
                                data_root=host.data_root,
                                context={"critic_issues": critic_issues},
                                llm_router=getattr(host, "_llm_router", None),
                            )
                            if resolved:
                                products[pid]["state"] = resolved
                                critic_exhausted = False
                                logger.warning(
                                    "Product %s: release-critic exhaust resolved by surrogate → %s",
                                    pid,
                                    resolved,
                                )
                        if critic_exhausted:
                            notify_qa_human_review_pending(pid, products[pid])
                            logger.warning(
                                "Product %s: release-critic repair budget exhausted → "
                                "HUMAN_REVIEW_PENDING (round %s/%s); issues=%s",
                                pid,
                                new_critic_round,
                                max_quality_loops,
                                critic_issues,
                            )
                    else:
                        products[pid]["state"] = "BUG_FOUND"
                        dev_task = {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": "developer",
                            "state": "DEV_FIXING",
                            "status": "pending",
                            "retry_count": 0,
                            "max_retries": 3,
                            "input_data": {
                                "product_id": pid,
                                "idea": product.get("idea", ""),
                                "critic_feedback": {
                                    "gate": "release_critic",
                                    "issues": critic_issues,
                                },
                                "critic_blocked": True,
                                "critic_repair_round": new_critic_round,
                                "critic_repair_max": max_quality_loops,
                            },
                            "created_at": time.time(),
                            "priority": host._get_priority("developer"),
                        }
                        task_queue.append(dev_task)
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state=prev_state,
                            next_task=dev_task,
                            task_id=task_id,
                            reason="release_critic",
                            blocked=True,
                            output_data=output.data if isinstance(output.data, dict) else None,
                        )
                        logger.warning(
                            "Release critic blocked completion for %s; queued DEV_FIXING "
                            "(%s) round %s/%s",
                            pid,
                            dev_task["id"],
                            new_critic_round,
                            max_quality_loops,
                        )
            if target_state == "COMPLETED" and not critic_blocked and pid in products:
                logger.info(f"Product {pid} pipeline completed!")
                try:
                    from web.backend.services.funnel_distribute import on_product_completed

                    on_product_completed(pid, products[pid])
                except Exception:
                    logger.debug("funnel_distribute failed for %s", pid, exc_info=True)
                try:
                    from web.backend.services.funnel_leads import (
                        notify_lead_product_completed,
                        on_product_state_change,
                    )

                    on_product_state_change(pid, products[pid])
                    await notify_lead_product_completed(pid, products[pid])
                except Exception:
                    logger.debug("funnel lead notify failed for %s", pid, exc_info=True)
                try:
                    spec_done = host._load_spec(pid)
                    dp_done = delivery_profile_from_product_dict(products[pid]) if pid in products else None
                    mq_done = evaluate_marketplace_quality(
                        pid, specification=spec_done, delivery_profile=dp_done
                    )
                    if mq_done.get("eligible"):
                        from web.backend.services.product_followup import (
                            merge_mark_storefront_established_listing,
                        )

                        if merge_mark_storefront_established_listing(pid):
                            products[pid]["updated_at"] = time.time()
                except Exception:
                    logger.debug(
                        "merge_mark_storefront_established_listing at completion failed for %s",
                        pid,
                        exc_info=True,
                    )
            elif prev_state == "COMPLETED" and target_state == "EVOLUTION_ANALYZING":
                # Periodic monitoring for COMPLETED product — don't create next sequential task
                logger.info(f"Periodic market monitoring completed for product {pid}")
            elif critic_blocked:
                logger.info("Completion held for %s due to release critic findings", pid)
            elif qa_gate_failed and not quality_gates_exhausted and not auto_recovered:
                dev_task = {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "developer",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "demo_quality_feedback": (qg or {}).get("demo_quality"),
                        "qa_findings": ((output.data or {}).get("qa_result") or {}).get("bugs_found", []),
                        "test_output": ((output.data or {}).get("qa_result") or {}).get("test_results", {}),
                        "quality_gates_feedback": {
                            "passed": (qg or {}).get("passed"),
                            # The two keys agents/dev.py reads to build
                            # `fix_these_first_they_break_the_build` and
                            # `only_edit_these_paths`. This hand-picked subset omitted both, so
                            # the prioritisation and scoping machinery existed on the consumer
                            # side and was fed nothing: every round received a flat list in
                            # which "the app does not boot" sat beside "missing empty state",
                            # and rounds were measurably spent on the cosmetics.
                            "blocking_defects": (qg or {}).get("blocking_defects"),
                            "repair_scope": (qg or {}).get("repair_scope"),
                            # The gates my static detectors report through. Without these the
                            # round cannot see a dead endpoint, a duplicate table or a wrong
                            # mesh envelope at all.
                            "module_health": (qg or {}).get("module_health"),
                            "frontend_build": (qg or {}).get("frontend_build"),
                            "api_contract": (qg or {}).get("api_contract"),
                            "demo_journey": (qg or {}).get("demo_journey"),
                            "demo_quality": (qg or {}).get("demo_quality"),
                            "browser_preview_e2e": (qg or {}).get("browser_preview_e2e"),
                            "backend_runtime_e2e": (qg or {}).get("backend_runtime_e2e"),
                            "methodology_review": (qg or {}).get("methodology_review"),
                            "reasons": (qg or {}).get("reasons"),
                            "issue_codes": [
                                i.get("code")
                                for i in ((qg or {}).get("demo_quality") or {}).get("issues", [])
                                if isinstance(i, dict) and i.get("code")
                            ],
                        },
                        "quality_repair_round": new_repair_round,
                        "quality_repair_max": max_quality_loops,
                        "qa_gate_blocked": True,
                    },
                    "created_at": time.time(),
                    "priority": host._get_priority("developer"),
                }
                exists = any(
                    t.get("product_id") == pid
                    and is_developer_agent(t.get("agent_type"))
                    and t.get("state") == "DEV_FIXING"
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                )
                if not exists:
                    task_queue.append(dev_task)
                    host._audit_agent_handoff(
                        product_id=pid,
                        from_agent=agent_type,
                        from_state=prev_state,
                        next_task=dev_task,
                        task_id=task_id,
                        reason="qa_gate",
                        blocked=True,
                        output_data=output.data if isinstance(output.data, dict) else None,
                    )
                    logger.warning(
                        f"QA gates failed for {pid} (repair {new_repair_round}/{max_quality_loops}); "
                        "BUG_FOUND → developer DEV_FIXING (mandatory regen/fix until gates pass or limit)"
                    )
            elif qa_gate_failed and quality_gates_exhausted:
                logger.warning(
                    "QA gates failed for %s — repair budgets exhausted; awaiting human review (not FAILED)",
                    pid,
                )
            elif security_gate_failed and not security_budget_exhausted:
                scan_payload = output.data if isinstance(output.data, dict) else {}
                sec_fb = build_security_gate_feedback(scan_payload, sec_reasons)
                sec_round = products[pid].get("security_repair_round", 0)
                dev_task = {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "developer",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "security_gate_feedback": sec_fb,
                        "security_repair_round": sec_round,
                        "security_repair_max": max_security_loops,
                        "security_gate_blocked": True,
                        "qa_gate_blocked": True,
                    },
                    "created_at": time.time(),
                    "priority": host._get_priority("developer"),
                }
                exists = any(
                    t.get("product_id") == pid
                    and is_developer_agent(t.get("agent_type"))
                    and t.get("state") == "DEV_FIXING"
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                )
                if not exists:
                    task_queue.append(dev_task)
                    host._audit_agent_handoff(
                        product_id=pid,
                        from_agent=agent_type,
                        from_state=prev_state,
                        next_task=dev_task,
                        task_id=task_id,
                        reason="security_gate",
                        blocked=True,
                        output_data=output.data if isinstance(output.data, dict) else None,
                    )
                    logger.warning(
                        "Security gate failed for %s (repair %s/%s); "
                        "BUG_FOUND → developer DEV_FIXING",
                        pid,
                        sec_round,
                        max_security_loops,
                    )
            elif security_gate_failed and security_budget_exhausted:
                logger.warning(
                    "Security gate failed for %s — repair budgets exhausted; awaiting human review",
                    pid,
                )
            elif live_gate_failed and live_mesh_payment_parked:
                logger.warning(
                    "Live Vercel payment-ops for %s parked at HUMAN_REVIEW — skipping developer enqueue",
                    pid,
                )
            elif live_gate_failed and not quality_gates_exhausted:
                from web.backend.services.live_deployment_gate import live_gate_dev_fixing_task

                dev_task = live_gate_dev_fixing_task(pid, products[pid] if pid in products else product, live_gate_payload)
                dev_task["priority"] = host._get_priority("developer")
                exists = any(
                    t.get("product_id") == pid
                    and is_developer_agent(t.get("agent_type"))
                    and t.get("state") == "DEV_FIXING"
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                )
                if not exists:
                    task_queue.append(dev_task)
                    host._audit_agent_handoff(
                        product_id=pid,
                        from_agent=agent_type,
                        from_state=prev_state,
                        next_task=dev_task,
                        task_id=task_id,
                        reason="live_deployment_gate",
                        blocked=True,
                        output_data=output.data if isinstance(output.data, dict) else None,
                    )
                    logger.warning(
                        "Live Vercel UI gate failed for %s; "
                        "BUG_FOUND → developer DEV_FIXING (full UI of the deployed site)",
                        pid,
                    )
            elif live_gate_failed and quality_gates_exhausted:
                logger.warning(
                    "Live Vercel gate failed for %s — repair budgets exhausted; awaiting human review",
                    pid,
                )
            elif (
                agent_type == "devops"
                and pid in products
                and str(products[pid].get("state") or "") == "HUMAN_REVIEW_PENDING"
            ):
                from web.backend.services.product_followup import post_devops_human_review_approved

                if post_devops_human_review_approved(pid):
                    next_task = host._create_next_task(products[pid])
                    if next_task and next_task.get("agent_type") == "sales":
                        exists = any(
                            t.get("product_id") == pid
                            and t.get("agent_type") == "sales"
                            and t.get("status") in ("pending", "running")
                            for t in task_queue
                        )
                        if not exists:
                            task_queue.append(next_task)
                            logger.info(
                                "Product %s human gate already approved — queued sales (%s)",
                                pid,
                                next_task.get("id"),
                            )
                else:
                    logger.info(
                        "Product %s paused at post-DevOps human gate — awaiting admin approve before sales",
                        pid,
                    )
            else:
                # Create next sequential task
                next_task = host._create_next_task(product)
                if next_task:
                    if next_task.get("agent_type") == "pm":
                        next_task.setdefault("input_data", {})["clarification_pack"] = await build_clarification_pack_llm(
                            product.get("idea", ""),
                            host._llm_router,
                        )
                    exists = any(
                        t.get("product_id") == pid
                        and t.get("agent_type") == next_task["agent_type"]
                        and t.get("state") == next_task["state"]
                        and t.get("status") in ("pending", "running")
                        for t in task_queue
                    )
                    if not exists:
                        task_queue.append(next_task)
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state=prev_state,
                            next_task=next_task,
                            task_id=task_id,
                            reason="sequential",
                            output_data=output.data if isinstance(output.data, dict) else None,
                        )
                        logger.info(f"Next task created for {pid}: {next_task['agent_type']} -> {next_task['state']}")
        else:
            task["status"] = "failed"
            task["error"] = output.error or "Agent returned failure"
            category, playbook = host.quality_manager.classify_failure(task["error"])
            task["failure_category"] = category
            task["auto_remediation_playbook"] = playbook
            task["completed_at"] = time.time()
            task.setdefault("retry_count", 0)
            from core.pipeline_retry_limits import task_max_retries

            task.setdefault("max_retries", task_max_retries())
            logger.warning(
                f"Agent '{agent_type}' failed task {task_id}: {output.error} "
                f"(retry {task['retry_count']}/{task['max_retries']})"
            )
            host.quality_manager.auto_requeue_pm_spec_gate(task, products, task_queue)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error calling agent '{agent_type}' for task {task_id}: {error_msg}")

        # === RETRY LOGIC for LLM JSON parse failures ===
        is_json_error = any(kw in error_msg for kw in [
            "invalid/non-JSON", "Invalid JSON", "JSON parse error",
            "non-JSON response"
        ])

        if is_json_error:
            json_retries = int(task.get("json_parse_retry_count") or 0)
            from core.pipeline_retry_limits import json_parse_max_retries

            max_json_retries = json_parse_max_retries()

            if json_retries < max_json_retries:
                logger.warning(
                    "JSON parse retry %d/%d for %s task %s: %s",
                    json_retries + 1,
                    max_json_retries,
                    agent_type,
                    task_id,
                    error_msg,
                )
                task["json_parse_retry_count"] = json_retries + 1
                task["status"] = "pending"
                task["error"] = None
                task["started_at"] = None
                task["completed_at"] = None
                await asyncio.sleep(min(2 ** json_retries, 8))
                return

        # Permanent failure (exhausted retries or non-retryable error)
        task["status"] = "failed"
        task["error"] = error_msg
        category, playbook = host.quality_manager.classify_failure(error_msg)
        task["failure_category"] = category
        task["auto_remediation_playbook"] = playbook
        task["completed_at"] = time.time()
        task.setdefault("retry_count", 0)
        from core.pipeline_retry_limits import task_max_retries

        task.setdefault("max_retries", task_max_retries())
        host.quality_manager.auto_requeue_pm_spec_gate(task, products, task_queue)
