"""Write simple indigo PNG icons for the tenant PWA."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "public" / "icons"
RGB = (79, 70, 229)
INK = (255, 255, 255)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    raw = b"".join(
        b"\x00" + b"".join(bytes(pixels[y * width + x]) for x in range(width))
        for y in range(height)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def paint(size: int, pad_ratio: float = 0.18) -> list[tuple[int, int, int]]:
    pixels = [RGB] * (size * size)
    pad = int(size * pad_ratio)
    bar = max(2, size // 9)
    left = pad
    right = size - pad - bar
    top = pad
    bottom = size - pad
    mid = size // 2 - bar // 2
    for y in range(top, bottom):
        for x in range(left, left + bar):
            pixels[y * size + x] = INK
        for x in range(right, right + bar):
            pixels[y * size + x] = INK
    for y in range(mid, mid + bar):
        for x in range(left, right + bar):
            pixels[y * size + x] = INK
    return pixels


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size, name, pad in (
        (192, "icon-192.png", 0.2),
        (512, "icon-512.png", 0.2),
        (512, "icon-maskable-512.png", 0.28),
    ):
        write_png(OUT / name, size, size, paint(size, pad))


if __name__ == "__main__":
    main()
