# Secretless fixed QA worker

The worker has one job, `platform_smoke`. It makes three parallel unauthenticated GET requests and reports only
HTTP status and pass/fail: backend `/health`, `https://modelmarket.dev/` and `https://hub.attestedmemory.net/`.
Only HTTP 200 passes. Redirects are not followed, response bodies/headers/errors are discarded, and each check
has one three-second deadline covering DNS, TCP, proxy CONNECT, TLS and headers. This establishes endpoint health,
not authenticated product behavior or a complete browser test.

The JSON contract is exactly:

```json
{"job":"platform_smoke","checks":[{"name":"backend_health","pass":true,"status":200},{"name":"modelmarket_https","pass":true,"status":200},{"name":"hub_https","pass":true,"status":200}],"passed":true}
```

Failure uses the same schema; transport failures have status 0. Exit code 0 means all three checks passed; otherwise
the CLI exits 1. Command-line arguments are rejected rather than interpreted as a URL or command. The entry point
does not read task text, environment-based target URLs, files from the daemon home or application credentials.
An unexpected credential/TLS-override environment key fails the job before networking; the host broker's fixed
`env -i` invocation and a new container without secret mounts remain the primary isolation boundary.

The container starts only an idle Node process. It serves no API. The host's reviewed broker executes only the fixed
`npm --silent run smoke` command in `/opt/qa` with a cleared environment, `HOME=/tmp`, explicit PATH and proxy values.
No agent-supplied command, argument, URL, npm script name, environment value or file path enters that invocation.
The package has no dependencies or install step. The source and package file are root-owned and immutable in the
read-only container; `/tmp` is a bounded ephemeral tmpfs. No daemon/home volume, env file, secret or Docker socket is
mounted in this worker. Container uid/gid is 10001, all capabilities are dropped, and no-new-privileges is enabled.

`../worker.compose.yaml` is a separate Compose project using the **existing** external `multica_agent` network at
`10.250.0.5`. It does not create or replace that network. Root's host firewall must restrict this address to the
existing proxy `10.250.0.2:8888` and backend `10.250.0.3:8080`; Tinyproxy must explicitly admit the worker address.
Network membership alone does not establish that restriction. Docker restart policy is `no`; the host's guarded
orchestration must apply the boundary before starting the worker.

The base is the official Node 22.23.4 Bookworm slim image, pinned to the multi-platform index digest
`sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d`, read from Docker Hub on 10 November 2026.
Its Linux amd64 manifest is `sha256:aaa4b5baf1ecff3b283486bb1f90405cdda225a3e6f79660d2c559fa510a7292`.
The build copies only the four fixed production files and does not install packages. Record the built image ID
separately; the base manifest is not the custom worker image ID.

Run the local builtin tests with Node 22 and Docker Compose available:

```sh
node --test multica/qa-runner/worker/test/*.test.mjs
```

Network fixtures use temporary loopback listeners, including a self-signed TLS server and an incomplete response
that keeps sending bytes. A disposable private key is generated only in the system temporary directory and removed
after the test. Production TLS always verifies the hostname/certificate against Node's built-in roots. The suite
also checks that the Compose render does not inherit a synthetic host token and that the CLI never prints one.

Base image and TLS behavior references: [official Node image](https://hub.docker.com/_/node) and
[Node 22 TLS documentation](https://nodejs.org/docs/latest-v22.x/api/tls.html).
