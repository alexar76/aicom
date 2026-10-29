"""Cross-package regressions for tokenless TCP admission (GCVE 000640–000643).

Load the actual admission functions without importing the applications: importing
the apps would create stores and engines unrelated to these OS-boundary tests.
The synthetic Linux socket table represents a public listener owned by a parent
and an unlisted worker relaying accepted traffic to a same-UID backend. Socket
ownership cannot establish the original caller's identity, so this must require
explicit operator trust even though the backend sees an ordinary local request.
"""

from __future__ import annotations

import ast
import io
import ipaddress
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
TCP = "/proc/net/tcp"
HEADER = "  sl local_address rem_address st tx_queue tr tm_when retrnsmt uid timeout inode\n"
UID = 501


@dataclass(frozen=True)
class Source:
    path: str
    prefix: str
    gate: str


SOURCES = (
    Source("aimarket-mcp/aimarket_mcp/server.py", "AIMARKET_MCP", "_auth_ok"),
    Source("metis/metis/api/auth.py", "METIS", "local_caller"),
    Source("treasury/treasury/service.py", "TREASURY", "_local_caller"),
    Source("platon/backend/platon/main.py", "PLATON", "_local_caller"),
    Source(
        "oracles/oracles/platon/backend/oracle_platon/main.py",
        "PLATON",
        "_local_caller",
    ),
)
FUNCTIONS = {
    "_proc_endpoint", "_flag", "_caller_is_this_user", "_peer_is_loopback",
    "_is_loopback_name", "_host_is_loopback", "_origin_is_local",
    "_auth_ok", "_local_caller", "local_caller",
}
CONSTANTS = {"_PROC_NET_TCP", "_LOOPBACK_NAMES", "_FORWARDING_HEADERS"}


def endpoint(address: str, port: int) -> str:
    raw = ipaddress.ip_address(address).packed
    if sys.byteorder == "little":
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    return f"{raw.hex().upper()}:{port:04X}"


def socket_row(local: str, remote: str, *, uid=UID, state="01", inode=302) -> str:
    return (
        f"0: {local} {remote} {state} 00000000:00000000 "
        f"00:00000000 00000000 {uid} 0 {inode} 1\n"
    )


def relay_table(*, uid=UID, peer="127.0.0.1") -> str:
    # The parent owns inode 300. The worker owns accepted ingress 301 and the
    # outbound backend socket 302; the backend owns its accepted socket 303.
    # Which PID holds these sockets does not change the authorization boundary.
    return HEADER + "".join((
        socket_row(endpoint("0.0.0.0", 8080), endpoint("0.0.0.0", 0),
                   state="0A", inode=300),
        socket_row(endpoint("192.0.2.10", 8080), endpoint("93.184.216.34", 40001),
                   inode=301),
        socket_row(endpoint(peer, 40000), endpoint(peer, 9090), uid=uid),
        socket_row(endpoint(peer, 9090), endpoint(peer, 40000), inode=303),
    ))


class Admission:
    def __init__(self, source: Source):
        self.source = source
        self.env: dict[str, str] = {}
        self.files: dict[str, str | OSError] = {TCP: relay_table()}
        namespace = {
            "os": SimpleNamespace(
                environ=self.env,
                geteuid=lambda: UID,
                path=SimpleNamespace(exists=lambda path: path in self.files),
            ),
            "sys": SimpleNamespace(byteorder=sys.byteorder),
            "ipaddress": ipaddress,
            "secrets": secrets,
            "open": self.open,
            "_API_KEY": "",
            "_PUBLIC": False,
            "_PRODUCTION": False,
        }
        path = ROOT / source.path
        tree = ast.parse(path.read_text(), filename=str(path))
        selected = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS
            or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in CONSTANTS
                for target in node.targets
            )
        ]
        module = ast.Module(body=[ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0,
        ), *selected], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
        self.gate = namespace[source.gate]
        self.owner = namespace["_caller_is_this_user"]

    def open(self, path: str, *args, **kwargs):
        try:
            value = self.files[path]
        except KeyError:
            raise FileNotFoundError(path) from None
        if isinstance(value, OSError):
            raise value
        return io.StringIO(value)

    def opt_in(self, *, unverified=False):
        self.env[self.source.prefix + "_LOCAL_RELAY"] = "1"
        if unverified:
            self.env[self.source.prefix + "_LOCAL_UNVERIFIED"] = "1"


@pytest.fixture(params=SOURCES, ids=lambda source: source.path)
def admission(request):
    return Admission(request.param)


def request(*, peer="127.0.0.1", host="127.0.0.1:9090", headers=None):
    return SimpleNamespace(
        client=SimpleNamespace(host=peer, port=40000),
        scope={"server": ("127.0.0.1", 9090)},
        headers={"host": host, **(headers or {})},
    )


