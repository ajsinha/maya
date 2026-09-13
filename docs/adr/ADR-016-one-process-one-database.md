# ADR-016 — One process, one database

*MAYA — Model & AI Lifecycle Assurance.*  **A topology, chosen — and the three
findings it keeps open on purpose.**

**Status:** accepted · **Date:** 2026-09

## Context

Three findings from adversarial review have stayed open across every pass, and
re-reading them together shows they are **one finding in three costumes**:

- **[H-2](../11-adversarial-review.md#52-the-high-findings)** — the warrant
  plane reads the control-plane schema. There is no `warrant_projection` table;
  `WarrantService.resolve` reads normalised tables one at a time.
- **[H-9](../11-adversarial-review.md#52-the-high-findings)** — a single
  Postgres primary is a scaling ceiling. No replicas, no partitioning, and no
  separate audit database — because there is no `audit_log` table at all, the
  evidence chain being the audit trail deliberately.
- **[§4.9](../11-adversarial-review.md#49-the-interface-and-the-api-are-two-answers-to-one-question)**
  — the interface reads in-process rather than through its own API.

Each was raised as a coupling defect. Each costs **nothing today**. And each
forecloses the same thing: **deployment independence** — the ability to run the
warrant plane, the database and the interface as separately scaled, separately
failing, separately deployed components.

Leaving all three "open" was accurate and useless. A reader could not tell an
undecided gap from a chosen position, and three separate open rows implied
three separate pieces of work when there is one question underneath.

## Decision

**MAYA is deployed as one process against one database, and the three couplings
above are consequences of that topology rather than defects within it.**

They stay listed as open rather than closed or accepted, for a reason stated in
the next section.

## Why

**The couplings buy real things at this scale.** Reading normalised tables
inside one process means a warrant resolution sees the register's actual state
with no projection to fall behind. One database means a governance act and its
evidence node commit in one transaction — the property [§4.4] was raised about,
now held by 152 `evidence.recording()` blocks. The interface reading in-process
means the screen and the API cannot disagree about what the register says,
which is a class of bug that eventual consistency between a UI service and an
API service produces continuously.

**The alternative costs are not hypothetical.** A `warrant_projection` table is
a cache, and a cache of authorisation state is a thing that can authorise
something the register has already revoked. Read replicas make the revocation
floor a distributed problem. An interface that talks to the API over HTTP needs
its own authentication path, and a second authentication path is a second place
to get authorisation wrong.

**And the measurements do not currently argue for it.** The scale work
(`docs/19`) moved the estate fold from 33.4s to 7.6s at fifty thousand models by
indexing, not by distributing. Nothing measured so far is bounded by
single-process throughput.

## Why they stay OPEN rather than accepted

This is the part worth stating plainly, because it is unusual.

An accepted finding is one somebody has decided not to act on. These are
findings that are **inert under one topology and simultaneously real under
another** — and the day this platform is deployed as more than one process, all
three become live at the same moment, not gradually. Marking them accepted would
retire them from the list a person plans that deployment against, and they would
be rediscovered as production incidents rather than as design work.

So the disposition is: **open, with the condition that makes them urgent written
down.** Anyone reading [19 — Deploying MAYA](../19-deploying-maya.md) and
considering horizontal scale should find these three, together, before writing
the deployment.

## Consequences

- The single-process assumption is now **stated**, not inferred. Anything that
  silently depends on it — in-process reads, non-distributed locks, the
  `evidence.recording()` transaction span — is depending on a recorded decision.
- Multi-process deployment is a **design change**, not a configuration change,
  and this ADR is the entry point to it.
- The three findings stay in the review's open column with a pointer here, so
  the summary and the sections agree.
- Nothing in the code changes as a result of this ADR. It records what was
  already true and was previously only visible as three unrelated complaints.

## What would reopen this

A measurement, not an opinion: a workload where single-process throughput, not
query cost, is the binding constraint. `docs/19` is where that measurement would
be recorded, and `tools/spikes/` is where it would be taken.
