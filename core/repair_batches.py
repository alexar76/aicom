"""Cut a repair round into short bursts instead of one long spray.

The developer agent is *asked* to return only what it changed. The prompt says so with the
measurement attached — "~80 files emitted to fix five findings, the overwhelming majority
byte-identical to what was already on disk" — and ``patch_mode`` adds "prefer minimal targeted
edits instead of full rewrites". Both are requests, and both are ignored: a round whose work
list named three files wrote about eighty-five, came back at 128 severity-weighted against a
baseline of 41, and was thrown away. Seven consecutive rounds went that way with the baseline
never moving.

Asking harder cannot fix this; the prose has already been sharpened once with numbers in it.
What changes the outcome is a **budget the instruction cannot outrun**: split the work by file,
give each batch its own call, and size the output allowance for a handful of files. A batch
physically cannot return eighty-five files.

Three consequences worth having beyond the obvious one:

* each call is small, so the model's attention is on a few files rather than a tree, and a
  128k-token generation stops being a 20-minute round;
* a batch that breaks something is caught by the existing cheap static check straight after it,
  so the damage is one batch wide instead of a whole round wide;
* the batches are ordered, so the defects that stop the product working — no boot, dead route,
  dead mesh call — are attempted first and land even if later batches fail.

Deliberately NOT applied to an initial build. A first generation legitimately needs the whole
tree in one coherent pass; batching that would produce files that never saw each other.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Files per batch. Three is small enough that the output allowance below is generous for it and
# still allows a real edit in each, and large enough that a defect spanning a module and its
# schema stays in one call — splitting those apart is how a "fix" lands half-applied.
DEFAULT_BATCH_FILES = 3

# Output allowance per batch. A repair edit to three files is a few thousand tokens; 24k leaves
# room for a genuinely large module without leaving room for a tree. This is the actual
# mechanism — the number the instruction cannot argue with.
# Fallback only. The real number comes from the model actually in use — see active_model_limits() —
# because a hard-coded ceiling is either smaller than the model (which truncates answers mid-function,
# as 24k did: a batch rewriting three files returned the third cut off, and the round was reverted for
# the SyntaxError that created) or larger than it (which fails the request outright).
DEFAULT_BATCH_MAX_TOKENS = 64_000


def active_model_limits() -> dict[str, int]:
    """``{max_tokens, context_window}`` for the provider the factory is actually routing to.

    Read from data/config/model_providers.yaml rather than assumed: the deployed provider advertises
    max_tokens 128000 and a 1M context window, and every fixed constant in this file was smaller than
    that for no reason other than nobody having looked.
    """
    out = {"max_tokens": 0, "context_window": 0}
    try:
        import yaml  # type: ignore

        from core.paths import resolve_data_root

        cfg_path = Path(resolve_data_root()) / "config" / "model_providers.yaml"
        if not cfg_path.is_file():
            cfg_path = Path(__file__).resolve().parents[1] / "data" / "config" / "model_providers.yaml"
        payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        # Loud, because a silent zero here means every limit quietly falls back to a constant — which
        # is exactly what happened while this function was missing its Path import.
        import logging

        logging.getLogger(__name__).warning(
            "Could not read model limits from provider config (%s); falling back to constants", exc
        )
        return out

    providers = payload.get("providers") or {}
    name = str(payload.get("default_provider") or "")
    block = providers.get(name) or {}
    if not block:
        # No default named: take the enabled provider with the highest priority, the same way the
        # router does, so this never disagrees with what actually serves the call.
        enabled = [
            (int(b.get("priority") or 0), b)
            for b in providers.values()
            if isinstance(b, dict) and b.get("enabled")
        ]
        block = max(enabled, key=lambda pair: pair[0])[1] if enabled else {}
    caps = (block or {}).get("capabilities") or {}
    for key in ("max_tokens", "context_window"):
        try:
            out[key] = int(caps.get(key) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    return out

# Defect codes where the product does not run at all. These lead, because nothing later matters
# while the app cannot boot, and because they land in one or two files each.
_BLOCKING_FIRST = (
    "duplicate_tablename",
    "route_handler_broken_injection",
    "mesh_contract_violation",
    "missing_symbol",
    "orphan_module_breaks_build",
    # Compile-fatal: tsc failed, there is no bundle, browser E2E sees only the landing page.
    # Measured on Sentinel round 50: this sat at the same "high" as visual_app_missing_skeleton
    # and the round edited operator Dashboard.tsx while PublicWidget.tsx still did not typecheck.
    "frontend_build_failed",
    # Runtime 401 after a successful login. The journey sends Bearer and holds no cookies; ranking
    # this with cosmetics is how six rounds flip-flopped two routers and never touched deps.py.
    "demo_journey_auth_rejected",
    "unexpected_keyword_argument",
    "live_exception_in_ui",
    "demo_journey_exception_in_200",
    "invalid_requirement",
    "vercel_build_failed",
)

# Files an UNSCOPED batch may land. Findings that name no file get one batch with no path
# restriction, and measured on the first live batched rounds that batch returned 19 and 21 files
# while its scoped siblings returned 3 and 1 — the sprawling round in miniature, and about
# three quarters of the round's whole output. The token allowance alone does not bind it: 21
# small files fit in 24k comfortably. So the count is capped and the surplus is dropped, which
# is the same shape as the rest of this module: a limit the instruction cannot outrun.
UNSCOPED_BATCH_MAX_FILES = 5


def unscoped_batch_max_files() -> int:
    try:
        return max(
            1, int(os.environ.get("AIFACTORY_REPAIR_UNSCOPED_MAX_FILES", UNSCOPED_BATCH_MAX_FILES))
        )
    except ValueError:
        return UNSCOPED_BATCH_MAX_FILES


# html/css belong here: a visual/E2E finding filed against index.html used to name no
# batch file (this regex stopped at scripts), the round scoped to operator TSX, and every
# landing edit was reverted. Measured on Sentinel round 56 — 71 reverts, demo_quality F.
_FILE_RE = re.compile(
    r"\b([\w./-]+\.(?:py|tsx?|jsx?|mjs|html|css)|[\w./-]*requirements(?:-[\w]+)?\.txt)\b"
)


def batching_enabled() -> bool:
    """On by default; ``AIFACTORY_REPAIR_BATCHING=0`` restores the single-call round."""
    return os.environ.get("AIFACTORY_REPAIR_BATCHING", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def batch_size() -> int:
    try:
        return max(1, int(os.environ.get("AIFACTORY_REPAIR_BATCH_FILES", DEFAULT_BATCH_FILES)))
    except ValueError:
        return DEFAULT_BATCH_FILES


def batch_max_tokens() -> int:
    """Everything the model will give us, unless an operator says otherwise.

    Batching exists to keep a round FOCUSED — few files, named findings — not to ration output. Those
    were conflated, and the ration is what broke: 24k against a batch of three whole files produced a
    file that stopped mid-def, and the round was reverted for the SyntaxError. An unused allowance
    costs nothing; a truncated answer costs a round.
    """
    raw = os.environ.get("AIFACTORY_REPAIR_BATCH_TOKENS", "").strip()
    if raw:
        try:
            return max(4_000, int(raw))
        except ValueError:
            pass
    model_max = active_model_limits().get("max_tokens") or 0
    return max(DEFAULT_BATCH_MAX_TOKENS, model_max)


def _files_in(text: str) -> list[str]:
    """Paths a finding mentions, in the order they appear."""
    out: list[str] = []
    for match in _FILE_RE.finditer(text or ""):
        rel = match.group(1).lstrip("./")
        if rel not in out:
            out.append(rel)
    return out


def _rank(finding: dict[str, Any]) -> int:
    """Lower sorts first: the product not running outranks everything else."""
    blob = " ".join(
        str(finding.get(k) or "") for k in ("code", "title", "detail", "description")
    ).lower()
    for i, code in enumerate(_BLOCKING_FIRST):
        if code in blob:
            return i
    severity = str(finding.get("severity") or "").lower()
    return len(_BLOCKING_FIRST) + {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 2)


def plan_batches(
    findings: list[dict[str, Any]],
    *,
    scope: list[str] | None = None,
    size: int | None = None,
) -> list[dict[str, Any]]:
    """Group findings into ``[{files, findings}]``, blocking defects first.

    Findings that name no file are collected into a final batch with no file restriction —
    something has to carry them, and putting them first would let a vague finding pull a round
    back into rewriting the tree.
    """
    per_batch = size or batch_size()
    allowed = {s.strip("/") for s in (scope or []) if s and "." in s}
    # Directory scopes bind as prefixes. They used to be dropped here entirely — only file entries
    # survived — so a round scoped to ["frontend/"] happily built batches out of BACKEND findings,
    # edited three backend files, and had every one reverted as out-of-scope: a whole round of work
    # thrown away by construction, measured live at 12:42.
    allowed_dirs = tuple(
        s.strip("/") + "/" for s in (scope or []) if s and "." not in s and s.strip("/")
    )

    by_file: dict[str, list[dict[str, Any]]] = {}
    fileless: list[dict[str, Any]] = []
    for finding in sorted(findings or [], key=_rank):
        text = " ".join(
            str(finding.get(k) or "")
            for k in ("file", "title", "detail", "description", "code")
        )
        named = _files_in(text)
        files = [
            f
            for f in named
            if (not allowed and not allowed_dirs)
            or f in allowed
            or (allowed_dirs and f.startswith(allowed_dirs))
        ]
        if not files:
            # A finding whose files were ALL filtered out is out of scope, full stop. Dropping it to
            # the fileless batch instead handed it back with no path restriction, and the very next
            # round spent that batch editing backend files under a frontend/ scope — every one
            # reverted. Genuinely file-less findings still ride along; out-of-scope ones wait for a
            # round whose scope includes them.
            if named and (allowed or allowed_dirs):
                continue
            fileless.append(finding)
            continue
        by_file.setdefault(files[0], []).append(finding)

    batches: list[dict[str, Any]] = []
    pending_files: list[str] = []
    pending_findings: list[dict[str, Any]] = []
    for path, group in by_file.items():
        pending_files.append(path)
        pending_findings.extend(group)
        if len(pending_files) >= per_batch:
            batches.append({"files": pending_files, "findings": pending_findings})
            pending_files, pending_findings = [], []
    if pending_files:
        batches.append({"files": pending_files, "findings": pending_findings})

    if fileless:
        batches.append({"files": [], "findings": fileless})
    return batches


# Per-file cap for the contents attached to a batch. Repair scopes are a handful of files, and a
# backend module is rarely above this; a frontend page occasionally is, and a truncated tail is still
# far better than no file at all — the model can anchor an append on what it can see.
# Fallback; attach_file_chars() scales this with the model's context window. 20k truncated real
# product files mid-class, and a round that cannot see the end of a file writes edits that miss.
MAX_ATTACHED_FILE_CHARS = 20_000


def attach_file_chars() -> int:
    """How much of a file to show the model, derived from its context window.

    Roughly four characters per token, a fifth of the window for attachments, and never less than the
    old constant. On the deployed provider (1M-token window) that is a 200k-character allowance, so
    every real product file arrives whole.
    """
    raw = os.environ.get("AIFACTORY_ATTACH_FILE_CHARS", "").strip()
    if raw:
        try:
            return max(4_000, int(raw))
        except ValueError:
            pass
    window = active_model_limits().get("context_window") or 0
    if window <= 0:
        return MAX_ATTACHED_FILE_CHARS
    return max(MAX_ATTACHED_FILE_CHARS, min(200_000, int(window * 4 * 0.2)))


def attach_file_contents(batch: dict[str, Any], code_dir: Any) -> dict[str, str]:
    """Read the batch's own files off disk, so the round can quote them instead of remembering them."""
    from pathlib import Path as _Path

    from core.product_paths import resolve_product_path

    out: dict[str, str] = {}
    root = _Path(code_dir)
    wanted = list(batch.get("files") or [])
    if not wanted:
        # The unscoped batch has no file list by construction, so it was the one batch still quoting
        # from memory — and it is where the misses concentrated: deps.py, advisory.ts, Dashboard.tsx,
        # all "find text does not appear in the file". Its findings still name paths, so read those.
        for finding in batch.get("findings") or []:
            text = " ".join(
                str(finding.get(k) or "")
                for k in ("file", "title", "detail", "description", "code")
            )
            for rel in _files_in(text):
                if rel not in wanted:
                    wanted.append(rel)
    for raw in wanted[:8]:
        # Resolve first: a finding may name the path the way its tool prints it, and a file that fails
        # to attach is a round working from memory.
        rel = resolve_product_path(root, str(raw)) or str(raw)
        path = root / rel
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _cap = attach_file_chars()
        if len(text) > _cap:
            text = text[:_cap] + "\n… (truncated — anchor your edit above this line)"
        out[str(rel)] = text

    # One hop of direct imports, as reference. A round with only PublicWidget.tsx attached tried to
    # fix `TS2345: Argument of type 'AdvisoryRes…'` twice and missed twice — the error just moved
    # (49 → 54) — because the type it had to match is declared in a file it could not see. Fixing a
    # type mismatch against an invisible interface is guessing with extra steps.
    _imp = re.compile(r"from\s*[\"'](\.[^\"']+)[\"']")
    extras: dict[str, str] = {}
    for rel, text in list(out.items()):
        if not rel.endswith((".ts", ".tsx")):
            continue
        base = (root / rel).parent
        for spec in _imp.findall(text):
            target = (base / spec).resolve()
            for cand in (
                [target.with_suffix(sfx) for sfx in (".ts", ".tsx")]
                + [target / "index.ts", target / "index.tsx", target]
            ):
                if not cand.is_file():
                    continue
                try:
                    rel2 = cand.relative_to(root.resolve()).as_posix()
                except ValueError:
                    break
                if rel2 not in out and rel2 not in extras and len(extras) < 4:
                    try:
                        body = cand.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        break
                    if len(body) > MAX_ATTACHED_FILE_CHARS:
                        body = body[:MAX_ATTACHED_FILE_CHARS] + "\n… (truncated)"
                    extras[rel2] = (
                        "// (reference: imported by "
                        + rel
                        + " — the types you must match are declared here)\n"
                        + body
                    )
                break
    out.update(extras)
    return out


