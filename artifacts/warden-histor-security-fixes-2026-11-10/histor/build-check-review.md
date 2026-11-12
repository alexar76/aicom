# Independent review of Histor scanner pin/build checks

Reviewed final package/lock/vendor metadata, verifier/tests, Dockerfile, Makefile and local CI YAML changes. No remaining actionable finding in the reviewed change.

The initial verifier accepted a changed installed package.json exports map because MOMUS buildDigest covers dist/*.js. A disposable reproduction is retained in `build-check-review-reproducer.json` as historical pre-fix evidence. The parent added a package.json SHA256 check and a module-routing mutation regression. Independently verified that metadata packageJsonSha256 matches bytes extracted directly from the pinned0.25.0 npm archive. The final verifier rejects the mutation through the new regression test.

`npm --prefix histor/scanner run check:build` passed; all five verifier tests passed. Test cases cover accepted artifact, older installed version, changed dist bytes, changed module routing, and modified archive. Makefile test and both local CI YAML paths now invoke these tests. No workflow was dispatched or published.

Dockerfile copies manifest, lock, vendor archive/metadata, verifier and its imported quality helper before the bundled npm ci/check step. The with-live-scanner target copies node_modules from the explicitly selected accepted-scanner image and verifies it against the same local version, package metadata digest and accepted dist digest before dropping root. An empty/default copied scanner fails closed. The default bundled target keeps the reproducible local archive path. No Docker execution was performed by this review subtask; the parent owns any build evidence.

The metadata sourceCommit and registryGitHead remain separate fields. The offline verifier establishes consistency with the pinned accepted artifact; it does not itself refresh the MOMUS receipt, prove arbitrary production state or authorize future rollback.
