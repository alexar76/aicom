"""The AWR/2 conformance CLI (SPEC.md section 17).

    awr verify <file> [--profile L0|L1|L2] [--parents <file>...] [--now <rfc3339>]
    awr canonicalize <file>
    awr digest <file>
    awr hashdata <file>
    awr issue <subject-file> --key <file> [--type <type>]

Exit codes: ``0`` valid / operation succeeded, ``1`` invalid document (a result was
produced), ``2`` usage or I/O error, ``3`` unimplemented subcommand.

Only the specified payload goes to stdout; every diagnostic goes to stderr.  ``--now``
exists so that the time-dependent warnings (``AWR-TIME-001``/``002``) are testable
deterministically.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence, TextIO

from . import __version__
from .documents import AWR_TYPES, coerce_now, format_rfc3339_utc, issue
from .didkey import load_key_file, parse_did_key
from .errors import AwrError
from .jcs import canonicalize, loads
from .proof import hash_data_for_document
from .digest import canonical_sri
from .verify import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    is_bundle,
    verify as verify_any,
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_UNIMPLEMENTED = 3

SUBCOMMANDS = ("verify", "canonicalize", "digest", "hashdata", "issue")


def _read_bytes(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    with open(path, "rb") as handle:
        return handle.read()


def _load_supporting(paths: Sequence[str]) -> List[Dict[str, Any]]:
    """Load supporting documents: each file is an AWR document or a bundle."""
    documents: List[Dict[str, Any]] = []
    for path in paths:
        value = loads(_read_bytes(path))
        if is_bundle(value):
            inner = value.get("documents")
            if isinstance(inner, list):
                documents.extend(d for d in inner if isinstance(d, dict))
            continue
        if isinstance(value, list):
            documents.extend(d for d in value if isinstance(d, dict))
            continue
        if isinstance(value, dict):
            documents.append(value)
    return documents


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awr",
        description="AWR/2 reference implementation (SPEC.md section 17 CLI contract)",
    )
    parser.add_argument("--version", action="version", version="awr %s" % (__version__,))
    subparsers = parser.add_subparsers(dest="command")

    verify_parser = subparsers.add_parser("verify", help="verify a document or bundle")
    verify_parser.add_argument("file")
    verify_parser.add_argument("--profile", choices=("L0", "L1", "L2"))
    verify_parser.add_argument(
        "--parents",
        nargs="+",
        default=(),
        metavar="FILE",
        help="supporting documents or bundles: chain parents, verdicts, blame targets",
    )
    verify_parser.add_argument("--now", metavar="RFC3339")
    verify_parser.add_argument(
        "--subject", metavar="ID", help="bundle subject document id (section 9)"
    )
    verify_parser.add_argument(
        "--max-depth", type=int, default=DEFAULT_MAX_DEPTH, metavar="N"
    )
    verify_parser.add_argument(
        "--max-nodes", type=int, default=DEFAULT_MAX_NODES, metavar="N"
    )
    verify_parser.add_argument(
        "--expected-key",
        metavar="KEY",
        help=(
            "the signing key, supplied OUT OF BAND as a did:key or 64 hex characters "
            "(section 12.4). Required of any AWR/1 verification that is to mean "
            "anything: an AWR/1 signature covers credentialSubject only, so a key taken "
            "from the document attests no identity."
        ),
    )
    verify_parser.add_argument(
        "--no-legacy",
        action="store_true",
        help=(
            "decline AWR/1 verification entirely (AWR-LEGACY-005). Section 12 support "
            "is OPTIONAL and a deployment with no AWR/1 corpus should refuse the path."
        ),
    )

    canon_parser = subparsers.add_parser(
        "canonicalize", help="print the section 4 canonical bytes"
    )
    canon_parser.add_argument("file")

    digest_parser = subparsers.add_parser(
        "digest", help="print sha256-<base64> over the canonical bytes"
    )
    digest_parser.add_argument("file")

    hashdata_parser = subparsers.add_parser(
        "hashdata", help="print proofConfigHash, transformedDocumentHash, hashData as hex"
    )
    hashdata_parser.add_argument("file")

    issue_parser = subparsers.add_parser("issue", help="issue a signed document")
    issue_parser.add_argument("subject_file", metavar="subject-file")
    issue_parser.add_argument("--key", required=True, metavar="FILE")
    issue_parser.add_argument("--type", choices=AWR_TYPES, default="WorkReceipt")
    issue_parser.add_argument("--id", metavar="URI", help="document id (default: urn:uuid:...)")
    issue_parser.add_argument("--now", metavar="RFC3339")
    issue_parser.add_argument("--valid-from", metavar="RFC3339")
    issue_parser.add_argument("--valid-until", metavar="RFC3339")
    issue_parser.add_argument("--issuer-name", metavar="NAME")
    issue_parser.add_argument(
        "--include-public-key-jwk",
        action="store_true",
        help="embed issuer.publicKeyJwk (section 5.2)",
    )
    return parser


def _parse_expected_key(value: Optional[str]) -> Optional[bytes]:
    """Section 17: --expected-key is a did:key or a 64-character hex public key."""
    if value is None:
        return None
    text = value.strip()
    if text.startswith("did:key:"):
        return parse_did_key(text.split("#", 1)[0])
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        raise AwrError(
            "AWR-KEY-002",
            "--expected-key must be a did:key or 64 hex characters, got %r" % (value,),
        )
    if len(raw) != 32:
        raise AwrError(
            "AWR-KEY-002",
            "--expected-key hex must decode to 32 bytes, got %d" % (len(raw),),
        )
    return raw


def _cmd_verify(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    data = _read_bytes(args.file)
    supporting = _load_supporting(args.parents)
    result = verify_any(
        data,
        profile=args.profile,
        supporting=supporting,
        subject_id=args.subject,
        now=args.now,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        expected_key=_parse_expected_key(args.expected_key),
        no_legacy=args.no_legacy,
    )
    out.write(json.dumps(result, indent=2, ensure_ascii=False))
    out.write("\n")
    for entry in result.get("reasons", ()):
        err.write("error %s: %s\n" % (entry["code"], entry["detail"]))
    for entry in result.get("warnings", ()):
        err.write("warning %s: %s\n" % (entry["code"], entry["detail"]))
    return EXIT_OK if result.get("valid") else EXIT_INVALID


def _cmd_canonicalize(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    value = loads(_read_bytes(args.file))
    canonical = canonicalize(value)
    out.write(canonical.decode("utf-8"))
    return EXIT_OK


def _cmd_digest(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    value = loads(_read_bytes(args.file))
    out.write(canonical_sri(value))
    out.write("\n")
    return EXIT_OK


def _cmd_hashdata(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    document = loads(_read_bytes(args.file))
    if not isinstance(document, dict):
        err.write("hashdata expects a JSON object\n")
        return EXIT_USAGE
    try:
        proof_config_hash, transformed_hash, hash_data = hash_data_for_document(document)
    except ValueError as exc:
        err.write("hashdata: %s\n" % (exc,))
        return EXIT_USAGE
    out.write(
        "%s\n%s\n%s\n"
        % (proof_config_hash.hex(), transformed_hash.hex(), hash_data.hex())
    )
    return EXIT_OK


def _cmd_issue(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    subject = loads(_read_bytes(args.subject_file))
    if not isinstance(subject, dict):
        err.write("issue expects the credentialSubject as a JSON object\n")
        return EXIT_USAGE
    try:
        key = load_key_file(args.key)
    except (ValueError, OSError) as exc:
        err.write("issue: unusable --key file: %s\n" % (exc,))
        return EXIT_USAGE
    moment = format_rfc3339_utc(coerce_now(args.now))
    document = issue(
        subject,
        key,
        document_type=args.type,
        document_id=args.id,
        valid_from=args.valid_from or moment,
        valid_until=args.valid_until,
        created=args.valid_from or moment,
        issuer_name=args.issuer_name,
        include_public_key_jwk=args.include_public_key_jwk,
    )
    out.write(json.dumps(document, indent=2, ensure_ascii=False))
    out.write("\n")
    err.write("issued %s by %s\n" % (document["id"], key.did))
    return EXIT_OK


_HANDLERS = {
    "verify": _cmd_verify,
    "canonicalize": _cmd_canonicalize,
    "digest": _cmd_digest,
    "hashdata": _cmd_hashdata,
    "issue": _cmd_issue,
}


def main(
    argv: Optional[Sequence[str]] = None,
    out: Optional[TextIO] = None,
    err: Optional[TextIO] = None,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr

    if argv and not argv[0].startswith("-") and argv[0] not in SUBCOMMANDS:
        err.write(
            "awr: subcommand %r is not implemented; expected one of %s\n"
            % (argv[0], ", ".join(SUBCOMMANDS))
        )
        return EXIT_UNIMPLEMENTED

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse already wrote usage to stderr
        return int(exc.code or EXIT_USAGE)
    if not getattr(args, "command", None):
        parser.print_usage(err)
        err.write("awr: a subcommand is required (%s)\n" % (", ".join(SUBCOMMANDS),))
        return EXIT_USAGE

    handler = _HANDLERS[args.command]
    try:
        return handler(args, out, err)
    except AwrError as exc:
        # A canonicalization or key failure on a document is an invalid document, which
        # section 17 maps to exit code 1; the reason code goes to stderr.
        err.write("error %s: %s\n" % (exc.code, exc.detail))
        return EXIT_INVALID
    except FileNotFoundError as exc:
        err.write("awr: %s\n" % (exc,))
        return EXIT_USAGE
    except OSError as exc:
        err.write("awr: %s\n" % (exc,))
        return EXIT_USAGE
    except ValueError as exc:
        err.write("awr: %s\n" % (exc,))
        return EXIT_USAGE
