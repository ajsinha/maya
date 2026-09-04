"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The standardised logger.

Every module logs through ``get_logger(__name__)`` so that names form the package
hierarchy and a single level change reaches all of them.

The rule this exists to serve: **no exception is ignored or swallowed**. A
handler may decide to continue — returning a default, skipping a row — but it may
never do so silently. Something that went wrong and left no trace is the failure
that costs a week to diagnose, and in a governance system it is worse than that:
a value that quietly fell back to a default is a governance claim resting on a
fact nobody checked.

``tests/test_logging_discipline.py`` enforces this by inspecting the AST of every
source file, so the rule cannot rot.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure(level: str = "INFO", fmt: str = FORMAT) -> None:
    """Install the standard format on the root logger. Idempotent."""
    logging.basicConfig(level=str(level).upper(), format=fmt, datefmt=DATEFMT, force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def swallowed(logger: logging.Logger, exc: BaseException, action: str,
              detail: Optional[Any] = None, level: int = logging.WARNING) -> None:
    """Record a handled exception that the caller has chosen to recover from.

    Use this at every ``except`` that returns a default or skips a value. It is
    deliberately noisy at WARNING: recovering from an error is a decision, and a
    decision that never appears in a log is indistinguishable from a bug.
    """
    logger.log(level, "%s — recovered from %s: %s%s", action, type(exc).__name__, exc,
               f" ({detail})" if detail is not None else "", exc_info=level >= logging.ERROR)
