"""Committing a machine-authored patch to a branch — the conductor's git hand.

The Factory produces a *diff*. That diff has to become a commit before anything can build it, and it
has to land somewhere a human can read, review and revert. This module does that, and only that.

Three properties are deliberate, and each one is a refusal rather than a preference:

**Branch only, never main, never force.** The worst thing a stolen credential can do here is create a
branch nobody merges. ``main`` protection on the server is a second, independent policy — one of
them being misconfigured must not be enough.

**Two commits, in this order, because the chain cannot be complete at push time.** The build needs a
commit to build; the gate verdict only exists after the build; the agent's result only after the
deploy. So the patch is pushed first, and the provenance sidecar is pushed afterwards as a second
commit. Writing a sidecar up front would mean fabricating an ``agent_result`` that had not happened —
and a provenance record that invents a field is worse than one that omits it.

**The sidecar satisfies the MERGE-SIDE validator, not the design doc.** ``scripts/pull_momus_fixes.sh``
is executable code that gates the merge, so it wins where the two disagree: it wants ``finding_id``,
``component``, ``gate_verdict``, ``conductor_pubkey`` and ``history`` at the TOP level, insists on
``gate_verdict.fixed is True`` with a named verifier key, and **rejects any record containing a bare
IPv4**. That last rule is load-bearing rather than cosmetic — this repo has a standing incident about
private hosts leaking into committed files — so every string that reaches the record is scrubbed.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

#: The merge-side validator rejects a record containing one of these, so redact before writing
#: rather than discovering it when a human tries to merge the branch.
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_FINDING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_GIT_TIMEOUT_S = 300
#: The first call clones a bare mirror of a ~1GB repository. Over loopback that is disk-speed, but
#: 300s is not a margin worth betting a cold start on.
_CLONE_TIMEOUT_S = 1800


def valid_finding_id(value: Any) -> bool:
    """Whether an id is safe in both a git ref suffix and a filesystem path."""
    return bool(_FINDING_ID.fullmatch(str(value or "")))


def scrub(value: Any, *, limit: int = 2000) -> Any:
    """Recursively remove bare IPv4 addresses and cap string length.

    Applied to everything that reaches the sidecar. The inputs include MOMUS's ``detail`` and the
    node agent's captured stderr — third-party text, unbounded, and exactly where a private host
    would show up."""
    if isinstance(value, str):
        return _IPV4.sub("[ip-redacted]", value)[:limit]
    if isinstance(value, dict):
        return {k: scrub(v, limit=limit) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, limit=limit) for v in value[:100]]
    return value


def short_signature(sig: Any) -> dict[str, Any]:
    """A signature as a correlatable PREFIX, never whole.

    Enough for a human to match this record against the order queue; useless as a credential. The
    verifying key travels in full — it is public by construction."""
    if not isinstance(sig, dict):
        return {}
    value = str(sig.get("value") or "")
    return {k: v for k, v in sig.items() if k != "value"} | (
        {"value_prefix": value[:16] + "…"} if value else {})


def ssh_remote_is_local(url: str) -> bool:
    """Is an SSH git remote on this host: localhost, a loopback address, or a container name
    (a single label, resolved on the private docker network)?"""
    url = (url or "").strip()
    if "://" in url:
        host = urlsplit(url).hostname or ""
    else:  # scp-like: [user@]host:path
        host = url.split(":", 1)[0].rsplit("@", 1)[-1] if ":" in url else ""
    host = host.strip("[]").lower()
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return "." not in host


@dataclass
class GitPushConfig:
    repo_url: str = ""                 # loopback Gitea, e.g. http://127.0.0.1:3000/alexar76/aicom.git
    work_root: str = "data/remediation/git"
    branch_prefix: str = "momus/fix-"
    author_name: str = "SKOPOS remediation conductor"
    author_email: str = "skopos-remediation@localhost"
    #: Two credential styles, and the SSH one is the default for a reason. Gitea ACCESS TOKENS are
    #: USER-scoped: `write:repository` covers every repository that user owns. A **deploy key** is
    #: per-repository, and — decisively — `push_whitelist_deploy_keys` is false on this repo's `main`
    #: protection, so a deploy key cannot reach `main` at all, while the owner's own account can.
    #: That is the second, independent policy the design asks for.
    token: str = ""
    #: Path to the private half of a write deploy key. Takes precedence over `token`.
    ssh_key_path: str = ""
    protected_branches: tuple[str, ...] = ("main", "master")
    #: EXPERIMENTAL. Merge a verified fix branch into the default branch, unattended.
    #:
    #: Off, and off is the design. "Branch only, never main" is what makes a stolen conductor
    #: credential a nuisance rather than an incident: the worst it can do is create a branch
    #: nobody merges. Turning this on changes that sentence, and it is the only thing in this
    #: module that does.
    #:
    #: It is also not sufficient on its own. The conductor pushes with a DEPLOY KEY, and this
    #: repository's `main` protection has `push_whitelist_deploy_keys` false — so the server
    #: refuses that key on `main` whatever this flag says. Enabling the merge therefore takes a
    #: second, deliberate act by the repository owner: whitelist the deploy key on `main`, or
    #: give the conductor an account token. Both widen what a compromise reaches. The flag is
    #: here so the decision is explicit and revertible, not so it is easy.
    #:
    #: Reversible two ways: unset the variable, and `git revert -m 1` the merge commit, which is
    #: an ordinary no-fast-forward merge naming the finding it came from.
    auto_merge: bool = False
    default_branch: str = "main"

    @classmethod
    def from_env(cls) -> "GitPushConfig":
        return cls(
            repo_url=os.environ.get("SKOPOS_GIT_REPO_URL", "").strip(),
            work_root=os.environ.get("SKOPOS_GIT_WORK_ROOT", "data/remediation/git").strip(),
            branch_prefix=os.environ.get("SKOPOS_FIX_BRANCH_PREFIX", "momus/fix-").strip() or "momus/fix-",
            token=os.environ.get("SKOPOS_GIT_TOKEN", "").strip(),
            ssh_key_path=os.environ.get("SKOPOS_GIT_SSH_KEY", "").strip(),
            auto_merge=os.environ.get("SKOPOS_EXPERIMENTAL_AUTO_MERGE", "").strip().lower()
                       in ("1", "true", "yes", "on"),
            default_branch=os.environ.get("SKOPOS_DEFAULT_BRANCH", "main").strip() or "main",
        )

    @property
    def configured(self) -> bool:
        return bool(self.repo_url)


@dataclass
class PushResult:
    ok: bool
    branch: str = ""
    commit_sha: str = ""
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "branch": self.branch, "commit_sha": self.commit_sha,
                "error": self.error, **({"details": self.details} if self.details else {})}


_GIT_CONFIG_ENV = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
_ENV_LOCK = threading.Lock()


class GitPusher:
    """Bare mirror + one worktree per finding. Never a shared checkout, never a shared branch."""

    def __init__(self, config: GitPushConfig | None = None, *, runner: Any = None):
        self.cfg = config or GitPushConfig.from_env()
        self._run = runner or self._subprocess_run

    @staticmethod
    def _subprocess_run(argv: list[str], cwd: str | None = None,
                        stdin: str | None = None) -> tuple[int, str, str]:
        timeout = _CLONE_TIMEOUT_S if "clone" in argv else _GIT_TIMEOUT_S
        try:
            proc = subprocess.run(argv, cwd=cwd, input=stdin, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            return proc.returncode, proc.stdout, proc.stderr
        except (subprocess.SubprocessError, OSError) as exc:
            return 127, "", f"{type(exc).__name__}: {exc}"

    # ── paths ───────────────────────────────────────────────────────────────
    @property
    def mirror(self) -> str:
        return os.path.join(self.cfg.work_root, "repo.git")

    def worktree(self, finding_id: str) -> str:
        if not valid_finding_id(finding_id):
            raise ValueError("finding_id is not safe for a worktree path")
        return os.path.join(self.cfg.work_root, "wt", finding_id)

    def branch_for(self, finding_id: str, attempt: int = 0) -> str:
        """One branch per ATTEMPT, not per finding.

        A job that is re-opened authors a second patch against the same base, and pushing it to
        the branch the first attempt already occupies is a non-fast-forward. Forcing is refused
        (rightly: a diverged fix branch may be one a human is reading), so every retry after the
        first failed at the push with "a human must reconcile it" — measured on the first real
        autonomous run. A suffixed branch always fast-forwards because it is new, and the attempts
        stay side by side for whoever reviews them.

        Attempt 0 keeps the original name, so existing branches, orders and tests are unaffected.
        """
        if not valid_finding_id(finding_id):
            raise ValueError("finding_id is not safe for a git branch")
        base = f"{self.cfg.branch_prefix}{finding_id}"
        return base if attempt <= 0 else f"{base}-{int(attempt)}"

    #: How far to walk looking for an unused branch name before giving up. A finding that has
    #: genuinely been remediated two hundred times is not a push problem.
    MAX_BRANCH_PROBE = 200

    def free_branch_for(self, finding_id: str, attempt: int = 0) -> str:
        """The first branch name for this finding the remote does not already hold.

        `attempt` alone is not unique, and could not be: a re-opened job resets its attempt
        budget to zero by design, so the second re-open computes the same name as the first
        and pushes a different commit to it. That is a non-fast-forward, forcing is refused
        (rightly — a diverged fix branch may be one a human is reading), and the whole
        autonomous cycle died at the push with "a human must reconcile it". Measured on a live
        run: the autopilot dispatched, the Factory authored a patch in seven seconds, and the
        loop stopped on a branch name.

        Reading the mirror rather than the remote: `_ensure_mirror` has just fetched
        `+refs/heads/*:refs/remotes/origin/*`, so this is a local lookup of a fresh answer.
        Unreadable refs fall back to the plain `attempt` name — a push that then collides is
        no worse off than before, and still never forces.
        """
        base = self.branch_for(finding_id, 0)
        rc, out, _ = self._git("-C", self.mirror, "for-each-ref", "--format=%(refname:short)",
                               f"refs/remotes/origin/{base}", f"refs/remotes/origin/{base}-*")
        if rc != 0:
            return self.branch_for(finding_id, attempt)
        taken = {line.strip().removeprefix("origin/") for line in (out or "").splitlines()
                 if line.strip()}
        ordinal = max(0, int(attempt))
        while ordinal <= self.MAX_BRANCH_PROBE:
            name = self.branch_for(finding_id, ordinal)
            if name not in taken:
                return name
            ordinal += 1
        return self.branch_for(finding_id, ordinal)

    def _ordinal_of(self, finding_id: str, branch: str) -> int:
        """The numeric suffix of a branch this class produced (0 for the unsuffixed name)."""
        base = self.branch_for(finding_id, 0)
        if branch == base:
            return 0
        tail = branch.removeprefix(base + "-")
        return int(tail) if tail.isdigit() else 0

    def _git(self, *args: str, cwd: str | None = None, stdin: str | None = None):
        """git with the credential supplied out of band — never interpolated into the URL.

        A credential in a URL ends up in git's own logs, in reflogs and in the process list of
        anything that can read /proc. So an HTTP token travels as a header, and an SSH key travels as
        ``GIT_SSH_COMMAND``."""
        argv = ["git"]
        if self.cfg.ssh_key_path:
            # IdentitiesOnly so a stray agent key cannot be tried instead. Host keys go unchecked
            # only for a remote on this host (loopback, or a container name on the private docker
            # network): no MITM position there, and a pinned key would break on every Gitea
            # recreate. The remote is configurable, though, and any other host is pinned on first
            # use and refused if its key changes (the CWE-295 class Vulnetix found in skopos-fleet).
            if ssh_remote_is_local(self.cfg.repo_url):
                checking = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            else:
                known = os.path.expanduser(os.environ.get("SKOPOS_KNOWN_HOSTS") or "~/.skopos/known_hosts")
                os.makedirs(os.path.dirname(known), exist_ok=True)
                checking = f"-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile={shlex.quote(known)}"
            ssh = (f"ssh -i {shlex.quote(self.cfg.ssh_key_path)} -o IdentitiesOnly=yes "
                   f"{checking} -o BatchMode=yes")
            argv = ["git", "-c", f"core.sshCommand={ssh}"]
        argv += list(args)
        if not self.cfg.ssh_key_path and self.cfg.token:
            # NOT `-c http.extraHeader=...`: that put the token in argv, and
            # /proc/<pid>/cmdline is world-readable — the very exposure the docstring above
            # forbids, two lines after forbidding it. git reads config from
            # GIT_CONFIG_COUNT/KEY/VALUE (git >= 2.31), so the token travels in the
            # environment instead, where /proc/<pid>/environ is readable only by the same UID
            # and root. Not secret from root; no longer readable by every user on the host.
            with _ENV_LOCK:
                previous = {k: os.environ.get(k) for k in _GIT_CONFIG_ENV}
                os.environ["GIT_CONFIG_COUNT"] = "1"
                os.environ["GIT_CONFIG_KEY_0"] = "http.extraHeader"
                os.environ["GIT_CONFIG_VALUE_0"] = f"Authorization: token {self.cfg.token}"
                try:
                    return self._run(argv, cwd, stdin)
                finally:
                    for key, was in previous.items():
                        if was is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = was
        return self._run(argv, cwd, stdin)

    # ── mirror ──────────────────────────────────────────────────────────────
    def _ensure_mirror(self) -> tuple[bool, str]:
        """A bare mirror once, then incremental fetches, and ALWAYS a fetch.

        The fetch is not only for freshness. A `--bare` clone puts the upstream heads in
        `refs/heads/*`; the remote-tracking refs this class bases worktrees on
        (`refs/remotes/origin/*`) are created by the fetch refspec below. Cloning and returning left
        the very first job with no `refs/remotes/origin/main` and a `fatal: invalid reference` — a
        failure that could only ever happen on a cold mirror, which is why no test caught it and a
        live run did."""
        os.makedirs(self.cfg.work_root, exist_ok=True)
        if not os.path.isdir(os.path.join(self.mirror, "objects")):
            # This repo's .git is ~1GB, so a clone per job is not viable; over loopback the one-off
            # clone runs at disk speed.
            rc, _, err = self._git("clone", "--bare", self.cfg.repo_url, self.mirror)
            if rc != 0:
                return False, f"clone failed: {err.strip()[:300]}"
        rc, _, err = self._git("-C", self.mirror, "fetch", "--prune", "origin",
                               "+refs/heads/*:refs/remotes/origin/*")
        return (rc == 0), ("" if rc == 0 else f"fetch failed: {err.strip()[:300]}")

    def _base_ref(self) -> str:
        """The upstream default branch to base a fix on, as a ref that actually resolves."""
        rc, out, _ = self._git("-C", self.mirror, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        branch = out.strip().split("/")[-1] if rc == 0 and out.strip() else ""
        for candidate in (f"refs/remotes/origin/{branch}" if branch else "",
                          "refs/remotes/origin/main", "refs/remotes/origin/master",
                          # A bare clone keeps upstream heads here; kept as a fallback so a mirror
                          # that somehow has no remote-tracking refs still produces a usable base
                          # instead of a "fatal: invalid reference".
                          f"refs/heads/{branch}" if branch else "",
                          "refs/heads/main", "refs/heads/master"):
            if not candidate:
                continue
            rc, _, _ = self._git("-C", self.mirror, "rev-parse", "--verify", "--quiet", candidate)
            if rc == 0:
                return candidate
        return "refs/remotes/origin/main"

    def _prepare_worktree(self, finding_id: str, component: str = "") -> tuple[str, str]:
        wt = self.worktree(finding_id)
        self._cleanup(finding_id)
        os.makedirs(os.path.dirname(wt), exist_ok=True)
        base = self._base_ref()
        if component == "warden":
            # Root-owned accepted source pointer, mounted read-only into the conductor.
            # A later fix starts at the deployed commit, preserving earlier unmerged fixes.
            try:
                with open(os.environ.get("SKOPOS_WARDEN_BASE_FILE", "/warden-state/source.json")) as stream:
                    base = json.load(stream)["commit"]
                if not re.fullmatch(r"[0-9a-f]{40}", base):
                    raise ValueError("invalid accepted commit")
            except (OSError, ValueError, KeyError, TypeError):
                return "", "WARDEN accepted source pointer missing or invalid"
        rc, _, err = self._git("-C", self.mirror, "worktree", "add", "--detach", wt, base)
        if rc != 0:
            return "", f"could not lay out a worktree: {err.strip()[:300]}"
        return wt, ""

    def _cleanup(self, finding_id: str) -> None:
        wt = self.worktree(finding_id)
        self._git("-C", self.mirror, "worktree", "remove", "--force", wt)
        shutil.rmtree(wt, ignore_errors=True)

    def _commit(self, wt: str, message: str) -> tuple[str, str]:
        for key, value in (("user.name", self.cfg.author_name), ("user.email", self.cfg.author_email)):
            self._run(["git", "-C", wt, "config", key, value])
        rc, out, err = self._run(["git", "-C", wt, "commit", "--no-verify", "-m", message])
        if rc != 0:
            return "", f"commit failed: {(err or out).strip()[:300]}"
        rc, out, _ = self._run(["git", "-C", wt, "rev-parse", "HEAD"])
        return (out.strip(), "") if rc == 0 else ("", "could not read the new commit id")

    def _push(self, wt: str, branch: str) -> tuple[bool, str]:
        if branch in self.cfg.protected_branches or not branch.startswith(self.cfg.branch_prefix):
            # Belt and braces on top of server-side protection. A bug that computed the wrong branch
            # name must not be able to reach a protected one.
            return False, f"refusing to push to '{branch}' — not under '{self.cfg.branch_prefix}'"
        rc, out, err = self._git("-C", wt, "push", "origin", f"HEAD:refs/heads/{branch}")
        if rc != 0:
            text = (err or out).strip()
            if "non-fast-forward" in text or "fetch first" in text:
                # Never --force. A diverged fix branch means someone else has been working on it;
                # overwriting their commit is exactly the damage force-push exists to cause.
                return False, (f"push rejected as non-fast-forward for '{branch}' — refusing to "
                               f"force; a human must reconcile it")
            return False, f"push failed: {text[:300]}"
        return True, ""


    # ── EXPERIMENTAL: merging a verified fix into the default branch ─────────
    def merge_to_main(self, *, finding_id: str, branch: str, component: str,
                      summary: str = "") -> PushResult:
        """Merge a verified fix branch into the default branch. OFF unless explicitly enabled.

        Every other path in this module refuses the default branch on principle, and that refusal
        is what keeps a stolen conductor credential a nuisance rather than an incident. This is
        the single exception, and it is written to be hard to reach by accident:

          * it refuses unless ``SKOPOS_EXPERIMENTAL_AUTO_MERGE`` is set;
          * it refuses any branch not under the fix prefix, so it cannot be pointed at something
            a person is working on;
          * it merges with ``--no-ff`` so the result is one revertible commit that names the
            finding, never a fast-forward that silently rewrites what main pointed at;
          * it never forces, and on any conflict it aborts and leaves the default branch
            untouched — a conflict means main moved, and reconciling that is a person's job.

        It is also expected to FAIL on this deployment until somebody decides otherwise: the
        conductor pushes with a deploy key, and the repository's ``main`` protection excludes
        deploy keys. That refusal comes from the server, not from here, and it is a second
        independent policy rather than a redundant one.
        """
        if not self.cfg.auto_merge:
            return PushResult(False, branch=branch,
                              error="auto-merge is off (SKOPOS_EXPERIMENTAL_AUTO_MERGE unset) — "
                                    "the fix branch is pushed and waits for human review")
        if not valid_finding_id(finding_id):
            return PushResult(False, error="finding_id contains unsafe path or git-ref characters")
        if not self.cfg.configured:
            return PushResult(False, error="SKOPOS_GIT_REPO_URL is unset")
        if not branch or not branch.startswith(self.cfg.branch_prefix):
            return PushResult(False, branch=branch,
                              error=f"refusing to merge '{branch}' — not a fix branch under "
                                    f"'{self.cfg.branch_prefix}'")
        target = self.cfg.default_branch
        ok, err = self._ensure_mirror()
        if not ok:
            return PushResult(False, branch=branch, error=err)
        wt, err = self._prepare_worktree(f"{finding_id}-merge")
        if not wt:
            return PushResult(False, branch=branch, error=err)
        try:
            rc, out, err = self._git("-C", wt, "fetch", "origin", target, branch)
            if rc != 0:
                return PushResult(False, branch=branch,
                                  error=f"could not fetch '{target}' and '{branch}': "
                                        f"{(err or out).strip()[:200]}")
            rc, out, err = self._run(["git", "-C", wt, "checkout", "-B", target,
                                      f"origin/{target}"])
            if rc != 0:
                return PushResult(False, branch=branch,
                                  error=f"could not check out '{target}': {(err or out).strip()[:200]}")
            message = (
                f"merge({component}): {summary or finding_id}\n\n"
                f"Fix for MOMUS finding {finding_id}, merged by the conductor.\n"
                f"Deployed and verified in place before this merge; the branch and its signed\n"
                f"provenance record remain at {branch}.\n\n"
                f"Machine-merged under SKOPOS_EXPERIMENTAL_AUTO_MERGE. Revert with\n"
                f"`git revert -m 1 <this commit>`.\n"
            )
            rc, out, err = self._run(["git", "-C", wt, "merge", "--no-ff", "--no-edit",
                                      "-m", message, f"origin/{branch}"])
            if rc != 0:
                # Abort rather than resolve. A conflict means main moved under the fix, and a
                # machine picking a side there is exactly the thing nobody asked for.
                self._run(["git", "-C", wt, "merge", "--abort"])
                return PushResult(False, branch=branch,
                                  error=f"merge into '{target}' conflicted — left untouched: "
                                        f"{(err or out).strip()[:250]}")
            rc, sha, _ = self._run(["git", "-C", wt, "rev-parse", "HEAD"])
            merged = (sha or "").strip()
            rc, out, err = self._git("-C", wt, "push", "origin", f"HEAD:refs/heads/{target}")
            if rc != 0:
                text = (err or out).strip()
                return PushResult(False, branch=branch, commit_sha=merged,
                                  error=f"push to '{target}' refused: {text[:300]}")
            return PushResult(True, branch=target, commit_sha=merged,
                              details={"merged_from": branch, "revert": f"git revert -m 1 {merged}"})
        finally:
            self._cleanup(f"{finding_id}-merge")

    # ── the two pushes ──────────────────────────────────────────────────────
    def push_patch(self, *, finding_id: str, component: str, diff: str, summary: str,
                   verifier_count: int = 0, attempt: int = 0) -> PushResult:
        """Apply the Factory's diff on top of the base branch and push it as a new branch."""
        if not valid_finding_id(finding_id):
            return PushResult(False, error="finding_id contains unsafe path or git-ref characters")
        if not self.cfg.configured:
            return PushResult(False, error="SKOPOS_GIT_REPO_URL is unset — cannot push a fix branch")
        if not diff.strip():
            return PushResult(False, error="the Factory returned no diff — nothing to commit")
        ok, err = self._ensure_mirror()
        if not ok:
            return PushResult(False, error=err)
        wt, err = self._prepare_worktree(finding_id, component=component)
        if not wt:
            return PushResult(False, error=err)
        try:
            # --3way so a diff generated against a slightly older base still applies cleanly;
            # NEVER --reject, which leaves .rej files and a half-applied tree that would then be
            # committed and built as if it were the patch.
            rc, out, aerr = self._run(["git", "-C", wt, "apply", "--3way", "--index", "-"],
                                      None, diff)
            if rc != 0:
                return PushResult(False, error=f"patch did not apply cleanly: "
                                              f"{(aerr or out).strip()[:400]}")
            message = (
                f"fix({component}): {summary or 'remediate ' + finding_id}\n\n"
                f"Authored by the AI-Factory for MOMUS finding {finding_id}.\n"
                + (f"Confirmed by {verifier_count} independent verifier(s).\n" if verifier_count else "")
                + "Provenance chain lands in a follow-up commit on this branch.\n\n"
                "Machine-authored. Requires human review before merge.\n"
            )
            sha, err = self._commit(wt, message)
            if not sha:
                return PushResult(False, error=err)
            branch = self.free_branch_for(finding_id, attempt)
            ok, err = self._push(wt, branch)
            if not ok and ("non-fast-forward" in (err or "") or "fetch first" in (err or "")):
                # Lost a race, or the mirror's view was stale. Walk on to the next free name —
                # never force, and never more than a handful of times.
                probe = branch
                for _ in range(5):
                    ordinal = self._ordinal_of(finding_id, probe) + 1
                    probe = self.branch_for(finding_id, ordinal)
                    ok, err = self._push(wt, probe)
                    if ok:
                        branch = probe
                        break
            if not ok:
                return PushResult(False, branch=branch, commit_sha=sha, error=err)
            return PushResult(True, branch=branch, commit_sha=sha)
        finally:
            self._cleanup(finding_id)

    def push_provenance(self, *, finding_id: str, component: str, record: dict[str, Any],
                        branch: str = "") -> PushResult:
        """Add ``.momus/<finding_id>.json`` to the fix branch as a second commit.

        Separate from the patch because the chain it records — the gate verdict, the deploy order,
        what the agent actually did — does not exist until after the patch has been built and shipped.
        """
        if not valid_finding_id(finding_id):
            return PushResult(False, error="finding_id contains unsafe path or git-ref characters")
        if not self.cfg.configured:
            return PushResult(False, error="SKOPOS_GIT_REPO_URL is unset")
        # The branch the PATCH actually landed on — a retry's provenance belongs on the retry's
        # branch, not on the first attempt's.
        branch = branch or self.branch_for(finding_id)
        ok, err = self._ensure_mirror()
        if not ok:
            return PushResult(False, branch=branch, error=err)
        wt = self.worktree(finding_id + "-prov")
        self._git("-C", self.mirror, "worktree", "remove", "--force", wt)
        shutil.rmtree(wt, ignore_errors=True)
        os.makedirs(os.path.dirname(wt), exist_ok=True)
        rc, _, gerr = self._git("-C", self.mirror, "worktree", "add", "--detach", wt,
                                f"refs/remotes/origin/{branch}")
        if rc != 0:
            return PushResult(False, branch=branch,
                              error=f"could not check out '{branch}' to add provenance: "
                                    f"{gerr.strip()[:300]}")
        try:
            target = os.path.join(wt, ".momus")
            os.makedirs(target, exist_ok=True)
            path = os.path.join(target, f"{finding_id}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=2, ensure_ascii=False, sort_keys=True)
                fh.write("\n")
            rc, _, aerr = self._run(["git", "-C", wt, "add", ".momus"])
            if rc != 0:
                return PushResult(False, branch=branch, error=f"git add failed: {aerr.strip()[:200]}")
            sha, err = self._commit(
                wt, f"chore({component}): provenance chain for {finding_id}\n\n"
                    f"Signed finding, gate verdict, deploy order and the node agent's result, so the "
                    f"audit is readable from git alone.\n\nMachine-authored.\n")
            if not sha:
                return PushResult(False, branch=branch, error=err)
            ok, err = self._push(wt, branch)
            return (PushResult(True, branch=branch, commit_sha=sha) if ok
                    else PushResult(False, branch=branch, commit_sha=sha, error=err))
        finally:
            self._git("-C", self.mirror, "worktree", "remove", "--force", wt)
            shutil.rmtree(wt, ignore_errors=True)


def provenance_record(*, job: Any, gate_verdict: dict[str, Any], deploy_order: dict[str, Any],
                      agent_result: dict[str, Any] | None, conductor_pubkey: str,
                      finding: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the sidecar in the shape the MERGE validator accepts.

    Both shapes at once: the five top-level fields ``scripts/pull_momus_fixes.sh`` reads, and the
    documents ``momus/docs/fix-provenance.md`` names. Signatures travel as prefixes and every string
    is scrubbed of bare IPv4, because the validator rejects the record outright if one survives."""
    def _sig_trim(doc: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(doc, dict):
            return {}
        out = dict(doc)
        if "signature" in out:
            out["signature"] = short_signature(out.get("signature"))
        return out

    verdict = _sig_trim(gate_verdict)
    record = {
        # ── what the merge-side validator requires, at the top level ──
        "finding_id": job.finding_id,
        "component": job.component,
        "gate_verdict": verdict,
        "conductor_pubkey": conductor_pubkey,
        "history": [dict(h) for h in (job.history or [])][-30:],
        # ── what fix-provenance.md names ──
        "finding": _sig_trim(finding) if finding else {"finding_id": job.finding_id,
                                                      "probe": job.probe,
                                                      "severity": job.severity},
        "verdicts": [verdict],
        "fix_verdict": verdict,
        "deploy_order": _sig_trim(deploy_order),
        "flags": list(job.flags or []),
    }
    # `agent_result` is omitted rather than invented when the deploy has not reported yet. A
    # provenance record that fabricates a field is worse than one that is visibly incomplete.
    if agent_result is not None:
        record["agent_result"] = agent_result
    return scrub(record)
