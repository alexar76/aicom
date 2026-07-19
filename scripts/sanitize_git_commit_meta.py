#!/usr/bin/env python3
"""Strip non-human commit trailers before satellite mirror pushes.

Human ``Co-Authored-By`` credit is KEPT — only self-inserting tooling co-authors
(Claude/Cursor/Copilot/CI bots) are removed — so real contributors appear in the
public mirror's GitHub contributor graph.
"""

from __future__ import annotations

import argparse
import re
import sys

# Tooling / AI / CI identities that insert themselves unasked and must never
# appear on public mirror history. Human contributors are NOT in this list.
_BLOCKED = re.compile(
    r"(github-actions|github-actions\[bot\]|cursor|claude|anthropic|openai|composer|"
    r"copilot|dependabot|noreply@anthropic\.com|"
    r"\[bot\]@users\.noreply\.github\.com|dependabot\[bot\]@users\.noreply\.github\.com)",
    re.IGNORECASE,
)

_CO_AUTHOR = re.compile(r"^Co-Authored-By:\s*.+$", re.IGNORECASE | re.MULTILINE)
_SIGNED_OFF = re.compile(r"^Signed-off-by:\s*.+$", re.IGNORECASE | re.MULTILINE)
_CREATED_BY = re.compile(r"^Created-by:\s*.+$", re.IGNORECASE | re.MULTILINE)
_REVIEWED_BY = re.compile(r"^Reviewed-by:\s*.+$", re.IGNORECASE | re.MULTILINE)
_ASSISTED_BY = re.compile(r"^Assisted-by:\s*.+$", re.IGNORECASE | re.MULTILINE)
# Note: Co-Authored-By is deliberately NOT in this blanket-strip list — it is
# handled separately so human co-authors survive (see sanitize_message).
_TRAILER_PREFIX = re.compile(
    r"^(Signed-off-by|Created-by|Reviewed-by|Assisted-by|"
    r"Generated-by|Tool-Used|AI-Model|Cursor-IDE):\s*.+$",
    re.IGNORECASE | re.MULTILINE,
)


def sanitize_message(text: str) -> str:
    """Strip tooling trailers, but KEEP human Co-Authored-By credit.

    A ``Co-Authored-By`` line is dropped ONLY when the co-author is blocked
    tooling (Claude/Cursor/Copilot/CI bots — see ``_BLOCKED``). Real human
    contributors are preserved so they appear in the mirror's contributor graph.
    """
    lines: list[str] = []
    for line in text.splitlines():
        if _CO_AUTHOR.match(line):
            # Keep human co-authors; strip only self-inserting AI/CI tooling.
            if _BLOCKED.search(line):
                continue
            lines.append(line)
            continue
        if _TRAILER_PREFIX.match(line) or _SIGNED_OFF.match(line):
            continue
        if _CREATED_BY.match(line) or _REVIEWED_BY.match(line) or _ASSISTED_BY.match(line):
            continue
        if _BLOCKED.search(line):
            continue
        lines.append(line)
    out = "\n".join(lines).strip()
    return out + ("\n" if text.endswith("\n") else "")


def validate_author(name: str, email: str) -> None:
    blob = f"{name} <{email}>"
    if _BLOCKED.search(blob):
        raise SystemExit(f"blocked git author identity: {blob}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", help="Commit message on stdin if omitted")
    parser.add_argument("--check-author", nargs=2, metavar=("NAME", "EMAIL"))
    args = parser.parse_args(argv)

    if args.check_author:
        validate_author(args.check_author[0], args.check_author[1])
        return 0

    raw = args.message if args.message is not None else sys.stdin.read()
    sys.stdout.write(sanitize_message(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
