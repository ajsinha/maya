# MAYA — a 4-hour soak run

> **What this is.** A live MAYA server, driven through its HTTP API and its screens, with the platform's own invariants asserted between every batch of work. The unit suite answers *does each part behave*. This answers *does the platform still tell the truth after hours of use* — and those come apart in ways only time reveals.

> **How to read it.** Every assertion made during the run is counted below and every failed one is reproduced in full, with what was expected and what came back. Nothing is summarised away. A soak report whose headline is *all good* is a report nobody can check.

## The result

| | |
|---|---|
| **Verdict** | **PASSED** |
| Duration | 4h 00m 02s |
| Cycles completed | 26 |
| Assertions made | 3,097 of a 3,000 budget |
| Passed | 3,097 |
| Failed | 0 |
| HTTP calls | 134,936 |
| Background requests between cycles | 115,648 |
| Responses that were 500s | 0 |
| Commit under test | `aaa2180` |
| Table format | `delta` |
| Delta backend | `deltalake` |
| Python | 3.12.3 |

Every assertion held, across 4h 00m 02s and a database that grew throughout. The invariants matter more than the scenarios here: a scenario passing says a path works, and an invariant still holding at the end says the platform is still the thing it claims to be.

## Failures

None. Every one of the 3,097 assertions held.

## What was tested, and why

### screens — 858 assertions, all passed

Every screen a signed-in person can reach, still rendering. A screen nobody can click to is not built — and one that fails after hours of use is worse than one that was never there.

| Assertion | Times checked | Failed |
|---|---:|---:|
| screen /about | 26 |  |
| screen /admin | 26 |  |
| screen /admin/api-keys | 26 |  |
| screen /admin/evidence | 26 |  |
| screen /admin/logs | 26 |  |
| screen /admin/principals | 26 |  |
| screen /admin/regimes | 26 |  |
| screen /admin/runtimes | 26 |  |
| screen /admin/scheduler | 26 |  |
| screen /board-pack | 26 |  |
| screen /dashboard | 26 |  |
| screen /dependencies | 26 |  |
| screen /docs | 26 |  |
| screen /features | 26 |  |
| screen /features/load | 26 |  |
| screen /features/new | 26 |  |
| screen /features/point-in-time | 26 |  |
| screen /featuresets | 26 |  |
| screen /featuresets/author | 26 |  |
| screen /featuresets/lattice | 26 |  |
| screen /findings | 26 |  |
| screen /health | 26 |  |
| screen /help | 26 |  |
| screen /limitations | 26 |  |
| screen /model-algebra | 26 |  |
| screen /models/new | 26 |  |
| screen /notifications | 26 |  |
| screen /packages | 26 |  |
| screen /policies | 26 |  |
| screen /telemetry | 26 |  |
| screen /tutorials | 26 |  |
| screen /warrants | 26 |  |
| screen /warrants/estate | 26 |  |

### invariant — 467 assertions, all passed

What must be true at every instant, whatever has happened. These are the reason a soak is worth hours rather than six minutes: a chain verifies easily after ten appends, and the question is whether it still verifies after thousands from concurrent writers.

| Assertion | Times checked | Failed |
|---|---:|---:|
| median latency has not collapsed | 25 |  |
| no credential appears in the log window | 26 |  |
| no request has produced a 500 | 26 |  |
| no table has drifted from the declaration | 26 |  |
| no two evidence nodes share a sequence number | 26 |  |
| open file handles are bounded | 26 |  |
| resident memory is bounded | 26 |  |
| the backend has not changed mid-run | 26 |  |
| the evidence chain still verifies | 26 |  |
| the evidence sequence has no gaps | 26 |  |
| the evidence sequence never goes backwards | 26 |  |
| the log ring never exceeds its capacity | 26 |  |
| the model register never loses a row | 26 |  |
| the running server reports what holds its feature data | 26 |  |
| the server process is still running | 26 |  |
| the table format has not changed mid-run | 26 |  |
| the thread count is bounded | 26 |  |
| the warrant epoch never goes backwards | 26 |  |

### lifecycle — 364 assertions, all passed

