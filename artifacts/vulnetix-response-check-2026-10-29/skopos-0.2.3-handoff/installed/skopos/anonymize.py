"""Reduce a visitor's IP address to a non-identifying form at ingest.

An IP address is personal data under the GDPR (CJEU C-582/14, *Breyer*) and
"personal information" under the CCPA/CPRA. Storing the full address of every
visitor — indexed, and charted as "top visitors" — is the kind of processing
that needs a lawful basis, a retention limit and a notice. None of that is
needed for what SKOPOS actually asks of an address: a country, an ASN, and a
rough sense of "how many distinct people". All three survive reduction, because
the reduction happens *after* the geo/ASN lookup has read the real value.

The stored form is one of:

    truncate  IPv4 -> a.b.c.0 (/24), IPv6 -> /48. The default. "Top IPs" becomes
              "top /24s", which for spotting a scan or reading traffic shape is
              the same picture, but a single machine can no longer be singled
              out and the row is no longer personal data.
    hash      salted SHA-256, first 12 hex, prefixed ``h:``. Distinct-visitor
              counts stay exact; the address is unrecoverable without the salt.
    off       keep the full address, for an operator who has their own lawful
              basis and retention in place and needs the exact value.

Applied in the single ingest path (:func:`skopos.collector.ingest_lines`) so
every transport — SSH pull and pushed agent report alike — inherits it, and a
future transport cannot arrive without it. Mirrors :mod:`skopos.redact`, which
does the same for secrets in URLs.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re

Mode = str  # "truncate" | "hash" | "off"

_MODES = ("truncate", "hash", "off")

#: IPv4 host bits to drop. /24 keeps the network a request came from while
#: dropping the one host inside it.
_V4_PREFIX = 24
#: IPv6 is handed out so generously that a single /64 is often one subscriber;
#: /48 is the analytics convention and the smallest block reliably above one home.
_V6_PREFIX = 48


def _env_mode() -> Mode:
    raw = os.environ.get("SKOPOS_IP_ANONYMIZE", "truncate").strip().lower()
    if raw in _MODES:
        return raw
    # An unrecognised value is a typo, and the safe reading of a typo in a
    # privacy control is the protective one, not "off".
    return "truncate"


def _env_salt() -> str:
    return os.environ.get("SKOPOS_IP_HASH_SALT", "")


def anonymize_ip(
    ip: str | None, *, mode: Mode | None = None, salt: str | None = None
) -> str | None:
    """Return a non-identifying stand-in for ``ip`` under ``mode``.

    A value that is not a parseable IP address is returned unchanged: upstream
    clamping (:func:`skopos.collector._sanitise`) already nulls a ``remote_addr``
    that was meant to be an address but was not, so inventing a truncation of a
    non-address here would only paper over a parser bug.

    Traffic between our own hosts has no data subject, and the exact address is
    what makes an internal log useful to debug against, so private, loopback and
    link-local addresses are left whole.
    """
    if ip is None:
        return None
    mode = mode if mode is not None else _env_mode()
    if mode == "off":
        return ip
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return ip
    if mode == "hash":
        salt = salt if salt is not None else _env_salt()
        digest = hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:12]
        return f"h:{digest}"
    prefix = _V4_PREFIX if addr.version == 4 else _V6_PREFIX
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False).network_address)


def anonymize_parsed(pr, *, mode: Mode | None = None, salt: str | None = None) -> dict:
    """The field of a parsed request that IP anonymisation rewrites.

    Mirrors :func:`skopos.redact.redact_parsed`: returns only the changed fields,
    so the caller can splice them into a frozen ``ParsedRequest``. Only
    ``remote_addr`` is touched here — ``line_raw`` is deliberately left with its
    original address so the deduplication hash in
    :func:`skopos.db.insert_requests` still sees two distinct requests as
    distinct; that field is reduced at the storage boundary instead, by
    :func:`scrub_ips_in_text`, after the hash has been taken.
    """
    mode = mode if mode is not None else _env_mode()
    if mode == "off":
        return {}
    original = getattr(pr, "remote_addr", None)
    if not original:
        return {}
    anon = anonymize_ip(original, mode=mode, salt=salt)
    if anon == original:
        return {}
    return {"remote_addr": anon}


#: Best-effort address tokens in free text. Each candidate is validated by
#: :func:`anonymize_ip` before anything is rewritten, so a false match (a version
#: string, a byte count) is returned untouched rather than mangled.
_V4_TOKEN = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])")
_V6_TOKEN = re.compile(r"(?<![\w:])(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}(?![\w:])")


def scrub_ips_in_text(
    text: str | None, *, mode: Mode | None = None, salt: str | None = None
) -> str | None:
    """Reduce every IP address embedded in a free-text line.

    Used for the verbatim ``line_raw``, which is dropped entirely by default and
    kept only when ``SKOPOS_STORE_RAW_LINES`` is set for parser debugging. Even
    then it must not carry a full address that the ``remote_addr`` column no
    longer does, so this runs at storage time — after the deduplication hash of
    the original line has been computed.
    """
    if not text:
        return text
    mode = mode if mode is not None else _env_mode()
    if mode == "off":
        return text

    def _sub(m: re.Match) -> str:
        anon = anonymize_ip(m.group(0), mode=mode, salt=salt)
        return anon if anon is not None else m.group(0)

    return _V6_TOKEN.sub(_sub, _V4_TOKEN.sub(_sub, text))


def backfill_existing(con, *, mode: Mode | None = None, salt: str | None = None) -> int:
    """Rewrite the ``remote_addr`` of already-stored rows in place.

    Anonymisation at ingest protects only rows written from now on. Run this once
    after enabling it to bring the history to the same standard. It reads the
    distinct stored addresses rather than every row, so the work is proportional
    to how many addresses there are, not how many hits.
    """
    from .db import DbConnection  # local import to keep this module dependency-light

    assert isinstance(con, DbConnection)
    mode = mode if mode is not None else _env_mode()
    if mode == "off":
        return 0

    rows = con.execute(
        "SELECT DISTINCT remote_addr FROM http_requests "
        "WHERE remote_addr IS NOT NULL AND remote_addr <> ''"
    ).fetchall()

    changed = 0
    for row in rows:
        addr = row["remote_addr"] if con.backend == "postgresql" else row[0]
        anon = anonymize_ip(addr, mode=mode, salt=salt)
        if anon == addr:
            continue
        con.execute(
            "UPDATE http_requests SET remote_addr=? WHERE remote_addr=?",
            (anon, addr),
        )
        changed += 1
    con.commit()
    return changed


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .config import load_app_env, load_config
    from .db import connect_for_config, init_db

    parser = argparse.ArgumentParser(
        description="SKOPOS IP anonymisation maintenance (one-off backfill of stored rows)."
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("SKOPOS_CONFIG", "config.yaml"),
        help="path to the SKOPOS config YAML (default: $SKOPOS_CONFIG or config.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=list(_MODES),
        default=None,
        help="override SKOPOS_IP_ANONYMIZE for this run",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="rewrite the addresses already stored in http_requests",
    )
    args = parser.parse_args(argv)

    load_app_env()
    cfg = load_config(args.config)
    con = connect_for_config(cfg)
    init_db(con)
    try:
        if args.backfill:
            n = backfill_existing(con, mode=args.mode)
            print(f"anonymised {n} distinct address(es) across stored rows")
        else:
            print("nothing to do; pass --backfill to rewrite stored rows")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
