# Outside signals checked on 2026-11-14

Each item was read at its source on 2026-11-14; nothing here is taken from a secondary summary.

## criba (cribalo.com): an outside honeypot's view of HISTOR

https://criba.cribalo.com/ — "AI traffic intelligence": a catalogue of bots that visit a public
research decoy MCP server and A2A agent (`mcp-senuelo`, nothing executes). Catalogue version
2026-11-11, licence CC BY-NC 4.0 (quoted here under attribution).

Entry, category *MCP indexers and directories*: "histor (modelmarket.dev) · histor.modelmarket.dev",
observed behaviour "server/discover, tools/list; UA says read-only".

What it shows: an independent operator saw HISTOR list tools and never call one, matching what
HISTOR's user agent declares. What it does not show: the catalogue gives no per-entry verdict on a
declared/observed mismatch (that is a per-visitor classifier output), so it is an observation, not
a certificate. Page headline that day: 235 distinct MCP clients since 8 November 2026; 16 of 741
MCP-speaking visitors (about 2.2%) ever called a tool.

## Agent-evidence work in the IETF and in research (no mention of our work)

- draft-nassar-agentproto-trail-00 (Cisco; 2 Nov 2026; agentproto list): witnessed Action Records;
  checkpoints in the TLOG-CHECKPOINT format, witness cosignatures as COSE countersignatures; no field
  for the tool definition in effect; Appendix A lists six related individual drafts.
- draft-munoz-wimse-authorization-evidence-01: signed pre-dispatch Permits anchored in SCITT.
- arXiv 2601.23132 (Polytechnique Montréal; v2 24 June 2026): MCP manifest signing with a Merkle log;
  operator and witnessing of the log not specified.

Drafted responses (not sent): PromoMaterials/outreach/presence-ietf-2026-11-14/.
