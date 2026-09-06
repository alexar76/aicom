# SKOPOS v0.1.2

Bot-filter correctness: **Hide bots** no longer relies only on `user_agents.is_bot`.

## Fixed
- Crawlers mislabeled as humans (`ua_is_bot=0`) still appeared with Hide bots on — notably **Applebot**, **360Spider**, **OAI-SearchBot**
- SQL analytics filter now excludes heuristic bot UA/browser matches in addition to `ua_is_bot=1`
- Ingest + Backfill re-classify those false negatives

## Install

```bash
pip install -U skopos-fleet==0.1.2
# or
docker pull ghcr.io/alexar76/skopos:v0.1.2
```

Live demo: https://skopos.modelmarket.dev  
Docs: https://alexar76.github.io/skopos/
