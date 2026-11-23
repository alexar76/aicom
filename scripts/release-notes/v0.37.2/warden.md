# WARDEN 0.37.2 — tool-set digests at depth

```bash
npm install -g @aimarket/warden@0.37.2
```

The contract and extras digests of a tool set (`mcp-tool-set-digest/1`, MTL/1) now follow the depth rule the
specification adopted on 22 November 2026 (section 12): every level up to 512, counting the tools array as level 1,
is digested, and past that the digest that would cover the value is `TSD-DEPTH` (`MTL-SUBJ-005` for the MTL digest)
while the other one is still computed. Until this release WARDEN gave no digest for anything nested deeper than 64
levels, the bound of its AWR canonicaliser, and reported the extras case as `TSD-TEXT`. AWR documents keep that bound.

`wrap` still refuses a tool set that has no contract digest. Scan verdicts, rulesets (23), the malware list, masking
and the flow guard rules are unchanged.

The specification: [SPEC.md, section 12](https://github.com/alexar76/mcp-tool-set-digest/blob/main/SPEC.md). The full
text is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.37.2/CHANGELOG.md).
