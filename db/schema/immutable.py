"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What the database refuses to let anybody change, and why it is here at all.

`db/schema/tables.py` carried a comment — *"Versions are immutable. There is no
UPDATE path other than status"* — written where a reader expects a constraint.
It was true of the callers and enforced by nothing: `Repository.set()` is
generic, `VersionRepository` overrode nothing, and there were **zero** triggers
and **zero** foreign keys in either dialect across ninety-one tables. Adversarial
review `§4.5` put it plainly: that is a convention, and conventions are what this
platform exists to replace with proofs.

## The rule these follow, which is finding C-3's

C-3 was raised against a Postgres `RULE ... DO INSTEAD NOTHING`: an UPDATE that
appeared to succeed and silently changed nothing. The defect never shipped, but
the principle it established did, and it is design rule **E8** —

> **Silence is never an acceptable enforcement mechanism for an integrity
> control.**

So every trigger here **raises**. A caller that tries to rewrite history is told
so, loudly, with the column named. Nothing is discarded quietly and nothing
returns success.

## Two shapes

**Immutable columns.** The row may change; these fields may not. `model_version`
is the case the comment described: `status` moves through its lifecycle and
everything describing *what the model is* was fixed when the version was
created. Changing `manifest_digest` after approval would leave the register
describing a model nobody approved.

**Append-only tables.** The row may not change at all, and may not be deleted.
`evidence_node` is the chain: `verify_chain` re-derives each node's content hash
and re-links it, so a mutation is *detected* — but detection is a report after
the fact, and C-4 asked for the other half. Nothing in `core/` updates or
deletes an evidence node, which is exactly why the constraint costs nothing and
is worth having: the day something does, it will be an accident.

## What this is not

