# Contributing to MAYA

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

This is a governance register. Almost everything that makes it one is a
**refusal** — a place where the platform declines to answer, or answers more
narrowly than somebody hoped. Most of the rules below exist because a refusal
was quietly turned into a pass, once, and nobody noticed for a release.

---

## Before you push

Five gates, in this order. They take about four minutes together and they are
the same five CI runs.

```bash
.venv/bin/python -m pytest -q -p no:randomly     # 1. the suite
.venv/bin/ruff check .                           # 2. lint, including bandit's S rules
.venv/bin/python tools/ci/typecheck.py           # 3. mypy over the gated modules
.venv/bin/python tools/ci/spec_lock.py           # 4. the API's shape has not moved
.venv/bin/python tools/ci/scan_secrets.py        # 5. nothing committed that should not be
```

Two of these need a flag when you meant to change what they check:

| | When |
|---|---|
| `tools/ci/spec_lock.py --update` | you added, removed or reshaped a route. **Read the diff**: a path you did not expect to move is usually a route registered in the wrong place |
| `tools/ci/render_schema.py` | you changed `db/schema/*.py`. The `.sql` files are **generated**; editing them by hand is a divergence nothing will catch until a deployment |

`-p no:randomly` is not optional advice. The suite is order-randomised by
default, and a failure you cannot reproduce is a failure you will talk yourself
out of.

### Two more, when the machine has them

```bash
MAYA_TEST_POSTGRES=postgresql://... pytest tests/test_row_level_security.py
MAYA_TEST_DOCKER=1                  pytest tests/test_deployment.py
```

Both **skip loudly** without the dependency, and the skip message says why. That
is deliberate: a green suite that silently did not run the cross-entity read is
exactly the assurance finding H-5 objected to.

---

## The discipline tests, and why they will fail you

Several tests do not test a feature. They walk the source and hold a rule. Each
exists because the rule had already been broken once, and each will fail on a
change that looks entirely reasonable.

| Test | The rule, and what it feels like when it fires |
|---|---|
| `test_refusal_discipline` | Every coded refusal maps to a status saying **who must act**. It will fail if you build a code with an f-string — `f"cost_{field}_required"` is invisible to a scanner that walks for literals, and the caller gets a bare 400 from the very thing meant to prevent that. Write the literal raise sites; the duplication is the point |
| `test_logging_discipline` | Every `except` logs what it recovered from. None is bare, none is only `pass` |
| `test_atomicity_discipline` | A write and its evidence node happen inside one `with evidence.recording()`. A crash between them leaves a governance act unrecorded |
| `test_scope_discipline` | A per-model permission check passes `model=`. One that forgot the model permits everything |
| `test_schema_discipline` | One typed declaration renders to both dialects identically, the checked-in `.sql` is not stale, and **every table carrying a `model_id` is read by the reference index** — otherwise deleting a model orphans rows while the dependency screen says nothing refers to it |
| `test_documentation_counts` | Every number claimed in prose is recounted from the code. It reads `docs/`, `content/`, the `.tex` paper, the README, `config/application.yaml` **and every Python docstring** |
| `test_size_discipline` | No source file over 1,500 lines, warning at 90% |
| `test_ui_reachability` | No orphaned page. A screen nobody can click to is not built, whatever the route table says |
| `test_ui_accessibility` | Every control has a `for`/`id`; every text pair clears AA in every theme; one `<h1>` per page |
| `test_deck_geometry` | No slide has overlapping or escaping content |
| `test_laws` | The foundational laws, run as property tests, with the three that do not run **named in the file** |

---

## Two mistakes this repository keeps making

Both have happened four times. They are here so the fifth is yours knowingly.

**A refusal code assembled at runtime.** Four nearly identical refusals invite an
f-string, and an interpolated code is invisible to the scanner. The fix reads as
duplication to anybody who does not know why.

**A route appended outside the function that registers it.** `routes/*.py`
register endpoints inside `register()`. Appending a block to the end of the file
puts it inside whatever method is last — sometimes after a `return`. Ruff catches
it when the block references an out-of-scope local; when it does not, the routes
simply **do not exist**, and the symptom is a 404 that looks like a path typo.
`spec_lock.py` catches this now.

---

## What a change is expected to carry

A feature is not finished when it works.

| | |
|---|---|
| **Tests** | including at least one that asserts the **refusal**, in its own words. A feature with only happy-path tests is a feature whose refusals are decorative |
| **A route** | if a person or a service needs it. `routes/base.py` must map any new refusal code |
| **The SDK** | `sdk/python/maya_sdk/` and its README row. A capability the SDK cannot reach reads to a new joiner as *the platform cannot do this* |
| **A screen, or a reason there is none** | a capability nobody can click to is one nobody uses |
| **The requirement row** | `docs/03-requirements.md`. Say what it *refuses*, not just what it does |
| **The design** | `docs/14-detailed-design.md`, and `docs/12`'s component table |
| **Help** | `content/help/`. The product documentation is part of the work, not an afterthought |

---

## How to write it

The prose in this repository is unusually heavy, and that is a decision rather
than an accident. Three rules:

**Say why, not what.** The code says what. A comment repeating it is noise that
goes stale. A comment explaining why the obvious alternative is wrong is the
thing nobody can reconstruct.

**Name the failure the rule prevents.** *"A partial ingest produces a precision
figure grading something other than the scanner"* survives a refactor. *"Validate
the input"* does not.

**When something is not built, say which kind of not-built it is.** A gap closes
with effort. A **refusal** closes only by making something else untrue, and the
sentence should name that thing. A reader takes a list of absences for a backlog
unless told otherwise, and several of this platform's would make it worse if
they were closed.

---

## Committing

Build on `develop`, one commit per milestone, then merge to `main` and push
both. A commit message here is expected to explain the *reasoning* — what was
wrong, what was considered, and what the fix costs. The git history is the only
record of the alternatives that were rejected.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
