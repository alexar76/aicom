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
