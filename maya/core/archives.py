"""
Reading an archive somebody else made (§21.1).

A zip file describes its own contents, and a small one can describe an enormous
expansion: a few kilobytes of zeros that inflate to gigabytes, thousands of entries, or
a name that escapes the directory it is read into. MAYA reads two kinds of archive from
outside — a reproducibility bundle offered for verification, and a spreadsheet offered as
a model — so the limits live here and both go through them. What is refused is named, and
nothing is read before the refusal: the entry table is checked first, and reading each
member stops at its declared size.

The limits are deliberately generous; they exist to bound the damage of a hostile file,
not to constrain a real one.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import zipfile
from typing import Any

from maya.core.errors import ValidationFailed

MAX_ENTRIES = 5_000
MAX_TOTAL_BYTES = 2 * 1024**3  # 2 GiB expanded
MAX_RATIO = 200  # expanded : compressed, over the archive as a whole


def limits(settings: Any = None) -> dict[str, int]:
    """The limits in force, from configuration where it is given."""
    if settings is None:
        return {"entries": MAX_ENTRIES, "bytes": MAX_TOTAL_BYTES, "ratio": MAX_RATIO}
    return {
        "entries": settings.int("api.limits.archive.max_entries", MAX_ENTRIES),
        "bytes": settings.int("api.limits.archive.max_expanded_bytes", MAX_TOTAL_BYTES),
        "ratio": settings.int("api.limits.archive.max_expansion_ratio", MAX_RATIO),
    }


def check(zf: zipfile.ZipFile, *, settings: Any = None, what: str = "archive") -> None:
    """Refuse an archive whose own entry table says it is hostile, before reading it."""
    caps = limits(settings)
    infos = zf.infolist()
    if len(infos) > caps["entries"]:
        raise ValidationFailed(
            f"This {what} declares {len(infos)} entries; at most {caps['entries']} are read",
            entries=len(infos),
            limit=caps["entries"],
        )
    expanded = sum(i.file_size for i in infos)
    if expanded > caps["bytes"]:
        raise ValidationFailed(
            f"This {what} expands to {expanded / 1e6:.0f} MB; at most "
            f"{caps['bytes'] / 1e6:.0f} MB is read",
            expanded_bytes=expanded,
            limit=caps["bytes"],
        )
    compressed = sum(i.compress_size for i in infos) or 1
    if expanded // compressed > caps["ratio"]:
        raise ValidationFailed(
            f"This {what} expands {expanded // compressed} times over, past the "
            f"{caps['ratio']}× limit: it is a decompression bomb or close enough to one",
            expansion_ratio=expanded // compressed,
            limit=caps["ratio"],
        )
    for i in infos:
        name = i.filename
        if name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
            raise ValidationFailed(
                f"This {what} holds an entry that would be written outside it: {name!r}",
                entry=name,
            )


def read(zf: zipfile.ZipFile, name: str, *, settings: Any = None, what: str = "archive") -> bytes:
    """One member, read no further than its declared size (a lying header cannot make
    MAYA read more than the entry table promised)."""
    info = zf.getinfo(name)
    caps = limits(settings)
    if info.file_size > caps["bytes"]:
        raise ValidationFailed(
            f"{name} in this {what} is {info.file_size / 1e6:.0f} MB; "
            f"at most {caps['bytes'] / 1e6:.0f} MB is read",
            entry=name,
            limit=caps["bytes"],
        )
    with zf.open(name) as fh:
        data = fh.read(info.file_size + 1)
    if len(data) > info.file_size:
        raise ValidationFailed(
            f"{name} in this {what} is larger than its entry table says, which no honest "
            "archive is",
            entry=name,
        )
    return data


def opened(data: bytes, *, settings: Any = None, what: str = "archive") -> zipfile.ZipFile:
    """``data`` as a zip file, checked. Raises ValidationFailed, never BadZipFile."""
    import io

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationFailed(f"This {what} is not a readable zip file: {exc}") from exc
    check(zf, settings=settings, what=what)
    return zf


__all__ = ["MAX_ENTRIES", "MAX_RATIO", "MAX_TOTAL_BYTES", "check", "limits", "opened", "read"]