A model from registration to a signed, executable warrant: register, tier, version, quorum, submit the record, approve it, attest it with two roles, promote to prod, issue a standing warrant, resolve a descriptor. Repeated every cycle against a database that is filling up, because a control that works on an empty register and not a full one fails in production and nowhere else.

| Assertion | Times checked | Failed |
|---|---:|---:|
| a developer creates a version | 26 |  |
| issue a standing warrant | 26 |  |
| model_owner attests the record | 26 |  |
| model_risk_manager attests the record | 26 |  |
| model_risk_manager signs the quorum | 26 |  |
| open a quorum on the version | 26 |  |
| promote it to prod champion | 26 |  |
| register a model | 26 |  |
| resolve a signed descriptor | 26 |  |
| submit the model RECORD to the register | 26 |  |
| the creator may NOT approve their own version | 26 |  |
| the risk manager approves the record | 26 |  |
| tier it from its exposure and purpose | 26 |  |
| validator signs the quorum | 26 |  |

### surfaces — 364 assertions, all passed

The read endpoints a script actually calls. Cheap, and worth repeating: they are the most likely to be broken by something else changing, and a 500 in any of them is the one outcome this platform has no story for.

| Assertion | Times checked | Failed |
|---|---:|---:|
| GET /engine | 26 |  |
| GET /features | 26 |  |
| GET /featuresets | 26 |  |
| GET /grammar | 26 |  |
| GET /logs?limit=5 | 26 |  |
| GET /me | 26 |  |
| GET /models | 26 |  |
| GET /policies | 26 |  |
| GET /principals | 26 |  |
| GET /references?kind=feature&id=soak_dscr_00001 | 26 |  |
| GET /roles | 26 |  |
| GET /scheduler | 26 |  |
| GET /version-approval-quorum | 26 |  |
| GET /warrants | 26 |  |

### refusals — 286 assertions, all passed

The controls, tried directly. A refusal nobody attempts is a claim rather than a control, and every one of these has a specific way it could silently start permitting: a use that was never approved, a principal with no entitlement, an environment nothing was promoted to, a duplicate semver, an auditor writing, a developer promoting, one person holding both halves of a separated duty, a password under the floor.

| Assertion | Times checked | Failed |
|---|---:|---:|
| a developer may not promote into an environment | 26 |  |
| a password below the floor is refused AT CREATION | 26 |  |
| a principal with no entitlement is refused | 26 |  |
| a urn cannot be registered twice | 26 |  |
| a use that was never approved is refused | 26 |  |
| a wrong password is refused | 26 |  |
| an anonymous caller is refused | 26 |  |
| an auditor may read everything and write nothing | 26 |  |
| an environment it was never promoted to is refused | 26 |  |
| incompatible roles cannot be held by one person | 26 |  |
| the same semver cannot be created twice | 26 |  |

### sources — 286 assertions, all passed

A feature view filled by PULLING from a file rather than by upload: declared with a column mapping, previewed, pulled, and pulled again. The interesting property is not that one pull works — it is that the hundredth still produces a NEW immutable version rather than amending the last, on a Delta store that has been growing all afternoon. The refusals are driven too, because a source that may only read is a claim until somebody tries to make it write.

| Assertion | Times checked | Failed |
|---|---:|---:|
| a pull produces a version | 26 |  |
| a second pull is a NEW version, not an update | 26 |  |
| a second source on one view is refused | 26 |  |
| a statement that writes is refused | 26 |  |
| and says the bytes were unchanged | 26 |  |
| create the view it fills | 26 |  |
| declare a file source with a column mapping | 26 |  |
| define a feature to be filled from a source | 26 |  |
| no credential is stored, only its name | 26 |  |
| preview reads it and reports it usable | 26 |  |
| the format is inferred from the suffix | 26 |  |

### features — 182 assertions, all passed

A scalar, a twelve-element array and a 3×3 matrix, defined and read back resolved. Shapes are here because they were once accepted at definition and unusable afterwards — a definition the platform took and could not honour.

| Assertion | Times checked | Failed |
|---|---:|---:|
| define a 3x3 matrix | 26 |  |
| define a scalar | 26 |  |
| define an array of twelve | 26 |  |
| read a 3x3 matrix back | 26 |  |
| read a scalar back | 26 |  |
| read an array of twelve back | 26 |  |
| the catalogue lists what was defined | 26 |  |

