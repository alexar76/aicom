# aimarket-dataset

**Weekly anonymized invocation corpus. Open data for researchers.**
Every week, exports `ai-market-corpus-week-N.jsonl` — fully anonymized invocation records (hashed IDs, PII scrubbed). Researchers cite it. Your orchestrator trains on it. Marketing effect: "the AI Economy's public dataset."

## When to Use
- Academic research on AI marketplace economics
- Training data for your own orchestrator (which capabilities get called for which tasks)
- Public transparency — "here's what the AI economy looks like this week"
- Marketing — press coverage from data journalists

## Installation
```bash
pip install aimarket-dataset
```

## Example
```python
from aimarket_hub.database import HubDatabase
from aimarket_dataset.dataset_exporter import export_dataset, schedule_weekly_export

db = HubDatabase("data/hub.db")

# Export this week's corpus
path = export_dataset(db, output_dir="data/datasets", week_number=21)
print(f"Exported to: {path}")

# Check a record
import json
with open(path) as f:
    record = json.loads(f.readline())
    print(record)
    # {"week": 21, "capability_id": "e1b44c49d7b5",
    #  "product_id": "cc2a8f969bd2", "price_usd": 0.40,
    #  "latency_ms": 8100, "success": true, ...}

# Cron-friendly: idempotent — exports only if this week's file doesn't exist
schedule_weekly_export(db)
```

## Schema
```json
{
  "week": 21,
  "capability_id": "sha256hash12",
  "product_id": "sha256hash12",
  "source_hub": "sha256hash12",
  "price_usd": 0.40,
  "latency_ms": 8100,
  "success": true,
  "timestamp": "2026-05-22T12:00:00Z",
  "protocol_version": "v2"
}
```

## Privacy
- All IDs are SHA-256 hashed (12-char prefix)
- PII patterns scrubbed (emails → `[email]`, SSN → `[ssn]`, cards → `[card]`, IPs → `[ip]`)
- No consumer addresses, no wallet data
- License: CC-BY 4.0

## License
MIT · Maintained by AI-Factory
