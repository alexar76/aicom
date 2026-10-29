#!/usr/bin/env python3
"""Refuse structured signing secrets that text-token scanners do not recognize.

This checks the entire candidate export, including ignored files: an ignored path
can still be tracked in the destination Git index. Findings contain only paths,
types and SHA-256 fingerprints, never credential values or matching lines.

Solana JSON keypairs and raw seed+public key files are verified mathematically.
A 64-byte signature/public test vector therefore does not count as a private key.
Private-key fields and explicitly named raw private seeds fail closed; naming a
directory ``test`` or adding an ignore comment cannot exempt an actual key.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterator


_CHUNK_SIZE = 128 * 1024
_OVERLAP = 4096
_HEX_FIELD = re.compile(
    r"(?i)(?<![\w])['\"]?"
    r"(?:private[_-]?key|secret[_-]?key|signing[_-]?seed|private[_-]?seed)"
    r"['\"]?\s*[:=]\s*['\"]?(?:0x)?"
    r"(?P<secret>[0-9a-f]{128}|[0-9a-f]{64})(?![0-9a-z])"
)
_JSON_KEYPAIR = re.compile(r"\[\s*(?:[0-9]{1,3}\s*,\s*){63}[0-9]{1,3}\s*\]")
_PRIVATE_PEM = re.compile(
    r"(?m)^[ \t]*-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
)
# Credential encodings are ASCII. Match bytes directly so large public media
# blobs do not require a second, expanded Unicode representation in memory.
_HEX_FIELD_BYTES = re.compile(_HEX_FIELD.pattern.encode("ascii"))
_JSON_KEYPAIR_BYTES = re.compile(_JSON_KEYPAIR.pattern.encode("ascii"))
_PRIVATE_PEM_BYTES = re.compile(_PRIVATE_PEM.pattern.encode("ascii"))
_PRIVATE_NAME = re.compile(
    r"(?i)(?:^id_(?:rsa|ecdsa|ed25519)$|^master\.key$|"
    r"(?:^|[._-])(?:session[._-]secret|dataset[._-]salt|vrf[._-]sk|"
    r"conductor[._-]key|treasury[._-]scanner[._-]ref[._-]key|mldsa)(?:[._-]|$)|"
    r"(?:^|[._-])(?:private(?:[._-](?:key|seed))?|signing[._-](?:key|seed)|"
    r"secret[._-](?:key|seed)|seed)(?:[._-]|$))"
)
# The ten standard Anvil/Hardhat development accounts are already public test
# vectors, also recognized by verify_mirror_secrets.sh and prod_startup_guard.
# Pin their exact SHA-256 values; a test directory or a comment is not an excuse
# to admit another private key. This exception applies only to hex key fields,
# never to a Solana wallet or a private key file with a different encoding.
_PUBLIC_EVM_TEST_KEY_SHA256 = frozenset({
    "59891c96881dfbcf7d2ddc270b7813e666694fbbffe8ddd2736bf91c1b0e85d4",
    "bca4c2c0761d850f0c403a699280f70f86ab6659a611ada431019203cd66098f",
    "193ae84c4c9567c25105535802f463f3f8dc420b0ce9a5b57c7931c764e623d6",
    "e25a680eff8baac7b15129a830ecc40211017919d5d32fce8c6b409af753e50f",
    "6718ba8966161cc843e01e8d19f018859e1bcba7f0e8f2c108578b497ac408b7",
    "ac29b3735d1b57180dea890d6321cd27e593723cbe9e227eed8a3fa35945122c",
    "93e372c67f7238faf2dfdc029246b299e88d71937680cbb895fedeb2a262ed19",
    "59ad99d565557cc0968550ed2f5ea5ff5fd1d279324a25d324a531053c9c16a3",
    "2d1831e800ec18fe3e29da2e4357db936efce5b9792d76683d465582f0910db0",
    "25061aad2bb0917814989eb38f95608a744ecb8173fdce329486e8b83086e5f0",
})

# Strong provider-specific token shapes mirror the text gate. Inspect the actual
# Git index too: a clean worktree must not hide a previously staged credential.
_API_TOKEN_BYTES = re.compile(
    rb"(?i)\b(?:npm_[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{20,}|"
    rb"github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|"
    rb"sk-(?:ant|or-v1|proj)-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    rb"glpat-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{30,}|"
    rb"GOCSPX-[A-Za-z0-9_-]{20,}|[0-9]{8,10}:AA[A-Za-z0-9_-]{33}\b|"
    rb"aimk_[A-Za-z0-9_-]{32}(?![A-Za-z0-9_-])|"
    rb"(?-i:AKIA[0-9A-Z]{16}|AIzaSy[0-9A-Za-z_-]{33}))"
)
_HEX_TOKEN_BYTES = re.compile(
    rb"(?i)\b(?:ADMIN|API|MESH|OPERATOR)_TOKEN[\"']?\s*[:=]\s*[\"']?"
    rb"(?P<secret>[0-9a-f]{32,})(?![0-9a-z])"
)
# These frozen public proofs have binary sizes similar to private material. Pin
# contents as well as paths; size alone would also allow a padded signing key.
_PROOF_FIXTURE_SHA256 = {
    "contracts/solana/programs/acex-capital/tests/fixtures/legacy-zk/pubkey_validity.proof":
        "965369f2db0c0e05a0eb74fe20447d705a75e28a48832e56b5a4dcde62907bd1",
    "contracts/solana/programs/acex-capital/tests/fixtures/legacy-zk/zero_ciphertext.proof":
        "249cdb9321614cb0ca1982ab08cf10c78094c863e39bf4d3db4344419dabfa63",
}
_API_PREFIXES = (
    b"npm_", b"ghp_", b"gho_", b"github_pat_", b"sk-", b"xoxb-", b"xoxa-",
    b"xoxp-", b"xoxr-", b"xoxs-", b"glpat-", b"hf_", b"gsk_", b"gocspx-", b"aimk_",
    b"akia", b"aizasy",
)


def _prefixed_matches(pattern, window: bytes, lowered: bytes, prefixes, *, telegram: bool = False):
    """Use literal C searches before checking the complete credential grammar.

    Unanchored lookbehind/word-boundary regexes otherwise inspect every byte of
    multi-gigabyte media history. Candidate starts retain the original regex's
    boundary checks and leftmost, non-overlapping matching behavior.
    """
    positions = set()
    for prefix in prefixes:
        offset = 0
        while (index := lowered.find(prefix, offset)) != -1:
            positions.add(index)
            offset = index + 1
    if telegram:
        offset = 0
        while (index := lowered.find(b":aa", offset)) != -1:
            positions.update(start for start in (index - 10, index - 9, index - 8) if start >= 0)
            offset = index + 1
    end = 0
    for position in sorted(positions):
        if position >= end:
            match = pattern.match(window, position)
            if match:
                yield match
                end = match.end()


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str
    sha256: str


def _fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _named_private_material(path: str, raw: bytes) -> bool:
    """Recognize the private raw/base64/hex files our key writers actually save."""
    if not _PRIVATE_NAME.search(Path(path).name):
        return False
    if len(raw) in (32, 64):
        return True
    text = raw.strip()
    if re.fullmatch(rb"[0-9a-fA-F]{64}(?:[0-9a-fA-F]{64})?", text):
        return True
    if re.fullmatch(rb"[A-Za-z0-9_+/=-]{43,88}", text):
        try:
            decoded = base64.b64decode(text + b"=" * (-len(text) % 4), altchars=b"-_", validate=True)
        except (ValueError, binascii.Error):
            pass
        else:
            if len(decoded) in (32, 64):
                return True
    if "mldsa" in Path(path).name.lower():
        lines = text.splitlines()
        # Two-line public||secret files emitted by our ML-DSA key writers.
        if len(lines) == 2 and (len(lines[0]), len(lines[1])) in {
            (2624, 5120), (3904, 8064), (5184, 9792),
        } and all(re.fullmatch(rb"[0-9a-fA-F]+", line) for line in lines):
            return True
    return False


def _has_ed25519_private_pair(raw: bytes) -> bool:
    """Check seed||public bytes without guessing from entropy or file names."""
    if len(raw) != 64:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    except ImportError as exc:
        # Do not certify a candidate we cannot distinguish from a live keypair.
        raise RuntimeError("cryptography is required to verify 64-byte keypair candidates") from exc
    derived = Ed25519PrivateKey.from_private_bytes(raw[:32]).public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return derived == raw[32:]


def _der_private_key(raw: bytes) -> bool:
    if not raw.startswith(b"\x30"):
        return False
    try:
        from cryptography.hazmat.primitives.serialization import load_der_private_key
    except ImportError as exc:
        raise RuntimeError("cryptography is required to verify DER key candidates") from exc
    try:
        load_der_private_key(raw, password=None)
    except TypeError:
        # The parser recognized an encrypted private key and needs a password.
        # Encryption does not turn private signing material into a public asset.
        return True
    except ValueError:
        return False
    return True


def _files(root: Path) -> Iterator[Path]:
    """Walk physical export files without consulting any Git ignore settings."""
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=_walk_error):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            if name == ".git":
                continue
            path = Path(parent) / name
            if stat.S_ISREG(path.lstat().st_mode):
                yield path


def _walk_error(exc: OSError) -> None:
    raise OSError("cannot enumerate candidate export") from exc


def _export_path_findings(rel: str, digest: str) -> list[Finding]:
    findings = []
    if Path(rel).name == "_signing_key_storage.py":
        trusted = Path(__file__).resolve().parents[1] / "security" / "signing_key_storage.py"
        if digest != _fingerprint(trusted.read_bytes()):
            findings.append(Finding(rel, "unexpected-signing-storage-module", digest))
    normalized = "/" + rel.replace("\\", "/")
    for suffix, expected in _PROOF_FIXTURE_SHA256.items():
        if normalized.endswith("/" + suffix) and digest != expected:
            findings.append(Finding(rel, "modified-frozen-proof", digest))
    return findings


def _scan_stream(rel: str, source: BinaryIO, *, export_policy: bool = False) -> list[Finding]:
    findings: set[Finding] = set()
    first = source.read(_CHUNK_SIZE)
    if len(first) < _CHUNK_SIZE:
        if len(first) == 64 and _has_ed25519_private_pair(first):
            findings.add(Finding(rel, "raw-ed25519-keypair", _fingerprint(first)))
        if _named_private_material(rel, first):
            findings.add(Finding(rel, "named-private-seed", _fingerprint(first)))
        if len(first) >= 32 and _der_private_key(first):
            findings.add(Finding(rel, "der-private-key", _fingerprint(first)))

    previous = b""
    chunk = first
    digest = hashlib.sha256()
    has_pem = False
    while chunk:
        digest.update(chunk)
        window = previous + chunk
        lowered = window.lower()
        if export_policy:
            for match in _prefixed_matches(_API_TOKEN_BYTES, window, lowered, _API_PREFIXES, telegram=True):
                findings.add(Finding(rel, "api-token-literal", _fingerprint(match.group(0))))
            for match in _prefixed_matches(
                _HEX_TOKEN_BYTES, window, lowered,
                (b"admin_token", b"api_token", b"mesh_token", b"operator_token"),
            ):
                findings.add(Finding(rel, "hex-token-field", _fingerprint(match.group("secret"))))
        for match in _prefixed_matches(
            _HEX_FIELD_BYTES, window, lowered, (b"private", b"secret", b"signing"),
        ):
            secret = bytes.fromhex(match.group("secret").decode("ascii"))
            fingerprint = _fingerprint(secret)
            if fingerprint not in _PUBLIC_EVM_TEST_KEY_SHA256:
                findings.add(Finding(rel, "hex-private-key-field", fingerprint))
        for match in _JSON_KEYPAIR_BYTES.finditer(window):
            array = json.loads(match.group(0))
            if not all(isinstance(v, int) and 0 <= v <= 255 for v in array):
                continue
            raw = bytes(array)
            if _has_ed25519_private_pair(raw):
                findings.add(Finding(rel, "solana-json-keypair", _fingerprint(raw)))
        if b"PRIVATE KEY-----" in window:
            has_pem |= bool(_PRIVATE_PEM_BYTES.search(window))
        previous = window[-_OVERLAP:]
        chunk = source.read(_CHUNK_SIZE)
    if export_policy:
        findings.update(_export_path_findings(rel, digest.hexdigest()))
    if has_pem:
        findings.add(Finding(rel, "pem-private-key", digest.hexdigest()))
    return sorted(findings, key=lambda f: (f.path, f.kind, f.sha256))


def scan_bytes(path: str, data: bytes, *, export_policy: bool = False) -> list[Finding]:
    """Inspect one historical blob, returning fingerprints without matching text."""
    return _scan_stream(path, io.BytesIO(data), export_policy=export_policy)


def scan(root: Path) -> list[Finding]:
    findings: set[Finding] = set()
    for path in _files(root):
        # Never load/execute a module or configuration from the candidate tree.
        with path.open("rb") as source:
            findings.update(_scan_stream(path.relative_to(root).as_posix(), source, export_policy=True))
    return sorted(findings, key=lambda f: (f.path, f.kind, f.sha256))


def _read_metadata(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("unsupported Git index")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("unsupported Git index")
        return raw
    finally:
        os.close(fd)


class _BlobReader:
    def __init__(self, source: BinaryIO, length: int):
        self.source, self.remaining = source, length
        self.digest = hashlib.sha256()

    def read(self, length: int) -> bytes:
        length = min(length, self.remaining)
        raw = self.source.read(length)
        if len(raw) != length:
            raise ValueError("incomplete Git object")
        self.remaining -= length
        self.digest.update(raw)
        return raw


def scan_index(root: Path) -> list[Finding]:
    """Read staged blobs using disposable metadata, never repository Git policy.

    The working tree can have a clean replacement while the index still contains
    a secret. Copy only the regular index and point cat-file at the object store;
    original config, hooks, attributes, filters and credentials are never used.
    Nonstandard linked/split/alternate metadata needs manual review instead.
    """
    root = root.resolve()
    metadata = root / ".git"
    if not metadata.exists():
        return []
    objects = metadata / "objects"
    if metadata.is_symlink() or not metadata.is_dir() or objects.is_symlink() or not objects.is_dir():
        raise ValueError("unsupported Git metadata")
    if any(os.path.lexists(objects / "info" / name) for name in ("alternates", "http-alternates")):
        raise ValueError("unsupported Git alternates")
    index = metadata / "index"
    if not os.path.lexists(index):
        return []
    raw_index = _read_metadata(index, 64 * 1024 * 1024)
    binary = next((p for p in ("/usr/bin/git", "/bin/git") if os.access(p, os.X_OK)), None)
    if binary is None:
        raise RuntimeError("Git is required to inspect the staged export")
    with tempfile.TemporaryDirectory(prefix="aicom-secret-index-") as scratch:
        isolated = Path(scratch)
        (isolated / "objects").mkdir()
        (isolated / "refs").mkdir()
        (isolated / "HEAD").write_text("ref: refs/heads/main\n")
        (isolated / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = true\n")
        (isolated / "index").write_bytes(raw_index)
        env = {
            "PATH": "/usr/bin:/bin", "HOME": scratch, "XDG_CONFIG_HOME": scratch,
            "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/false", "SSH_ASKPASS": "/bin/false",
            "GIT_SSH_COMMAND": "/bin/false", "GIT_ALLOW_PROTOCOL": "",
            "GIT_PROTOCOL_FROM_USER": "0", "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1", "GIT_OBJECT_DIRECTORY": str(objects),
        }
        command = [binary, f"--git-dir={scratch}", "--no-pager"]
        for setting in (
            "core.hooksPath=/dev/null", "core.fsmonitor=false", "core.attributesFile=/dev/null",
            "core.pager=cat", "credential.helper=", "protocol.allow=never", "submodule.recurse=false",
        ):
            command += ["-c", setting]
        listed = subprocess.run(
            command + ["ls-files", "--stage", "-z"], cwd=scratch, env=env,
            capture_output=True, timeout=20, check=True,
        )
        entries: dict[str, list[str]] = {}
        for record in listed.stdout.split(b"\0"):
            if not record:
                continue
            header, separator, path = record.partition(b"\t")
            if not separator:
                raise ValueError("invalid Git index record")
            mode, oid, _stage = header.split()
            if mode not in (b"100644", b"100755"):
                continue  # Symlink and submodule entries do not publish their targets.
            if not re.fullmatch(rb"[0-9a-f]{40}", oid):
                raise ValueError("unsupported Git object format")
            entries.setdefault(oid.decode("ascii"), []).append(os.fsdecode(path))
        findings: set[Finding] = set()
        process = subprocess.Popen(
            command + ["cat-file", "--batch"], cwd=scratch, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            for oid, paths in entries.items():
                process.stdin.write(oid.encode("ascii") + b"\n")
                process.stdin.flush()
                reply = process.stdout.readline()
                header = reply.split()
                if len(header) != 3 or header[:2] != [oid.encode("ascii"), b"blob"] or not header[2].isdigit():
                    raise ValueError("unavailable Git blob")
                length = int(header[2])
                # Read once per object; names can affect raw-seed classification.
                raw = _BlobReader(process.stdout, length)
                if length < _CHUNK_SIZE:
                    content = raw.read(length)
                    rows = [row for path in paths for row in scan_bytes(path, content, export_policy=True)]
                else:
                    # Stream content once; evaluate path-sensitive source/proof
                    # policies separately for every alias of this Git object.
                    content_rows = _scan_stream("", raw, export_policy=True)
                    rows = [Finding(path, row.kind, row.sha256) for path in paths for row in content_rows]
                    rows += [row for path in paths for row in _export_path_findings(path, raw.digest.hexdigest())]
                if raw.remaining or process.stdout.read(1) != b"\n":
                    raise ValueError("invalid Git object framing")
                findings.update(Finding(row.path, "index-" + row.kind, row.sha256) for row in rows)
            process.stdin.close()
            if process.wait(timeout=20) != 0:
                raise ValueError("Git object inspection failed")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        return sorted(findings, key=lambda f: (f.path, f.kind, f.sha256))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--git-index", action="store_true", help="also inspect already staged Git blobs")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print("error: candidate export directory does not exist", file=sys.stderr)
        return 2
    try:
        findings = scan(args.root)
        if args.git_index:
            findings += scan_index(args.root)
    except Exception as exc:
        # Error strings may include parser input or file contents; emit only type.
        print(f"error: structured secret scan failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    if findings:
        print(json.dumps({"structured_secret_findings": [asdict(f) for f in findings]}, sort_keys=True))
        return 1
    print("OK structured secret check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
