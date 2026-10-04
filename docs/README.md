# docs

The specification is the source of truth for MAYA. Version 1.0.0 implements its spine and the model governance built on it; the README states exactly what is shipped, with the test that proves each capability ([*What's shipped*](../README.md#whats-shipped)), what is out of scope by decision, and what is not yet done ([*Status*](../README.md#status--read-this-first)).
The documents are grouped by what you are doing. Each folder is below, with what is in it.

```
docs/
  getting-started/   from nothing to MAYA running, with data of your own
  architecture/      how every component fits together: diagrams, code and screenshots
  developer/         how to extend and change each component: plugins, connectors, endpoints, tests
  reference/         the REST API, executed by its own tests
  design/            the specification, the implementation plan, and the decision records
  operations/        runbooks for when MAYA misbehaves
  quality/           what has been measured, and the audit of the specification against the code
  publications/      the research paper, the deck and the article
  CHANGELOG.md       what each release changed
```

The full reference for each part of MAYA — features, models, warrants, governance, the SDK,
operations — is in the product, under **Help**, and in [`maya/web/guides/`](../maya/web/guides/).

## Getting started — [`getting-started/`](getting-started/)

| Document | What it is |
|---|---|
| [`QUICKSTART.md`](getting-started/QUICKSTART.md) | **Start here.** From nothing to MAYA running, signed in, with demonstration data and a feature of your own, in about fifteen minutes; every step says what you should see and what to do if you don't |
| [`IDE.md`](getting-started/IDE.md) | **Running MAYA in PyCharm or IntelliJ IDEA**: the interpreter, a run configuration for the server and the web UI, debugging, tests, case studies and the gates |

## Architecture — [`architecture/`](architecture/README.md)

**How MAYA fits together.** The system map and the governed chain end to end, then one page per
component — web UI, REST API, SDK, services, persistence, the lake and storage, resolution, the
formula engine, workflow, warrants and custody, jobs and the scheduler, security,
observability, the AI gateway and documents, model risk governance, integrations and plugins —
each with its diagrams, the code that carries it, examples and screenshots taken from a running
MAYA. These pages explain how the parts are built and connect; the rules a user follows are in
the Help references they link to. Also in MAYA under **Help → Inside MAYA**.

## Developer guide — [`developer/`](developer/README.md)

**Extending and changing MAYA.** Setting up, the change workflow and its gates, and a guide per
extension: the plugin registry, source connectors, LLM providers, workflow checks, document
templates, model artifacts, REST endpoints, settings and YAML configuration, tables and the
schema, jobs, tests and gates, case studies, and the standalone SDK. Also in MAYA under
**Help → Inside MAYA**.

## Reference — [`reference/`](reference/)

| Document | What it is |
|---|---|
| [`API_GUIDE.md`](reference/API_GUIDE.md) | **Talking to MAYA over HTTP.** The REST API from first `curl` to a sealed execution warrant, with a small Python client, every convention (keys, paging, ETags, idempotency, jobs), every error and every endpoint. Each example is executed by `tests/test_api_guide.py` |
| [`authoring-reference.md`](../maya/web/guides/authoring-reference.md) | **What each designer expects.** The rules behind every authoring screen: a model's formula, its Python function (assignments and one `return`) and its Python artifact (a class `Model` with `fit(self, X, y, ctx)` and `predict(self, X, params, ctx)`, the import allowlist and the sandbox limits); features and their sources, rules and quality checks; feature sets; and both warrants, covenants included. The same page is in Help, and each screen's *What this needs* panel links to its section |

## Design — [`design/`](design/)

| Document | What it is |
|---|---|
| [`MAYA_Requirements_and_Design.md`](design/MAYA_Requirements_and_Design.md) | **The specification**, revision 2.8 (the notes for 2.2 to 2.8 are at its top, each marked where it lands). 30 sections: vision, personas, domain model, the four subsystems (features, feature sets, models, warrants), `maya_delta` and physical storage, authz, architecture, the UI, the API and SDK, engineering standards, the design read adversarially (§28), and the ten innovations (§29) |
| [`IMPLEMENTATION_PLAN.md`](design/IMPLEMENTATION_PLAN.md) | **How it gets built.** Milestones M0–M8 with executable exit criteria, each marked with what it delivered by 0.3.0 and what it did not; the 28-rung CI gate ladder and which rungs exist; the six one-way doors; and the decision register |
| [`design/adr/`](design/adr/README.md) | **Why it is built this way.** Twenty-eight architecture decision records: the package layout and working practice, the eight decisions and six further calls of §26.3, and the later decisions of revisions 2.2 and 2.3 and version 0.3 — each with its context, its cost, and the code and tests that carry it |

## Operations — [`operations/`](operations/)

| Document | What it is |
|---|---|
| [`operations/runbooks/`](operations/runbooks/README.md) | **What to do when it misbehaves.** Twenty operational procedures, the nine §20 requires to ship with the product among them — schema rebuild, moving between SQLite and PostgreSQL, `maya_delta` fallback, integrity drift, audit chain and custody, stuck jobs and pins, orphaned pin partitions, Delta small files, database failover, a suspended warrant, an SSO outage, a suspected sandbox escape, quota exhaustion, default-password remediation, the restore drill, and the governance ones: restated data under a live model, periodic review and expiry, a governance backlog, the AI gateway — each with symptoms, diagnosis commands, steps, verification and limits |

## Quality — [`quality/`](quality/)

| Document | What it is |
|---|---|
| [`BENCHMARKS.md`](quality/BENCHMARKS.md) | **What has been measured**, against §3 and §24.3: the machine, how to reproduce each run, every number from the unedited result files in [`benchmarks/`](quality/benchmarks/), and what has not been measured |
| [`quality/audit/`](quality/audit/spec-audit-2026-09-19.md) | **What was not built on 2026-09-19.** Revision 2.3 read against the code, requirement by requirement: counts by class, the gaps ranked by what they cost a user, and the places the specification contradicts itself (now marked *Revision 2.4*). Every ranked gap has since been closed but for one clause of gap 14, and the header at its top says which; the per-requirement tables below it are a snapshot of that day and have not been re-walked |

## Publications — [`publications/`](publications/)

| Document | What it is |
|---|---|
| [`publications/research/`](publications/research/) | **The research paper**, *Models as Parametric Kernels: An Order, an Operator and a Polynomial* — [PDF](publications/research/models-as-parametric-kernels.pdf), [LaTeX source](publications/research/models-as-parametric-kernels.tex), and an [article version](publications/research/models-as-parametric-kernels-article.md). The formal account MAYA came out of, rewritten against 1.0.0 with a new section on the governance judgements (materiality, review, monitoring, champion and challenger, fairness, black boxes and LLM applications): every claim is marked with the module and test that carry it, or as not in the system. CC BY-NC-ND 4.0 ([`research/LICENSE`](publications/research/LICENSE)); everything else here is proprietary |
| [`MAYA-Model-Management-Formalism-and-System-Design.pptx`](publications/MAYA-Model-Management-Formalism-and-System-Design.pptx) | **The deck**, 72 slides in nine parts: why model governance fails and what SR 11-7 and SS1/23 ask; the vocabulary from nothing; the lifecycle end to end; the governance layer (findings, materiality, periodic review, monitoring, champion and challenger, fairness, the supervisory inventory); models beyond formulas (black boxes, MLflow and SageMaker imports, what MAYA does beside an ML platform, LLM applications); the formal core; how it runs; fifteen case studies with six in depth; and what is measured and not done. Generated by [`tools/deck/`](../tools/deck/GUIDE.md) and checked for layout by `tests/test_deck_geometry.py` |
| [`articles/medium/`](publications/articles/medium/README.md) | **The Medium article** on MAYA's design, with its six diagrams (generated by `diagrams.py` beside it) |

## Release notes

| Document | What it is |
|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | **What each release changed**, as narrative; the version itself lives in `maya/core/version.py` |

## Revision 2.1 — what changed, 2026-09-17

The eight open decisions of §26.3 are **closed**, and six further calls are folded into
the sections that carry them:

| Call | Section |
|---|---|
| No database migrations — two generated `.sql` files, everything through SQLAlchemy | §14.3 |
| `maya_delta`: native `deltalake` preferred, MAYA's own pure-Python Delta as fallback | §7.4 |
| Windows, Linux and macOS as equal first-class platforms — *since amended by the owner's decision: only Linux is exercised* ([ADR-014](design/adr/ADR-014-platforms.md)) | §24.5 |
| Bootstrap 5 + jQuery, vendored, on a Harvard Crimson visual system | §16.6 |
| The universal table contract — every table paginated, searchable, sortable | §16.7 |
| Workflow authored and managed in the UI; YAML as a projection, not a second authority | §10.6 |
| One startup script, `run_maya_web.py` | §24.5 |

> **The `.docx` and `.pdf` beside the specification are renderings of the Markdown**, which
> is the authority. `python tools/docs/build_spec.py` rebuilds both (pandoc and Tectonic;
> the diagrams are drawn in headless Chrome) and is rerun whenever the Markdown changes.
> They were last rebuilt at revision 2.8.

## What goes here next

`design/adr/` and `operations/runbooks/` are written (above). The decision records were due in M0 and arrived
after 0.3.0; specification §26.3 and plan §4 remain the registers they expand. All nine of
the procedures §20 asks for are now written, and eleven more beside them;
[their index](operations/runbooks/README.md) names what they still do not reach.
Still to come: per-subsystem design notes, beside the specification in `design/`.

> The research paper (`publications/research/`) and the deck were restored from the
> previous build and rewritten since; `NOTICE` and
> `publications/research/LICENSE` resolve. The deck is regenerated with
> `python tools/deck/build.py` (see [`tools/deck/GUIDE.md`](../tools/deck/GUIDE.md)) and the
> PDF with `tectonic` from `publications/research/models-as-parametric-kernels.tex`.

## The previous build

Deleted on 2026-09-17. Not gone — unreferenced. It is the parent of the commit that
emptied this repository:

```bash
git show 21ab4d0 --stat            # the last commit of the previous build
git checkout 21ab4d0 -- <path>     # bring one file back
```