### details — 182 assertions, all passed

The pages that answer *what is this thing*, asked about a feature and a model this cycle actually created. Here because two of them were unreachable and nothing noticed: a detail page that renders only when somebody types its URL is a page no test and no person ever opens.

| Assertion | Times checked | Failed |
|---|---:|---:|
| a matrix feature's page shows its declared shape | 26 |  |
| and offers the specification editor | 26 |  |
| and shows the seal and lifetime the register holds | 26 |  |
| and the catalogue links to it | 26 |  |
| the LaTeX specification editor opens | 26 |  |
| the feature detail page renders | 26 |  |
| the model page renders | 26 |  |

### apikeys — 36 assertions, all passed

A key that works, a key that has been revoked, and the difference stated in the refusal rather than left to be inferred from a generic 401.

| Assertion | Times checked | Failed |
|---|---:|---:|
| a revoked key is refused, and says which | 9 |  |
| issue a key | 9 |  |
| revoke it | 9 |  |
| the key authenticates | 9 |  |

### concurrency — 26 assertions, all passed

Four writers at the evidence chain at the same instant. The engine takes an advisory lock so the sequence stays dense and unique; one caller can never show the lock is really taken, and the sequence invariant below is what makes this phase mean something.

| Assertion | Times checked | Failed |
|---|---:|---:|
| 4 simultaneous writers all succeed | 26 |  |

### evidence — 26 assertions, all passed

The chain, read as an auditor would read it.

| Assertion | Times checked | Failed |
|---|---:|---:|
| an auditor may read the chain | 26 |  |

### batch — 12 assertions, all passed

The governance batch, run on demand. It is idempotent by design, so running it every fifth cycle tests that claim rather than costing anything.

| Assertion | Times checked | Failed |
|---|---:|---:|
| and reports its own health | 6 |  |
| the batch runs on demand | 6 |  |

### bootstrap — 7 assertions, all passed

The six personas and one service principal the run acts as. Duties are separated here because they are separated in the platform — no single account can walk the whole path, and a soak that ran as `admin` throughout would exercise none of the segregation this system's argument rests on.

| Assertion | Times checked | Failed |
|---|---:|---:|
| create soak.audit | 1 |  |
| create soak.dev | 1 |  |
| create soak.mrm | 1 |  |
| create soak.ops | 1 |  |
| create soak.owner | 1 |  |
| create soak.val | 1 |  |
| create the service principal | 1 |  |

### startup — 1 assertions, all passed

The server came up and answered. Everything below assumes it.

| Assertion | Times checked | Failed |
|---|---:|---:|
| the server accepts connections | 1 |  |

## Resources over the run

A soak that does not measure these is a functional test that took a long time. A leak is invisible to a unit suite by construction — the process exits before it matters. The **shape** is the finding: growth that tracks work done and then flattens is a cache; growth that tracks time is a leak, and the two are indistinguishable for the first hour.

**Verdict: a cache, not a leak.**

| | |
|---|---:|
| Growth per cycle, first half | 4.25 MB |
| Growth per cycle, second half | 0.93 MB |
| Spread across the last four steady samples | 2.4 MB |
| Added while shutting down and publishing | 6.3 MB |
| Total, start to end | 63 MB |

The first half grew at 4.25 MB a cycle and the second at 0.93 — the rate fell by 78%, and the last four samples sit within 2.4 MB of each other. That is a cache warming and settling: page cache, the bounded log ring filling to its capacity, the connection pool reaching its size. A leak does not slow down, because nothing about it is finite.

| Metric | At the start | At the end | Peak | Trace |
|---|---:|---:|---:|---|
| Resident memory | 245.4MB | 314.9MB | 314.9MB | `▁▁▂▃▄▄▄▄▅▅▅▅▆▆▆▆▆▆▆▆▇▇▇▇▇█` |
| Open file handles | 34.0 | 34.0 | 34.0 | `▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁` |
| Threads | 99.0 | 106.0 | 106.0 | `▁▂▄▆▇▇▇▇▇▇▇▇▇█▇▇██▇▇▇▇█▇██` |
| Database size | 0.0MB | 1.4MB | 1.4MB | `▁▄▄▄▅▅▅▅▅▅▅▆▆▆▆▆▆▆▆▆▇▇▇▇▇█` |

