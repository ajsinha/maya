# docs

The specification is the source of truth for MAYA. Version 0.3.0 implements its spine; the README states exactly what is shipped, with the test that proves each capability ([*What's shipped*](../README.md#whats-shipped)), what is out of scope by decision, and what is not yet done ([*Status*](../README.md#status--read-this-first)).
Read in this order.

| Document | What it is |
|---|---|
| [`MAYA_Requirements_and_Design.md`](MAYA_Requirements_and_Design.md) | **The specification**, revision 2.3 (the notes for 2.2 and 2.3 are at its top, each marked where it lands). 30 sections: vision, personas, domain model, the four subsystems (features, feature sets, models, warrants), `maya_delta` and physical storage, authz, architecture, the UI, the API and SDK, engineering standards, the design read adversarially (§28), and the ten innovations (§29) |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | **How it gets built.** Milestones M0–M8 with executable exit criteria, each marked with what it delivered by 0.3.0 and what it did not; the 28-rung CI gate ladder and which rungs exist; the six one-way doors; and the decision register |
| [`BENCHMARKS.md`](BENCHMARKS.md) | **What has been measured**, against §3 and §24.3: the machine, how to reproduce each run, every number from the unedited result files in [`benchmarks/`](benchmarks/), and what has not been measured |
| [`CHANGELOG.md`](CHANGELOG.md) | **What each release changed**, as narrative; the version itself lives in `maya/core/version.py` |

## Revision 2.1 — what changed, 2026-09-17

The eight open decisions of §26.3 are **closed**, and six further calls are folded into
the sections that carry them:

| Call | Section |
|---|---|
| No database migrations — two generated `.sql` files, everything through SQLAlchemy | §14.3 |
| `maya_delta`: native `deltalake` preferred, MAYA's own pure-Python Delta as fallback | §7.4 |
| Windows, Linux and macOS as equal first-class platforms | §24.5 |
| Bootstrap 5 + jQuery, vendored, on a Harvard Crimson visual system | §16.6 |
| The universal table contract — every table paginated, searchable, sortable | §16.7 |
| Workflow authored and managed in the UI; YAML as a projection, not a second authority | §10.6 |
| One startup script, `run_maya_web.py` | §24.5 |

> **The `.docx` and `.pdf` beside the specification are renderings of the Markdown**, which
> is the authority. `python tools/docs/build_spec.py` rebuilds both (pandoc and Tectonic;
> the diagrams are drawn in headless Chrome) and is rerun whenever the Markdown changes.
> They were last rebuilt at revision 2.3.

## What goes here next

`adr/` for numbered architecture decisions — the fourteen calls in plan §4 were to
become ADR-001 onward during M0. They have not been written; until they are, plan §4
and specification §26.3 are the register. `design/` for per-subsystem design notes, `runbooks/` for the
operational procedures §20 requires to ship *with* the product, and `research/` when the
paper is rewritten.

> The research paper and the presentation decks are **deferred by decision**, to be
> rewritten against this specification. `NOTICE` still references
> `docs/research/LICENSE`, which went with the previous build — restore it with the
> paper, or amend `NOTICE` then.

## The previous build

Deleted on 2026-09-17. Not gone — unreferenced. It is the parent of the commit that
emptied this repository:

```bash
git show 21ab4d0 --stat            # the last commit of the previous build
git checkout 21ab4d0 -- <path>     # bring one file back
```
