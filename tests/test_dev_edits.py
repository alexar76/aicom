"""A repair round can now say what to change instead of retyping the file.

The developer's output contract had one verb: here is a file, here are its full contents. So every
repair regenerated whole files, and a regenerated file is retyped from the model's memory of it —
which is where invented names come from. From a rejected round's log:

    added: missing_attribute: settings.ATLAS_BASE_URL; missing_symbol: app.services.cache.CacheService

`atlas_base_url` was declared three lines away in a file the round had no reason to touch, and
`CacheService` was the class in the module being imported from. Neither was the defect the round was
sent to fix; both were introduced by the retyping, and the round was thrown away for them.

Exact strings rather than a unified diff, deliberately: line numbers in a generated patch are wrong
about as often as they are right, while an exact string either matches or does not — and "does not" is
a fact we can hand back instead of a corrupted file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.dev_edits import apply_edits

QUIET = lambda *a, **k: None  # noqa: E731


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def code(tmp_path: Path) -> Path:
    return _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": (
                "from .config import settings\n\nBASE = settings.ATLAS_BASE_URL\n"
            ),
            "backend/app/deps.py": "from .services.cache import cache_service\n",
        },
    )


def test_the_two_live_defects_are_fixed_without_touching_anything_else(code):
    before_lines = (code / "backend/app/main.py").read_text(encoding="utf-8").splitlines()
    previous, changed, problems = apply_edits(
        code,
        [
            {
                "path": "backend/app/main.py",
                "find": "settings.ATLAS_BASE_URL",
                "replace": "settings.atlas_base_url",
            },
            {
                "path": "backend/app/deps.py",
                "find": "from .services.cache import cache_service",
                "replace": "from .services.cache import CacheService",
            },
        ],
        log=QUIET,
        product_id="prod-x",
    )
    assert problems == []
    assert set(changed) == {"backend/app/main.py", "backend/app/deps.py"}
    after = (code / "backend/app/main.py").read_text(encoding="utf-8")
    assert "settings.atlas_base_url" in after
    # Every other line is byte-identical — that is the whole point.
    assert after.splitlines()[0] == before_lines[0]
    assert len(after.splitlines()) == len(before_lines)


def test_previous_content_is_captured_so_the_existing_rollback_works(code):
    previous, _changed, _problems = apply_edits(
        code,
        [{"path": "backend/app/deps.py", "find": "cache_service", "replace": "CacheService"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert previous["backend/app/deps.py"] == "from .services.cache import cache_service\n"


def test_text_that_is_not_on_disk_changes_nothing_and_is_reported(code):
    """The commonest cause is quoting from memory — exactly what edits exist to prevent."""
    original = (code / "backend/app/main.py").read_text(encoding="utf-8")
    _previous, changed, problems = apply_edits(
        code,
        [{"path": "backend/app/main.py", "find": "settings.ATLAS_BASE_URI", "replace": "x"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert changed == []
    assert (code / "backend/app/main.py").read_text(encoding="utf-8") == original
    assert "does not appear in the file" in problems[0]


def test_an_ambiguous_find_is_refused(code):
    """A `find` that appears twice is an instruction with two meanings."""
    _tree(code, {"backend/app/twice.py": "x = 1\ny = 1\n"})
    _previous, changed, problems = apply_edits(
        code,
        [{"path": "backend/app/twice.py", "find": "= 1", "replace": "= 2"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert changed == []
    assert "appears 2 times" in problems[0]
    assert (code / "backend/app/twice.py").read_text(encoding="utf-8") == "x = 1\ny = 1\n"


def test_replace_all_is_available_when_it_is_meant(code):
    _tree(code, {"backend/app/twice.py": "x = 1\ny = 1\n"})
    _previous, changed, problems = apply_edits(
        code,
        [
            {
                "path": "backend/app/twice.py",
                "find": "= 1",
                "replace": "= 2",
                "replace_all": True,
            }
        ],
        log=QUIET,
        product_id="prod-x",
    )
    assert problems == [] and changed == ["backend/app/twice.py"]
    assert (code / "backend/app/twice.py").read_text(encoding="utf-8") == "x = 2\ny = 2\n"


def test_a_missing_file_says_to_use_files_instead(code):
    _previous, changed, problems = apply_edits(
        code,
        [{"path": "backend/app/nope.py", "find": "a", "replace": "b"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert changed == [] and "use `files` to create it" in problems[0]


def test_a_path_outside_the_product_is_refused(code):
    _previous, changed, problems = apply_edits(
        code,
        [{"path": "../../etc/passwd", "find": "root", "replace": "x"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert changed == [] and "path refused" in problems[0]


def test_a_malformed_edit_is_reported_not_ignored(code):
    _previous, changed, problems = apply_edits(
        code, [{"path": "backend/app/main.py"}, "nonsense", {}], log=QUIET, product_id="prod-x"
    )
    assert changed == []
    assert any("needs path, find and replace" in p for p in problems)


def test_a_no_op_edit_is_reported(code):
    _previous, _changed, problems = apply_edits(
        code,
        [{"path": "backend/app/deps.py", "find": "cache_service", "replace": "cache_service"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert any("changed nothing" in p for p in problems)


# --- wiring ------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def test_edits_are_applied_after_the_writes_and_nothing_is_excluded():
    """The first version had this backwards and it cost seventeen edits in one round.

    Edits ran first, and any file the response also rewrote had its edits dropped — "editing a file
    about to be replaced is pointless". That reasoning does not survive batching. From the first live
    round where the model preferred the tool:

        batch 1/3: 0 rewrite(s) and 3 edit(s)
        batch 2/3: 0 rewrite(s) and 15 edit(s)
        batch 3/3: 4 rewrite(s) and 0 edit(s)
        Applied 1 edit(s)                      <- seventeen discarded

    The rewrites came from the UNSCOPED batch — the least focused one, the sprawl this design exists to
    fight — and they silently overrode eighteen surgical edits from the scoped batches. In this order
    both intents survive: the rewrite lands, then the edit refines it, and an edit whose `find` no
    longer matches is reported rather than vanishing.
    """
    src = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
    apply_at = src.index("_edit_previous, _edited_paths, _edit_problems = apply_edits(")
    write_at = src.index('for file_info in code_data.get("files", []) or []:')
    assert write_at < apply_at, "edits still run before the writes that can overwrite them"
    window = src[apply_at : apply_at + 400]
    assert 'code_data.get("edits") or []' in window
    assert "not in {" not in window, "edits are still filtered against the rewritten files"


def test_edited_files_join_the_rounds_write_list():
    """Otherwise the scope guard, the delivery check and the rollback all miss them."""
    src = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "saved_relative_paths.append(_rel)" in src
    assert 'saved_files.append({"path": _rel, "edited": True})' in src


def test_the_prompt_tells_the_model_the_key_exists():
    prompt = (ROOT / "agents" / "prompts" / "developer_core_prompt.md").read_text(encoding="utf-8")
    assert "EDITS BEAT REWRITES" in prompt
    assert '"find"' in prompt and '"replace_all"' in prompt
    assert "settings.ATLAS_BASE_URL" in prompt, (
        "the measurement that justifies the rule is missing, and a bare rule gets ignored"
    )
    contract = prompt[prompt.index("=== OUTPUT CONTRACT (strict) ===") :]
    assert "- edits:" in contract, "edits is not in the strict output contract"


def test_the_batch_runner_keeps_edits_from_every_batch():
    """Two batches may each edit a different part of one file; keying by path would drop one."""
    src = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
    runner = src[src.index("async def _generate_repair_batches") :]
    runner = runner[: runner.index("\n    async def execute(")]
    assert "merged_edits: list[dict] = []" in runner
    assert 'for edit in data.get("edits") or []:' in runner
    assert '"edits": merged_edits' in runner
    # An edit outside the batch's files is KEPT and measured, not dropped. The hard drop cost the
    # very first live round: batch 1 produced an edit to models/audit.py — where the duplicate table
    # actually lives — and it was thrown away before anything could measure it. Batch scope exists to
    # stop sprawl, and sprawl is a property of rewrites: a rewritten file is retyped in full and can
    # lose anything in it, while an edit changes the bytes it names. The safer of the two cannot
    # deserve the stricter rule, and the round guard already measures out-of-scope writes.
    assert "the round guard measures it" in runner
    assert "dropped an edit" not in runner, "an edit is discarded before anything measures it"
    # A round of pure edits must not be discarded for having no rewrites.
    assert "if not merged and not merged_edits and not merged_deletions:" in runner


def test_the_batch_instruction_offers_edits_first():
    from core.repair_batches import batch_instruction, plan_batches

    batches = plan_batches(
        [
            {
                "severity": "critical",
                "code": "missing_attribute",
                "title": "Module health: missing_attribute",
                "detail": "Settings never declares cors_origins (backend/app/config.py)",
            }
        ]
    )
    text = batch_instruction(batches[0], 0, 1)
    assert "Prefer `edits`" in text
    assert "retyped from memory" in text


def test_the_instruction_teaches_appending_rather_than_rewriting():
    """The failure that costs the most rounds, watched live:

        Reverted schemas/analytics.py: the rewrite dropped 'DashboardUpdate', which other modules import
        Reverted rule_engine.py: the rewrite dropped 'RuleEngine', which other modules import
        Code generation complete: 0 files

    The round was adding three classes to a schemas file. Rewriting a file to add to it means
    reproducing everything already in it from memory; an append cannot lose what it never touched.
    """
    from core.repair_batches import batch_instruction, plan_batches

    batch = plan_batches(
        [{"severity": "critical", "code": "missing_symbol",
          "title": "Module health: missing_symbol",
          "detail": "backend/app/schemas/analytics.py does not define 'ChartCreate'"}]
    )[0]
    text = batch_instruction(batch, 0, 1)
    assert "use an edit that appends" in text
    assert "unique anchor near the end" in text
    assert "DashboardUpdate" in text, "the measurement that justifies the rule is missing"

    prompt = (ROOT / "agents" / "prompts" / "developer_core_prompt.md").read_text(encoding="utf-8")
    assert "append with an edit" in prompt
    assert "RuleEngine" in prompt


def test_a_repair_round_is_shown_the_files_it_must_change(tmp_path):
    """The single most expensive omission in this pipeline.

    The developer payload carries the idea, the spec, the plan, the architecture and the findings —
    and never the current contents of the files the round is told to change. So every `find` string
    was quoted from memory and missed:

        4 edit(s) did not apply: advisory.ts: `find` text does not appear in the file …
                                 Dashboard.tsx: `find` text does not appear in the file …

    and every rewrite reconstructed the file from memory and dropped whatever it failed to recall:

        Reverted schemas/analytics.py: the rewrite dropped 'DashboardUpdate' …
        Reverted rule_engine.py: the rewrite dropped 'RuleEngine' …
        Code generation complete: 0 files

    Neither is a model failing at its job. Both are what happens when you ask someone to edit a
    document they cannot see.
    """
    from core.repair_batches import attach_file_contents, batch_instruction, plan_batches

    code = tmp_path / "code"
    (code / "backend" / "app" / "schemas").mkdir(parents=True)
    (code / "backend" / "app" / "schemas" / "analytics.py").write_text(
        "class DashboardUpdate:\n    name: str\n", encoding="utf-8"
    )
    batch = plan_batches(
        [{"severity": "critical", "code": "missing_symbol",
          "title": "Module health: missing_symbol",
          "detail": "backend/app/schemas/analytics.py does not define 'ChartCreate'"}]
    )[0]

    contents = attach_file_contents(batch, code)
    assert contents == {"backend/app/schemas/analytics.py": "class DashboardUpdate:\n    name: str\n"}

    text = batch_instruction(batch, 0, 1, contents)
    assert "class DashboardUpdate" in text, "the round still cannot see the file"
    assert "EXACTLY AS THEY ARE ON DISK RIGHT NOW" in text
    assert "character for character" in text
    assert "anything you leave out of a rewritten file is deleted" in text


def test_a_large_file_is_truncated_rather_than_dropped(tmp_path):
    """A truncated tail still lets an append anchor on what is visible; nothing at all does not."""
    from core.repair_batches import MAX_ATTACHED_FILE_CHARS, attach_file_contents

    code = tmp_path / "code"
    (code / "frontend").mkdir(parents=True)
    (code / "frontend" / "big.tsx").write_text("x" * (MAX_ATTACHED_FILE_CHARS + 5000), encoding="utf-8")
    contents = attach_file_contents({"files": ["frontend/big.tsx"]}, code)
    body = contents["frontend/big.tsx"]
    assert len(body) < MAX_ATTACHED_FILE_CHARS + 200
    assert "truncated" in body


def test_a_missing_file_is_simply_absent(tmp_path):
    from core.repair_batches import attach_file_contents

    code = tmp_path / "code"
    code.mkdir()
    assert attach_file_contents({"files": ["nope.py"]}, code) == {}


def test_the_runner_passes_the_tree_to_every_batch():
    """Structural: the attachment is inert unless the runner knows where the code lives."""
    src = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "code_root: Path," in src
    assert "attach_file_contents(batch, code_root)" in src
    assert 'code_root=self.data_root / "code" / product_id' in src


def test_the_unscoped_batch_also_gets_its_files(tmp_path):
    """It has no file list by construction, so it was the one batch still quoting from memory.

    Measured on the round where the attachment first worked: the scoped batch returned
    `0 rewrite(s) and 2 edit(s)` and every one applied, while the unscoped batch's misses were all
    `find text does not appear in the file` — deps.py, advisory.ts, Dashboard.tsx. Its findings still
    name paths; they just were not being read.
    """
    from core.repair_batches import attach_file_contents

    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "deps.py").write_text("cache = None\n", encoding="utf-8")
    batch = {
        "files": [],
        "findings": [
            {"severity": "high", "title": "Demo journey: import_error",
             "detail": "backend/app/deps.py imports a name that does not exist"},
        ],
    }
    assert attach_file_contents(batch, code) == {"backend/app/deps.py": "cache = None\n"}


def test_an_ambiguous_find_is_told_where_the_matches_are(code):
    """"Be more specific" is advice; the three places are an instruction.

    The same message came back three rounds running for backend/app/services/rule_engine.py — the
    model kept choosing an anchor that occurs three times and had no way to know which lines they were
    on, so every retry was another guess at the same ambiguity. The round ended with
    `Code generation complete: 0 files`.
    """
    _tree(code, {"backend/app/svc.py": "def a():\n    return x\n\ndef b():\n    return x\n"})
    _previous, changed, problems = apply_edits(
        code,
        [{"path": "backend/app/svc.py", "find": "    return x", "replace": "    return y"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert changed == []
    assert "appears 2 times" in problems[0]
    assert "line 2:" in problems[0] and "line 5:" in problems[0], problems[0]
    assert "Extend `find`" in problems[0]


def test_a_miss_quotes_the_nearest_real_text(code):
    """"Does not appear" is a verdict; the actual lines are an instruction.

    One round hit this twice on the same file with two different reasons — an anchor occurring three
    times, then an anchor occurring nowhere — and ended with nothing landed. Whitespace or a
    half-remembered line is enough to miss, and the model cannot diff its guess against a file without
    being told where the guess went wrong.
    """
    _tree(code, {"backend/app/svc.py": "class RuleEngine:\n    def evaluate_advisory(self):\n        return 1\n"})
    _previous, changed, problems = apply_edits(
        code,
        [{"path": "backend/app/svc.py",
          "find": "    def compute_advisory(self):",
          "replace": "    def compute_advisory(self):"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert changed == []
    assert "does not appear" in problems[0]
    assert "closest text in the file" in problems[0], problems[0]
    assert "evaluate_advisory" in problems[0], "the nearest real line was not quoted back"
    assert "2: " in problems[0], "line numbers are missing from the quote"


def test_nothing_remotely_similar_gets_no_misleading_quote(code):
    _tree(code, {"backend/app/svc.py": "x = 1\n"})
    _previous, _changed, problems = apply_edits(
        code,
        [{"path": "backend/app/svc.py",
          "find": "class TotallyDifferentThing:\n    def wildly_unrelated(self, a, b, c):",
          "replace": "y"}],
        log=QUIET,
        product_id="prod-x",
    )
    assert "does not appear" in problems[0]
    assert "closest text" not in problems[0]


def test_a_finding_style_wrapped_path_lands_in_the_real_tree(tmp_path):
    """Findings carry `code/<product>/backend/…` and the model echoes it back.

    Taken literally the write created a nested phantom tree — measured live:

        Salvaged … giving back 1 file(s): code/prod-bdb1634806de/backend/app/routers/auth.py

    The salvage pass caught the phantom, but the round's actual fix went nowhere. Stripping the wrapper
    at `_resolve_safe_code_path` covers writes, edits and deletions in one place.
    """
    from agents.dev import _resolve_safe_code_path

    code = tmp_path / "prod-bdb1634806de"
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "routers" / "auth.py").write_text("x = 1\n", encoding="utf-8")

    for wrapped in (
        "code/prod-bdb1634806de/backend/app/routers/auth.py",
        "data/code/prod-bdb1634806de/backend/app/routers/auth.py",
        "prod-bdb1634806de/backend/app/routers/auth.py",
        "backend/app/routers/auth.py",
    ):
        got = _resolve_safe_code_path(code, wrapped)
        assert got == (code / "backend" / "app" / "routers" / "auth.py").resolve(), wrapped
    # A genuine escape is still refused.
    assert _resolve_safe_code_path(code, "../outside.py") is None


def test_a_ts_batch_carries_the_types_it_must_match(tmp_path):
    """Fixing a type mismatch against an invisible interface is guessing with extra steps.

    Measured: a round with only PublicWidget.tsx attached tried to fix
    `TS2345: Argument of type 'AdvisoryRes…'` twice and missed twice — the error just moved
    (49 → 54, then a new one at 106) — because AdvisoryResponse is declared in ../api/advisory,
    which was never shown to it.
    """
    from core.repair_batches import attach_file_contents

    code = tmp_path / "code"
    (code / "frontend" / "src" / "pages").mkdir(parents=True)
    (code / "frontend" / "src" / "api").mkdir(parents=True)
    (code / "frontend" / "src" / "pages" / "PublicWidget.tsx").write_text(
        "import { getAdvisory, AdvisoryResponse } from '../api/advisory'\n", encoding="utf-8"
    )
    (code / "frontend" / "src" / "api" / "advisory.ts").write_text(
        "export type AdvisoryResponse = { level: string }\n"
        "export const getAdvisory = () => fetch('/api/advisory')\n",
        encoding="utf-8",
    )
    got = attach_file_contents({"files": ["frontend/src/pages/PublicWidget.tsx"]}, code)
    assert "frontend/src/api/advisory.ts" in got, "the declaring file is still invisible"
    assert "the types you must match are declared here" in got["frontend/src/api/advisory.ts"]
    # And the batch file itself is still first-class.
    assert "frontend/src/pages/PublicWidget.tsx" in got


def test_the_reference_hop_is_bounded_and_relative_only(tmp_path):
    from core.repair_batches import attach_file_contents

    code = tmp_path / "code"
    (code / "frontend" / "src").mkdir(parents=True)
    imports = "".join(f"import {{ x{i} }} from './m{i}'\n" for i in range(8))
    (code / "frontend" / "src" / "big.tsx").write_text(
        imports + "import { useState } from 'react'\n", encoding="utf-8"
    )
    for i in range(8):
        (code / "frontend" / "src" / f"m{i}.ts").write_text(f"export const x{i} = {i}\n", encoding="utf-8")
    got = attach_file_contents({"files": ["frontend/src/big.tsx"]}, code)
    refs = [k for k in got if k != "frontend/src/big.tsx"]
    assert len(refs) <= 4, "the reference hop is unbounded"
    assert not any("react" in k for k in refs)


def test_the_batch_merge_carries_deletions_through():
    """A deletion the model was explicitly told to make must survive the batch merge.

    Measured: the batch scoped to the case collision answered exactly as its finding instructed —
    delete UI/Toast.tsx — and the merge returned only files/edits/notes. The round logged
    "returned 0 rewrite(s) and 0 edit(s)", the collision outlived its tenth informed round, and
    module_health plus frontend_build stayed red on one un-deletable file. A round that ONLY
    deletes is a repair, not an empty response.
    """
    from pathlib import Path

    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    merge = dev[dev.index("merged_edits: list[dict] = []") :]
    merge = merge[: merge.index("async def execute(")]
    assert 'for _del in data.get("delete_files") or []:' in merge
    assert '"delete_files": merged_deletions,' in merge
    assert "if not merged and not merged_edits and not merged_deletions:" in merge

    batches = (
        Path(__file__).resolve().parents[1] / "core" / "repair_batches.py"
    ).read_text(encoding="utf-8")
    assert "delete_files" in batches, "the batch contract never tells the model how to delete"
