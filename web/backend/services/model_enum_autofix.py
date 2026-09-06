"""Restore SQLAlchemy model enums that repair rounds collapsed into model aliases.

Measured on Relay: Dev rewrote ``models/__init__.py`` to

    WorkspaceTier = Workspace
    HandoffStatus = Handoff
    …

so ``WorkspaceTier.solo`` raised ``AttributeError`` at seed and every boot gate
failed forever. The column still declares the enum values in ``SAEnum(..., name=)``;
this autofix rebuilds real ``str, enum.Enum`` classes from those named enums.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# SAEnum name= → Python enum class the product imports.
_SAENUM_NAME_TO_CLASS = {
    "workspace_tier": "WorkspaceTier",
    "handoff_status": "HandoffStatus",
    "verification_source": "VerificationSource",
    "operator_role": "OperatorRole",
    "verification_category": "VerificationCategory",
}

_ALIAS_RE = re.compile(
    r"^(?P<name>(?:WorkspaceTier|HandoffStatus|OperatorRole|VerificationSource|"
    r"VerificationCategory|\w+(?:Tier|Status|Role|Source|Kind|Type|Category)))"
    r"\s*=\s*(?P<model>[A-Z]\w+)\s*$",
    re.M,
)

_CLASS_ENUM_RE = re.compile(
    r"^class (?P<name>WorkspaceTier|HandoffStatus|OperatorRole|VerificationSource|"
    r"VerificationCategory)\(str,\s*enum\.Enum\):(?P<body>.*?)(?=^class |\Z)",
    re.M | re.S,
)

_SAENUM_FULL_RE = re.compile(
    r"""SAEnum\s*\(\s*(?P<args>.*?)\s*\)""",
    re.M | re.S,
)


def apply_model_enum_autofix(code_root: Path) -> list[str]:
    """Rewrite broken enum aliases / wrong enum bodies under ``**/models/__init__.py``."""
    if not code_root.is_dir():
        return []
    actions: list[str] = []
    for init in code_root.rglob("models/__init__.py"):
        if ".aicom_sandbox" in init.parts or "node_modules" in init.parts:
            continue
        try:
            text = init.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        updated = _fix_init(init.parent, text)
        if updated != text:
            try:
                init.write_text(updated, encoding="utf-8")
                actions.append(str(init.relative_to(code_root)))
            except OSError as exc:
                logger.debug("model enum autofix write failed %s: %s", init, exc)
    if actions:
        logger.info("model_enum_autofix applied to %s (%s)", code_root.name, actions)
    return actions


def _enum_block(name: str, values: tuple[str, ...]) -> str:
    members = "\n".join(f'    {v} = "{v}"' for v in values)
    return f"class {name}(str, enum.Enum):\n{members}\n"


def _fix_init(models_dir: Path, text: str) -> str:
    saenums = _collect_named_saenums(models_dir)
    if not saenums and not _ALIAS_RE.search(text):
        return text

    imported = set(re.findall(r"^from \.[\w.]+ import (.+)$", text, re.M))
    imported_names: set[str] = set()
    for chunk in imported:
        for part in chunk.split(","):
            name = part.strip().split(" as ")[-1].strip()
            if name:
                imported_names.add(name)

    out = text

    # 1) Replace ``Name = Model`` aliases.
    for m in reversed(list(_ALIAS_RE.finditer(out))):
        name = m.group("name")
        model = m.group("model")
        if model not in imported_names:
            continue
        values = saenums.get(name)
        if not values:
            continue
        out = out[: m.start()] + _enum_block(name, values) + out[m.end() :]

    # 2) Replace existing Enum classes whose members don't match SAEnum.
    for m in reversed(list(_CLASS_ENUM_RE.finditer(out))):
        name = m.group("name")
        values = saenums.get(name)
        if not values:
            continue
        existing = tuple(re.findall(r'^\s+(\w+)\s*=\s*[\'"]([^\'"]+)[\'"]', m.group("body"), re.M))
        existing_vals = tuple(v for _, v in existing)
        if existing_vals == values:
            continue
        out = out[: m.start()] + _enum_block(name, values) + out[m.end() :]

    if "import enum" not in out and "(str, enum.Enum)" in out:
        out = "import enum\n" + out
    return out


def _collect_named_saenums(models_dir: Path) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for py in models_dir.glob("*.py"):
        if py.name == "__init__.py":
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _SAENUM_FULL_RE.finditer(src):
            args = m.group("args")
            vals = tuple(re.findall(r"['\"]([^'\"]+)['\"]", args))
            # Drop the name= value from members if it was captured as a string —
            # actually name= uses a kwarg string too. Parse carefully:
            # SAEnum("a", "b", name="handoff_status")
            name_m = re.search(r'name\s*=\s*[\'"](\w+)[\'"]', args)
            if not name_m:
                continue
            enum_name = name_m.group(1)
            # Values are only the positional string literals before name=.
            before_name = args[: name_m.start()]
            vals = tuple(re.findall(r"['\"]([^'\"]+)['\"]", before_name))
            if not vals:
                continue
            cls = _SAENUM_NAME_TO_CLASS.get(enum_name)
            if cls:
                found[cls] = vals
            found[enum_name] = vals
    return found
