# MAYA — pre-release QA log

**Pass 1: 2026-09-12.** 314 cases, enumerated before they were run, executed
against a live instance, every result recorded whether it passed or not.

This log is written to be *compared*, not re-read. Case IDs are stable and are
never renumbered; every result carries the commit it was taken at; the result
column is per pass. A second pass fills the `Pass 2` column and the delta is
the whole point.

---

## Contents

| # | Section |
|---|---|
| 1 | [The environment](#1-the-environment) |
| 2 | [Summary](#2-summary) |
| 3 | [Defects found and fixed](#3-defects-found-and-fixed) |
| 4 | [Defects found and NOT fixed](#4-defects-found-and-not-fixed) |
| 5 | [The refusals this platform promises, and whether they fired](#5-the-refusals-this-platform-promises-and-whether-they-fired) |
| 6 | [Every case](#6-every-case) |
| 7 | [What could not be tested, and why](#7-what-could-not-be-tested-and-why) |
| 8 | [Expected to change in pass 2](#8-expected-to-change-in-pass-2) |
| 9 | [Every code change, and the case that prompted it](#9-every-code-change-and-the-case-that-prompted-it) |
| 10 | [What I recommend reverting](#10-what-i-recommend-reverting) |

> **Status: this pass was stopped part-way through remediation.** The baseline
> it ran against, `9baa0c5`, still carries open adversarial-review findings
> (H-2, H-9, §4.9, H-3, C-4 dispositions 3–4, C-6, M-4, M-7's tombstone), and a
> tester cannot tell an open finding from a defect worth filing. The remediation
> below was already made when that was established; it is recorded in full in
> §9, with a revert recommendation in §10, and **no change was made after the
> stop**. The case list is the durable part: the IDs are stable, so the real
> pass against a clean baseline compares directly against the Pass 1 column.

---

## 1. The environment

| | |
|---|---|
| **Commit at the start of the pass** | `9baa0c5` — *WCAG 2.2 AA measured where markup can be* |
| **Commit label for post-remediation results** | `wt-679bbf5b` — `9baa0c5` plus this pass's uncommitted working tree |
| **Date** | 2026-09-12 |
| **Host / port** | `127.0.0.1`, ports 5399 and 5401–5406 (never the default 5006) |
| **Configuration** | a copy of `config/application.yaml` in a temp directory, `data.dir` pointed at it. **The repository's own `data/` was never touched.** |
| **Database** | SQLite, 91 tables, 16 integrity triggers applied at start-up |
| **Feature store** | Delta (`deltalake`), the shipped default |
| **Estate** | `docs/QA/qa_setup.py`, plus `r.hale` (auditor) and `o.perez` (operator), which the cheatsheet does not create |

### Reproducing this

Everything below is re-runnable. The cases are shipped as
**[`qa_cases.py`](qa_cases.py)** so a later pass is a comparison rather than a
rewrite:

```bash
# 1. a throwaway instance — never the repository's own data/
mkdir -p /tmp/qa/data
sed -e 's#  dir: ./data#  dir: /tmp/qa/data#' -e 's/PORT:5006/PORT:5399/' \
    -e 's/host: "0.0.0.0"/host: "127.0.0.1"/' \
    config/application.yaml > /tmp/qa/application.yaml
.venv/bin/python run_maya_web.py --config /tmp/qa/application.yaml

# 2. the estate, and the two accounts the cases need beyond it
.venv/bin/python docs/QA/qa_setup.py --url http://127.0.0.1:5399
curl -su admin:maya-admin-dev -X POST http://127.0.0.1:5399/api/v1/principals \
  -H 'content-type: application/json' \
  -d '{"username":"r.hale","display_name":"R Hale","roles":["auditor"],"password":"aud-password-long"}'
curl -su admin:maya-admin-dev -X POST http://127.0.0.1:5399/api/v1/principals \
  -H 'content-type: application/json' \
  -d '{"username":"o.perez","display_name":"O Perez","roles":["operator"],"password":"ops-password-long"}'

# 3. the cases
.venv/bin/python docs/QA/qa_cases.py --url http://127.0.0.1:5399 --enumerate
.venv/bin/python docs/QA/qa_cases.py --url http://127.0.0.1:5399 --run --out /tmp/qa/results.jsonl
```

**Run them once, in ID order, against a freshly built estate.** They walk one
estate forward through its lifecycle — register, tier, approve, attest, amend,
decommission, delete — so a case that runs twice against the same database is
answering a different question the second time. Several of the pass-1 anomalies
in this log are exactly that, and are marked where they occur.

### How to read a case

Every case states, **before it runs**, which of these it expects:

| | |
|---|---|
| `accepted` | the act is permitted and the register records it |
| `refused:code` | the platform says no, with the code named here in advance |
| `reported` | no refusal, but the answer carries a caveat somebody must read |
| `EXPLORATORY` | the expectation could not be stated in advance; what was learned is recorded |

**A refusal is usually the feature working.** A `409` or a `423` from this
platform is nearly always a control operating as designed, and a case that
treats one as a failure has misunderstood the product. What is worth reporting
is the opposite: a success that does not correspond to anything, a promised
refusal that does not happen, or a screen that offers a control and then
refuses it.

---

## 2. Summary

### By outcome

| | Pass 1 @ `9baa0c5` | Re-run @ `wt-679bbf5b` | Pass 2 |
|---|---|---|---|
| **PASS** | 241 | 289 | |
| **FAIL** | 55 | 7 | |
| **EXPLORATORY** | 14 | 18 | |
| **BLOCKED** | 0 | 0 | |
| **Total** | 310 *(QA-090 and QA-091 did not execute in pass 1 — see §7)* | 314 | |

Of the 55 pass-1 FAILs, **22 were product defects** and **33 were cases whose
own call or expectation was wrong**. Both are recorded; a mis-stated
expectation is a QA defect and is logged as one rather than quietly edited
away. Every corrected case says in `qa_cases.py` what it used to assert and why
that was wrong.

### By area

| Area | Cases | P1 PASS | P1 FAIL | P1 EXPL | Re-run PASS | Re-run FAIL | Re-run EXPL |
|---|---|---|---|---|---|---|---|
| auth | 15 | 14 | 1 | 0 | 15 | 0 | 0 |
| rbac | 20 | 20 | 0 | 0 | 20 | 0 | 0 |
| apikeys | 13 | 11 | 1 | 1 | 11 | 1 | 1 |
| models | 16 | 12 | 4 | 0 | 15 | 0 | 1 |
| versions | 5 | 1 | 3 | 1 | 2 | 2 | 1 |
| lifecycle | 10 | 7 | 3 | 0 | 7 | 0 | 3 |
| attestation | 6 | 4 | 2 | 0 | 6 | 0 | 0 |
| quorum | 19 | 15 | 2 | 0 | 18 | 0 | 1 |
| aliases | 6 | 5 | 0 | 1 | 4 | 0 | 2 |
| features | 9 | 5 | 4 | 0 | 6 | 3 | 0 |
| featuresets | 11 | 11 | 0 | 0 | 11 | 0 | 0 |
| warrants | 13 | 9 | 4 | 0 | 13 | 0 | 0 |
| parameters | 5 | 4 | 1 | 0 | 5 | 0 | 0 |
| execution | 4 | 4 | 0 | 0 | 4 | 0 | 0 |
| validation | 5 | 3 | 0 | 2 | 3 | 0 | 2 |
| findings | 10 | 2 | 6 | 2 | 7 | 1 | 2 |
| monitoring | 10 | 5 | 4 | 1 | 10 | 0 | 0 |
| docsearch | 7 | 7 | 0 | 0 | 7 | 0 | 0 |
| decommission | 12 | 11 | 0 | 1 | 11 | 0 | 1 |
| authority | 22 | 19 | 1 | 2 | 20 | 0 | 2 |
| recert | 19 | 7 | 12 | 0 | 19 | 0 | 0 |
| holds | 13 | 10 | 3 | 0 | 13 | 0 | 0 |
| portfolio | 10 | 9 | 0 | 1 | 9 | 0 | 1 |
| screens | 54 | 46 | 4 | 2 | 53 | 0 | 1 |
| **total** | **314** | **241** | **55** | **14** | **289** | **7** | **18** |

Areas outside the API — the CLI, `tools/ops` backup and restore, and the
SQLite immutability triggers — were exercised by hand rather than through
`qa_cases.py`; they are recorded as **QA-B1 … QA-B12** in §6.

### The five gates, after remediation

| Gate | Result |
|---|---|
| `pytest -q -p no:randomly` | **6133 passed, 16 skipped** (6094 before; 39 new regression tests) |
| `ruff check .` | All checks passed |
| `tools/ci/typecheck.py` | Success: no issues found in 333 source files |
| `tools/ci/spec_lock.py` | matches, 533 paths (`--update` run: one route added) |
| `tools/ci/scan_secrets.py` | no secrets found in 1007 tracked files |
| `tools/ci/render_schema.py` | re-run after the schema change; both `.sql` files regenerated |

---

## 3. Defects found and fixed

Twelve. Each one names the case that found it, what was expected, what
actually came back verbatim, the diagnosis, the change and the regression test
that fails without it.

---

### D-1 · The access recertification reviewer cannot answer their own campaign

**Severity: high.** A control built, wired, documented and unreachable.

| | |
|---|---|
| **Cases** | QA-205, QA-207, QA-208, QA-209, QA-210, QA-211, QA-214, QA-216 |
| **Ran** | `POST /api/v1/recertification` as `admin`, naming `s.iqbal` as reviewer; then `POST /api/v1/recertification/REC-QA-1/j.okafor` as `s.iqbal` |
| **Expected** | `accepted` — the named reviewer answers a row |
| **Actual** | `403` |

```json
{"error":"forbidden",
 "detail":"'principal:manage' is not granted by your roles (model_risk_manager)",
 "remediation":"ask an administrator for a role that carries this permission"}
```

And as the only account that *does* hold `principal:manage`:

```json
{"error":"not_the_reviewer",
 "detail":"REC-QA-1 names s.iqbal as its reviewer, not admin",
 "remediation":"a campaign that anybody may answer is a campaign whose `reviewer`
   column is decoration. Hand it over deliberately with `reassign`, which
   records who passed it on and why"}
```

**Diagnosis.** The route required `principal:manage`, which only `admin`
carries, and `Recertification.answer()` refuses anybody who is not the
campaign's named reviewer. The two checks exclude each other. A campaign whose
reviewer sits anywhere but the administrator's chair **could not be answered by
anyone at all** — the reviewer is refused the route, and the person who can
reach the route is refused by the campaign. Setting `reviewer: "admin"` is the
only workable configuration, and `self_recertification` then refuses admin's own
row, which `population: []` (the default, meaning everybody active) always
includes.

`not_the_reviewer` was added precisely so the `reviewer` column would stop being
decoration. Making it load-bearing without giving the reviewer the standing to
act turned the whole workflow off. Every existing HTTP test in
`tests/test_recertification.py` opened its campaigns with `reviewer: "root"` —
the administrator — which is why it looked as though it worked.

**Fixed** in `routes/principal_routes.py`: the reviewer is authorised **by being
named**. An administrator chose them when the campaign was opened, and that act
needs `principal:manage` and still does. Anybody who is *not* the named reviewer
still needs `principal:manage` before `answer()` gives them the same refusal, so
nothing was weakened — `not_the_reviewer`, `self_recertification` and
`campaign_closed` remain the controls, and all three still fire.

**Regression** — `tests/test_recertification.py::TestTheReviewerCanActuallyAnswer`,
four tests: a second-line reviewer answers; the reviewer is still refused their
own row; an administrator who is not the reviewer is still refused; somebody
with no standing at all is refused.

---

### D-2 · `/recertification/{ref}/reassign` and `/close` were unreachable

**Severity: high.** Two endpoints that could never be called.

| | |
|---|---|
| **Cases** | QA-212, QA-213, QA-215, QA-216 |
| **Ran** | `POST /api/v1/recertification/REC-QA-1/close` |
| **Expected** | `accepted` |
| **Actual** | `422` |

```json
{"detail":[{"type":"missing","loc":["body","state"],"msg":"Field required","input":{}}]}
```

**Diagnosis.** Starlette matches routes in declaration order, and
`POST /recertification/{reference}/{principal}` was declared **before** the two
literal routes. So `/REC-QA-1/close` bound `principal="close"`, fell into the
answer handler and asked for a `state` field. `/reassign` did the same. Nothing
failed loudly: the campaign simply stayed open forever, and a reviewer could
never be handed over — which is the escape hatch D-1's control depends on.

**Fixed** in `routes/principal_routes.py`: `/reassign` and `/close` are declared
before `/{principal}`, with a comment saying why the order is the control. No
path changed, so `spec_lock` is unaffected.

**Regression** — `tests/test_recertification.py::TestReassignAndCloseAreReachable`,
four tests, including that a reassigned reviewer can then answer and that a
closed campaign refuses `campaign_closed`.

---

### D-3 · A monitor's observations answered 500, and ignored the legal-entity scope

**Severity: high** (the scope half). Both bugs in the same five lines.

| | |
|---|---|
| **Cases** | QA-247 (the 500), QA-B9 (the scope) |
| **Ran** | `GET /api/v1/monitors/no-such-monitor/observations` |
| **Expected** | `reported` — or a coded refusal |
| **Actual** | `500 Internal Server Error`, empty body |

```
Internal Server Error
```

Server-side: `MonitorError: no monitor no-such-monitor`, unhandled, at
`routes/monitoring_routes.py:269 → core/monitoring/definitions.py:141`.

Then, with a principal scoped to `LE-UK-99` and the model in `LE-US-01`:

```
GET /api/v1/models/qa.pd.scorecard        -> 403 out_of_scope
GET /api/v1/monitors?urn=…                -> 403 out_of_scope
GET /api/v1/monitors/<id>/observations    -> 200  {"monitor":{…},"observations":[…],"breaches":[…]}
```

**Diagnosis.** Two things every sibling route on a monitor already did, and this
one did neither. `monitors.require(...)` was called **outside** `self.guard`, so
a coded refusal escaped as an unhandled exception — no code, no detail, no
remediation, on the one path a reader reaches by pasting an identifier. And
`self.authorise(request, "monitor:read")` was called **without `model=`**, so
the legal-entity scope was never applied: a principal refused the model itself
and refused the monitor list for it could read that model's monitor definition,
every observation on it and every breach, through the one route that forgot to
say which model it was about. `docs/11 §7` records that "scope in Python remains
the control" — so this is a hole in the control, not a known-open topology item.

**Fixed** in `routes/monitoring_routes.py`: `require` inside `guard`, and
`model=self.model_behind(monitor)` on the authorise call.

**Regression** — `tests/test_api_operations.py::TestReadingAMonitorsObservations`,
three tests: an unresolvable id is a 404 `no_monitor` and not a 500; a real
monitor answers; a principal scoped to another entity is refused 403.

---

### D-4 · The register accepted any string as a model URN

**Severity: medium-high.** A row nothing can act on, and a dead link on the
first screen.

| | |
|---|---|
| **Cases** | QA-053, QA-314 |
| **Ran** | `POST /api/v1/models` with `{"urn": "not-a-urn", …}` |
| **Expected** | `refused` |
| **Actual** | `201 Created` |

```json
{"urn":"not-a-urn","name":"bad urn","status":"draft","tier":null,…}
```

and then, for every act on it:

```json
{"error":"not_found","detail":"no model not-a-urn"}
```

**Diagnosis.** `POST /models` took the `urn` field verbatim. Every route that
acts on a model addresses it by path and resolves through `urn_of`, which
prefixes `maya://model/` — so the row was registered, was listed by
`GET /models`, **was rendered as a link on the dashboard**, and answered 404 to
everything: it could not be tiered, versioned, approved, retired,
decommissioned, held or deleted. Confirmed at the interface: the dashboard's
model list carried `/model/not-a-urn` for every role, and that link 404s.

`maya://model/x@1.0.0` was accepted too, which is worse in kind: it registers a
second model whose identifier is a *pinned reference to the first one*, and
warrant resolution parses that suffix.

**Fixed** in `routes/model_routes.py`: `_refuse_unaddressable_urn`, called at
registration. Deliberately at the route rather than in `ModelCatalogue.register`
— the catalogue is called in-process with identifiers that came from somewhere
already trusted, and the failure being closed here is a caller typing one in.

```json
{"error":"validation_failed",
 "detail":"'not-a-urn' is not a model urn, and a register row whose identifier
   no route can address is one nothing can be done to afterwards",
 "remediation":"register it as maya://model/<name>"}
```

**Regression** — `tests/test_api.py::TestAModelUrnMustBeAddressable`, six tests.

---

### D-5 · `maya worklist` called a route that does not exist

| | |
|---|---|
| **Cases** | QA-B10 |
| **Ran** | `python -m maya_sdk.cli worklist` |
| **Expected** | `accepted` — the CLI ships this command and documents it as *what is waiting on you* |
| **Actual** | exit 1 |

```
REFUSED (404) http_404
  Not Found
  [request 5f76c7dd81d35a67]
```

**Diagnosis.** `WorkList.mine` has been computed in-process by the HTML
dashboard since the first milestone and had no endpoint. `cli.py:121` calls
`GET /api/v1/worklist`; `openapi.lock.json` had no such path. A person with the
CLI and no browser had no way to ask.

**Fixed** in `routes/lifecycle_routes.py`: `GET /api/v1/worklist`, authenticated
and self-scoped by construction — `mine` filters by permission, role and
legal-entity scope, so it answers for the caller and cannot be asked about
somebody else. `openapi.lock.json` regenerated with `spec_lock.py --update`
(533 paths, one added).

**Regression** — `tests/test_api.py::TestTheWorklistHasAnEndpoint`, three tests.

---

### D-6 · The dashboard showed every model to a principal with no `model:read`

**Severity: medium.** This one is in `core/authz/policy.py`, so it needs saying
plainly: **the change makes the control stricter, not weaker.** The case failed
because the platform was too permissive, and the fix adds a check that was
missing. Nothing that was refused before is permitted now.

| | |
|---|---|
| **Cases** | QA-313 |
| **Ran** | signed in as `q.tester` (`feature_curator`: four permissions, none of them `model:read`), read the dashboard, then opened every link it offers |
| **Expected** | `reported` — no navbar link a role is offered should refuse it |
| **Actual** | `500` from the case's own assertion |

```
q.tester is offered /model/qa.decom and gets 403;
q.tester is offered /model/qa.ews.tier1 and gets 403;
q.tester is offered /model/qa.pd.scorecard and gets 403;
q.tester is offered /model/qa.untiered and gets 403
```

**Diagnosis.** `AuthorizationPolicy.visible()` filtered by legal-entity and
domain **scope alone**, and left the permission to whoever called it. Nineteen
callers check `model:read` first. The dashboard does not — it requires only a
session — and it is the first screen after sign-in. So a principal holding no
`model:read` at all was shown every model in the estate, each rendered as a link
to a page that then answered 403. That is exactly the thing
`docs/QA/README.md` asks a tester to report: *a screen that offers a control and
then refuses it.*

**Fixed** in `core/authz/policy.py`: `visible()` returns `[]` when the principal
does not hold `model:read`, then applies the scope as before. Both halves belong
there — `visible` answers *which models may this person see*, and a list
filtered by entity but not by permission is an answer to a narrower question
that reads the same.

**Regression** — `tests/test_authz.py::TestWhatIsVisibleIsFilteredByPermissionAndNotOnlyByScope`,
three tests, including that the scope still applies on top of the permission.

---

### D-7 · A feature view did not know what it declared, so the null-column type fallback never ran

**Severity: medium.** The sixth control this session found built, wired,
documented and never executed.

**This is the schema change.** One column added: `feature_view.features`, `Text`,
`NOT NULL`, `server_default '[]'`.

| | |
|---|---|
| **Cases** | QA-B11 |
| **Ran** | created a view declaring `dscr` and `ltv`, then read back the view row and `ViewManager._dtypes(view)` |
| **Expected** | `reported` — the declared dtypes, used to type a column that arrives empty |
| **Actual** | the view row has no such key, and `_dtypes` returns `{}` on every call |

```
view row keys: ['created_at','delta_table','description','entity','id','name','owner']
features key present: False
```

**Diagnosis.** A view's declared feature list went into the evidence node the
creation appended, and onto each *version* once one existed — but never onto the
view row, because `feature_view` had no column for it.
`ViewManager._dtypes(view)` iterates `view.get("features")`, which was always
absent, so it returned an empty map unconditionally. That map is the whole of
the answer to a column that arrives entirely null — a feature with nothing in
this window, or a restatement that withdraws a figure. Its own docstring says
Arrow cannot infer a type from all-nulls, that Delta then stored a null-typed
column and **Iceberg refused the write**, and that "MAYA knows the answer and
simply was not passing it". It still was not. The table format is a
configuration choice, so on an Iceberg deployment this is a failed write rather
than a quiet degradation.

**Fixed** across four files:

| File | Change |
|---|---|
| `db/schema/features.py` | `FEATURE_VIEW` gains `Column("features", Text, nullable=False, server_default=text("'[]'"))` |
| `db/schema/sqlite.sql`, `db/schema/postgres.sql` | regenerated by `tools/ci/render_schema.py` — never hand-edited |
| `db/repositories.py` | `FeatureViewRepository` decodes `features` as JSON, like every other document column |
| `core/features/views.py` | `create()` stores the declared list on the row |

An existing database picks the column up with
`python run_maya_web.py --repair-schema`, which is the additive-nullable case
that tool exists for.

**Regression** — `tests/test_features.py::TestAViewKnowsWhatItDeclares`, three
tests: the row carries its declaration; `_dtypes` is non-empty; and a wholly
null column is stored with a real type rather than as an object column.

---

### D-8 · Two refusals told an operator to run a command that has never existed

| | |
|---|---|
| **Cases** | QA-B7 |
| **Ran** | `python -m tools.ops.verify --help` |
| **Expected** | `accepted` — both `tools/ops/backup.py` and `tools/ops/restore.py` name it in their PostgreSQL refusals |
| **Actual** | |

```
/home/…/.venv/bin/python: No module named tools.ops.verify
```

**Diagnosis.** The remediation is the third of the three parts a MAYA refusal
carries, and one naming a phantom is worse than none: it costs the reader the
time to find out, and it reads as though somebody checked. The only reader who
reaches either line is an operator on PostgreSQL, at the moment they are trying
to take or restore a backup.

**Fixed** in `tools/ops/backup.py` and `tools/ops/restore.py`: both remediations
now name `GET /api/v1/evidence/chain`, which exists, returns the chain head, and
is what the manifest is checked against. The history is a code comment rather
than something a user reads.

**Regression** — `tests/test_backup_restore.py::TestEveryRemediationNamesSomethingThatExists`
sweeps every `python -m <module>` named anywhere under `tools/` and refuses one
that will not import.

---

### D-9 … D-12 · The QA pack itself

The pack is handed to testers outside the organisation. It had four defects,
and all four were invisible to anybody who had ever run it against a database
that already had the estate in it. **`docs/QA/qa_setup.py` did not complete on
an empty instance.**

#### D-9 · The setup script asked for the tier before the version existed

| | |
|---|---|
| **Cases** | QA-B1 |
| **Ran** | `python docs/QA/qa_setup.py` against an empty instance |
| **Expected** | `accepted` — the script's own docstring promises idempotence and completion |
| **Actual** | `SystemExit(2)` at step 5 |

```
  REFUSED  its risk tier
     this assessment lands on a different tier depending on trainability_class,
     and the request did not say
     register a version first — the class is derived from the kernel, and with
     no version this model's complexity is being read at its most favourable
```

The refusal is **right** — it is the control that stops a model being tiered at
its most favourable reading. The script had the order backwards, so no version
and no kernel were ever created and the cheatsheet described a model that did
not exist.

**Fixed** in `docs/QA/qa_setup.py` and `docs/QA/qa-setup.sh`: the version is
created first.

#### D-10 · The accounts the cheatsheet signs in as were never created

| | |
|---|---|
| **Cases** | QA-B2 |
| **Ran** | `GET /api/v1/principals` after `qa_setup.py` |
| **Expected** | the five accounts the cheatsheet's *Sign-in accounts* table publishes |
| **Actual** | `admin`, `q.tester`, `svc/qa-runner` — and nothing else |

`s.iqbal`, `j.okafor` and `a.mehta` are named in the cheatsheet's own table and
used from section 8 onwards. They did not exist, so **every command in sections
8 to 11 answered 401** for a tester following the document in order: the
approval workflow, attestation, alias promotion — the whole of what this estate
exists to demonstrate, including every segregation-of-duties refusal it is
built to show.

**Fixed** in `qa_setup.py`, `qa-setup.sh` and the README's account table, which
now also lists `a.mehta` and `d.raman`.

#### D-11 · The pack's kernel made its own section 9 impossible

| | |
|---|---|
| **Cases** | QA-133, QA-134 |
| **Ran** | `POST /api/v1/fit-warrants` with the featureset the cheatsheet's section 6 builds |
| **Expected** | `accepted` |
| **Actual** | `409` |

```json
{"error":"schema_not_satisfied",
 "detail":"'qa_pd_training' does not provide intercept, beta_dscr, beta_ltv,
   which this version declares it reads",
 "remediation":"bind a featureset whose schema covers the kernel's inputs, or
   create a model version whose input schema matches this set — adding a
   regressor is a model change, not a data change"}
```

**Diagnosis.** The kernel in `qa_setup.py` declared `intercept`, `beta_dscr` and
`beta_ltv` in `input_schema`. L-W10 asks whether the featureset supplies
everything `input_schema` names, so it demanded a training set carrying the
coefficients — columns no training set has, because they are what the training
produces. **No fit warrant could ever be issued for this estate.**

The cheatsheet's section 4 warns against exactly this mistake, in bold, and the
script it ships with makes it. Every case study in the repository uses the
correct shape (`parameter_schema` for the coefficients); only the QA pack did
not.

**Fixed** in `qa_setup.py`, `qa-setup.sh` and both README kernel blocks: the
coefficients move to `parameter_schema`. Verified end to end on a clean estate —
the fit warrant now issues.

#### D-12 · The setup script was not idempotent about the tier

| | |
|---|---|
| **Cases** | QA-B3 |
| **Ran** | `python docs/QA/qa_setup.py` twice |
| **Expected** | `accepted` — "run it twice and it says what already exists" |
| **Actual** | `SystemExit(2)` on the second run |

```
  REFUSED  its risk tier
     these are the same facts as the last assessment, so re-running the formula
     moves the review date without anything having been reviewed
     say what was examined and why the tier is unchanged, or send the facts that
     have moved
```

**Diagnosis.** Uncovered by fixing D-9 — the script never got this far before.
The refusal is right, and it is a control worth keeping: a periodic review
discharged by re-POSTing last year's numbers is the failure it exists to stop.

**Fixed** in `docs/QA/qa_setup.py`: `tier_once()` asks whether the model is
already tiered and does nothing if it is, the same shape as the existing
`load_once()`. **It does not route around the refusal with a canned
`review_note`** — a setup script asserting that a review happened is the failure
the refusal exists to stop, and the regression test asserts the string
`review_note` does not appear in the helper.

**Regression for D-9 to D-12** —
`tests/test_qa_pack.py::TestTheSetupScriptBuildsTheEstateTheCheatsheetDescribes`,
ten tests: the version precedes the tier in both scripts; each of the six
accounts is created by both scripts and listed in the README; the coefficients
are parameters and not inputs in the Python, the shell and the cheatsheet; and
re-running does not re-assess.

*A note on the SDK, found while fixing D-12 and not fixed:* `maya.models.assess`
has no `review_note` parameter, so an annual re-tiering with unchanged facts
cannot be expressed through the SDK at all — only through `maya.call`. The
script's own docstring says "if a call here is awkward, that is the SDK's
problem to fix rather than the script's to route around". Recorded as **N-11**.

---

### The changed files, in full

| File | Defect | What changed |
|---|---|---|
| `routes/principal_routes.py` | D-1, D-2 | route order; the reviewer is authorised by being named |
| `routes/monitoring_routes.py` | D-3 | `require` inside `guard`; `model=` on the authorise call |
| `routes/model_routes.py` | D-4 | `_refuse_unaddressable_urn` at registration |
| `routes/lifecycle_routes.py` | D-5 | `GET /api/v1/worklist` |
| `openapi.lock.json` | D-5 | `spec_lock.py --update`, one path added |
| `core/authz/policy.py` | D-6 | `visible()` checks `model:read` — **stricter, not weaker** |
| `db/schema/features.py` | D-7 | `feature_view.features` column added |
| `db/schema/sqlite.sql`, `db/schema/postgres.sql` | D-7 | regenerated by `render_schema.py` |
| `db/repositories.py` | D-7 | `FeatureViewRepository` decodes `features` |
| `core/features/views.py` | D-7 | `create()` stores the declaration on the row |
| `tools/ops/backup.py`, `tools/ops/restore.py` | D-8 | the remediation names something that exists |
| `docs/QA/qa_setup.py`, `docs/QA/qa-setup.sh` | D-9…D-12 | order, people, kernel, idempotence |
| `docs/QA/README.md` | D-10, D-11 | the account table and both kernel blocks |
| `docs/QA/qa_cases.py` | — | new: the 314 cases, re-runnable |
| `pyproject.toml` | — | `S310` allowed under `docs/QA/`, for the same reason `tools/soak/` has it |
| `tests/…` (7 files) | all | 39 regression tests |

---

## 4. Defects found and NOT fixed

Every one of these is a real finding, reproduced, with a diagnosis. None was
fixed, and the reason is given in each case — mostly that the fix is a design
decision with a blast radius a QA pass should not take unilaterally.

### N-1 · A principal whose username contains `/` cannot be suspended

**Severity: high. This is the one on this list most worth acting on.**

| | |
|---|---|
| **Cases** | QA-044, QA-B4 |
| **Ran** | `POST /api/v1/principals/svc%2Fqa-runner/suspend`, and with a literal slash |
| **Expected** | `accepted`, then `401 key_principal_not_active` on the key |
| **Actual** | `{"detail":"Not Found"}` from both spellings; the key kept authenticating, `200` |

All four `/api/v1/principals/{username}/…` routes — `suspend`, `reinstate`,
`roles`, `password` — declare `{username}`, which does not match a path
segment containing `/`. `svc/…` is the platform's own convention for service
accounts: `qa_setup.py` creates `svc/qa-runner`, `content/help/02-quickstart.md`
creates `svc/origination`, `content/help/13` signs in as `svc/scheduler`. **None
of them can be suspended, reinstated, re-roled or given a password**, and the
`key_principal_not_active` refusal — which is implemented correctly at
`core/apikeys/register.py:245` and is promised in the cheatsheet's API-key table
— can never be reached for the identities API keys exist for.

*Why not fixed here:* the fix is `{username:path}` on four routes, which changes
four path templates in the OpenAPI lock and needs thinking about the greedy
match (a username ending in `/suspend`). That is a small change but it is an
authorisation surface, and it wants its own review rather than being folded into
a QA pass alongside eleven other edits.

### N-2 · A version can be created with a `semver` that is not one

| | |
|---|---|
| **Cases** | QA-107 |
| **Expected** | `refused` |
| **Actual** | `201`, `{"semver":"one point oh",…}` |

Ordering (`latest_version`), alias pinning (`@one point oh`) and every
comparison in the register take it on faith. *Why not fixed:* deciding whether
MAYA requires strict semver, or merely a comparable ordering, is a product
decision — `case_studies/` uses `1.0.0` throughout but nothing states the rule.

### N-3 · A kernel may name a runtime that does not exist

| | |
|---|---|
| **Cases** | QA-109 |
| **Expected** | `refused` |
| **Actual** | `201`, with `"runtime":"telepathy"`, classified `T2` |

*Why not fixed:* this one is arguably right. A version may legitimately name a
runtime a given deployment does not have installed — an air-gapped register
holding a QuantLib model on a host without QuantLib. The refusal happens at
execution, `no_runtime` 501, which is the honest place for it. Recorded so the
next reader does not have to work that out again.

### N-4 · A feature may be defined with no description

| | |
|---|---|
| **Cases** | QA-113 |
| **Expected** | `refused` — a role is refused without one |
| **Actual** | `201` |

The asymmetry is the finding: `POST /roles` refuses without a description,
saying "a list of permissions is not an explanation of who should hold them",
and `POST /features` does not, though `similar()` uses the description for
duplicate detection. *Why not fixed:* nothing promises this refusal, and it
would break any estate that has ever loaded features from a source without one.

### N-5 · `dtype` is free text

| | |
|---|---|
| **Cases** | QA-114 |
| **Expected** | `refused` |
| **Actual** | `201`, `{"dtype":"vibes"}` |

Three lines above it in `core/features/catalogue.py`, `sensitivity` is closed
against a vocabulary, with a comment that applies word for word here: *"a
lattice over free text is a lattice over nothing, because 'Confidential',
'confidential' and 'CONF' are three classes to a computer and one to a person."*
`dtype` decides how Delta types the column and what a featureset slot must
match. *Why not fixed:* the repository already uses six spellings —
`numeric` (192), `float` (34), `string` (14), `integer` (9), `categorical` (7),
`text` (1) — for what is probably three kinds. Closing the vocabulary means
choosing the canonical set and normalising ~250 call sites and the Delta typing.
That is a design change, not a QA fix.

### N-6 · Materialising a row can silently redefine what a view version carries

| | |
|---|---|
| **Cases** | QA-117 |
| **Ran** | `POST /feature-views/qa_borrower/materialise` with one row whose only column is `not_in_the_view` |
| **Expected** | `refused` |
| **Actual** | `201` |

```json
{"feature_view_id":"…","version":2,"features":["not_in_the_view"],
 "row_count":1,"quarantined":false,…}
```

`qa_borrower` declares `dscr, ltv, monthly_balances, correlation`. Version 2
carries a single column that is not a defined feature at all, and the version's
feature list is inferred from whatever arrived. Downstream this surfaces as a
confusing featureset refusal ("no materialised feature view supplies 'dscr'")
rather than as wrong data. *Why not fixed:* the check became **possible** only
with D-7 — until the view row carried its declaration there was nothing to
compare against — and adding a refusal to the load path in the same pass as the
schema change is two behavioural changes on one hot path. **This is the natural
follow-on to D-7 and is the recommended next fix.**

### N-7 · A model may be registered with an empty `purpose`

QA-052, `201`. Purpose is prose and `purpose_class` is the tiering fact, so
nothing downstream reads it — which is the argument for requiring it, since it
appears on every compiled document. Not promised anywhere; recorded.

### N-8 · An alias may be moved with an empty justification

QA-104, `200`. `docs/QA/README.md` says "Every alias move is recorded with who
moved it and why", and the *why* may be blank. *Why not fixed:* the suite's own
`registered` fixture in `tests/conftest.py` moves an alias with no
justification, which says the platform currently treats it as optional. Making
it mandatory is a deliberate change, not a bug fix.

### N-9 · A version with an empty kernel classifies as `T0`

QA-108, `201`, `trainability_class: "T0"`. `VersionIn.kernel` defaults to `{}`,
and a kernel that declares nothing is read as "no parameters, deterministic" —
the simplest class there is, which feeds `complexity=simple` into the tier.
`core/risk/tiering.py` carries a long comment about the sibling of this bug (a
model with *no version* being read as T0) and refuses that case. The
empty-kernel case is not refused. *Why not fixed:* an artifact-only version may
legitimately have little to declare, and deciding what a kernel must minimally
say is a modelling decision.

### N-10 · A second approval of an approved version answers 200

QA-067, QA-097. `POST /models/{n}/versions/{v}/approve` on an
already-approved version returns the version record rather than
`already_approved`. It appears to be a no-op rather than a second approval, but
the caller cannot tell the difference between "I approved it" and "it was
already approved", and on a tier-1 model the same call is refused
`quorum_required` *before* approval and answers 200 *after* it. Recorded as an
answer that does not correspond to an act.

### N-11 · `maya.models.assess` cannot express `review_note`

Found while fixing D-12. The register refuses a re-assessment with unchanged
facts unless the caller says what was examined; the SDK has no parameter for it,
so the only route is `maya.call`. See the note under D-12.

### N-12 · A not-found is answered `409 feature_refused`

QA-119. `GET /feature-views/qa_borrower/versions/99/data` returns
`409 feature_refused: feature view 'qa_borrower' has no version 99`. Every
comparable absence in the platform answers 404. `feature_refused` is one of the
seven class-mapped codes with no literal raise site, which is how a "not found"
came to wear a "refused" code. Cosmetic, but it is the refusal taxonomy and
`tests/test_refusal_discipline.py` exists to keep that clean.

### N-13 · The `admin` role holds both halves of every separated duty

QA-069. `admin` submitted a model record and then approved it, `200`. This is
deliberate — `conflicts()` returns `[]` for anyone holding `admin`, and
`_refuse_for_holders` skips them, both with comments calling it break-glass —
and `model_owner` holds `model:submit` without `model:approve` while
`model_risk_manager` holds the reverse, so the separation is enforced by role
for every real account. Recorded because the register refuses to *define* a role
holding both halves (QA-018, `409 incompatible_permissions`) while shipping one
that does, and a reader who finds one should find the other. Note that
segregation-of-duties from the evidence chain **does** still bind `admin`:
QA-065 and QA-100 both refused it.

---

## 5. The refusals this platform promises, and whether they fired

The highest-value target in this pass: a promised refusal that does not happen.
Every code below is promised in `content/help/`, `docs/11-adversarial-review.md`
or `docs/QA/README.md`, and every one was provoked deliberately.

| Code | Status | Case | Fired? |
|---|---|---|---|
| `unauthenticated` | 401 | QA-002, QA-007, QA-011, QA-012, QA-013 | yes |
| `forbidden` | 403 | QA-016, QA-024, QA-025, QA-026, QA-030, QA-032, QA-048 | yes |
| `incompatible_permissions` | 409 | QA-018 | yes |
| `incompatible_roles` | 409 | QA-081 | yes |
| `role_in_use` | 409 | QA-019 | yes |
| `self_suspension` | 409 | QA-020 | yes |
| `outside_key_scope` | 403 | QA-039 | yes |
| `scope_exceeds_principal` | 422 | QA-040 | yes |
| `lifetime_refused` | 422 | QA-041 | yes |
| `key_revoked` | 401 | QA-046 | yes |
| `key_principal_not_active` | 401 | QA-044 | **no — unreachable, see N-1** |
| `unknown_purpose_class` | 422 | QA-058 | yes |
| `segregation_of_duties` | 403 | QA-065, QA-100, QA-233 | yes |
| `quorum_required` | 409 | QA-084 | yes |
| `approval_open` | 409 | QA-087 | yes |
| `role_not_held` | 403 | QA-072, QA-088 | yes |
| `role_not_required` | 403 | QA-089 | yes |
| `already_signed` | 409 | QA-074, QA-092 | yes |
| `already_signed_personally` | 409 | QA-091 | yes |
| `approval_closed` | 409 | QA-095 | yes |
| `no_tier` / `not_tiered` | 409 | QA-060, QA-061, QA-099 | yes |
| `unknown_decision` | 409 | QA-098 | yes |
| `registry_refused` (attested is immutable) | 409 | QA-077 | yes |
| `schema_not_satisfied` (L-W10) | 409 | QA-133 | yes |
| `no_approved_parameters` | 409 | QA-132 | yes |
| `self_approval` | 403 | QA-140 (via `forbidden` first) | yes, behind the permission |
| `principal_not_self` | 403 | QA-143 | yes |
| `use_not_approved` / `no_entitlement` | 403 | QA-144, QA-145 | yes |
| `parameter_overridden` | 409 | QA-147 | yes |
| `revoked` | 410 | QA-151 | yes |
| `rationale_required` | 422 | QA-155 | yes |
| `replacement_required` | 422 | QA-156 | yes |
| `replacement_not_registered` | 422 | QA-157 | yes |
| `unknown_retention_class` | 422 | QA-158 | yes |
| `already_decommissioned` | 409 | QA-162 | yes |
| `illegal_transition` | 409 | QA-163 | yes |
| `matter_required` | 422 | QA-166 | yes |
| `unknown_scope` | 422 | QA-167 | yes |
| `under_legal_hold` | **423** | QA-170 | yes |
| `no_hold` | 404 | QA-171 | yes |
| `not_active` (hold lifted twice) | 409 | QA-174 | yes |
| `reason_required` | 422 | QA-172, QA-176, QA-209 | yes |
| `band_name_required` / `stages_required` / `unknown_tier` / `negative_floor` / `band_exists` / `unknown_band` | 422/404/409 | QA-179…QA-185, QA-199 | yes |
| `principal_required` / `instrument_required` / `ceiling_required` | 422 | QA-186, QA-187, QA-188 | yes |
| `out_of_sequence` | 409 | QA-191 | yes |
| `no_delegated_authority` | 409 | QA-B5 | yes |
| `beyond_delegated_authority` | 409 | QA-194 | yes, **only once the exposure is fact-sourced** |
| `reference_required` / `campaign_exists` / `no_such_principal` | 422/409/404 | QA-200, QA-202, QA-204 | yes |
| `not_the_reviewer` | 403 | QA-206 | yes |
| `self_recertification` | 403 | QA-207 | yes, **only after D-1** |
| `unknown_answer` | 422 | QA-208 | yes, **only after D-1** |
| `not_in_population` | 404 | QA-210 | yes, **only after D-1** |
| `campaign_closed` | 409 | QA-216 | yes, **only after D-1 and D-2** |
| `empty_query` | 422 | QA-220 | yes |
| `limit_out_of_range` | 422 | QA-221, QA-222 | yes |
| `unknown_dimension` / `same_dimension` | 422 | QA-253, QA-254 | yes |
| `no_reference` | 422 | QA-248 | yes |
| immutability triggers (14 columns + `evidence_node`) | DB abort | QA-B12 | yes |
| backup: non-empty target, chain does not verify | exit 1 | QA-B6 | yes |
| restore: over a database holding evidence | exit 1 | QA-B8 | yes |

**One promised refusal did not fire: `key_principal_not_active` (N-1).** It is
implemented correctly; the route that would put a principal into the state it
tests cannot be addressed for the usernames it applies to.

**One fired only under a precondition worth stating.**
`beyond_delegated_authority` tests the ceiling against an exposure **attested to
a system of record**, and reports rather than refuses when there is none. In an
estate where nobody has recorded a fact source — which is how the platform ships
— the delegated-authority ceiling never binds. That is deliberate and
documented in the source ("a control that refuses the whole estate the day it is
switched on is a control that gets switched off the same day"), and
`GET /api/v1/authority/estate` reports the unsourced models. It is written down
here because "the ceiling is enforced" and "the ceiling is enforced where
somebody recorded where the number came from" are different claims, and only the
second is true.

---

## 6. Every case

`Pass 1` is the result at `9baa0c5`, before any change in this pass.
`Re-run` is the same case at `wt-679bbf5b` — `9baa0c5` plus this pass's
remediations — against a freshly built estate. `Pass 2` is for the next pass.

A `FAIL` in the Pass 1 column is not always a product defect: 33 of the 55 were
cases whose own call or expectation was wrong, and each of those is marked in
`qa_cases.py` with what it used to assert and why that was wrong. §3 and §4 list
the ones that were real.

| ID | Area | Action | Expectation | Pass 1 @ 9baa0c5 | Pass 1 answer, verbatim | Re-run @ wt-679bbf5b | Pass 2 |
|---|---|---|---|---|---|---|---|
| **QA-001** | auth | GET /me with valid Basic credentials | `accepted` | PASS 200 | `{"username":"admin","roles":["admin"],"permissions":["alias:move","assist:attest","assist:generate","assist:read","assist:register","assumption:read",` | PASS 200 | |
| **QA-002** | auth | GET /me with no credentials at all | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-003** | auth | GET /me with a wrong password | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-004** | auth | GET /me for a username that does not exist | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-005** | auth | GET /health unauthenticated (liveness must not need auth) | `accepted` | PASS 200 | `{"status":"healthy","uptime_seconds":340.0,"version":"0.1.0","storage":{"table_format":"delta","backend":"deltalake","reference_implementation":true,"` | PASS 200 | |
| **QA-006** | auth | GET /health/ready unauthenticated | `accepted` | PASS 200 | `{"status":"ready","evidence_chain":{"valid":true,"length":27,"head":"sha256:6b37c6c91684132750d3edcc8216ceb240a1c51606c1ebdc6658e065e5a1e028","scope":` | PASS 200 | |
| **QA-007** | auth | GET a protected API path unauthenticated (/models) | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-008** | auth | Browser login with correct password (form POST) | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-009** | auth | Browser login with a wrong password | `refused:401` | FAIL 401 | `(an HTML page)` | PASS 401 | |
| **QA-010** | auth | A password shorter than 12 characters is refused at creation | `refused:*` | PASS 422 | `{"error":"password_too_short","detail":"a password is at least 12 characters","remediation":"choose a longer one; this is the credential for a princip` | PASS 422 | |
| **QA-011** | auth | Empty Basic header value | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-012** | auth | Bearer token that is not an API key | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-013** | auth | X-API-Key header with a garbage value | `refused:401` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-014** | auth | Suspended principal cannot authenticate | `refused:401|403` | PASS 401 | `{"error":"unauthenticated","detail":"this endpoint requires an authenticated principal","remediation":"sign in, present HTTP Basic credentials, or sen` | PASS 401 | |
| **QA-015** | auth | Reinstated principal can authenticate again | `accepted` | PASS 200 | `{"username":"o.perez","roles":["operator"],"permissions":["evidence:read","limitation:read","log:read","model:read","monitor:evaluate","monitor:read",` | PASS 200 | |
| **QA-016** | rbac | feature_curator may not register a model | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'model:register' is not granted by your roles (feature_curator)","remediation":"ask an administrator for a role that ca` | PASS 403 | |
| **QA-017** | rbac | A role defined without a description is refused | `refused:*` | PASS 422 | `{"detail":[{"type":"missing","loc":["body","description"],"msg":"Field required","input":{"name":"nodesc","permissions":["model:read"]}}]}` | PASS 422 | |
| **QA-018** | rbac | A role holding both halves of a separated duty | `refused:incompatible_permissions` | PASS 409 | `{"error":"incompatible_permissions","detail":"'solo' would hold both halves of a separated duty: effective challenge means somebody other than the bui` | PASS 409 | |
| **QA-019** | rbac | Deleting a role somebody still holds | `refused:role_in_use` | PASS 409 | `{"error":"role_in_use","detail":"'feature_curator' is held by q.tester, and a role that stops existing while somebody holds it makes their next reques` | PASS 409 | |
| **QA-020** | rbac | Suspending yourself | `refused:self_suspension` | PASS 409 | `{"error":"self_suspension","detail":"you cannot suspend yourself: reinstating needs 'principal:manage', which you would no longer have","remediation":` | PASS 409 | |
| **QA-021** | rbac | A role granting a permission that does not exist | `refused:*` | PASS 422 | `{"error":"unknown_permission","detail":"'model:levitate' is not a recognised permission","remediation":"check the spelling against core.authz.common.P` | PASS 422 | |
| **QA-022** | rbac | Creating a principal with a role that does not exist | `refused:*` | PASS 422 | `{"error":"unknown_role","detail":"'not_a_role' is not a recognised role","remediation":"known roles are admin, auditor, feature_curator, model_develop` | PASS 422 | |
| **QA-023** | rbac | Duplicate username | `refused:*` | PASS 409 | `{"error":"duplicate_principal","detail":"a principal named 's.iqbal' already exists","remediation":"choose another username, or update the existing pr` | PASS 409 | |
| **QA-024** | rbac | An auditor may not register a model | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'model:register' is not granted by your roles (auditor)","remediation":"ask an administrator for a role that carries th` | PASS 403 | |
| **QA-025** | rbac | An operator may not approve a version | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'version:approve' is not granted by your roles (operator)","remediation":"ask an administrator for a role that carries ` | PASS 403 | |
| **QA-026** | rbac | A validator may not manage principals | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (validator)","remediation":"ask an administrator for a role that carrie` | PASS 403 | |
| **QA-027** | rbac | /me reports the caller's effective permissions | `reported` | PASS 200 | `{"username":"q.tester","roles":["feature_curator"],"permissions":["feature:define","feature:materialise","feature:read","featureset:define"],"scope":"` | PASS 200 | |
| **QA-028** | rbac | Changing a principal's roles as admin | `accepted` | PASS 200 | `{"id":"01a0982bf170cdbd2ad1999aec6c","username":"o.perez","display_name":"O Perez","kind":"person","email":null,"roles":["operator","auditor"],"legal_` | PASS 200 | |
| **QA-029** | rbac | Reverting that role change | `accepted` | PASS 200 | `{"id":"01a0982bf170cdbd2ad1999aec6c","username":"o.perez","display_name":"O Perez","kind":"person","email":null,"roles":["operator"],"legal_entities":` | PASS 200 | |
| **QA-030** | rbac | A non-admin may not change their own roles | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (feature_curator)","remediation":"ask an administrator for a role that ` | PASS 403 | |
| **QA-031** | rbac | Setting a password shorter than the minimum | `refused:*` | PASS 422 | `{"error":"password_too_short","detail":"a password is at least 12 characters","remediation":"choose a longer one; this is the credential for a princip` | PASS 422 | |
| **QA-032** | rbac | A model_developer may not move an alias | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'alias:move' is not granted by your roles (model_developer)","remediation":"ask an administrator for a role that carrie` | PASS 403 | |
| **QA-033** | rbac | Suspending another principal, then reinstating | `accepted` | PASS 200 | `{"id":"01a0982bf14c1fdf52d524a628de","username":"r.hale","display_name":"R Hale","kind":"person","email":null,"roles":["auditor"],"legal_entities":[],` | PASS 200 | |
| **QA-034** | rbac | Amending a role's permission list | `accepted` | PASS 200 | `{"id":"01a0982a68742780cfdedf533a4e","name":"feature_curator","description":"defines and loads features, nothing else","permissions":["feature:define"` | PASS 200 | |
| **QA-035** | rbac | Reading the role catalogue as an auditor | `accepted` | PASS 200 | `{"roles":[{"name":"admin","description":"Everything, including principal management. For bootstrap and break-glass.","built_in":true,"permissions":["a` | PASS 200 | |
| **QA-036** | apikeys | Issue a key for the service principal | `accepted` | PASS 201 | `{"id":"01a0982f27bc5b74e937fce43ffd","username":"svc/qa-runner","name":"qa-nightly","prefix":"maya_sk_REsNWO…","scopes":["model:read","warrant:resolve` | PASS 201 | |
| **QA-037** | apikeys | Authenticate with the key via X-API-Key | `accepted` | PASS 200 | `{"username":"svc/qa-runner","roles":["service"],"permissions":["model:read","warrant:resolve"],"scope":"all entities, all domains"}` | PASS 200 | |
| **QA-038** | apikeys | Authenticate with the key as a Bearer token | `accepted` | PASS 200 | `{"models":[{"id":"01a0982a68cd94fe02d84e8ca652","urn":"maya://model/qa.pd.scorecard","name":"QA PD scorecard","description":"","model_class":"credit.p` | PASS 200 | |
| **QA-039** | apikeys | A key narrower than its principal is refused outside its scope | `refused:outside_key_scope` | PASS 403 | `{"error":"outside_key_scope","detail":"the API key 'qa-nightly' does not carry 'evidence:read', though svc/qa-runner does","remediation":"use a key wh` | PASS 403 | |
| **QA-040** | apikeys | A key scope wider than the principal's roles | `refused:scope_exceeds_principal` | PASS 422 | `{"error":"scope_exceeds_principal","detail":"the key would carry principal:manage, which 'svc/qa-runner' does not hold. A credential cannot grant what` | PASS 422 | |
| **QA-041** | apikeys | A key lifetime of 99999 days | `refused:lifetime_refused` | PASS 422 | `{"error":"lifetime_refused","detail":"a key lives between 1 and 365 days, and this asked for 99999. A key with no practical expiry is a credential nob` | PASS 422 | |
| **QA-042** | apikeys | A key for a principal that does not exist | `refused:*` | PASS 404 | `{"error":"no_such_principal","detail":"no principal 'svc/ghost' to issue a key for","remediation":"create the principal first; a key is a way for an i` | PASS 404 | |
| **QA-043** | apikeys | The secret is not returned again by the list endpoint | `reported` | PASS 200 | `{"keys":[{"id":"01a0982f27bc5b74e937fce43ffd","username":"svc/qa-runner","name":"qa-nightly","prefix":"maya_sk_REsNWO…","scopes":["model:read","warran` | PASS 200 | |
| **QA-044** | apikeys | A key whose principal is suspended | `refused:key_principal_not_active|401` | FAIL 200 | `{"username":"svc/qa-runner","roles":["service"],"permissions":["model:read","warrant:resolve"],"scope":"all entities, all domains"}` | FAIL 200 | |
| **QA-045** | apikeys | Revoke the key | `accepted` | PASS 200 | `{"id":"01a0982f27bc5b74e937fce43ffd","username":"svc/qa-runner","name":"qa-nightly","prefix":"maya_sk_REsNWO…","scopes":["model:read","warrant:resolve` | PASS 200 | |
| **QA-046** | apikeys | Using a revoked key names it as revoked, not a generic 401 | `refused:key_revoked` | PASS 401 | `{"error":"key_revoked","detail":"the API key 'qa-nightly' was revoked on 2026-09-13 00:33 UTC: QA finished","remediation":"issue a new key; a revoked ` | PASS 401 | |
| **QA-047** | apikeys | Revoking an already-revoked key | `EXPLORATORY: idempotent or refused` | EXPLORATORY 409 | `{"error":"already_revoked","detail":"'qa-nightly' was revoked by admin already","remediation":""}` | EXPLORATORY 409 | |
| **QA-048** | apikeys | A non-admin issuing a key for somebody else | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (feature_curator)","remediation":"ask an administrator for a role that ` | PASS 403 | |
| **QA-049** | models | Register a second model (tier-1 candidate) | `accepted` | PASS 201 | `{"urn":"maya://model/qa.ews.tier1","name":"QA early warning","description":"","model_class":"credit.pd.scorecard","domain":"credit","owner":"person/j.` | PASS 201 | |
| **QA-050** | models | Register a third model, left untiered on purpose | `accepted` | PASS 201 | `{"urn":"maya://model/qa.untiered","name":"QA untiered","description":"","model_class":"credit.pd.scorecard","domain":"credit","owner":"person/j.okafor` | PASS 201 | |
| **QA-051** | models | Register a model whose urn is already taken | `refused:*` | PASS 409 | `{"error":"registry_refused","detail":"a model is already registered with urn maya://model/qa.pd.scorecard","remediation":"the refusal names the clause` | PASS 409 | |
| **QA-052** | models | Register a model with no purpose | `EXPLORATORY: is a purpose load-bearing?` | FAIL 201 | `{"urn":"maya://model/qa.nopurpose","name":"n","description":"","model_class":"c","domain":"credit","owner":"person/x","legal_entity":"uk","purpose":""` | EXPLORATORY 201 | |
| **QA-053** | models | Register a model with a urn that is not a maya urn | `refused:*` | FAIL 201 | `{"urn":"not-a-urn","name":"bad urn","description":"","model_class":"credit.pd.scorecard","domain":"credit","owner":"person/j.okafor","legal_entity":"L` | PASS 422 | |
| **QA-054** | models | Register a model with an unknown field in the body | `refused:422` | PASS 422 | `{"detail":[{"type":"extra_forbidden","loc":["body","sneaky"],"msg":"Extra inputs are not permitted","input":1}]}` | PASS 422 | |
| **QA-055** | models | GET a model that does not exist | `refused:404` | PASS 404 | `{"error":"not_found","detail":"no model does.not.exist"}` | PASS 404 | |
| **QA-056** | models | Assess a tier before any version exists, where the answer does not turn on it | `accepted` | FAIL 200 | `{"tier":1,"materiality":"critical","complexity":"advanced","required_controls":["independent_validation","annual_review","monthly_monitoring","committ` | PASS 200 | |
| **QA-057** | models | Create version 1.0.0 on the tier-1 candidate | `accepted` | PASS 201 | `{"model_id":"01a09830feea6d7abd6745535a35","semver":"1.0.0","manifest":{"urn":"maya://model/qa.ews.tier1","semver":"1.0.0","kernel":{"runtime":"formul` | PASS 201 | |
| **QA-058** | models | Assess with an unknown purpose class | `refused:unknown_purpose_class` | PASS 422 | `{"error":"unknown_purpose_class","detail":"purpose class 'vibes' is not in the configured vocabulary, so it has no materiality rank","remediation":"de` | PASS 422 | |
| **QA-059** | models | Assess the tier-1 candidate at critical exposure | `accepted` | PASS 200 | `{"tier":1,"materiality":"critical","complexity":"advanced","required_controls":["independent_validation","annual_review","monthly_monitoring","committ` | PASS 200 | |
| **QA-060** | models | Submit an untiered model for approval | `refused:*` | PASS 409 | `{"error":"nothing_to_approve","detail":"this model has no versions; there is nothing to approve","remediation":"create at least one version before sub` | PASS 409 | |
| **QA-061** | models | Approve an untiered model | `refused:*` | PASS 409 | `{"error":"illegal_transition","detail":"cannot 'approve' a model that is 'draft'; from here you may: submit, retire","remediation":"the record is bein` | PASS 409 | |
| **QA-062** | models | Attest a model that was never approved | `refused:*` | PASS 409 | `{"error":"no_attestation_open","detail":"no attestation is open for maya://model/qa.untiered","remediation":"the record must be approved before it can` | PASS 409 | |
| **QA-063** | models | PATCH a model's description as its owner | `accepted` | FAIL 422 | `{"detail":[{"type":"extra_forbidden","loc":["body","description"],"msg":"Extra inputs are not permitted","input":"left untiered deliberately, for QA b` | PASS 200 | |
| **QA-064** | models | Version approval on a model with no version | `refused:*` | PASS 404 | `{"error":"not_found","detail":"no version 9.9.9 for qa.untiered"}` | PASS 404 | |
| **QA-065** | lifecycle | Approve version 1.0.0 as the person who created it | `refused:segregation_of_duties` | PASS 403 | `{"error":"segregation_of_duties","detail":"the person who created a version may not approve it — admin recorded 'version_created' against this subject` | PASS 403 | |
| **QA-066** | lifecycle | Approve version 1.0.0 as the second line (tier 3, one signature) | `accepted` | PASS 200 | `{"id":"01a0982c1fbc954bc5189f39f956","model_id":"01a0982a68cd94fe02d84e8ca652","semver":"1.0.0","manifest":{"urn":"maya://model/qa.pd.scorecard","semv` | PASS 200 | |
| **QA-067** | lifecycle | Approve the same version twice | `EXPLORATORY: idempotent or refused` | FAIL 200 | `{"id":"01a0982c1fbc954bc5189f39f956","model_id":"01a0982a68cd94fe02d84e8ca652","semver":"1.0.0","manifest":{"urn":"maya://model/qa.pd.scorecard","semv` | EXPLORATORY 200 | |
| **QA-068** | lifecycle | Submit the model record | `accepted` | PASS 200 | `{"id":"01a0982a68cd94fe02d84e8ca652","urn":"maya://model/qa.pd.scorecard","name":"QA PD scorecard","description":"","model_class":"credit.pd.scorecard` | PASS 200 | |
| **QA-069** | lifecycle | Approve the model record as the submitter (admin holds both) | `EXPLORATORY: is submit/approve segregated?` | FAIL 200 | `{"id":"01a0982a68cd94fe02d84e8ca652","urn":"maya://model/qa.pd.scorecard","name":"QA PD scorecard","description":"","model_class":"credit.pd.scorecard` | EXPLORATORY 200 | |
| **QA-070** | lifecycle | Approve the model record as the second line | `EXPLORATORY: already approved by QA-069` | FAIL 409 | `{"error":"illegal_transition","detail":"cannot 'approve' a model that is 'approved'; from here you may: attest, retire","remediation":"the record is a` | EXPLORATORY 409 | |
| **QA-071** | attestation | First attestation signature (model_risk_manager) | `reported` | PASS 200 | `{"urn":"maya://model/qa.pd.scorecard","state":"approved","meaning":"approved but not yet attested; not in force until it is","mutable":false,"availabl` | PASS 200 | |
| **QA-072** | attestation | The same person signing under a second role they do not hold | `refused:role_not_held` | FAIL 403 | `{"error":"role_not_held","detail":"s.iqbal does not hold the role 'model_owner'","remediation":"sign for a role you hold; an attestation signed under ` | PASS 403 | |
| **QA-073** | attestation | Signing an attestation without model:attest at all | `refused:forbidden` | FAIL 403 | `{"error":"forbidden","detail":"'model:attest' is not granted by your roles (validator)","remediation":"ask an administrator for a role that carries th` | PASS 403 | |
| **QA-074** | attestation | The same role signing twice | `refused:already_signed` | PASS 409 | `{"error":"already_signed","detail":"the 'model_risk_manager' signature is already recorded","remediation":"each required role signs once"}` | PASS 409 | |
| **QA-075** | attestation | The owner completes the attestation | `accepted` | PASS 200 | `{"urn":"maya://model/qa.pd.scorecard","state":"attested","meaning":"in force and immutable; open an amendment to change it","mutable":false,"available` | PASS 200 | |
| **QA-076** | attestation | The model now reads as attested and immutable | `reported` | PASS 200 | `{"model":{"id":"01a0982a68cd94fe02d84e8ca652","urn":"maya://model/qa.pd.scorecard","name":"QA PD scorecard","description":"","model_class":"credit.pd.` | PASS 200 | |
| **QA-077** | lifecycle | Add a version to an attested model | `refused:*` | PASS 409 | `{"error":"registry_refused","detail":"cannot add a version to maya://model/qa.pd.scorecard: this model is attested and therefore immutable; open an am` | PASS 409 | |
| **QA-078** | lifecycle | Amend the attested model as a model_risk_manager (lacks model:amend) | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'model:amend' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role that ca` | PASS 403 | |
| **QA-079** | lifecycle | Open an amendment as the owner | `accepted` | PASS 200 | `{"id":"01a0982a68cd94fe02d84e8ca652","urn":"maya://model/qa.pd.scorecard","name":"QA PD scorecard","description":"","model_class":"credit.pd.scorecard` | PASS 200 | |
| **QA-080** | lifecycle | Add version 2.0.0 under the amendment | `accepted` | PASS 201 | `{"model_id":"01a0982a68cd94fe02d84e8ca652","semver":"2.0.0","manifest":{"urn":"maya://model/qa.pd.scorecard","semver":"2.0.0","kernel":{"runtime":"for` | PASS 201 | |
| **QA-081** | quorum | Assigning two incompatible roles to one person | `refused:incompatible_roles` | PASS 409 | `{"error":"incompatible_roles","detail":"p.dual would hold incompatible roles: effective challenge is not effective when the builder runs it: a develop` | PASS 409 | |
| **QA-082** | quorum | One person holding model_risk_manager and validator (a supported pair) | `accepted` | PASS 200 | `{"id":"01a098344beb6aa8ff61fb0c508d","username":"p.dual","display_name":"P Dual","kind":"person","email":null,"roles":["model_risk_manager","validator` | PASS 200 | |
| **QA-083** | quorum | The published quorum by tier | `reported` | PASS 200 | `{"quorum":[{"tier":1,"required_roles":["model_risk_manager","validator"],"signatures":2},{"tier":2,"required_roles":["model_risk_manager","validator"]` | PASS 200 | |
| **QA-084** | quorum | Single-signature approval of a tier-1 version | `refused:quorum_required` | PASS 409 | `{"error":"quorum_required","detail":"a tier 1 version is approved by a quorum of model_risk_manager, validator, not by one signature","remediation":"o` | PASS 409 | |
| **QA-085** | quorum | What this version's approval needs | `reported` | PASS 200 | `{"urn":"maya://model/qa.ews.tier1","semver":"1.0.0","tier":1,"quorum_required":true,"required_roles":["model_risk_manager","validator"],"band":null,"s` | PASS 200 | |
| **QA-086** | quorum | Open a quorum on the tier-1 version | `accepted` | PASS 201 | `{"id":"01a098344c0939ff4c3c1c3418e1","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09830fef8c034c70d54cbf0f7","tier":1,"required_ro` | PASS 201 | |
| **QA-087** | quorum | Open a second quorum while one is open | `refused:approval_open` | PASS 409 | `{"error":"approval_open","detail":"an approval is already open for version 1.0.0","remediation":"complete or withdraw it before opening another"}` | PASS 409 | |
| **QA-088** | quorum | Sign for a role the signer does not hold | `refused:role_not_held` | PASS 403 | `{"error":"role_not_held","detail":"s.iqbal does not hold the role 'validator'","remediation":"sign for a role you hold; an approval signed under a bor` | PASS 403 | |
| **QA-089** | quorum | Sign for a role this quorum does not require | `refused:role_not_required` | PASS 403 | `{"error":"role_not_required","detail":"'model_owner' is not one of the roles this approval requires (model_risk_manager, validator)","remediation":"si` | PASS 403 | |
| **QA-090** | quorum | First signature (model_risk_manager) by a dual-hatted person | `reported` | — | `` | PASS 200 | |
| **QA-091** | quorum | The same person signing the second role: a quorum is people, not hats | `refused:already_signed_personally` | — | `` | PASS 409 | |
| **QA-092** | quorum | The same role signed twice by two different people | `refused:already_signed` | FAIL 200 | `{"id":"01a098344c0939ff4c3c1c3418e1","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09830fef8c034c70d54cbf0f7","tier":1,"required_ro` | PASS 409 | |
| **QA-093** | quorum | Quorum progress names who is outstanding | `reported` | PASS 200 | `{"id":"01a098344c0939ff4c3c1c3418e1","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09830fef8c034c70d54cbf0f7","tier":1,"required_ro` | PASS 200 | |
| **QA-094** | quorum | The second person completes the quorum | `accepted` | PASS 200 | `{"id":"01a098344c0939ff4c3c1c3418e1","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09830fef8c034c70d54cbf0f7","tier":1,"required_ro` | PASS 200 | |
| **QA-095** | quorum | Signing a closed approval | `refused:approval_closed` | PASS 409 | `{"error":"approval_closed","detail":"this approval is already 'approved'","remediation":"open a new one if another is needed"}` | PASS 409 | |
| **QA-096** | quorum | Withdrawing a closed approval | `refused:*` | PASS 409 | `{"error":"approval_closed","detail":"this approval is already 'approved'","remediation":""}` | PASS 409 | |
| **QA-097** | quorum | Single-signature approval after the quorum approved it | `EXPLORATORY: idempotent or refused` | FAIL 200 | `{"id":"01a09830fef8c034c70d54cbf0f7","model_id":"01a09830feea6d7abd6745535a35","semver":"1.0.0","manifest":{"urn":"maya://model/qa.ews.tier1","semver"` | EXPLORATORY 200 | |
| **QA-098** | quorum | An unknown decision word on a signature | `refused:unknown_decision|404|409` | PASS 409 | `{"error":"approval_closed","detail":"this approval is already 'approved'","remediation":"open a new one if another is needed"}` | PASS 409 | |
| **QA-099** | quorum | Open a quorum on a model with no tier | `refused:no_tier|not_tiered|no_such_version` | PASS 409 | `{"error":"no_tier","detail":"this model has no risk tier, so how many signatures its version needs is undecided","remediation":"assess the model first` | PASS 404 | |
| **QA-100** | aliases | Promote a version into prod as the person who created it | `refused:segregation_of_duties` | PASS 403 | `{"error":"segregation_of_duties","detail":"the person who created a version may not promote it into an environment — admin recorded 'version_created' ` | PASS 403 | |
| **QA-101** | aliases | Promote as the second line | `accepted` | PASS 200 | `{"model":"maya://model/qa.pd.scorecard","environment":"prod","alias":"champion","version":"1.0.0","refinement":{"holds":true,"reason":"no incumbent"},` | PASS 200 | |
| **QA-102** | aliases | Promote a version that was never approved | `refused:*` | PASS 409 | `{"error":"registry_refused","detail":"version 2.0.0 is 'draft', not approved; an alias may only point at an approved version","remediation":"the refus` | PASS 409 | |
| **QA-103** | aliases | Promote a semver that does not exist | `refused:*` | PASS 409 | `{"error":"registry_refused","detail":"no version 7.7.7 for maya://model/qa.pd.scorecard","remediation":"the refusal names the clause that failed; sati` | PASS 409 | |
| **QA-104** | aliases | Promote with an empty justification | `EXPLORATORY: is a justification required?` | PASS 409 | `{"error":"registry_refused","detail":"version 1.0.0 is 'draft', not approved; an alias may only point at an approved version","remediation":"the refus` | EXPLORATORY 200 | |
| **QA-105** | aliases | Re-promote the same version to the same alias | `EXPLORATORY: idempotent or refused` | EXPLORATORY 200 | `{"model":"maya://model/qa.pd.scorecard","environment":"prod","alias":"champion","version":"1.0.0","refinement":{"holds":true,"reason":"refines"},"vari` | EXPLORATORY 200 | |
| **QA-106** | versions | Duplicate semver on the same model | `refused:*` | PASS 409 | `{"error":"registry_refused","detail":"version 1.0.0 already exists for maya://model/qa.ews.tier1; versions are immutable","remediation":"the refusal n` | PASS 409 | |
| **QA-107** | versions | A semver that is not a semver | `refused:*` | FAIL 201 | `{"model_id":"01a09830feea6d7abd6745535a35","semver":"one point oh","manifest":{"urn":"maya://model/qa.ews.tier1","semver":"one point oh","kernel":{"ru` | FAIL 201 | |
| **QA-108** | versions | A version with an empty kernel | `EXPLORATORY: is a kernel required?` | EXPLORATORY 201 | `{"model_id":"01a09830feecc38d5f84b69edf10","semver":"1.0.0","manifest":{"urn":"maya://model/qa.untiered","semver":"1.0.0","kernel":{},"contract":{},"a` | EXPLORATORY 201 | |
| **QA-109** | versions | A kernel naming a runtime that does not exist | `refused:*` | FAIL 201 | `{"model_id":"01a09830feecc38d5f84b69edf10","semver":"1.1.0","manifest":{"urn":"maya://model/qa.untiered","semver":"1.1.0","kernel":{"runtime":"telepat` | FAIL 201 | |
| **QA-110** | versions | Version history for one model | `reported` | FAIL 422 | `{"detail":[{"type":"missing","loc":["query","urn"],"msg":"Field required","input":null}]}` | PASS 200 | |
| **QA-111** | features | Define a feature as a curator | `accepted` | PASS 201 | `{"feature":{"id":"01a098363567ef23868c88c835aa","name":"utilisation","entity":"borrower","dtype":"numeric","description":"credit line utilisation","bu` | PASS 201 | |
| **QA-112** | features | Define a feature with a name already taken | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"feature 'dscr' is already defined","remediation":"correct the feature definition or the view version and retry"}` | PASS 409 | |
| **QA-113** | features | Define a feature with no description | `refused:*` | FAIL 201 | `{"feature":{"id":"01a09836356be5c681a8f6f3f80c","name":"nodesc_feature","entity":"borrower","dtype":"numeric","description":"","business_definition":"` | FAIL 201 | |
| **QA-114** | features | Define a feature with an unknown dtype | `refused:*` | FAIL 201 | `{"feature":{"id":"01a09836356df8fb5a1450dcdb12","name":"weird","entity":"borrower","dtype":"vibes","description":"an unknown dtype","business_definiti` | FAIL 201 | |
| **QA-115** | features | A curator may not register a model but may load data | `accepted` | PASS 200 | `{"features":[{"id":"01a0982a689ad73f0a68d60351e2","name":"correlation","entity":"borrower","dtype":"numeric","description":"a 3x3 correlation matrix",` | PASS 200 | |
| **QA-116** | features | Materialise rows missing a required clock | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"row is missing 'ingest_ts'; feature rows carry two clocks — event_ts (when it was true) and ingest_ts (when we le` | PASS 409 | |
| **QA-117** | features | Materialise a row for a feature the view does not carry | `refused:*` | FAIL 201 | `{"feature_view_id":"01a0982a689f834ec98fb9a1e413","version":2,"features":["not_in_the_view"],"delta_version":0,"valid_time_column":"event_ts","ingest_` | FAIL 201 | |
| **QA-118** | features | Read a view version's data point-in-time | `reported` | PASS 200 | `{"view":"qa_borrower","version":1,"namespace":"features/borrower/qa_borrower/v1","delta_version":0,"rows":[{"entity_id":"C1","event_ts":100.0,"ingest_` | PASS 200 | |
| **QA-119** | features | Read a view version that does not exist | `refused:feature_refused|404` | FAIL 409 | `{"error":"feature_refused","detail":"feature view 'qa_borrower' has no version 99","remediation":"correct the feature definition or the view version a` | PASS 409 | |
| **QA-120** | featuresets | Define a featureset whose slots match the kernel | `accepted` | PASS 201 | `{"id":"01a098363592cf1aee38664fbe56","name":"qa_pd_training","entity":"borrower","owner":"admin","description":"slot names match the kernel input name` | PASS 201 | |
| **QA-121** | featuresets | A label slot that is not one of the slots | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"the label slot 'not_a_slot' is not one of the slots this featureset resolves to","remediation":"correct the featu` | PASS 409 | |
| **QA-122** | featuresets | Publish a version leaving a slot unbound | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"these slots are unfilled: defaulted. a version that cannot fill the schema is not a version of this featureset","` | PASS 409 | |
| **QA-123** | featuresets | Bind a slot to a feature nothing has materialised | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"no materialised feature view supplies 'utilisation'; materialise it before a featureset can pin it","remediation"` | PASS 409 | |
| **QA-124** | featuresets | Publish a version pinning every slot | `accepted` | PASS 201 | `{"id":"01a09836359f57a4c88800d31752","featureset_id":"01a098363592cf1aee38664fbe56","version":1,"bindings":{"dscr":{"feature":"dscr","slot":"dscr","dt` | PASS 201 | |
| **QA-125** | featuresets | A featureset composed from another | `accepted` | PASS 201 | `{"id":"01a0983635a1ed5daaba25c57117","name":"qa_pd_extended","entity":"borrower","owner":"admin","description":"everything the training set has, plus ` | PASS 201 | |
| **QA-126** | featuresets | What the composed featureset resolves to | `reported` | PASS 200 | `{"id":"01a0983635a1ed5daaba25c57117","name":"qa_pd_extended","entity":"borrower","owner":"admin","description":"everything the training set has, plus ` | PASS 200 | |
| **QA-127** | featuresets | Compose from a featureset that does not exist | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"cannot compose from 'nope': no such featureset","remediation":"correct the feature definition or the view version` | PASS 409 | |
| **QA-128** | featuresets | A derived feature from an expression | `accepted` | PASS 201 | `{"id":"01a0983635a7fce40eb77b90078b","feature_id":"01a0983635a6d94dbb1c7a3dac67","name":"coverage_ratio","expression":"dscr / ltv","inputs":["dscr","l` | PASS 201 | |
| **QA-129** | featuresets | A derived feature whose expression names an unknown feature | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"undefined inputs: unknown_thing; a derived feature can only read features the catalogue knows about","remediation` | PASS 409 | |
| **QA-130** | featuresets | A derived feature whose expression calls a function nobody allows | `refused:*` | PASS 409 | `{"error":"feature_refused","detail":"'that' is not one of the functions this language provides: abs, ceil, exp, floor, log, max, min, round, sqrt","re` | PASS 409 | |
| **QA-131** | warrants | Grant a standing warrant to the service account | `accepted` | PASS 201 | `{"model_id":"01a0982a68cd94fe02d84e8ca652","environment":"lab","binding_kind":"alias","alias_name":"champion","version_id":null,"flavour":"formula","p` | PASS 201 | |
| **QA-132** | warrants | Resolve before any parameters are approved | `refused:no_approved_parameters` | PASS 409 | `{"error":"no_approved_parameters","detail":"this version's parameter object is 'estimated_coefficients' and nothing inhabits it: no approved parameter` | PASS 409 | |
| **QA-133** | warrants | A fit warrant whose featureset cannot fill the kernel's slots (L-W10) | `refused:schema_not_satisfied` | PASS 409 | `{"error":"schema_not_satisfied","detail":"'qa_pd_inputs' does not provide dscr, ltv, intercept, beta_dscr, beta_ltv, which this version declares it re` | PASS 409 | |
| **QA-134** | warrants | A fit warrant whose featureset does fill them | `accepted` | FAIL 409 | `{"error":"schema_not_satisfied","detail":"'qa_pd_training' does not provide intercept, beta_dscr, beta_ltv, which this version declares it reads","rem` | PASS 201 | |
| **QA-135** | warrants | Assemble a point-in-time training set | `accepted` | PASS 201 | `{"name":"qa_pd_train_v1","kind":"training","delta_table":"snapshots/qa_pd_train_v1","delta_version":0,"row_count":2,"as_of":1000.0,"pit_verified":true` | PASS 201 | |
| **QA-136** | warrants | The training set carries the RESTATED value, not the first-known one | `reported` | PASS 200 | `{"featureset":"qa_pd_training","version":1,"returned":2,"rows":[{"defaulted_12m":0,"entity_id":"C2","event_ts":500.0,"ingest_ts":505.0,"dscr":2.1,"ltv` | PASS 200 | |
| **QA-137** | parameters | Record parameters with no warrant id | `refused:*` | PASS 422 | `{"error":"warrant_required","detail":"a fitted parameter set must name the warrant it was produced under; without it, which data produced these number` | PASS 422 | |
| **QA-138** | parameters | Record parameters against a warrant id that does not exist | `refused:unknown_warrant|*` | PASS 404 | `{"error":"unknown_warrant","detail":"MAYA did not issue warrant not-a-warrant","remediation":"parameters are accepted only against a warrant from this` | PASS 404 | |
| **QA-139** | parameters | Record parameters against the grant | `accepted` | PASS 201 | `{"id":"01a09836360d110d9db0dcb86b9f","model_id":"01a0982a68cd94fe02d84e8ca652","model_version_id":"01a0982c1fbc954bc5189f39f956","name":"qa-fit-2026Q1` | PASS 201 | |
| **QA-140** | parameters | The owner who recorded a set has no parameter:approve | `refused:forbidden` | FAIL 403 | `{"error":"forbidden","detail":"'parameter:approve' is not granted by your roles (model_owner)","remediation":"ask an administrator for a role that car` | PASS 403 | |
| **QA-141** | parameters | Somebody else approves it | `accepted` | PASS 200 | `{"id":"01a09836360d110d9db0dcb86b9f","model_id":"01a0982a68cd94fe02d84e8ca652","model_version_id":"01a0982c1fbc954bc5189f39f956","name":"qa-fit-2026Q1` | PASS 200 | |
| **QA-142** | warrants | Resolve now that parameters are approved | `accepted` | PASS 200 | `{"maya_warrant":"1.0","warrant_id":"01a098363614ec031542c1bddbd7","issued_at":1789260084.7564542,"subject":{"urn":"maya://model/qa.pd.scorecard@1.0.0"` | PASS 200 | |
| **QA-143** | warrants | Resolve in somebody else's name, without warrant:issue | `refused:principal_not_self` | FAIL 403 | `{"error":"forbidden","detail":"'warrant:resolve' is not granted by your roles (feature_curator)","remediation":"ask an administrator for a role that c` | PASS 403 | |
| **QA-144** | warrants | Resolve for a use the grant does not cover | `refused:use_not_approved|no_entitlement` | PASS 403 | `{"error":"use_not_approved","detail":"declared use 'origination_decision' is not the approved use 'model_development'","remediation":"seek approval fo` | PASS 403 | |
| **QA-145** | warrants | Resolve in an environment the grant does not cover | `refused:no_entitlement|restricted` | PASS 403 | `{"error":"no_entitlement","detail":"svc/qa-runner holds no warrant for maya://model/qa.pd.scorecard in prod","remediation":"request a warrant grant fo` | PASS 403 | |
| **QA-146** | execution | Execute inside MAYA at the approved point | `accepted` | PASS 200 | `{"descriptor_id":"01a09836361b883507a182612539","model_urn":"maya://model/qa.pd.scorecard","version":"1.0.0","prediction":{"family":"formula","target"` | PASS 200 | |
| **QA-147** | execution | A caller supplying one of the coefficients | `refused:parameter_overridden` | PASS 409 | `{"error":"parameter_overridden","detail":"the inputs supply beta_dscr, which this version's approved parameter set also supplies","remediation":"a cal` | PASS 409 | |
| **QA-148** | execution | Execute with a required feature missing | `refused:*` | PASS 422 | `{"error":"missing_inputs","detail":"the expression reads ltv, and the call supplied neither an input nor a parameter of that name","remediation":"supp` | PASS 422 | |
| **QA-149** | execution | Execute a version that does not exist | `refused:*` | PASS 404 | `{"error":"not_found","detail":"nothing bound for maya://model/qa.pd.scorecard@8.8.8 in lab","remediation":"point the alias at an approved version"}` | PASS 404 | |
| **QA-150** | warrants | Revoke the grant | `accepted` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","urn"],"msg":"Field required","input":{"warrant_id":"01a0983635c00059717315c9a889","reason":"QA-150 finishe` | PASS 200 | |
| **QA-151** | warrants | Resolve after revocation | `refused:revoked|no_entitlement|410` | FAIL 200 | `{"maya_warrant":"1.0","warrant_id":"01a09836362a6b352e652c61f470","issued_at":1789260084.778879,"subject":{"urn":"maya://model/qa.pd.scorecard@1.0.0",` | PASS 410 | |
| **QA-152** | warrants | Every standing grant across the estate | `reported` | PASS 200 | `{"warrants":[{"id":"01a0983635c00059717315c9a889","model_id":"01a0982a68cd94fe02d84e8ca652","environment":"lab","binding_kind":"alias","alias_name":"c` | PASS 200 | |
| **QA-153** | decommission | Posture with no model named | `reported` | PASS 200 | `{"notifies_anybody":false,"archives_anything":false,"deletes_anything":false,"required":[{"field":"rationale","why":"why it is being taken out, in mor` | PASS 200 | |
| **QA-154** | decommission | Register and attest a model to decommission | `accepted` | PASS 200 | `{"id":"01a098384b23d68ffed331025412","urn":"maya://model/qa.decom","name":"QA decommission target","description":"","model_class":"credit.pd.scorecard` | PASS 200 | |
| **QA-155** | decommission | Decommission with a rationale of three characters | `refused:rationale_required` | PASS 422 | `{"error":"rationale_required","detail":"a decommissioning needs a rationale somebody can read later","remediation":"why it is being taken out, in more` | PASS 422 | |
| **QA-156** | decommission | Decommission naming no replacement at all | `refused:replacement_required` | PASS 422 | `{"error":"replacement_required","detail":"no replacement was named","remediation":"name the registered URN that does this job now, or 'none' if nothin` | PASS 422 | |
| **QA-157** | decommission | Decommission naming a replacement nobody registered | `refused:replacement_not_registered` | PASS 422 | `{"error":"replacement_not_registered","detail":"'maya://model/does.not.exist' is not a model in this register","remediation":"register the successor f` | PASS 422 | |
| **QA-158** | decommission | Decommission under a retention class nobody defined | `refused:unknown_retention_class` | PASS 422 | `{"error":"unknown_retention_class","detail":"'forever_and_ever' is not a retention class this platform has","remediation":"the classes are artifact, a` | PASS 422 | |
| **QA-159** | decommission | Who consumes this model | `reported` | PASS 200 | `{"urn":"maya://model/qa.decom","known":true,"consumers":[],"live":[],"detail":"0 live model(s) read this one, of 0 reached. Nothing downstream depends` | PASS 200 | |
| **QA-160** | decommission | A model_risk_manager decommissioning (needs model:retire) | `EXPLORATORY: does mrm hold model:retire?` | EXPLORATORY 403 | `{"error":"forbidden","detail":"'model:retire' is not granted by your roles (validator)","remediation":"ask an administrator for a role that carries th` | EXPLORATORY 403 | |
| **QA-161** | decommission | Decommission properly | `accepted` | PASS 201 | `{"model_id":"01a098384b23d68ffed331025412","urn":"maya://model/qa.decom","rationale":"superseded by the 2026 rebuild","replacement":"maya://model/qa.p` | PASS 201 | |
| **QA-162** | decommission | Decommission the same model twice | `refused:already_decommissioned` | PASS 409 | `{"error":"already_decommissioned","detail":"maya://model/qa.decom already carries a decommissioning record","remediation":"read it at GET /decommissio` | PASS 409 | |
| **QA-163** | decommission | Decommission a model in a state retire cannot be reached from | `refused:illegal_transition|*` | PASS 409 | `{"error":"illegal_transition","detail":"a model in 'amending' cannot be retired, so it cannot be decommissioned either","remediation":"retirement is r` | PASS 409 | |
| **QA-164** | decommission | What the estate still owes on decommissioning | `reported` | PASS 200 | `{"retired":1,"decommissioned":1,"without_a_record":[],"detail":"1 of 1 retired model(s) carry a decommissioning record. Every retirement says what rep` | PASS 200 | |
| **QA-165** | holds | The retention schedule | `reported` | PASS 200 | `{"classes":[{"artifact_class":"evidence_chain","years":10.0,"because":"AI Act Art. 19 asks for logs over the system's lifetime, and the chain is what ` | PASS 200 | |
| **QA-166** | holds | Place a hold with no matter named | `refused:matter_required` | PASS 422 | `{"error":"matter_required","detail":"a legal hold with no matter recorded is one nobody can tell has ended — and since a hold has no end date, that is` | PASS 422 | |
| **QA-167** | holds | Place a hold under a scope kind nobody defined | `refused:unknown_scope` | PASS 422 | `{"error":"unknown_scope","detail":"'galaxy' is not a hold scope","remediation":"one of estate (everything this register holds. Blunt, and sometimes ex` | PASS 422 | |
| **QA-168** | holds | An auditor may not place a hold | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'hold:place' is not granted by your roles (auditor)","remediation":"ask an administrator for a role that carries this p` | PASS 403 | |
| **QA-169** | holds | Place an estate-wide hold | `accepted` | PASS 201 | `{"reference":"HOLD-0001","matter":"FCA request 2026-08","scope_kind":"estate","scope_id":null,"classes":[],"owner":"s.iqbal","placed_by":"s.iqbal","pl` | PASS 201 | |
| **QA-170** | holds | Delete a model while a hold covers it | `refused:under_legal_hold` | FAIL 422 | `{"error":"reason_required","detail":"deleting a model requires a reason","remediation":""}` | PASS 423 | |
| **QA-171** | holds | Lift a hold that does not exist | `refused:no_hold` | PASS 404 | `{"error":"no_hold","detail":"no legal hold 'HOLD-9999'","remediation":"references look like HOLD-0001"}` | PASS 404 | |
| **QA-172** | holds | Lift a hold with no reason | `refused:reason_required` | PASS 422 | `{"error":"reason_required","detail":"lifting a hold with no reason resumes deletion on material somebody may be about to ask for, and records nothing ` | PASS 422 | |
| **QA-173** | holds | Lift the hold | `accepted` | PASS 200 | `{"id":"01a098384b92288784b4b7ff4fa0","reference":"HOLD-0001","matter":"FCA request 2026-08","scope_kind":"estate","scope_id":null,"classes":[],"owner"` | PASS 200 | |
| **QA-174** | holds | Lift the same hold twice | `refused:not_active` | PASS 409 | `{"error":"not_active","detail":"HOLD-0001 is lifted","remediation":"a hold is lifted once"}` | PASS 409 | |
| **QA-175** | holds | Delete a model as somebody who is not an administrator | `refused:forbidden|deletion_refused` | FAIL 403 | `{"error":"forbidden","detail":"'model:delete' is not granted by your roles (model_owner)","remediation":"ask an administrator for a role that carries ` | PASS 403 | |
| **QA-176** | holds | Delete a model with no reason | `refused:reason_required` | PASS 422 | `{"error":"reason_required","detail":"deleting a model requires a reason","remediation":""}` | PASS 422 | |
| **QA-177** | holds | Delete the throwaway model as an administrator, hold lifted | `accepted` | FAIL 422 | `{"error":"reason_required","detail":"deleting a model requires a reason","remediation":""}` | PASS 200 | |
| **QA-178** | authority | The authority posture with nothing published | `reported` | PASS 200 | `{"dimensions":["tier","amount","legal_entity"],"amount_comes_from":"the sourced exposure fact (`H-8`) and nowhere else — a figure attested to a named ` | PASS 200 | |
| **QA-179** | authority | Publish a band with no name | `refused:band_name_required` | PASS 422 | `{"error":"band_name_required","detail":"a band needs a name","remediation":"name it after the authority it encodes — the row gets quoted in a committe` | PASS 422 | |
| **QA-180** | authority | Publish a band with no stages | `refused:stages_required` | PASS 422 | `{"error":"stages_required","detail":"a band with no stages requires no signatures","remediation":"give it at least one stage: a list of roles that sig` | PASS 422 | |
| **QA-181** | authority | Publish a band for a tier outside 1..4 | `refused:unknown_tier` | PASS 422 | `{"error":"unknown_tier","detail":"tier 9 is not one this platform has","remediation":"the tiers are 1 to 4; a band with no tier applies to all of them` | PASS 422 | |
| **QA-182** | authority | Publish a band with a negative floor | `refused:negative_floor` | PASS 422 | `{"error":"negative_floor","detail":"an amount floor below zero matches nothing","remediation":"use 0 for a band with no floor"}` | PASS 422 | |
| **QA-183** | authority | An operator may not publish a band | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'policy:publish' is not granted by your roles (operator)","remediation":"ask an administrator for a role that carries t` | PASS 403 | |
| **QA-184** | authority | Publish a tier-1 band: first line signs, then second | `accepted` | PASS 201 | `{"id":"01a09839ac093b1710a995d44c69","name":"qa-tier1-band","tier":1,"at_or_above":0.0,"legal_entity":null,"stages":[["model_risk_manager"],["validato` | PASS 201 | |
| **QA-185** | authority | Publish a band whose name is taken | `refused:band_exists` | PASS 409 | `{"error":"band_exists","detail":"a band called 'qa-tier1-band' is already published","remediation":"withdraw it before publishing another under that n` | PASS 409 | |
| **QA-186** | authority | Delegate with no principal named | `refused:principal_required` | PASS 422 | `{"error":"principal_required","detail":"a delegation needs a person","remediation":"whose authority this is. A delegation to a role rather than a pers` | PASS 422 | |
| **QA-187** | authority | Delegate with no instrument | `refused:instrument_required` | PASS 422 | `{"error":"instrument_required","detail":"no instrument was named for this delegation","remediation":"the board resolution, charter or letter that gran` | PASS 422 | |
| **QA-188** | authority | Delegate a ceiling of zero | `refused:ceiling_required` | PASS 422 | `{"error":"ceiling_required","detail":"a ceiling of zero delegates nothing","remediation":"the largest amount they may approve, in one currency. A pers` | PASS 422 | |
| **QA-189** | authority | A new tier-1 version, so the band binds to a fresh approval | `accepted` | PASS 201 | `{"model_id":"01a09830feea6d7abd6745535a35","semver":"2.0.0","manifest":{"urn":"maya://model/qa.ews.tier1","semver":"2.0.0","kernel":{"runtime":"formul` | PASS 201 | |
| **QA-190** | authority | Open a quorum that the band should shape into stages | `accepted` | PASS 201 | `{"id":"01a09839ac1b8080ee4feef511f3","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09839ac16c595efb1d0ed160a","tier":1,"required_ro` | PASS 201 | |
| **QA-191** | authority | The second stage signs before the first | `refused:out_of_sequence` | PASS 409 | `{"error":"out_of_sequence","detail":"'validator' signs after model_risk_manager on band 'qa-tier1-band', and model_risk_manager have not signed yet","` | PASS 409 | |
| **QA-192** | authority | The first stage signs, with no delegation on record at all | `EXPLORATORY: no_delegated_authority or permitted` | EXPLORATORY 200 | `{"id":"01a09839ac1b8080ee4feef511f3","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09839ac16c595efb1d0ed160a","tier":1,"required_ro` | EXPLORATORY 200 | |
| **QA-193** | authority | Delegate a ceiling far below the model's exposure | `accepted` | PASS 201 | `{"principal":"a.mehta","ceiling":1000.0,"currency":"USD","legal_entity":null,"instrument":"BR-2026-04","granted_by":"s.iqbal","granted_at":1789260311.` | PASS 201 | |
| **QA-194** | authority | Signing above the delegated ceiling | `refused:beyond_delegated_authority` | FAIL 200 | `{"id":"01a09839ac1b8080ee4feef511f3","model_id":"01a09830feea6d7abd6745535a35","model_version_id":"01a09839ac16c595efb1d0ed160a","tier":1,"required_ro` | PASS 409 | |
| **QA-195** | authority | A ceiling in a currency the estate does not report in | `EXPLORATORY: ceiling_not_comparable at delegation or at signing` | EXPLORATORY 201 | `{"principal":"p.dual","ceiling":500000000000.0,"currency":"JPY","legal_entity":null,"instrument":"BR-2026-05","granted_by":"s.iqbal","granted_at":1789` | EXPLORATORY 201 | |
| **QA-196** | authority | What authority applies to one model | `reported` | PASS 200 | `{"urn":"maya://model/qa.ews.tier1","tier":1,"legal_entity":"LE-US-01","amount":null,"amount_source":null,"band":"qa-tier1-band","stages":[["model_risk` | PASS 200 | |
| **QA-197** | authority | The signing sequence for one model | `reported` | PASS 200 | `{"urn":"maya://model/qa.ews.tier1","tier":1,"legal_entity":"LE-US-01","amount":null,"amount_source":null,"band":"qa-tier1-band","stages":[["model_risk` | PASS 200 | |
| **QA-198** | authority | Delegations on record | `reported` | PASS 200 | `{"delegations":[{"id":"01a09839ac2ba7cb6800d3d5c92d","principal":"a.mehta","ceiling":1000.0,"currency":"USD","legal_entity":null,"instrument":"BR-2026` | PASS 200 | |
| **QA-199** | authority | Withdraw a band that does not exist | `refused:unknown_band` | PASS 404 | `{"error":"unknown_band","detail":"no band called 'no-such-band' is published","remediation":""}` | PASS 404 | |
| **QA-200** | recert | Open a campaign with a reference nobody quoted | `refused:reference_required` | PASS 422 | `{"error":"reference_required","detail":"a recertification campaign needs a reference","remediation":"it gets quoted in an audit finding; 'the review w` | PASS 422 | |
| **QA-201** | recert | Open a campaign whose reviewer is not a principal | `refused:no_such_principal` | PASS 404 | `{"error":"no_such_principal","detail":"no principal 'nobody.here'","remediation":""}` | PASS 404 | |
| **QA-202** | recert | Open a campaign over somebody who is not a principal | `refused:no_such_principal` | FAIL 404 | `{"error":"no_such_principal","detail":"no principal 'ghost.person'","remediation":""}` | PASS 404 | |
| **QA-203** | recert | Open a campaign over three named people | `accepted` | PASS 201 | `{"reference":"REC-QA-1","title":"QA access review","reviewer":"s.iqbal","status":"open","population":3,"confirmed":0,"revoked":0,"unreviewed":3,"unrev` | PASS 201 | |
| **QA-204** | recert | Open a second campaign under the same reference | `refused:campaign_exists` | PASS 409 | `{"error":"campaign_exists","detail":"a recertification called 'REC-QA-1' is already open","remediation":"close it before opening another under that re` | PASS 409 | |
| **QA-205** | recert | The named reviewer answers a row | `accepted` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 200 | |
| **QA-206** | recert | Somebody who is not the reviewer answers | `refused:not_the_reviewer` | PASS 403 | `{"error":"not_the_reviewer","detail":"REC-QA-1 names s.iqbal as its reviewer, not admin","remediation":"a campaign that anybody may answer is a campai` | PASS 403 | |
| **QA-207** | recert | The reviewer answers their own row | `refused:self_recertification` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 403 | |
| **QA-208** | recert | An answer outside the vocabulary | `refused:unknown_answer` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 422 | |
| **QA-209** | recert | Revoking with no reason | `refused:reason_required` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 422 | |
| **QA-210** | recert | Answering for somebody not in the population | `refused:not_in_population` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 404 | |
| **QA-211** | recert | Answering under a reference that does not exist | `refused:forbidden|unknown_recertification` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 403 | |
| **QA-212** | recert | Reassign the review with no reason | `refused:reason_required` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","state"],"msg":"Field required","input":{"to":"admin","reason":""}},{"type":"extra_forbidden","loc":["body"` | PASS 422 | |
| **QA-213** | recert | Reassign the review | `accepted` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","state"],"msg":"Field required","input":{"to":"admin","reason":"reviewer on leave"}},{"type":"extra_forbidd` | PASS 200 | |
| **QA-214** | recert | The old reviewer answers after reassignment | `refused:forbidden|not_the_reviewer` | FAIL 403 | `{"error":"forbidden","detail":"'principal:manage' is not granted by your roles (model_risk_manager)","remediation":"ask an administrator for a role th` | PASS 403 | |
| **QA-215** | recert | Close the campaign | `accepted` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","state"],"msg":"Field required","input":{}}]}` | PASS 200 | |
| **QA-216** | recert | Answer a closed campaign | `refused:campaign_closed` | FAIL 403 | `{"error":"not_the_reviewer","detail":"REC-QA-1 names s.iqbal as its reviewer, not admin","remediation":"a campaign that anybody may answer is a campai` | PASS 409 | |
| **QA-217** | recert | Read one campaign | `reported` | PASS 200 | `{"reference":"REC-QA-1","title":"QA access review","reviewer":"s.iqbal","status":"open","population":3,"confirmed":0,"revoked":0,"unreviewed":3,"unrev` | PASS 200 | |
| **QA-218** | recert | The recertification posture across the estate | `reported` | PASS 200 | `{"answers":["confirmed","revoked"],"unanswered_is":"unreviewed","times_out":false,"revokes_outside_maya":false,"decides_who_reviews_whom":false,"dorma` | PASS 200 | |
| **QA-219** | docsearch | Search with no query at all | `refused:422` | PASS 422 | `{"detail":[{"type":"missing","loc":["query","q"],"msg":"Field required","input":null}]}` | PASS 422 | |
| **QA-220** | docsearch | Search for a stopword only | `refused:empty_query` | PASS 422 | `{"error":"empty_query","detail":"a search with no terms in it would return the whole corpus, which is not a search","remediation":"give a word or two;` | PASS 422 | |
| **QA-221** | docsearch | Search with a limit outside the range | `refused:limit_out_of_range` | PASS 422 | `{"error":"limit_out_of_range","detail":"500 is not a page size; the bound is 1 to 200","remediation":""}` | PASS 422 | |
| **QA-222** | docsearch | Search with a limit of zero | `refused:limit_out_of_range` | PASS 422 | `{"error":"limit_out_of_range","detail":"0 is not a page size; the bound is 1 to 200","remediation":""}` | PASS 422 | |
| **QA-223** | docsearch | Search an estate with no documents | `reported` | PASS 200 | `{"query":"backtest","terms":["backtest"],"results":[],"matches":0,"documents_searched":0,"could_not_be_read":[],"scoped":true,"detail":"nothing matche` | PASS 200 | |
| **QA-224** | docsearch | What the search can and cannot read | `reported` | PASS 200 | `{"documents":0,"readable":0,"unread":0,"unread_by_media_type":{},"coverage":0.0,"semantic_search":{"available":false,"why_not":"semantic search means ` | PASS 200 | |
| **QA-225** | docsearch | An operator with no document:read may not search | `refused:forbidden` | PASS 403 | `{"error":"forbidden","detail":"'document:read' is not granted by your roles (operator)","remediation":"ask an administrator for a role that carries th` | PASS 403 | |
| **QA-226** | validation | Open a validation naming the version's author as validator | `EXPLORATORY: refused or permitted at open` | EXPLORATORY 201 | `{"id":"01a0983c5b162019a4176d31e148","model_id":"01a0982a68cd94fe02d84e8ca652","model_version_id":"01a0982c1fbc954bc5189f39f956","kind":"initial","sco` | EXPLORATORY 201 | |
| **QA-227** | validation | Record a test result | `accepted` | PASS 201 | `{"id":"01a0983c5b1b5a15a7b8a7e98ec4","validation_id":"01a0983c5b162019a4176d31e148","test_key":"discrimination.gini","parameters":{},"slice":{},"value` | PASS 201 | |
| **QA-228** | validation | Conclude with no tier verdict | `refused:*` | PASS 409 | `{"error":"validation_refused","detail":"concluding a validation requires a verdict on the model's risk tier, and 'None' is not one; the three are rema` | PASS 409 | |
| **QA-229** | validation | Conclude with a tier verdict that is not remains_appropriate and no note | `refused:*` | PASS 409 | `{"error":"validation_refused","detail":"a verdict of 'should_be_higher' needs a note. Saying the tier is wrong without saying why is not something any` | PASS 409 | |
| **QA-230** | validation | Conclude a validation the concluder did not run | `EXPLORATORY` | EXPLORATORY 409 | `{"error":"validation_refused","detail":"cannot approve: 1 test(s) failed (discrimination.gini); conclude 'approved_with_conditions' with the condition` | EXPLORATORY 409 | |
| **QA-231** | findings | Raise a finding against the model | `accepted` | FAIL 409 | `{"error":"validation_refused","detail":"unknown severity 'high'; expected one of Critical, High, Medium, Low, Observation","remediation":"the refusal ` | PASS 201 | |
| **QA-232** | findings | Raise a finding with a severity nobody defined | `refused:*` | PASS 409 | `{"error":"validation_refused","detail":"unknown severity 'apocalyptic'; expected one of Critical, High, Medium, Low, Observation","remediation":"the r` | PASS 409 | |
| **QA-233** | findings | The person who raised a finding closes it | `refused:raiser_may_not_close|verifier_not_self|*` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","evidence"],"msg":"Field required","input":{"note":"closing my own finding"}},{"type":"extra_forbidden","lo` | FAIL 403 | |
| **QA-234** | findings | Acknowledge the finding as its owner | `accepted` | FAIL 404 | `{"error":"no_finding","detail":"no finding None","remediation":"check the identifier against the register for this model"}` | PASS 200 | |
| **QA-235** | findings | The owner who acknowledged it has no finding:extend | `refused:forbidden|self_extension` | FAIL 404 | `{"error":"no_finding","detail":"no finding None","remediation":"check the identifier against the register for this model"}` | PASS 403 | |
| **QA-236** | findings | Extend as somebody in the second line | `accepted` | FAIL 404 | `{"error":"no_finding","detail":"no finding None","remediation":"check the identifier against the register for this model"}` | PASS 200 | |
| **QA-237** | findings | Findings ageing across the estate | `reported` | PASS 200 | `{"model":null,"scope":7,"models":7,"open":0,"closed":0,"blocking":0,"overdue":0,"unacknowledged":0,"unplanned":0,"escalated":0,"worst_severity":null,"` | PASS 200 | |
| **QA-238** | findings | A blocking finding stops a warrant resolving | `EXPLORATORY: is high severity blocking?` | EXPLORATORY 200 | `{"maya_warrant":"1.0","warrant_id":"01a0983c5b4f61e88c79d63b9820","issued_at":1789260487.5034413,"subject":{"urn":"maya://model/qa.pd.scorecard@1.0.0"` | EXPLORATORY 410 | |
| **QA-239** | findings | Assign the finding to somebody else | `accepted` | FAIL 404 | `{"error":"no_finding","detail":"no finding None","remediation":"check the identifier against the register for this model"}` | PASS 200 | |
| **QA-240** | findings | Close it as somebody who did not raise it | `EXPLORATORY: what closure requires` | EXPLORATORY 422 | `{"detail":[{"type":"missing","loc":["body","evidence"],"msg":"Field required","input":{"note":"the re-fit landed and was reviewed"}},{"type":"extra_fo` | EXPLORATORY 200 | |
| **QA-241** | monitoring | The monitor kinds this platform knows | `reported` | PASS 200 | `{"kinds":[{"kind":"input_drift","tests":["stability.psi"],"needs_labels":false},{"kind":"score_drift","tests":["stability.psi"],"needs_labels":false},` | PASS 200 | |
| **QA-242** | monitoring | Define a monitor | `accepted` | FAIL 422 | `{"error":"unknown_kind","detail":"unknown monitor kind 'drift'","remediation":"expected one of input_drift, score_drift, performance, calibration"}` | PASS 201 | |
| **QA-243** | monitoring | Define a monitor with a test key nobody implements | `refused:*` | PASS 422 | `{"error":"unknown_kind","detail":"unknown monitor kind 'drift'","remediation":"expected one of input_drift, score_drift, performance, calibration"}` | PASS 409 | |
| **QA-244** | monitoring | Ingest an externally computed value | `accepted` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","window_start"],"msg":"Field required","input":{"value":0.11,"computed_by":"the bank's own drift job","meth` | PASS 201 | |
| **QA-245** | monitoring | An ingest that tries to mark its own homework | `refused:422` | PASS 422 | `{"detail":[{"type":"missing","loc":["body","window_start"],"msg":"Field required","input":{"value":0.99,"computed_by":"an optimistic engine","passed":` | PASS 422 | |
| **QA-246** | monitoring | Ingest a value that breaches the threshold | `reported` | FAIL 422 | `{"detail":[{"type":"missing","loc":["body","window_start"],"msg":"Field required","input":{"value":0.91,"computed_by":"the bank's own drift job","meth` | PASS 201 | |
| **QA-247** | monitoring | Observations on the monitor | `reported` | FAIL 500 | `Internal Server Error` | PASS 200 | |
| **QA-248** | monitoring | Evaluate a drift monitor with no rows and no reference | `refused:no_reference` | EXPLORATORY 404 | `{"error":"no_monitor","detail":"no monitor None","remediation":""}` | PASS 422 | |
| **QA-249** | monitoring | Run the governance batch | `accepted` | PASS 200 | `{"ran":26,"failed":0,"at":1789260487.592772,"results":[{"id":"01a0983c5ba9ae65bc157131ccac","job":"immaterial.conditions","outcome":{"models":0,"raise` | PASS 200 | |
| **QA-250** | monitoring | Scheduler history after the run | `reported` | PASS 200 | `{"runs":[{"id":"01a0983c5ba9ae65bc157131ccac","job":"immaterial.conditions","outcome":{"models":0,"raised":[],"count":0,"detail":"0 immaterial model(s` | PASS 200 | |
| **QA-251** | portfolio | The dimensions a portfolio may be cut by | `reported` | PASS 200 | `{"dimensions":[{"dimension":"domain","means":"the business the model serves"},{"dimension":"tier","means":"what rides on it being right"},{"dimension"` | PASS 200 | |
| **QA-252** | portfolio | Portfolio by tier (enters the estate fold) | `accepted` | PASS 200 | `{"dimension":"tier","means":"what rides on it being right","cells":[{"value":"3","models":3,"owed":3,"urns":["maya://model/qa.decom","maya://model/qa.` | PASS 200 | |
| **QA-253** | portfolio | Portfolio by a dimension nobody defined | `refused:unknown_dimension` | PASS 422 | `{"error":"unknown_dimension","detail":"'nonsense' is not a dimension this register is cut by","remediation":"one of domain (the business the model ser` | PASS 422 | |
| **QA-254** | portfolio | A heatmap of one dimension against itself | `refused:same_dimension` | PASS 422 | `{"error":"same_dimension","detail":"a heatmap of tier against itself is a list with extra steps","remediation":"choose two different dimensions"}` | PASS 422 | |
| **QA-255** | portfolio | A heatmap of domain against tier | `accepted` | PASS 200 | `{"rows":"domain","columns":"tier","row_values":["credit"],"column_values":["1","3","untiered"],"grid":{"credit":{"3":{"models":3,"owed":3,"urns":["may` | PASS 200 | |
| **QA-256** | portfolio | Portfolio by trainability class | `accepted` | PASS 200 | `{"dimension":"trainability_class","means":"how its parameters were arrived at — derived from the latest version, never declared","cells":[{"value":"T0` | PASS 200 | |
| **QA-257** | portfolio | The portfolio trend over twelve points | `accepted` | PASS 200 | `{"points":[{"at":1757724666.5295625,"models":0,"by_status":{},"by_tier":{},"chain_seq":null,"chain_hash":null},{"at":1760591575.6204715,"models":0,"by` | PASS 200 | |
| **QA-258** | portfolio | Aggregate risk across the estate | `accepted` | PASS 200 | `{"models":7,"with_something_owed":4,"exposure_known_for":4,"exposure_coverage":0.5714,"exposure_total":50501000000.0,"exposure_with_something_owed":25` | PASS 200 | |
| **QA-259** | portfolio | The notification batch dry run (folds over the whole estate) | `accepted` | PASS 200 | `{"channel":"log","dry_run":true,"considered":6,"sent":0,"suppressed":6,"failed":0,"deliveries":[{"principal":"admin","channel":"log","state":"suppress` | PASS 200 | |
| **QA-260** | portfolio | An operator with no report:read may not cut the portfolio | `EXPLORATORY: does operator hold report:read?` | EXPLORATORY 403 | `{"error":"forbidden","detail":"'report:read' is not granted by your roles (operator)","remediation":"ask an administrator for a role that carries this` | EXPLORATORY 403 | |
| **QA-261** | screens | Dashboard (/dashboard) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-262** | screens | Register a model (/models/new) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-263** | screens | Features (/features) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-264** | screens | Define a feature (/features/new) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-265** | screens | Load values (/features/load) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-266** | screens | Point in time (/features/point-in-time) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-267** | screens | Featuresets (/featuresets) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-268** | screens | Compose a featureset (/featuresets/author) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-269** | screens | The featureset lattice (/featuresets/lattice) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-270** | screens | Model algebra (/model-algebra) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-271** | screens | Warrants (/warrants) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-272** | screens | Who may run what (/warrants/estate) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-273** | screens | Findings (/findings) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-274** | screens | Portfolio (/portfolio) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-275** | screens | Model health (/model-health) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-276** | screens | Document search (/documents/search) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-277** | screens | Query (/query) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-278** | screens | Notifications (/notifications) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-279** | screens | Policies (/policies) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-280** | screens | Waivers (/waivers) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-281** | screens | Limitations (/limitations) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-282** | screens | Assumptions (/assumptions) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-283** | screens | Classification (/classification) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-284** | screens | Campaigns (/campaigns) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-285** | screens | Break glass (/break-glass) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-286** | screens | Supervisory matters (/supervisory) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-287** | screens | Vendor models (/vendor-models) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-288** | screens | Board pack (/board-pack) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-289** | screens | Dependencies (/dependencies) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-290** | screens | Telemetry (/telemetry) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-291** | screens | Lifecycle profiles (/lifecycle-profiles) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-292** | screens | Packages (/packages) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-293** | screens | Assist (/assist) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-294** | screens | Tutorials (/tutorials) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-295** | screens | Help (/help) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-296** | screens | About (/about) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-297** | screens | Admin (/admin) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-298** | screens | People and roles (/admin/principals) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-299** | screens | API keys (/admin/api-keys) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-300** | screens | Evidence (/admin/evidence) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-301** | screens | Live log (/admin/logs) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-302** | screens | Regimes (/admin/regimes) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-303** | screens | Runtimes (/admin/runtimes) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-304** | screens | Scheduler (/admin/scheduler) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-305** | screens | Perimeter (/admin/perimeter) as admin | `accepted` | PASS 200 | `(an HTML page)` | PASS 200 | |
| **QA-306** | screens | The dashboard with no session at all | `reported` | EXPLORATORY 200 | `(an HTML page)` | PASS 303 | |
| **QA-307** | screens | Admin -> People and roles as an auditor | `accepted` | FAIL 200 | `(an HTML page)` | PASS 200 | |
| **QA-308** | screens | Admin -> API keys as a feature curator | `refused:403` | FAIL 200 | `(an HTML page)` | PASS 403 | |
| **QA-309** | screens | The live log as a model developer | `EXPLORATORY: does model_developer hold log:read?` | EXPLORATORY 200 | `(an HTML page)` | EXPLORATORY 403 | |
| **QA-310** | screens | A model page for a model that does not exist | `refused:404` | FAIL 200 | `(an HTML page)` | PASS 404 | |
| **QA-311** | screens | A model page as somebody scoped to another legal entity | `refused:403` | FAIL 200 | `(an HTML page)` | PASS 403 | |
| **QA-312** | screens | The dashboard as every non-admin role in turn | `reported` | PASS 200 | `q.tester=200; s.iqbal=200; j.okafor=200; a.mehta=200; d.raman=200; r.hale=200; o.perez=200` | PASS 200 | |
| **QA-313** | screens | The navbar offers no page the role is then refused | `reported` | — | `` | PASS 200 | |
| **QA-314** | screens | No navbar link points at a model the register cannot address | `reported` | — | `` | PASS 200 | |

### Beyond the API

Twelve cases run by hand rather than through `qa_cases.py`, because their
surface is not HTTP.

| ID | Area | Action | Expectation | Pass 1 @ `9baa0c5` | Answer, verbatim | Re-run @ `wt-679bbf5b` | Pass 2 |
|---|---|---|---|---|---|---|---|
| **QA-B1** | qa pack | `python docs/QA/qa_setup.py` against an empty instance | `accepted` | **FAIL** | `REFUSED  its risk tier — this assessment lands on a different tier depending on trainability_class, and the request did not say` | PASS — completes, tier 3 | |
| **QA-B2** | qa pack | the accounts the cheatsheet's table publishes exist afterwards | `reported` | **FAIL** | only `admin`, `q.tester`, `svc/qa-runner` | PASS — six accounts | |
| **QA-B3** | qa pack | run it a second time | `accepted` | **FAIL** | `REFUSED  its risk tier — these are the same facts as the last assessment, so re-running the formula moves the review date without anything having been reviewed` | PASS — "already tiered, Tier 3 — not re-assessing, because re-running the formula is not a review" | |
| **QA-B4** | rbac | suspend `svc/qa-runner`, both spellings of the slash | `accepted` | **FAIL** | `{"detail":"Not Found"}` | FAIL — unchanged, see N-1 | |
| **QA-B5** | authority | sign a banded approval with delegations recorded but none held | `refused:no_delegated_authority` | PASS | `{"error":"no_delegated_authority","detail":"s.iqbal holds no live delegated authority",…}` | PASS | |
| **QA-B6** | ops | `python -m tools.ops.backup` twice into the same directory | `refused` | PASS, exit 1 | `… is not empty. A backup writes into a fresh directory so that a partial copy can never be mistaken for a complete one — there is no merging here, deliberately.` | PASS | |
| **QA-B7** | ops | `python -m tools.ops.verify --help`, the command both refusals name | `accepted` | **FAIL** | `No module named tools.ops.verify` | PASS — no `python -m` under `tools/` names a module that will not import | |
| **QA-B8** | ops | `python -m tools.ops.restore` over a live database | `refused` | PASS, exit 1 | `refusing to restore over a database holding 176 evidence node(s). Two chains do not interleave, so there is no merge here and the act is irreversible.` | PASS | |
| **QA-B9** | monitoring | read a monitor's observations as a principal scoped to another legal entity | `refused:403` | **FAIL** | `200` with the monitor, its observations and its breaches | PASS — `{"error":"out_of_scope","detail":"model belongs to legal entity LE-US-01, outside your scope (LE-UK-99)"}` | |
| **QA-B10** | cli | `python -m maya_sdk.cli worklist` | `accepted` | **FAIL**, exit 1 | `REFUSED (404) http_404 / Not Found` | PASS — the worklist, exit 0 | |
| **QA-B11** | features | a view row carries the features it declares | `reported` | **FAIL** | view row keys: `created_at, delta_table, description, entity, id, name, owner` — no `features`, so `_dtypes` returns `{}` always | PASS | |
| **QA-B12** | schema | UPDATE each immutable `model_version` column, and UPDATE/DELETE `evidence_node`, directly in SQLite | `refused` | PASS | `model_version.semver is immutable: it describes what the version IS…` / `evidence_node is append-only: it is the evidence chain…` — 16 triggers, all firing; `status` mutable by design | PASS | |

Also confirmed by hand, and recorded here rather than as numbered cases:
the CLI's exit-code contract (`0` answered, `1` refused, `2` unreachable) holds
for `whoami`, `worklist`, `call` and an unreachable URL; `qa_setup.py` builds a
clean estate and the cheatsheet's sections 8 and 9 then run end to end on it
(version approval refused for the creator, accepted for the second line, record
submitted and approved, two-role attestation completed, featureset published,
fit warrant issued).

---

## 7. What could not be tested, and why

A QA report with no coverage gaps is one nobody should trust. These are this
pass's.

**PostgreSQL was not exercised at all.** Everything here ran on SQLite. The two
schemas differ in two substitutions and are generated from the same `tables.py`,
but the immutability triggers are written twice — 16 `RAISE(ABORT)` triggers in
SQLite against four `RAISE EXCEPTION` functions in plpgsql — and only the SQLite
half was attacked (QA-B12). `docs/11 §4.5` claims both. **The PostgreSQL half of
that claim is untested by this pass.**

**Iceberg was not exercised.** The instance ran on Delta, the shipped default.
D-7 is precisely a bug whose worst symptom is on Iceberg (a refused write rather
than a quiet null-typed column), and it was diagnosed statically and fixed
without ever reproducing the Iceberg failure. A pass on `table_format: iceberg`
would be worth having.

**A restore was refused but never completed.** QA-B8 proves the refusal;
restoring into an empty location and verifying the chain head against the
manifest was not run, so the round trip is covered only by
`tests/test_backup_restore.py` and not by this pass.

**`version:sign` segregation is unreachable with the shipped roles.** The rule
exists (`core/authz/segregation.py`) and is the one whose absence the comment
above it describes as "the control got weaker as the model got riskier". To fire
it, the person who created a version must hold `model_risk_manager` or
`validator` — and `version:create` lives only with `model_developer` and
`model_owner`, both of which are declared incompatible with both signing roles.
So the rule is defence in depth against a configuration the platform refuses to
create. Not a defect; genuinely untestable through the API, and worth knowing.

**`ceiling_not_comparable` was provoked but not observed.** QA-195 records a
JPY delegation successfully (`201`); the refusal fires at *signing*, and getting
`p.dual` into a required role on a fact-sourced model at the right stage of a
banded quorum did not fit the estate's forward walk. The code path is read and
looks right; it is not proven by this pass.

**Concurrency was not tested.** Every case is sequential. The
`already_signed_personally` race that `UNIQUE (version_approval_id, principal)`
exists to close, the feature-view orphan that `mode="overwrite"` exists to
close, and the idempotency store are all covered by unit tests and by nothing
here.

**Two cases did not execute in pass 1.** QA-090 and QA-091 — the dual-hatted
signer — failed on a harness defect (`p.dual` missing from the credential table)
and their first real execution is the post-remediation column. They are the two
rows in §6 with no Pass 1 result.

**The screens were checked for reachability and refusal, not for content.**
54 screen cases confirm that every navbar entry renders for a role that should
see it and is refused for one that should not, and QA-313 walks every link each
role is offered. Nothing here checks that a page shows the *right* numbers.
The first version of these cases was worse than useless: it used HTTP Basic,
which the UI routes ignore, so all 45 "passed" against the sign-in page. That is
recorded because it is the shape of mistake this log exists to make visible.

**Assist, telemetry, board packs, regimes, export packs, break-glass, campaigns,
intake, vendor assessments, overlays, waivers and rule sets** were reached only
as screens (`200` under a role that should see them). Their APIs are ~90 of the
533 paths and this pass did not drive them.

---

## 8. Expected to change in pass 2

Stated in advance. A fix that flips a case nobody predicted is worth knowing
about, and so is one that flips nothing.

**These should move FAIL → PASS**, and each has a named fix behind it:

| Case | Was | Should be | Fix |
|---|---|---|---|
| QA-205, QA-207, QA-208, QA-209, QA-210, QA-216 | FAIL 403 `forbidden` | PASS | D-1 |
| QA-213, QA-215 | FAIL 422 | PASS | D-2 |
| QA-247 | FAIL 500 | PASS 404 `no_monitor` | D-3 |
| QA-B9 | FAIL 200 | PASS 403 `out_of_scope` | D-3 |
| QA-053 | FAIL 201 | PASS 422 `validation_failed` | D-4 |
| QA-B10 | FAIL exit 1 | PASS exit 0 | D-5 |
| QA-313 | FAIL (four dead links) | PASS | D-6 |
| QA-B11 | FAIL | PASS | D-7 |
| QA-B7 | FAIL | PASS | D-8 |
| QA-B1, QA-B2, QA-B3 | FAIL | PASS | D-9…D-12 |
| QA-134 | FAIL 409 `schema_not_satisfied` | PASS 201 | D-11 |

**These should stay FAIL** — they are recorded, diagnosed and deliberately not
fixed. A pass 2 that shows them passing means something changed that this log
does not explain:

QA-107 (N-2), QA-109 (N-3), QA-113 (N-4), QA-114 (N-5), QA-117 (N-6),
QA-B4 (N-1).

**These should stay EXPLORATORY**, and what they found is in §4:
QA-047, QA-052, QA-056, QA-067, QA-069, QA-070, QA-097, QA-104, QA-105,
QA-108, QA-160, QA-192, QA-195, QA-226, QA-230, QA-238, QA-240, QA-248,
QA-260, QA-306, QA-309.

**Cases whose result depends on the estate's history, not on the code.** These
answer differently on a second run against the same database, and a change in
them means the estate was reused rather than rebuilt: QA-036 and QA-045
(the API key already exists / is already revoked), QA-051, QA-106, QA-112,
QA-120, QA-125 (already-exists conflicts), QA-154 and QA-161 (the model is
already decommissioned), QA-169 and QA-173 (the hold is already lifted),
QA-203 (the campaign already exists). **Rebuild the estate before pass 2.**

**One thing to check in pass 2 that no case covers yet.** N-6 is the natural
follow-on to D-7: now that a view row carries its declared features, a load
carrying a column the view never declared can be refused. If that fix is made,
QA-117 flips and a new case should assert that a load of a *subset* is still
accepted — narrowing a version is legitimate, inventing a column is not.

---

## 9. Every code change, and the case that prompted it

One row per changed file, in the order a reviewer should read them. **Nothing
here was speculative** — every change traces to a case in §6 that failed
against `9baa0c5` — but "traceable to a failing case" is not the same as "in
scope for a QA pass", and the last column says which of these I would defend
and which I would hand back.

`git diff` at the time of the stop: **24 files modified, 1 added**,
784 insertions, 47 deletions.

### Product code — five files

| File | Prompting case | What changed | Why, in one line | Confidence |
|---|---|---|---|---|
| `routes/principal_routes.py` | QA-205, QA-207–QA-211, QA-214, QA-216 (all FAIL 403 `forbidden`) | `/reassign` and `/close` declared before `/{principal}`; the answer route authorises the campaign's **named reviewer** and still requires `principal:manage` from anybody else | Two endpoints were unreachable and no non-administrator reviewer could answer a campaign; the campaign's own refusals are untouched and all still fire | **High** — the control got no weaker, and the four new tests assert each refusal still lands |
| `routes/monitoring_routes.py` | QA-247 (FAIL 500), QA-B9 (FAIL 200 across a legal-entity boundary) | `monitors.require` moved inside `self.guard`; `model=self.model_behind(monitor)` added to the `authorise` call | A 500 with an empty body on a bad identifier, and the legal-entity scope not applied on the one monitor route that omitted `model=` | **High** — matches every sibling route in the same file exactly |
| `routes/model_routes.py` | QA-053 (FAIL 201), QA-314 (a dead `/model/not-a-urn` link on the dashboard) | `_refuse_unaddressable_urn` before `reg.register`, at the route only | The register accepted identifiers no route can address, and the estate page linked to one | **High** — route-layer only, uses the existing `validation_failed` code, no taxonomy change |
| `routes/lifecycle_routes.py` | QA-B10 (FAIL, `maya worklist` → 404) | **new route** `GET /api/v1/worklist` | The CLI ships a documented command calling a path that does not exist | **Low — see §10.** This adds API surface. Removing the CLI command was the other fix and is the smaller one |
| `core/authz/policy.py` | QA-313 (FAIL: four dashboard links a `feature_curator` is offered and then refused) | `visible()` returns `[]` unless the principal holds `model:read`, then scopes as before | The dashboard showed every model in the estate to somebody with no permission to read one | **Medium — see §10.** The change is strictly *stricter*: it adds a check that was absent and permits nothing that was previously refused. But `visible()` has 19 callers and only the test suite and one screen were checked |

**On `core/authz/policy.py` specifically**, since it is authorisation: the case
did not fail because something was refused. It failed because something was
**permitted** — a principal with none of `model:read` was shown the whole
register. The fix denies more than before and allows nothing new. No test was
made to pass by relaxing a control; the three new tests in
`tests/test_authz.py` assert that the scope still applies *on top of* the
permission, so neither half can be dropped later without a failure.

### The schema change — four files, one column

| File | Prompting case | What changed |
|---|---|---|
| `db/schema/features.py` | QA-B11 (FAIL: the view row has no `features` key, so `ViewManager._dtypes` returns `{}` on every call) | `FEATURE_VIEW` gains `Column("features", Text, nullable=False, server_default=text("'[]'"))` |
| `db/schema/sqlite.sql`, `db/schema/postgres.sql` | — | regenerated by `tools/ci/render_schema.py`; **not hand-edited** |
| `db/repositories.py` | — | `FeatureViewRepository` gains `JSON = ("features",)` so the column decodes like every other document column |
| `core/features/views.py` | — | `create()` writes the declared list onto the row |

**The column is `feature_view.features`.** The finding it closes is D-7: a
view's declared feature list existed only in the evidence node and on each
version, so the fallback that types a column arriving entirely null — the one
whose own docstring says Iceberg refuses the write without it — read a key that
did not exist and returned an empty map every time it was called. Additive,
nullable-with-default, so `run_maya_web.py --repair-schema` picks it up on an
existing database.

**This is the largest-blast-radius change in the diff and the one I would hand
back first.** See §10.

### Documentation and the QA pack — four files, no product code

| File | Prompting case | What changed |
|---|---|---|
| `docs/QA/qa_setup.py` | QA-B1, QA-B2, QA-B3, QA-133/QA-134 | version before tier; creates the six accounts the cheatsheet publishes; coefficients moved to `parameter_schema`; `tier_once()` for idempotence |
| `docs/QA/qa-setup.sh` | same | the same four changes in the bash twin |
| `docs/QA/README.md` | QA-B2, QA-134 | the account table gains `a.mehta` and `d.raman`; both kernel blocks gain `parameter_schema`; the section 4 note now names the refusal the mistake produces |
| `tools/ops/backup.py`, `tools/ops/restore.py` | QA-B7 | two refusals stop naming `python -m tools.ops.verify`, which has never existed, and name `GET /api/v1/evidence/chain` instead |

### Test and tooling files

| File | What changed |
|---|---|
| `tests/test_recertification.py` | +8 tests (D-1, D-2) |
| `tests/test_api_operations.py` | +3 tests (D-3) |
| `tests/test_api.py` | +9 tests (D-4, D-5) |
| `tests/test_authz.py` | +3 tests (D-6) |
| `tests/test_features.py` | +3 tests (D-7) |
| `tests/test_backup_restore.py` | +2 tests (D-8) |
| `tests/test_qa_pack.py` | +10 tests (D-9…D-12) |
| `openapi.lock.json` | `spec_lock.py --update` — one path added, `/api/v1/worklist`; goes with D-5 |
| `pyproject.toml` | `S310` added to the `docs/QA/*.py` ignore list, for the reason `tools/soak/*.py` already has it: `qa_cases.py` drives a running instance over HTTP on purpose. Goes with `qa_cases.py` |
| `docs/QA/qa_cases.py` | **new.** The 314 cases, runnable, with stable IDs |

### Nothing else was touched

No change was made to `core/lifecycle/`, `core/execution/`, `core/risk/`,
`core/evidence/`, `db/schema/immutable.py`, or any refusal code, status mapping
or permission definition. `routes/base.py` `STATUS` is unchanged: D-4 reuses the
existing `validation_failed`, so the refusal taxonomy and
`tests/test_refusal_discipline.py` are untouched.

---

## 10. What I recommend reverting

Ordered by how strongly I would hand each one back. The **findings** are real
in every case and stay in this log whatever happens to the code; what is at
issue is whether the *change* belongs in a QA pass against a baseline with open
findings.

### Revert: the schema change (D-7)

`db/schema/features.py`, `db/schema/sqlite.sql`, `db/schema/postgres.sql`,
`db/repositories.py`, `core/features/views.py`, and
`tests/test_features.py::TestAViewKnowsWhatItDeclares`.

A column added to a shipped schema is not a QA fix. It needs a migration story
for deployed databases (`--repair-schema` handles it, but somebody should decide
that), it touches the feature-store write path, and its worst symptom is on
Iceberg — which this pass never ran. **The finding is solid and I would file it
as a defect: `ViewManager._dtypes` has never once returned a non-empty map, so
the null-column typing fallback described in its own docstring has never
executed.** That belongs on the backlog with the other uncalled controls, not in
a QA diff.

### Revert: the new endpoint (D-5)

`routes/lifecycle_routes.py`, `openapi.lock.json`, and
`tests/test_api.py::TestTheWorklistHasAnEndpoint`.

Adding an API path is a product decision. The defect — `maya worklist` calls
`GET /api/v1/worklist`, which does not exist — has two fixes, and I took the
larger one. The smaller is to delete the CLI subcommand, which is a one-line
change and forecloses nothing. Either way it should be somebody's decision
rather than a side effect of a QA pass.

### Consider reverting: the authorisation change (D-6)

`core/authz/policy.py` and
`tests/test_authz.py::TestWhatIsVisibleIsFilteredByPermissionAndNotOnlyByScope`.

I would defend this one on the merits — it closes a real gap, it is strictly
stricter, and the alternative (filtering in the dashboard route alone) leaves
the same hole in any future caller that forgets. But it changes the behaviour of
a function with 19 callers on the strength of one screen and the test suite, and
if you want the QA diff to be small, this is the third to go. If it stays, the
thing worth a second pair of eyes is whether any caller legitimately shows model
names to somebody without `model:read` — `ui_featureset_routes.py:518` (which
models a featureset feeds) is the one I would look at first.

### Keep: the three route fixes

`routes/principal_routes.py` (D-1, D-2), `routes/monitoring_routes.py` (D-3),
`routes/model_routes.py` (D-4).

Each is small, local, tied to a case that failed verbatim above, and each closes
a control that was either unreachable or absent. D-1 and D-2 together mean the
access-recertification workflow can be completed by somebody other than the
administrator, which it could not before; D-3 closes a scope leak; D-4 stops the
register accepting identifiers it cannot address. None of them changes a
refusal, a permission set or a status code.

### Keep: the QA pack and the documentation

`docs/QA/*`, `tools/ops/*.py`, `pyproject.toml`.

No product code. The pack did not complete against an empty instance and its
cheatsheet's sections 8 to 11 could not be followed; those are defects in a
deliverable handed to people outside the organisation, and the fixes are the
kind that should not wait for a baseline.

### If everything is reverted

The log stands on its own. §6 is 326 enumerated cases with expectations stated
in advance and answers recorded verbatim; §3 and §4 are 12 fixed and 13
unfixed findings with diagnoses; §5 is every promised refusal and whether it
fired. `docs/QA/qa_cases.py` re-runs the lot against any instance. That is the
case list for the real pass, and none of it depends on the remediation staying.
