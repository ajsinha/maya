# ADR-013 — Offsets for people, cursors for queues

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context

`core/domain/paging.py` pages every ordinary listing with `LIMIT`/`OFFSET`, and
its own docstring argues for that choice: *a governance register is read by
people who want page four, and an offset says what it means.* That argument is
right for what it covers.

It stops being right for one shape of list: **one that grows at the head while
somebody walks it.** The discovery queue is the case — a scanner posts candidates
while a triager works down them — and there the failure is silent. A candidate
arriving above your position shifts everything down by one, page 2 starts where
page 1 ended plus one, and **you skip a row**. Nothing errors. You receive a
complete-looking queue with a hole in it, and the hole is a model nobody triaged.

The obvious resolution — replace offsets with cursors everywhere — loses
something real. A person asking for page four of the model register is asking a
question a cursor cannot answer.

## Decision

**Keep both, and state which each is for.**

> Offsets where a **human wants page four**. Cursors where a **machine is
> draining a queue that is being filled**.

`core/http/conventions.py` holds the keyset cursor. It names *the last row seen*
rather than a position, so a write above it changes nothing. Two properties make
it safe:

**It is opaque, and that is not security.** Base64 is trivially readable and the
cursor holds nothing a caller is not entitled to. What opacity buys is that
nobody builds a client that *constructs* one — a hand-built cursor is a client
depending on an internal ordering, which is then an ordering that can never
change.

**It carries the ordering it was issued under**, and resuming under a different
sort is refused. Replaying a cursor under another ordering is a different query
that produces a plausible answer, and nothing in the result would show it.

`GET /api/v1/conventions` publishes the rule, so a client does not hold its own
idea of how paging works — a second implementation that drifts silently, because
a wrong cursor still returns rows.

## Consequences

- **+** The discovery queue can be drained safely while it is being filled, which
  is the only condition under which it is ever drained.
- **+** The register keeps *page four*, which is what most of its readers want.
- **+** A paged answer's shape is fixed now. When the repositories learn to page
  in the database rather than in Python, a client that walks with cursors keeps
  its guarantee and nothing about its code changes — the alternative, ship
  offsets now and fix it later, means changing every client.
- **−** **Two paging mechanisms**, and a reader has to know which applies. The
  mitigation is that both modules say so in their own docstrings and point at
  each other, and the endpoint publishes it.
- **−** The cursor pages **in Python**, over a list the repository returned. That
  is the honest shape of what the repositories do today, and pretending otherwise
  would be a paging API whose guarantee is a lie one layer down.
- **−** A cursor expires (one hour). Resuming a week-old walk of a register that
  has moved is not resuming anything, and it is refused rather than honoured.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
