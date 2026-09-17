# docs

The specification is the source of truth for MAYA, and the code does not exist yet.
Read in this order.

| Document | What it is |
|---|---|
| [`MAYA_Requirements_and_Design.md`](MAYA_Requirements_and_Design.md) | **The specification.** 30 sections: vision, personas, domain model, the four subsystems (features, feature sets, models, warrants), storage, authz, architecture, the UI, the API and SDK, engineering standards, the design read adversarially (§28), and the ten innovations (§29). Also published as `.docx` and `.pdf` — the same content, for people who want to mark it up |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | **How it gets built.** Milestones M0–M7 with executable exit criteria, the CI gate ladder, the three one-way doors, and the eight decisions that block Phase 1 |

## What goes here next

`adr/` for numbered architecture decisions (the eight open decisions each become one
when answered), `design/` for per-subsystem design notes, `runbooks/` for the
operational procedures §20 requires to ship *with* the product, and `research/` if
the paper returns.

> `NOTICE` still references `docs/research/LICENSE`, which was removed with the rest
> of the previous build. Restore it with the paper, or amend `NOTICE`.

## The previous build

Deleted on 2026-09-17. Not gone — unreferenced. It is the parent of the commit that
emptied this repository:

```bash
git show 21ab4d0 --stat            # the last commit of the previous build
git checkout 21ab4d0 -- <path>     # bring one file back
```
