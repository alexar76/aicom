# PR #15 re-review of c79a3b7 (2026-11-24) — SUPERSEDED: owner chose to merge as is; the posted text is in colleague task §161, the three edges are fixed by us after the merge

Checked read-only from public GitHub (pull/15/head = c79a3b75e6748fab88456c0f527de1cc3395c121):
- test file and ci.yml step are byte-identical to warden-pr15-regression-tests-ci.patch (main 03328d60d) applied
  on 3b41da80;
- `node --test integrations/canari/test/verify-attestation.test.mjs`: 31/31 pass, Node 22.22.1;
- all four earlier findings fixed (binding inside + outside the signature, expiry required, types checked, missing
  payloadType blocks, inherited/unknown verdict blocks);
- GitHub CI runs (CI, CI macOS) are `action_required`: a maintainer must approve the workflow run;
- probes (ephemeral key, synthetic statements): `now: NaN` with an expired statement → allow; `expires_at: "2099"` →
  allow; two subjects with the second digest different → allow (only subject[0] is read).

## Text

Thanks, checked c79a3b7. The test file and the CI step are byte-identical to the patch, and 31 of 31 pass here on Node 22.22.1. All four points from the review are addressed: the digest is bound inside the signature (in-toto subject against artifact_sha256) and to the caller's expectedArtifactSha256, a missing, unparseable or past expires_at blocks, the three types are checked and a missing payloadType blocks instead of throwing, and an inherited or unknown verdict blocks.

Both judgement calls are fine as they are. The sha256: prefix normalises to the same 64 hex, and one allowed payload type in one set is what we want.

Three small things I found by probing, none of them reachable with a well-formed Canari bundle and a sane caller, but cheap to close:

- `opts.now` is used as given. With `now: NaN`, `expiry <= now` is false, so an expired statement is allowed. A `Number.isFinite(now)` check that blocks would close it.
- Only `subject[0]` is compared. A statement with two subjects whose second digest differs is still allowed. Requiring exactly one subject, or requiring every subject to carry the same sha256, would make the binding unambiguous.
- `Date.parse` accepts loose forms such as `"2099"`. Requiring an RFC 3339 timestamp (date, time and zone) for `expires_at` would match the form in both fixtures (`2026-12-07T15:34:22Z`).

The CI runs on this PR are waiting for a maintainer to approve the workflow, which we will do on our side.