It is **not** the whole of `§4.5`. There are still no foreign keys, so
referential integrity remains the application's business, and a generic `DELETE`
still reaches most tables. What this closes is the specific claim the documents
make — that an approved version and the evidence chain cannot be rewritten —
which was the part being asserted without an enforcer behind it.
"""
from __future__ import annotations

from typing import Dict, Tuple

#: Columns that may never change once the row exists, by table.
#:
#: `status` is deliberately absent from `model_version`: it is the one field the
#: lifecycle moves, and the comment this replaces said so.
IMMUTABLE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "model_version": (
        "model_id", "semver", "manifest", "manifest_digest",
        "trainability_class", "parameter_kind", "fit_procedure",
        "deterministic", "input_schema", "parameter_schema", "output_schema",
        "artifact_digest", "created_at", "created_by",
    ),
}

#: Tables that accept inserts and nothing else. No UPDATE, no DELETE.
APPEND_ONLY: Tuple[str, ...] = (
    "evidence_node",
)

#: What a refusal says. The column and the table are in it because a trigger
#: that says "constraint violated" sends somebody to read the schema, and the
#: whole argument for raising rather than discarding is that the caller finds
#: out what they did.
WHY_IMMUTABLE = (
    "is immutable: it describes what the version IS, and changing it would "
    "leave the register describing a model nobody approved. Create a new "
    "version"
)
WHY_APPEND_ONLY = (
    "is append-only: it is the evidence chain, and a row that can be rewritten "
    "or removed is not evidence. Append a correcting node instead"
)

#: Rows that must be empty of content, and the flag that says so.
#:
#: **H-3 — immutable evidence versus erasure.** The chain cannot be edited, and
#: an erasure request over a node carrying personal data would therefore be a
#: request the register could not honour. Law L-18 answers it by **discarding**
#: the payload at append time rather than storing an erasable pointer: there is
#: no `payload_uri`, no per-subject key and no shred path anywhere here, which
#: is the stronger guarantee for the law as stated — there is nothing to erase,
#: so nothing to leak — and the weaker one for anybody hoping to resolve it
#: later.
#:
#: The review's disposition was *satisfied in the law, not in the mechanism*,
#: and that was exactly right: the discarding happened in `EvidenceEngine._try`
#: and **nothing enforced it**. Any other writer — a migration, a repair
#: script, a future call site, a test fixture — could insert a node with the
#: flag set and the content still in it, and the chain would hash it, verify
#: it, and hold personal data in a table that cannot be corrected.
#:
#: A control that lives in one function is a convention. This makes it a
#: constraint, in both dialects, at the only layer every writer goes through.
EMPTY_WHEN_FLAGGED: Dict[str, Tuple[str, str]] = {
    # table: (flag column, column that must be empty)
    "evidence_node": ("contains_personal_data", "payload"),
}

WHY_EMPTY = (
    "a node flagged as containing personal data must store an EMPTY payload. "
    "The chain cannot be edited, so a node that holds content it may later be "
    "asked to erase is a request this register could never honour. Law L-18: "
    "the payload is discarded at append, not stored behind a pointer"
)


def sqlite_statements() -> list:
    """`BEFORE UPDATE` triggers raising `ABORT`, and delete guards."""
    out = []
    for table, columns in sorted(IMMUTABLE_COLUMNS.items()):
        for column in columns:
            out.append(
                f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{column}\n"
                f"BEFORE UPDATE OF {column} ON {table}\n"
                f"FOR EACH ROW WHEN OLD.{column} IS NOT NEW.{column}\n"
                f"BEGIN\n"
                f"    SELECT RAISE(ABORT, '{table}.{column} {WHY_IMMUTABLE}');\n"
                f"END;")
    for table in sorted(APPEND_ONLY):
        out.append(
            f"CREATE TRIGGER IF NOT EXISTS append_only_{table}_update\n"
            f"BEFORE UPDATE ON {table}\n"
            f"BEGIN\n"
            f"    SELECT RAISE(ABORT, '{table} {WHY_APPEND_ONLY}');\n"
            f"END;")
        out.append(
            f"CREATE TRIGGER IF NOT EXISTS append_only_{table}_delete\n"
            f"BEFORE DELETE ON {table}\n"
            f"BEGIN\n"
            f"    SELECT RAISE(ABORT, '{table} {WHY_APPEND_ONLY}');\n"
            f"END;")
    for table, (flag, content) in sorted(EMPTY_WHEN_FLAGGED.items()):
        # BEFORE INSERT, because the table is append-only — there is no UPDATE
        # path to guard, and insert is the only moment the rule can be broken.
        out.append(
            f"CREATE TRIGGER IF NOT EXISTS empty_when_flagged_{table}\n"
            f"BEFORE INSERT ON {table}\n"
            f"FOR EACH ROW WHEN NEW.{flag} = 1\n"
            f"    AND NEW.{content} IS NOT NULL\n"
            f"    AND NEW.{content} NOT IN ('', '{{}}')\n"
            f"BEGIN\n"
            f"    SELECT RAISE(ABORT, '{table}.{content}: {WHY_EMPTY}');\n"
            f"END;")
    return out


def postgres_statements() -> list:
    """The same refusals, as `plpgsql` functions raising an exception.

    One function per table rather than per column: Postgres compares with `IS
    DISTINCT FROM`, which handles NULL the way the SQLite `IS NOT` above does,
    and a single function keeps the message identical across the columns it
    guards.
    """
    out = []
    for table, columns in sorted(IMMUTABLE_COLUMNS.items()):
        checks = "\n".join(
            f"    IF NEW.{c} IS DISTINCT FROM OLD.{c} THEN\n"
            f"        RAISE EXCEPTION '{table}.{c} {WHY_IMMUTABLE}';\n"
            f"    END IF;" for c in columns)
        out.append(
            f"CREATE OR REPLACE FUNCTION maya_immutable_{table}()\n"
            f"RETURNS trigger AS $$\nBEGIN\n{checks}\n    RETURN NEW;\n"
            f"END;\n$$ LANGUAGE plpgsql;")
        out.append(
            f"DROP TRIGGER IF EXISTS immutable_{table} ON {table};\n"
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE ON {table}\n"
            f"FOR EACH ROW EXECUTE FUNCTION maya_immutable_{table}();")
    for table in sorted(APPEND_ONLY):
        out.append(
            f"CREATE OR REPLACE FUNCTION maya_append_only_{table}()\n"
            f"RETURNS trigger AS $$\nBEGIN\n"
            f"    RAISE EXCEPTION '{table} {WHY_APPEND_ONLY}';\n"
            f"END;\n$$ LANGUAGE plpgsql;")
        out.append(
            f"DROP TRIGGER IF EXISTS append_only_{table} ON {table};\n"
            f"CREATE TRIGGER append_only_{table}\n"
            f"BEFORE UPDATE OR DELETE ON {table}\n"
            f"FOR EACH ROW EXECUTE FUNCTION maya_append_only_{table}();")
    for table, (flag, content) in sorted(EMPTY_WHEN_FLAGGED.items()):
        out.append(
            f"CREATE OR REPLACE FUNCTION maya_empty_when_flagged_{table}()\n"
            f"RETURNS trigger AS $$\nBEGIN\n"
            f"    IF NEW.{flag} AND coalesce(NEW.{content}, '') "
            f"NOT IN ('', '{{}}') THEN\n"
            f"        RAISE EXCEPTION '{table}.{content}: {WHY_EMPTY}';\n"
            f"    END IF;\n    RETURN NEW;\n"
            f"END;\n$$ LANGUAGE plpgsql;")
        out.append(
            f"DROP TRIGGER IF EXISTS empty_when_flagged_{table} ON {table};\n"
            f"CREATE TRIGGER empty_when_flagged_{table}\n"
            f"BEFORE INSERT ON {table}\n"
            f"FOR EACH ROW EXECUTE FUNCTION "
            f"maya_empty_when_flagged_{table}();")
    return out
