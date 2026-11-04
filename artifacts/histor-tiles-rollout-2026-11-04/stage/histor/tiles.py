"""The label log as a tiled transparency log (c2sp.org/tlog-tiles), read-only.

A witness or monitor that knows only the C2SP specifications can follow HISTOR's log without its API:

    <prefix>/checkpoint                       the latest checkpoint (histor-tlog/2, with cosignatures)
    <prefix>/tile/<L>/<N>[.p/<W>]             Merkle tree tiles
    <prefix>/tile/entries/<N>[.p/<W>]         entry bundles: the leaf inputs, uint16 length-prefixed

``<prefix>`` is ``https://`` + the checkpoint origin (``histor.modelmarket.dev/log``), which is where a
witness that found the log in a witness-network list looks for it.

Nothing is computed here that the log does not already store. ``log_nodes`` holds every complete subtree
``node(level, index)`` (histor.merkle), and the hashes of tile ``N`` at level ``L`` are exactly the nodes
at tree level ``8·L`` with indices ``N·256 … N·256+255``: ``MTH(D[(N·256+i)·256^L : (N·256+i+1)·256^L])``.
A full tile is one indexed range read of 256 rows.

An entry is a label's leaf input, ``JCS(label)`` (RFC 8785), recomputed from the stored label. Every entry
of a bundle is hashed and compared with the level-0 node it must match before the bundle is served; a
mismatch, or an entry longer than the 65,535 bytes a uint16 prefix can carry, is refused rather than served.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from awr import canonicalize

from histor.db import Tx
from histor.store import Store

TILE_WIDTH = 256
TILE_HEIGHT = 8
HASH_SIZE = 32
MAX_LEVEL = 63
MAX_ENTRY = 0xFFFF

_LEVEL = re.compile(r"^(0|[1-9][0-9]?)$")
_WIDTH = re.compile(r"^[1-9][0-9]{0,2}$")


class TileError(ValueError):
    """A tile path that is not well formed, or a tile the log does not have yet (404)."""


class TileIntegrityError(RuntimeError):
    """Stored data that would make a wrong tile or bundle (500): refused, never served."""


@dataclass(frozen=True)
class Tile:
    level: int | None  # None for an entry bundle
    index: int
    width: int | None  # None for a full tile

    @property
    def entries(self) -> bool:
        return self.level is None

    @property
    def count(self) -> int:
        return self.width or TILE_WIDTH


def encode_index(index: int) -> str:
    """``1234067`` → ``x001/x234/067`` (all but the last element begin with ``x``)."""
    if index < 0:
        raise TileError("negative tile index")
    digits = str(index)
    digits = "0" * (-len(digits) % 3) + digits
    groups = [digits[i:i + 3] for i in range(0, len(digits), 3)]
    return "/".join(["x" + g for g in groups[:-1]] + [groups[-1]])


def tile_path(level: int | None, index: int, width: int | None = None) -> str:
    """The path below ``<prefix>/`` of a tile (``level`` None: an entry bundle)."""
    head = "tile/entries" if level is None else f"tile/{level}"
    suffix = f".p/{width}" if width is not None else ""
    return f"{head}/{encode_index(index)}{suffix}"


def parse_tile_path(path: str) -> Tile:
    """``<L>/<N>[.p/<W>]`` or ``entries/<N>[.p/<W>]`` — the part after ``tile/``. Strict: one spelling
    per tile, so a cache keyed by URL never holds the same tile twice."""
    parts = path.split("/")
    if not parts or not parts[0]:
        raise TileError("empty tile path")
    head, rest = parts[0], parts[1:]
    if head == "entries":
        level = None
    elif _LEVEL.match(head) and int(head) <= MAX_LEVEL:
        level = int(head)
    else:
        raise TileError("tile level must be 0..63 without leading zeros")
    width = None
    if len(rest) >= 2 and rest[-2].endswith(".p"):
        if not _WIDTH.match(rest[-1]) or not 1 <= int(rest[-1]) <= TILE_WIDTH - 1:
            raise TileError("partial tile width must be 1..255 without leading zeros")
        width = int(rest[-1])
        rest = rest[:-2] + [rest[-2][:-2]]
    if not rest:
        raise TileError("missing tile index")
    for element in rest[:-1]:
        if len(element) != 4 or element[0] != "x" or not element[1:].isdigit():
            raise TileError("index elements other than the last are x followed by three digits")
    if len(rest[-1]) != 3 or not rest[-1].isdigit():
        raise TileError("the last index element is three digits")
    digits = "".join(e.lstrip("x") for e in rest)
    index = int(digits)
    if encode_index(index) != "/".join(rest):  # e.g. a needless leading x000/
        raise TileError("tile index is not in its canonical spelling")
    return Tile(level=level, index=index, width=width)


def _available(tile: Tile, size: int) -> None:
    """Refuse a tile the tree of ``size`` leaves does not contain in full (spec: no empty tiles, and a
    partial tile only as wide as the nodes that exist)."""
    height = 0 if tile.entries else TILE_HEIGHT * tile.level
    nodes = size >> height  # complete nodes at that tree level
    first = tile.index * TILE_WIDTH
    if first + tile.count > nodes:
        raise TileError("the log does not have that tile yet")


def read_hash_tile(tx: Tx, tile: Tile, size: int) -> bytes:
    """The ``count`` hashes of a Merkle tree tile, concatenated (8,192 bytes for a full tile)."""
    if tile.entries:
        raise TileError("not a hash tile")
    _available(tile, size)
    level = TILE_HEIGHT * tile.level
    first = tile.index * TILE_WIDTH
    rows = tx.execute(
        "SELECT idx, hash FROM log_nodes WHERE level=? AND idx>=? AND idx<? ORDER BY idx",
        (level, first, first + tile.count),
    )
    if len(rows) != tile.count or any(int(r["idx"]) != first + i for i, r in enumerate(rows)):
        raise TileIntegrityError("the log's stored nodes do not cover that tile")  # see Store.append_leaf
    return b"".join(bytes.fromhex(r["hash"]) for r in rows)


def read_entry_bundle(tx: Tx, tile: Tile, size: int) -> bytes:
    """The leaf inputs of ``count`` consecutive labels, each prefixed by its big-endian uint16 length,
    checked one by one against the level-0 nodes before they are returned."""
    if not tile.entries:
        raise TileError("not an entry bundle")
    _available(tile, size)
    first = tile.index * TILE_WIDTH
    last = first + tile.count
    labels = tx.execute(
        "SELECT leaf_index, body FROM labels WHERE leaf_index>=? AND leaf_index<? ORDER BY leaf_index",
        (first, last),
    )
    leaves = tx.execute(
        "SELECT idx, hash FROM log_nodes WHERE level=0 AND idx>=? AND idx<? ORDER BY idx", (first, last)
    )
    if len(labels) != tile.count or len(leaves) != tile.count:
        raise TileIntegrityError("the log's stored labels do not cover that bundle")
    out = bytearray()
    for i, (label, leaf) in enumerate(zip(labels, leaves, strict=True)):
        if int(label["leaf_index"]) != first + i or int(leaf["idx"]) != first + i:
            raise TileIntegrityError("the log's stored labels do not cover that bundle")
        entry = canonicalize(json.loads(label["body"]))
        if hashlib.sha256(b"\x00" + entry).hexdigest() != leaf["hash"]:
            raise TileIntegrityError(f"label {first + i} does not hash to its leaf")
        if len(entry) > MAX_ENTRY:
            raise TileIntegrityError(f"label {first + i} is longer than an entry bundle can carry")
        out += len(entry).to_bytes(2, "big") + entry
    return bytes(out)


def read_tile(tx: Tx, tile: Tile) -> bytes:
    """A hash tile or an entry bundle for the log as it stands now."""
    size = Store.log_size(tx)
    return read_entry_bundle(tx, tile, size) if tile.entries else read_hash_tile(tx, tile, size)
