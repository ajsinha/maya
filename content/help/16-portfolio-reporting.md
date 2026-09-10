---
title: Risk appetite and the board pack
slug: portfolio-reporting
section: Oversight
order: 135
icon: clipboard-data
summary: "An appetite statement is only a control if a machine can evaluate it. Twelve indicators derived from the register, limits declared with a rationale and versioned so a relaxation is findable, a pack kept as it was read, a query layer over entities rather than tables, supervisory extracts that name what they do not know — and why there is deliberately no single number."
audience: Model risk managers, Committees, Auditors
---

# Risk appetite and the board pack

A committee asks three questions, in this order:

1. **Are we inside the limits we set?**
2. **What is outside them?**
3. **What moved since we last met?**

A report answering only the first is a dashboard, and a dashboard is why nobody
reads the pack.

Each question needs something different. The first needs the limit to be
*computable*. The second needs the exception list to be the output rather than a
footnote. The third needs the previous pack to still exist as it was read, which
means a pack has to be a record and not a query.

## An appetite statement a machine can evaluate

In most banks an appetite statement is a sentence in a document. That is not a
control: nobody can compute against a sentence, so the number in the quarterly
pack is prepared by hand, and whether it is inside the limit is somebody's
judgement rather than an evaluation.

Here a limit is a **declared threshold over a metric the platform already
derives**, so utilisation is arithmetic and a breach is a fact.

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/risk-appetite \
  -H 'Content-Type: application/json' \
  -d '{"metric":"blocking_findings","limit":5,"amber":3,
       "owner":"person/s.iqbal",
       "rationale":"tolerance while the remediation programme runs; reviewed at
                    the March committee"}'
```

### The twelve things that may be held to a limit

The vocabulary is closed, and `GET /api/v1/risk-appetite/metrics` publishes it
with the reason each one matters.

| Metric | Direction | Unit |
|---|---|---|
| `models_untiered` — models with no risk tier assessed | lower is better | count |
| `models_not_in_force` — registered but not attested | lower is better | count |
| `blocking_findings` — open findings that block promotion and warrants | lower is better | count |
| `findings_overdue` — past the date their owner accepted | lower is better | count |
| `models_unmonitored` — in force, with no monitor defined | lower is better | count |
| `open_breaches` — monitor breaches currently open | lower is better | count |
| `overlay_magnitude` — aggregate absolute magnitude of live overlays | lower is better | amount |
| `overlays_persistent` — renewed past their limit | lower is better | count |
| `attestations_lapsed` — models whose attestation has expired | lower is better | count |
| `baseline_debt` — models carrying cold-start compliance debt | lower is better | count |
| `monitored_share` — share of models in force that are monitored | **higher** is better | ratio |
| `in_force_share` — share of registered models that are attested | **higher** is better | ratio |

Two of the twelve run the other way, and that is the reason direction is a
property of the metric rather than something its author declares. Whether more
is worse is a fact about *open blocking findings*, not an opinion somebody
expresses while setting a limit — and letting an author state it would let one
state it wrongly, producing a limit that reports green while the estate
deteriorates.

### Four refusals, and why each fires when it does

| Refusal | Fires when |
|---|---|
| `unknown_metric` | the metric is not one the platform computes |
| `rationale_required` | the limit carries no reason (or `rationale_too_long` past 2,000 characters) |
| `amber_beyond_limit` | the warning sits on the far side of the thing it warns about |
| `unknown_scope` | the scope names a dimension other than `tier`, `domain` or `legal_entity` |

All four fire **when the limit is written**, not when the report is run. A limit
that failed at the moment a committee was reading it would fail at the worst
possible time, and its author is long gone by then.

The rationale is the one worth arguing for. A number nobody can explain is a
number nobody will ever change, so it is either ignored or obeyed without
thought, and both are worse than not having it. The rationale travels into every
pack, so a reader who was not in the room can tell what the limit is *for*.

### Versions accumulate, and a relaxation is named

Nothing is edited. A limit that can be changed without a record is a limit that
can be **relaxed** without one, and the relaxation is exactly the event a reader
six months later comes looking for. So a new version is appended, and the
evidence node carries `relaxed: true` when the change made the limit easier to
satisfy — computed, not left to whoever wrote it.

A committee raising a limit because the estate grew is doing something
reasonable. A committee raising it because the estate breached it is doing
something else, and only the record tells the two apart.

```bash
curl -u s.iqbal:pw localhost:5006/api/v1/risk-appetite/history/blocking_findings
curl -u s.iqbal:pw localhost:5006/api/v1/risk-appetite    # live limits
```

Limits may be **scoped** to a tier, a domain or a legal entity. `GET
/api/v1/risk-appetite` lists them least specific first, which is the order they
resolve in: the most specific declared limit wins, and a scoped limit does not
supersede the estate-wide one — the same left-to-right precedence featuresets
and warrant profiles use. Retiring a limit stops the estate being held to it and
leaves every version on the record.

## The pack

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/board-packs/preview -d '{}'
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/board-packs \
  -H 'Content-Type: application/json' -d '{"period":"2026-Q1"}'
```

