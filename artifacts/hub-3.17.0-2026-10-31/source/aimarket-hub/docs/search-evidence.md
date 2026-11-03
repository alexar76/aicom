# Evidence in web search

The terminal displays `/ai-market/v2/search` catalogue `matches` and `observed`
offers in separate sections. Only catalogue matches can use the hub's existing
invocation flow. Observed rows link to a same-origin HTTPS seller endpoint and
show the payment recipient and last observation time. They never become hub
invocation targets. An observed-only response is still a search result.

Catalogue matches carry an additive `evidence` object:

- `kind`: `signed_catalogue`, `local_catalogue`, or `catalogue_unrecorded`.
- `scope`: `catalogue`. This describes advertised terms, not delivery.
- `signer`, `signer_public_key`: the source catalogue origin and the key actually
  used to verify its manifest. These are not the tool's declared receipt key.
- `checked_at`: UTC time of the successful signature/freshness check preceding
  indexing; `checked_by` identifies the observing hub.

Migration 064 adds a per-capability evidence record. The crawler supplies it only
after validating the manifest and verifying its signature and freshness policy.
Tool-supplied evidence fields are ignored. Later failed crawls do not advance an
existing row's verification time, even if the peer's `last_crawl` changes.

Existing rows stay `catalogue_unrecorded` until a successful refresh. Local
catalogue rows are hub records, not an assertion that a seller signed a manifest.
Missing signer/time fields are displayed as not recorded. No data migration
fabricates historical checks. Observed rows use `observed_by` / `observed_at` and
explicitly state that the seller did not sign the listing.

The UI includes English, Russian, Spanish, French and Chinese labels. None of
these labels proves delivery or changes existing payment/admission rules.

Version 3.17.0 bundles the authored terminal page, operator/plugin pages and UI
dictionaries in the wheel. Source/Docker deployments use their authored files;
pip installations resolve the bundled copies. Rebuilding from the sdist retains
the same UI inputs. Installing the new hub applies migration 064 on startup.
