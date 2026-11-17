# MOMUS code rules on outside code with published vulnerabilities (2026-11-16)

Owner, 11-16: «давай прогоним момус по чужому коду». Question: would MOMUS's code target find real bugs in code that
is not ours, before anyone published them?

## Method

- Rules: `momus/momus/codescan/vulnetix_classes.py` as in aicom main 14af764e8, the same `scan_file` the MOMUS `code`
  target runs (5 rules: VX-306-OPEN-WITHOUT-KEY, VX-918-CHECK-THEN-CONNECT, VX-918-UNPINNED-RETURN,
  VX-FWD-HEADER-TRUST, VX-SSH-NO-HOSTKEY). Python only; Semgrep (push gate) is not part of MOMUS and was not run.
- Set: GitHub global advisories, ecosystem pip, CWE-918, 306, 290, 348, 322, 295, read 2026-11-16 via `gh api`
  (read-only). 294 unique; 172 not withdrawn with a GitHub fix-commit link (`candidates.json`); 147 distinct fix commits.
- For each fix commit: every changed `.py` (and ssh-config-like) file at the parent and at the fix, from
  raw.githubusercontent.com (`fetch.py`). Downloaded code was parsed, never run.
- Hit = a rule of the advisory's class fires in a changed file before the fix. Fix-confirmed = the fix lowers that count.
  Counted per distinct fix commit (several advisories share one commit). `score.py`, `results.json`.
- The files flagged anywhere were read again at each repo's default branch the same evening (`head.py`).

## Result

| Class | Fix commits | Rule fired before the fix | …and the fix removed it |
|---|---:|---:|---:|
| SSRF (CWE-918) | 54 | 8 | 5 |
| Missing auth (CWE-306) | 45 | 4 | 2 |
| Spoofed client address (CWE-290/348) | 17 | 3 | 3 |
| TLS / ssh host key (CWE-295/322) | 36 | 0 | 0 |

So about 1 published vulnerability in 15 of these classes is in reach of the rules (10 of 152 class-commit pairs
confirmed by the fix). Found ones include pyload (XFF login bypass), langflow `get_client_ip`, OctoPrint
`get_remote_address` (CVE-2024-32977), crewAI scrape tools, docling image loader, datamodel-code-generator, flyto-core.
TLS verification (CWE-295) is outside the rules entirely: VX-SSH-NO-HOSTKEY reads ssh options only.

Misses are mostly what the rules cannot see: no URL check at all (the rule needs a check followed by a connect by
name), authorisation logic in a route, path or redirect handling, non-Python code.

## Still flagged in today's code (default branch, 2026-11-16 evening), read by hand

| Repo, file | Rule | Reading |
|---|---|---|
| MervinPraison/PraisonAI `spider_tools.py` `scrape_page` | CHECK-THEN-CONNECT | plausible: `_validate_url` then `requests.Session().get` by name, a DNS-rebinding gap after the 2026-08 fixes. Not verified by running, not reported |
| open-webui `retrieval/utils.py`, `retrieval/web/utils.py` | CHECK-THEN-CONNECT | false positive: requests go through `get_ssrf_safe_requests_session`, a connect-time guard the rule does not recognise |
| BerriAI/litellm `auth_utils.get_request_ip_address` | FWD-HEADER-TRUST | by design: X-Forwarded-For only when the operator sets `use_x_forwarded_for` |
| mlflow `server/auth`, bambuddy `core/auth.py` | OPEN-WITHOUT-KEY | by design: checks that pass when the operator turned auth off |

## What it means

- For bug bounties the rules are a pointer, not a finder: low recall (≈7 %) and most current-code flags are by design
  or guarded in a way the rule misses. One plausible lead in ~150 commits' worth of files.
- Rule improvements this shows: recognise connect-time guards (a session/adapter named like `ssrf_safe`), treat an
  explicit operator opt-in for forwarded headers as accepted, add a TLS `verify=False` rule.
