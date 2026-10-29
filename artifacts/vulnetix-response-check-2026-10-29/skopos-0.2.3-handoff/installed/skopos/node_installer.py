"""Render the self-contained installer that puts the agent on a monitored host.

The installer is one file the operator copies to a host and runs as root. It
carries the agent source, the privileged dumper, the systemd units and a config
— but never a long-lived secret. It is handed a single-use enrollment ticket on
**stdin**, and the credential it receives in exchange is written straight to a
0640 file that only root and the agent's own user can read.

Why stdin and not an argument: everything in ``argv`` is visible in
``/proc/<pid>/cmdline`` to every local user for the life of the process, and
ends up in shell history and in sudo's log. A ticket that leaks there is a ticket
someone else can burn.
"""

from __future__ import annotations

import json
import shlex

from . import remote_scripts
from .node_agent import agent_source, agent_sha256, agent_version
from .wrapper_gen import authorized_keys_line, sshd_dropin

NODE_USER = "skopos-node"
INSTALL_DIR = "/usr/local/lib/skopos-node"
CONFIG_DIR = "/etc/skopos-node"
STATE_DIR = "/var/lib/skopos-node"
RUN_DIR = "/run/skopos-node"
PRIVDUMP_PATH = "/usr/local/libexec/skopos-node-privdump"
BIN_PATH = "/usr/local/bin/skopos-node"

DEFAULT_LOG_ROOTS = ("/var/log/nginx", "/var/log/apache2", "/var/log/httpd")

#: The server name is interpolated into the generated script's comments and
#: messages, so it is held to what can appear there harmlessly.
_SAFE_NAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
)


def log_roots_for(server) -> tuple[str, ...]:
    """Directories this server's agent should be allowed to read.

    Derived from the server's own configuration rather than left to the operator
    to remember: a host whose apache logs live under /opt would otherwise get an
    agent that reads nothing and reports zero lines, which looks exactly like a
    quiet host.
    """
    import os

    roots: list[str] = list(DEFAULT_LOG_ROOTS)
    for block in (getattr(server, "nginx", None), getattr(server, "apache", None)):
        if block is None:
            continue
        paths = list(getattr(block, "access_log_paths", None) or [])
        single = getattr(block, "access_log_path", None)
        if single:
            paths.append(single)
        for p in paths:
            directory = os.path.dirname(str(p).strip())
            if directory.startswith("/") and directory not in roots:
                roots.append(directory)
    return tuple(roots)


def containers_for(server) -> tuple[str, ...]:
    """Containers this server's agent may read logs from."""
    names: list[str] = []
    for block in (getattr(server, "nginx", None), getattr(server, "apache", None)):
        for name in (getattr(block, "docker_log_containers", None) or []) if block else []:
            if name not in names:
                names.append(str(name))
    return tuple(names)


def render_privdump(*, containers: tuple[str, ...] = (), container_lines: int = 2000) -> str:
    """The root half of the agent: no arguments, no input, no caller.

    Everything that needs privilege lives here. It is a timer job rather than
    something the unprivileged agent can ask for, because the alternatives —
    putting the agent in the ``docker`` group, or giving it sudo for ``ss`` or
    ``fail2ban-client`` — all hand back root by a different name. With no
    parameters there is nothing for a caller to influence, so the only attack
    surface is the scripts themselves.
    """
    container_block = ""
    if containers:
        names = " ".join(shlex.quote(c) for c in containers)
        container_block = f'''
# Allow-listed container logs. The list is fixed at install time and lives in a
# root-owned file, so a compromised container cannot add itself.
install -d -m 0750 -o root -g {NODE_USER} "$RUN/containers"
for name in {names}; do
  out="$RUN/containers/$name.log"
  if docker logs --tail {int(container_lines)} "$name" 2>&1 | head -c 524288 >"$out.tmp"; then
    chmod 0640 "$out.tmp"; chown root:{NODE_USER} "$out.tmp"; mv -f "$out.tmp" "$out"
  else
    rm -f "$out.tmp"
  fi
done
'''

    return f'''#!/bin/bash
# SKOPOS privileged dumper — GENERATED, DO NOT EDIT.
#
# Runs as root on a timer with no arguments and reads nothing from its caller.
# Writes the output of the collection scripts to {RUN_DIR} where the
# unprivileged agent can read it.
#
# agent: {agent_version()}
set -uo pipefail
umask 027
export LC_ALL=C LANG=C
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN={RUN_DIR}
install -d -m 0750 -o root -g {NODE_USER} "$RUN"

emit() {{
  local name="$1"
  local out="$RUN/$name"
  if timeout 90 bash -s >"$out.tmp" 2>/dev/null; then :; fi
  # Cap the dump so a host under brute force cannot produce an unbounded file.
  if [ -f "$out.tmp" ]; then
    head -c 524288 "$out.tmp" > "$out.tmp2" 2>/dev/null || true
    mv -f "$out.tmp2" "$out.tmp"
    chmod 0640 "$out.tmp"
    chown root:{NODE_USER} "$out.tmp"
    mv -f "$out.tmp" "$out"
  fi
}}

emit probe.txt <<'SKOPOS_PROBE_EOF'
{remote_scripts.PROBE}
SKOPOS_PROBE_EOF

emit knocks.txt <<'SKOPOS_KNOCKS_EOF'
{remote_scripts.PORT_KNOCKS}
SKOPOS_KNOCKS_EOF
{container_block}
exit 0
'''


