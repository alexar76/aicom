# WARDEN 0.39.2 release candidate

The source commit is `1cb76428f` on local `main`. In 0.39.1 the verifier was present in the source tree, but the build did not copy it to `dist` and the npm allowlist did not include it. The tarball now contains `dist/canari.js`, `dist/canari.d.ts` and the integration guide. The verifier is included in the JavaScript build digest used by MOMUS.

- Archive `aimarket-warden-0.39.2.tgz` contains 516 files. The SHA-256 is recorded in [SHA256SUMS](SHA256SUMS).
- The archive was installed offline into an empty consumer directory. The installed package imported as `@aimarket/warden/canari`, accepted a signed fixture with a matching digest, and blocked it with a different digest. The TypeScript consumer resolved the declarations. All 37 adapter tests passed.
- The build, package typecheck and release version consistency checks passed. The final run passed 2,246 tests across 92 files and the local flow regression gate. This run enabled loopback for test servers and omitted the Codex directory from the test process's `PATH`, which had triggered the protected-settings guard in an existing test. The static scanner reported ruleset 24 with digest `sha256-Zopy0S98Rea7ozLSCa82BNsFO1ttse9ck6b/B4LrD9A=`.
- The MOMUS build digest is `248ae5f9ba947f6ce617c33796badaf5cbc45384ebcb4f5471e5dc45de066e24`. The published quality check returned `Quality cycle has not passed`. npm still reports 0.39.1 as latest. The archive remains a local candidate.
