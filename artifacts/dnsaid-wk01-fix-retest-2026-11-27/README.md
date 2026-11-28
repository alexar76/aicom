# DNS-AID well-known (key65409) fix retested — 2026-11-27

Ingmar Van Glabbeek filed our 2026-11-26 lab finding (../dnsaid-marketplace-interop-2026-11-26) as
dns-aid/dns-aid-core#317 and fixed it in #318 (branch fix/well-known-wk01-format, head
`feb7bda5078903ff98de7df1868850ed800a4850`, open at the time). We had offered to retest with a non-default catalogue
path and a malformed value.

`retest.py` runs dns-aid's own `resolve_catalog_pointer_detail` against a loopback DNS server for
`_index._agents.<case>.modelmarket.test` SVCB records, all targeting modelmarket.dev, whose discovery document is at
the non-default `/.well-known/agent-marketplace`. Only dns-aid's resolver is redirected; its decoding, validation and
URL checks run unmodified; warnings are captured with `structlog.testing.capture_logs`. Python 3.12, dnspython 2.9.2,
cryptography 50.0.2, certifi 2026.11.20.

| case | key65409 value | dns-aid 0.28.1 (PyPI) | #318 at feb7bda |
|---|---|---|---|
| control | no SVCB | no pointer | no pointer |
| wk01 | `00 11` + `agent-marketplace` | `ai-catalog.json`, silent | `agent-marketplace` |
| plain | `agent-marketplace` | `agent-marketplace` | `agent-marketplace` |
| wk01-two | entries `../escape`, `agent-marketplace` | `ai-catalog.json`, silent | `agent-marketplace` (first valid) |
| malformed | `00 40` + `agent-marketplace` (says 64, 17 follow) | `ai-catalog.json`, silent | record skipped, `catalog_pointer.well_known_malformed` |
| malformed-and-good | the malformed one (priority 1) + wk01 (priority 2) | `ai-catalog.json`, silent | `agent-marketplace`; warning only when the malformed RR comes first in the answer |

Outputs: `result-stock.txt` (exit 1: four FAILs, as the issue describes), `result-pr.txt` (exit 0). The discovery
document at the resolved URL and its catalogue were fetched over HTTPS: 320 tools, same signer key.

**Outside #318 (pre-existing):** the pointer code takes the first usable RR in the order the answer lists them and does
not sort by SvcPriority (RFC 9460: lower SvcPriority is preferred). Two valid RRs, priority 1 → agent-marketplace and
priority 2 → ai-catalog.json, 20 lookups each run: priority 1 chosen 13/20 and 10/20 in two runs. With 0.28.1 both
resolve to ai-catalog.json (the priority-1 wk01 value is not decoded), so that run says nothing about order.

Reproduce: `python -I -B retest.py` in a venv with `dns-aid` (0.28.1, or
`dns-aid @ git+https://github.com/dns-aid/dns-aid-core@feb7bda5078903ff98de7df1868850ed800a4850`) and the pins above.
