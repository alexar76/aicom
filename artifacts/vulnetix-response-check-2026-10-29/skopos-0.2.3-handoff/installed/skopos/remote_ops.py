"""The closed vocabulary of things SKOPOS may ask a monitored host to do.

Every remote action is a :class:`RemoteOp`: a name, validated arguments, and the
shell script that implements it. Two transports consume the same op:

``direct``
    the script is piped into the host's shell over SSH. This is the historical
    behaviour and needs a shell-capable account on the far end.

``wrapper``
    only ``op.token`` crosses the wire, as ``SSH_ORIGINAL_COMMAND`` for a key
    pinned to ``command="/usr/local/bin/skopos-collect"``. The host re-derives
    the script from its own copy of the catalogue, so a stolen key buys the
    attacker exactly this list and nothing else.

Because the wrapper matches on ``op.token``, the token grammar is deliberately
narrow — see :func:`_token_arg`. Anything that cannot be expressed in it is not
expressible over a restricted key, which is the correct failure direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import remote_scripts
from .shell_safe import validate_docker_name, validate_log_path
from .ssh import SSHConnInfo, run_command

#: Bumped whenever the op vocabulary or a script's output format changes in a way
#: an older installed wrapper would get wrong. ``skopos-collect --protocol``
#: reports the version it was generated for; a mismatch is surfaced, not ignored.
PROTOCOL_VERSION = 1

#: Tokens travel through ``SSH_ORIGINAL_COMMAND`` and get split on whitespace by
#: the wrapper, so an argument may not contain any. The character class is an
#: allow-list rather than a deny-list: shell metacharacters, quotes, backslashes,
#: newlines and glob characters are all absent from it by construction.
_TOKEN_ARG_RE = re.compile(r"^[A-Za-z0-9_./:@=+-]+$")

_MIN_LINES = 100
_MAX_LINES = 100_000


class OpError(ValueError):
    """An op could not be built because its arguments failed validation."""


def _token_arg(value: str, *, label: str) -> str:
    if not _TOKEN_ARG_RE.match(value or ""):
        raise OpError(
            f"{label} cannot be sent over a restricted key: {value!r} contains "
            "characters outside [A-Za-z0-9_./:@=+-]"
        )
    if value.startswith("-"):
        raise OpError(f"{label} must not start with '-': {value!r}")
    return value


def _clamp_lines(lines: int) -> int:
    return max(_MIN_LINES, min(_MAX_LINES, int(lines)))


@dataclass(frozen=True)
class RemoteOp:
    """One permitted remote action, in both of its representations."""

    name: str
    args: tuple[str, ...]
    script: str
    timeout_s: int

    @property
    def token(self) -> str:
        """The ``SSH_ORIGINAL_COMMAND`` payload for wrapper mode."""
        return " ".join((self.name, *self.args))


# --- Fixed ops (no arguments) ----------------------------------------------

def op_ping() -> RemoteOp:
    return RemoteOp("ping", (), remote_scripts.PING, 12)


def op_probe() -> RemoteOp:
    return RemoteOp("probe", (), remote_scripts.PROBE, 90)


def op_port_knocks() -> RemoteOp:
    return RemoteOp("port-knocks", (), remote_scripts.PORT_KNOCKS, 90)


def op_discover_docker() -> RemoteOp:
    return RemoteOp("discover-docker", (), remote_scripts.DISCOVER_DOCKER, 30)


def op_discover_nginx_logs() -> RemoteOp:
    return RemoteOp("discover-nginx-logs", (), remote_scripts.DISCOVER_NGINX_LOGS, 30)


def op_discover_apache_logs() -> RemoteOp:
    return RemoteOp("discover-apache-logs", (), remote_scripts.DISCOVER_APACHE_LOGS, 30)


# --- Parametrised ops -------------------------------------------------------

def op_tail(path: str, lines: int) -> RemoteOp:
    """Tail a log file. ``path`` must be absolute and free of shell metacharacters."""
    clean = validate_log_path(path)
    n = _clamp_lines(lines)
    return RemoteOp(
        "tail",
        (_token_arg(clean, label="Log path"), str(n)),
        remote_scripts.tail_file(clean, n),
        60,
    )


def op_docker_logs(container: str, lines: int) -> RemoteOp:
    """Read a container's recent stdout."""
    clean = validate_docker_name(container)
    n = _clamp_lines(lines)
    return RemoteOp(
        "docker-logs",
        (_token_arg(clean, label="Container name"), str(n)),
        remote_scripts.docker_logs(clean, n),
        60,
    )


