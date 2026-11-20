# WARDEN 0.33.0 — Open Terminal in OpenWebUI

```bash
npx -y @aimarket/warden@0.33.0 scan
```

The OpenWebUI Filter checks model calls to terminals configured under Integrations through the WARDEN gateway.
The full text is in the
[CHANGELOG](https://github.com/alexar76/warden/blob/v0.33.0/CHANGELOG.md).

In 0.32.0, native Open Terminal calls under Integrations bypassed the Filter. In 0.33.0 those calls go through the
existing WARDEN gateway with an Integrations connection: terminal responses feed the flow policy, and commands and
other potentially active operations are reviewed after outside text in `ask` or `deny` mode. Approval is tied to the
terminal connection as well as the chat, user and arguments. The External Tools setup still handles MCP and OpenAPI
connections.

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list
unchanged from 0.30.0. No scan verdict changes.
