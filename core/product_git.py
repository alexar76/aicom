"""Local Git operations on generated code without trusting product Git policy.

Git configuration, hooks and environment variables can execute programs even for
``status`` or ``add``. Generated files must never supply that policy. Existing
ordinary repositories remain usable; nonstandard metadata needs manual review.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path


class UnsafeProductGit(ValueError):
    """The product contains Git metadata the factory cannot safely process."""


def private_metadata_path(code_dir: Path) -> Path:
    """Factory-owned state, never inside a generated product's writable mount."""
    from core.paths import data_root

    root = Path(code_dir).resolve()
    store = data_root().resolve() / "private_product_git"
    if store == root or store.is_relative_to(root):
        raise UnsafeProductGit("Private Git storage must be outside generated code")
    identity = hashlib.sha256(os.fsencode(str(root))).hexdigest()
    return store / identity / "repo"


def has_product_git(code_dir: Path) -> bool:
    """Compatibility check only; ProductGit validates before using any metadata."""
    return private_metadata_path(code_dir).exists() or os.path.lexists(Path(code_dir) / ".git")


def _private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise UnsafeProductGit("Private Git storage requires an owned mode-0700 directory")
    finally:
        os.close(fd)


_CORE_KEYS = frozenset({
    "repositoryformatversion", "filemode", "bare", "logallrefupdates",
    "ignorecase", "precomposeunicode", "symlinks", "autocrlf", "eol",
    "safecrlf", "quotepath", "compression", "abbrev", "checkstat",
    "trustctime", "protecthfs", "protectntfs", "longpaths",
})
_REMOTE_KEY = re.compile(r"remote\.[a-z0-9][a-z0-9._/-]*\.(url|pushurl|fetch)$")
_BRANCH_KEY = re.compile(r"branch\.[a-z0-9][a-z0-9._/-]*\.(remote|merge|rebase)$")
_FIXED_CONFIG = (
    "core.hooksPath=/dev/null", "core.fsmonitor=false", "core.untrackedCache=false",
    "core.attributesFile=/dev/null", "core.excludesFile=/dev/null",
    "core.pager=cat", "core.editor=/bin/false", "commit.gpgSign=false",
    "tag.gpgSign=false", "credential.helper=", "credential.interactive=false",
    "protocol.allow=never", "protocol.https.allow=always", "http.followRedirects=false",
    "submodule.recurse=false", "core.protectHFS=true", "core.protectNTFS=true",
)
_FORBIDDEN_METADATA = frozenset({
    "commondir", "config.worktree", "worktrees", "modules",
    "objects/info/alternates", "objects/info/http-alternates",
})


def _read_regular(path: Path, *, limit: int = 1_048_576) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise UnsafeProductGit("Unsafe Git metadata file; manual review required")
        with os.fdopen(fd, "rb", closefd=False) as source:
            value = source.read(limit + 1)
        if len(value) > limit:
            raise UnsafeProductGit("Git metadata is too large; manual review required")
        return value
    finally:
        os.close(fd)


