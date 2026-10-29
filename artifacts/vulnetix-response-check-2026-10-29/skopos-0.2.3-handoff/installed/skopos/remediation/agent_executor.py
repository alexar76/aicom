"""The deploy executor that runs ON a SKOPOS node agent — the constrained deployer.

This is the *only* code path by which a redeploy happens, and it is deliberately small and
paranoid. Before it does anything it runs ``verify_deploy_chain`` (MOMUS-fixed verdict +
conductor signature + local service allowlist). Only then does it run a single, fixed-shape
redeploy command for that one allowlisted service. It never accepts an arbitrary command; the
DeployOrder carries a service name, not a shell string, so there is nothing to inject.

Default is DRY-RUN: it validates and reports the command it *would* run, executing nothing. A real
node agent flips ``dry_run=False`` and provides the compose file for its host.

**A deploy that cannot be undone is a one-way door.** So this executor does three things beyond
running the command, and they are what make turning ``dry_run`` off defensible:

1. **It writes down where it came from.** Before recreating anything it reads the running
   container's image digest and the image reference compose names for it, and journals both
   (``agent_state.py``). That record is the only rollback target that exists; nothing in the order
   supplies one.
2. **It gates its own work.** ``docker compose up`` exits 0 the moment the container is created —
   long before a container that crash-loops on the new image has had time to fail. So the executor
   waits, then checks the container is actually up, not restarting, and not unhealthy.
3. **It undoes its own damage, immediately.** A failed health gate rolls back on the spot rather
   than reporting a broken service and waiting for instructions. Waiting would mean a poll interval
   of downtime for a fault the agent has already diagnosed locally.

The conductor can also order a rollback for the case only MOMUS can see — the patch deployed and
came up healthy, but the finding still reproduces against the live container. That path is
``execute_rollback``, and it resolves its target from this agent's journal, never from the order.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from typing import Any

from skopos.remediation.agent_state import AgentStateStore, BuildRecord, DeployRecord
from skopos.remediation.deploy_order import (
    verify_build_chain,
    verify_deploy_chain,
    verify_rollback_chain,
)

#: How long to let a freshly recreated container prove it is not crash-looping before believing it.
#: `compose up` returning 0 means "created", not "working", and the gap between those is exactly
#: where a bad patch hides.
DEFAULT_HEALTH_WAIT_S = 20.0
#: Docker calls are quick; a hung daemon must not wedge the agent's poll loop.
_INSPECT_TIMEOUT_S = 30
_DEPLOY_TIMEOUT_S = 300
#: A build clones, fetches and compiles an image; it is the one genuinely slow step here.
_BUILD_TIMEOUT_S = 1800


class NodeDeployExecutor:
    def __init__(self, *, conductor_pubkey: str, momus_pubkey: str,
                 service_allowlist: list[str], compose_file: str = "",
                 dry_run: bool = True, state: AgentStateStore | None = None,
                 health_wait_s: float = DEFAULT_HEALTH_WAIT_S,
                 repo_url: str = "", repo_dir: str = "", work_dir: str = "",
                 branch_prefixes: tuple[str, ...] = ("momus/fix-",),
                 build_map: dict[str, dict[str, str]] | None = None,
                 require_tests: bool = False,
                 host: str = "", runner: Any = None, sleeper: Any = None):
        self.conductor_pubkey = conductor_pubkey
        self.momus_pubkey = momus_pubkey
        self.service_allowlist = list(service_allowlist)
        self.compose_file = compose_file
        self.dry_run = dry_run
        self.state = state
        self.health_wait_s = health_wait_s
        # ── build inputs, all LOCAL ────────────────────────────────────────
        # Where source may come from, which branches are acceptable, and how each service is built.
        # None of this is ever read off an order: the order says *which commit*, the host says
        # *which repo, which branches, and how to build*. Same split as the service allowlist, for
        # the same reason — a compromised conductor must not be able to widen any of it.
        self.repo_url = repo_url
        self.repo_dir = repo_dir
        self.work_dir = work_dir
        self.branch_prefixes = tuple(branch_prefixes)
        self.build_map = dict(build_map or {})
        # Whether a failing component test suite BLOCKS the build, or is merely reported.
        # Starts advisory on purpose: a gate that has never run is not yet a gate you can
        # trust to refuse, and a false refusal here stops every repair on the host.
        self.require_tests = bool(require_tests)
        self.host = host.strip()
        # Test seams. Real runs shell out; tests inject a fake docker and a fake clock so the health
        # gate can be exercised without waiting 20 real seconds per case.
        self._run = runner or self._subprocess_run
        self._sleep = sleeper or time.sleep

    # ── plumbing ────────────────────────────────────────────────────────────
    @staticmethod
    def _subprocess_run(argv: list[str], timeout: int) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
            return proc.returncode, proc.stdout, proc.stderr
        except (subprocess.SubprocessError, OSError) as exc:
            return 127, "", f"{type(exc).__name__}: {exc}"

    def _compose_service(self, service: str) -> str:
        """The compose service name for a component.

        These are NOT the same string: MOMUS names its canary target `canary`, while the compose
        service is `momus-canary`. An order carries the COMPONENT, because that is what the finding
        is about, so translating it is the host's job — exactly like the allowlist and the build
        recipe. Falls back to the component name when the host declares no mapping, which is the
        common case where they happen to match."""
        return (self.build_map.get(service, {}) or {}).get("compose_service") or service

    def _addressed_here(self, order: dict[str, Any]) -> tuple[bool, str]:
        """Bind signed orders to this host, not merely to an allowlisted service."""
        addressed = str(order.get("host") or "").strip()
        if self.host and addressed != self.host:
            return False, f"order is addressed to host '{addressed}', not this agent '{self.host}'"
        return True, "host matches"

    def _compose_file_for(self, service: str) -> str:
        """The compose file this service lives in.

        One agent, one compose file was enough while the loop only ever touched the canary. The
        services MOMUS probes are in different compose projects on the same host — the canary in
        `momus-deploy`, the oracle family in `oracles`, GAIA in `gaia` — so a single global file
        would make `compose ps` return nothing and the deploy step read as "service not running".
        Per-service, and still the HOST's to declare: an order names a component, never a file.
        """
        return (self.build_map.get(service, {}) or {}).get("compose_file") or self.compose_file

    def _compose(self, *args: str, service: str = "") -> list[str]:
        argv = ["docker", "compose"]
        compose_file = self._compose_file_for(service) if service else self.compose_file
        for path in [p for p in str(compose_file or "").split(",") if p.strip()]:
            argv += ["-f", path.strip()]
        return argv + list(args)

    def _container_id(self, service: str) -> str:
        rc, out, _ = self._run(self._compose("ps", "-q", self._compose_service(service),
                                     service=service),
                               _INSPECT_TIMEOUT_S)
        return out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else ""

    def _image_of(self, container_id: str) -> tuple[str, str]:
        """(image digest actually running, image reference compose asked for).

        Both come from one inspect: ``.Image`` is the immutable digest — the only thing worth
        rolling back *to* — and ``.Config.Image`` is the tag compose resolves, which is what a
        rollback has to re-point at that digest for ``compose up`` to pick it up."""
        rc, out, _ = self._run(
            ["docker", "inspect", "--format", "{{.Image}}|{{.Config.Image}}", container_id],
            _INSPECT_TIMEOUT_S)
        if rc != 0 or "|" not in out:
            return "", ""
        digest, _, ref = out.strip().partition("|")
        return digest.strip(), ref.strip()

    def _health(self, service: str) -> tuple[bool, str]:
        """Is the service actually up? Checked AFTER a wait, because `compose up` is not a verdict."""
        cid = self._container_id(service)
        if not cid:
            return False, "no container for the service after deploy"
        rc, out, err = self._run(
            ["docker", "inspect", "--format",
             "{{.State.Status}}|{{.State.Restarting}}|{{.RestartCount}}|"
             "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", cid],
            _INSPECT_TIMEOUT_S)
        if rc != 0:
            return False, f"docker inspect failed after deploy: {err.strip()[:200]}"
        parts = out.strip().split("|")
        if len(parts) < 4:
            return False, f"unreadable container state: {out.strip()[:200]}"
        status, restarting, restarts, health = (p.strip() for p in parts[:4])
        if status != "running":
            return False, f"container is '{status}', not running"
        if restarting.lower() == "true":
            return False, "container is restarting (crash loop)"
        # A container recreated seconds ago should not have restarted yet. Any count here means it
        # came up, died, and was restarted by the policy — the exact failure `compose up` hides.
        if restarts.isdigit() and int(restarts) > 0:
            return False, f"container already restarted {restarts}x since deploy (crash loop)"
        if health not in ("none", "healthy"):
            return False, f"container healthcheck reports '{health}'"
        return True, f"running, healthcheck={health}"

    # ── build ───────────────────────────────────────────────────────────────
    def execute_build(self, order: dict[str, Any]) -> dict[str, Any]:
        """Turn a named commit into a tagged, digest-identified image — the missing arm.

        Until this existed the loop could not self-heal even in principle: nothing ever produced a
        patched image, so the deploy step recreated the container from the image already on the host
        and the gate had nothing new to judge.

        Source arrives as a *commit reference*, never inline. The agent fetches it from the repo IT
        is configured with, refuses any branch outside its own prefix list, and refuses a commit that
        is not actually the tip of the branch it was told about. Then it builds with the dockerfile
        and context ITS OWN map specifies for that service.
        """
        host_ok, host_reason = self._addressed_here(order)
        if not host_ok:
            return {"built": False, "refused": True, "reason": host_reason}
        ok, reason = verify_build_chain(
            order, conductor_pubkey=self.conductor_pubkey,
            service_allowlist=self.service_allowlist,
            allowed_branch_prefixes=list(self.branch_prefixes))
        if not ok:
            return {"built": False, "refused": True, "reason": reason}

        service = order["service"]
        sha = str(order["commit_sha"]).strip().lower()
        branch = str(order["branch"]).strip()
        spec = self.build_map.get(service)
        if not spec:
            # A service the host never described how to build. Refusing beats guessing a Dockerfile.
            return {"built": False, "refused": True,
                    "reason": f"no local build recipe for '{service}' — set it in the agent's build "
                              f"map before this service can be built"}
        if not self.repo_url or not self.repo_dir or not self.work_dir:
            return {"built": False, "refused": True,
                    "reason": "agent has no repo/work directory configured — cannot fetch source"}

        tag = f"{service}:momus-{sha[:12]}"
        if self.dry_run:
            return {"built": False, "dry_run": True, "reason": reason, "would_tag": tag,
                    "would_build_from": f"{branch}@{sha[:12]}",
                    "dockerfile": spec.get("dockerfile", ""), "context": spec.get("context", ".")}

        prepared, why = self._prepare_source(sha, branch)
        if not prepared:
            return {"built": False, "reason": why}

        worktree = os.path.join(self.work_dir, sha[:12])
        dockerfile = os.path.join(worktree, spec.get("dockerfile", "Dockerfile"))
        context = os.path.join(worktree, spec.get("context", "."))
        rc, out, err = self._run(
            ["docker", "build", "--label", "skopos.source.commit=" + sha, "-f", dockerfile, "-t", tag, context], _BUILD_TIMEOUT_S)
        if rc != 0:
            self._cleanup_worktree(worktree)
            return {"built": False, "reason": f"docker build failed (rc={rc})",
                    "stderr": err[-3000:], "stdout": out[-1000:]}

        # The component's OWN tests, before anything else looks at this build.
        #
        # Until now the single gate was one MOMUS probe re-run. A probe asserts the one
        # behaviour it was written for; a patch that satisfies it and breaks everything else
        # passed the gate and shipped. The probe is a regression test for the finding, not a
        # test suite, and it was never meant to be both.
        tests = self._run_component_tests(spec, dockerfile, context, tag)
        if tests.get("blocked"):
            self._cleanup_worktree(worktree)
            return {"built": False, "reason": tests.get("reason") or "component tests failed",
                    "tests": tests}

        digest = self._image_digest(tag)
        self._cleanup_worktree(worktree)
        if not digest:
            # Without a digest there is nothing for the gate to bind its verdict to, and nothing the
            # deploy step could check against this agent's build journal. A tag alone is mutable.
            return {"built": False, "reason": f"built {tag} but could not read its image digest"}

        quality = self._quality_gate(service, "candidate", digest)
        if not quality[0]:
            return {"built": False, "reason": quality[1], "tests": tests}

        if self.state:
            self.state.record_build(BuildRecord(
                order_id=str(order.get("order_id") or ""), service=service, commit_sha=sha,
                image_tag=tag, image_digest=digest))

        # An image nobody can reach cannot be gated. MOMUS probes `<host>-candidate` by convention,
        # so the build step also STARTS the candidate — otherwise the pre-promotion verdict would be
        # "unreachable → inconclusive" every time, which blocks every deploy and looks like a patch
        # problem. Published on no host port: it is reachable only from inside the shared network.
        started, where = self._start_candidate(service, tag)
        result = {"built": True, "reason": reason, "image_tag": tag, "image_digest": digest,
                  "commit_sha": sha, "branch": branch, "service": service,
                  "candidate_running": started, "candidate": where, "tests": tests}
        if not started and getattr(self, "_last_candidate_error", ""):
            result["candidate_error"] = self._last_candidate_error
        return result

    #: How long the component's own suite may take. Targeted at the patched modules, so this
    #: is generous rather than tight — a suite that needs longer is telling you it is the wrong
    #: suite for a gate that runs every fifteen minutes.
    _TEST_TIMEOUT_S = 600
    #: Enough of a failing suite to see which assertion went, and the summary line.
    _TEST_OUTPUT_TAIL = 4000

    def _run_component_tests(self, spec: dict[str, str], dockerfile: str,
                             context: str, tag: str) -> dict[str, Any]:
        """Run the patched component's own tests against the image just built.

        Returns a record that always says what happened, including "there is no suite" —
        an absent gate that reports nothing is indistinguishable from a gate that passed,
        and that is exactly the confusion that let a probe stand in for a test suite.

        Never blocks unless ``require_tests`` is on. Network is off: a unit suite that needs
        the internet is not testing this patch.
        """
        target = str(spec.get("test_target") or "").strip()
        paths = [p for p in str(spec.get("test_paths") or "").split() if p]
        if not target:
            return {"ran": False, "blocked": False,
                    "reason": "this component's recipe declares no test stage",
                    "enforced": self.require_tests}

        test_tag = f"{tag}-tests"
        rc, out, err = self._run(
            ["docker", "build", "--target", target, "-f", dockerfile, "-t", test_tag, context],
            _BUILD_TIMEOUT_S)
        if rc != 0:
            # A test stage that will not build is a broken gate, not a failing patch. Say which.
            return {"ran": False, "blocked": self.require_tests,
                    "reason": f"the test stage '{target}' failed to build (rc={rc})",
                    "stderr": err[-self._TEST_OUTPUT_TAIL:], "enforced": self.require_tests}

        command = (["npm", "test", "--", "--maxWorkers=2"] if spec.get("test_runner") == "npm" else
                   ["python", "-m", "pytest", "-q", "--no-header", *paths])
        argv = ["docker", "run", "--rm", "--network", "none", "--memory", "1g", test_tag, *command]
        rc, out, err = self._run(argv, self._TEST_TIMEOUT_S)
        self._run(["docker", "rmi", "-f", test_tag], _INSPECT_TIMEOUT_S)

        passed = rc == 0
        record: dict[str, Any] = {
            "ran": True, "passed": passed, "target": target, "paths": paths,
            "blocked": (not passed) and self.require_tests,
            "enforced": self.require_tests,
            "summary": (out or err).strip().splitlines()[-1][:300] if (out or err).strip() else "",
        }
        if not passed:
            record["reason"] = ("the patched component's own tests failed — the probe may be "
                                "satisfied, but something else in the component is not")
            record["output"] = ((out or "") + (err or ""))[-self._TEST_OUTPUT_TAIL:]
        return record

    def _quality_gate(self, service: str, phase: str, image: str) -> tuple[bool, str]:
        if service != "warden":
            return True, "no external quality hook required"
        # An invariant, not an order/model-controlled command or an optional recipe field.
        hook = "/usr/local/sbin/skopos-warden-quality"
        rc, _, _ = self._run([hook, phase, image], 14400)
        return rc == 0, "WARDEN signed full quality gate " + ("passed" if rc == 0 else "failed")

    def _candidate_name(self, service: str) -> str:
        # Named after the COMPOSE service, because MOMUS derives the candidate host it probes from
        # the target URL it was configured with — which resolves the compose/container name.
        return f"{self._compose_service(service)}-candidate"

    def _network_of(self, service: str) -> str:
        """The network the live service is on, so the candidate is reachable from MOMUS.

        Read off the running container rather than configured, because that is the network MOMUS is
        actually able to resolve names on; a value from a config file can be stale."""
        declared = self.build_map.get(service, {}).get("network", "")
        if declared:
            return declared
        cid = self._container_id(service)
        if not cid:
            return ""
        rc, out, _ = self._run(
            ["docker", "inspect", "--format",
             "{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{println}}{{end}}", cid],
            _INSPECT_TIMEOUT_S)
        if rc != 0:
            return ""
        names = [n.strip() for n in out.splitlines() if n.strip()]
        return names[0] if names else ""

    #: How much of a dead candidate's output to carry back. Enough for a traceback's last frames.
    CANDIDATE_LOG_TAIL = 1500

    def _candidate_last_words(self, name: str) -> str:
        """What the container said before it stopped.

        The gate cannot render this verdict: there is nothing to probe. And the message that
        reached the conductor — "candidate container is 'exited'" — is true and useless, so the
        next attempt was told a container failed and not WHY. A real one read
        `ValueError: An Ed25519 private key is 32 bytes long`, which is a fix in one line.
        """
        rc, out, err = self._run(["docker", "logs", "--tail", "40", name], _INSPECT_TIMEOUT_S)
        if rc != 0:
            return ""
        text = ((err or "") + "\n" + (out or "")).strip()
        return text[-self.CANDIDATE_LOG_TAIL:]

    def _start_candidate(self, service: str, image: str) -> tuple[bool, str]:
        name = self._candidate_name(service)
        self.remove_candidate(service)      # a stale candidate would be gated instead of this build
        network = self._network_of(service)
        if not network:
            return False, ("could not determine the service network — the candidate would be "
                           "unreachable from MOMUS")
        argv = ["docker", "run", "-d", "--name", name, "--network", network,
                # No published ports, no host mounts, no privileges: this container exists only to be
                # probed for a few seconds. It gets a hard memory ceiling so a pathological build
                # cannot take the host down while being examined.
                "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL",
                "--memory", "512m", "--pids-limit", "256",
                "--label", "skopos.remediation=candidate"]
        # Optional per-service env for the candidate, from the HOST's build map. Not every service
        # runs correctly on its image defaults, and a candidate that starts on the wrong port is
        # unreachable — which the gate reports as "inconclusive", i.e. blocks the deploy for a reason
        # that has nothing to do with the patch. Values come from the host, never from an order.
        for key, value in sorted((self.build_map.get(service, {}).get("env") or {}).items()):
            argv += ["-e", f"{key}={value}"]
        argv.append(image)
        rc, _, err = self._run(argv, _DEPLOY_TIMEOUT_S)
        if rc != 0:
            return False, f"could not start the candidate container: {err.strip()[:200]}"
        self._sleep(self.health_wait_s)
        rc, out, _ = self._run(["docker", "inspect", "--format", "{{.State.Status}}", name],
                               _INSPECT_TIMEOUT_S)
        status = out.strip() if rc == 0 else "unknown"
        if status != "running":
            # A candidate that will not even start is itself a verdict on the patch — and the
            # gate cannot render it, because there is nothing left to probe. So the fact AND
            # the container's own last words go back; the conductor feeds them to the next
            # attempt, which is the only thing that can act on them.
            self._last_candidate_error = self._candidate_last_words(name)
            return False, f"candidate container is '{status}', not running"
        self._last_candidate_error = ""
        return True, f"{name} on {network}"

    def remove_candidate(self, service: str) -> None:
        """Best effort. A leftover candidate is the one thing that could make a LATER gate examine
        the wrong build, so removal happens before every build and after every promotion."""
        self._run(["docker", "rm", "-f", self._candidate_name(service)], _INSPECT_TIMEOUT_S)

    def _prepare_source(self, sha: str, branch: str) -> tuple[bool, str]:
        """Fetch `branch` into a local mirror, check `sha` really is its tip, lay out a worktree.

        The tip check matters: without it the order could name any commit reachable in the repo —
        including one on a branch the prefix rule was meant to exclude — and the prefix check would
        pass on a branch name that had nothing to do with the code being built."""
        mirror = self.repo_dir
        if not os.path.isdir(os.path.join(mirror, "objects")):
            rc, _, err = self._run(["git", "clone", "--bare", self.repo_url, mirror], _BUILD_TIMEOUT_S)
            if rc != 0:
                return False, f"could not clone the source mirror: {err.strip()[:300]}"
        rc, _, err = self._run(
            ["git", "-C", mirror, "fetch", "--force", "origin", f"refs/heads/{branch}:refs/heads/{branch}"],
            _BUILD_TIMEOUT_S)
        if rc != 0:
            return False, f"could not fetch '{branch}': {err.strip()[:300]}"
        rc, out, _ = self._run(["git", "-C", mirror, "rev-parse", f"refs/heads/{branch}"],
                               _INSPECT_TIMEOUT_S)
        tip = out.strip()
        if rc != 0 or not tip:
            return False, f"could not resolve '{branch}' after fetching it"
        if not tip.startswith(sha) and not sha.startswith(tip[:len(sha)]):
            return False, (f"commit {sha[:12]} is not the tip of '{branch}' (tip is {tip[:12]}) — "
                           f"refusing to build a commit the named branch does not point at")
        worktree = os.path.join(self.work_dir, sha[:12])
        self._cleanup_worktree(worktree)
        os.makedirs(self.work_dir, exist_ok=True)
        rc, _, err = self._run(["git", "-C", mirror, "worktree", "add", "--detach", worktree, tip],
                               _BUILD_TIMEOUT_S)
        if rc != 0:
            return False, f"could not lay out a worktree for {sha[:12]}: {err.strip()[:300]}"
        return True, "source prepared"

    def _cleanup_worktree(self, worktree: str) -> None:
        """Best effort: a leftover worktree wastes disk but must never fail a build or a report."""
        self._run(["git", "-C", self.repo_dir, "worktree", "remove", "--force", worktree],
                  _INSPECT_TIMEOUT_S)
        self._run(["rm", "-rf", worktree], _INSPECT_TIMEOUT_S)

    def _image_digest(self, image: str) -> str:
        rc, out, _ = self._run(["docker", "image", "inspect", "--format", "{{.Id}}", image],
                               _INSPECT_TIMEOUT_S)
        return out.strip() if rc == 0 else ""

    # ── forward deploy ──────────────────────────────────────────────────────
    def execute(self, order: dict[str, Any]) -> dict[str, Any]:
        host_ok, host_reason = self._addressed_here(order)
        if not host_ok:
            return {"deployed": False, "refused": True, "reason": host_reason}
        ok, reason = verify_deploy_chain(
            order, conductor_pubkey=self.conductor_pubkey, momus_pubkey=self.momus_pubkey,
            service_allowlist=self.service_allowlist)
        if not ok:
            return {"deployed": False, "refused": True, "reason": reason}

        service = order["service"]
        order_id = str(order.get("order_id") or "")
        # THE image the order asks for. This used to be read by nothing at all: `DeployOrder.image`
        # existed, carried a value, and was silently dropped — so a "fix deploy" recreated the
        # container from the image already on the host and could not possibly have fixed anything.
        # That single omission is what made the loop theatre rather than self-healing.
        wanted = str(order.get("image") or "").strip()
        built: BuildRecord | None = None
        if wanted:
            built = self.state.built_image(wanted) if self.state else None
            if built is None:
                # The same containment as rollback: the agent acts only on images IT produced. An
                # order naming any other image on the host — a different service's, a stale one, one
                # an operator pulled by hand — resolves to nothing and is refused.
                return {"deployed": False, "refused": True,
                        "reason": f"image '{wanted}' was not built by this agent — refusing to "
                                  f"deploy an image with no local build record"}
            if built.service != service:
                return {"deployed": False, "refused": True,
                        "reason": f"image '{wanted}' was built for '{built.service}', not "
                                  f"'{service}' — refusing to cross-deploy it"}

        if service == "warden":
            current, note = self._quality_gate(service, "authorize", wanted)
            if not current:
                return {"deployed": False, "refused": True, "reason": note}

        # A single, fixed-shape command. The service name is allowlisted and passed as an argv
        # element (never interpolated into a shell string), so there is no command-injection surface.
        argv = self._compose("up", "-d", "--no-deps", "--force-recreate",
                             self._compose_service(service), service=service)

        if self.dry_run:
            return {"deployed": False, "dry_run": True, "reason": reason,
                    "would_run": " ".join(shlex.quote(a) for a in argv),
                    "would_promote": built.image_digest if built else "",
                    "image_requested": wanted}

        # 1. Remember where we came from, BEFORE changing anything. A rollback target read after the
        #    deploy would describe the new state, which is useless — and reading it at all is what
        #    the whole undo path depends on, so a failure here is worth reporting rather than hiding.
        prev_cid = self._container_id(service)
        prev_image, running_ref = self._image_of(prev_cid) if prev_cid else ("", "")
        # The tag compose will resolve. Prefer what the host declared; fall back to what the running
        # container was created from. Needed by BOTH directions — promote and restore work by moving
        # this tag, because `compose up` resolves a tag and cannot be handed a digest.
        compose_ref = (self.build_map.get(service, {}).get("image_ref") or running_ref)
        record = DeployRecord(order_id=order_id, service=service, previous_image=prev_image,
                              compose_image_ref=compose_ref,
                              finding_id=str(order.get("finding_id") or ""))

        # 2. Promote the requested image by moving the compose tag onto its digest. Symmetric with
        #    the restore path, deliberately: one mechanism, exercised in both directions.
        if built is not None:
            if not compose_ref:
                return {"deployed": False, "refused": True,
                        "reason": f"cannot determine the compose image reference for '{service}' "
                                  f"(nothing running and no image_ref in the local build map) — "
                                  f"refusing to promote an image blindly"}
            rc, _, err = self._run(["docker", "tag", built.image_digest, compose_ref],
                                   _INSPECT_TIMEOUT_S)
            if rc != 0:
                return {"deployed": False,
                        "reason": f"could not promote {built.image_digest[:19]}… to {compose_ref}: "
                                  f"{err.strip()[:200]}",
                        "previous_image": prev_image}

        rc, out, err = self._run(argv, _DEPLOY_TIMEOUT_S)
        result: dict[str, Any] = {"deployed": rc == 0, "returncode": rc, "reason": reason,
                                  "stdout": out[-2000:], "stderr": err[-2000:],
                                  "previous_image": prev_image, "compose_image_ref": compose_ref,
                                  "promoted_image": built.image_digest if built else "",
                                  "rollback_available": record.can_roll_back}
        if rc != 0:
            record.outcome = "error"
            self._journal(record)
            return result

        # 3. `compose up` said "created". Find out whether it actually WORKS.
        self._sleep(self.health_wait_s)
        healthy, health_note = self._health(service)
        result["health"] = health_note
        new_cid = self._container_id(service)
        record.deployed_image = self._image_of(new_cid)[0] if new_cid else ""
        result["deployed_image"] = record.deployed_image

        # 4. And find out whether it is actually the image we meant to ship. `compose up` reports
        #    success for recreating a container from whatever the tag happened to resolve to, so
        #    "deployed: true" on its own never proved the patch was applied — the omission this whole
        #    step exists to close. A mismatch here means the fix did NOT reach the host, which is a
        #    failure to report, not a success with a footnote.
        if built is not None and record.deployed_image != built.image_digest:
            result.update({
                "deployed": False, "image_mismatch": True,
                "reason": f"{reason}; but the running container is "
                          f"{record.deployed_image[:19] or '(unknown)'}…, not the promoted "
                          f"{built.image_digest[:19]}… — the patch did NOT take effect",
            })
            record.outcome = "error"
            self._journal(record)
            return result

        if healthy:
            healthy, quality_note = self._quality_gate(service, "live", record.deployed_image)
            if not healthy:
                health_note = quality_note
        if healthy:
            record.outcome = "deployed"
            self._journal(record)
            # The candidate has served its purpose: the real service now runs that exact digest.
            # Removed only on the SUCCESS path — after a failure it is the most useful thing on the
            # host to look at, and the next build clears any stale one anyway.
            if built is not None:
                self.remove_candidate(service)
            return result

        # 5. It does not work. Undo it here and now — a poll interval of downtime for a fault this
        #    agent has already diagnosed would be a choice, not a constraint.
        record.outcome = "deployed"     # journalled as a deploy first, so the undo has a target
        self._journal(record)
        undo = self._restore(record, reason=f"post-deploy health gate failed: {health_note}")
        result.update({"deployed": False, "health_gate_failed": True,
                       "rolled_back": bool(undo.get("rolled_back")),
                       "rollback": undo,
                       "reason": f"{reason}; deploy REVERTED: {health_note}"})
        return result

    # ── rollback ────────────────────────────────────────────────────────────
    def execute_rollback(self, order: dict[str, Any]) -> dict[str, Any]:
        """Undo a prior deploy on this host, on the conductor's signed instruction.

        Used for the failure only MOMUS can see: the container came up healthy, so the local gate
        passed, but the finding still reproduces against the live service."""
        host_ok, host_reason = self._addressed_here(order)
        if not host_ok:
            return {"rolled_back": False, "refused": True, "reason": host_reason}
        ok, reason = verify_rollback_chain(
            order, conductor_pubkey=self.conductor_pubkey,
            service_allowlist=self.service_allowlist)
        if not ok:
            return {"rolled_back": False, "refused": True, "reason": reason}

        target_order = str(order.get("rollback_of") or "")
        record = self.state.get(target_order) if self.state else None
        if record is None:
            # The order names a deploy this agent never performed. There is nothing to go back to,
            # and inventing a target is exactly what this design refuses to do.
            return {"rolled_back": False, "refused": True,
                    "reason": f"no local record of order '{target_order}' — this agent never "
                              f"executed it, so there is no state to return to"}
        if record.service != order.get("service"):
            return {"rolled_back": False, "refused": True,
                    "reason": f"order '{target_order}' was for service '{record.service}', not "
                              f"'{order.get('service')}'"}
        if not record.can_roll_back:
            return {"rolled_back": False, "refused": True,
                    "reason": "no previous image was recorded for that deploy (first-ever start) — "
                              "nothing to roll back to"}
        if self.dry_run:
            return {"rolled_back": False, "dry_run": True, "reason": reason,
                    "would_restore": record.previous_image,
                    "would_run": " ".join(shlex.quote(a) for a in self._compose(
                        "up", "-d", "--no-deps", "--force-recreate",
                        self._compose_service(record.service), service=record.service))}
        return self._restore(record, reason=str(order.get("reason") or "conductor-ordered rollback"))

    def _restore(self, record: DeployRecord, *, reason: str) -> dict[str, Any]:
        """Re-point the compose tag at the previously-running digest and recreate the container.

        Two steps rather than one because `compose up` resolves the *tag* from the compose file; it
        has no way to be told "that digest instead". So the tag is moved back first."""
        if not record.can_roll_back:
            return {"rolled_back": False, "reason": "nothing recorded to roll back to"}
        rc, _, err = self._run(["docker", "tag", record.previous_image, record.compose_image_ref],
                               _INSPECT_TIMEOUT_S)
        if rc != 0:
            # The old image is gone from the local store (pruned) — say so plainly instead of
            # reporting a generic failure, because the remedy is an operator's, not a retry's.
            return {"rolled_back": False, "trigger": reason,
                    "reason": f"could not re-tag {record.previous_image[:19]}… as "
                              f"{record.compose_image_ref}: {err.strip()[:200]} (image pruned?)"}
        argv = self._compose("up", "-d", "--no-deps", "--force-recreate",
                             self._compose_service(record.service), service=record.service)
        rc, out, err = self._run(argv, _DEPLOY_TIMEOUT_S)
        if rc != 0:
            return {"rolled_back": False, "trigger": reason,
                    "reason": f"restore command failed (rc={rc}): {err.strip()[:300]}",
                    "stdout": out[-1000:]}
        self._sleep(self.health_wait_s)
        healthy, health_note = self._health(record.service)
        if healthy:
            healthy, quality_note = self._quality_gate(record.service, "live", record.previous_image)
            if not healthy:
                health_note = quality_note
        if self.state:
            self.state.mark_rolled_back(record.order_id)
        return {"rolled_back": True, "trigger": reason, "restored_image": record.previous_image,
                "service": record.service, "healthy_after_rollback": healthy,
                "health": health_note,
                # The honest bad case: we reverted and the OLD image is not healthy either. That is
                # not a rollback failure, it is a host that needs a human, and it must not read as ok.
                "needs_human": not healthy}

    def _journal(self, record: DeployRecord) -> None:
        if self.state:
            self.state.record(record)
