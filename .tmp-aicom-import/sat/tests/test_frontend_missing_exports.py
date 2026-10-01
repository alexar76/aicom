"""The TypeScript twin of find_missing_symbols, and the detector that ends the plateau.

The last defect on the live product was a cross-file refactor: the frontend API layer plus five
consumers. Every attempt died the same way, and the salvage log shows the coin flip in plain text:

    Salvaged the repair round … the rest of the round stands (0 vs 0 before)
    Frontend build: AuditTable.tsx(2,10): error TS2305: Module has no exported member …  × 5
    Round guard: reverted a repair round (3 -> 20)

The static score read ZERO across the entire frontend, so reverting the API layer alone — leaving five
importers referencing exports that no longer existed — measured as free. tsc knew better, but tsc runs
minutes later in QA, and the salvage decision had already been made. Same theorem as the Python twin at
05:00: a defect the score cannot see is a defect the machinery cannot preserve a fix for.

Precision over reach, as with every detector that feeds the score: relative imports between product
files only, `export *` makes a module unenumerable and exempt, namespace imports are not judged, and an
unresolvable path is another detector's business.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import find_frontend_missing_exports


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


CLIENT = (
    "export const getDashboards = () => fetch('/api/analytics/dashboards')\n"
    "export function login(email: string, password: string) { return fetch('/login') }\n"
    "export type SpendData = { total: number }\n"
)


def test_the_live_ts2305_shape_is_found_with_the_fix_named(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/api/client.ts": CLIENT,
            "frontend/src/pages/AnalyticsDashboard.tsx": (
                "import { listDashboards } from '../api/client'\n"
            ),
        },
    )
    found = find_frontend_missing_exports(code)
    assert len(found) == 1, found
    f = found[0]
    assert f["name"] == "listDashboards"
    assert f["file"] == "frontend/src/api/client.ts"
    assert f["importer"] == "frontend/src/pages/AnalyticsDashboard.tsx"
    assert f["did_you_mean"] == ["getDashboards"]
    assert "fix the IMPORT" in f["detail"], (
        "without this the round renames the export and breaks every other importer — "
        "the oscillation that burned three rounds"
    )


def test_a_correct_import_is_silent(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/api/client.ts": CLIENT,
            "frontend/src/App.tsx": (
                "import { getDashboards, login } from './api/client'\n"
                "import type { SpendData } from './api/client'\n"
            ),
        },
    )
    assert find_frontend_missing_exports(code) == []


def test_aliased_imports_and_reexports_resolve(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/api/auth.ts": "export { login as signIn } from './client'\n",
            "frontend/src/api/client.ts": CLIENT,
            "frontend/src/App.tsx": "import { signIn as enter } from './api/auth'\n",
        },
    )
    assert find_frontend_missing_exports(code) == []


def test_export_star_makes_a_module_unenumerable(tmp_path):
    """A false positive here feeds a score that discards work."""
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/api/index.ts": "export * from './client'\n",
            "frontend/src/api/client.ts": CLIENT,
            "frontend/src/App.tsx": "import { anything } from './api'\n",
        },
    )
    assert find_frontend_missing_exports(code) == []


def test_third_party_and_unresolvable_imports_are_not_judged(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/App.tsx": (
                "import { useState } from 'react'\n"
                "import { thing } from '@/lib/utils'\n"
                "import { gone } from './missing/file'\n"
            ),
        },
    )
    assert find_frontend_missing_exports(code) == []


def test_a_missing_default_export_is_reported_only_for_a_bare_module(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/empty.ts": "// nothing here yet\n",
            "frontend/src/App.tsx": "import Widget from './empty'\n",
        },
    )
    found = find_frontend_missing_exports(code)
    assert [f["name"] for f in found] == ["default"]


def test_namespace_imports_are_not_judged(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/api/client.ts": CLIENT,
            "frontend/src/App.tsx": "import * as api from './api/client'\n",
        },
    )
    assert find_frontend_missing_exports(code) == []


def test_index_resolution_works(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "frontend/src/api/index.ts": "export const ping = () => 1\n",
            "frontend/src/App.tsx": "import { pong } from './api'\n",
        },
    )
    assert [f["name"] for f in find_frontend_missing_exports(code)] == ["pong"]


def test_it_is_wired_where_the_plateau_lived():
    """Score, breakdown, identities, gate, blocking list, revert re-measure — all six.

    A detector visible to only some of them recreates the exact deadlock it exists to end: the gate
    would report what the salvage pass cannot see.
    """
    root = Path(__file__).resolve().parents[1]

    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "ts_exports = find_frontend_missing_exports(code_dir)" in check
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not ts_exports" in passed_expr

    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "5 * len(find_frontend_missing_exports(code_root, limit=200))" in score
    breakdown = dev[dev.index("def _tree_defect_breakdown(") : dev.index("def _breakdown_delta(")]
    assert '"frontend_missing_export"' in breakdown
    ids = dev[dev.index("def _tree_defect_identities(") : dev.index("def _identities_appeared(")]
    assert '"frontend_missing_export"' in ids

    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"frontend_missing_export"' in qa[: qa.index("# Deletions next")]

    executor = (root / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    assert '(find_frontend_missing_exports, "frontend_missing_export")' in executor
