# WARDEN 0.38.1 — Open WebUI setup upgrades the gateway, and Open Terminal file writes to the user's home are recognised

```bash
npm install -g @aimarket/warden@0.38.1
```

Re-running Open WebUI `setup` now upgrades the default gateway package with the Filter, including installs that
saved an older default gateway in `setup.json`; `check` flags mismatched versions, and custom `--package` overrides
are kept. Native Open Terminal `write_file` and `replace_file_content` are recognised when `path` in
`destinationArgs` is the exact path relative to the authenticated user's default home and appears in the user's
own message. The gateway still checks the file payload, and changed shell arguments still need authorisation.

The repository also has a new integration, `integrations/canari/verify-attestation.mjs`: given a signed Canari
attestation, its public key and the SHA-256 of the artifact about to be installed, it returns allow, review or block
in WARDEN's vocabulary, and refuses anything it cannot bind to those bytes. Thanks to @lanbass869-cell, who wrote it
in [#15](https://github.com/alexar76/warden/pull/15). It is not part of the npm package; run its tests with
`bash integrations/canari/run-tests.sh`.

The full text is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.38.1/CHANGELOG.md).
