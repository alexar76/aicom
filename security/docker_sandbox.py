"""
Shared hardened ``docker run`` argument builder for preview / isolation sandboxes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


def hardened_docker_run_args(
    *,
    name: str,
    network: str = "none",
    memory: str = "512m",
    cpus: str = "0.5",
    workdir: str = "/workspace",
    volume_mount: str | None = None,
    writable_tmpfs: Sequence[str] | None = None,
    publish_port: int | None = None,
    publish_host: str = "127.0.0.1",
    read_only_root: bool = False,
    pids_limit: int = 64,
    user: str = "65534:65534",
) -> list[str]:
    """
    Build ``docker run`` flags shared by API sandbox and SandboxIsolation container mode.

    Defaults: no network, dropped capabilities, no-new-privileges, non-root, bounded PIDs.

    ``volume_mount`` should normally be passed read-only (``...:/workspace:ro``);
    pass ``writable_tmpfs`` (e.g. ``["/work"]``) to give the workload private,
    non-persistent scratch space instead of letting it write back to the host.
    """
    cmd: list[str] = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--network",
        network,
        "--memory",
        memory,
        "--cpus",
        cpus,
        "--pids-limit",
        str(pids_limit),
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--user",
        user,
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
    ]
    for mount in writable_tmpfs or ():
        cmd.extend(["--tmpfs", f"{mount}:rw,nosuid,size=64m"])
    if read_only_root:
        cmd.append("--read-only")
    if volume_mount:
        cmd.extend(["-v", volume_mount])
    if publish_port is not None:
        # Bind to loopback by default so sandbox previews are not exposed on
        # every host interface (0.0.0.0). Callers that need a public bind can
        # pass publish_host="0.0.0.0" explicitly.
        host_prefix = f"{publish_host}:" if publish_host else ""
        cmd.extend(["-p", f"{host_prefix}{publish_port}:{publish_port}"])
    if workdir:
        cmd.extend(["-w", workdir])
    return cmd


def append_image_and_command(cmd: list[str], image: str, command: Sequence[str] | str) -> list[str]:
    """Append image reference and container command argv."""
    out = list(cmd)
    out.append(image)
    if isinstance(command, str):
        out.extend(["sh", "-lc", command])
    else:
        out.extend(command)
    return out


def assert_hardened_flags_present(cmd: Iterable[str]) -> None:
    """Test helper: verify expected isolation flags are present."""
    flat = list(cmd)
    joined = " ".join(flat)
    for needle in (
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
    ):
        if needle not in joined and needle not in flat:
            raise ValueError(f"missing hardened flag: {needle}")
