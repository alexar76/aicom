#!/usr/bin/env python3
"""Thin entry point: the rules live in MOMUS (momus/momus/codescan/vulnetix_classes.py), so the push gate and
MOMUS's `code` target run the same code. Loaded by file path: no MOMUS install or package import needed.

Usage and exit codes: see that module (``--ref REF``, ``--base BASE``, ``--json``)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "momus" / "momus" / "codescan" / "vulnetix_classes.py"
_spec = importlib.util.spec_from_file_location("vulnetix_classes", _PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["vulnetix_classes"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

# Re-export for callers and tests that import this script as a module.
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

if __name__ == "__main__":
    sys.exit(_mod.main())
