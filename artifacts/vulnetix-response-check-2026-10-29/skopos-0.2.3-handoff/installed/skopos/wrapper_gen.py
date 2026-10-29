"""Pinning an inbound SSH key to the agent, and nothing else.

This module used to generate a shell program that re-implemented the whole op
grammar on the monitored host. It no longer does. ``skopos-node ssh-op`` answers
a two-word vocabulary — ``v1 ping`` and ``v1 collect`` — and decides what it is
willing to read from a root-owned file on the host, so there is no grammar left
for a second implementation to get subtly wrong.

What remains is the small part that was never about parsing: building the
``authorized_keys`` line and the sshd drop-in that make the key a single command
instead of a shell.
"""

from __future__ import annotations

AGENT_COMMAND = "/usr/local/bin/skopos-node ssh-op"


def authorized_keys_line(
    public_key: str,
    *,
    from_addresses: tuple[str, ...] = (),
    command: str = AGENT_COMMAND,
) -> str:
    """Build the pinned ``authorized_keys`` entry for a collector key.

    ``restrict`` is the important word: it turns off port forwarding, agent
    forwarding, X11 and pty allocation in one option, and keeps doing so as
    OpenSSH adds new things worth turning off. ``command=`` is what stops the key
    being a shell.

    ``from=`` is offered but not encouraged. Behind NAT it authorises every
    process on the collector's whole host rather than the collector, and when an
    ISP renumbers it fails at three in the morning — which is how deployments end
    up with ``from="0.0.0.0/0"`` and a false sense of restriction. It is worth
    setting only when the collector reaches the host over a tunnel with a fixed
    address.

    The options are assembled as a fixed tuple, never concatenated from caller
    input: a later ``port-forwarding`` token on the same line would silently
    re-enable what ``restrict`` removed.
    """
    key = " ".join((public_key or "").split())
    if not key:
        raise ValueError("public key is empty")
    if "\n" in public_key or "\r" in public_key:
        raise ValueError("public key must be a single line")
    if '"' in command:
        raise ValueError("command must not contain quotes")

    opts = [f'command="{command}"', "restrict"]
    if from_addresses:
        for addr in from_addresses:
            if '"' in addr or "," in addr or any(c.isspace() for c in addr):
                raise ValueError(f"Invalid from= address: {addr!r}")
            if addr.strip() in ("0.0.0.0/0", "::/0", "*"):
                raise ValueError(
                    "from=0.0.0.0/0 restricts nothing; omit from= instead of "
                    "writing one that always matches"
                )
        opts.append('from="{}"'.format(",".join(from_addresses)))
    return f"{','.join(opts)} {key}"


def sshd_dropin(user: str = "skopos-node", *, command: str = AGENT_COMMAND) -> str:
    """The sshd fragment that constrains the agent's account.

    sshd's own ``ForceCommand`` outranks whatever the key or the client asks for,
    and — unlike ``authorized_keys`` in a home directory — it cannot be edited by
    the account it constrains. That difference is the point: a forced command the
    constrained user can rewrite protects against a stolen key but not against
    anything that manages to run as that user.
    """
    if not user.isidentifier() and not user.replace("-", "_").isidentifier():
        raise ValueError(f"implausible user name: {user!r}")
    return f"""# Installed by SKOPOS. Constrains the agent account and nothing else.
#
# Every directive lives inside the Match block on purpose. sshd includes this
# drop-in near the top of sshd_config and takes the first value it sees for a
# keyword, so a global AuthorizedKeysFile here would silently replace whatever
# key layout the host already had — on a fleet that centralises keys, for every
# account at once.
Match User {user}
    AuthorizedKeysFile /etc/ssh/authorized_keys.d/%u
    ForceCommand {command}
    PermitTTY no
    AllowTcpForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTunnel no
    MaxSessions 2

# Close the Match block. sshd applies drop-ins in sorted order and everything
# after a Match belongs to it, so a file that ends mid-block silently captures
# whatever the next drop-in declares globally.
Match all
"""
