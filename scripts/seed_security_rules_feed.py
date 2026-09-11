#!/usr/bin/env python3
"""Seed a local security-rules feed capability for local-security-audit.

Registers ``security-rules.sec-feed@v1`` on a hub DB. The capability returns a
JSON pattern pack (same regexes the desktop app used to hardcode) so ``buy_feed``
+ ``scan_secrets`` can consume marketplace output instead of a frozen local list.

    python3 scripts/seed_security_rules_feed.py /app/data/hub.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Keep in sync with desktop-integrations/local-security-audit DEFAULT_PATTERNS.
DEFAULT_PATTERNS = [
    {"id": "aws-akia", "pattern": r"AKIA[0-9A-Z]{16}", "severity": "critical", "description": "AWS Access Key ID"},
    {"id": "aws-secret", "pattern": r"aws_secret_access_key\s*=\s*['\"]?[A-Za-z0-9/+=]{40}", "severity": "critical", "description": "AWS Secret Access Key"},
    {"id": "ghp", "pattern": r"ghp_[A-Za-z0-9]{36}", "severity": "critical", "description": "GitHub Personal Access Token"},
    {"id": "gho", "pattern": r"gho_[A-Za-z0-9]{36}", "severity": "critical", "description": "GitHub OAuth Token"},
    {"id": "private-key", "pattern": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "severity": "critical", "description": "Private Key"},
    {"id": "stripe-live", "pattern": r"sk_live_[A-Za-z0-9]{24,}", "severity": "critical", "description": "Stripe Live Secret Key"},
    {"id": "generic-cred", "pattern": r"(?:password|passwd|pwd|secret|token|api_key|apikey)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "severity": "high", "description": "Generic credential assignment"},
    {"id": "jwt", "pattern": r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}", "severity": "medium", "description": "JWT token in source"},
    {"id": "db-url", "pattern": r"(?:postgres|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@", "severity": "critical", "description": "Database connection string with credentials"},
    {"id": "slack", "pattern": r"xox[bps]-[A-Za-z0-9-]{10,}", "severity": "high", "description": "Slack Bot/User Token"},
    {"id": "gitlab", "pattern": r"glpat-[A-Za-z0-9_-]{20,}", "severity": "critical", "description": "GitLab Personal Access Token"},
]

CAPABILITY_ID = "security-rules.sec-feed@v1"
PRODUCT_ID = "security-rules"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db_path")
    args = ap.parse_args()

    path = Path(args.db_path)
    if not path.exists():
        print(f"missing db: {path}", file=sys.stderr)
        return 1

    # Store the pattern pack in prompt_template as JSON — hub invoke for caps
    # without invoke_url/factory can return this via sandbox/demo path; the
    # desktop client also treats buy_feed result / cache as the pack.
    pack = json.dumps({"patterns": DEFAULT_PATTERNS, "version": "1.0.0"}, indent=2)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        INSERT OR REPLACE INTO capabilities
            (capability_id, product_id, name, version, description,
             input_schema, output_schema, price_per_call_usd, p50_latency_ms,
             success_rate_30d, source_hub, source_hub_name,
             routed_price_usd, routing_fee_bps, trust_score, agent, prompt_template,
             invoke_url, publisher_id, provider_pubkey, stake_usd, is_demo, updated_at)
        VALUES (?, ?, ?, 'v1', ?, ?, ?, 0.01, 50, 0.99, 'local', 'modelmarket.dev',
                NULL, 0, 0.7, '', ?, '', 'hub:security-rules', '', 0.0, 0, datetime('now'))
        """,
        (
            CAPABILITY_ID,
            PRODUCT_ID,
            "security-rules.sec-feed",
            "Security rules feed — regex pattern pack for local secret scanners (category: security)",
            json.dumps({"type": "object", "properties": {"ecosystem": {"type": "string"}}}),
            json.dumps({
                "type": "object",
                "properties": {
                    "patterns": {"type": "array"},
                    "version": {"type": "string"},
                },
            }),
            pack,
        ),
    )
    conn.commit()
    print(f"seeded {CAPABILITY_ID} → {path}")
    # Also write a sidecar the client can fetch if invoke returns the pack
    sidecar = path.with_suffix(".security-rules.json")
    sidecar.write_text(pack, encoding="utf-8")
    print(f"wrote {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
