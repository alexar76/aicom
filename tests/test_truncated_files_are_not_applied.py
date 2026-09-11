"""A file that does not parse is not a repair, and truncation is how you get one.

Measured on a stuck product. A batch was asked to rewrite three whole files against a 24k-token
output cap; the third came back stopping mid-def, and the next verdict read:

    Incomplete function definition causes SyntaxError in app/deps.py
    Incomplete test in test_atlas_client.py

Those counted against the round, so the round was reverted — losing the two files that were fine. The
model was not wrong: we asked for more than the answer could hold. Writing the fragment anyway is the
one response that makes it worse.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
BATCHES = (ROOT / "core" / "repair_batches.py").read_text(encoding="utf-8")


def test_an_unparsable_python_file_is_dropped_from_the_batch():
    block = DEV[DEV.index('if str(path).endswith(".py"):') :][:1800]
    assert "_ast.parse(_content)" in block
    assert "except SyntaxError" in block
    assert "does not parse" in block


def test_the_message_names_the_line_and_the_likely_cause():
    """"Dropped a file" is not actionable; "line 41, response probably cut off" is."""
    block = DEV[DEV.index('if str(path).endswith(".py"):') :][:1800]
    assert "_syn.lineno" in block and "_syn.msg" in block
    assert "cut " in block and "truncated file is worse than no file" in block


def test_the_check_runs_before_the_file_joins_the_round():
    """Applied first, the fragment becomes the rollback baseline for everything after it."""
    block = DEV[DEV.index('if str(path).endswith(".py"):') :][:1800]
    assert block.index("_ast.parse(_content)") < block.index("undefined_names_in_source"), (
        "a file that cannot parse cannot be meaningfully checked for unbound names either"
    )


def test_the_output_allowance_is_large_enough_for_a_multi_file_batch():
    assert "DEFAULT_BATCH_MAX_TOKENS = 64_000" in BATCHES
    assert "24_000" not in BATCHES.split("DEFAULT_BATCH_MAX_TOKENS")[0][-200:]


def test_the_allowance_stays_tunable():
    from core.repair_batches import batch_max_tokens

    assert batch_max_tokens() >= 64_000
    assert "AIFACTORY_REPAIR_BATCH_TOKENS" in BATCHES


def test_the_limits_come_from_the_model_configuration():
    """Every size in this file was a constant smaller than the deployed model, for no reason other
    than nobody having looked: the provider advertises max_tokens 128000 and a 1M-token context
    window, against a 24k output ceiling and a 20k file-attachment cut."""
    from core.repair_batches import active_model_limits, attach_file_chars, batch_max_tokens

    limits = active_model_limits()
    assert limits["max_tokens"] >= 8192, "the provider config could not be read"
    assert limits["context_window"] >= 32_000
    assert batch_max_tokens() >= limits["max_tokens"]
    assert attach_file_chars() > 20_000, "a file truncated mid-class produces edits that miss"


def test_a_failure_to_read_the_config_is_loud():
    """A silent zero means every limit falls back to a constant — which is what happened while
    active_model_limits() was missing its Path import, and nothing said so."""
    src = (ROOT / "core" / "repair_batches.py").read_text(encoding="utf-8")
    block = src[src.index("def active_model_limits(") : src.index("def findings_listing_budget(")]
    assert "except Exception as exc:" in block
    assert "logging" in block and "falling back to constants" in block
