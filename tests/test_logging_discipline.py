"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

No exception is ignored or swallowed. Ever.

This is a rule about the whole codebase rather than about any one function, so it
is tested the way such rules have to be tested — by inspecting the source itself.
Every ``except`` handler in every module must log, through the standard logger.

A handler may still decide to carry on: return a default, skip a malformed row,
translate a domain refusal into an HTTP status. What it may not do is make that
decision invisible. In a system whose entire product is evidence, an error that
left no trace is not merely a debugging inconvenience — it is a governance claim
resting on something nobody checked.

Written as an AST walk rather than a grep so that it cannot be fooled by the word
"logger" appearing in a comment or a string.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = sorted(
    p for d in ("core", "db", "routes") for p in (ROOT / d).rglob("*.py")
) + [ROOT / "run_maya_web.py"]

LOGGING_CALLS = {"debug", "info", "warning", "error", "critical", "exception", "log", "swallowed"}


def _logs(node: ast.ExceptHandler) -> bool:
    """True when the handler body makes a logging call at any depth."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        if isinstance(fn, ast.Attribute) and fn.attr in LOGGING_CALLS:
            return True
        if isinstance(fn, ast.Name) and fn.id in LOGGING_CALLS:
            return True
    return False


def _handlers():
    for path in SOURCE:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                yield path.relative_to(ROOT), node


def test_source_files_were_found():
    """Guard against the walk silently covering nothing."""
    assert len(SOURCE) > 15
    assert sum(1 for _ in _handlers()) > 0, "no except handlers found — is the walk working?"


def test_no_exception_is_handled_without_logging():
    silent = [f"{path}:{h.lineno}" for path, h in _handlers() if not _logs(h)]
    assert not silent, (
        "these exception handlers do not log; every handler must record what it "
        "recovered from, through core.log:\n  " + "\n  ".join(silent))


def test_no_bare_except():
    """`except:` catches KeyboardInterrupt and SystemExit as well. Never right here."""
    bare = [f"{path}:{h.lineno}" for path, h in _handlers() if h.type is None]
    assert not bare, "bare `except:` found at:\n  " + "\n  ".join(bare)


def test_no_handler_body_is_only_pass():
    """`except X: pass` is the exact shape the rule exists to forbid."""
    empty = [f"{path}:{h.lineno}" for path, h in _handlers()
             if all(isinstance(s, ast.Pass) for s in h.body)]
    assert not empty, "handler discards the exception entirely at:\n  " + "\n  ".join(empty)


@pytest.mark.parametrize("path", [p for p in SOURCE if p.name not in ("log.py",)])
def test_modules_use_the_standard_logger(path):
    """No module builds its own logger with logging.getLogger directly."""
    src = path.read_text()
    if "getLogger" in src:
        assert "core.log" in src, (
            f"{path.relative_to(ROOT)} calls logging.getLogger directly; "
            "use core.log.get_logger so every logger shares one hierarchy and format")
