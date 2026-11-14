# Seller review before publication — live 2026-11-14

**Why.** YuTao (Insight, PriorSeal) in alexar76/aimarket-hub#23, 2026-11-13T13:34:47Z: «We will review any proposed
aggregate text and every attributed Insight or PriorSeal number before publication.» Owner: «Да, делай».

**What runs.**
- Gate on our side: `scripts/seller_review.py` + `scripts/seller_review_registry.json` (who, patterns, 72 h window,
  `silence_is_consent: false`). A paragraph that names a registered seller and holds a digit is filed; publication
  passes only on the seller's OK. Fails closed (exit 2 waiting/objected, 3 check failed). Hooked into
  `modelmarket-blog/deploy.sh` (live posts) and `schedule_release.sh` (the scheduled post). Aggregates without names:
  `seller_review.py file --seller yutao FILE`. Gate token: `~/.config/seller-review/admin_token` on the owner's Mac (0600).
- Seller's side: gateway okx-a2mcp `src/web/review.js`, `https://modelmarket.dev/tools/review/<private token>/`
  (page, `feed.xml`, `feed.json`, OK/object form), API `/tools/review/api/requests` (Bearer gate token).
  Secrets on factory-vps `/opt/okx-a2mcp-secrets/review_sellers.json` and `review_admin_token` (uid 1000, 0400);
  answers on docker volume `okx-a2mcp-review` (`/data/review/state.json`).

**Deploy.** `okx-a2mcp/deploy.sh` from local main 8a0602940: `okx-a2mcp:prod-20261114-8a0602940` healthy; previous
container kept stopped as `okx-a2mcp-prev` (image `aicom-security:okx-a2mcp-symmartys-20261114`, another session's
build of 08:55Z). Before deploying, the live container's 30 source files equalled main byte for byte; it also held
`src/mcp/emporion-tools.json`, which no code reads (leftover of the EMPORION→SYMMARTYS rename) and the new image drops.
Rollback: on factory-vps `docker rm -f okx-a2mcp && docker rename okx-a2mcp-prev okx-a2mcp && docker start okx-a2mcp`.

**Checked after deploy:** /tools/, /tools/x402-check, /tools/badge/vet402.svg 200; unpaid POST /x402/histor-check 402;
review API 401 without token, 200 `{"requests":[]}` with it; YuTao's page, feed.xml, feed.json 200 (checked on the host
without printing the token); a random 64-hex link 404; volume writable by uid 1000. Tests: gateway 85/85, gate 11/11.

**Not done yet:** YuTao has no public e-mail; the private link goes to him only after he writes to qwezzy721@gmail.com
(colleague task §111 step 1 + 6). No webhook/e-mail push yet — asked him which he prefers.
