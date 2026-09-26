"""
The deck, as data. Parts 6 and 7: the formal core, and how MAYA runs.

One deck split across four modules only to keep each file under the repository's file-size gate; read them in order (see GUIDE.md).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "6",
        "title": "The formal core",
        "sub": "Why the facts above can be derived rather than typed. A model is a kernel over typed "
        "inputs and a parameter object; from that shape follow what can stand in for what, when a "
        "value was knowable, and what a result depends on. Proofs are in the research paper; this "
        "part gives the engineer's view.",
        "points": [
            "Four facts that rot",
            "Approval as a relation",
            "The point-in-time read",
            "Reproducibility by content",
            "Where a machine may do the work",
        ],
    },
    {
        "kind": "table",
        "kicker": "The problem with forms",
        "title": "Four declared facts, and how each one rots",
        "intro": "These are not hypothetical. Each is a field that exists in registers now, each is "
        "filled in by a person, and each decays in a way that is invisible from the field "
        "itself — which is what makes a declared fact worse than an absent one.",
        "rows": [
            ["", "The declaration", "How it rots", "What the damage looks like"],
            [
                "D1  Kind",
                "What sort of artefact this is: pricer, scorecard, network, rule set",
                "Typed once, at registration, by whoever was filling the form",
                "A monitor that cannot detect anything runs for two years and reads as coverage",
            ],
            [
                "D2  Fit",
                "Whether this data, or this replacement version, fits where the last one did",
                "Implemented four times in four code paths that drift apart",
                "They drift towards permitting more, because nobody files a bug against a check that "
                "wrongly allows",
            ],
            [
                "D3  Currency",
                "What a training row could have known at the moment it describes",
                "A convention in whoever wrote the query, applied unevenly",
                "Look-ahead that improves every metric it corrupts, so nothing asks to be "
                "investigated",
            ],
            [
                "D4  Support",
                "What a conclusion rests on: which tests, which approvals, which data",
                "A log of what happened, which is not the same as a derivation",
                "“Is this still supported?” cannot be answered without a person reading the log",
            ],
        ],
        "col_w": [1.4, 3.3, 3.2, 3.7],
        "note": "Paper §1. The claim of this part is narrow: each of these four is derivable from "
        "structure that has to exist anyway, and a derived fact cannot be typed wrong, cannot "
        "drift, and cannot disagree with the object it describes.",
    },
    {
        "kind": "table",
        "kicker": "D2 · Fit",
        "title": "Four questions that were one question",
        "intro": "Each of these is asked somewhere in a model register, and in the registers we have "
        "examined each has a code path of its own: a variance routine, a slot loop, a contract "
        "refinement check — and for the dependency edge, frequently nothing at all.",
        "rows": [
            ["Where it is asked", "What it actually asks", "The comparison"],
            [
                "A replacement version",
                "May this version stand where the incumbent stood?",
                "Its inputs accept at least what the incumbent's did, and its outputs still provide "
                "what the incumbent's provided",
            ],
            [
                "Binding data to a model",
                "Does this feature set provide what the model declares it reads?",
                "The set's schema can stand in for the model's input contract",
            ],
            [
                "A dependency edge",
                "Does what the source produces arrive where the target reads it?",
                "The source's output schema can stand in for the target's input contract",
            ],
            [
                "One feature set, two models",
                "Can a single feature set serve both of these?",
                "The set can stand in for the greatest lower bound of the two contracts",
            ],
        ],
        "col_w": [2.4, 4.2, 5.0],
        "note": "Paper §3.1 and §3.5. Four implementations of one relation are four opportunities to "
        "disagree — predictably in the direction of permitting more, because a check that "
        "wrongly refuses is reported within the hour and a check that wrongly allows is not "
        "reported at all.",
    },
    {
        "kind": "bullets",
        "kicker": "The order",
        "title": "A can stand in for B: one relation, written down once",
        "items": [
            (
                "When one field accepts another",
                "Same datatype; nullable if the other is; a lower bound no greater and an upper bound "
                "no less, an absent bound being the widest there is. A can stand in for B when every "
                "field B declares is present in A at a field that accepts it.",
            ),
            (
                "Extra fields are free",
                "A may carry fields B does not. Nobody has to look at them, so a richer provider is "
                "always admissible — which is what makes the relation usable in a bank, where the "
                "feature set serving one model always carries more than that model reads.",
            ),
            (
                "Being fussier is not free",
                "Each shared field must accept at least what B's accepted. A replacement that rejects "
                "an input its predecessor took is a replacement that breaks a caller: somebody was "
                "relying on the old tolerance, and nothing recorded that they were.",
            ),
            (
                "And the direction is the one nobody guesses",
                "“Refinement” suggests narrowing, and a subtype is narrower in what it denotes. But a "
                "schema here is the set of inputs a slot will accept, and standing in for something "
                "means accepting at least what it accepted — so wider acceptance is admissible and "
                "narrower regresses. The two readings of “narrower” are easy to hold at once and "
                "impossible to hold consistently, and an order stated in the intuitive direction "
                "admits exactly the replacements that break callers.",
            ),
        ],
        "note": "Paper §3.2. This is why it is worth writing down as an order with a stated direction "
        "rather than as a rule of thumb: the failure a rule of thumb produces here is silent, "
        "and it is in the permissive direction.",
    },
    {
        "kind": "bullets",
        "kicker": "D3 · Currency",
        "title": "The point-in-time read, stated as an operator",
        "intro": "Part 2 gave the rule in words: the latest fact that was both true by the decision date "
        "and known by the decision date. Written as an operator it acquires two properties a "
        "convention cannot have — it can be reasoned about, and it can be wrong in a way "
        "somebody notices.",
        "items": [
            (
                "The admissible set",
                "For a label time — the moment the decision was taken — and an observation time at "
                "which the assembly is run, the records admissible for a row are those whose event "
                "time is at or before the label, and whose ingest time is at or before the earlier of "
                "the label and the observation.",
            ),
            (
                "The read",
                "The latest admissible record, by event time and then by ingest time. It is undefined "
                "when nothing is admissible, rather than empty: a row for which nothing could have "
                "been known is a different fact about the world from a row whose value was zero, and "
                "an operator returning the same thing for both would lose it.",
            ),
            (
                "Both bounds are present because they refuse different things",
                "The event bound is what the world had done by the moment of the decision. The ingest "
                "bound is what could have been known at that moment. A read with one clock answers a "
                "question nobody asked — what do we think now about what was true then — and answers "
                "it without saying so.",
            ),
            (
                "And the ingest bound is the earlier of the two, not the observation",
                "The observation time is a single date for a whole assembly and is usually far later "
                "than any individual label. Bounding knowledge by the assembly date admits, for every "
                "early row, everything learned between that row's own decision date and the moment "
                "somebody pressed the button.",
            ),
        ],
        "note": "Paper §5.2. That last bound is one character of the definition and it is the whole "
        "guarantee; its omission is invisible in every test that does not restate a fact.",
    },
    {
        "kind": "table",
        "kicker": "Four properties",
        "title": "And the fourth one is reproducibility",
        "intro": "Each is elementary to prove and none is ornamental. Together they are the difference "
        "between a read that is correct and a read that is stable — and the fourth makes "
        "reproducibility a property of the operator rather than of the discipline of whoever "
        "re-runs it.",
        "rows": [
            ["Property", "What it says", "Why it is worth having"],
            [
                "Idempotent",
                "Reading the record it just returned returns that record",
                "A cached row and a recomputed row agree, so the operator may be applied twice without "
                "an answer moving",
            ],
            [
                "Commutes with projection",
                "Dropping non-clock columns before or after the read gives the same row",
                "Admissibility depends on the two clocks alone, so a narrower query is the same query "
                "rather than a cheaper approximation of it",
            ],
            [
                "Monotone in the observation time",
                "A later observation admits a superset",
                "Nothing that was knowable stops being knowable. It is monotonicity of the set and not "
                "of the chosen row, which is why the fourth property has to be separate",
            ],
            [
                "Saturating at the label",
                "At every observation at or after the label, the admissible set is the same set",
                "A row assembled at any time after its label is the row that would have been assembled "
                "at the label, whatever arrived in between. This is reproducibility, and it is what "
                "the earlier-of-the-two bound buys",
            ],
        ],
        "col_w": [2.5, 4.0, 5.1],
        "note": "Paper §5.2. Without saturation a re-run quietly improves on the original, and the "
        "numbers then agree with nothing — including themselves. Nobody notices, because the "
        "second set is better by every measure that gets looked at.",
    },
    {
        "kind": "bullets",
        "kicker": "One layer across",
        "title": "The ingest clock of a derived feature, as arithmetic that cannot be forgotten",
        "items": [
            (
                "The rule, as arithmetic",
                "The moment a derived feature became knowable is the latest ingest time among the "
                "base features it reads. Stated that way it is a rule, and a rule can have exceptions "
                "somebody forgets.",
            ),
            (
                "The rule, as a consequence of the derivation",
                "It is the derivation itself, evaluated with each base feature replaced by its own "
                "ingest time. The upgrade is not cosmetic: every route to the number now goes through "
                "the same object, so there is no exception to forget.",
            ),
            (
                "What does this rest on?",
                "The base features the derivation actually reads — deliberately not the transitive "
                "ancestor set, because the two answer different questions. The ancestor walk returns "
                "every ancestor, derived ones included, which is the right answer to what breaks if "
                "this changes. The base features are the right answer to what data this ultimately "
                "reads.",
            ),
            (
                "Does it touch the label?",
                "Whether the target's own feature appears among those base features. A feature "
                "derived from a derivation of the target is still the target, so leakage detection "
                "becomes a membership test rather than a graph walk with a depth limit and a hope.",
            ),
        ],
        "note": "Paper §6.2. Two routes to one answer are worth having only while they agree, so the "
        "identity between them is asserted rather than assumed.",
    },
    {
        "kind": "split",
        "kicker": "The same boundary, from the other side",
        "title": "Where a machine may do the work",
        "intro": "If an answer can be checked it matters little what produced it: a wrong one is caught "
        "and discarded, and the only cost is wasted effort. If it cannot be checked, then "
        "trusting the answer is trusting the producer, and no amount of process changes that. "
        "So the useful question is not whether the generator is good enough but whether there "
        "is a check — and there is one exactly where the fact derives from structure.",
        "left": {
            "head": "A check exists, so an error costs throughput",
            "items": [
                (
                    "Encode a regulatory regime",
                    "An encoding either keeps truth invariant under translation or it does not. "
                    "Expensive expert work becomes cheap proposal and mechanical verification, "
                    "and the expert adjudicates rather than authors.",
                ),
                (
                    "Bind data to a model, or wire two models",
                    "Both are the one order of D2. A refusal names the slot that is missing or "
                    "the one that narrowed.",
                ),
                (
                    "Assemble fitting evidence, and cite it",
                    "The point-in-time operator, recomputed by a route that does not reuse the "
                    "one that assembled the rows; and a citation checked by evaluating the "
                    "derivation in true-or-false arithmetic.",
                ),
            ],
        },
        "right": {
            "head": "No check exists, so the answer is its producer",
            "items": [
                (
                    "Choose the tiering rule",
                    "It constitutes the standard, so there is nothing independent for it to be "
                    "checked against.",
                ),
                (
                    "Conclude a validation, or accept residual risk",
                    "Correctness here is not a property of the text. It is an exercise of "
                    "authority, and the boundary is drawn by the mathematics rather than by "
                    "risk appetite — which is worth scrutinising in proportion to how "
                    "comfortable a conclusion it is.",
                ),
                (
                    "And one honest exception",
                    "Sampled agreement between a stated formula and an implementation can "
                    "refute the implementation and can never certify it, so however many "
                    "samples it draws it is not a check in this sense. A report saying so in "
                    "its first four words is worth more than one that passes quietly.",
                ),
            ],
        },
        "note": "Paper §9. MAYA's assistant sits entirely in the left column: it proposes, it never "
        "approves, it never blocks, and it never writes to a sealed object.",
    },
    {
        "kind": "divider",
        "num": "7",
        "title": "How it runs",
        "sub": "One platform reached six ways, one database at a time, a sandbox whose strength is "
        "verified rather than assumed, and an audit chain anchored outside the database.",
        "points": [
            "Six places, one set of objects",
            "The REST API",
            "Policy as data",
            "The audit chain",
            "Storage",
            "The sandbox",
            "Connectors",
        ],
    },
    {
        "kind": "cards",
        "kicker": "Where the work happens",
        "title": "Six places, and the same objects visible from each",
        "cols": 3,
        "cards": [
            (
                "WORKBENCH",
                "Author and rehearse",
                "Define a feature, upload or pull its data, preview a resolution before it is pinned, "
                "build a feature set, open a workspace to try a change safely.",
            ),
            (
                "CATALOG",
                "Find and compare",
                "Features and feature sets with their versions, pins, lineage and quality history; "
                "compare two versions; download a pin as tabular or wide.",
            ),
            (
                "MODELS",
                "Register and review",
                "The kernel wizard, the mathematics, the code artifact and its ladder report, the "
                "specification document, the semantic diff between two versions.",
            ),
            (
                "WARRANTS",
                "Licence and verify",
                "Draw a training warrant, fetch the data, upload dials, seal an execution warrant, "
                "export a bundle — and verify a bundle somebody hands you.",
            ),
            (
                "INBOX",
                "Decide",
                "The review queue, scoped to what you may actually see, with what is overdue, what is "
                "blocked and by which named check.",
            ),
            (
                "ADMIN",
                "Operate",
                "Namespaces and grants, users and sign-on, sources, jobs, events and webhooks, "
                "storage, retention, custody anchors, and a health page naming every resolved seam.",
            ),
        ],
        "note": "maya/web/routes/: workbench.py, catalog.py, models.py, warrants.py, home.py, admin.py, "
        "lineage.py, workflow.py, workspaces.py. Every page is rendered in "
        "tests/test_web.py::test_every_page_renders, and the journeys through them in "
        "tests/test_web_journeys.py.",
    },
    {
        "kind": "split",
        "kicker": "Four surfaces, one contract",
        "title": "Whatever you drive it with, it is the same platform",
        "left": {
            "head": "The surfaces",
            "items": [
                (
                    "The web interface is an SDK client",
                    "It has no private path to the services; a gate fails the build if anything "
                    "under the web tier imports past the SDK.",
                ),
                (
                    "The REST API",
                    "246 endpoints, each with an SDK method and each method with an endpoint, "
                    "checked both ways by a gate.",
                ),
                (
                    "The Python SDK",
                    "Synchronous and asynchronous, with record and replay for tests, and an "
                    "offline mode that serves a bundle and refuses everything the bundle does "
                    "not hold.",
                ),
                (
                    "The command line",
                    "The whole spine, including bundle export and offline verification.",
                ),
            ],
        },
        "right": {
            "head": "What every screen owes you",
            "items": [
                (
                    "Every table pages, searches and sorts",
                    "Rows per page remembered per table per user, sort applied to the whole "
                    "result set rather than the visible page, export honouring the active "
                    "filter. A crawler gate refuses any table not drawn by the one macro.",
                ),
                (
                    "Large tables page from the server",
                    "Signed cursors, the same controls, and an exact total counted in the "
                    "database under row-level authorization.",
                ),
                (
                    "Search is MAYA's own index",
                    "Ranked, prefix-matched, every term required, filtered by read permission, "
                    "kept current inside the writing transaction. p95 0.16 s over 100,000 "
                    "objects.",
                ),
                (
                    "Status is never colour alone",
                    "Every pill carries a glyph and a word, and the palette is recomputed by a "
                    "gate against contrast floors.",
                ),
            ],
        },
        "note": "tools/ci/table_contract.py, sdk_parity.py, contrast.py; "
        "tests/test_web.py::test_web_imports_only_the_sdk; "
        "tests/test_browser.py::test_a_server_paged_table_pages_searches_and_sorts; "
        "docs/BENCHMARKS.md for the search figure.",
    },
    {
        "kind": "split",
        "kicker": "The API",
        "title": "Everything the screen does is a documented HTTP call",
        "intro": "The web UI, the Python SDK and the CLI all use the same 246 endpoints under /api/v1. "
        "docs/API_GUIDE.md walks them from a first curl to a sealed execution warrant, and the "
        "test suite executes every example in it.",
        "left": {
            "head": "Conventions",
            "items": [
                (
                    "Credentials",
                    "A session token, or an API key narrowed to roles, namespaces, actions and "
                    "networks.",
                ),
                (
                    "Problem documents",
                    "Every failure has a machine-readable type and a sentence saying what to do.",
                ),
                (
                    "Cursor paging, ETags",
                    "Conditional reads answer 304; guarded writes refuse a stale If-Match.",
                ),
            ],
        },
        "right": {
            "head": "Safe to retry",
            "items": [
                (
                    "Idempotency keys",
                    "A retried pin returns the original pin and job, before and after it seals.",
                ),
                ("Jobs", "Slow work answers 202 and a job to poll or stream."),
                (
                    "Parity, enforced",
                    "A gate fails the build if an endpoint lacks an SDK method or a way to "
                    "reach it from the UI.",
                ),
            ],
        },
    },
    {
        "kind": "split",
        "kicker": "Workflow",
        "title": "Policy is data, and the policy itself is governed",
        "left": {
            "head": "How a transition is described",
            "items": [
                (
                    "Eight states, six object types",
                    "draft, in_review, changes_requested, approved, published, deprecated, "
                    "retired, withdrawn — over every governed kind: features, feature sets, models, "
                    "parameter sets and both warrants.",
                ),
                (
                    "Checks and approvals by name",
                    "A transition lists the states it leaves, the capability it needs, the named "
                    "checks to pass, and the approvals required as a role and a count — with a "
                    "count that may apply only in production.",
                ),
                (
                    "Refused at edit time",
                    "An unreachable state, an unsatisfiable approval or an unknown condition is "
                    "rejected when the policy is saved, so nothing fails open at approval "
                    "time.",
                ),
            ],
        },
        "right": {
            "head": "The awkward cases",
            "items": [
                (
                    "Segregation of duties",
                    "Three levels, shipped as small-team, standard and regulated presets; under "
                    "the strictest, nobody who created, submitted or updated an object may "
                    "approve it.",
                ),
                (
                    "Break-glass",
                    "Administrators only, a written reason of real length, marked forced on the "
                    "record, audited as its own action, and the owner told whether or not they "
                    "subscribed.",
                ),
                (
                    "Delegation and escalation",
                    "Only an approver may delegate, never to themselves, within dates; the "
                    "approval records whose behalf it was on. Five days in review is the "
                    "shipped service level, swept hourly.",
                ),
            ],
        },
        "note": "maya/workflow/ and maya/security/roles.py; tests/test_workflow_matrix.py, "
        "tests/test_delegation.py. The YAML projection round-trips byte-identically for whoever "
        "wants policy in a repository, but the database is the authority.",
    },
    {
        "kind": "split",
        "kicker": "Lineage and custody",
        "title": "Both directions, and an audit chain that anchors outside the database",
        "left": {
            "head": "Lineage",
            "items": [
                (
                    "Upstream and downstream",
                    "From an execution warrant back to the source files, and from a source "
                    "forward to every warrant that depends on it.",
                ),
                (
                    "Derived objects are nodes, not shortcuts",
                    "A derived feature keeps its expression in lineage rather than being "
                    "flattened, so what a number ultimately reads is a traversal and not a "
                    "guess.",
                ),
                (
                    "Which is what makes a blast radius honest",
                    "It is computed from edges that were type-checked when they were recorded, so "
                    "a line on the lineage graph is a claim that was checked, not a drawing.",
                ),
            ],
        },
        "right": {
            "head": "The audit chain",
            "items": [
                (
                    "Hash-chained per entry",
                    "Each row's digest covers the previous digest and its own fields, so a "
                    "rewritten row breaks every row after it.",
                ),
                (
                    "Anchored out of the database, hourly",
                    "The chain head is signed, appended to a file and emitted as an event. "
                    "Timestamping by a third-party authority is opt-in, because it sends the "
                    "head to a third party.",
                ),
                (
                    "It refuses to certify tampering",
                    "A chain that does not verify is not anchored, and verification names the "
                    "sequence number where it broke.",
                ),
                (
                    "The honest limit",
                    "An anchor is only as external as the file it is written to; point it at "
                    "off-host or write-once storage.",
                ),
            ],
        },
        "note": "maya/services/ops.py (lineage), maya/persistence/repositories/special.py (the chain), "
        "maya/services/custody.py (the anchors); "
        "tests/test_custody.py::test_an_anchor_catches_a_rechained_rewrite and "
        "::test_a_real_tsa_signature_is_verified_against_its_ca.",
    },
    {
        "kind": "bullets",
        "kicker": "Persistence",
        "title": "One database at a time, two generated schema files, no migrations",
        "items": [
            (
                "SQLite in the shipped configuration; PostgreSQL by setting one key",
                "Never both, and never mixed. Several web processes on one node require PostgreSQL, "
                "and MAYA refuses them over SQLite rather than running them unsafely.",
            ),
            (
                "One typed metadata, two DDL files",
                "maya/persistence/schema/sqlite.sql and postgresql.sql are produced from the "
                "SQLAlchemy models; a gate regenerates both and fails on any difference, and a "
                "planted hand-edit is shown to trip it.",
            ),
            (
                "A mismatched database is refused at startup",
                "It is never upgraded in place. There is no migration tool, so there is no "
                "half-applied migration — and the upgrade is a procedure somebody has to run. The "
                "trade is stated rather than hidden.",
            ),
            (
                "The upgrade path is export, recreate, import",
                "The estate export reads the database as it stands, so it still works across the "
                "schema change that made it necessary, and a column it cannot fill is named rather "
                "than defaulted.",
            ),
            (
                "One door to the database",
                "No SQLAlchemy import outside maya/persistence, held by a gate. The suite has run "
                "green on PostgreSQL 16, 17 and 18; 14 is the documented floor and has not been "
                "run.",
            ),
        ],
        "note": "maya/persistence/; tools/ci/gen_schema.py and import_boundaries.py; "
        "tests/test_foundation.py::test_shipped_schema_files_match_the_metadata, "
        "tests/test_workflow_and_estate.py::test_schema_mismatch_refuses_to_start.",
    },
    {
        "kind": "table",
        "kicker": "Code artifacts",
        "title": "Six rungs, one refusal each, then a sandbox tier that is declared",
        "intro": "A model may carry uploaded Python. It is treated as hostile until proved otherwise, "
        "and the ladder stops at the first failing rung and records the rest as not run — so a "
        "report never implies a check it did not perform.",
        "rows": [
            ["Rung", "What it checks"],
            [
                "1  parse",
                "The source parses; a linter runs where it is installed, and whether it ran is "
                "recorded rather than assumed",
            ],
            [
                "2  entry point",
                "The declared class implements the interface MAYA will call: fit and predict, with the "
                "signatures it expects",
            ],
            [
                "3  import allowlist",
                "Numeric and data libraries only — math, statistics, itertools, numpy, pandas, polars, "
                "pyarrow, scipy, scikit-learn, statsmodels and a few more",
            ],
            [
                "4  static ban",
                "No open, eval, exec, compile, dynamic import or dunder attribute access; no os, sys, "
                "subprocess, socket, pathlib, pickle or threading",
            ],
            [
                "5  smoke run",
                "One run in the sandbox against a sample, under CPU, memory and wall-clock caps",
            ],
            [
                "6  determinism",
                "The smoke run twice with the same seed, outputs compared — a mismatch is recorded as "
                "a warning, not a refusal",
            ],
        ],
        "col_w": [1.9, 9.7],
        "note": "maya/formula/artifact.py and maya/security/sandbox.py; tests/test_sandbox.py, "
        "tests/test_sandbox_linux.py. Rungs 1–5 decide the verdict. The tier is strong on Linux "
        "only when a probe child fails to escape a bubblewrap jail with a seccomp filter and a "
        "cgroup scope, and it is stamped on every artifact validated under it.",
    },
    {
        "kind": "table",
        "kicker": "Held by gates",
        "title": "One command, and never a remembered list",
        "intro": "Every architectural rule on the last ten slides is enforced by a program rather than "
        "by review, and each rung has been shown to catch a planted fault. A rule that is only "
        "written down holds until the first deadline.",
        "rows": [
            ["Stage", "What it checks"],
            [
                "Static, every run",
                "Lint; strict typing of maya/services; file size; both import boundaries; import "
                "cycles; public names per module; seam imports; SDK public symbols; version single "
                "source; no secrets; the table contract; colour contrast; SDK↔API parity for 246 "
                "endpoints; UI↔SDK parity; the API contract snapshot; protocol literals; a security "
                "linter; schema drift",
            ],
            ["--tests", "The whole suite under a 90% line-coverage floor; 92.9% at this release"],
            [
                "--fallback",
                "The suite again with every optional accelerator pinned to its pure-Python fallback, "
                "so the fallback is a tested path rather than a hope",
            ],
            ["--security", "A dependency audit, and the sandbox escape tests"],
            ["--bench", "A benchmark regression of more than 10% needs a written note"],
        ],
        "col_w": [1.7, 9.9],
        "note": "tools/ci/gates.py; tests/test_api_and_gates.py and tests/test_gate_ladder.py. The "
        "ladder runs locally and in the pre-commit hook on every commit; there is no hosted "
        "continuous integration, by decision.",
    },
]
