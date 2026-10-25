Fourteen of the 292 PyPI MCP packages we rechecked answered `tools/list`. Twelve had newer releases. Two worked at the same version after we installed their declared MCP extra. Another 276 failed on imports, APIs or installation dependencies; two needed prerequisites our synthetic environment did not provide.

We did not add our old `mcp<2` workaround. We installed the versions published by the packages and respected their own dependency constraints.

**AI disclosure:** AI agents prepared the investigation code, analysis and this article under the project owner’s direction. I maintain HISTOR and WARDEN in the alexar76/AICOM ecosystem. This is a follow-up to our own measurements, not an independent audit. The version snapshot and runs below are from **24 October 2026**.

## The question was whether the packages recovered

In [our earlier package census](https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh), we described 292 PyPI packages as broken by MCP SDK 2. [Kartik asked](https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh#comment-3i31k) whether we would track how many recovered once maintainers added an upper bound on `mcp`.

That deserved a follow-up with fresh installations. It also required correcting our original classification: a traceback containing `mcp.server.fastmcp` does not establish that SDK 2 caused the failure.

We reconstructed the historical 292-package cohort, fetched each package's latest-version metadata on 24 October at 20:02–20:03 UTC, and ran fresh installations between 20:13 and 21:19 UTC. Where a new package version existed, we also installed the old version afresh under matching conditions.

The outcome was:

| Result | Packages |
| --- | ---: |
| Newer version lists tools; fresh old-version control fails under matching conditions | **11** |
| Newer version lists tools; old version is no longer available for a control | **1** |
| Same version lists tools with its declared MCP extra | **2** |
| Import/API or installation dependency failure | **276** |
| Authentication or project-index prerequisite not supplied | **2** |
| Total | **292** |

Success here means that `initialize` and `tools/list` answered. It does not establish safety, successful business operations or a working integration with a real account.

## Twelve newer releases now answer, with eleven confirmed pairs

Thirty packages had newer releases than their historical version. Twelve answered `tools/list`, seventeen still failed on imports or APIs, and one reached a request for real authentication.

For eleven of the twelve successes, a fresh installation of the old version failed on the same host, image, runtime, observer and launch configuration. The twelfth old release could not be installed because PyPI no longer had it.

| Package | Historical → checked version | Observed dependency change or qualification |
| --- | --- | --- |
| [apillow-mcp](https://pypi.org/project/apillow-mcp/0.1.4/) | 0.1.3 → 0.1.4 | Adds a package-owned `mcp<2` constraint. |
| [imperal-mcp](https://pypi.org/project/imperal-mcp/0.6.0/) | 0.5.3 → 0.6.0 | Adds an upper bound on MCP. |
| [kratos-mcp-server](https://pypi.org/project/kratos-mcp-server/0.10.0/) | 0.9.0 → 0.10.0 | Declares `mcp>=1.30.0,<2`. |
| [mcp-server-openfda](https://pypi.org/project/mcp-server-openfda/0.2.1/) | 0.2.0 → 0.2.1 | Declares `mcp[cli]<2`. |
| [screaming-frog-mcp](https://pypi.org/project/screaming-frog-mcp/0.4.3/) | 0.4.1 → 0.4.3 | Declares `mcp>=1.30.0,<2`. |
| [sprout-social-mcp](https://pypi.org/project/sprout-social-mcp/0.2.0/) | 0.1.3 → 0.2.0 | Declares `mcp[cli]<2`. |
| [youtube-studio-mcp](https://pypi.org/project/youtube-studio-mcp/0.3.1/) | 0.3.0 → 0.3.1 | Declares `mcp>=1.30.0,<2`. |
| [scrapling-fetch-mcp](https://pypi.org/project/scrapling-fetch-mcp/0.2.6/) | 0.2.4 → 0.2.6 | Moves to `mcp>=2.0.0`. |
| [sraverify-mcp](https://pypi.org/project/sraverify-mcp/0.1.1/) | 0.0.2 → 0.1.1 | Moves to `mcp[cli]>=2.3,<3`. |
| [stremio-mcp](https://pypi.org/project/stremio-mcp/0.4.1/) | 0.3.0 → 0.4.1 | Moves to `mcp>=2,<3`. |
| [gandr-mcp](https://pypi.org/project/gandr-mcp/0.2.0/) | 0.1.8 → 0.2.0 | Changes its bounded MCP 1 range from `>=1.2,<1.3` to `>=1.9,<2`; old control fails on a private Pydantic import. |
| [aleth-mcp](https://pypi.org/project/aleth-mcp/0.3.1/) | 0.2.0 → 0.3.1 | Current release answers with `mcp>=1,<2`; old 0.2.0 is unavailable, so no confirmed pair. |

Seven confirmed pairs therefore involve adding an upper bound. Three newer packages support SDK 2. One pair involves an already bounded dependency range and a Pydantic-related old failure. These are package counts, not counts of independent maintainers.

The comparisons show release-associated recovery under current fresh dependency resolution. They do not isolate one changed line as the sole cause or establish that our previous article prompted a fix.

## Two successes were corrections to our installation profile

At unchanged versions, `ifcopenshell-mcp 0.9.0` listed 25 tools and `webresearcher-mcp-server 0.1.1` listed four after installation with their author-declared `[mcp]` extra.

The plain installations do not install the SDK. We retained a plain-install control on the same host and image for each extra test. Only the declared installation extra changed within those comparisons.

These are useful operational successes, but calling them two new maintainer fixes would be wrong. Our old workaround could both install a missing dependency and restrict its version; a successful retry with `mcp<2` did not distinguish those effects.

## What still failed

The 276 software or dependency failures break down as follows:

| Observed failure | Packages |
| --- | ---: |
| Explicit MCP 2 diagnostic for the removed FastMCP import path | 230 |
| Missing low-level `Server` decorators | 34 |
| Missing `FastMCP` export from `mcp.server` | 1 |
| Private Pydantic import `eval_type_backport` | 10 |
| Unavailable exact dependency `pglast==7.2.0` | 1 |

The SDK's [official migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md) describes the FastMCP import-path and low-level `Server` handler changes. The failure categories above come from each saved run's diagnostic, rather than inferring the cause from the presence of a path anywhere in a traceback.

The `pglast` case deserves a distinction. `postgres-mcp 0.3.0` could not install its required `pglast==7.2.0`. We separately checked the exact-version API and complete PyPI release index: neither that version nor its PEP 440 equivalent `7.2` was present. That is stronger evidence than pip merely failing to find a compatible wheel. It is still an observation at this dated snapshot.

We left two packages outside the software-failure count. `d1-mcp-mint 1.0.7` initialized but needed a real service access token to list tools. `codemap-mcp 0.2.0`, after its `[server]` extra, required a prepared project graph database. We did not provide either prerequisite and cannot classify them as fully working or broken from this test.

## The correction to our earlier claim

Our earlier wording that all 292 were MCP 2 breakages was too broad.

The historical classifier matched `mcp.server.fastmcp` anywhere in a traceback. It included missing optional SDK installations and MCP 1/Pydantic failures. Some packages already had an upper bound; one pinned `mcp==1.14.1`.

The 292 remain a useful historical cohort to follow. They are not 292 independently established instances of the same cause. That correction also applies to my earlier reply to Kartik.

## What this rerun establishes

Installations and package execution ran on **two Linux servers in gVisor**, using Python 3.12. Installations used fresh work directories, wheels only and no pip cache. Every main latest-version and old-version request supplied `pins: []`; the unavailable old release failed before installation. Author-owned constraints were respected. Both hosts' images were recorded; confirmed old/new pairs used the same image within the pair.

Dependency fetching had registry access. Program execution used an internal trap network with synthetic replies and no internet route. The standard observer can also try canary `tools/call` requests; those behavioral results are outside this availability count. Extra-installation follow-ups had networking disabled and did not call tools. No real account credentials were supplied. The full exercise contains **342 observation attempts**, not 342 different packages.

There is an important historical limit. We did not find a separate frozen name manifest for the original article. We reconstructed this cohort from persisted observations before 14 October UTC and obtained the same 292 packages at two cutoff points. Reconstructing the broader census produced 12,940 targets / 12,938 endpoints, so this follow-up does **not** claim to reproduce the original full denominator of 12,915 or its complete old retry totals.

The answer to Kartik is now concrete: twelve newer releases list tools, eleven have a matching failing old-version control, and seven of those confirmed pairs add an upper bound. Most of the historical cohort still fails in this environment. Two apparent recoveries also taught us that installation profiles belong in the measurement, alongside version numbers.
