---
title: Risk appetite and the board pack
slug: portfolio-reporting
section: Oversight
order: 135
icon: clipboard-data
summary: "Holding the estate to limits somebody actually set: appetite as a computable threshold rather than a sentence in a document, indicators derived from the register, what is outside the limits, what moved since the last meeting — and why there is deliberately no single number."
audience: Model risk managers, Committees, Auditors
---

# Risk appetite and the board pack

A committee asks three questions, in this order:

1. **Are we inside the limits we set?**
2. **What is outside them?**
3. **What moved since we last met?**

A report that answers only the first is a dashboard, and a dashboard is why
nobody reads the pack.

## Appetite, as something a machine can check

In most banks an appetite statement is a sentence in a document. That is not a
control: nobody can compute against a sentence, so the number in the quarterly
pack is prepared by hand, and whether it is inside the limit is somebody's
judgement rather than an evaluation.

Here a limit is a **declared threshold over a metric the platform derives**, so
utilisation is arithmetic and a breach is a fact.

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/risk-appetite \
  -H 'Content-Type: application/json' \
  -d '{"metric":"blocking_findings","limit":5,"amber":3,
       "owner":"person/s.iqbal",
       "rationale":"tolerance while the remediation programme runs; reviewed at
                    the March committee"}'
```

### Four refusals, and why each exists

**A metric the platform cannot compute is refused when the limit is written** —
not when the report is run. A limit that failed at the moment a committee was
reading it would fail at the worst possible time, and its author is long gone by
then. Ask what may be held to a limit:

```bash
curl -u s.iqbal:pw localhost:5006/api/v1/risk-appetite/metrics
```

**A limit with no rationale is refused.** A number nobody can explain is a number
nobody will ever change, so it is either ignored or obeyed without thought, and
both are worse than not having it. The rationale travels into every pack, so a
reader who was not in the room can tell what the limit is *for*.

**An amber threshold on the far side of the limit is refused.** A warning that
can only fire after the thing it warns about has happened is not a warning.

**Direction belongs to the metric, not to its author.** Whether more is worse is
a property of *open blocking findings*, not an opinion somebody expresses while
setting a limit — and letting an author declare it would let one declare it
wrongly, producing a limit that reports green while the estate deteriorates.

### Versions accumulate, and a relaxation is named

Nothing is edited. A limit that can be changed without a record is a limit that
can be **relaxed** without one, and the relaxation is exactly the event a reader
six months later comes looking for — so the evidence node for a new version
carries `relaxed: true` when it made the limit easier to satisfy.

A committee raising a limit because the estate grew is doing something
reasonable. A committee raising it because the estate breached it is doing
something else, and only the record tells the two apart.

```bash
curl -u s.iqbal:pw localhost:5006/api/v1/risk-appetite/history/blocking_findings
```

Limits may be **scoped** to a tier, a domain or a legal entity. The most specific
declared limit wins, and a scoped limit does not supersede the estate-wide one —
the same left-to-right precedence featuresets and warrant profiles use.

## The pack

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/board-packs/preview -d '{}'
```

`preview` computes without recording; `POST /board-packs` records. Somebody
preparing for a meeting should be able to see what the pack will say before the
committee is minuted against what they find.

Each indicator comes back with its value, its limit, its **standing** (`within`,
`amber`, `breach`, or `no_appetite`), its utilisation, what it did since the last
pack, and why a committee cares about it at all.

### An unmeasured indicator is never reported as clean

A metric this instance cannot compute — because the service that answers it is
not wired — comes back as `null` with a reason, and the pack says so in its
headline. **Zero is a measurement; an absent service is not**, and reporting one
as the other is how a committee is told an estate is healthy when it is
unobserved.

### Slack: a limit that has never been approached

An appetite whose utilisation stays under 25% pack after pack is reported as
**slack**. It is not a breach and it is not an error. A limit never approached is
a limit not constraining anything, and a control that has never fired is
indistinguishable from one that *cannot* — which is what a committee reviewing
its own appetite needs to hear and almost never does.

### A pack is kept as it was read

A committee minute refers to "the March pack". A pack recomputed today is a
different document with the same name, so packs are persisted with their
indicator values and their digest, and `movement` compares against the last one
cut over the same scope.

## Why there is no single number

There is no `model_risk_score`, and there will not be one.

Aggregating model risk into one figure requires that the parts compose, and they
do not: two models fed by the same curve are not two independent risks. Any
single number either **double-counts the shared dependency or ignores it**, and a
committee cannot decompose it to find out which — so a number that looks
authoritative is one nobody can act on.

The pack says this in itself rather than leaving an absence, so a reader who came
looking for the number finds the reason. What to act on is the exception list.

If you want to know what two models rest on in common, that is a different
question with a real answer:

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/shared-dependencies \
  -H 'Content-Type: application/json' \
  -d '{"urns":["maya://model/risk.credit_var","maya://model/markets.swaption"]}'
```

## Who may do what

| | |
|---|---|
| `report:read` | reading a pack — a `:read`, so every role holds it. A pack is what the estate is told about itself |
| `report:cut` | recording one. Held by the model risk manager, beside publishing a policy gate: both fix what the estate is measured by |
| `policy:publish` | declaring or retiring a limit |
