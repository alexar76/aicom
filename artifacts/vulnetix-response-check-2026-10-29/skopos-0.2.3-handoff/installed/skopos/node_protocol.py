"""The wire contract between a monitored host and SKOPOS.

This file is shipped to every monitored host byte-for-byte and imported by both
ends, so that a signature the agent produces and a signature SKOPOS verifies can
never be computed from two subtly different strings. Two rules keep it that way:

* **stdlib only.** The agent may not install packages, so nothing here may import
  anything the host does not already have.
* **no SKOPOS imports.** ``import skopos`` on a monitored host would drag in the
  dashboard. A test asserts the absence of both.

Design notes that are load-bearing rather than stylistic:

Identity is never in the body. The signature covers ``key_id`` from a header, and
SKOPOS resolves that to a server name through its own credential table. A node
therefore cannot report as another host no matter what it puts in the document —
which is the single most important property of the whole protocol.

The signature covers the **exact bytes on the wire**, hashed, not a re-serialised
structure. Signing ``json.dumps(body)`` on one side and re-serialising on the
other diverges on key order, float formatting and unicode escaping, and the bug
only shows up for some payloads.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import zlib

#: Bumped when the document shape or the signing string changes. The receiver
#: refuses a version it does not know rather than guessing.
PROTOCOL_VERSION = 1

# --- Header names -----------------------------------------------------------

HDR_NODE = "X-Skopos-Node"
HDR_TIMESTAMP = "X-Skopos-Timestamp"
HDR_SEQ = "X-Skopos-Seq"
HDR_SIGNATURE = "X-Skopos-Sig"

# --- Limits -----------------------------------------------------------------
#
# Every one of these is a bound an attacker would otherwise choose for us. They
# are part of the protocol, not tuning knobs: the agent enforces them so it never
# builds a document the server will throw away, and the server enforces them
# again because the agent is not trusted.

MAX_BODY_BYTES = 8 * 1024 * 1024
#: Guards against a compressed body that expands to fill memory. Checked as a
#: running budget during decompression, never by decompressing first and
#: measuring afterwards.
MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

MAX_LINES_PER_REPORT = 20_000
MAX_LINE_BYTES = 8 * 1024
MAX_SOURCES = 64
MAX_SOURCE_ID_BYTES = 512
MAX_PROBE_BYTES = 512 * 1024

#: How far a report's clock may drift from the server's before it is refused.
#: Generous because monitored hosts genuinely do drift; skew is surfaced as a
#: diagnostic rather than silently tolerated.
MAX_CLOCK_SKEW_SECONDS = 900

#: A node that jumps this far ahead is not merely reordered — treat it as a
#: reinstall or a cloned credential and make a human look.
MAX_SEQ_ADVANCE = 10_000


class ProtocolError(ValueError):
    """The message is not well-formed. Never leaks which check failed to a peer."""


def canonical_signing_string(
    *, key_id: str, timestamp: int, seq: int, body: bytes
) -> bytes:
    """The exact bytes both ends run through HMAC.

    Fields are newline-separated and none of them may contain a newline (the
    caller's validation guarantees that), so the encoding is unambiguous — no
    field can be shifted into another by choosing a clever value.
    """
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join((str(key_id), str(int(timestamp)), str(int(seq)), digest)).encode(
        "utf-8"
    )


def sign(secret: bytes, *, key_id: str, timestamp: int, seq: int, body: bytes) -> str:
    material = canonical_signing_string(
        key_id=key_id, timestamp=timestamp, seq=seq, body=body
    )
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


def verify(
    secret: bytes, signature: str, *, key_id: str, timestamp: int, seq: int, body: bytes
) -> bool:
    expected = sign(secret, key_id=key_id, timestamp=timestamp, seq=seq, body=body)
    presented = str(signature or "")
    # compare_digest raises TypeError on a non-ASCII str, which would leave the
    # handler as a 500 — both an availability bug and a way to distinguish
    # inputs. A signature is hex; anything else is simply wrong.
    if not presented.isascii():
        return False
    return hmac.compare_digest(expected, presented)


#: gzip framing, not bare zlib. The request declares ``Content-Encoding: gzip``,
#: so the bytes have to actually be gzip — and a proxy or client library in the
#: middle is entitled to assume so. 16 + MAX_WBITS selects the gzip wrapper.
_GZIP_WBITS = 16 + zlib.MAX_WBITS


def compress(body: bytes) -> bytes:
    """gzip a document for transport. Reports are mostly repeated log prefixes."""
    obj = zlib.compressobj(6, zlib.DEFLATED, _GZIP_WBITS)
    return obj.compress(body) + obj.flush()


def decompress(blob: bytes, *, max_bytes: int = MAX_DECOMPRESSED_BYTES) -> bytes:
    """Inflate with a hard output budget.

    ``gzip.decompress(blob)`` would allocate whatever the stream asks for, so a
    1 MB body can become a 1 GB allocation. Feeding a bounded ``max_length`` and
    checking for leftovers costs nothing and removes the bomb entirely.
    """
    if len(blob) * MAX_COMPRESSION_RATIO < len(blob):  # pragma: no cover - overflow guard
        raise ProtocolError("invalid body")
    obj = zlib.decompressobj(_GZIP_WBITS)
    try:
        out = obj.decompress(blob, max_bytes)
    except zlib.error as e:
        raise ProtocolError("body is not valid gzip") from e
    if obj.unconsumed_tail or not obj.eof:
        raise ProtocolError("compressed body exceeds the permitted size")
    ratio_cap = max(1, len(blob)) * MAX_COMPRESSION_RATIO
    if len(out) > ratio_cap:
        raise ProtocolError("compressed body exceeds the permitted expansion ratio")
    return out


def encode_document(doc: dict) -> bytes:
    """Serialise a report deterministically.

    ``sort_keys`` and a compact separator are not cosmetic: they make the bytes a
    function of the content alone, so the same document always hashes the same
    way and a diff between two reports is readable.
    """
    return json.dumps(
        doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


#: ASCII digits only. ``str.isdigit()`` is true for Arabic-Indic and other
#: Unicode digit forms, which ``int()`` happily accepts — so two different header
#: strings would parse to the same number while signing as different bytes.
_ASCII_DIGITS = frozenset("0123456789")


def parse_int_header(raw, *, label: str) -> int:
    text = str(raw or "").strip()
    body = text[1:] if text[:1] == "-" else text
    if not body or len(text) > 20 or not set(body) <= _ASCII_DIGITS:
        raise ProtocolError(f"invalid {label}")
    return int(text)


def clean_line(raw) -> str | None:
    """Make one log line safe to store, or reject it.

    A log line is the most attacker-controlled value in the system: on a push
    host the agent chooses it outright, and on any host a request to the
    monitored site chooses most of it. Three things have to go before it reaches
    a database column.
    """
    if not isinstance(raw, str):
        return None
    # A NUL aborts the whole insert on PostgreSQL and truncates silently on
    # SQLite — one crafted line would otherwise discard the entire batch.
    if "\x00" in raw:
        return None
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError:
        # Lone surrogates survive json.loads but get mangled by the "replace"
        # error handler used for the dedup hash, which lets two different lines
        # collide and suppress each other.
        return None
    if not encoded.strip():
        return None
    if len(encoded) > MAX_LINE_BYTES:
        encoded = encoded[:MAX_LINE_BYTES]
        raw = encoded.decode("utf-8", errors="ignore")
    return raw