def test_same_uid_multiprocess_relay_is_denied_without_operator_opt_in(admission):
    conn = request()
    assert admission.owner(conn) is False
    assert admission.gate(conn) is False
    # LOCAL_UNVERIFIED alone cannot enable keyless TCP, even with a valid table.
    admission.env[admission.source.prefix + "_LOCAL_UNVERIFIED"] = "1"
    assert admission.gate(conn) is False


@pytest.mark.parametrize("peer,host", [
    ("127.0.0.1", "localhost:9090"),
    ("::1", "[::1]:9090"),
])
def test_same_uid_local_tcp_requires_and_accepts_explicit_relay_trust(admission, peer, host):
    admission.files[TCP] = relay_table(peer=peer)
    conn = request(peer=peer, host=host)
    assert admission.gate(conn) is False
    admission.opt_in()
    assert admission.owner(conn) is True
    assert admission.gate(conn) is True


@pytest.mark.parametrize("relay,unverified,allowed", [
    (False, False, False),
    (False, True, False),
    (True, False, False),
    (True, True, True),
])
def test_no_socket_table_requires_both_explicit_opt_ins(admission, relay, unverified, allowed):
    admission.files.clear()  # macOS/Windows or Linux without a mounted /proc
    if relay:
        admission.opt_in()
    if unverified:
        admission.env[admission.source.prefix + "_LOCAL_UNVERIFIED"] = "1"
    assert admission.gate(request()) is allowed


@pytest.mark.parametrize("table", [
    HEADER,
    HEADER + "a malformed short row\n",
    HEADER + socket_row(endpoint("127.0.0.1", 40002), endpoint("127.0.0.1", 9090)),
    HEADER + socket_row(endpoint("127.0.0.1", 40000), endpoint("127.0.0.1", 9091)),
    HEADER + socket_row(endpoint("127.0.0.1", 40000), endpoint("127.0.0.1", 9090), state="0A"),
    HEADER + socket_row(endpoint("127.0.0.1", 40000), endpoint("127.0.0.1", 9090), uid="invalid"),
    HEADER + socket_row("BADHEX:9C40", endpoint("127.0.0.1", 9090)),
    HEADER + socket_row(endpoint("127.0.0.1", 40000), "BADHEX:2382"),
    PermissionError("socket table unreadable"),
], ids=["empty", "short-row", "wrong-client-port", "wrong-server-port", "not-established",
        "malformed-uid", "malformed-local", "malformed-remote", "unreadable"])
def test_available_socket_table_never_falls_back_to_unverified_trust(admission, table):
    admission.opt_in(unverified=True)
    admission.files[TCP] = table
    assert admission.owner(request()) is False
    assert admission.gate(request()) is False


def test_operator_opt_ins_never_override_a_known_different_socket_owner(admission):
    admission.opt_in(unverified=True)
    admission.files[TCP] = relay_table(uid=UID + 1)
    assert admission.owner(request()) is False
    assert admission.gate(request()) is False


@pytest.mark.parametrize("headers", [
    {"x-forwarded-for": "198.51.100.1"},
    {"x-real-ip": "198.51.100.1"},
    {"forwarded": "for=198.51.100.1"},
    {"x-forwarded-host": "localhost"},
    {"x-forwarded-for": ""},
    {"origin": "https://attacker.example"},
    {"origin": "null"},
    {"origin": "ftp://localhost"},
], ids=["xff", "real-ip", "forwarded", "forwarded-host", "empty-forwarded-header",
        "remote-origin", "opaque-origin", "wrong-origin-scheme"])
def test_local_opt_ins_preserve_forwarding_and_browser_origin_checks(admission, headers):
    admission.opt_in(unverified=True)
    admission.files.clear()
    assert admission.gate(request(headers=headers)) is False


@pytest.mark.parametrize("peer,host", [
    ("198.51.100.1", "localhost:9090"),
    ("172.18.0.7", "localhost:9090"),
    ("invalid-address", "localhost:9090"),
    ("127.0.0.1", "attacker.example:9090"),
    ("127.0.0.1", "localhost.attacker.example:9090"),
    ("127.0.0.1", ""),
])
def test_local_opt_ins_preserve_peer_and_host_checks(admission, peer, host):
    admission.opt_in(unverified=True)
    admission.files.clear()
    assert admission.gate(request(peer=peer, host=host)) is False


def test_local_opt_ins_still_reject_missing_peer(admission):
    admission.opt_in(unverified=True)
    admission.files.clear()
    conn = request()
    conn.client = None
    assert admission.gate(conn) is False
