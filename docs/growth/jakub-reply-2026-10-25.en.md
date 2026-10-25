Thanks, Jakub — I checked a concrete example: [HISTOR change 17172](https://histor.modelmarket.dev/api/v1/changes/17172), for `@mapled/mcp` 0.21.5 → 0.21.6. Both snapshots contain 33 tools; only two descriptions change. One adds “carry on without asking” after approval on Mapled’s screen. The complete changed descriptions match the corresponding pinned npm archives.

Replaying those snapshots through published WARDEN 0.21.0 on Linux shows the changed words and the approval cue. The changed definitions require review, and reading the status leaves the original approval intact.

It also exposed a real mistake: both historical handshakes report `serverInfo.version=0.1.0`, and our review incorrectly suggested `@mapled/mcp@0.1.0` as a package pin. That reported version is not the npm artifact version. The verified newer artifact is [0.21.6](https://registry.npmjs.org/%40mapled%2Fmcp/0.21.6).

I’ve corrected that locally: review keeps the server-reported version separate from package identity and no longer constructs an npm pin from it. The correction is not released yet.

This checked review output and approval-state behavior using archived definitions. It wasn’t a fresh Mapled execution or a usability test of KyttoMCP.