class ProductGit:
    """Run factory-selected commands only, with a private environment and policy."""

    def __init__(self, code_dir: Path):
        self.root = Path(code_dir).absolute()
        self.metadata = private_metadata_path(self.root)
        self._temporary: tempfile.TemporaryDirectory | None = None
        self._lock_fd: int | None = None

    def __enter__(self) -> ProductGit:
        if self.root.is_symlink() or not self.root.is_dir():
            raise UnsafeProductGit("Git requires a real product directory")
        self.root = self.root.resolve()
        self.metadata = private_metadata_path(self.root)
        # Fixed system locations never consult a product-controlled PATH.
        self.binary = next((p for p in ("/usr/bin/git", "/bin/git") if os.access(p, os.X_OK)), None)
        if self.binary is None:
            raise FileNotFoundError("git executable not found")
        self._temporary = tempfile.TemporaryDirectory(prefix="aicom-product-git-")
        self.home = Path(self._temporary.name)
        (self.home / "template").mkdir()
        # An allowlist is deliberate: LD_*, DYLD_*, GIT_CONFIG_COUNT/PARAMETERS,
        # GIT_EXEC_PATH, SSH_AUTH_SOCK, provider credentials and parent HOME never
        # reach Git or its HTTPS helper.
        self.env = {
            "PATH": "/usr/bin:/bin", "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home),
            "TMPDIR": str(self.home),
            "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/false", "SSH_ASKPASS": "/bin/false",
            "GIT_SSH_COMMAND": "/bin/false", "GIT_ALLOW_PROTOCOL": "https",
            "GIT_PROTOCOL_FROM_USER": "0", "GIT_NO_REPLACE_OBJECTS": "1",
        }
        try:
            self._lock()
            self._validate_worktree()
            if not self.metadata.exists():
                self._migrate_metadata()
            self._validate()
        except OSError as exc:
            self.__exit__()
            raise UnsafeProductGit("Unsafe or changing Git metadata; manual review required") from exc
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        if self._temporary is not None:
            self._temporary.cleanup()

    def _lock(self) -> None:
        # Product writers cannot access this store. Serialize whole multi-command
        # operations across factory processes, not merely one Git invocation.
        store = self.metadata.parent.parent
        store.parent.mkdir(parents=True, exist_ok=True)
        _private_directory(store)
        _private_directory(self.metadata.parent)
        fd = os.open(self.metadata.parent / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
                raise UnsafeProductGit("Unsafe private Git lock")
            deadline = time.monotonic() + 20
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise UnsafeProductGit("Product Git operation already running") from None
                    time.sleep(0.05)
        except BaseException:
            os.close(fd)
            raise
        self._lock_fd = fd

    def _migrate_metadata(self) -> None:
        """Import once through anchored no-follow descriptors, then validate the copy.

        Checking mutable source paths and later copying/running them is unsafe:
        a generated container can replace config or a directory in between.
        Git never opens the original metadata, including after migration.
        """
        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                source_fd = os.open(".git", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            except FileNotFoundError:
                return
        finally:
            os.close(root_fd)
        temporary = None
        target = self.metadata
        try:
            temporary = Path(tempfile.mkdtemp(prefix="import-", dir=self.metadata.parent))
            self._copy_metadata(source_fd, temporary)
            # Only the private copy is authoritative. Mutations of the source
            # during/after validation cannot install executable Git policy.
            self.metadata = temporary
            self._validate_metadata()
            self.metadata = target
            os.replace(temporary, target)
        finally:
            self.metadata = target
            os.close(source_fd)
            if temporary is not None and temporary.exists():
                shutil.rmtree(temporary)

    def _copy_metadata(self, source_fd: int, destination: Path) -> None:
        count = 0
        total = 0
        limit = 512 * 1024 * 1024

        def copy_directory(directory_fd: int, target: Path, prefix: str = "") -> None:
            nonlocal count, total
            for name in os.listdir(directory_fd):
                count += 1
                relative = f"{prefix}/{name}" if prefix else name
                if count > 100_000 or relative.count("/") > 32 or relative.lower() in _FORBIDDEN_METADATA:
                    raise UnsafeProductGit("Git metadata needs manual review")
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    try:
                        (target / name).mkdir(mode=0o700)
                        copy_directory(child_fd, target / name, relative)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(info.st_mode):
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                    try:
                        before = os.fstat(fd)
                        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                            raise UnsafeProductGit("Unsafe or shared Git metadata")
                        with (target / name).open("xb") as output:
                            os.chmod(target / name, 0o600)
                            while chunk := os.read(fd, 1024 * 1024):
                                total += len(chunk)
                                if total > limit:
                                    raise UnsafeProductGit("Git metadata needs manual review")
                                output.write(chunk)
                        after = os.fstat(fd)
                        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            raise UnsafeProductGit("Git metadata changed during import; retry required")
                    finally:
                        os.close(fd)
                else:
                    raise UnsafeProductGit("Unsafe Git metadata; manual review required")

        copy_directory(source_fd, destination)

    def _validate_config(self) -> None:
        config = self.metadata / "config"
        if not config.exists():
            raise UnsafeProductGit("Git configuration missing; manual review required")
        contents = _read_regular(config)
        # Parse only the already-opened bytes, from an empty directory. Never
        # discover a repository or follow even an unconditional include.
        parsed = subprocess.run(
            [self.binary, "config", "--no-includes", "--null", "--file", "-", "--list"],
            input=contents, cwd=self.home, env=self.env, capture_output=True, timeout=5,
        )
        if parsed.returncode:
            raise UnsafeProductGit("Invalid Git configuration; manual review required")
        for record in parsed.stdout.split(b"\0"):
            if not record:
                continue
            key_bytes, _, value_bytes = record.partition(b"\n")
            key = key_bytes.decode("utf-8", "strict").lower()
            value = value_bytes.decode("utf-8", "strict")
            # Git init records the explicit trusted --work-tree when its git-dir
            # lives elsewhere. No arbitrary product-chosen redirection is valid.
            if key == "core.worktree" and value == str(self.root):
                continue
            if key.startswith("core.") and key[5:] in _CORE_KEYS:
                if key == "core.bare" and value.lower() not in ("false", "no", "off", "0"):
                    raise UnsafeProductGit("Bare product repositories are not supported")
                continue
            if key in ("user.name", "user.email", "init.defaultbranch"):
                continue
            if key == "extensions.objectformat" and value in ("sha1", "sha256"):
                continue
            if _BRANCH_KEY.fullmatch(key):
                continue
            remote = _REMOTE_KEY.fullmatch(key)
            if remote:
                if remote.group(1) in ("url", "pushurl"):
                    from web.backend.services.url_safety import validate_git_remote_url

                    try:
                        if not validate_git_remote_url(value):
                            raise ValueError("Empty remote")
                    except ValueError as exc:
                        raise UnsafeProductGit("Unsafe product Git remote; manual review required") from exc
                continue
            # Reject includes, aliases, filters, credentials, signing, fsmonitor,
            # SSH/transport commands, URL rewrites and future executable policy.
            raise UnsafeProductGit("Untrusted Git configuration; manual review required")

    def _validate_metadata(self) -> None:
        if self.metadata.is_symlink():
            raise UnsafeProductGit("External Git metadata is not supported")
        if self.metadata.exists():
            if not self.metadata.is_dir():
                raise UnsafeProductGit("External Git directories/worktrees are not supported")
            pending = [self.metadata]
            count = 0
            while pending:
                directory = pending.pop()
                with os.scandir(directory) as entries:
                    for entry in entries:
                        count += 1
                        if count > 100_000:
                            raise UnsafeProductGit("Git metadata needs manual review")
                        path = Path(entry.path)
                        rel = path.relative_to(self.metadata).as_posix().lower()
                        info = entry.stat(follow_symlinks=False)
                        if (
                            rel in _FORBIDDEN_METADATA
                            or stat.S_ISLNK(info.st_mode)
                            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
                            or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
                        ):
                            raise UnsafeProductGit("Unsafe or shared Git metadata; manual review required")
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(path)
            self._validate_config()

    def _validate_worktree(self) -> None:
        # Embedded repositories can contain their own gitdir indirections and
        # policy. Git may inspect these when staging; require manual removal.
        for directory, names, files in os.walk(self.root, followlinks=False):
            for name in names + files:
                if name.casefold() == ".git" and Path(directory) != self.root:
                    raise UnsafeProductGit("Nested Git metadata is not supported")
                if name.casefold() == ".git" and name != ".git":
                    raise UnsafeProductGit("Ambiguous Git metadata is not supported")
            if Path(directory) == self.root:
                names[:] = [name for name in names if name != ".git"]

    def _validate(self) -> None:
        self._validate_metadata()
        self._validate_worktree()

    def run(self, args: list[str], *, timeout: int = 10, text: bool = True) -> subprocess.CompletedProcess:
        """Arguments are chosen by factory code, never by generated output."""
        self._validate()
        config = [item for setting in _FIXED_CONFIG for item in ("-c", setting)]
        return subprocess.run(
            [self.binary, "--no-pager", *config, f"--git-dir={self.metadata}",
             f"--work-tree={self.root}", *args],
            cwd=self.root, env=self.env, capture_output=True, text=text, timeout=timeout,
        )

    def init(self) -> subprocess.CompletedProcess:
        return self.run(["init", f"--template={self.home / 'template'}"])
