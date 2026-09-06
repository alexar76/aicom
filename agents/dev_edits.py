"""Let a repair round say *what to change* instead of retyping the file.

The developer's output contract had one verb: here is a file, here are its full contents. So every
repair regenerated whole files, and a regenerated file is retyped from the model's memory of it —
which is where invented names come from. Straight from a rejected round's log:

    added: missing_attribute: settings.ATLAS_BASE_URL; missing_symbol: app.services.cache.CacheService

``atlas_base_url`` was declared three lines away in a file the round had no reason to touch;
``CacheService`` was the class in the module being imported from. Neither was the defect the round was
sent to fix — both were introduced *by the retyping*, and the round was then rejected for them. Ten
named defects, each with a file and a symbol, kept costing a round apiece and often losing ground.

An edit cannot do that. ``{"path", "find", "replace"}`` touches the bytes it names and nothing else:
no other line of the file is at risk, the output is three lines instead of four hundred, and a round
that fixes ten renames is one call.

Exact strings rather than a unified diff, deliberately. Line numbers in a generated patch are wrong
about as often as they are right — the model is counting lines it cannot see — while an exact string
either matches or does not, and "does not" is a fact we can report back instead of a corrupted file.
Uniqueness is required for the same reason: a ``find`` that appears twice is an instruction with two
meanings, and guessing which one was meant is how a fix lands in the wrong place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _resolve(code_root: Path, rel: str):
    from agents.dev import _resolve_safe_code_path

    return _resolve_safe_code_path(code_root, rel)


def _occurrence_map(text: str, needle: str, limit: int = 4) -> str:
    """``line 12: "    return advisory"; line 40: …`` — where the ambiguous matches actually are."""
    lines = text.splitlines()
    hits: list[str] = []
    for number, line in enumerate(lines, start=1):
        if needle.splitlines()[0] in line if needle else False:
            stripped = line.strip()
            hits.append(f'line {number}: "{stripped[:70]}"')
            if len(hits) >= limit:
                break
    return "; ".join(hits) or "several places"


def _nearest_text(text: str, needle: str, span: int = 6) -> str:
    """The window of real lines that most resembles ``needle``, quoted with line numbers."""
    import difflib

    lines = text.splitlines()
    wanted = [l for l in needle.splitlines() if l.strip()]
    if not lines or not wanted:
        return ""
    width = min(max(len(wanted), 1), span)
    best_at, best_ratio = 0, 0.0
    for start in range(0, max(1, len(lines) - width + 1)):
        window = "\n".join(lines[start : start + width])
        ratio = difflib.SequenceMatcher(None, window, "\n".join(wanted)).ratio()
        if ratio > best_ratio:
            best_at, best_ratio = start, ratio
    if best_ratio < 0.35:
        return ""
    return "\n".join(
        f"{n}: {lines[n - 1]}" for n in range(best_at + 1, min(best_at + width, len(lines)) + 1)
    )


def apply_edits(
    code_root: Path,
    edits: Any,
    *,
    log,
    product_id: str,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Apply ``[{path, find, replace, replace_all?}]``.

    Returns ``(previous_content, changed_paths, problems)``. ``previous_content`` is the pre-edit text
    of every file touched, so the round's existing rollback works on edits exactly as it does on
    rewritten files. ``problems`` is what to tell the model on a retry: an edit that did not apply is
    a fact worth reporting, never a silent no-op.
    """
    previous: dict[str, str] = {}
    changed: list[str] = []
    problems: list[str] = []
    if not isinstance(edits, list):
        return previous, changed, problems

    for raw in edits:
        if not isinstance(raw, dict):
            continue
        rel = str(raw.get("path") or "").strip()
        find = raw.get("find")
        replace = raw.get("replace")
        if not rel or not isinstance(find, str) or not isinstance(replace, str) or not find:
            problems.append(f"edit for {rel or '(no path)'} needs path, find and replace")
            continue

        target = _resolve(code_root, rel)
        if target is None:
            log("WARNING", f"Skipping unsafe edit path for {product_id}: {rel!r}")
            problems.append(f"{rel}: path refused")
            continue
        if not target.is_file():
            # The path may be spelled the way some tool printed it — tsc from inside frontend/, a
            # traceback with the backend root stripped. Resolve it against the tree before refusing:
            # two edits were lost to exactly this, on a product down to one defect.
            from core.product_paths import resolve_product_path

            fixed = resolve_product_path(code_root, rel)
            if fixed and fixed != rel:
                log("INFO", f"Edit path for {product_id} resolved: {rel} -> {fixed}")
                rel = fixed
                target = _resolve(code_root, rel)
            if target is None or not target.is_file():
                problems.append(f"{rel}: no such file — use `files` to create it")
                continue
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{rel}: unreadable ({exc})")
            continue

        occurrences = text.count(find)
        if occurrences == 0:
            # Quote the nearest real text back. "Does not appear" is a verdict; the actual lines are an
            # instruction, and the same round hit this twice on one file with two different reasons —
            # first an anchor occurring three times, then an anchor occurring nowhere. Whitespace and a
            # half-remembered line are enough to miss, and the model cannot diff its guess against a
            # file it has already been shown without being told where it went wrong.
            nearest = _nearest_text(text, find)
            problems.append(
                f"{rel}: `find` text does not appear in the file, so nothing was changed."
                + (f" The closest text in the file is:\n{nearest}" if nearest else "")
                + " Quote it exactly as it is on disk, character for character."
            )
            continue
        if occurrences > 1 and not raw.get("replace_all"):
            # Show where they are. "Be more specific" is advice; the three places are an instruction.
            # This exact message came back three rounds running for the same file — the model kept
            # choosing an anchor that occurs three times and had no way to know which lines they were
            # on, so each retry was another guess at the same ambiguity.
            problems.append(
                f"{rel}: `find` appears {occurrences} times, at {_occurrence_map(text, find)}. "
                "Extend `find` with the lines above or below one of them until it is unique, or set "
                "replace_all when every occurrence should change."
            )
            continue

        previous.setdefault(rel, text)
        patched = text.replace(find, replace) if raw.get("replace_all") else text.replace(find, replace, 1)
        if patched == text:
            problems.append(f"{rel}: edit changed nothing (find and replace are identical)")
            continue
        try:
            target.write_text(patched, encoding="utf-8")
        except OSError as exc:
            problems.append(f"{rel}: could not be written ({exc})")
            continue
        if rel not in changed:
            changed.append(rel)

    if changed:
        log(
            "INFO",
            f"Applied {len(edits)} edit(s) for {product_id} across {len(changed)} file(s) without "
            f"rewriting them: {', '.join(changed[:6])}",
        )
    if problems:
        log(
            "WARNING",
            f"{len(problems)} edit(s) for {product_id} did not apply: {'; '.join(problems[:4])}",
        )
    return previous, changed, problems


EDIT_CONTRACT_PROMPT = """
=== TARGETED EDITS (prefer these in a repair round) ===
Alongside `files`, the response may carry `edits` — changes described by the text they replace:

  "edits": [
    {"path": "backend/app/main.py", "find": "settings.ATLAS_BASE_URL", "replace": "settings.atlas_base_url"},
    {"path": "backend/app/deps.py", "find": "from .services.cache import cache_service",
     "replace": "from .services.cache import CacheService"}
  ]

Rules, and the reason for each:
- `find` must appear EXACTLY as it is on disk, and exactly once. Quote it from the file you were
  given, not from memory. If it appears more than once, include surrounding lines until it is unique,
  or set "replace_all": true when every occurrence should change.
- An edit that does not match changes nothing and is reported back to you. It is not a silent no-op.
- Use `files` only to create a new file or when a file genuinely needs rewriting end to end.

Why this is the better tool for a repair: a rewritten file is retyped from memory, and that is where
names like `settings.ATLAS_BASE_URL` come from when the field is declared `atlas_base_url` three lines
away. An edit touches the bytes it names and puts no other line at risk. It is also a few lines of
output instead of a few hundred, so a round that fixes ten renames is one call rather than ten.
""".strip()
