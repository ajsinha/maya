---
title: Findings
slug: findings
section: Assurance
order: 130
icon: exclamation-triangle
summary: Why the findings register is a control rather than a log — severity, blocking, the closure rule, and the two gates that refuse.
audience: Model risk, Model owners
---

# Findings

Every model risk framework requires findings to be tracked. Most systems track
them in a table that nothing reads.

The difference here is one column: **`blocking`**.

## An open blocking finding refuses two things

**Alias promotion.**

```
alias move refused: 1 blocking finding(s) open against
maya://model/credit.pd.smallbiz (Label leakage in the training set);
close them or downgrade them before promoting a version
```

**Warrant resolution.** HTTP 423, error code `blocked`:

```json
{
  "error": "blocked",
  "detail": "1 blocking finding(s) open against maya://model/credit.pd.smallbiz (...)",
  "remediation": "close the blocking findings, or withdraw the model from service"
}
```

A model that failed challenge cannot reach production by any route that does not
pass through this register. That is what makes it a control.

## Severity and default blocking

| Severity | Remediation window | Blocks by default |
|---|---|---|
| Critical | 30 days | **yes** |
| High | 90 days | no |
| Medium | 180 days | no |
| Low | 365 days | no |
| Observation | 365 days | no |

Blocking can be forced on any finding (`"blocking": true`). Only Critical blocks
without anyone deciding — and the default is what happens when nobody decides,
which is the case worth designing for.

Due dates are **derived from severity** rather than negotiated per finding, so a
Critical finding is not a diary entry.

```bash
POST /api/v1/findings
{
  "urn": "maya://model/credit.pd.smallbiz",
  "severity": "Critical",
  "title": "Label leakage in the training set",
  "owner": "person/j.okafor",
  "description": "The 90-day-arrears flag is computed after the label date.",
  "category": "data_quality",
  "source": "validation"
}
```

An owner is required. *A finding with no owner is a finding nobody will fix* — and
that is the refusal message.

## Closure needs someone else

```bash
POST /api/v1/findings/{id}/close
{"verified_by": "person/a.mehta", "evidence": {"pr": "1420", "rerun": "val-3391"}}
```

Two rules:

- **The owner may not verify their own closure.** The person who owns the
  remediation is the person with the strongest reason to declare it done, and a
  blocking finding is the only thing standing between a failed model and
  production.
- **Closure evidence is required.** An empty closure is refused.

There is also no back door: `set_status` will move a finding to
`in_remediation` or `resolved`, but attempting to set it to `closed` is refused
with *use close() — closure needs a verifier and evidence*.

## Sources

`validation`, `monitoring`, `audit`, `regulator`, `self_identified`. The source
matters for reporting: a regulator-raised finding and a self-identified one carry
very different weight in a supervisory conversation, and aggregating them
together loses exactly the distinction that matters.

## Reading the register

```bash
GET /api/v1/findings?urn=maya://model/credit.pd.smallbiz
```

Returns the open list, the blocking subset, and a summary — open count, blocking
count, overdue count, worst severity, and a breakdown by severity. That summary
is what the model page shows, and what an inventory row needs.
