# aimarket-hub 3.17.0 release

The primary server at https://modelmarket.dev runs the verified 3.17.0 wheel, including the terminal and five UI translations. Module and distribution versions agree. THEMIS was recreated in the new hub network namespace and passed health checks. All 280 database rows, the signing identity and 15 plugins were preserved. The previous container and a consistent database backup remain on the server. No GitHub writes were performed.

3841 unique tests passed, 20 skipped. The initial full run hit localhost sandbox and select file-descriptor limits; all 37 affected cases passed in the focused unrestricted rerun. An offline candidate test migrated a copy of the real database, then exercised the bundled UI and dictionaries. Archives passed strict Twine metadata and distribution secret checks.

Live browser QA confirmed signed catalogue metadata, an observed-only result, mixed catalogue/observed groups and a language switch retaining observed. The observed QA used our own origin, an explicit deployment self-test name and an unpaid 402 probe. Its temporary record was removed; no third-party seller or payment was created. See qa/ and public-after.json.

## PyPI pending

PyPI still serves 3.16.5. The exact 3.17.0 wheel and sdist in dist/ are ready, but no existing alexar76 project token was available in the environment, standard PyPI settings, standard keyring entries or server settings. The user was asked for a secure file path; the token itself must not be pasted into chat.

After a token is available, use release-venv/bin/python publish_verified.py --token-file /absolute/path/to/existing/token from this directory. It checks all 567 source hashes and both archive hashes, reruns metadata/secret checks, uploads only missing matching artifacts to the official PyPI endpoint, and verifies the public hashes. Credentials stay in process memory and are not written to evidence.

See release-status.json, artifact-hashes.json, rollout.json, backup.json and test-summary.json for receipts.
