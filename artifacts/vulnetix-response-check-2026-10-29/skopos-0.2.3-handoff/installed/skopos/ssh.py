from __future__ import annotations

import os
from dataclasses import dataclass

import paramiko

#: Where host keys are remembered when a server does not name its own file.
#: Kept out of ``~/.ssh/known_hosts`` so the collector's trust store is a
#: reviewable artefact rather than a side effect of whoever last used the shell.
DEFAULT_KNOWN_HOSTS = "~/.skopos/known_hosts"


class HostKeyUnknown(RuntimeError):
    """The host is not in the trust store and strict checking is on.

    Carries the remediation in its message because this is the one SSH failure an
    operator hits during normal onboarding, and a bare ``RejectPolicy`` traceback
    tells them nothing about what to do next.
    """


@dataclass(frozen=True)
class SSHConnInfo:
    host: str
    port: int
    user: str
    key_path: str | None = None
    key_passphrase_env: str | None = None
    #: When true the far end pins this key to ``skopos-collect`` and we send an op
    #: token instead of a shell script. See :mod:`skopos.remote_ops`.
    forced_command: bool = False
    #: Overrides :data:`DEFAULT_KNOWN_HOSTS` for this server.
    known_hosts_path: str | None = None


def strict_host_keys_enabled() -> bool:
    """Verify host keys unless explicitly told not to.

    Defaults to on. Turning it off is a deliberate act with a loud name, not the
    consequence of forgetting to set a variable: an unverified first connect
    hands the whole log stream to whoever answers on that address.
    """
    raw = os.environ.get("SKOPOS_SSH_STRICT_HOST_KEYS")
    if raw is None or raw == "":
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


def known_hosts_file(info: SSHConnInfo | None = None) -> str:
    configured = (info.known_hosts_path if info else None) or os.environ.get(
        "SKOPOS_KNOWN_HOSTS"
    )
    return os.path.expanduser(configured or DEFAULT_KNOWN_HOSTS)


def _load_pkey(key_path: str, passphrase: str | None) -> paramiko.PKey:
    path = os.path.expanduser(key_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"SSH key not found: {path}")
    last_err: Exception | None = None
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key_file(path, password=passphrase)
        except PermissionError as e:
            raise PermissionError(
                f"SSH key not readable (check permissions, should be 600): {path}"
            ) from e
        except Exception as e:  # noqa: BLE001 - try next key type
            last_err = e
    assert last_err is not None
    raise last_err


def _build_client(info: SSHConnInfo) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    if strict_host_keys_enabled():
        path = known_hosts_file(info)
        if os.path.isfile(path):
            try:
                client.load_host_keys(path)
            except Exception as e:  # noqa: BLE001 - a corrupt store must not read as "trusted"
                raise HostKeyUnknown(
                    f"Could not read the SKOPOS known_hosts file at {path}: {e}"
                ) from e
        try:
            client.load_system_host_keys()
        except Exception:
            pass
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client


def connect(info: SSHConnInfo, *, timeout_s: int = 20) -> paramiko.SSHClient:
    """Open an authenticated SSH connection, or raise with something actionable."""
    passphrase = None
    if info.key_passphrase_env:
        passphrase = os.environ.get(info.key_passphrase_env)

    client = _build_client(info)

    pkey = None
    if info.key_path:
        pkey = _load_pkey(info.key_path, passphrase)

    try:
        client.connect(
            hostname=info.host,
            port=info.port,
            username=info.user,
            pkey=pkey,
            timeout=timeout_s,
            banner_timeout=timeout_s,
            auth_timeout=timeout_s,
            # Use the key we were configured with and nothing else. Left at their
            # defaults these two options let paramiko authenticate with any key in
            # the invoking user's ~/.ssh or agent, which quietly defeats the point
            # of giving every host its own least-privilege key.
            allow_agent=False,
            look_for_keys=False,
        )
    except paramiko.SSHException as e:
        if "not found in known_hosts" in str(e) or isinstance(e, paramiko.BadHostKeyException):
            client.close()
            raise HostKeyUnknown(
                f"Host key for {info.host}:{info.port} is not trusted "
                f"({known_hosts_file(info)}). Verify the fingerprint out of band, then run:\n"
                f"  python skoposctl.py trust-host --host {info.host} --port {info.port}\n"
                f"Only set SKOPOS_SSH_STRICT_HOST_KEYS=0 if you accept unverified first contact."
            ) from e
        client.close()
        raise
    except Exception:
        client.close()
        raise
    return client


def run_command(info: SSHConnInfo, command: str, timeout_s: int = 20) -> str:
    client = connect(info, timeout_s=timeout_s)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout_s)
        _ = stdin  # unused
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            # Don't fail hard — nginx logs can produce benign warnings depending on shell.
            out = out + ("\n" if out and not out.endswith("\n") else "") + f"# STDERR:\n{err}"
        return out
    finally:
        client.close()


def scan_host_key(host: str, port: int = 22, *, timeout_s: int = 12) -> paramiko.PKey:
    """Fetch a host's public key without authenticating, for the trust-on-first-use step."""
    sock = paramiko.Transport((host, port))
    sock.start_client(timeout=timeout_s)
    try:
        key = sock.get_remote_server_key()
    finally:
        sock.close()
    return key


def remember_host_key(host: str, port: int, key: paramiko.PKey, *, path: str | None = None) -> str:
    """Record a verified host key in the trust store and return the file written."""
    target = os.path.expanduser(path or known_hosts_file())
    os.makedirs(os.path.dirname(target), exist_ok=True)
    hostkeys = paramiko.HostKeys()
    if os.path.isfile(target):
        hostkeys.load(target)
    entry = host if port in (22, None) else f"[{host}]:{port}"
    hostkeys.add(entry, key.get_name(), key)
    hostkeys.save(target)
    os.chmod(target, 0o600)
    return target
