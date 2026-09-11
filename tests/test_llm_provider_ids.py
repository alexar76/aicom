"""Legacy LLM provider id normalization and JSONL migration."""

import json
from pathlib import Path

from llm.pricing_estimate import enrich_llm_log_entry, migrate_llm_calls_provider_ids
from llm.provider_ids import normalize_llm_provider_id


def test_normalize_deep_seek_aliases():
    assert normalize_llm_provider_id("deep-seek") == "deepseek_api"
    assert normalize_llm_provider_id("dee-seek") == "deepseek_api"
    assert normalize_llm_provider_id("deepseek_api") == "deepseek_api"
    assert normalize_llm_provider_id("groq_api") == "groq_api"


def test_enrich_llm_log_entry_rewrites_legacy_provider():
    entry = {"provider": "deep-seek", "model": "deepseek-chat", "tokens_used": 1_000_000}
    enrich_llm_log_entry(entry)
    assert entry["provider"] == "deepseek_api"
    assert entry["provider_legacy"] == "deep-seek"
    assert entry["estimated_cost_usd"] == 0.27


def test_migrate_llm_calls_jsonl(tmp_path):
    log = tmp_path / "llm_calls.jsonl"
    log.write_text(
        json.dumps(
            {
                "provider": "deep-seek",
                "model": "deepseek-chat",
                "tokens_used": 1000,
                "estimated_cost_usd": 0.99,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stats = migrate_llm_calls_provider_ids(log, dry_run=False, re_enrich_cost=True)
    assert stats["migrated"] == 1
    row = json.loads(log.read_text(encoding="utf-8").strip())
    assert row["provider"] == "deepseek_api"
    assert row["provider_legacy"] == "deep-seek"
    assert row["estimated_cost_usd"] != 0.99
