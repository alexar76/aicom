# Oracle Gateway startup regression

Date: 27 October 2026. Work is local to the alexar76 ecosystem in `aicom`.

The exact 0.3.1 wheel fails before `initialize`. The exact 0.3.2 wheel initializes, advertises
36 unique tools and exits cleanly in the same CPython 3.12.13 / MCP SDK 1.30.0 environment.
The current workspace's five Python package modules are byte-identical to that verified
0.3.2 wheel. The existing source fix is confirmed; no additional production-code fix or
version bump was needed.

## Cause and fix

In 0.3.1, `mcp_tool_surface.py` enables postponed annotations and defines aliases such as
`ValuesList` and `TrimFraction` inside `register_extended_tools`. The nested
`aggregate_values` function therefore has the string annotation `ValuesList`. FastMCP calls
`inspect.signature(..., eval_str=True)` using the function's global namespace; the registrar's
local alias is unavailable. This produces `NameError: ValuesList`, wrapped as FastMCP
`InvalidSignature`, before the process can answer the MCP handshake.

In 0.3.2, annotations in that registrar module are evaluated when functions are defined.
The actual `Annotated` type objects retain their constraints. The future import remains in
`stdio_server.py`, where the shared aliases are module globals and can be resolved normally.
Other 0.3.2 changes register additional oracle families and report the package version;
the expanded catalogue is separate from the annotation startup fix.

## Regression coverage

The new [process startup test](https://github.com/alexar76/aimarket-oracle-gateway/blob/main/tests/test_stdio_startup.py)
starts the workspace server with an explicit source path, Python `-I -B -u`, a PATH-only
environment and a temporary directory. It completes `initialize`, sends the initialized
notification, drains paginated `tools/list` and checks:

- The negotiated protocol, server identity and source version.
- The complete capability catalogue plus free discovery, without duplicate tool names.
- `aggregate_values` input constraints and registration of the separate family tools.
- Clean EOF shutdown with a single startup deadline and bounded terminate/kill fallback.

The child denies network connections and child processes through Python audit hooks. The
test has no dependency skip; MCP is already a required project dependency. It performs no
`tools/call`. All **48 plugin tests passed**, with zero failures and zero skips; see
[JUnit](pytest.xml).

The [negative control](negative-control.json) restores only the future import in a temporary
copy of current source. The same process startup harness then catches the original
`ValuesList → InvalidSignature` failure before initialize. Workspace source is unchanged,
and the temporary copy is removed. This isolates the cause independently of the other
0.3.2 changes. [Probe implementation](check_negative_control.py) · [stderr](negative-control-stderr.log).

## Release evidence

- [Fresh exact-wheel reproduction](releases/README.md).
- [Wheel replay verification](releases/verification.json), complete wire messages and stdout/stderr.
- [Acceptance checks and source hashes](acceptance.json).
- [Package testing instructions](https://github.com/alexar76/aimarket-oracle-gateway/blob/main/README.md#test-mcp-startup-locally).

No network requests, dependency installations, oracle calls, payments, deployment or GitHub
publication occurred. The existing clean SDK runtime was reused without modification.

For the startup regression in a normal development environment, run from the plugin directory:

```bash
python -m pytest tests/test_stdio_startup.py tests/test_stdio_schema.py -q
```

The local evidence replay uses the existing release runtime:

```bash
/private/tmp/pypi-mcp-releases-20261027/bin/python -I -B \
  docs/evidence/oracle-gateway-startup-regression-2026-10-27/check_negative_control.py
```

The historical upgrade brief still has no successful 0.3.1 toolset to compare. Its `unknown`
is now explained by a reproduced startup defect, while 0.3.2 startup is verified. Failed
observations were preserved rather than converted into empty successful tool lists.
