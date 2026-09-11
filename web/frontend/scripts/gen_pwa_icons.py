#!/usr/bin/env python3
"""Write static PNG icons for Web Manifest (Android install / maskable). Stdlib only.

Visual: dark indigo gradient + centered “CPU chip” motif (same idea as the navbar Cpu icon),
not a flat solid square — reads clearly at launcher sizes and stays inside maskable safe zone.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "icons"

# Background gradient stops (top → bottom), slate-900 → indigo-900 → indigo-500
C_TOP = (15, 23, 42)
C_MID = (49, 46, 129)
C_BOT = (99, 102, 241)
# Chip (indigo-400 / indigo-300 accents, inner die)
CHIP_FACE = (129, 140, 248)  # indigo-400
CHIP_BORDER = (199, 210, 254)  # indigo-200
CHIP_INNER = (30, 27, 75)  # indigo-950-ish
PIN = (165, 180, 252)  # indigo-300


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _lerp_rgb(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _new_buffer(width: int, height: int) -> list[list[tuple[int, int, int]]]:
    return [[(0, 0, 0) for _ in range(width)] for _ in range(height)]


def _fill_rect(
    buf: list[list[tuple[int, int, int]]],
    w: int,
    h: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    rgb: tuple[int, int, int],
) -> None:
    xa, xb = max(0, min(x0, x1)), min(w, max(x0, x1))
    ya, yb = max(0, min(y0, y1)), min(h, max(y0, y1))
    for y in range(ya, yb):
        row = buf[y]
        for x in range(xa, xb):
            row[x] = rgb


def _gradient_background(buf: list[list[tuple[int, int, int]]], w: int, h: int) -> None:
    for y in range(h):
        t = y / max(h - 1, 1)
        if t <= 0.5:
            c = _lerp_rgb(C_TOP, C_MID, t * 2.0)
        else:
            c = _lerp_rgb(C_MID, C_BOT, (t - 0.5) * 2.0)
        row = buf[y]
        for x in range(w):
            row[x] = c


def _draw_brand_chip(buf: list[list[tuple[int, int, int]]], s: int) -> None:
    w = h = s
    cx, cy = w // 2, h // 2
    u = max(s / 24.0, 1.0)

    # Outer package (border + face)
    half = int(4.2 * u)
    x0, x1 = cx - half, cx + half
    y0, y1 = cy - int(3.4 * u), cy + int(3.4 * u)
    _fill_rect(buf, w, h, x0 - 2, y0 - 2, x1 + 2, y1 + 2, CHIP_BORDER)
    _fill_rect(buf, w, h, x0, y0, x1, y1, CHIP_FACE)

    # Inner “die”
    ih, iw = int(2.0 * u), int(2.6 * u)
    _fill_rect(buf, w, h, cx - iw, cy - ih, cx + iw, cy + ih, CHIP_INNER)

    # Pins (left / right), three stacks — matches lucide Cpu feel
    pw, ph = max(1, int(0.55 * u)), max(2, int(1.1 * u))
    gap = int(1.25 * u)
    ys = [cy - gap, cy, cy + gap]
    lx0 = int(x0 - pw - int(0.35 * u))
    rx0 = int(x1 + int(0.35 * u))
    for yy in ys:
        _fill_rect(buf, w, h, lx0, yy - ph // 2, lx0 + pw, yy + ph // 2, PIN)
        _fill_rect(buf, w, h, rx0, yy - ph // 2, rx0 + pw, yy + ph // 2, PIN)


def write_brand_icon_png(path: Path, size: int) -> None:
    buf = _new_buffer(size, size)
    _gradient_background(buf, size, size)
    _draw_brand_chip(buf, size)

    rows: list[bytes] = []
    for y in range(size):
        raw_row = bytearray([0])
        for x in range(size):
            r, g, b = buf[y][x]
            raw_row.extend((r, g, b))
        rows.append(bytes(raw_row))
    raw = b"".join(rows)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    sig = b"\x89PNG\r\n\x1a\n"
    body = sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def main() -> None:
    write_brand_icon_png(OUT / "icon-192.png", 192)
    write_brand_icon_png(OUT / "icon-512.png", 512)
    print(f"OK — wrote {OUT / 'icon-192.png'} and {OUT / 'icon-512.png'}")


if __name__ == "__main__":
    main()
