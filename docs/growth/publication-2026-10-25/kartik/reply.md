# Продолжение ответа Kartik — подготовлено, не отправлено

Ветка: https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh#comment-3i31k

## Текст ответа

Following up with the fresh-install count you asked for: we rechecked the reconstructed 292-package cohort on 24 October, without adding our own `mcp<2` constraint.

Fourteen answered `initialize` and `tools/list`: twelve had newer releases, while two worked at the same version after we installed their declared MCP extra. Eleven of the twelve newer-release successes have a matching fresh old-version control that still fails; the remaining old release is no longer available from PyPI.

Seven confirmed pairs add an upper bound, three move to SDK 2, and one changes an already bounded range with a Pydantic-related old failure. Another 276 still fail on imports, APIs or dependencies; two need real authentication or a prepared project index that our synthetic environment did not provide.

I also need to correct my earlier reply: not all 292 were proven MCP 2 failures. Our old classifier included missing extras and MCP 1/Pydantic errors because it matched the FastMCP path anywhere in a traceback.

The follow-up explains the controls and limitations: https://dev.to/alexar76/we-rechecked-292-failing-mcp-packages-12-newer-releases-now-list-tools-p72

Disclosure: I maintain HISTOR and WARDEN. AI agents prepared the investigation, analysis and this reply under the project owner’s direction. Listing tools does not establish safety or authenticated functionality.