def render_units(*, interval_s: int = 300, push: bool) -> dict[str, str]:
    """systemd units for the dumper and, in push mode, the reporter."""
    hardening = "\n".join([
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "ProtectKernelTunables=yes",
        "ProtectControlGroups=yes",
        "RestrictSUIDSGID=yes",
        "RestrictNamespaces=yes",
        "LockPersonality=yes",
        "MemoryMax=256M",
        "CPUQuota=25%",
        "TasksMax=64",
    ])

    units = {
        "skopos-node-privdump.service": f"""[Unit]
Description=SKOPOS privileged host dump
Documentation=https://skopos.modelmarket.dev/

[Service]
Type=oneshot
ExecStart={PRIVDUMP_PATH}
# Root by construction — that is why it takes no arguments and no input.
User=root
TimeoutStartSec=300
PrivateTmp=yes
NoNewPrivileges=yes
MemoryMax=256M
CPUQuota=25%
""",
        "skopos-node-privdump.timer": f"""[Unit]
Description=Run the SKOPOS privileged host dump

[Timer]
OnBootSec=45s
OnUnitActiveSec={int(interval_s)}s
AccuracySec=15s

[Install]
WantedBy=timers.target
""",
    }

    if push:
        units["skopos-node.service"] = f"""[Unit]
Description=SKOPOS host agent report
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User={NODE_USER}
Group={NODE_USER}
ExecStart={BIN_PATH} report
TimeoutStartSec=120
ReadWritePaths={STATE_DIR}
{hardening}
"""
        units["skopos-node.timer"] = f"""[Unit]
Description=Report to SKOPOS on a schedule

[Timer]
OnBootSec=90s
OnUnitActiveSec={int(interval_s)}s
AccuracySec=15s
RandomizedDelaySec=20s

[Install]
WantedBy=timers.target
"""
    return units


def render_config(
    *,
    base_url: str,
    log_roots: tuple[str, ...] = DEFAULT_LOG_ROOTS,
    containers: tuple[str, ...] = (),
    interval_s: int = 300,
    privileged: bool = True,
) -> str:
    return json.dumps(
        {
            "base_url": base_url,
            "log_roots": list(log_roots),
            "containers": list(containers),
            "interval_s": int(interval_s),
            "privileged": bool(privileged),
        },
        indent=2,
    )


def _heredoc(name: str, body: str) -> str:
    delim = f"SKOPOS_FILE_{name}"
    for line in body.splitlines():
        if line.strip() == delim:
            raise ValueError(f"{name} collides with its heredoc delimiter")
    return f"cat >\"$tmp\" <<'{delim}'\n{body}\n{delim}"


