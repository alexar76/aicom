# WARDEN 0.39.0 — a link through a URL shortener in a tool definition is reported

```bash
npm install -g @aimarket/warden@0.39.0
```

Static scan ruleset 24 adds one advisory rule, `TOOL_DEF_SHORT_LINK`. When a tool's description, schema, title or
other prose links through a URL shortener (bit.ly, tinyurl.com, t.co, is.gd, cutt.ly and others: the whole host,
optionally under `www.`, followed by a path), the scan reports it at `low`. It never blocks. Shorteners are also
used honestly, but the name hides where the link leads, so it is the address to read before an agent follows it.
No blocking rule changed, so nothing that ruleset 23 blocked or passed changes verdict. The ruleset digest is new
(`sha256-Zopy0S98…`), so pinned scan results are only comparable within one ruleset.

The idea came from a question under our HISTOR article on DEV.to: on a sample of 2,000 recorded tool-definition
changes, filtering out each server's own domain and the code registries still left 34 of the 58 changes that named a
new address, while a list of shorteners matched exactly one. HISTOR's change records list the same hosts apart
(`newShortLinks`).

The full text is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.39.0/CHANGELOG.md).
