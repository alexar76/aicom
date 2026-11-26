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

## Repeat in Ingmar's Instruqt lab

On 2026-11-26 at about 12:10 UTC, the test ran on the workstation in step 5 of the IETF 127 Instruqt track. The lab includes stock `dns-aid` 0.28.1, its locally patched `dns-aid-next` 0.28.1, and the common-parameters client `dawnlab` 0.1.0. The lab and both DNS-AID clients map `well-known` to private-use SvcParamKey `65409`. [Instruqt track](https://play.instruqt.com/infoblox/invite/amv3mzygm6kq)

The lab's documented signing and registrar commands enabled DNSSEC on its private `builder.test` zone. An add-only DDNS update published two priority-1 `_index._agents` SVCB records pointing to `modelmarket.dev` with `alpn=h2`. The control name had no record. The lab's validating resolver reported `AD=True` for both test records. The SDK calls received just the domain name and used the installed resolver configuration. The probe made the HTTPS requests after obtaining the URLs from the SDK.

| Test domain | `well-known` SvcParamValue | Both installed SDK pointer resolvers | `dawnlab.unicast.resolve_owner` |
| --- | --- | --- | --- |
| `mmwk1126-control.builder.test` | No record | No pointer | No SVCB |
| `mmwk1126-len.builder.test` | `00 11` followed by `agent-marketplace` | `/.well-known/ai-catalog.json`, HTTP 200 with the separate ARD AI Catalog | Preserved the prefix as the literal presentation escapes `\000\017` |
| `mmwk1126-plain.builder.test` | `agent-marketplace` bytes | `/.well-known/agent-marketplace`, HTTP 200. `catalogue_url` led to `/ai-market/v2/manifest`, HTTP 200 with tools. | `agent-marketplace` |

`dawnlab` was tested with the resolver used by `dawn compare`, which takes the explicit SVCB owner and returns parsed parameters. The domain-only lookup and HTTPS follow-through were tested with the SDKs. The stock lab module `dns_aid/core/catalog_pointer.py` matched the public 0.28.1 wheel byte for byte. The patched module differed, with the same result in all three cases.

| Installed file | SHA-256 |
| --- | --- |
| Stock `dns_aid/core/catalog_pointer.py` | `2687697ab9e818aefe60cf46ea7a1335c073d107184bcbe0877fa68c4507fe7a` |
| Patched `dns_aid/core/catalog_pointer.py` | `0ebc2e1b4b3af2d10650a86fcf76e0e5f5e958ed9a34a35798eaf0c457351f06` |
| `dawnlab/keys.py` | `41ca6cba1b861c232b430b798fe5556565bdcfd55625fc42879d9c067fde5325` |
| `dawnlab/unicast.py` | `10d2179aa484b64c929343d59cd0584f0dbef88bca1af32082f08b6aff93f8e9` |

In a fresh lab session at step 5, save `lab_probe.py` on the workstation and run the following commands from its directory.

```sh
lab identity sign builder.test
lab registrar ds-add builder.test
/opt/dns-aid-venv/bin/python lab_probe.py add
/opt/dawn-venv/bin/python lab_probe.py dawn
/opt/dns-aid-venv/bin/python lab_probe.py sdk
/opt/dns-aid-next-venv/bin/python lab_probe.py sdk
```
