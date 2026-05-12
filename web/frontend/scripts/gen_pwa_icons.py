#!/usr/bin/env python3
"""Write static PNG icons for Web Manifest (Android install / maskable). Stdlib only."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

# Brand-adjacent solid fills (readable on launchers; full-bleed OK for maskable).
BG = (49, 46, 129)  # indigo-900-ish
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "icons"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def write_solid_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    row = b"\x00" + bytes([r, g, b] * width)
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    sig = b"\x89PNG\r\n\x1a\n"
    body = sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def main() -> None:
    write_solid_png(OUT / "icon-192.png", 192, 192, BG)
    write_solid_png(OUT / "icon-512.png", 512, 512, BG)
    print(f"OK — wrote {OUT / 'icon-192.png'} and {OUT / 'icon-512.png'}")


if __name__ == "__main__":
    main()
