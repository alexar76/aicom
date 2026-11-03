# HISTOR follows robots.txt in production (2026-11-02)

The owner asked for full RFC 9309 compliance, losing as little as the standard allows. The code is
`0643fee6e` (HISTOR CHANGELOG, Unreleased; `histor/docs/operations.md`, "robots.txt (RFC 9309)"). The
owner approved the production rollout ("Yes, roll it out"); before that the auto-mode classifier had
stopped the first attempt.

## Rollout

`histor_robots_overlay.sh` on admin-vps, 05:39:39–05:40:14Z (`rollout.log`):
- **Base.** `aicom-security:histor-histor-1-rb-20261102` = `d2f3b3dcea1e`, built FROM the running
  `wd-20261102` (`914a930a9334`, WARDEN 0.22.4, deployed by another session at 04:35Z).
- **Pre-checks.** All 12 replaced files were checked equal to `main` before `0643fee6e` in the running
  container.
- **Inside the image.**
  - The MOMUS gate passed (run `20261102T042600`, build `bcfc888d…`, unchanged).
  - `smoke.py` passed: migration 019 is last; RFC 9309 decisions; the reader takes the policy; the
    check note.
- **Switch.** Compose moved to the new image and the service came up healthy, applying migration 019.
- **After.**
  - The host tree was updated.
  - The MOMUS binding moved to `d2f3b3dcea1e`, and `histor:warden-remediation-base` was retagged.
  - The interrupted crawl was restarted.
- **Rollback.** At the top of the script.

## Checked live (05:41–05:45Z)

- **First minute and a half after the restart.**
  - `robots_txt` held 48 origins: 40 files, 8 with a 4xx (none).
  - 14 targets were `robots-disallowed`, all observed before (their history stays).
  - 67 reads were `ok`.
- **No errors** in the service log.
- **An example: `https://signupsheet.page/mcp`.**
  - Detail: "https://signupsheet.page/robots.txt disallows /mcp for HISTOR: 'Disallow: /mcp' in the
    'User-agent: *' group (RFC 9309). To let HISTOR read it, add 'User-agent: histor' with
    'Allow: /mcp'."
  - The live file says the same. Its `*` group has `Disallow: /mcp` and `Allow: /mcp/server-card`, and
    so do its groups for named AI crawlers.
  - `/api/v1/servers/4066029fdd47ab40` gives `lastStatus` `robots-disallowed` and keeps
    `firstPinned` 2026-10-26 and the digest.
  - `POST /api/v1/check` for that endpoint ends its note with: "HISTOR does not read this endpoint: its
    site's robots.txt does not allow HISTOR (RFC 9309). Changes to its tools after 2026-11-01 are not
    recorded; the comparison is with its last observation."
  - The server page shows the note in the viewer's language ("Не наблюдается: robots.txt этого сайта не
    разрешает HISTOR…") above the deciding rule.
  - The crawler FAQ on the landing page is the new text.
- **Other examples:**
  - www.nextarena.co/api/mcp and flowershow.app/api/mcp (`Disallow: /api/`);
  - eu-parliament.caseyjhand.com/mcp (`Disallow: /mcp`).

## What can still be kept (not built)

Of the 4,359 hosts with a disallowed endpoint in the 2026-11-02 survey:
- 103 explicitly allow an MCP server card (`Allow: /mcp/server-card`, `/.well-known/mcp…`);
- for 3,046, `/.well-known/mcp/server-card.json` is not disallowed for HISTOR.

How many publish a card that lists their tools is not known yet. A card the robots.txt allows could be
read as the publisher's declared tool set, the kind HISTOR already shows as "declared", without
touching the disallowed MCP path.