def findings_listing_budget() -> int:
    """Characters the findings listing may spend in one batch prompt (env-tunable).

    Generous by design: twelve findings of a thousand characters is twelve thousand, and the model
    context is measured in hundreds of thousands. The failure mode this protects against is not a
    prompt that is too long — it is a prompt where the sentence that mattered got cut off.
    """
    import os

    raw = os.environ.get("AIFACTORY_FINDINGS_LISTING_BUDGET", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 0
    return value if value >= 2000 else 120_000


def batch_instruction(
    batch: dict[str, Any],
    index: int,
    total: int,
    file_contents: dict[str, str] | None = None,
) -> str:
    """What to tell the model about this burst, and about the rest of the round."""
    files = batch.get("files") or []
    lines = [
        f"=== REPAIR BATCH {index + 1} OF {total} ===",
        "This call fixes ONE batch of a larger round. Other batches handle the rest, so do not "
        "attempt anything outside this one — work you do here on someone else's batch is "
        "discarded, and it is how a round that had three files of work ended up rewriting "
        "eighty-five.",
    ]
    if files:
        lines.append(
            "Prefer `edits` — {\"path\", \"find\", \"replace\"} — for anything already on disk: a "
            "rewritten file is retyped from memory and that is where invented names come from. Only "
            "these files may be touched: " + ", ".join(files) + "."
        )
        lines.append(
            "To ADD something to a file that already exists — a class, a function, a field — use an "
            "edit that appends: `find` a short unique anchor near the end of the file (the last line "
            "of the last definition), `replace` it with that same anchor followed by your new code. "
            "Do NOT rewrite the file to add to it."
        )
        lines.append(
            "This is the failure that costs the most rounds. Watched live: a round rewrote "
            "schemas/analytics.py to add three classes and dropped DashboardUpdate, and rewrote "
            "rule_engine.py and dropped RuleEngine — both reverted for dropping symbols other modules "
            "import, and the round ended having written nothing at all. A rewrite has to reproduce "
            "everything already in the file from memory; an append cannot lose what it never touched."
        )
        lines.append(
            "Return a file in `files[]` with complete contents only if it is new or genuinely needs "
            "rewriting end to end."
        )
        lines.append(
            'When a finding says a file must be DELETED, return its exact path in `delete_files` — '
            'e.g. {"delete_files": ["frontend/src/components/UI/Toast.tsx"]}. Do not empty the file '
            "instead, and do not re-create it under another name."
        )
        lines.append(
            "If fixing them genuinely requires touching another file, return that file too and "
            "say why in `notes` — but a batch that returns the tree will be reverted."
        )
    else:
        lines.append(
            "These findings name no specific file. Return the smallest set of files that "
            f"addresses them, and AT MOST {unscoped_batch_max_files()} files — anything beyond "
            "that is dropped, not reviewed. Pick the ones that matter most; a batch like this "
            "returned 21 files on a real round while its siblings returned 3 and 1, and that is "
            "how a round stops being a repair."
        )
    if file_contents:
        # The single most expensive omission in this pipeline. A repair round was asked to change
        # files it had never been shown, so every `find` string was quoted from memory and missed, and
        # every rewrite reconstructed the file from memory and dropped whatever it failed to recall —
        # DashboardUpdate out of schemas/analytics.py, RuleEngine out of rule_engine.py, both reverted,
        # the round finishing with nothing written. Neither symptom is a model failing at its job;
        # both are what happens when you ask someone to edit a document they cannot see.
        lines.append("")
        lines.append("=== THESE FILES, EXACTLY AS THEY ARE ON DISK RIGHT NOW ===")
        lines.append(
            "Quote `find` from this text, character for character. Preserve everything you are not "
            "changing — anything you leave out of a rewritten file is deleted from the product."
        )
        for path, text in file_contents.items():
            lines.append(f"\n--- {path} ---\n{text}")
        lines.append("")
    lines.append("The findings for THIS batch only:")
    # No per-finding truncation. The cut is what turned a full instruction into its opposite: a
    # 716-character missing-attribute finding met a 600-character limit, the list of methods the class
    # DOES declare survived at offset 297, and the sentence forbidding deletion of the call site fell
    # off the end — leaving "…or stop reading it" as the last thing the model read. It deleted the
    # ATLAS invocation twice, hollowing the product out to satisfy the finding.
    #
    # A finding is written to be executable; half a finding is a different instruction. So each one
    # goes in whole, and the only limit is a budget on the whole listing — announced when it bites,
    # never silent, because "some findings were omitted" is information the round needs and
    # "instruction ends mid-sentence" is not.
    _findings = list(batch.get("findings") or [])
    _budget = findings_listing_budget()
    _spent = 0
    _shown = 0
    for finding in _findings[:12]:
        title = str(finding.get("title") or finding.get("code") or "").strip()
        detail = str(finding.get("detail") or finding.get("description") or "").strip()
        entry = f"- [{finding.get('severity', 'high')}] {title}: {detail}"
        if _shown and _spent + len(entry) > _budget:
            break
        lines.append(entry)
        _spent += len(entry)
        _shown += 1
    _omitted = len(_findings) - _shown
    if _omitted > 0:
        lines.append(
            f"({_omitted} further finding(s) are not listed here — the listing hit its "
            f"{_budget}-character budget. They arrive in a later round; nothing has been silently "
            "dropped from the product's diagnosis.)"
        )
    return "\n".join(lines)