### Latency

Each cycle of work took a median of **1.4s** (fastest 0.6s, slowest 3.8s) across 26 cycles.

`▃▁▁▁▁▁▁▁▁▁▂▁▂▂▂▃▃▃▃▃▆▃▅▄▄█`

A cycle does the same work every time. A trace that climbs is the platform getting slower as its register fills, which is a finding even when nothing fails.

## Cycle log

One line per cycle: the work done, the assertions made, and how long the runner then rested to spread the budget across the full duration.

| Cycle | Finished at | Took | Assertions so far | Failures | Rested |
|---:|---|---:|---:|---:|---:|
| 1 | 0h 00m 03s | 1.7s | 130 | 0 | 650s |
| 2 | 0h 10m 54s | 0.6s | 247 | 0 | 616s |
| 3 | 0h 21m 10s | 0.7s | 364 | 0 | 604s |
| 4 | 0h 31m 15s | 0.7s | 485 | 0 | 603s |
| 5 | 0h 41m 19s | 0.7s | 602 | 0 | 598s |
| 6 | 0h 51m 18s | 1.0s | 721 | 0 | 596s |
| 7 | 1h 01m 14s | 0.8s | 842 | 0 | 597s |
| 8 | 1h 11m 12s | 0.9s | 959 | 0 | 594s |
| 9 | 1h 21m 07s | 0.9s | 1,076 | 0 | 592s |
| 10 | 1h 31m 00s | 1.0s | 1,197 | 0 | 593s |
| 11 | 1h 40m 54s | 1.5s | 1,316 | 0 | 592s |
| 12 | 1h 50m 46s | 1.0s | 1,433 | 0 | 590s |
| 13 | 2h 00m 37s | 1.1s | 1,554 | 0 | 591s |
| 14 | 2h 10m 30s | 1.2s | 1,671 | 0 | 589s |
| 15 | 2h 20m 20s | 1.2s | 1,788 | 0 | 587s |
| 16 | 2h 30m 09s | 1.9s | 1,911 | 0 | 589s |
| 17 | 2h 40m 00s | 1.6s | 2,028 | 0 | 588s |
| 18 | 2h 49m 49s | 1.6s | 2,145 | 0 | 585s |
| 19 | 2h 59m 36s | 1.6s | 2,266 | 0 | 587s |
| 20 | 3h 09m 25s | 1.6s | 2,383 | 0 | 585s |
| 21 | 3h 19m 13s | 3.0s | 2,502 | 0 | 583s |
| 22 | 3h 28m 57s | 1.9s | 2,623 | 0 | 587s |
| 23 | 3h 38m 47s | 2.5s | 2,740 | 0 | 581s |
| 24 | 3h 48m 30s | 2.0s | 2,857 | 0 | 573s |
| 25 | 3h 58m 06s | 2.4s | 2,978 | 0 | 113s |
| 26 | 4h 00m 02s | 3.8s | 3,097 | 0 | 0s |

## What a passing run does and does not prove

**It proves** that the governed path works end to end, repeatedly, against a register that grows the whole time; that the controls refuse when they should, on the thousandth attempt as on the first; that the evidence chain stays verifiable and its sequence dense and unique under concurrent writers; that the schema does not drift at runtime; that no request produced an unmapped failure; and that memory, file handles and threads stay bounded over hours.

**It does not prove** anything about PostgreSQL — this run is SQLite, which is the shipped default and not what a bank deploys. It says nothing about **iceberg** either: the table format is a configuration choice and this run made the other one, so four hours of evidence exists for `delta` alone. It does not prove behaviour under real concurrency at scale: four simultaneous writers is enough to make an advisory lock matter and is not a load test. It does not exercise a restart mid-transaction, a disk filling up, or a clock moving. And it cannot prove the absence of a control nobody thought to try — every refusal asserted here is one somebody chose to attempt.

---

*Rendered from `3,204` journal records by `tools/soak/report.py`. The journal is committed beside this file, so every number here can be recomputed.*
