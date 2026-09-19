# docs

The specification is the source of truth for MAYA. Version 0.1.0 implements its spine; the README states exactly what is and is not shipped.
Read in this order.

| Document | What it is |
|---|---|
| [`MAYA_Requirements_and_Design.md`](MAYA_Requirements_and_Design.md) | **The specification**, revision 2.1. 30 sections: vision, personas, domain model, the four subsystems (features, feature sets, models, warrants), `maya_delta` and physical storage, authz, architecture, the UI, the API and SDK, engineering standards, the design read adversarially (§28), and the ten innovations (§29) |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | **How it gets built.** Milestones M0–M8 with executable exit criteria, the 28-rung CI gate ladder, the six one-way doors, and the decision register |

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

> **The `.docx` and `.pdf` beside the specification were exported before revision 2.1 and
> are behind it.** The Markdown is the authority. They were not regenerated because they
> carry rendered diagram images from a toolchain that is not wired up here, and producing
> a degraded file under the same name is exactly the *builds, validates, and is wrong*
> failure this project is built to avoid. Regenerate them deliberately, with the
> toolchain that made them.

## What goes here next

`adr/` for numbered architecture decisions — the fourteen calls in plan §4 become
ADR-001 onward during M0. `design/` for per-subsystem design notes, `runbooks/` for the
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