`preview` computes without recording; `POST /board-packs` records. Somebody
preparing for a meeting should be able to see what the pack will say before the
committee is minuted against what they find.

Each indicator comes back with its value, its limit and amber, its
**standing**, its utilisation, what it did since the last pack, and why a
committee cares about it at all — plus the limit's rationale, owner and version.

| Standing | Means |
|---|---|
| `within` | inside the limit |
| `amber` | past the warning threshold, not past the limit |
| `breach` | outside the limit |
| `no_appetite` | measured, with no limit declared — a number, not an indicator |

The `exceptions` list is every row standing at `amber` or `breach`. That is the
answer to question two, and it is a field rather than something a reader
assembles.

### An unmeasured indicator is never reported as clean

A metric this instance cannot compute — because the service that answers it is
not wired, or because computing it raised — comes back as `null` with the
reason, is listed under `unmeasured`, and the pack's headline says so in
capitals. **Zero is a measurement; an absent service is not**, and reporting one
as the other is how a committee is told an estate is healthy when it is
unobserved.

The same rule holds for ratios. `monitored_share` over an empty estate is
`null`, not 1.0 — reporting a perfect ratio over an empty set is the most
flattering possible lie.

### Movement, and when it is not comparable

`movement` compares against the last pack cut over the same scope: what it was,
what changed, and whether that is an improvement given the metric's own
direction. Where either side was unmeasured it says *not comparable* rather than
computing a difference against a missing number.

### Slack: a limit that has never been approached

An appetite whose utilisation stays under 25% for two consecutive packs is
reported as **slack**. It is not a breach and it is not an error. A limit never
approached is a limit not constraining anything, and a control that has never
fired is indistinguishable from one that *cannot* — which is what a committee
reviewing its own appetite needs to hear and almost never does.

### A pack is kept as it was read

A committee minute refers to "the March pack". A pack recomputed today is a
different document with the same name. So packs are persisted with their
indicator values and a digest, and `GET /api/v1/board-packs/{id}` returns one as
it was read rather than as it would now be recomputed. That is what makes
question three answerable at all.

## Why there is no single number

There is no `model_risk_score`, and there will not be one. Every pack carries
the reason in a `no_composite` field rather than leaving an absence, so a reader
who came looking for the number finds an explanation:

> This pack reports indicators and refuses to average them. A single model-risk
> figure requires the parts to compose, and they do not: two models fed by the
> same curve are not two independent risks, so any one number either
> double-counts the shared dependency or ignores it — and a committee cannot
> decompose it to find out which. The exceptions below are what to act on.

That is `L-14` — lax monoidality — arriving as a product decision rather than a
footnote in a paper. The law itself is one of the six that do not yet run; what
*does* run is a test asserting that no pack ever grows a key called
`model_risk_score`, `composite` or `overall`.

The obstruction is also computable, which is the constructive half of the
refusal. *What do these models rest on in common?* is a different question with
a real answer:

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/shared-dependencies \
  -H 'Content-Type: application/json' \
  -d '{"urns":["maya://model/risk.credit_var","maya://model/markets.swaption"]}'
