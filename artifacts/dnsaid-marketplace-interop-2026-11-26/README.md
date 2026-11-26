# ModelMarket catalogue discovery through DNS-AID

On 2026-11-26, a loopback DNS server answered queries for the private `modelmarket.test` zone. The client received a test domain and a resolver address. Only `_index._agents` had an SVCB answer in each populated test case. Both SVCB records used ServiceMode, `alpn=h2`, and `modelmarket.dev` as TargetName. The HTTPS requests went to the live ModelMarket site with normal certificate validation. DNSSEC signatures on the test answers were validated separately against a local test trust anchor.

| Test domain | SVCB payload | Observed result with `dns-aid` 0.28.1 |
| --- | --- | --- |
| `control.modelmarket.test` | No record | No catalogue pointer |
| `draft.modelmarket.test` | `key65409` with the draft's two-byte length prefix followed by `agent-marketplace` | Resolved `/.well-known/ai-catalog.json`. It returned HTTP 200 with the separate ARD AI Catalog. |
| `sdk.modelmarket.test` | `key65409` with plain `agent-marketplace` bytes | Resolved `/.well-known/agent-marketplace`. That document returned HTTP 200 and its `catalogue_url` led to `/ai-market/v2/manifest`, also HTTP 200. |

The test decoder read the length-prefixed draft response and produced the same marketplace URL as the SDK did with its own encoding. Both wire variants used the SDK's private-use code point `65409`. The SDK's resolver configuration was redirected to the test DNS server. Its pointer decoder and URL checks ran unmodified. The probe followed the returned URL and the discovery document's `catalogue_url` over HTTPS. It checked that the manifest contained tools and that its signature block carried the key advertised by the discovery document. Cryptographic verification of the manifest signature was outside the scope of this run.

The run used Python 3.14.8, `dns-aid` 0.28.1, `dnspython` 2.9.2, `cryptography` 50.0.2, and `certifi` 2026.11.20. The published SDK wheel SHA-256 was `3055fd37d7d153f50f117210724e4daddc137e5268276563b2664fbe1d9c38fb`. The marketplace manifest in this run was generated at `2026-11-26T11:50:56Z` and had SHA-256 `5f1152a2bcec0d731250d5204534bc917540c79e231845561b298004d824d206`. Live document hashes will change on subsequent runs.

Run from this directory with a Python 3.14 virtual environment and access to loopback UDP and public HTTPS.

```sh
python -m pip install 'dns-aid==0.28.1' 'dnspython==2.9.2' 'cryptography==50.0.2' 'certifi==2026.11.20'
python -I -B probe.py
```

References

- [DNS-AID organizational index, section 3.2](https://datatracker.ietf.org/doc/html/draft-mozleywilliams-dawn-dnsaid-00#section-3.2)
- [Well-known SvcParam wire format, section 2.1](https://datatracker.ietf.org/doc/html/draft-mk-dnsop-svcb-well-known-01#section-2.1)
- [DNS-AID SDK 0.28.1 release](https://pypi.org/project/dns-aid/0.28.1/)
