"""Source text of a module whose code was split into a package of parts.

Several tests read an agent's source and assert what it contains ("the developer's
coherence check counts X"). When a module's helpers move into a package beside it, that
contract covers the module and its parts together; ``read_split`` returns both.
"""

from __future__ import annotations

from pathlib import Path

# module path (as it ends) -> the package its parts moved into, beside the module
SPLIT_PARTS = {
    "agents/dev.py": "dev_tree",
    "web/backend/api/sandbox.py": "sandbox_parts",
}


def read_split(path: Path) -> str:
    """The module's own text, then each part's text in name order."""
    text = path.read_text(encoding="utf-8")
    posix = path.as_posix()
    parts = next((pkg for suffix, pkg in SPLIT_PARTS.items() if posix.endswith("/" + suffix)), None)
    if parts:
        for part in sorted((path.parent / parts).glob("*.py")):
            text += "\n" + part.read_text(encoding="utf-8")
    return text
