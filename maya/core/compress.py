"""
Compression seam (§13.4.2): zstandard preferred, stdlib zlib fallback.

The codec is written into the header of every compressed payload, so a
payload compressed on one machine decompresses on another regardless of which
backend either resolved.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import zlib

from maya.core.backends import Backends

_ZSTD, _ZLIB = b"MZS1", b"MZL1"


def compress(data: bytes) -> bytes:
    if Backends.selected("compress") == "zstandard":
        import zstandard

        return _ZSTD + zstandard.ZstdCompressor(level=6).compress(data)
    return _ZLIB + zlib.compress(data, 6)


def decompress(data: bytes) -> bytes:
    magic, body = data[:4], data[4:]
    if magic == _ZSTD:
        import zstandard

        return zstandard.ZstdDecompressor().decompress(body)
    if magic == _ZLIB:
        return zlib.decompress(body)
    raise ValueError("Unknown compression header")


def procstat() -> dict[str, float | None]:
    """Process resource reporting (the procstat seam). Never used for caps."""
    if Backends.selected("procstat") == "psutil":
        import psutil

        p = psutil.Process()
        return {
            "rss_mb": p.memory_info().rss / 2**20,
            "cpu_percent": p.cpu_percent(None),
            "threads": float(p.num_threads()),
        }
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        return {"rss_mb": rss, "cpu_percent": None, "threads": None}
    except ImportError:
        return {"rss_mb": None, "cpu_percent": None, "threads": None}
