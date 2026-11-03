# Capture conditions beside a tool-definition digest

Status: proposal, 31 October 2026. Not part of MTL/1 yet. Written for any public record of MCP tool
definitions (HISTOR, heldfast, AgentAvow, rugsnare) and for profiles that define a shared digest.

## 1. Problem

Two records that read the same server on the same day can publish different digests for the same
tool, and neither is wrong. On 26 October 2026 HISTOR and heldfast both read 23,190 servers. With
every field present, 315,605 of 318,389 tools (99.1%) had the same heldfast fingerprint. Of the
444 servers that differed, 78 differed only because of how they were read:

| servers | capture difference |
|---:|---|
| 24 | npm package run with network by one reader and without by the other |
| 24 | the definition contains the reader's environment: home directory, placeholder credentials, a date or a random id |
| 15 | the server sent no `outputSchema`/`title` to one reader: a 2024-11-05 handshake, or no `MCP-Protocol-Version` header after a newer one |
| 10 | one reader stopped at the first `tools/list` page (976 tools missing across 11 paginated servers) |
| 5 | same package version, offline on both sides: one negotiated 2026-07-28 against 2025-06-18, four list a different number of tools from run to run |

Another 218 ran different package versions, and 148 were read at different moments around an edit
or a failed read.

The data, scripts and pinned inputs are in `research-data/interop-digests-2026-10-31`. A digest
alone cannot say which of these happened. A consumer that compares two digests reads every capture
difference as drift.

## 2. The block

A record that publishes a tool or tool-set digest SHOULD publish this object beside it. Members a
reader does not know are omitted, never guessed.

```json
"capture": {
  "observedAt": "2026-10-26T13:34:32Z",
  "transport": "streamable-http",
  "protocol": {"requested": "2025-06-18", "negotiated": "2025-11-25", "versionHeader": true},
  "pages": {"read": 3, "complete": true},
  "clientCapabilities": [],
  "launch": {
    "package": "npm:example-mcp",
    "resolvedVersion": "1.2.3",
    "args": ["--stdio"],
    "envNames": ["EXAMPLE_API_KEY"],
    "envValues": "placeholder",
    "network": "none",
    "home": "/home/reader"
  }
}
```

- `protocol.requested` is the version the reader asked for. `negotiated` is the version the server
  answered. `versionHeader` is true when every request after the handshake carried
  `MCP-Protocol-Version: <negotiated>` (Streamable HTTP). Without the header a server assumes
  2025-03-26 and may drop newer members.
- `pages.complete` is true only when `tools/list` was followed until no `nextCursor` was returned.
- `clientCapabilities` lists the capability names the reader declared (`sampling`, `roots`,
  `elicitation`…). Some servers register tools only for clients that declare them.
- `launch` applies to servers the reader started. `envValues` is `none`, `placeholder` or
  `real`; values are never published. `network` is `none` or `full`. `home` is the home directory
  the process saw, because definitions quote it.

## 3. Rules

1. A reader MUST follow `nextCursor`. A digest over an incomplete list MUST carry
   `"complete": false` and MUST NOT be compared with a complete one.
2. Over Streamable HTTP a reader SHOULD send `MCP-Protocol-Version` on every request after
   `initialize`, and record whether it did.
3. Two digests of the same format are comparable as the same server's definition when
   `pages.complete` is true for both, `protocol.negotiated` and `versionHeader` are equal, and,
   for launched servers, `resolvedVersion`, `args`, `envNames`, `envValues` and `network` are
   equal. When they are not, a difference is reported as a capture difference, not as drift.
4. A record SHOULD flag a definition that contains its own `home` or one of its placeholder
   values. Such a digest identifies the reader as much as the server, and no other reader will
   reproduce it.

## 4. What this does not settle

The field set of a shared digest and how missing and empty members are written (heldfast writes a
missing description as `""` and drops an empty `outputSchema`; AgentAvow drops a missing
description and keeps `{}`) are separate decisions for the profile that defines the digest. The
capture block applies whichever digest is chosen.
