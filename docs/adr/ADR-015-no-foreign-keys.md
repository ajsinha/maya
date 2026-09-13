# ADR-015 — No foreign keys

*MAYA — Model & AI Lifecycle Assurance.*  **A decision, not an omission.**

**Status:** accepted · **Date:** 2026-09

## Context

The schema declares ninety-one tables and **zero** foreign-key constraints in
either dialect. Adversarial review [§4.5](../11-adversarial-review.md) found
this while attacking immutability, and the two halves of that finding have had
different fates. The immutability half is closed: `db/schema/immutable.py`
generates `BEFORE UPDATE` triggers that raise, applied at schema time.

The referential half stayed open, and it stayed open **undecided**, which is the
state this project treats as worse than either answer. A reader finding "no
foreign keys" in a review has no way to tell an oversight from a position.

## Decision

**There are no foreign-key constraints, and there will not be.** Referential
integrity is the application's business.

## Why

**The compensating control already exists and is stronger for the case that
matters.** `core/references/index.py` reads every table carrying a `model_id`
before a deletion and refuses one that anything still refers to, *naming what
refers to it*.

> **This sentence was not true when it was written, and the correction is worth
> keeping visible.** The index queried thirty-three of the thirty-eight tables;
> `validation`, `version_approval`, `model_assumption` and `model_limitation`
> were never read, so a model with an unfinished validation reported
> `deletable: true`. An ADR that rests a decision on a compensating control has
> to be right about what the control covers, and this one was not for two
> milestones. It is true now, and true by construction rather than by
> inspection: `core/retention/cascade.py` declares a disposition for **every**
> table carrying a `model_id`, and `tests/test_tombstones.py` fails the build if
> one is missing. See [14 §26a.2](../14-detailed-design.md) — the mechanism
> matters more than the instance, because the earlier guard test passed by
> matching the table's name *in prose*. A foreign key would refuse the same deletion with
`FOREIGN KEY constraint failed` and no indication of which of twenty tables
objected. The index is also the thing `test_schema_discipline` walks, so a
twenty-first table cannot be added without a decision about it — a guarantee a
constraint list does not give.

**`CREATE TABLE IF NOT EXISTS` and constraints do not combine.** There are no
migrations by design ([19 §4](../19-deploying-maya.md)). A table that already
exists is skipped whole, so a foreign key added later would reach a fresh
install and never a deployed one — the same defect that moved every `UNIQUE`
clause out of the table bodies and into `CREATE UNIQUE INDEX IF NOT EXISTS`.
Constraints that arrive only on new databases are worse than none, because the
schema file then describes a guarantee half the estate does not have.

**Insert order would become a schema concern.** The register is a graph with
cycles in it — a model references a version and a version references a model;
an amendment references both. Ordering every write to satisfy a constraint
graph is a cost paid on every future table, and it buys a check the reference
index already performs with a better error message.

## What this costs, stated plainly

**Orphan rows are possible.** Delete a row by a path that does not go through
the reference index — a direct `DELETE`, a repair script, a restore — and the
rows pointing at it survive pointing at nothing. Nothing in the database will
say so.

**The guarantee is only as good as the call sites.** This is exactly the
criticism §4.5 made of immutability before the triggers existed, and it is
accepted here rather than answered. The difference is that immutability was
being *claimed* in a comment while unenforced, and this is not claimed anywhere.

**A reviewer expecting them will not find them.** That is the reason this
document exists.

## What would change this

A deployment that grants the application role `DELETE` on tables the reference
index does not read, or a second writer against the same database. Both are
outside the single-process, single-writer deployment this platform is built
for — and if either arrives, the argument above stops holding rather than
weakening.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