# → {"shared": [{"urn": "maya://model/markets.curve.usd_ois",
#                "relied_on_by": [...], "count": 2}],
#    "detail": "1 shared dependenc(y/ies). maya://model/markets.curve.usd_ois is
#               relied on by 2 of them, so a fault there is not 2 independent
#               faults — which is the reason an aggregate risk assignment cannot
#               simply add up"}
```

Supervisors ask about common dependencies and shared assumptions in prose. This
is that question with an answer, and it needs `model:read` rather than a
reporting permission, because it is a fact about the register rather than about
the pack.

## Asking your own questions

The **Query the register** screen and `POST /query` let you ask anything the
register knows, without waiting for somebody to build a report.

There is no box that takes SQL, and there is no parameter for one.

> A tool pointed at the database has to decide for itself what *in force* means.
> `status = 'approved'` is the obvious answer and it is wrong — a model can be
> approved and carry a blocking finding. So a second definition of the most
> important word in the register comes into existence, lives in a dashboard
> nobody governs, and is the one on the slide. **Handing out SQL is not a
> semantic layer; it is a database credential with a nicer name.**

You query **entities and fields**, not tables and columns. Fields marked
*derived* — `in_force`, `overdue`, `stalled`, `expired` — are computed by the
same code the screens use, so your query and the model page cannot disagree.

Scope filters **rows**, not access: a reader restricted to one legal entity gets
a shorter table rather than a refusal, and the answer says how many rows were
removed. Read that number. A total that is silently short gets reconciled
against somebody else's, and the difference is blamed on a bug rather than on a
permission.

### Saved views carry the query, never the rows

Save a query, share it, and what you have shared is the **question**. Anyone who
opens it re-runs it under their own scope, so two people can legitimately see
different numbers from one view.

That is not a limitation, it is the point. Had the rows been stored, sharing a
view would carry your scope to the reader — an author who can see four legal
entities would hand three of them to somebody entitled to one, and nobody in
that exchange would have realised they were making a disclosure decision.

A view is run once when you save it, so a broken one is refused while you are
still there to fix it.

### Exports

CSV, Parquet and JSON. **Every export is recorded in the evidence chain**, because
*who took a copy of the model inventory, and when* is a question asked after
something has gone wrong, and by then the answer has to already exist.

`.xlsx` is refused, and the refusal says why rather than the format simply being
missing: a binary workbook cannot be diffed, carries formatting and formulas that
are not in the register, and invites the edit-then-circulate cycle that turns an
extract into a second source of truth nobody versions. CSV opens in Excel.

## Supervisory returns

`GET /regulatory-returns` lists what MAYA can extract — AI Act high-risk
registration, a supervisory model inventory, a third-party model return — and,
before you run any of them, **which of their fields the register cannot answer**.

> **An extract is not a filing.** MAYA produces the fields it holds. It does not
> submit anything, it does not sign anything, and it does not fill in a box it
> cannot answer.

That last part is the whole design. Every inventory return has fields a register
genuinely does not know — the authorised representative, the notified body, the
identifier of an EU declaration of conformity. A tool that puts a plausible value
in those boxes has produced the most dangerous artefact this platform can make,
because unlike everything else here **it goes to a supervisor**. So they come back
empty, named, counted, and the header says the extract is incomplete. Filing it
anyway is a decision somebody takes with their eyes open.

Two kinds of gap, and only one of them is your work:

| | What it means |
|---|---|
| `not_held` | MAYA has no field for this. A limit of the platform |
| `empty_in_this_extract` | MAYA could hold it and every row is blank. A gap in your data |

The population is **derived, and the exclusions are listed**. Which models fall
under Annex III comes from the designations and purpose classes already on the
register, not from a checkbox somebody ticked at onboarding — because the
checkbox is the field that is wrong. Models left out are shown with the reason
they were left out: a regulator's first question about a population of eleven is
what happened to the twelfth.

None of this is a legal opinion. Where the reading of Annex III is arguable, the
extract names the fact it turned on, so your counsel can disagree with a specific
derivation rather than with a number.

## Who may do what

| | |
|---|---|
| `policy:publish` | declaring or retiring a limit — the same permission as putting a policy gate in force, because both fix what the estate is measured by |
| `report:read` | reading a pack or previewing one |
| `report:cut` | recording one. This is the pack a minute refers to |

`report:read` is a read permission and reaches the second line, internal audit
and administrators — it is deliberately **not** in the first line's set. A model
owner reads their own model; the estate telling itself how it is doing is the
second line's document.

Nothing here is separately scoped: a board pack is about the estate, and an
estate-level number filtered to somebody's own legal entity would be a different
number with the same name. Scope the *limit* instead, which is what the `scope`
field is for.
