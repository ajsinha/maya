"""
The capabilities deck: what MAYA does, told through the product.

It walks the platform the way somebody using it would — the screens, the
objects, the refusals — and then carries one real model, the IFRS 9 expected
credit loss study in ``case_studies/06-ifrs9-expected-credit-loss/``, from a
blank namespace to a suspended execution warrant. A feature list persuades
nobody; a model that went all the way through, including where it was refused
and what it failed to explain, is the argument.

Every figure comes from the code, the README's "What's shipped",
docs/BENCHMARKS.md or a study's recorded run, and each slide's note names it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from capabilities_deck_2 import SLIDES as LATER

CHAPTER = "MAYA · Capabilities"
TITLE = "MAYA — Capabilities"
SUBJECT = "What MAYA does, shown through the product, and one model carried end to end"

PRODUCT = [
    {
        "kind": "title",
        "kicker": "CAPABILITIES  ·  THE PRODUCT, AND ONE MODEL ALL THE WAY THROUGH",
        "title": ["What MAYA does,", "and what it refuses to do"],
        "sub": "MAYA — Model & AI Lifecycle Assurance.  Evidence, not assertion.",
        "agenda": [
            "The product: where the work happens",
            "Data you can stand behind",
            "Models you can check",
            "Governance that holds",
            "One model end to end: IFRS 9 expected credit loss",
            "What MAYA does not do",
        ],
    },
    {
        "kind": "divider",
        "num": "1",
        "title": "The product",
        "sub": "A governance platform lives or dies on whether people would rather use it than a notebook, so the interface is a deliverable rather than a skin over an API.",
        "points": [
            "Where the work happens",
            "Four surfaces, one contract",
            "The first five minutes",
        ],
    },
    {
        "kind": "cards",
        "kicker": "Where the work happens",
        "title": "Six places, and the same objects visible from each",
        "cols": 3,
        "cards": [
            (
                "Workbench",
                "Author and rehearse",
                "Define a feature, upload or pull its data, preview a resolution before it is pinned, build a feature set, open a workspace to try a change safely.",
            ),
            (
                "Catalog",
                "Find and compare",
                "Features and feature sets with their versions, pins, lineage and quality history; compare two versions; download a pin as tabular or wide.",
            ),
            (
                "Models",
                "Register and review",
                "The kernel wizard, the formula, the code artifact and its ladder report, the specification document, the semantic diff between two versions.",
            ),
            (
                "Warrants",
                "Licence and verify",
                "Draw a training warrant, fetch the data, upload parameters, seal an execution warrant, export a bundle — and verify a bundle somebody hands you.",
            ),
            (
                "Inbox",
                "Decide",
                "The review queue, scoped to what you may actually see, with what is overdue, what is blocked and by which named check.",
            ),
            (
                "Admin",
                "Operate",
                "Namespaces and grants, users and sign-on, sources, jobs, events and webhooks, storage, retention, custody anchors, and a health page that names every resolved seam.",
            ),
        ],
        "note": "maya/web/routes/: workbench.py, catalog.py, models.py, warrants.py, home.py, admin.py, lineage.py, workflow.py, workspaces.py. Every page is rendered in tests/test_web.py::test_every_page_renders, and the journeys through them in tests/test_web_journeys.py.",
    },
    {
        "kind": "split",
        "kicker": "Four surfaces, one contract",
        "title": "Whatever you drive it with, it is the same platform",
        "left": {
            "head": "The surfaces",
            "items": [
                (
                    "The web UI is an SDK client",
                    "It has no private path to the services; a gate fails the build if anything under the web tier imports past the SDK.",
                ),
                (
                    "The REST API",
                    "215 endpoints, each with an SDK method and each method with an endpoint, checked both ways by a gate.",
                ),
                (
                    "The Python SDK",
                    "Synchronous and asynchronous, with record and replay for tests, and an offline mode that serves a bundle and refuses everything the bundle does not hold.",
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
                    "Rows per page remembered per table per user, sort applied to the whole result set rather than the visible page, export honouring the active filter. A crawler gate refuses any table not drawn by the one macro.",
                ),
                (
                    "Large tables page from the server",
                    "Signed cursors, the same controls, and an exact total counted in the database under row-level authorization.",
                ),
                (
                    "Search is MAYA's own index",
                    "Ranked, prefix-matched, every term required, filtered by read permission, kept current inside the writing transaction. p95 0.16 s over 100,000 objects.",
                ),
                (
                    "Status is never colour alone",
                    "Every pill carries a glyph and a word, and the palette is recomputed by a gate against contrast floors.",
                ),
            ],
        },
        "note": "README, “The interface”; tools/ci/table_contract.py, tools/ci/sdk_parity.py, tools/ci/contrast.py; tests/test_browser.py::test_a_server_paged_table_pages_searches_and_sorts; docs/BENCHMARKS.md for the search figure.",
    },
    {
        "kind": "bullets",
        "kicker": "The first five minutes",
        "title": "Ceremony scales with consequence",
        "items": [
            (
                "A scratch namespace with no ceremony",
                "One command turns a CSV into a typed, resolvable, versioned feature: the platform loses to a notebook the moment it is more trouble than one.",
            ),
            (
                "Then the same object, governed",
                "Moving it into a team namespace is what adds the review, the approvals and the audit — not a different kind of object, and not a migration.",
            ),
            (
                "Preview before you commit",
                "A resolution can be previewed, a feature set planned, a change rehearsed in a workspace, and a formula translated by the kernel wizard, all without writing anything.",
            ),
            (
                "Refusals name themselves",
                "An unsupported source, an unreadable formula, an unaggregated index, a covenant with nothing to watch: each is refused with the reason and the position, never approximated.",
            ),
        ],
        "note": "tests/test_features.py::test_scratch_quick_feature_has_zero_ceremony and tests/test_cli.py::test_quick_upload_and_restatement; specification §28.1. SC-9 — a new designer publishing a first model inside an hour — has not been timed with a real person, and the README says so.",
    },
]

DATA = [
    {
        "kind": "divider",
        "num": "2",
        "title": "Data you can stand behind",
        "sub": "A feature is a governed bitemporal dataset. A pin is the same bytes forever. Between them sits an algebra, so a derived dataset is an ordinary dataset.",
        "points": [
            "Two clocks, and as-of reads",
            "Pins, hashes and shared fragments",
            "The feature algebra",
            "Feature sets and cascade pinning",
            "Grant conditions",
        ],
    },
    {
        "kind": "split",
        "kicker": "Bitemporality",
        "title": "Two clocks, so “what did we know then” stays answerable",
        "left": {
            "head": "How a row is stored",
            "items": [
                (
                    "Event time",
                    "The date a value is about — the first column of the feature's index.",
                ),
                (
                    "Knowledge time",
                    "The instant MAYA could first have known it, stamped on every ingested row.",
                ),
                (
                    "A restatement is an append",
                    "A vendor correction never overwrites: the ingest log is append-only, so the old answer is still there.",
                ),
            ],
        },
        "right": {
            "head": "What you can then ask",
            "items": [
                (
                    "Read the world as of a date",
                    "The knowledge-time cut runs first, then the latest knowledge per key, then the grid, then the fill rules — on every read path, including a feature set's.",
                ),
                (
                    "Prove a training set has no look-ahead",
                    "Every row's knowledge time at or before its event date plus the declared lag, issued as a signed certificate with the warrant.",
                ),
                (
                    "See what was filled",
                    "Every resolution emits a fill report: rows filled per rule and the longest run, stored with the pin.",
                ),
            ],
        },
        "note": "maya/resolution/resolver.py and maya/services/feature_data.py; tests/test_features.py::test_sc11_point_in_time_after_restatement, tests/test_properties.py::test_a_restatement_never_overwrites. Point-in-time correctness exists elsewhere as a join semantic; the certificate is the part nobody else issues.",
    },
    {
        "kind": "split",
        "kicker": "Pins",
        "title": "A pin is a manifest of shared fragments, sealed by a hash",
        "left": {
            "head": "What sealing means",
            "items": [
                (
                    "The hash is over values, not file bytes",
                    "Column order is ignored, any changed value is noticed, and two pins of the same data agree across engine versions and machines.",
                ),
                (
                    "Re-pinning the same data is free and identical",
                    "Byte-identical content hash, and nothing new written.",
                ),
                (
                    "Fragment boundaries follow the content",
                    "One inserted row leaves every earlier fragment untouched, so an unchanged month costs under 5% of a full pin.",
                ),
            ],
        },
        "right": {
            "head": "What it buys",
            "items": [
                (
                    "A pin can be handed to an auditor",
                    "Immutable, content-addressed, and verifiable without trusting the system that produced it.",
                ),
                (
                    "Storage that does not multiply",
                    "Month-end pins of a slow-moving feature share almost everything.",
                ),
                (
                    "Speed that was measured",
                    "Pin write 59.7 MB/s on one worker against a 50 MB/s target; resolution of a 50-attribute, ten-year, 500-symbol feature set at 0.98 s warm.",
                ),
            ],
        },
        "note": "maya/core/canonical.py (the definition of the hash), maya/core/chunker.py; tests/test_features.py::test_sc1_repin_is_byte_identical_and_changed_data_is_not and ::test_sc12_unchanged_month_costs_under_five_percent; docs/BENCHMARKS.md.",
    },
    {
        "kind": "table",
        "kicker": "The feature algebra",
        "title": "Fifteen operators, each yielding a definition rather than a result",
        "intro": "A derived feature is an ordinary feature: named, versioned, pinnable, permissioned and "
        "visible in lineage. Inheritance stores a diff, not a copy, so a fix to a parent reaches "
        "every child.",
        "rows": [
            ["Operator", "Produces", "Operator", "Produces"],
            ["project", "A subset of attributes", "aggregate", "A coarser index"],
            ["rename", "The same data, renamed", "lag", "Values shifted by n periods"],
            ["transform", "A derived feature by pipeline", "resample", "A new frequency"],
            [
                "union",
                "Rows of both, collisions by policy",
                "case",
                "Row-wise choice between inputs",
            ],
            ["intersect", "Rows whose index is in both", "pivot", "Long to wide"],
            ["difference", "Rows of the first absent from the second", "unpivot", "Wide to long"],
            ["compose", "Attributes of both, aligned", "sample", "A deterministic seeded subset"],
            ["coalesce", "First non-null across ordered inputs", "", ""],
        ],
        "col_w": [1.6, 4.2, 1.6, 4.2],
        "note": "maya/resolution/algebra.py. Typed at definition time with no data read; each operator declares whether it is additive, behavioral or breaking; non-causality propagates; a canonical derivation hash lets MAYA refuse an algebraically identical near-copy rather than accept a second truth.",
    },
    {
        "kind": "split",
        "kicker": "Feature sets",
        "title": "A view over features, and pinned as a whole or not at all",
        "left": {
            "head": "Building one",
            "items": [
                (
                    "Attributes mapped from members",
                    "Each names its member, the source attribute, an optional cast and its overrides; alignment is inner, outer, left, or as-of with a tolerance.",
                ),
                (
                    "Six layers of precedence, shown per attribute",
                    "The attribute's override, a member group, the set's policy, an inherited policy, the member's own, then the system default of leaving it null.",
                ),
                (
                    "Refused rather than guessed",
                    "A member index with columns the set lacks is refused unless an aggregation is declared for them.",
                ),
            ],
        },
        "right": {
            "head": "Pinning one",
            "items": [
                (
                    "Cascade, or nothing",
                    "A set refuses to pin while any member is unpinned; cascade pins them all under one name and date in one job, and a single quality failure rolls the whole thing back.",
                ),
                (
                    "Three materialization policies, one hash",
                    "always writes the frame; on_demand and never seal by the hash of the output and replay it from the member pins, and a replay that does not reproduce the hash fails the read.",
                ),
                (
                    "Withheld, never dropped",
                    "An attribute you may not read comes back named and null, so the shape of the answer does not depend on who asked.",
                ),
            ],
        },
        "note": "maya/resolution/featureset.py and maya/services/featuresets.py; tests/test_materialization.py, tests/test_warrants.py::test_cascade_rolls_back_entirely_on_a_member_failure. Feature-set operators beyond extend are not built; the specification audit lists it.",
    },
    {
        "kind": "split",
        "kicker": "Grant conditions",
        "title": "Narrowing a grant without forking the data",
        "left": {
            "head": "Three conditions",
            "items": [
                (
                    "row_filter",
                    "An expression over the row with the asking principal substituted, so one grant serves a whole desk.",
                ),
                (
                    "column_mask",
                    "null, or hash — the digest of the value's text, so a join still works and the value never leaves.",
                ),
                (
                    "time_bound",
                    "A cutoff date; a row with a later event date is dropped before the caller sees it.",
                ),
            ],
        },
        "right": {
            "head": "And when several apply",
            "items": [
                ("Row filters", "Combined with AND: the narrowest wins."),
                ("Column masks", "Unioned, and null beats hash on a conflict."),
                ("Time bounds", "The earliest cutoff wins."),
                (
                    "On every path",
                    "Member-level and set-level conditions are applied inside feature-set resolution, on live and pinned data alike, so no read escapes a mask.",
                ),
            ],
        },
        "note": "maya/security/conditions.py; tests/test_conditions.py. Conditions only ever narrow a grant. Nothing in the UI, the API, the SDK or the CLI reaches data without passing the one authorization function first.",
    },
]

MODELS = [
    {
        "kind": "divider",
        "num": "3",
        "title": "Models you can check",
        "sub": "A model is mathematics, code, parameters and a document, versioned against one another — so a reviewer can ask whether the code is the mathematics and get an answer in numbers.",
        "points": [
            "The compute-kernel wizard",
            "Mathematics as data",
            "Code, on a six-rung ladder",
            "Conformance, and declared black boxes",
            "Composite models",
            "Documents, spreadsheets and vendor models",
        ],
    },
    {
        "kind": "flow",
        "kicker": "The compute-kernel wizard",
        "title": "Write the mathematics; read back what MAYA made of it",
        "steps": [
            ("Write", "As LaTeX or plain text, and say which symbols are parameters"),
            ("Translate", "MAYA parses it into a typed tree, or refuses and names the position"),
            (
                "Read back",
                "The tree, the LaTeX it renders as, each input with its role, the intermediates in order",
            ),
            ("Take the function", "One portable function, or the full reference module"),
        ],
        "box_h": 2.0,
        "items": [
            "It reads nothing and writes nothing. Whoever wrote the mathematics sees what MAYA made of it before a model version exists to attach it to — the alternative is finding out at registration, which is later and more expensive.",
            "The emitted kernel is one self-contained function taking the inputs and the parameters and returning one value per row. Imports and helpers sit inside the function body, and it needs numpy alone unless the formula uses a normal distribution.",
            "The same parser and generator serve registration, so the wizard shows what a registered version would hold rather than a mock-up of it. Black–Scholes, a logistic probability of default and a Nelson–Siegel curve ship as worked examples on the page.",
        ],
        "note": "Web page /models/kernel; API POST /formula/kernel; SDK client.models.kernel. maya/formula/parse.py and codegen.py; one parser reads both LaTeX and Python-ish text, including LaTeX's implicit multiplication.",
    },
    {
        "kind": "split",
        "kicker": "Mathematics as data",
        "title": "A typed expression tree, and the four things it makes possible",
        "left": {
            "head": "What is stored",
            "items": [
                (
                    "Four node kinds",
                    "An operator with arguments, a reference, a constant, a parameter — over twenty-three typed operators.",
                ),
                (
                    "Three roles for every input",
                    "Feature, parameter or constant. The parameters are exactly what training fills, so the contract is derived rather than declared twice.",
                ),
                (
                    "Joint constraints, with reasons",
                    "A constraint such as a volatility model's stationarity condition carries the reason it exists, and a violation is reported as the terms, their values and the total.",
                ),
                (
                    "Or an honest hole",
                    "A declared black box must state what it estimates and its architecture, or it is refused.",
                ),
            ],
        },
        "right": {
            "head": "What MAYA does with it",
            "items": [
                (
                    "Type-checks the inputs",
                    "Against the bound feature set, listing every miss at once.",
                ),
                (
                    "Renders the document",
                    "The specification's formula blocks are pulled from the tree, so the document cannot drift from the implementation.",
                ),
                (
                    "Diffs two versions mathematically",
                    "“The discount factor changed from continuous to simple compounding”, not a text diff.",
                ),
                (
                    "Emits reference code",
                    "Tested equal to MAYA's own evaluator, and the hash ignores LaTeX spelling while noticing mathematics.",
                ),
            ],
        },
        "note": "maya/formula/: ir.py, latex.py, diff.py, evaluate.py, codegen.py, specdoc.py; tests/test_formula.py::test_diff_detects_compounding_change and ::test_hash_ignores_latex_but_not_math. A model version is minted when the IR hash, the artifact hash or the input contract changes.",
    },
    {
        "kind": "table",
        "kicker": "Code artifacts",
        "title": "Six rungs, one refusal each, and a sandbox tier that is declared",
        "rows": [
            ["Rung", "What it checks"],
            [
                "1  parse",
                "The source parses; a linter runs where it is installed, and whether it ran is recorded",
            ],
            ["2  entry point", "The declared class implements the interface MAYA will call"],
            [
                "3  import allowlist",
                "Numeric and data libraries only — numpy, pandas, polars, pyarrow, scipy, scikit-learn, statsmodels and the standard numeric modules",
            ],
            [
                "4  static ban",
                "No file, process, network or dynamic-code use: no open, eval, exec, dynamic import, dunder attribute access, os, subprocess, socket, pickle, threading",
            ],
            [
                "5  smoke run",
                "One run in the sandbox against a sample, under CPU, memory and wall-clock caps",
            ],
            [
                "6  determinism",
                "The same run twice with the same seed, outputs compared; a mismatch is a recorded warning",
            ],
        ],
        "col_w": [1.9, 9.7],
        "note": "maya/formula/artifact.py, maya/security/sandbox.py. The ladder stops at the first failure and records the rest as not run, so a report never implies a check it did not perform; rungs 1–5 decide the verdict. The tier is strong on Linux only when a probe child fails to escape, and it is stamped on every artifact validated under it.",
    },
    {
        "kind": "split",
        "kicker": "Is the code the mathematics?",
        "title": "Conformance testing, and what a black box forfeits",
        "left": {
            "head": "Differential testing",
            "items": [
                (
                    "The comparison",
                    "The uploaded code is run against MAYA's own evaluation of the documented mathematics on sampled inputs, to a relative tolerance of 1e-9.",
                ),
                (
                    "Counterexamples, not a verdict",
                    "Up to ten disagreeing rows with the expected and the actual value, so the argument is about numbers.",
                ),
                (
                    "Tied to the artifact",
                    "A version with code cannot advance until conformance has run against that exact artifact and agreed everywhere sampled.",
                ),
                (
                    "Honest about itself",
                    "The report says sampled agreement is not proof, and that MAYA cannot know whether a feature set is representative.",
                ),
            ],
        },
        "right": {
            "head": "Declared black boxes",
            "items": [
                (
                    "Registered, not excluded",
                    "With the estimate and the architecture declared, the input contract enforced, and warrants that behave exactly as they do for anything else.",
                ),
                (
                    "Conformance is skipped and says so",
                    "There is no documented closed form to test against, and the report states that rather than passing quietly.",
                ),
                (
                    "Blind scoring is refused by name",
                    "“A declared black box cannot be scored by MAYA.” Scoring evaluates the mathematics in process; it never runs the uploaded artifact.",
                ),
                (
                    "Covenants become the control",
                    "For an opaque model they are the only one available, which is where the review effort belongs.",
                ),
            ],
        },
        "note": "maya/formula/conformance.py and maya/services/models.py; ADR-007. Study 07 in case_studies/ is a card-fraud network carried through on exactly these terms, and study 05 has a conformance test that passes on a narrow domain and fails on the whole option chain.",
    },
    {
        "kind": "table",
        "kicker": "Composite models",
        "title": "A graph of models, governed as one model",
        "rows": [
            ["Rule", "How it behaves"],
            [
                "Five kinds",
                "ensemble, pipeline, router, residual, hierarchical; trained sequentially, in parallel or jointly",
            ],
            [
                "One contract",
                "The union of the members' contracts and the combiner's own inputs; two members wanting one name at different types is refused, naming the attribute",
            ],
            [
                "One parameter set",
                "Namespaced by member alias, with the combiner's own parameters bare; a member may borrow an approved set, frozen",
            ],
            ["One warrant", "Over one feature set, however many members there are"],
            [
                "Maturity capped",
                "At the least mature member's, and the members blocking a promotion are named rather than left to be inferred",
            ],
            [
                "Bounded and reproducible",
                "Members bound pinned or tracking, nesting capped at four, cycles refused, opacity propagating from any black-box member, per-member seeds derived from one seed",
            ],
        ],
        "col_w": [2.1, 9.5],
        "note": "maya/formula/composite.py; tests/test_formula.py::test_composite_union_maturity_seeds_and_eval. Study 04 in case_studies/ is a router with two members and a seal that refuses while half the composite is unfitted; study 06, which follows, is an ensemble with three members and parameters of its own.",
    },
    {
        "kind": "split",
        "kicker": "Documents and models that already exist",
        "title": "The specification, the spreadsheet and the vendor's black box",
        "left": {
            "head": "The specification document",
            "items": [
                (
                    "Nine required sections",
                    "Purpose, scope and limitations, formulation, assumptions, data, calibration, validation evidence, known weaknesses, change log — submission is blocked while one is empty.",
                ),
                (
                    "Bound to the mathematics",
                    "Formula blocks render from the tree and references pull from the catalog, so the document cannot drift.",
                ),
                (
                    "A real build, or a labelled draft",
                    "With Tectonic it is a true LaTeX build; without it a watermarked draft that cannot be approved outside dev.",
                ),
            ],
        },
        "right": {
            "head": "Spreadsheets and vendor models",
            "items": [
                (
                    "A workbook lifted into the mathematics",
                    "Arithmetic, standard functions, named cells and ranges, and lookups over constant tables; everything else refused by cell. Checked against the workbook's own results and against a headless recalculation.",
                ),
                (
                    "A vendor model registered as what it is",
                    "A declared contract, the vendor's version and documentation, the same review and the same warrants — and what cannot be verified marked unverifiable rather than omitted.",
                ),
                (
                    "Because completeness is the question",
                    "The firm stays accountable for a model it bought, so leaving it out of the inventory is not an option.",
                ),
            ],
        },
        "note": "maya/formula/specdoc.py, maya/formula/xlsx.py, maya/services/models.py; tests/test_typeset.py, tests/test_spreadsheet_libreoffice.py, tests/test_vendor_models.py. Spreadsheet import is v1 scope and has not been checked against workbooks saved by Microsoft Excel.",
    },
]

SLIDES = PRODUCT + DATA + MODELS + LATER
