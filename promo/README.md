# Promo Ops Kit

Structured launch materials for AI-Factory distribution.

## Folder map

- `channels/producthunt.md` — Product Hunt launch copy and first-comment pack.
- `channels/show-hn.md` — Show HN post (architecture + metrics narrative).
- `channels/reddit.md` — Reddit post variants for `r/programming` and `r/SideProject`.
- `channels/x.md` — X/Twitter thread and short variants.
- `channels/telegram-email.md` — announcement copy for Telegram and email.
- `followups/templates.md` — follow-up message templates for comments and DMs.
- `utm/campaigns.example.json` — source-of-truth UTM campaign definitions.

## Automation flow

1. Edit `utm/campaigns.example.json` with final landing URLs and campaign names.
2. Generate tracked links:
   - `python3 scripts/promo_build_links.py --in promo/utm/campaigns.example.json --out promo/utm/generated-links.md`
3. Paste generated links into channel templates in `promo/channels/`.
4. For automated reposts use existing outreach channels (webhook/telegram/smtp) from Admin -> Outreach.

## Channel strategy

- Product Hunt / Show HN / Reddit: publish manually from trusted accounts.
- Telegram / email / webhook fan-out: automate after each manual launch milestone.
