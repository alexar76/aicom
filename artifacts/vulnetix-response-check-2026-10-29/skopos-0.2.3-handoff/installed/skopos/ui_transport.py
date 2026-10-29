"""The per-server transport picker, and the case for the agent.

The choice here is the single biggest security decision an operator makes in
SKOPOS, so the UI states the trade plainly instead of listing three equal
options. The agent is preselected, and a host still on SSH says why that costs
something — not as a scold, but because "SKOPOS holds a key that opens this
machine" is a fact worth seeing next to the machine it applies to.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from .config import ServerConfig

#: Ordered best-first. The first entry is what a new server gets.
TRANSPORT_CHOICES = ("agent-push", "agent-ssh", "direct-ssh")

TRANSPORT_LABELS = {
    "agent-push": "Agent — the host reports in  ·  recommended",
    "agent-ssh": "Agent over SSH — SKOPOS connects to a locked-down key",
    "direct-ssh": "Direct SSH — SKOPOS runs shell commands  ·  legacy",
}

TRANSPORT_BLURBS = {
    "agent-push": (
        "SKOPOS holds **no credential** for this host and never connects to it. "
        "The agent runs unprivileged, reads only the log directories you allow, "
        "and posts what it finds over HTTPS. If SKOPOS itself were compromised, "
        "this host would not be reachable from it."
    ),
    "agent-ssh": (
        "SKOPOS connects with a key pinned to the agent, so the key can ask for "
        "exactly two things — `ping` and `collect` — and cannot run anything "
        "else. Use this when a host cannot make outbound connections. "
        "It still means a key on the SKOPOS box opens a session here."
    ),
    "direct-ssh": (
        "SKOPOS pipes shell scripts to this host over SSH, so the key it holds "
        "is a **full shell**. Whoever steals it gets everything the account can "
        "do — which, if that account is `root`, is everything. This is how "
        "SKOPOS used to work; it is kept for hosts not yet migrated."
    ),
}


@dataclass(frozen=True)
class TransportChoice:
    transport: str
    ssh_mode: str


def _needs_attention(server: ServerConfig) -> str | None:
    if server.transport == "direct-ssh":
        if (server.ssh.user or "").strip() == "root":
            return (
                "This host is collected **as root over a full-shell SSH key**. "
                "That key is the most valuable thing in this deployment: it opens "
                "a root session on this machine, and it is sitting on the SKOPOS "
                "box. Moving to the agent removes it entirely."
            )
        return (
            "SKOPOS holds a full-shell SSH key for this host. The agent needs no "
            "inbound credential at all."
        )
    return None


def render_transport_picker(server: ServerConfig, *, key_prefix: str) -> TransportChoice:
    """Render the picker for one server and return what the operator chose."""
    current = server.transport if server.transport in TRANSPORT_CHOICES else "direct-ssh"

    warning = _needs_attention(server)
    if warning:
        st.warning(warning, icon="🔑")

    chosen = st.radio(
        "How does this host's data reach SKOPOS?",
        TRANSPORT_CHOICES,
        index=TRANSPORT_CHOICES.index(current),
        format_func=lambda t: TRANSPORT_LABELS[t],
        key=f"{key_prefix}_transport",
        horizontal=False,
    )
    st.caption(TRANSPORT_BLURBS[chosen])

    if chosen != current and chosen.startswith("agent"):
        st.info(
            "Saving this switches the config. The host will not report until you "
            "install the agent on it — the installer is below.",
            icon="↓",
        )

    ssh_mode = "wrapper" if chosen == "agent-ssh" else "direct"
    return TransportChoice(transport=chosen, ssh_mode=ssh_mode)


def render_agent_panel(server: ServerConfig, *, config_path: str, key_prefix: str) -> None:
    """Enrollment ticket and one-shot installer for an agent-mode host."""
    if server.transport == "direct-ssh":
        return

    from .db import connect_for_config
    from .config import load_config
    from .node_installer import containers_for, log_roots_for, render_installer
    from .node_store import create_ticket, list_credentials

    st.markdown("**Agent**")

    cfg = load_config(config_path)
    con = connect_for_config(cfg)
    try:
        creds = [c for c in list_credentials(con, server_name=server.name) if not c["revoked_at_utc"]]
    except Exception as e:  # noqa: BLE001 - a DB hiccup must not break the page
        creds = []
        st.caption(f"Could not read agent status: {e}")
    finally:
        con.close()

    if creds:
        live = creds[0]
        st.success(
            f"Enrolled · last report {live['last_seen_at_utc'] or 'never'} · "
            f"{live['reports_total']} reports · agent {live['agent_version'] or '?'}",
            icon="✅",
        )
        if live.get("clock_skew_s") and abs(int(live["clock_skew_s"])) > 60:
            st.caption(
                f"This host's clock is {live['clock_skew_s']}s off ours. Reports still "
                "arrive, but log timestamps will look shifted."
            )
    else:
        st.caption("No agent has enrolled for this host yet.")

    base_url = st.text_input(
        "URL the agent reports to",
        value=st.session_state.get(f"{key_prefix}_base_url", "https://skopos.modelmarket.dev"),
        key=f"{key_prefix}_base_url",
        help="Must be reachable from the monitored host, and must be https.",
    )

    if st.button("Generate installer", key=f"{key_prefix}_gen", use_container_width=True):
        con = connect_for_config(cfg)
        try:
            ticket = create_ticket(con, server.name)
        finally:
            con.close()
        script = render_installer(
            base_url=base_url,
            server_name=server.name,
            push=(server.transport == "agent-push"),
            log_roots=log_roots_for(server),
            containers=containers_for(server),
        )
        st.session_state[f"{key_prefix}_ticket"] = ticket
        st.session_state[f"{key_prefix}_script"] = script

    ticket = st.session_state.get(f"{key_prefix}_ticket")
    script = st.session_state.get(f"{key_prefix}_script")
    if ticket and script:
        st.download_button(
            "Download installer",
            data=script,
            file_name=f"skopos-node-install-{server.name}.sh",
            mime="text/x-shellscript",
            key=f"{key_prefix}_dl",
            use_container_width=True,
        )
        st.caption(
            "Run it on the host and paste the ticket when it asks. Passing it on "
            "the command line instead would put it in `/proc` for every local "
            "user to read, and leave it in shell history."
        )
        st.code(f"sudo bash skopos-node-install-{server.name}.sh", language="bash")
        st.text_input(
            "Ticket to paste",
            value=ticket,
            key=f"{key_prefix}_ticket_show",
            help="Single use, valid for 30 minutes.",
        )
