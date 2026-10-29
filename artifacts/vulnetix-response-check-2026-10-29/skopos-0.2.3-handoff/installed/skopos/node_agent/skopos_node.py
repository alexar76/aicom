#!/usr/bin/env python3
"""SKOPOS host agent — collects this machine's logs and posture, and ships them.

Runs on every monitored host. Three things it must never stop being true:

* **stdlib only.** Monitored hosts do not get ``pip install``.
* **no imports from ``skopos``.** This file lives on someone else's server.
* **not root.** Anything needing privilege is done by ``skopos-node-privdump``,
  a separate argument-free root job on a timer whose output this agent merely
  reads. That split is the whole reason the agent can be unprivileged: there is
  no ``docker`` group and no ``sudo`` rule to hand back root-equivalence.

Three transports carry the same document:

``report``   POST it to SKOPOS. No inbound credential exists on this host.
``ssh-op``   print it, when SKOPOS connects to a key pinned to this command.
``collect``  print it locally, for debugging.

In ``ssh-op`` the only thing that crosses the wire is a verb — ``ping`` or
``collect``. There is no operation that takes a path or a container name, so
path traversal and argument injection are not defended against here, they are
absent. What may be read is decided by a root-owned config file on this host,
never by the caller.
"""

from __future__ import annotations

import base64
import errno
import fnmatch
import grp
import gzip
import hashlib
import hmac
import json
import os
import pwd
import socket
import ssl
import stat
import sys
import time
import urllib.error
import urllib.request

AGENT_VERSION = "1.0.0"
PROTOCOL_VERSION = 1

CONFIG_PATH = os.environ.get("SKOPOS_NODE_CONFIG", "/etc/skopos-node/config.json")
CREDENTIAL_PATH = os.environ.get("SKOPOS_NODE_CREDENTIAL", "/etc/skopos-node/credential.json")
STATE_PATH = os.environ.get("SKOPOS_NODE_STATE", "/var/lib/skopos-node/state.json")
RUN_DIR = os.environ.get("SKOPOS_NODE_RUN_DIR", "/run/skopos-node")

# Exit codes. Distinct so a failure is diagnosable from systemd alone.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REJECT = 92
EXIT_UNSAFE = 93

# --- Limits. Mirrored from the server so we never build a report it will bin.
MAX_LINE_BYTES = 8 * 1024
MAX_LINES_PER_REPORT = 20_000
MAX_SOURCES = 64
MAX_PROBE_BYTES = 512 * 1024
MAX_BYTES_PER_FILE = 4 * 1024 * 1024
#: On first sight of a file we take only its tail. Without this, adding a host
#: with a year of logs would try to ship the year.
INITIAL_TAIL_BYTES = 256 * 1024

#: Age past which a privileged dump is stale enough that reporting it would be
#: claiming to know something we no longer know.
MAX_DUMP_AGE_S = 3600


class Unsafe(Exception):
    """The host is not in a state where running is safe."""


class Reject(Exception):
    """A caller asked for something outside the vocabulary."""


class Resync(Exception):
    """We adopted a corrected sequence number; the next run will go through."""


# --------------------------------------------------------------------------
# Config and state
# --------------------------------------------------------------------------

def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        if default is None:
            raise
        return default
    except (ValueError, OSError) as e:
        raise Unsafe("cannot read %s: %s" % (path, e))


def load_config():
    cfg = _read_json(CONFIG_PATH)
    if not isinstance(cfg, dict):
        raise Unsafe("%s must contain a JSON object" % CONFIG_PATH)
    cfg.setdefault("log_roots", ["/var/log/nginx", "/var/log/apache2", "/var/log/httpd"])
    cfg.setdefault("log_globs", ["*access*.log", "access_log", "*access_log"])
    cfg.setdefault("containers", [])
    cfg.setdefault("interval_s", 300)
    cfg.setdefault("privileged", True)
    cfg.setdefault("verify_tls", True)
    return cfg


def load_state():
    state = _read_json(STATE_PATH, default={})
    if not isinstance(state, dict):
        return {}
    return state


