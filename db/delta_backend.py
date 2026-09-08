"""
MAYA — which Delta implementation is in use, decided once.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

`deltalake` ships as a compiled Rust extension, and some estates forbid binary
wheels outright — no amount of vendoring helps, because there is nothing to
vendor that is allowed to run. `maya_deltalake` is a pure-Python implementation
of the six calls MAYA makes, writing the real Delta transaction log, and this
chooses between them.

**Chosen once, here.** Three modules imported `deltalake` directly, and three
import sites is three places to get the fallback wrong — the usual way being
that two of them fall back and the third raises ImportError at the moment
somebody exports a large table. Everything now imports from this module.

**Preferring the real one is deliberate.** Where `deltalake` is installed it is
faster, it is the reference implementation, and it supports the whole protocol.
The fallback exists so an estate that cannot install it is not shut out, not to
replace it. `MAYA_DELTA_BACKEND` forces the choice, which is how the
conformance suite runs the same tests against both.

**The choice is announced.** At INFO when the real one is found, at WARNING
when it is not — because "this instance is running on the fallback" is
something an operator should learn from the log rather than from a difference
in behaviour. The `/health` payload carries it too.
"""
from __future__ import annotations

import os
from typing import Any

from core.log import get_logger

logger = get_logger(__name__)

#: `deltalake`, `maya_deltalake`, or unset to prefer the real one and fall back.
ENV = "MAYA_DELTA_BACKEND"

REAL = "deltalake"
FALLBACK = "maya_deltalake"


def _choose() -> "tuple[str, Any, Any]":
    """The backend, its DeltaTable and its write_deltalake.

    Typed `Any`, deliberately. The two implementations are interchangeable
    ACROSS THE SUBSET MAYA USES and are different types everywhere else —
    `deltalake.DeltaTable` supports merge, vacuum, object stores and a protocol
    version this does not — so no annotation can say "these are the same"
    without lying about the ninety per cent that differs.

    What holds them equal is `tests/test_maya_deltalake.py`: one test body run
    against both, plus tables written by each and read by the other. That is a
    stronger statement than a shared signature, because it is about behaviour
    rather than about shape.

    The MODULES are imported rather than the names, so the two branches do not
    bind one local name to two different types — which is a real complaint and
    not a nuisance: it is the type checker noticing exactly the substitution
    this file exists to make.
    """
    wanted = (os.environ.get(ENV) or "").strip().lower()

    if wanted == FALLBACK:
        import maya_deltalake as forced_fallback
        logger.warning(
            "using the %s fallback because %s asks for it. It implements the "
            "subset MAYA uses and writes the real Delta log, so tables stay "
            "readable by Spark and by deltalake — but it is single-writer, "
            "local-filesystem only, and refuses anything outside that subset.",
            FALLBACK, ENV)
        return (FALLBACK, forced_fallback.DeltaTable,
                forced_fallback.write_deltalake)

    if wanted == REAL:
        # Asked for by name: an ImportError here is the right outcome. Falling
        # back silently after being told which to use would make the setting a
        # suggestion, and a setting quietly ignored is worse than one not
        # offered.
        import deltalake as forced_real
        logger.info("using the %s package, as %s asks", REAL, ENV)
        return REAL, forced_real.DeltaTable, forced_real.write_deltalake

    if wanted:
        raise ValueError(
            f"{ENV}={wanted!r} is not a Delta backend; use '{REAL}' or "
            f"'{FALLBACK}', or leave it unset to prefer {REAL} and fall back")

    try:
        import deltalake as preferred
    except ImportError as exc:
        import maya_deltalake as fallback
        logger.warning(
            "the %s package is not importable (%s), so MAYA is using its own "
            "%s. It writes the real Delta transaction log — tables remain "
            "readable by Spark, Databricks and deltalake itself — and it "
            "implements only the subset MAYA uses: single writer, local "
            "filesystem, no merge, no partitioning, no object store. Anything "
            "outside that refuses by name rather than approximating.",
            REAL, exc, FALLBACK)
        return FALLBACK, fallback.DeltaTable, fallback.write_deltalake
    logger.info("Delta backend: %s", REAL)
    return REAL, preferred.DeltaTable, preferred.write_deltalake


_backend, _table, _write = _choose()

#: Annotated `Any` at the point of binding. mypy is correct that the two
#: implementations are different types and wrong that it matters here: what
#: makes them substitutable is the conformance suite, which runs one test body
#: against both and reads each one's tables with the other. A type annotation
#: claiming they are the same would be asserting something no annotation can
#: check, in place of something a test does check.
BACKEND: str = _backend
DeltaTable: Any = _table
write_deltalake: Any = _write

#: True when the compiled reference implementation is in use.
IS_REAL = BACKEND == REAL


def describe() -> dict:
    """What is in use, for `/health` and for a soak report to record.

    A run whose result depends on which implementation was underneath should
    say which it was, and asking afterwards is asking the wrong process.
    """
    return {"backend": BACKEND, "reference_implementation": IS_REAL,
            "detail": ("the deltalake package" if IS_REAL else
                       "MAYA's own pure-Python subset — real Delta log, "
                       "single writer, local filesystem only")}


__all__ = [
    "BACKEND",
    "ENV",
    "FALLBACK",
    "IS_REAL",
    "REAL",
    "DeltaTable",
    "describe",
    "write_deltalake",
]
