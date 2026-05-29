#!/usr/bin/env python3
"""Bootstrap user-guide.md and README gallery/promo sections for desktop SKUs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop-integrations"

PRODUCTS = {
    "interview-prep-coach": {
        "title": "Interview Prep Coach",
        "tagline": "Company-specific interview banks with marketplace freshness",
        "tier": "Tier 1 — Flagship consumer",
        "economics": "Discover question banks, open USDT channels, invoke with TEE verify, sell anonymized trajectories",
        "screens": ["prep-dashboard", "marketplace-browse", "mock-interview", "wallet-details"],
    },
    "personal-finance-coach": {
        "title": "Personal Finance Coach",
        "tagline": "Local-first finance intelligence with marketplace tax rules",
        "tier": "Tier 2 — Privacy-first consumer",
        "economics": "Buy ML categorizers and tax rules; bank data never leaves device",
        "screens": ["overview", "import", "marketplace", "privacy"],
    },
    "capability-composer": {
        "title": "Capability Composer",
        "tagline": "Visual pipeline builder for AI Market capabilities",
        "tier": "Tier 3 — Builder tool",
        "economics": "Discover capabilities, chain DAG, execute via channels, publish templates for sale",
        "screens": ["canvas", "discover", "templates", "export"],
    },
    "cold-outreach-coach": {
        "title": "Cold Outreach Coach",
        "tagline": "B2B email optimization with decentralized deliverability rules",
        "tier": "Tier 2 — Sales enablement",
        "economics": "Buy weekly SPF/DKIM rules; sell anonymized structural reply-rate signals",
        "screens": ["dashboard", "composer", "deliverability", "marketplace"],
    },
    "creator-algorithm-coach": {
        "title": "Creator Algorithm Coach",
        "tagline": "TikTok/YouTube/IG algorithm signals by niche",
        "tier": "Tier 2 — Creator economy",
        "economics": "Buy algorithm windows; sell TEE-verified creator metrics",
        "screens": ["dashboard", "discover", "publish", "insights"],
    },
    "discovery-prospector": {
        "title": "Discovery Prospector",
        "tagline": "Find underserved marketplace niches before competitors",
        "tier": "Tier 5 — Idea service for builders",
        "economics": "Buy hub telemetry, detect gaps, sell niche insight reports",
        "screens": ["gaps-list", "gap-detail", "telemetry", "sdk-export"],
    },
    "freelance-contract-reviewer": {
        "title": "Freelance Contract Reviewer",
        "tagline": "Local contract parsing with marketplace clause libraries",
        "tier": "Tier 2 — Legal/freelance",
        "economics": "Buy jurisdiction clause packs; sell anonymized clause patterns",
        "screens": ["dashboard", "upload", "marketplace", "review-report"],
    },
    "reputation-dashboard": {
        "title": "Reputation Dashboard",
        "tagline": "Yelp for aimarket — verified capability ratings",
        "tier": "Tier 5 — Meta trust layer",
        "economics": "Fetch on-chain reputation; submit purchase-anchored reviews",
        "screens": ["top-capabilities", "my-reviews", "seller-console", "curator-console"],
    },
}


def user_guide(meta: dict) -> str:
    title = meta["title"]
    return f"""# {title} — User Guide

## What this product does

{meta['tagline']}. {meta['tier']}.

## AI Market economics (integrated)

This app implements **AI Market Protocol v2** via `aimarket_agent`:

- **Wallet** — Ed25519-signed payments (dev key in local builds; OS keychain in production)
- **Discovery** — Search hub capabilities by intent and category
- **Channels** — Pre-funded USDT channels on Base for micro-payments per invoke
- **Invoke + TEE** — Capability calls with optional attestation verification
- **Settlement** — Channel close returns unused balance

{meta['economics']}.

## First launch

1. Complete onboarding / connect wallet (Settings or wallet panel)
2. Open marketplace or discovery tab
3. Search by intent relevant to your workflow
4. Open a channel (~\$5 covers ~50 calls at \$0.10 each)
5. Invoke capabilities; review Bill of Materials / receipts

## Privacy

See product README and `docs/architecture.md`. Local-first apps keep sensitive content on-device; only structural or anonymized metrics may be published.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Hub unreachable | Check `HUB_URL` or use local factory at `http://127.0.0.1:8080` |
| `privateKeyHex` error | Wallet key must be 64-char hex |
| Empty marketplace | Run factory pipeline to seed demo capabilities |

## More

- [Value in plain words](value.md)
- [User cases](user-cases.md)
- [SDK integration](sdk-integration.md)
- [Architecture](architecture.md)
"""


def readme_promo_block(meta: dict) -> str:
    screens = meta["screens"]
    gallery_rows = "\n".join(
        f"| ![{s}](assets/screenshots/{s}.png) |" for s in screens[:4]
    )
    return f"""
## Promo video

Watch the product walkthrough (Playwright capture from factory pipeline):

- **Latest clip:** [`docs/gallery/promo-latest.webm`](../docs/gallery/promo-latest.webm) *(generated on shipped builds)*
- **Record locally:** `./scripts/run_web_demo.sh` then open Admin → Demo Storefront

## Screenshot gallery

| | | | |
|---|---|---|---|
{gallery_rows}

Full gallery: **[assets/screenshots/](assets/screenshots/)**

Screenshots: `python3 ../../scripts/capture_desktop_screenshots.py <slug>` from repo root.
"""


def main() -> None:
    for slug, meta in PRODUCTS.items():
        root = DESKTOP / slug
        if not root.is_dir():
            continue
        docs = root / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "user-guide.md").write_text(user_guide(meta), encoding="utf-8")

        shots = root / "assets" / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        (shots / "README.md").write_text(
            f"# {meta['title']} screenshots\n\n"
            f"Expected files: {', '.join(s + '.png' for s in meta['screens'])}.\n",
            encoding="utf-8",
        )

        readme = root / "README.md"
        if readme.is_file():
            text = readme.read_text(encoding="utf-8")
            if "## Promo video" not in text:
                # Insert after first --- block
                parts = text.split("\n---\n", 1)
                if len(parts) == 2:
                    text = parts[0] + readme_promo_block(meta) + "\n---\n" + parts[1]
                    readme.write_text(text, encoding="utf-8")
        print(f"OK {slug}")

    import subprocess
    subprocess.run(
        ["python3", str(ROOT / "scripts" / "bootstrap_product_value.py")],
        check=False,
        cwd=ROOT,
    )


if __name__ == "__main__":
    main()
