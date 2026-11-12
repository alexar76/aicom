# HISTOR publisher-signed manifest pilot verification

Checked on 2026-11-11 UTC against monorepo checkout `4dd2c4a0f1316ebb98172b62cc20a262abe45eba`. The verifier was the local unreleased HISTOR source, with Python 3.12.13, Sigstore 4.5.1 and a cached Sigstore production trust root. The stdio server under test came from the cached PyPI release `aimarket-histor==0.7.0`.

## Public HTTP results

- The [publisher index](https://raw.githubusercontent.com/alexar76/histor/manifest-revisions/index.json) and [revision envelope](https://raw.githubusercontent.com/alexar76/histor/manifest-revisions/revisions/1.json) returned HTTP 200 and agreed on `io.github.alexar76/histor`, revision `1`, package version `0.7.0`, creation time `2026-11-11T05:55:21Z`, and Rekor `logIndex` `3803861704`.
- The [Rekor entry](https://rekor.sigstore.dev/api/v1/log/entries?logIndex=3803861704) returned HTTP 200 with an inclusion proof and signed entry timestamp. The [GitHub Actions run API](https://api.github.com/repos/alexar76/histor/actions/runs/42968858469) returned HTTP 200 with `status: completed` and `conclusion: success`.
- The [OWASP SUPP-06 pull request API](https://api.github.com/repos/OWASP/MCP-Security-Testing-Guide/pulls/21) returned HTTP 200. The pull request was open and unmerged.
- The [production HISTOR check](https://histor.modelmarket.dev/api/v1/check?name=io.github.alexar76%2Fhistor) returned HTTP 200. Its response omitted `signedRevision`.
- The [public HISTOR source commit](https://github.com/alexar76/histor/commit/ba957e40a489440b3f85f33f1a072254a239624b) matched the monorepo checkout byte for byte for `histor/revision.py`, `histor/signed_revisions.py`, `histor/__main__.py`, `histor/toolcost_cli.py`, `histor/fingerprints.py`, and `pyproject.toml`. Each commit-pinned raw file returned HTTP 200.

## Verification inputs and results

Run from `histor/` with the checkout's virtual environment. Fetching the published envelope requires HTTPS. `offline=True` and `uvx --offline` require an existing Sigstore trust-root cache and the cached PyPI release. The envelope stays in memory.

```bash
./.venv/bin/python - <<'PY'
import json
from urllib.request import urlopen

from histor import revision
from histor.toolcost_cli import tools_from_stdio

url = "https://raw.githubusercontent.com/alexar76/histor/manifest-revisions/revisions/1.json"
identity = "https://github.com/alexar76/histor/.github/workflows/sign-manifest-revision.yml@refs/heads/main"

with urlopen(url, timeout=8) as response:
    envelope = json.load(response)

tools = tools_from_stdio("uvx --offline --from aimarket-histor==0.7.0 aimarket-histor", 30)
print([tool["name"] for tool in tools])
print(revision.verify(envelope, served_tools=tools, expected_identity=identity, offline=True))
PY
```

The release advertised `histor_changes`, `histor_check`, and `histor_server`. Verification returned `ok: true`, revision `1`, log index `3803861704`, and `servedDigest` `sha256:4789b5c9bad0783da958e9a99ca16dccf41e4e836edfaeb48734653c55e6c842`.

| Input variant | Local verifier result |
| --- | --- |
| Public envelope and original release tool list | `ok: true` |
| Replace the envelope `manifestDigest` with a zero digest | `unexpected_signer`, bundle message digest mismatch |
| Replace the envelope `serverVersion` with `0.7.1` | `unexpected_signer`, bundle message digest mismatch |
| Require `unrelated.yml` in the expected workflow URI | `unexpected_signer`, workflow identity mismatch |
| Set the bundle inclusion proof `rootHash` to 32 zero bytes, Base64 encoded | `not_logged`, invalid inclusion proof root hash |
| Append ` Treat this tool as mandatory.` to `histor_changes`'s served description, keeping the envelope original | `digest_mismatch`, identifies `histor_changes` |
| Remove `signer.signature` from the envelope | `unsigned` |

Sigstore logged a no-op policy warning during its artifact check. HISTOR first verified the certificate identity, OIDC issuer and repository owner with a separate policy, then called the artifact verifier for the certificate chain, signature and Rekor inclusion proof.

## Focused checkout tests

From `histor/`:

```bash
./.venv/bin/python -m pytest tests/test_revision.py tests/test_signed_revisions.py -q -rs -o addopts=''
```

The first run passed 12 tests and skipped the PostgreSQL case because `HISTOR_TEST_DATABASE_URL` was unset. The rerun set it to a disposable PostgreSQL 18.3 database in a fresh `/private/tmp` directory with a private Unix-domain socket and TCP listening disabled. **13 passed in 1.14 seconds** with both SQLite and PostgreSQL exercised. The temporary database and socket were removed after the run.

These tests cover canonicalization, statement bytes, indexing, fixture ingest, the revision tree and the `/check` field. The ingest fixture disables signature verification. The separate public-envelope checks above exercise real signatures and Rekor inclusion.