- Nothing was sent to any project.

## Second round, same evening: four more rules (owner: «давай улучшим и то и то»)

Added to `momus/momus/codescan/vulnetix_classes.py` (so the push gate and the MOMUS `code` target both run them):

- `VX-295-TLS-OFF` (Python and JS/TS): `verify=False`, `ssl=False`, `CERT_NONE`, `check_hostname = False`,
  unverified contexts; JS `rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED=0`, `strictSSL: false`. Not
  flagged: a flag from config, code under an `if` limited to a loopback peer, a function that compares the
  certificate itself (`getpeercert`, fingerprint).
- `VX-918-FETCH-UNCHECKED`: an entry point (route/tool decorator, or `_run`/`run`/`load`… of a `*Tool`/`*Loader`/
  `*Scraper` class) passes a URL-like parameter to an HTTP client with no address check in the function. JS: a
  request to `req.query/body/params` in a file with no check.
- `VX-918-REDIRECT-AFTER-CHECK`: the same address is checked (`is_safe_url`, `validate_url`, `ssrf`… — base64
  "urlsafe" helpers excluded) and then fetched with redirects followed (requests default, `follow_redirects=True`,
  `urlopen`).
- `VX-306-ROUTE-NO-AUTH`: a module creates its FastAPI/Flask/Starlette/Quart/Sanic app and serves POST/PUT/PATCH/
  DELETE routes on it with no authentication word anywhere. Routers mounted elsewhere are not judged.

Method: fix commits split in two by hash (`split.json`): rules written and tuned on the dev half (86 class-commit
pairs), measured on the held-out half (68) and on a separate npm set (169 advisories with fix commits, 168
class-commit pairs, `candidates_npm.json`, never used for tuning). `eval.py` = the scorer.

Honest note: the held-out half was scored twice. The first score used a version where three of the four new rules
were silent because of a bug (call names cut to their last part, found by the unit tests); the bug fix was mechanical,
not a change made to fit those advisories.

| Set | Old rules: confirmed by the fix | New rules |
|---|---:|---:|
| pip dev half (tuning) | 2 / 86 | 6 / 86 |
| pip held-out half | 3 / 68 | 3 / 68 |
| npm (not used for tuning) | 0 / 168 | 3 / 168 |
| **all** | **5 / 322 (1.6 %)** | **12 / 322 (3.7 %)** |

- The whole gain is `VX-295-TLS-OFF` (+4 pip dev, +3 npm). On the held-out pip half TLS fired on 2 pre-fix files but
  the fixes did not remove the flagged line, so they do not count.
- `VX-918-FETCH-UNCHECKED` and `VX-306-ROUTE-NO-AUTH` added no confirmed hit. A wider version of FETCH-UNCHECKED
  (any helper with a URL parameter in a module without checks) found 1 more pip case but flagged 38 places in our own
  repo, nearly all operator-configured URLs in scripts — dropped.
- `VX-918-REDIRECT-AFTER-CHECK` fires on 4 held-out units already caught by CHECK-THEN-CONNECT, and on PraisonAI's
  fixed `web_crawl` it points at a real leftover: the `urllib.urlopen` fallback still follows redirects unchecked.
- Noise on our own repo (main): 2 new findings, both `VX-306-ROUTE-NO-AUTH`: `relay-scout-fix/relay_scout/api.py`
  (image not deployed) and `scripts/local_image_server.py` (loopback by default, its doc suggests 0.0.0.0 for
  containers). 0 TLS, 0 fetch, 0 redirect findings.

What still misses: authorisation logic (who may do what — needs knowledge of the app's roles), SSRF where the URL
comes from stored data or headers (webhooks, OAuth `request_uri`, auth realms), DNS-rebinding fixes, and JS/TS beyond
TLS (the line rules found no SSRF or route case in 168 npm commits). Those need data-flow analysis (Semgrep/CodeQL
taint rules), not more patterns.