#: Ops that take no arguments, keyed by name. The wrapper generator walks this to
#: build its dispatch table, so adding an op here is the only place it is added.
FIXED_OPS = {
    op.name: op
    for op in (
        op_ping(),
        op_probe(),
        op_port_knocks(),
        op_discover_docker(),
        op_discover_nginx_logs(),
        op_discover_apache_logs(),
    )
}

#: Ops that take arguments. The wrapper validates these itself rather than
#: trusting the token, so the grammar is stated once here and enforced twice.
PARAM_OPS = ("tail", "docker-logs")

OP_NAMES = (*FIXED_OPS.keys(), *PARAM_OPS)


# --- Transport --------------------------------------------------------------

def ssh_info(server) -> SSHConnInfo:
    """Connection details for a :class:`~skopos.config.ServerConfig`.

    Lives here rather than in four modules that each grew their own copy.
    """
    if getattr(server, "transport", "direct-ssh") == "agent-push":
        # Reaching out to a push host would recreate the inbound credential the
        # transport exists to remove, so this is a programming error, not a
        # fallback.
        raise ValueError(
            f"server '{getattr(server, 'name', '?')}' uses agent-push; "
            "SKOPOS never connects to it"
        )
    ssh = server.ssh
    return SSHConnInfo(
        host=ssh.host,
        port=ssh.port,
        user=ssh.user,
        key_path=ssh.key_path,
        key_passphrase_env=ssh.key_passphrase_env,
        forced_command=getattr(ssh, "mode", "direct") == "wrapper",
        known_hosts_path=getattr(ssh, "known_hosts_path", None),
    )


def run_op(info: SSHConnInfo, op: RemoteOp, *, timeout_s: int | None = None) -> str:
    """Execute an op over SSH, sending whatever the far end is willing to accept."""
    payload = op.token if info.forced_command else op.script
    return run_command(info, payload, timeout_s=timeout_s or op.timeout_s)


def run_server_op(server, op: RemoteOp, *, timeout_s: int | None = None) -> str:
    """Convenience wrapper: build the connection from a server config and run ``op``."""
    return run_op(ssh_info(server), op, timeout_s=timeout_s)


# --- agent-ssh --------------------------------------------------------------
#
# When the far end is ``skopos-node`` behind a forced command, the vocabulary is
# two verbs and nothing else. There is no path, no container name and no count
# on the wire, so the injection and traversal classes that a parametrised op
# has to defend against simply do not arise. What the host is willing to read is
# decided by a root-owned file on the host.

AGENT_VERBS = ("ping", "collect")


def agent_request(verb: str) -> str:
    if verb not in AGENT_VERBS:
        raise OpError(f"unknown agent verb: {verb!r}")
    return f"v1 {verb}"


def run_agent_op(server, verb: str, *, timeout_s: int = 120) -> str:
    """Ask an agent-ssh host for one thing and return its raw stdout."""
    info = ssh_info(server)
    out = run_command(info, agent_request(verb), timeout_s=timeout_s)
    # run_command appends "# STDERR:\n<all of stderr>". Dropping only the marker
    # line left the stderr text glued to the JSON document, so any warning on the
    # host — a locale notice, a sudo banner — made the response unparseable.
    marker = out.find("# STDERR:")
    if marker != -1:
        out = out[:marker]
    return out.strip()
