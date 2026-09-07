"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A governed act and the record of it are one thing, or they are not a record.

Every service committed its state change and then appended to the chain as a
separate statement. A scan found **85** such pairs. `LifecycleService._move`
was the shape at its worst, because it is every lifecycle transition:

    self.registry.catalogue.models.set({"status": rule.target}, id=model["id"])
    self.evidence.append(f"model_{name}", "model", model["id"], ...)

Make the append fail — a full disk, a lost connection, the UNIQUE on `seq` —
and the model is `submitted` while the chain has no record of it. The caller
gets a 500 and retries, and the retry is refused as an illegal transition FROM
`submitted`. The hole is permanent and nothing in the product can close it.

Worse than untidy: segregation of duties is decided by reading this chain, so a
missing `version_created` node does not fail closed. "You cannot approve what
you created" simply has nothing left to read.

This test is the line held. It is the same shape as
`tests/test_logging_discipline.py`: a rule the codebase can be scanned for,
rather than a convention people remember.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

WRITES = ("add", "set", "remove")
SIMPLE = (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr, ast.Return, ast.Pass)


def _has_write(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr in WRITES for n in ast.walk(node))


def _is_append(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "append":
            value = n.func.value
            if isinstance(value, ast.Attribute) and value.attr == "evidence":
                return True
            if isinstance(value, ast.Name) and value.id == "evidence":
                return True
    return False


def _unatomic(path: pathlib.Path) -> list:
    """Write-then-record pairs with nothing holding them together."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    found = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for parent in ast.walk(function):
            for field in ("body", "orelse", "finalbody"):
                block = getattr(parent, field, None)
                if not isinstance(block, list) or isinstance(parent, ast.With):
                    continue
                for i, stmt in enumerate(block):
                    if not isinstance(stmt, SIMPLE) or not _has_write(stmt) \
                            or _is_append(stmt):
                        continue
                    for j in range(i + 1, min(i + 5, len(block))):
                        nxt = block[j]
                        if not isinstance(nxt, SIMPLE):
                            break
                        if _is_append(nxt):
                            head = "\n".join(
                                lines[max(0, stmt.lineno - 12):stmt.lineno - 1])
                            if "transaction(" not in head \
                                    and "recording(" not in head:
                                found.append(
                                    f"{path.relative_to(ROOT)}:{stmt.lineno}")
                            break
                        if _has_write(nxt):
                            break
    return found


def test_no_act_is_committed_before_the_record_of_it():
    """A repository write followed by an evidence append, with no transaction
    around the pair, is an act that can outlive its own record."""
    offenders = []
    for path in sorted(CORE.rglob("*.py")):
        offenders.extend(_unatomic(path))
    assert not offenders, (
        "these write-then-record pairs are not atomic — the act commits and "
        "the record of it is a separate statement, so a failure between them "
        "leaves the act done and unrecorded:\n    "
        + "\n    ".join(offenders)
        + "\nWrap each in `with self.evidence.recording():`.")


def test_the_helper_serialises_as_well_as_grouping():
    """`recording()` must take the evidence write lock, not merely open a
    transaction: the chain is read-then-write, and the lock has to be held
    before the outermost transaction reads anything."""
    import inspect

    from core.evidence import EvidenceEngine

    source = inspect.getsource(EvidenceEngine.recording)
    assert 'serialise="evidence_seq"' in source


def test_a_failed_record_rolls_the_act_back(tmp_path):
    """The behaviour, not the shape. With the append failing, the state change
    must not survive."""
    import pytest

    from core.evidence import EvidenceEngine
    from db import EvidenceRepository, ModelRepository
    from db.database import Database

    database = Database(f"sqlite:///{tmp_path}/atomic.db")
    database.apply_schema()
    evidence = EvidenceEngine(EvidenceRepository(database))
    models = ModelRepository(database)
    models.add({"urn": "maya://model/x", "name": "x", "model_class": "c",
                "domain": "credit", "owner": "o", "legal_entity": "uk",
                "purpose": "p", "status": "draft", "created_at": 1.0,
                "created_by": "t"})
    row = models.one(urn="maya://model/x")

    def fails(*_args, **_kwargs):
        raise RuntimeError("the disk went away between the two commits")

    evidence.append = fails                      # type: ignore[method-assign]
    with pytest.raises(RuntimeError), evidence.recording():
        models.set({"status": "submitted"}, id=row["id"])
        evidence.append("model_submit", "model", row["id"], {})

    assert models.one(id=row["id"])["status"] == "draft", \
        "the act outlived the record of it"
    assert not EvidenceRepository(database).many()
