# Gitea deploy-agent credential rotation — 2026-10-27

The user explicitly authorized replacing the Gitea credential used by the
deploy-agent, rotating the `alexar76` account password, and checking the agent.
The current delivery instruction is a local commit on `main`, with no push or
GitHub write.

## Change

The previous `SKOPOS_AGENT_REPO_URL` embedded the local account password.
The replacement uses a dedicated PAT with the sole `read:repository` scope.
The URL and cached Git origin retain the same endpoint and contain no userinfo.
A root-owned credential store with mode `0600` supplies authentication through
service-specific Git configuration. Credential matching includes the repository
path; an unrelated path does not receive the PAT.

The normal Gitea web password form is used with in-memory cookies and CSRF
tokens. No secret is passed in process arguments. Account ID, login, local
authentication source, blank login name and administrator status are preserved.
The conductor's separate SSH authentication is outside this change.

## Execution and recovery

`rotate_remote.py` is the reviewed, dated operator helper for `admin-vps`, using
Python 3.11 or newer as root. It deliberately refuses to overwrite an existing
rotation state directory. It is not a scheduled job or a general deployment tool.
Private state stays under a root-only `/run` directory. Only explicitly selected
public JSON projections belong in this evidence directory.

The first attempt created the replacement PAT, then rolled back the environment
file and cached origin after an immediate process-environment check failed.
Independent checks confirmed the old password still worked, the generated new
password was not active, and the new PAT could read the repository.

The helper now waits for the environment to become ready: a `Type=simple` service
may report active before the executable has received its environment. Three
regression tests cover delayed readiness, timeout and replacement of the PID.
The explicit `--resume-agent-rollback` mode validates the rollback checkpoints
and reuses the existing PAT and pending password. It does not mint a second PAT.

Local checks:

```sh
.venv/bin/python docs/evidence/gitea-agent-rotation-2026-10-27/test_rotate_remote.py
.venv/bin/ruff check docs/evidence/gitea-agent-rotation-2026-10-27/*.py
git diff --check
```

## Acceptance criteria

- Fresh requests without cookies reject the old account password with `401` and
  accept the new password with `200`, preserving the account identity.
- The PAT reads the private repository; Basic-auth receive-pack discovery is
  denied with `403`. No Git push command is executed.
- Direct and cached-origin Git reads and the allowed-branch fetch dry run pass
  after the account password changes.
- The restarted agent loads the clean URL and Git credential configuration,
  stays active with a stable PID/restart count, and naturally polls its server
  successfully after rotation. No order-claim endpoint is invoked manually.
- Temporary old-secret state is removed after negative authentication checks.
  New credentials are delivered through a protected local file outside Git.

## Verified result

The resumed rotation completed at `2026-10-27T18:37:28Z` with the original
replacement PAT. Fresh old/new password checks returned `401`/`200`.
The agent remained active as PID `1996670`, with `NRestarts=0` and two successful
natural polls after password rotation. All Git transport checks passed.

`final-readback.json` confirms that both URLs are credential-free, the credential
store is root-owned with mode `0600`, old private recovery state was removed,
and the new credential values are absent from process arguments and the new
PID's journal. The protected handoff file is outside this repository; neither
its values nor its location are versioned here.

`verified.json` and the other public projections contain only check results and
non-secret metadata. The completed helper SHA-256 is
`eb0855502565db18d6665080cfa518383e29f6d55d58c5e78c272a3ec752457a`.

## Scope limitation

Gitea 1.22.6 uses a user-wide repository-category PAT scope. It does not restrict
this PAT to one repository at the server. The path restriction above applies to
the agent's credential helper. This Gitea version also predates the fix for the
Git Bearer scope bypass in [GHSA-cc8w-r4qh-3v65](https://github.com/go-gitea/gitea/security/advisories/GHSA-cc8w-r4qh-3v65).
The observed Basic-auth write denial must not be described as complete server
enforcement across every authentication path. Upgrading Gitea is a separate task.

References: [Gitea 1.22 rootless Docker paths](https://docs.gitea.com/1.22/installation/install-with-docker-rootless/),
[native password-change handler](https://raw.githubusercontent.com/go-gitea/gitea/v1.22.6/routers/web/user/setting/account.go),
[Git credential matching](https://git-scm.com/docs/gitcredentials).
