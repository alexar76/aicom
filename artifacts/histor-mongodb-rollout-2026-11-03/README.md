# MongoDB MCP checker on HISTOR

The checker is served by the HISTOR app at
[histor.modelmarket.dev/mongodb-mcp-read-only-tools.html](https://histor.modelmarket.dev/mongodb-mcp-read-only-tools.html).
The initial image rollout stopped at MOMUS run `20261103T033035` because the
sandbox host lacked the local `histor-node:22` image. nginx served the standalone
page during recovery. The image was rebuilt with Node `22.23.4` and verified
under gVisor. Signed MOMUS run `20261103T200001` passed, HISTOR was updated, and
nginx resumed proxying the checker and its assets to the app. The homepage
links to the checker, and the app sitemap lists it. The earlier sitemap URL
is still accessible.

IndexNow accepted the one new URL (HTTP 200). This confirms receipt.

On November 4, the existing [MCP capture comparison](https://modelmarket.dev/blog/two-public-records-of-mcp-tool-definitions-one-day-23190-servers-where-they-agree/) gained a contextual checker link tagged `from=capture-conditions-article`.
The checker now copies a Markdown review note with a link tagged `from=shared-review-note`.
The production report groups the two tags separately from search referrals.

## SKOPOS

In [SKOPOS](https://skopos.modelmarket.dev/app/) open Web Analytics → Sources.
Under Addresses select `histor.modelmarket.dev` and set Path contains to
`/mongodb-mcp-read-only-tools.html`. Keep the bot and service traffic filters
enabled. Use Journal to inspect the underlying requests.

The repeatable aggregate report can be run from this workspace:

```sh
bash artifacts/histor-mongodb-rollout-2026-11-03/skopos-search.sh
```

It queries production SKOPOS in read-only mode and groups eligible requests by
UTC date and referrer. It excludes marked probes, common bot user agents and
unsuccessful responses, and groups common paid tags separately. Counts are
requests with observable attribution. Search visits with a stripped referrer
appear as unattributed; crawler visits and unique people cannot be inferred
with certainty from HTTP headers.

## Hugging Face dataset entry

The [HISTOR dataset card](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions)
links to the package search with `from=hf-dataset`. Revision
`08c5d40772ca66213928f6b43e05792139aa5d75` changes only the card. The scheduled
Hugging Face uploader adds the same link to its copy of each later snapshot card.

Run the dedicated SKOPOS report from the workspace:

```sh
bash artifacts/histor-mongodb-rollout-2026-11-03/skopos-search.sh hf-dataset
```

It separates tagged entry requests from the subset with an observed Hugging
Face referrer. Package history opens inside the browser app, so these counts
describe entry requests.

## PyPI package entry

The HISTOR 0.6.1 distribution description links to package search with
`from=pypi-histor`. To read the dedicated SKOPOS report:

```sh
bash artifacts/histor-mongodb-rollout-2026-11-03/skopos-search.sh pypi-histor
```

It separates all tagged entry requests from those with an observed PyPI
referrer. It excludes probes and reports requests rather than unique visitors.