def save_state(state):
    directory = os.path.dirname(STATE_PATH)
    if directory:
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            pass
    tmp = STATE_PATH + ".tmp"
    # Write-then-rename: a crash mid-write must not leave a state file that
    # parses as "never seen any of these files" and re-ships everything.
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_PATH)
    try:
        os.chmod(STATE_PATH, 0o600)
    except OSError:
        pass


def assert_safe_install():
    """Refuse to run if the things that decide our behaviour are writable by us.

    An agent that can rewrite its own config or its own code is an agent whose
    restrictions mean nothing the moment anything executes as its user.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0 and os.environ.get("SKOPOS_NODE_ALLOW_ROOT") != "1":
        raise Unsafe(
            "refusing to run as root; privileged collection belongs to "
            "skopos-node-privdump"
        )
    if os.environ.get("SKOPOS_NODE_UNSAFE_SKIP_OWNERSHIP_CHECK") == "1":
        # For test harnesses that cannot chown. The installer never sets this,
        # and selftest reports it as a problem so it cannot hide in production.
        return
    me = os.geteuid() if hasattr(os, "geteuid") else None
    for path in (os.path.abspath(__file__), CONFIG_PATH):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if me is not None and st.st_uid == me:
            raise Unsafe("%s is owned by the agent's own user" % path)
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise Unsafe("%s is group- or world-writable" % path)


# --------------------------------------------------------------------------
# Reading logs safely
# --------------------------------------------------------------------------

def _under_root(resolved, roots):
    for root in roots:
        root = os.path.normpath(root)
        if resolved == root or resolved.startswith(root.rstrip("/") + "/"):
            return True
    return False


def open_log_fd(path, roots):
    """Open a log file, or raise. Validates the descriptor, not the name.

    Checking a path and then opening it by name is a race: on a log directory
    the application user can write to, the file can become a symlink between the
    two steps. So the file is opened first — refusing to traverse a final
    symlink and refusing to block — and every check is then made against the
    descriptor we are actually holding.
    """
    flags = os.O_RDONLY | os.O_NONBLOCK
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        flags |= getattr(os, name, 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            # A FIFO would hang the collection until the timer kills it; a
            # device node would produce output forever.
            raise Reject("%s is not a regular file" % path)
        if st.st_nlink != 1:
            # A hard link into the log directory is a way to present a file
            # that lives somewhere we would never have allowed.
            raise Reject("%s has more than one link" % path)
        try:
            actual = os.readlink("/proc/self/fd/%d" % fd)
        except OSError:
            actual = os.path.realpath(path)
        if not _under_root(os.path.normpath(actual), roots):
            raise Reject("%s resolves outside the permitted roots" % path)
        return fd, st, actual
    except Exception:
        os.close(fd)
        raise


def read_new_lines(path, roots, state_entry):
    """Return (lines, new_state, truncated) for everything appended since last time.

    Tracking an offset rather than re-reading a fixed tail means a busy host does
    not re-send the same four thousand lines every cycle, and a quiet one does
    not miss lines that scrolled past between runs.
    """
    fd, st, _actual = open_log_fd(path, roots)
    try:
        prev = state_entry or {}

        # Identity is inode plus a fingerprint of the first bytes. The inode
        # alone is not enough: logrotate's copytruncate empties the file in
        # place, so the inode is unchanged and the new content can be the same
        # length as what we already read. Offset comparison alone then reads
        # "nothing new" and the host goes quiet without anyone noticing.
        head = b""
        if st.st_size:
            os.lseek(fd, 0, os.SEEK_SET)
            head = os.read(fd, 256)
        head_digest = hashlib.sha256(head).hexdigest()[:16] if head else ""

        same_file = (
            prev.get("dev") == st.st_dev
            and prev.get("ino") == st.st_ino
            and prev.get("head") == head_digest
        )
        pos = int(prev.get("pos", 0)) if same_file else 0

        if not same_file:
            if prev:
                # Rotated or rewritten: read it from the start, not from a tail,
                # or we would skip whatever landed before we noticed.
                pos = 0
            else:
                # First sight of this file — take only the tail, so adding a host
                # with a year of logs does not try to ship the year.
                pos = max(0, st.st_size - INITIAL_TAIL_BYTES)
        elif pos > st.st_size:
            pos = 0

        truncated = False
        to_read = st.st_size - pos
        if to_read > MAX_BYTES_PER_FILE:
            # Skip ahead rather than ship a burst; the gap is reported.
            pos = st.st_size - MAX_BYTES_PER_FILE
            to_read = MAX_BYTES_PER_FILE
            truncated = True

        os.lseek(fd, pos, os.SEEK_SET)
        chunks = []
        remaining = to_read
        while remaining > 0:
            try:
                blob = os.read(fd, min(65536, remaining))
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                raise
            if not blob:
                break
            chunks.append(blob)
            remaining -= len(blob)

        data = b"".join(chunks)
        # Keep a partial trailing line for next time instead of shipping half of it.
        cut = data.rfind(b"\n")
        if cut == -1:
            consumed = 0
            body = b""
        else:
            consumed = cut + 1
            body = data[:consumed]

        lines = []
        for raw in body.split(b"\n"):
            if not raw.strip():
                continue
            if len(raw) > MAX_LINE_BYTES:
                raw = raw[:MAX_LINE_BYTES]
            text = raw.decode("utf-8", errors="replace").replace("\x00", "")
            if text.strip():
                lines.append(text)

        return (
            lines,
            {"dev": st.st_dev, "ino": st.st_ino, "pos": pos + consumed, "head": head_digest},
            truncated,
        )
    finally:
        os.close(fd)


#: Mirrors the server's validate_log_path. A path that cannot be expressed as a
#: source id is skipped here rather than shipped, because the server rejects the
#: entire document on one bad id — so one file named "a;b.log", which any
#: application in the log directory can create, would silence the whole host.
_SAFE_PATH_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:@=+-"
)


def expressible_as_source(path):
    if not path.startswith("/") or ".." in path.split("/"):
        return False
    if len(path.encode("utf-8")) > 512:
        return False
    return set(path) <= _SAFE_PATH_CHARS


def discover_logs(cfg):
    """Find access logs inside the roots this host has authorised.

    Discovery only ever narrows: it looks within the configured roots and cannot
    introduce a path from outside them. Adding a root needs root on this host,
    which is the point — a foothold in the web application must not be able to
    choose what the agent reads.
    """
    roots = [os.path.normpath(r) for r in cfg.get("log_roots", [])]
    globs = cfg.get("log_globs") or ["*access*.log"]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            continue
        for name in entries:
            if name.endswith((".gz", ".xz", ".bz2", ".zst", ".1", ".2", ".3")):
                continue
            if not any(fnmatch.fnmatch(name, g) for g in globs):
                continue
            candidate = os.path.join(root, name)
            if os.path.isfile(candidate) and expressible_as_source(candidate):
                found.append(candidate)
    for extra in cfg.get("log_files") or []:
        norm = os.path.normpath(extra)
        if _under_root(norm, roots) and norm not in found and os.path.isfile(norm):
            found.append(norm)

    def rank(path):
        base = os.path.basename(path)
        # Exact conventional names first, then shorter names, then the rest.
        return (base not in ("access.log", "access_log", "other_vhosts_access.log"), len(base), base)

    found.sort(key=rank)
    return found[:MAX_SOURCES]


# --------------------------------------------------------------------------
# Privileged dumps, produced by the root timer
# --------------------------------------------------------------------------

def read_dump(name):
    """Read one of the root-written dumps, with its age. Never fabricates."""
    path = os.path.join(RUN_DIR, name)
    try:
        st = os.stat(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(MAX_PROBE_BYTES)
    except OSError:
        return None, None
    age = max(0, int(time.time() - st.st_mtime))
    if age > MAX_DUMP_AGE_S:
        # Reporting a stale snapshot as current is how a dashboard shows a green
        # host that stopped being observed hours ago.
        return None, age
    return text, age


def container_sources(cfg):
    """Container logs, as written by the root timer for allow-listed names only."""
    out = []
    directory = os.path.join(RUN_DIR, "containers")
    if not os.path.isdir(directory):
        return out
    allowed = set(cfg.get("containers") or [])
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".log"):
            continue
        container = name[: -len(".log")]
        if container not in allowed:
            continue
        try:
            with open(os.path.join(directory, name), "r", encoding="utf-8", errors="replace") as fh:
                blob = fh.read(MAX_BYTES_PER_FILE)
        except OSError:
            continue
        lines = [ln[:MAX_LINE_BYTES] for ln in blob.splitlines() if ln.strip()]
        if lines:
            out.append({
                "id": "docker:%s" % container,
                "kind": "docker",
                "parser": "auto",
                "lines": lines,
            })
    return out


# --------------------------------------------------------------------------
# Building the document
# --------------------------------------------------------------------------

def _facts(cfg, errors, probe_age, knocks_age):
    try:
        user = pwd.getpwuid(os.geteuid()).pw_name
    except Exception:
        user = str(os.geteuid()) if hasattr(os, "geteuid") else "?"
    try:
        groups = sorted(grp.getgrgid(g).gr_name for g in os.getgroups())
    except Exception:
        groups = []
    return {
        "hostname": socket.gethostname()[:128],
        "agent_user": user[:64],
        # Reported so the dashboard can flag a host where someone put the agent
        # in a group that hands back the privilege this design removed.
        "groups": groups[:32],
        "probe_age_s": probe_age,
        "knocks_age_s": knocks_age,
        "privileged": bool(cfg.get("privileged", True)),
        "interval_s": int(cfg.get("interval_s", 300)),
        "python": "%d.%d" % sys.version_info[:2],
        "collect_errors": errors[:20],
    }


def collect(cfg, state):
    roots = [os.path.normpath(r) for r in cfg.get("log_roots", [])]
    errors = []
    sources = []
    budget = MAX_LINES_PER_REPORT

    for path in discover_logs(cfg):
        if budget <= 0 or len(sources) >= MAX_SOURCES:
            break
        key = "file:%s" % path
        try:
            lines, entry, truncated = read_new_lines(path, roots, state.get(key))
        except (Reject, OSError) as e:
            errors.append("%s: %s" % (path, e))
            continue
        state[key] = entry
        if not lines:
            continue
        if len(lines) > budget:
            lines = lines[-budget:]
            truncated = True
        budget -= len(lines)
        parser = "apache" if "apache" in path or "httpd" in path else "nginx"
        sources.append({
            "id": key,
            "kind": "file",
            "parser": parser,
            "lines": lines,
            "truncated": truncated,
        })

    for source in container_sources(cfg):
        if budget <= 0 or len(sources) >= MAX_SOURCES:
            break
        source["lines"] = source["lines"][:budget]
        budget -= len(source["lines"])
        sources.append(source)

    probe = knocks = None
    probe_age = knocks_age = None
    if cfg.get("privileged", True):
        probe, probe_age = read_dump("probe.txt")
        knocks, knocks_age = read_dump("knocks.txt")
        if probe is None and probe_age is None:
            errors.append("no privileged dump yet; is skopos-node-privdump.timer running?")

    doc = {
        "protocol": PROTOCOL_VERSION,
        "agent_version": AGENT_VERSION,
        "generated_at": int(time.time()),
        "sources": sources,
        "facts": _facts(cfg, errors, probe_age, knocks_age),
    }
    if probe:
        doc["probe"] = probe
    if knocks:
        doc["knocks"] = knocks
    return doc


# --------------------------------------------------------------------------
# Push transport
# --------------------------------------------------------------------------

def credential_secret(credential):
    """The raw HMAC key from a credential file.

    Enrollment hands back the secret base64-encoded, because JSON has no bytes.
    Signing with the *encoded text* instead of the bytes it stands for produces a
    perfectly well-formed signature that the server will never accept, and the
    only symptom is a 401 — so the decode happens here, once, rather than at each
    call site.
    """
    raw = credential.get("secret_b64") or credential.get("secret")
    if isinstance(raw, bytes):
        return raw
    return base64.b64decode(raw)


def _tls_context(cfg):
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ca = cfg.get("ca_file")
    if ca and os.path.isfile(ca):
        ctx.load_verify_locations(ca)
    return ctx


def send_report(cfg, credential, doc):
    base = str(cfg.get("base_url", "")).rstrip("/")
    if not base.startswith("https://") and not cfg.get("allow_plaintext"):
        raise Unsafe("base_url must be https (set allow_plaintext for a lab)")

    # Burn the sequence number *before* sending, not after a success.
    #
    # The server claims a seq during authentication — it has to, or a replay
    # whose ingest failed could simply be retried. So a number is spent the
    # moment the request is authenticated, whatever happens next. An agent that
    # only advanced on success would retry with a seq the server has already
    # consumed, be told it is a replay, and stay stuck on that number forever.
    # Numbers are free; deadlock is not.
    state = load_state()
    seq = int(state.get("seq", 0)) + 1
    state["seq"] = seq
    save_state(state)

    body = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if len(body) > 64 * 1024:
        body = gzip.compress(body, 6)
        headers["Content-Encoding"] = "gzip"

    timestamp = int(time.time())
    key_id = credential["key_id"]
    secret = credential_secret(credential)
    # Sign the bytes that actually go on the wire — after compression, before any
    # re-serialisation — so the two ends can never disagree about what was signed.
    material = "\n".join(
        (key_id, str(timestamp), str(seq), hashlib.sha256(body).hexdigest())
    ).encode("utf-8")
    signature = hmac.new(secret, material, hashlib.sha256).hexdigest()

    headers.update({
        "X-Skopos-Node": key_id,
        "X-Skopos-Timestamp": str(timestamp),
        "X-Skopos-Seq": str(seq),
        "X-Skopos-Sig": signature,
    })

    request = urllib.request.Request(base + "/node/v1/report", data=body, headers=headers, method="POST")
    # An explicit opener with no ProxyHandler: an HTTPS_PROXY in the environment
    # must not silently become a man in the middle for the fleet's posture data.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=_tls_context(cfg)),
    )
    try:
        # A first report from a busy host carries a large backlog, and the
        # server enriches every new address before answering. 30s was not enough
        # for that and the agent gave up on work the server had already done.
        with opener.open(request, timeout=180) as response:
            return json.loads(response.read(65536).decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise
        # We fell behind — an earlier attempt of ours was accepted for
        # authentication and then failed, spending its number. The server has
        # told us which one to use; adopt it rather than retrying a spent one
        # on every tick until a human looks.
        try:
            hint = json.loads(e.read(4096).decode("utf-8") or "{}")
            next_seq = int(hint["next_seq"])
        except Exception:
            raise e
        state = load_state()
        current = int(state.get("seq", 0))
        # Only ever move forward, and only by a sane amount. This is the one
        # value the server gets to influence on this host, so it does not get to
        # push the counter somewhere we can never come back from.
        if not (current < next_seq <= current + 100000):
            raise Resync(
                "server proposed seq %d, which is not a sane step from %d; ignoring"
                % (next_seq, current)
            )
        state["seq"] = next_seq
        save_state(state)
        raise Resync("adopted seq %d; the next run will use it" % next_seq)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def _emit(doc):
    sys.stdout.write(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")


def cmd_collect(cfg, *, stateless=False):
    """Print one document.

    ``stateless`` is for ``ssh-op``. Over SSH the agent writes to stdout and
    never learns whether SKOPOS received or accepted the result, so there is
    nothing that could honestly authorise advancing a read offset. Committing
    anyway makes every dropped connection a permanent hole in the fleet's logs;
    deferring the commit by one call only moves that hole. So the SSH path keeps
    no offsets at all: it returns a bounded recent window each time and lets the
    server's deduplication absorb the overlap — at-least-once, which is the only
    honest choice for a system whose job is noticing things.

    The push path does get an acknowledgement (the HTTP 200) and therefore does
    track offsets, in :func:`cmd_report`.
    """
    if stateless:
        # A throwaway state: every file is "first seen", which read_new_lines
        # answers with its tail window.
        doc = collect(cfg, {})
    else:
        state = load_state()
        doc = collect(cfg, state)
        save_state(state)
    _emit(doc)
    return EXIT_OK


def cmd_report(cfg):
    credential = _read_json(CREDENTIAL_PATH)

    # Read positions are advanced in a copy and only committed once the report
    # has actually landed. Committing them first would mean a failed send
    # silently skipped those lines for good; committing a copy means the next
    # attempt re-reads them and the server's deduplication absorbs the overlap.
    working = dict(load_state())
    doc = collect(cfg, working)
    result = send_report(cfg, credential, doc)

    committed = load_state()  # re-read: send_report has advanced the sequence
    committed.update({k: v for k, v in working.items() if k != "seq"})
    save_state(committed)

    sys.stdout.write(json.dumps(result) + "\n")
    return EXIT_OK


def cmd_ssh_op(cfg):
    """Serve one operation to a key pinned to this command.

    The vocabulary is two words. There is no operation that accepts a path, a
    container name or a count, so there is nothing here for a caller to inject
    into — the request is either one of these strings or it is refused.
    """
    request = os.environ.get("SSH_ORIGINAL_COMMAND", "").strip()
    if not request:
        raise Reject("no operation requested")
    if len(request) > 64:
        raise Reject("request too long")

    parts = request.split()
    if len(parts) != 2 or parts[0] != "v1":
        raise Reject("expected 'v1 <ping|collect>'")
    verb = parts[1]

    if verb == "ping":
        _emit({
            "protocol": PROTOCOL_VERSION,
            "agent_version": AGENT_VERSION,
            "capabilities": ["ping", "collect"],
            "hostname": socket.gethostname()[:128],
        })
        return EXIT_OK
    if verb == "collect":
        return cmd_collect(cfg, stateless=True)
    raise Reject("unknown operation")


def cmd_selftest(cfg):
    problems = []
    if os.environ.get("SKOPOS_NODE_UNSAFE_SKIP_OWNERSHIP_CHECK") == "1":
        problems.append(
            "SKOPOS_NODE_UNSAFE_SKIP_OWNERSHIP_CHECK is set; the agent is not "
            "verifying that its own code and config are root-owned"
        )
    try:
        assert_safe_install()
    except Unsafe as e:
        problems.append(str(e))
    logs = discover_logs(cfg)
    if not logs:
        problems.append("no readable access logs under %s" % ", ".join(cfg.get("log_roots", [])))
    for path in logs:
        try:
            open_log_fd(path, [os.path.normpath(r) for r in cfg.get("log_roots", [])])[0]
        except Exception as e:
            problems.append("%s: %s" % (path, e))
    if cfg.get("privileged", True):
        probe, age = read_dump("probe.txt")
        if probe is None:
            problems.append("no fresh privileged dump (age=%s)" % age)
    report = {"ok": not problems, "logs": logs, "problems": problems, "version": AGENT_VERSION}
    _emit(report)
    return EXIT_OK if not problems else EXIT_ERROR


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "ssh-op"

    try:
        if command == "version":
            sys.stdout.write(AGENT_VERSION + "\n")
            return EXIT_OK
        cfg = load_config()
        if command not in ("ssh-op", "selftest"):
            # selftest's whole job is to report an unsafe install, so it must be
            # allowed to reach its own diagnostics instead of dying on the check.
            assert_safe_install()
        if command == "collect":
            return cmd_collect(cfg)
        if command == "report":
            return cmd_report(cfg)
        if command == "ssh-op":
            assert_safe_install()
            return cmd_ssh_op(cfg)
        if command == "selftest":
            return cmd_selftest(cfg)
        raise Reject("unknown command %r" % command)
    except Resync as e:
        sys.stderr.write("SKOPOS_NODE_RESYNC: %s\n" % e)
        return EXIT_OK
    except Reject as e:
        sys.stderr.write("SKOPOS_NODE_REJECT: %s\n" % e)
        return EXIT_REJECT
    except Unsafe as e:
        sys.stderr.write("SKOPOS_NODE_UNSAFE: %s\n" % e)
        return EXIT_UNSAFE
    except urllib.error.HTTPError as e:
        sys.stderr.write("SKOPOS_NODE_HTTP: %s %s\n" % (e.code, e.reason))
        return EXIT_ERROR
    except Exception as e:  # noqa: BLE001 - a host agent must not die noisily
        sys.stderr.write("SKOPOS_NODE_ERROR: %s: %s\n" % (type(e).__name__, e))
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
