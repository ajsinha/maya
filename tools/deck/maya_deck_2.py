"""
The MAYA deck, parts 3 and 4: the objects the platform keeps, and how it runs.

Part 3 takes each word Part 1 defined and says what MAYA stores for it. Part 4
is the machinery around those objects — the surfaces, the workflow, the storage,
the checks a build has to pass.

Split from ``maya_deck`` only to keep each file short enough to read. Every
figure comes from the code, the README's "What's shipped" or
``docs/BENCHMARKS.md``, and every slide's note names the module or the test.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

OBJECTS = [
    {
        "kind": "divider",
        "num": "3",
        "title": "The objects MAYA keeps",
        "sub": "Part 1 defined seven words. This part says what the platform stores for each of "
        "them, and what it refuses. Nothing new is introduced: every object here is one of those "
        "words with an identity, a version, a workflow state and an audit trail attached.",
        "points": [
            "Definition, version, pin — and six governed kinds",
            "Features: sources, clocks, resolution",
            "The feature algebra",
            "Feature sets: alignment and cascade pinning",
            "Models: the typed formula tree",
            "The compute-kernel wizard",
            "Parameter sets, bounds and joint constraints",
            "Warrants, covenants and the evidence bundle",
        ],
    },
    {
        "kind": "table",
        "kicker": "The pattern, everywhere",
        "title": "Six governed kinds, and the same three layers under each",
        "intro": "Part 1's definition–version–pin pattern is not a feature of features. It is the "
        "shape of every object MAYA governs, which is why one workflow engine, one authorization "
        "function and one audit chain serve all of them.",
        "rows": [
            ["Governed kind", "What its definition says", "What a version freezes"],
            [
                "Feature version",
                "Schema, index, source, fill rules, quality checks",
                "All of it, classified breaking, behavioural or additive",
            ],
            [
                "Feature-set version",
                "Which features, which attributes, the grid and the alignment",
                "The recipe, not the rows; the rows are frozen by a pin",
            ],
            [
                "Model version",
                "The mathematics, the code artifact, the input contract, the document",
                "Minted when the mathematics, the artifact or the contract changes",
            ],
            [
                "Parameter set",
                "The dial values, their provenance and the reasoning behind them",
                "The numbers, approved as a set — a partial upload is not a smaller decision",
            ],
            [
                "Training warrant",
                "Which model may be fitted on which pinned data, by whom, until when",
                "The subject, the split, the escrow and the leakage certificate",
            ],
            [
                "Execution warrant",
                "Which model may run with which dials, in which environment",
                "The licence itself, with its expiry, its covenants and its limits",
            ],
        ],
        "col_w": [2.2, 4.7, 4.7],
        "note": "maya/workflow/policy.py names exactly these six as the governed object types. A "
        "bare name resolves to the latest approved version and MAYA records that resolution, so "
        "“latest” never hides inside an audit trail.",
    },
    {
        "kind": "table",
        "kicker": "Features",
        "title": "Where a feature's rows come from, and what each source costs",
        "rows": [
            ["Source", "How it behaves", "Proved by"],
            [
                "csv, parquet, json",
                "Uploaded files, content-addressed; the inferred schema is a proposal the designer "
                "confirms rather than a guess applied",
                "tests/test_features.py, tests/test_cli.py::test_quick_upload_and_restatement",
            ],
            [
                "sql",
                "A read-only query on an administrator-managed connection, with typed parameters "
                "bound rather than interpolated",
                "tests/test_sql_source.py",
            ],
            [
                "python",
                "A reviewed producer function run in the sandbox on every pull: the escape hatch, "
                "and it needs approval",
                "tests/test_python_source.py",
            ],
            [
                "derived",
                "An expression over other feature versions or pins, kept in lineage rather than "
                "flattened into a copy",
                "tests/test_features.py::test_derived_union_and_inheritance",
            ],
            [
                "unsupported",
                "Anything else is refused by name, never approximated with the nearest thing that "
                "parses",
                "tests/test_features.py::test_unsupported_source_is_refused_by_name",
            ],
        ],
        "col_w": [1.5, 5.6, 4.5],
        "note": "maya/services/sources.py. Every upload and every pull lands in the append-only "
        "bitemporal ingest log with an ingest time, which is the premise Part 2's operator needs "
        "and the reason MAYA pulls a source rather than querying it in place.",
    },
    {
        "kind": "split",
        "kicker": "Resolution",
        "title": "Declarative gap filling, bounded and reported",
        "intro": "Resolving a feature version means: cut the log by ingest time, take the latest "
        "knowledge per key, lay the rows on the declared grid, then apply the fill rules. Every "
        "read path does it in that order, including a feature set's.",
        "left": {
            "head": "Grid and rules",
            "items": [
                (
                    "The grid",
                    "As the rows arrived, or a shipped calendar: NYSE, LSE, TARGET, ISO business "
                    "days, natural days.",
                ),
                (
                    "Ten rules per attribute",
                    "Leave null, forward fill, backward fill, linear or spline interpolation, a "
                    "constant, a window mean, last known as of, zero, previous period.",
                ),
                (
                    "Bounded, and refused when unbounded is meant",
                    "Forward fill takes a row limit and a maximum age; beyond either, the value "
                    "stays null. A negative lag is rejected as look-ahead.",
                ),
                (
                    "Non-causal rules are named as such",
                    "Backward fill and both interpolations consume the future. Inside a training "
                    "set they require a written justification.",
                ),
            ],
        },
        "right": {
            "head": "What every run emits",
            "items": [
                (
                    "A fill report",
                    "Rows filled per rule and the longest fill run, stored with the pin so "
                    "nobody has to guess later how much of the data was invented.",
                ),
                (
                    "A quality verdict that can block",
                    "Contract checks run on every resolution and always on a pin; a failure "
                    "blocks the pin rather than warning about it.",
                ),
                (
                    "Measured",
                    "Warm p95 0.98 s for a 50-attribute, 10-year, 500-symbol set with no rules; "
                    "6.1 s with a bounded forward fill on all fifty.",
                ),
                (
                    "And a refusal for a rule it cannot honour",
                    "A custom rule function is in the grammar and refused in this build, because "
                    "no sandboxed rule function is registered. A name MAYA cannot honour is a "
                    "refusal, not a silent no-op.",
                ),
            ],
        },
        "note": "maya/resolution/resolver.py and rules.py; tests/test_resolution_core.py, "
        "tests/test_features.py::test_quality_contract_blocks_the_pin; docs/BENCHMARKS.md for the "
        "two timings.",
    },
    {
        "kind": "table",
        "kicker": "The feature algebra",
        "title": "Fifteen operators, each yielding a definition rather than a result",
        "intro": "A derived feature is an ordinary feature: named, versioned, pinnable, "
        "permissioned and visible in lineage. That closure is what stops “derived data” "
        "being a second, ungoverned category — and inheritance stores a difference rather than a "
        "copy, so a fix to a parent reaches every child.",
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
        "note": "maya/resolution/algebra.py: typed at definition time with no data read, each "
        "operator declaring whether it is additive, behavioural or breaking; non-causality "
        "propagates; and a canonical derivation hash lets MAYA refuse an algebraically identical "
        "near-copy rather than accept a second truth.",
    },
    {
        "kind": "split",
        "kicker": "Feature sets",
        "title": "Alignment, and six layers deciding what fills a gap",
        "left": {
            "head": "Mapping and alignment",
            "items": [
                (
                    "Attribute mapping",
                    "Each attribute names its member, the source attribute, an optional cast and "
                    "its own overrides.",
                ),
                (
                    "Alignment",
                    "Inner, outer, left on a named member, or as-of with a tolerance and a "
                    "direction.",
                ),
                (
                    "Broadcast, stated rather than silent",
                    "A narrower member index is broadcast across the grid and the resolution "
                    "plan says so.",
                ),
                (
                    "Refused",
                    "A member index carrying columns the set lacks, unless an aggregation is "
                    "declared for them — collapsing rows is a modelling decision.",
                ),
            ],
        },
        "right": {
            "head": "Precedence, shown per attribute",
            "items": [
                "1  The attribute's own override",
                "2  A member-group override",
                "3  The set's global policy",
                "4  Inherited policy, nearest ancestor first",
                "5  The member feature's own policy",
                "6  System default: leave it null",
            ],
        },
        "note": "maya/resolution/featureset.py (choose_rule); tests/test_resolution_algebra.py::"
        "test_featureset_precedence_layers_and_broadcast and ::"
        "test_featureset_refuses_unaggregated_extra_index. Which layer decided an attribute is "
        "shown in the plan, not left for the reader to infer.",
    },
    {
        "kind": "bullets",
        "kicker": "Pinning a set",
        "title": "Cascade, materialisation, and one hash for all three policies",
        "items": [
            (
                "A set refuses to pin while any member is unpinned",
                "A cascade pins each unpinned member under one shared name and as-of date in one "
                "job, and rolls the whole cascade back if any member fails its quality contract.",
            ),
            (
                "Three materialisation policies, chosen per namespace",
                "Always, the default, writes the resolved frame. On demand and never seal the "
                "pin by the hash of its output and rebuild it from the member pins when read; "
                "under on demand the first rebuild is written back.",
            ),
            (
                "All three seal by the same hash",
                "So the policy is a storage decision and not a correctness one. A rebuild that "
                "does not reproduce the hash fails the read with an integrity error rather than "
                "serving different numbers — safe, and unavailable, and the README says so.",
            ),
            (
                "Withheld, never quietly dropped",
                "An attribute the caller may not read comes back named and null. The shape of "
                "the answer does not depend on who asked, which means a script does not silently "
                "compute something different for a different user.",
            ),
        ],
        "note": "maya/services/featuresets.py; tests/test_materialization.py, "
        "tests/test_warrants.py::test_cascade_rolls_back_entirely_on_a_member_failure. An "
        "algebraically identical set is detected and refused as a near-copy.",
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
                    "An expression over the row with the asking principal substituted, so one "
                    "grant serves a whole desk rather than needing one per person.",
                ),
                (
                    "column_mask",
                    "Null, or hash — the digest of the value's text, so a join still works and "
                    "the value itself never leaves.",
                ),
                (
                    "time_bound",
                    "A cutoff date; a row with a later event date is dropped before the caller "
                    "sees it.",
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
                    "Member-level and set-level conditions are applied inside feature-set "
                    "resolution, on live and pinned data alike, so no read escapes a mask.",
                ),
            ],
        },
        "note": "maya/security/conditions.py; tests/test_conditions.py. Conditions only ever "
        "narrow a grant; they are never a route to widening one. Nothing in the interface, the "
        "API, the SDK or the command line reaches data without passing one authorization "
        "function first.",
    },
    {
        "kind": "split",
        "kicker": "Models",
        "title": "The mathematics, stored as a typed tree rather than as a string",
        "intro": "Part 1 said a model is a kernel and a set of dials. MAYA stores the kernel as a "
        "typed expression tree, which is the difference between mathematics a system can check "
        "and mathematics it can only display.",
        "left": {
            "head": "What is stored",
            "items": [
                (
                    "Four node kinds",
                    "An operator with arguments, a reference to an input, a constant, and a "
                    "parameter — over twenty-three typed operators.",
                ),
                (
                    "Three roles for every input",
                    "Feature, parameter or constant. The parameters are exactly what training "
                    "fills, so the input contract is derived rather than declared twice.",
                ),
                (
                    "Written three ways, stored once",
                    "Parsed from LaTeX or plain text; lifted from an uploaded Python function by "
                    "static analysis; or lifted from a workbook's formula graph.",
                ),
                (
                    "Or an honest hole",
                    "Where there is no closed form, a declared black box must state what it "
                    "estimates and its architecture, or it is refused.",
                ),
            ],
        },
        "right": {
            "head": "What MAYA does with it",
            "items": [
                (
                    "Type-checks the inputs",
                    "Against the bound feature set, listing every miss at once rather than the "
                    "first.",
                ),
                (
                    "Renders the document",
                    "The specification's formula blocks are pulled from the tree, so the document "
                    "cannot drift from the implementation.",
                ),
                (
                    "Diffs two versions mathematically",
                    "“The discount factor changed from continuous to simple "
                    "compounding”, rather than a text diff of the LaTeX.",
                ),
                (
                    "Emits reference code",
                    "Tested equal to MAYA's own evaluator; and the tree's hash ignores LaTeX "
                    "spelling while noticing a change in the mathematics.",
                ),
            ],
        },
        "note": "maya/formula/: ir.py, parse.py, latex.py, diff.py, evaluate.py, codegen.py, "
        "specdoc.py; tests/test_formula.py::test_diff_detects_compounding_change and "
        "::test_hash_ignores_latex_but_not_math.",
    },
    {
        "kind": "flow",
        "kicker": "The compute-kernel wizard",
        "title": "Write the mathematics; read back what MAYA made of it",
        "steps": [
            ("Write", "As LaTeX or plain text, and say which symbols are the dials"),
            ("Translate", "MAYA parses it into the typed tree, or refuses and names the position"),
            (
                "Read back",
                "The tree, the LaTeX it renders as, each input with the role it was given, the "
                "intermediates in order",
            ),
            ("Take the function", "One portable function, or the full reference module"),
        ],
        "box_h": 2.0,
        "items": [
            "It reads nothing and writes nothing. Whoever wrote the mathematics sees what MAYA "
            "made of it before a model version exists to attach it to; the alternative is finding "
            "out at registration, which is later and more expensive.",
            "The emitted kernel is one self-contained function taking the inputs and the dials "
            "and returning one value per row. Imports and helpers sit inside the function body, "
            "and it needs numpy alone unless the formula uses a normal distribution.",
            "The same parser and the same code emitter serve registration, so the wizard shows "
            "what a registered version would hold rather than a mock-up of it. Black–Scholes, a "
            "logistic probability of default and a Nelson–Siegel curve ship as worked examples on "
            "the page.",
        ],
        "note": "Web page /models/kernel; API POST /formula/kernel; SDK client.models.kernel. "
        "maya/formula/parse.py and codegen.py; tests/test_compute_kernel.py::"
        "test_the_kernel_is_one_function_and_nothing_else.",
    },
    {
        "kind": "split",
        "kicker": "Parameter sets",
        "title": "The dials, with their bounds, their reasons and their constraints",
        "intro": "A parameter set is a governed object in its own right, for the reason Part 2 "
        "gave: a refit is a new set of numbers rather than a new model, and the two need "
        "different controls.",
        "left": {
            "head": "What a set carries",
            "items": [
                (
                    "Every declared dial, or it is refused",
                    "A set is a set. A partial upload is not a smaller decision, it is an "
                    "incomplete one, and the refusal names the parameter that is missing.",
                ),
                (
                    "Per-parameter bounds",
                    "A probability in zero to one, a factor at or above zero. Checked on upload, "
                    "not when a strange number reaches a report.",
                ),
                (
                    "Its provenance",
                    "Which act produced it, on which rows, against which checksum, and the "
                    "reasoning where there was no fit at all.",
                ),
            ],
        },
        "right": {
            "head": "Joint constraints, and why bounds are not enough",
            "items": [
                (
                    "A constraint over several dials at once",
                    "A volatility model's stationarity condition: two coefficients each "
                    "perfectly admissible on their own, and inadmissible together. No table of "
                    "per-parameter ranges can express that.",
                ),
                (
                    "Each carries the reason it exists",
                    "So a violation is not a cryptic refusal. It is reported as the terms, their "
                    "values, the computed total, and the sentence saying why the constraint is "
                    "there.",
                ),
                (
                    "Checked where bounds are checked",
                    "On upload, in the same pass, so there is no window in which a set has passed "
                    "one kind of check and not the other.",
                ),
            ],
        },
        "note": "Specification §8.4; maya/formula/ir.py (constraint_errors) and "
        "maya/services/warrants.py (check_constraints); tests/test_formula.py::"
        "test_a_model_can_declare_a_constraint_bounds_cannot_express. Joint constraints exist "
        "because the Nelson–Siegel study in Part 5 needed them.",
    },
    {
        "kind": "flow",
        "kicker": "Training warrants",
        "title": "The checksum cycle that turns paperwork into a control",
        "steps": [
            (
                "Draw",
                "An approved model against a pinned feature set; the contract is checked and "
                "every miss listed",
            ),
            ("Certify", "A signed leakage certificate is issued with the warrant, or refuses it"),
            ("Download", "Train and validation only; who, when and the content hash recorded"),
            (
                "Upload",
                "Dials checked against that hash, against their bounds, and against any joint "
                "constraint",
            ),
            ("Seal", "Approval by policy; every referenced object becomes undeletable"),
        ],
        "box_h": 2.1,
        "items": [
            "The test partition is escrowed: hashed and its row count fixed when the warrant is "
            "drawn, and not included in the download. MAYA scores uploaded dials against it, "
            "returns metrics only, and numbers every attempt on the warrant.",
            "Dials fitted on data matching no checksum MAYA issued are flagged and cannot be "
            "approved without an explicit written justification. That is how a judgement, as "
            "distinct from a fit, gets recorded honestly rather than disguised as one.",
            "A warrant defaults to a 70 / 15 / 15 split, seed 42, an escrowed holdout and a "
            "year's expiry — all overridable, and all recorded on the warrant rather than "
            "remembered.",
        ],
        "note": "maya/services/warrants.py; tests/test_warrants.py::"
        "test_the_checksum_cycle_seal_score_execute_and_bundle and ::"
        "test_contract_mismatch_is_refused_listing_every_attribute.",
    },
    {
        "kind": "split",
        "kicker": "Look-ahead, and the holdout",
        "title": "The leakage certificate, and what the developer never receives",
        "left": {
            "head": "The leakage certificate",
            "items": [
                (
                    "The rule",
                    "Every row's ingest time is at or before its event date plus the declared "
                    "lag, one day by default. That is Part 2's operator, checked over the frame "
                    "that was actually assembled.",
                ),
                (
                    "Three verdicts",
                    "Certified; certified with exceptions, where every exception carries a "
                    "written justification; or refused.",
                ),
                (
                    "Signed, and specific",
                    "Rows examined, the violations with up to twenty example rows, and each "
                    "exception's reason. Without a signing backend it says it is unsigned, and "
                    "why.",
                ),
                (
                    "Honest about its own scope",
                    "It examines the rows the frame carries an ingest time for, and states how "
                    "many it read rather than implying it read them all.",
                ),
            ],
        },
        "right": {
            "head": "The escrowed holdout",
            "items": [
                (
                    "Fixed when the warrant is drawn",
                    "The test partition is hashed and its row count recorded at that moment, so "
                    "the set cannot move afterwards.",
                ),
                (
                    "Scored by MAYA, not by the developer",
                    "MAYA re-derives the split, refuses if the escrowed set has moved, evaluates "
                    "the mathematics in process, and returns metrics only.",
                ),
                (
                    "Every attempt numbered",
                    "Because “scored forty times, best reported” is a fact a reviewer "
                    "should be able to see, and it is not visible anywhere else.",
                ),
                (
                    "The one runtime exception MAYA concedes",
                    "It scores the mathematics and never the uploaded artifact — and for a "
                    "declared black box there is no mathematics to score, so it refuses by name.",
                ),
            ],
        },
        "note": "maya/services/warrants.py; tests/test_warrants.py::"
        "test_leakage_certificate_refuses_late_knowledge; ADR-007, which states that exception "
        "and no more.",
    },
    {
        "kind": "table",
        "kicker": "Execution warrants",
        "title": "A live licence: it expires, it is revoked, and it suspends itself",
        "rows": [
            ["Control", "Behaviour"],
            [
                "Drawn from",
                "A training warrant and an approved parameter set, or straight from a model that "
                "takes no dials at all",
            ],
            [
                "Environments",
                "dev, uat, prod — each permitted explicitly, and an approval may be required only "
                "for prod",
            ],
            [
                "Covenants",
                "Input null rate, input range, input population stability, output range, maximum "
                "rows per day, staleness in days. A breach suspends the warrant at once, writes a "
                "custody event and notifies the owner",
            ],
            [
                "Population drift",
                "A population stability index against a baseline fixed when the warrant was "
                "drawn, so the baseline cannot move later; the default ceiling is 0.25 over ten "
                "bins",
            ],
            [
                "Limits",
                "Calls per day, rows per call, rows per day — these throttle and record overage; "
                "they do not suspend",
            ],
            [
                "Reinstatement",
                "By the model owner or an administrator, with a written reason. A covenant naming "
                "no output on a multi-output model is refused at creation: a covenant with "
                "nothing to compare against is worse than none",
            ],
            [
                "Offline use",
                "Permitted, and both the copy and the warrant are labelled unattested for good",
            ],
        ],
        "col_w": [2.0, 9.6],
        "note": "maya/services/execution.py; tests/test_security_regressions.py::test_each_covenant "
        "and ::test_execution_limits. A revoked, expired or suspended warrant fails every "
        "consuming call closed, naming the covenant that broke or the person to contact.",
    },
    {
        "kind": "split",
        "kicker": "Evidence",
        "title": "A bundle that proves itself on a machine with no MAYA",
        "left": {
            "head": "What is in the archive",
            "items": [
                (
                    "The subject and its data",
                    "Warrant, model version and mathematics, the specification source, the code "
                    "artifact and its report, the dials, the leakage certificate, the training "
                    "frame, the feature-set pin's manifest and its member pins, the Python "
                    "version and the resolved backends.",
                ),
                (
                    "The definition of the hash",
                    "MAYA's own canonical encoder and fragment chunker ship inside the bundle, "
                    "because they are the definition of the hash rather than a description of it.",
                ),
                (
                    "A signed manifest",
                    "Every file's digest, the data's content hash, the expected output hash, and "
                    "whether re-execution is possible — with the reason when it is not.",
                ),
            ],
        },
        "right": {
            "head": "What the verifier does",
            "items": [
                (
                    "Needs Python, pyarrow and numpy",
                    "Nothing from MAYA, and no network.",
                ),
                (
                    "Bounds the archive first",
                    "Entry count, expanded size, compression ratio and path traversal, before a "
                    "byte is read.",
                ),
                (
                    "Recomputes, then re-executes",
                    "Every file digest, the signature, the data's content hash using the shipped "
                    "encoder, and the model's outputs against the expected hash.",
                ),
                (
                    "Refuses on one changed byte",
                    "A tampered bundle is refused before anything is served, not partly served.",
                ),
            ],
        },
        "note": "maya/services/bundle.py, maya/sdk/offline.py; tests/test_sdk_modes.py::"
        "test_a_tampered_bundle_is_refused_before_anything_is_read and "
        "tests/test_sc2_aged_warrant.py, which reproduces a warrant aged two years in the "
        "fixture.",
    },
    {
        "kind": "table",
        "kicker": "Composite models",
        "title": "A graph of models, governed as one model",
        "intro": "Part 2 made composition a type check. A composite is what MAYA stores when that "
        "check passes: one model, one contract, one parameter set, one warrant, however many "
        "members it holds.",
        "rows": [
            ["Rule", "How it behaves"],
            [
                "Five kinds",
                "ensemble, pipeline, router, residual, hierarchical; trained sequentially, in "
                "parallel or jointly",
            ],
            [
                "One contract",
                "The union of the members' contracts and the combiner's own inputs; two members "
                "wanting one name at different types is refused, naming the attribute",
            ],
            [
                "One parameter set",
                "Namespaced by member alias, with the combiner's own dials bare; a member may "
                "borrow an approved set, frozen",
            ],
            ["One warrant", "Over one feature set, however many members there are"],
            [
                "Maturity capped",
                "At the least mature member's, and the members blocking a promotion are named "
                "rather than left to be inferred",
            ],
            [
                "Bounded and reproducible",
                "Members bound pinned or tracking, nesting capped at four, cycles refused, "
                "opacity propagating from any black-box member, per-member seeds derived from one "
                "seed",
            ],
        ],
        "col_w": [2.1, 9.5],
        "note": "maya/formula/composite.py; tests/test_formula.py::"
        "test_composite_union_maturity_seeds_and_eval and tests/test_sdk_modes.py::"
        "test_a_composite_model_is_re_executed_by_the_bundle_verifier. The clause about the "
        "combiner's own inputs was added because the IFRS 9 study in Part 5 found it missing.",
    },
    {
        "kind": "split",
        "kicker": "Documents, and models that already exist",
        "title": "The specification, the spreadsheet and the vendor's black box",
        "left": {
            "head": "The specification document",
            "items": [
                (
                    "Nine required sections",
                    "Purpose; scope and limitations; mathematical formulation; assumptions; data "
                    "and features used; calibration methodology; validation evidence; known "
                    "weaknesses; change log. Submission is blocked while one is empty.",
                ),
                (
                    "Bound to the mathematics",
                    "Formula blocks render from the tree and references pull from the catalog, so "
                    "the document cannot drift from the thing it describes.",
                ),
                (
                    "A real build, or a labelled draft",
                    "With Tectonic installed it is a true LaTeX build; without it a watermarked "
                    "draft that cannot be approved outside dev.",
                ),
            ],
        },
        "right": {
            "head": "Spreadsheets and vendor models",
            "items": [
                (
                    "A workbook lifted into the mathematics",
                    "Arithmetic, standard functions, named cells and ranges, and lookups over "
                    "constant tables; everything else refused by cell. Checked against the "
                    "workbook's own results and against a headless recalculation.",
                ),
                (
                    "A vendor model registered as what it is",
                    "A declared contract, the vendor's version and documentation, the same review "
                    "and the same warrants — and what cannot be verified marked unverifiable "
                    "rather than omitted.",
                ),
                (
                    "Because completeness is the question",
                    "The firm stays accountable for a model it bought, so leaving it out of the "
                    "inventory is not an option available to anybody.",
                ),
            ],
        },
        "note": "maya/formula/specdoc.py and xlsx.py, maya/services/models.py; "
        "tests/test_typeset.py, tests/test_spreadsheet_libreoffice.py, "
        "tests/test_vendor_models.py. Spreadsheet import is v1 scope and has not been checked "
        "against workbooks saved by Microsoft Excel.",
    },
]

RUNNING = [
    {
        "kind": "divider",
        "num": "4",
        "title": "How it runs",
        "sub": "The machinery around the objects: where the work happens, how a change is priced "
        "before it lands, where the bytes sit, and the checks a build has to pass. Each rule here "
        "is held by a gate rather than by good intentions, because a rule that is only written "
        "down holds until the first deadline.",
        "points": [
            "Six places, four surfaces, one SDK",
            "Workflow as data, and the awkward cases",
            "Workspaces and shadow replay",
            "Lineage and the audit chain",
            "Storage, fragments and content addressing",
            "One database at a time, and no migrations",
            "The artifact ladder and the sandbox",
            "Conformance, and the gate ladder",
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
                "Define a feature, upload or pull its data, preview a resolution before it is "
                "pinned, build a feature set, open a workspace to try a change safely.",
            ),
            (
                "CATALOG",
                "Find and compare",
                "Features and feature sets with their versions, pins, lineage and quality "
                "history; compare two versions; download a pin as tabular or wide.",
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
                "Draw a training warrant, fetch the data, upload dials, seal an execution "
                "warrant, export a bundle — and verify a bundle somebody hands you.",
            ),
            (
                "INBOX",
                "Decide",
                "The review queue, scoped to what you may actually see, with what is overdue, "
                "what is blocked and by which named check.",
            ),
            (
                "ADMIN",
                "Operate",
                "Namespaces and grants, users and sign-on, sources, jobs, events and webhooks, "
                "storage, retention, custody anchors, and a health page naming every resolved "
                "seam.",
            ),
        ],
        "note": "maya/web/routes/: workbench.py, catalog.py, models.py, warrants.py, home.py, "
        "admin.py, lineage.py, workflow.py, workspaces.py. Every page is rendered in "
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
                    "215 endpoints, each with an SDK method and each method with an endpoint, "
                    "checked both ways by a gate.",
                ),
                (
                    "The Python SDK",
                    "Synchronous and asynchronous, with record and replay for tests, and an "
                    "offline mode that serves a bundle and refuses everything the bundle does not "
                    "hold.",
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
        "note": "tools/ci/table_contract.py, sdk_parity.py, contrast.py; tests/test_web.py::"
        "test_web_imports_only_the_sdk; tests/test_browser.py::"
        "test_a_server_paged_table_pages_searches_and_sorts; docs/BENCHMARKS.md for the search "
        "figure.",
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
                    "retired, withdrawn — over the six governed kinds of Part 3.",
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
                    "rejected when the policy is saved, so nothing fails open at approval time.",
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
                    "approval records whose behalf it was on. Five days in review is the shipped "
                    "service level, swept hourly.",
                ),
            ],
        },
        "note": "maya/workflow/ and maya/security/roles.py; tests/test_workflow_matrix.py, "
        "tests/test_delegation.py. The YAML projection round-trips byte-identically for whoever "
        "wants policy in a repository, but the database is the authority.",
    },
    {
        "kind": "split",
        "kicker": "Rehearsing a change",
        "title": "Price the change before anybody approves it",
        "left": {
            "head": "Workspaces",
            "items": [
                (
                    "A copy-on-write branch of the catalog",
                    "Staging a change stores a proposed definition and copies nothing else; "
                    "resolution inside the workspace reads the proposal in place of the version "
                    "it would replace.",
                ),
                (
                    "Approval is the merge",
                    "And a base that moved underneath is a conflict rather than a surprise.",
                ),
                (
                    "A recorded challenger on the review",
                    "A non-binding memo that never approves, never blocks and never writes to a "
                    "sealed object; the reviewer records whether they agreed with it.",
                ),
            ],
        },
        "right": {
            "head": "Shadow replay",
            "items": [
                (
                    "Every dependent warrant re-scored",
                    "The feature set is resolved as it is and as proposed, and both are scored "
                    "with the warrant's own model and dials.",
                ),
                (
                    "Numbers, not a list of names",
                    "Rows added and removed, coverage, median, p95 and worst absolute shift, and "
                    "how much of the book moves past materiality.",
                ),
                (
                    "Bounded, and the bound is stated",
                    "A sample size, a materiality from the model, the namespace or the default, "
                    "and a daily comparison budget — a namespace over budget gets an entry naming "
                    "the shortfall rather than a quiet “nothing moved”.",
                ),
            ],
        },
        "note": "maya/services/workspaces.py; tests/test_workspaces.py. Study 03 in case_studies/ "
        "is this as a worked example: a prepayment change proposed under a live model, and 60% of "
        "the book moves.",
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
                    "flattened, so what a number ultimately reads is a traversal and not a guess.",
                ),
                (
                    "Which is what makes a blast radius honest",
                    "It is computed from edges that were type-checked when they were recorded — "
                    "Part 2's point about the wire that was a drawing.",
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
                    "Timestamping by a third-party authority is opt-in, because it sends the head "
                    "to a third party.",
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
        "note": "maya/services/ops.py (lineage), maya/persistence/repositories/special.py (the "
        "chain), maya/services/custody.py (the anchors); tests/test_custody.py::"
        "test_an_anchor_catches_a_rechained_rewrite and ::"
        "test_a_real_tsa_signature_is_verified_against_its_ca.",
    },
    {
        "kind": "split",
        "kicker": "Storage",
        "title": "Fragments chosen by content, and a hash over values",
        "left": {
            "head": "Fragments",
            "items": [
                (
                    "Boundaries chosen by the content itself",
                    "A row ends a fragment when its own digest, read as an integer, divides by "
                    "the target — so inserting one row leaves every earlier fragment untouched.",
                ),
                (
                    "Counted in rows, not bytes",
                    "Target 512 rows, never fewer than 32 and never more than 8,192.",
                ),
                (
                    "Shared across pins",
                    "Pinning writes only the fragments the store has never seen, so an unchanged "
                    "month costs under 5% of a full pin.",
                ),
            ],
        },
        "right": {
            "head": "The canonical hash",
            "items": [
                (
                    "Over values, never over file bytes",
                    "Column order is ignored, every changed value is noticed, and two pins of "
                    "the same data agree across engine versions and machines.",
                ),
                (
                    "SHA-256, domain-separated",
                    "Row digests, then a fragment hash over the run, then the content hash over "
                    "the schema digest and the fragment hashes in order.",
                ),
                (
                    "MAYA's encoder is the authority",
                    "maya/core/canonical.py is the specification of the hash; the fast path "
                    "computes it a column at a time and is tested equal to it.",
                ),
                (
                    "And pinning is a saga, because two stores cannot commit together",
                    "Fragments are written, the hash is recomputed from what was actually "
                    "written, and only then is the metadata committed. A half-written pin is made "
                    "invisible by a reaper — invisible, not impossible, and the specification "
                    "says so.",
                ),
            ],
        },
        "note": "maya/core/canonical.py, chunker.py, maya/storage/lake.py; "
        "tests/test_features.py::test_sc1_repin_is_byte_identical_and_changed_data_is_not and "
        "::test_sc12_unchanged_month_costs_under_five_percent; specification §15.3 and §28.11 for "
        "the accepted risk. Pin write throughput 59.7 MB/s on one worker against a 50 MB/s target.",
    },
    {
        "kind": "bullets",
        "kicker": "Persistence",
        "title": "One database at a time, two generated schema files, no migrations",
        "items": [
            (
                "SQLite in the shipped configuration; PostgreSQL by setting one key",
                "Never both, and never mixed. Several web processes on one node require "
                "PostgreSQL, and MAYA refuses them over SQLite rather than running them unsafely.",
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
                "half-applied migration — and the upgrade is a procedure somebody has to run. "
                "The trade is stated rather than hidden.",
            ),
            (
                "The upgrade path is export, recreate, import",
                "The estate export reads the database as it stands, so it still works across the "
                "schema change that made it necessary, and a column it cannot fill is named "
                "rather than defaulted.",
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
        "intro": "A model may carry uploaded Python. It is treated as hostile until proved "
        "otherwise, and the ladder stops at the first failing rung and records the rest as not "
        "run — so a report never implies a check it did not perform.",
        "rows": [
            ["Rung", "What it checks"],
            [
                "1  parse",
                "The source parses; a linter runs where it is installed, and whether it ran is "
                "recorded rather than assumed",
            ],
            [
                "2  entry point",
                "The declared class implements the interface MAYA will call: fit and predict, "
                "with the signatures it expects",
            ],
            [
                "3  import allowlist",
                "Numeric and data libraries only — math, statistics, itertools, numpy, pandas, "
                "polars, pyarrow, scipy, scikit-learn, statsmodels and a few more",
            ],
            [
                "4  static ban",
                "No open, eval, exec, compile, dynamic import or dunder attribute access; no os, "
                "sys, subprocess, socket, pathlib, pickle or threading",
            ],
            [
                "5  smoke run",
                "One run in the sandbox against a sample, under CPU, memory and wall-clock caps",
            ],
            [
                "6  determinism",
                "The smoke run twice with the same seed, outputs compared — a mismatch is "
                "recorded as a warning, not a refusal",
            ],
        ],
        "col_w": [1.9, 9.7],
        "note": "maya/formula/artifact.py and maya/security/sandbox.py; tests/test_sandbox.py, "
        "tests/test_sandbox_linux.py. Rungs 1–5 decide the verdict. The tier is strong on Linux "
        "only when a probe child fails to escape a bubblewrap jail with a seccomp filter and a "
        "cgroup scope, and it is stamped on every artifact validated under it.",
    },
    {
        "kind": "split",
        "kicker": "Is the code the mathematics?",
        "title": "Differential testing, and what a black box forfeits",
        "intro": "The model has two descriptions: the tree MAYA holds, and the Python somebody "
        "uploaded. Nothing guarantees they agree, so MAYA compares them on numbers rather than "
        "asking anybody to assert it.",
        "left": {
            "head": "Conformance testing",
            "items": [
                (
                    "The comparison",
                    "The uploaded code is run against MAYA's own evaluation of the documented "
                    "mathematics on sampled inputs, to a relative tolerance of 1e-9.",
                ),
                (
                    "Counterexamples, not a verdict",
                    "Up to ten disagreeing rows with the expected and the actual value, so the "
                    "argument is about numbers.",
                ),
                (
                    "Tied to the exact artifact",
                    "A version with code cannot advance until conformance has run against that "
                    "artifact hash and agreed everywhere sampled.",
                ),
                (
                    "Honest about itself, in its first four words",
                    "Sampled agreement is not proof, and MAYA cannot know whether a feature set "
                    "is representative. An undeclared dial is placed off-centre inside its bounds "
                    "so a comparison cannot miss a bug by landing on a round number.",
                ),
            ],
        },
        "right": {
            "head": "Declared black boxes",
            "items": [
                (
                    "Registered, not excluded",
                    "With the estimate and the architecture declared, the input contract "
                    "enforced, and warrants that behave exactly as they do for anything else.",
                ),
                (
                    "Conformance is skipped and says so",
                    "There is no documented closed form to test against, and the report states "
                    "that rather than passing quietly.",
                ),
                (
                    "Blind scoring is refused by name",
                    "Scoring evaluates the mathematics in process and never runs the uploaded "
                    "artifact, so for a declared black box there is nothing to score.",
                ),
                (
                    "Covenants become the control",
                    "For an opaque model they are the only one available, which is exactly where "
                    "Part 2 said the review effort belongs.",
                ),
            ],
        },
        "note": "maya/formula/conformance.py and maya/services/models.py; ADR-007. Part 5 carries "
        "two studies through on these terms: a card-fraud network as a declared black box, and a "
        "yield curve whose planted bug only conformance testing can see.",
    },
    {
        "kind": "table",
        "kicker": "Held by gates",
        "title": "One command, and never a remembered list",
        "intro": "Every architectural rule on the last ten slides is enforced by a program rather "
        "than by review, and each rung has been shown to catch a planted fault. A rule that is "
        "only written down holds until the first deadline.",
        "rows": [
            ["Stage", "What it checks"],
            [
                "Static, every run",
                "Lint; strict typing of maya/services; file size; both import boundaries; import "
                "cycles; public names per module; seam imports; SDK public symbols; version "
                "single source; no secrets; the table contract; colour contrast; SDK↔API parity "
                "for 215 endpoints; UI↔SDK parity; the API contract snapshot; protocol literals; "
                "a security linter; schema drift",
            ],
            [
                "--tests",
                "The whole suite under a 90% line-coverage floor; 92.9% at this release",
            ],
            [
                "--fallback",
                "The suite again with every optional accelerator pinned to its pure-Python "
                "fallback, so the fallback is a tested path rather than a hope",
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

SLIDES = OBJECTS + RUNNING
