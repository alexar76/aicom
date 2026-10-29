"""SSH key helpers, connection tests, and interactive terminal launcher."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .remote_ops import op_ping, run_op
from .ssh import SSHConnInfo

DEFAULT_KEY_CANDIDATES = (
    "~/.ssh/id_ed25519",
    "~/.ssh/id_rsa",
)


@dataclass(frozen=True)
class SSHKeyInfo:
    private_path: str
    public_path: str
    exists: bool


def resolve_key_path(preferred: str | None = None) -> SSHKeyInfo:
    candidates = [preferred] if preferred else list(DEFAULT_KEY_CANDIDATES)
    for raw in candidates:
        if not raw:
            continue
        priv = os.path.expanduser(raw)
        pub = f"{priv}.pub"
        if os.path.isfile(priv):
            return SSHKeyInfo(private_path=priv, public_path=pub, exists=True)
    fallback = os.path.expanduser(preferred or DEFAULT_KEY_CANDIDATES[0])
    return SSHKeyInfo(private_path=fallback, public_path=f"{fallback}.pub", exists=False)


def build_keygen_ed25519_cmd(*, key_path: str = "~/.ssh/id_ed25519") -> str:
    path = os.path.expanduser(key_path)
    return (
        f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
        f'ssh-keygen -t ed25519 -C "stats@$(hostname)" -f {shlex.quote(path)}'
    )


def build_keygen_rsa_cmd(*, key_path: str = "~/.ssh/id_rsa") -> str:
    path = os.path.expanduser(key_path)
    return (
        f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
        f'ssh-keygen -t rsa -b 4096 -C "stats@$(hostname)" -f {shlex.quote(path)}'
    )


def build_ssh_copy_id_cmd(
    *,
    user: str,
    host: str,
    port: int,
    public_key_path: str,
) -> str:
    pub = os.path.expanduser(public_key_path)
    port_flag = f"-p {port} " if port and port != 22 else ""
    return f"ssh-copy-id {port_flag}-i {shlex.quote(pub)} {shlex.quote(f'{user}@{host}')}"


def build_ssh_login_cmd(*, user: str, host: str, port: int, private_key_path: str) -> str:
    priv = os.path.expanduser(private_key_path)
    port_flag = f"-p {port} " if port and port != 22 else ""
    return f"ssh {port_flag}-i {shlex.quote(priv)} {shlex.quote(f'{user}@{host}')}"


def test_ssh_connection(info: SSHConnInfo, *, timeout_s: int = 12) -> tuple[bool, str]:
    try:
        out = run_op(info, op_ping(), timeout_s=timeout_s)
        if "SKOPOS_SSH_OK" in out:
            lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("# STDERR")]
            detail = " · ".join(lines[1:3]) if len(lines) > 1 else "connected"
            return True, detail
        return False, out.strip()[:400] or "Unexpected SSH response"
    except Exception as e:
        return False, str(e)



def open_interactive_terminal(command: str) -> tuple[bool, str]:
    """Open a system terminal running an interactive command (password prompts work)."""
    system = platform.system()
    try:
        if system == "Darwin":
            script_path = Path(os.environ.get("TMPDIR", "/tmp")) / f"stats_cmd_{os.getpid()}.sh"
            script_path.write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
            script_path.chmod(0o700)
            subprocess.Popen(
                ["open", "-a", "Terminal", str(script_path)],
                start_new_session=True,
            )
            return True, "Terminal opened"
        if system == "Linux":
            for term_cmd in (
                ["x-terminal-emulator", "-e", "bash", "-lc", command],
                ["gnome-terminal", "--", "bash", "-lc", command],
                ["konsole", "-e", "bash", "-lc", command],
            ):
                try:
                    subprocess.Popen(term_cmd, start_new_session=True)
                    return True, "Terminal opened"
                except FileNotFoundError:
                    continue
            return False, "No supported terminal emulator found on Linux"
        return False, f"Automatic terminal launch is not supported on {system}"
    except Exception as e:
        return False, str(e)


def public_key_installed_hint(public_key_path: str) -> str | None:
    path = Path(os.path.expanduser(public_key_path))
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip().splitlines()[0][:80]
    except OSError:
        return None