def render_installer(
    *,
    base_url: str,
    server_name: str,
    push: bool = True,
    log_roots: tuple[str, ...] = DEFAULT_LOG_ROOTS,
    containers: tuple[str, ...] = (),
    interval_s: int = 300,
    privileged: bool = True,
    collector_public_key: str = "",
) -> str:
    """One self-contained installer for one host."""
    if not push and not collector_public_key:
        raise ValueError(
            "an agent-ssh installer needs the collector's public key: without it "
            "no authorized_keys entry and no sshd ForceCommand are written, and "
            "the host ends up with an agent nothing can reach"
        )
    if not server_name or not set(server_name) <= _SAFE_NAME_CHARS:
        raise ValueError(
            f"server name {server_name!r} cannot be rendered into an installer; "
            "use letters, digits, dot, underscore or hyphen"
        )
    config = render_config(
        base_url=base_url,
        log_roots=log_roots,
        containers=containers,
        interval_s=interval_s,
        privileged=privileged,
    )
    privdump = render_privdump(containers=containers)
    units = render_units(interval_s=interval_s, push=push)
    agent = agent_source()

    unit_blocks = []
    for name, body in units.items():
        token = name.replace(".", "_").replace("-", "_")
        unit_blocks.append(
            f'begin_file /etc/systemd/system/{name} 0644 root:root\n'
            f'{_heredoc(token, body)}\n'
            f'commit_file'
        )
    unit_writes = "\n\n".join(unit_blocks)

    ssh_block = ""
    if collector_public_key:
        key_line = authorized_keys_line(collector_public_key)
        dropin = sshd_dropin(NODE_USER)
        ssh_block = f'''
# --- agent-ssh: pin an inbound key to the agent, and only to the agent -------
#
# The key lives in a root-owned directory, not in the agent user's home. If it
# lived in ~{NODE_USER}/.ssh the agent's own user could rewrite it and drop the
# forced command, which would make the restriction decorative the moment
# anything ran as that user.
install -d -m 0755 -o root -g root /etc/ssh/authorized_keys.d
printf '%s\\n' {shlex.quote(key_line)} \\
  > /etc/ssh/authorized_keys.d/{NODE_USER}
chmod 0644 /etc/ssh/authorized_keys.d/{NODE_USER}
chown root:root /etc/ssh/authorized_keys.d/{NODE_USER}

cat > /etc/ssh/sshd_config.d/60-skopos-node.conf <<'SKOPOS_SSHD_EOF'
{dropin}SKOPOS_SSHD_EOF

# Never reload a config that does not parse — that is how a host loses SSH.
if sshd -t; then
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  say "sshd: forced command installed for {NODE_USER}"
else
  rm -f /etc/ssh/sshd_config.d/60-skopos-node.conf
  fail "sshd -t rejected the SKOPOS drop-in; reverted and left sshd untouched"
fi
'''

    enroll_block = ""
    if push:
        enroll_block = f'''
# --- enrollment ---------------------------------------------------------------
#
# The ticket arrives on stdin and is used exactly once. The credential we get
# back never touches argv, the environment, or a systemd unit file.
if [ -f {CONFIG_DIR}/credential.json ] && [ "${{FORCE_REENROLL:-0}}" != "1" ]; then
  say "already enrolled; keeping the existing credential"
else
  if [ -t 0 ]; then
    # Prompt instead of demanding a pipeline. `printf %s '<ticket>' | bash ...`
    # puts the ticket in printf's own argv — readable in /proc by every local
    # user while it runs, and left behind in shell history. Reading it here with
    # -s keeps it out of both.
    printf 'Enrollment ticket (input hidden): ' >&2
    read -r -s TICKET
    printf '\n' >&2
  else
    TICKET="$(cat)"
  fi
  [ -n "$TICKET" ] || fail "no enrollment ticket given"

  # Through the environment, not argv: /proc/<pid>/cmdline is world-readable,
  # /proc/<pid>/environ is readable only by the owner and root.
  SKOPOS_ENROLL_TICKET="$TICKET" python3 - <<'SKOPOS_ENROLL_EOF'
import json, os, ssl, sys, socket, urllib.request

ticket = os.environ["SKOPOS_ENROLL_TICKET"].strip()
cfg = json.load(open("{CONFIG_DIR}/config.json"))
url = cfg["base_url"].rstrip("/") + "/node/v1/enroll"
body = json.dumps({{"ticket": ticket, "hostname": socket.gethostname()}}).encode()

ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({{}}),
    urllib.request.HTTPSHandler(context=ctx),
)
req = urllib.request.Request(url, data=body, headers={{"Content-Type": "application/json"}})
try:
    with opener.open(req, timeout=30) as r:
        out = json.loads(r.read(65536))
except Exception as e:
    sys.stderr.write("enrollment failed: %s\\n" % e)
    raise SystemExit(1)

path = "{CONFIG_DIR}/credential.json"
# O_EXCL so a concurrent installer cannot be raced into overwriting a
# credential, and 0600 before a single byte is written.
fd = os.open(path + ".new", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as fh:
    json.dump({{"key_id": out["key_id"], "secret_b64": out["secret_b64"]}}, fh)
os.replace(path + ".new", path)
sys.stderr.write("enrolled as %s (%s)\\n" % (out.get("server_name"), out["key_id"]))
SKOPOS_ENROLL_EOF

  chown root:{NODE_USER} {CONFIG_DIR}/credential.json
  chmod 0640 {CONFIG_DIR}/credential.json
  unset TICKET SKOPOS_ENROLL_TICKET
fi
'''

    timers = "skopos-node-privdump.timer" + (" skopos-node.timer" if push else "")
    login_shell = "/bin/sh" if collector_public_key else "/usr/sbin/nologin"
    roots_list = " ".join(shlex.quote(r) for r in log_roots)

    # Built outside the f-string below: on Python 3.9 an f-string expression may
    # not contain a backslash, and these all do.
    launcher = "#!/bin/sh\nexec python3 %s/skopos_node.py \"$@\"" % INSTALL_DIR
    launcher_block = _heredoc("LAUNCHER", launcher)
    agent_block = _heredoc("AGENT", agent)
    privdump_block = _heredoc("PRIVDUMP", privdump)
    config_block = _heredoc("CONFIG", config)
    tmpfiles_block = _heredoc("TMPFILES", "d %s 0750 root %s -" % (RUN_DIR, NODE_USER))
    first_report_block = (
        '\nsay "sending the first report"\n'
        'runuser -u %s -- %s report || fail "the first report did not go through"\n'
        % (NODE_USER, BIN_PATH)
    ) if push else ""

    return f'''#!/bin/bash
# SKOPOS host agent installer — GENERATED for "{server_name}".
#
#   sudo bash {shlex.quote(f"install-{server_name}.sh")}      (it will prompt for the ticket)
#
# Installs an unprivileged agent plus a root timer that does the parts needing
# privilege. Grants no sudo rules and adds the agent to no groups that would
# make it root by another name.
#
# agent {agent_version()} sha256 {agent_sha256()}
set -euo pipefail

say()  {{ printf '[skopos] %s\\n' "$*" >&2; }}
fail() {{ printf '[skopos] ERROR: %s\\n' "$*" >&2; exit 1; }}

[ "$(id -u)" -eq 0 ] || fail "run me as root"

# On Debian /usr/local and its subdirectories ship as 2775 root:staff. A root
# timer living under a group-writable directory is a privilege escalation for
# every member of that group, so normalise the ones we install into and refuse
# if we cannot.
for d in /usr/local /usr/local/bin /usr/local/lib /usr/local/libexec; do
  [ -d "$d" ] || install -d -m 0755 -o root -g root "$d"
  chown root:root "$d" 2>/dev/null || true
  chmod g-w,o-w "$d" 2>/dev/null || true
  perms="$(stat -c '%U:%a' "$d")"
  case "$perms" in
    root:7[0-5][0-5]|root:5[0-5][0-5]) ;;
    *) fail "$d is $perms; refusing to install a root timer under it" ;;
  esac
done
command -v python3 >/dev/null || fail "python3 is required"
command -v systemctl >/dev/null || fail "systemd is required"

FILE_TARGET=""
FILE_MODE=""
FILE_OWNER=""
tmp=""

begin_file() {{ FILE_TARGET="$1"; FILE_MODE="$2"; FILE_OWNER="$3"; tmp="$(mktemp)"; }}
commit_file() {{
  install -D -m "$FILE_MODE" -o "${{FILE_OWNER%%:*}}" -g "${{FILE_OWNER##*:}}" "$tmp" "$FILE_TARGET"
  rm -f "$tmp"
  say "wrote $FILE_TARGET"
}}

# --- user ---------------------------------------------------------------------
if ! id -u {NODE_USER} >/dev/null 2>&1; then
  useradd --system --home-dir {STATE_DIR} --create-home \\
          --shell {login_shell} {NODE_USER}
  say "created user {NODE_USER}"
else
  # Re-assert it: a host converted from push to agent-ssh would otherwise keep
  # nologin, and sshd's ForceCommand needs a shell to run the command with.
  current_shell="$(getent passwd {NODE_USER} | cut -d: -f7)"
  if [ "$current_shell" != "{login_shell}" ]; then
    usermod --shell {login_shell} {NODE_USER}
    say "set {NODE_USER} shell to {login_shell}"
  fi
fi
install -d -m 0700 -o {NODE_USER} -g {NODE_USER} {STATE_DIR}
install -d -m 0750 -o root -g {NODE_USER} {CONFIG_DIR}
install -d -m 0755 -o root -g root {INSTALL_DIR}
install -d -m 0755 -o root -g root /usr/local/libexec
install -d -m 0755 -o root -g root /etc/ssh/sshd_config.d

# --- files --------------------------------------------------------------------
begin_file {INSTALL_DIR}/skopos_node.py 0644 root:root
{agent_block}
commit_file

begin_file {BIN_PATH} 0755 root:root
{launcher_block}
commit_file

begin_file {PRIVDUMP_PATH} 0755 root:root
{privdump_block}
commit_file

begin_file {CONFIG_DIR}/config.json 0644 root:root
{config_block}
commit_file

begin_file /usr/lib/tmpfiles.d/skopos-node.conf 0644 root:root
{tmpfiles_block}
commit_file

{unit_writes}

systemd-tmpfiles --create /usr/lib/tmpfiles.d/skopos-node.conf >/dev/null 2>&1 || true

# --- log access ---------------------------------------------------------------
#
# An ACL grants exactly these directories. The `adm` fallback is broader — it
# reaches every adm-readable file in /var/log, including syslog — so it is used
# only when the filesystem cannot do ACLs, and it says so.
GRANTED=""
for root in {roots_list}; do
  [ -d "$root" ] || continue
  if command -v setfacl >/dev/null 2>&1 && \\
     setfacl -m u:{NODE_USER}:rx "$root" 2>/dev/null && \\
     setfacl -R -m u:{NODE_USER}:rX "$root" 2>/dev/null && \\
     setfacl -d -m u:{NODE_USER}:rX "$root" 2>/dev/null; then
    GRANTED="$GRANTED $root(acl)"
  else
    usermod -aG adm {NODE_USER} 2>/dev/null || true
    GRANTED="$GRANTED $root(adm-group)"
    say "WARNING: no ACL support on $root — fell back to the adm group, which"
    say "         also reads syslog and every other adm-readable log."
  fi
done
{enroll_block}{ssh_block}
# --- verify what we granted, then start ---------------------------------------
for f in {INSTALL_DIR}/skopos_node.py {CONFIG_DIR}/config.json {PRIVDUMP_PATH}; do
  owner="$(stat -c '%U' "$f")"
  [ "$owner" = "root" ] || fail "$f is owned by $owner, not root"
done

systemctl daemon-reload
systemctl enable --now {timers}
say "running the first privileged dump"
systemctl start skopos-node-privdump.service || say "privdump failed; see journalctl -u skopos-node-privdump"

sleep 2
say "self-test:"
runuser -u {NODE_USER} -- {BIN_PATH} selftest || say "self-test reported problems (above)"
{first_report_block}
say ""
say "installed for {server_name}"
say "  user      {NODE_USER} (no sudo rules, no docker group)"
say "  granted  $GRANTED"
say "  timers    {timers}"
say "  logs      journalctl -u skopos-node -u skopos-node-privdump"
'''
