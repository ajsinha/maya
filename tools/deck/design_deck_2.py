"""
The system design deck, parts 4–6: models, warrants and evidence, and the
platform that governs them — ending with what is not built and where to read on.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

MODELS = [
    {
        "kind": "divider",
        "num": "4",
        "title": "Models",
        "sub": "A model is a compute kernel with four faces versioned together: its mathematics, its code, its parameters and its specification document.",
        "points": [
            "The formula IR",
            "The compute-kernel wizard",
            "Code artifacts and the sandbox",
            "Specification documents",
            "Conformance, and declared black boxes",
            "Composite models",
            "Spreadsheets and vendor models",
        ],
    },
    {
        "kind": "split",
        "kicker": "The formula IR",
        "title": "Mathematics as a typed expression tree",
        "left": {
            "head": "Written three ways, stored once",
            "items": [
                (
                    "Parsed",
                    "One parser reads both LaTeX and Python-ish text, including LaTeX's implicit multiplication; anything it cannot read is refused with the position named.",
                ),
                (
                    "Lifted",
                    "From an uploaded Python function by AST analysis, or from a workbook's formula graph.",
                ),
                (
                    "Four node kinds, three roles",
                    "op, ref, const, param — and every input is a feature, a parameter or a constant. The parameters are exactly what training fills.",
                ),
                (
                    "Declared black box",
                    "Where there is no closed form the IR carries an opaque node that must state what the model estimates and its architecture, or it is refused.",
                ),
            ],
        },
        "right": {
            "head": "And then made to do work",
            "items": [
                ("Rendered", "Back to LaTeX, for the specification document."),
                (
                    "Diffed mathematically",
                    "“The discount factor changed from continuous to simple compounding”, rather than a text diff (tests/test_formula.py::test_diff_detects_compounding_change).",
                ),
                (
                    "Evaluated",
                    "By MAYA's own evaluator over twenty-three typed operators, and by emitted reference code tested equal to it.",
                ),
                (
                    "Hashed",
                    "The hash ignores LaTeX spelling and notices mathematics (test_hash_ignores_latex_but_not_math).",
                ),
            ],
        },
        "note": "maya/formula/: ir.py, parse.py, latex.py, evaluate.py, diff.py, codegen.py, specdoc.py. A model version is minted when the IR hash, the artifact hash or the input contract changes. Joint constraints such as a GARCH model's alpha + beta < 1 live on the IR and each must carry the reason it exists.",
    },
    {
        "kind": "flow",
        "kicker": "The compute-kernel wizard",
        "title": "Translate the mathematics before anything is committed",
        "steps": [
            (
                "Write",
                "The formula as LaTeX or as plain text, and say which symbols are parameters",
            ),
            ("Translate", "MAYA parses it into the typed tree, or refuses with the position"),
            (
                "Read back",
                "The tree, the LaTeX MAYA renders it as, the inputs with the role each was given, and the intermediates in order",
            ),
            ("Take the function", "One portable function, or the full reference module"),
        ],
        "box_h": 2.0,
        "items": [
            "Stateless by design: it reads nothing and writes nothing, so whoever wrote the mathematics can see what MAYA made of it before a model version exists to attach it to. The alternative is finding out at registration.",
            "The emitted kernel is one self-contained function, def compute(X, params), returning one entry per row. Imports and any helper live inside the function body, and it depends on numpy alone unless the formula uses a normal distribution.",
            "The same parser and the same generator serve the registration path, so what the wizard shows is what a registered version would hold, not a preview of it.",
        ],
        "note": "Web page /models/kernel; API POST /formula/kernel; SDK client.models.kernel; maya/services/models.py (kernel) and maya/formula/codegen.py (to_python_kernel, to_python). Worked examples ship with the page: Black–Scholes, a logistic probability of default, and a Nelson–Siegel curve.",
    },
    {
        "kind": "table",
        "kicker": "Code artifacts",
        "title": "Six rungs, one refusal each, then a declared sandbox tier",
        "rows": [
            ["Rung", "What it checks"],
            [
                "1  parse",
                "The source parses; a linter runs where it is installed, and whether it ran is recorded rather than assumed",
            ],
            [
                "2  entry point",
                "The declared class implements the interface: fit(self, X, y, ctx) and predict(self, X, params, ctx)",
            ],
            [
                "3  import allowlist",
                "Numeric and data libraries only — math, statistics, itertools, numpy, pandas, polars, pyarrow, scipy, scikit-learn, statsmodels and a few more",
            ],
            [
                "4  static ban",
                "No open, eval, exec, compile, dynamic import, dunder attribute access; no os, sys, subprocess, socket, pathlib, pickle, threading",
            ],
            [
                "5  smoke run",
                "One run in the sandbox against a sample, under CPU, memory and wall-clock caps",
            ],
            [
                "6  determinism",
                "The smoke run twice with the same seed, outputs compared — a mismatch is recorded as a warning, not a refusal",
            ],
        ],
        "col_w": [1.9, 9.7],
        "note": "maya/formula/artifact.py and maya/security/sandbox.py. The ladder stops at the first failing rung and records the rest as not run, so a report never implies a check it did not perform; only rungs 1–5 gate the verdict. The tier is strong on Linux only when a probe child fails to escape a bubblewrap jail with seccomp and a cgroup v2 scope, and it is recorded on every artifact validated under it (tests/test_sandbox.py, tests/test_sandbox_linux.py).",
    },
    {
        "kind": "bullets",
        "kicker": "Specification documents",
        "title": "A LaTeX document per model version, bound to the IR",
        "items": [
            (
                "Nine required sections, and submission is blocked while one is empty",
                "Purpose; scope and limitations; mathematical formulation; assumptions; data and features used; calibration methodology; validation evidence; known weaknesses; change log (tests/test_warrants.py::test_model_submission_is_blocked_by_an_incomplete_spec).",
            ),
            (
                "Formula blocks are pulled from the IR, not retyped",
                "The \\mayaformula macro renders the mathematics from the tree and \\mayaref pulls catalog content, so the document cannot drift from the implementation it describes.",
            ),
            (
                "True builds with Tectonic, labelled drafts without it",
                "Without Tectonic MAYA renders a watermarked draft, and typeset.require_true_build forbids approval on a draft outside dev (maya/core/typeset.py, tests/test_typeset.py).",
            ),
            (
                "Air-gapped sites need one extra step",
                "Tectonic downloads its TeX bundle on first use, so an air-gapped server must be given a cached bundle.",
            ),
        ],
        "note": "maya/formula/specdoc.py. The document is a version of the model, governed like the rest of it: versioned, diffed, approved, audited.",
    },
    {
        "kind": "split",
        "kicker": "Is the code the mathematics?",
        "title": "Conformance testing, and what a black box forfeits",
        "left": {
            "head": "Differential testing against the document",
            "items": [
                (
                    "The comparison",
                    "The uploaded artifact's predict is run against MAYA's own evaluation of the documented IR on sampled inputs, to a relative tolerance of 1e-9.",
                ),
                (
                    "Counterexamples, not a verdict",
                    "Up to ten disagreeing rows are reported with the expected and actual value, so the argument is about numbers rather than opinions.",
                ),
                (
                    "Tied to the artifact hash",
                    "A version with code cannot advance until conformance has run against that exact artifact and agreed everywhere sampled.",
                ),
                (
                    "Honest about what it is",
                    "The report says so itself: sampled agreement is not proof, and MAYA cannot know whether a feature set is representative.",
                ),
            ],
        },
        "right": {
            "head": "Declared black boxes",
            "items": [
                (
                    "Registered, not excluded",
                    "A model kind of its own, with the estimate and the architecture declared and the input contract enforced as usual.",
                ),
                (
                    "Conformance is skipped, and says so",
                    "There is no documented closed form to test against, and the report states that rather than passing quietly.",
                ),
                (
                    "Blind scoring is refused by name",
                    "“A declared black box cannot be scored by MAYA”: scoring evaluates the formula IR in process, never the uploaded artifact.",
                ),
                (
                    "Covenants become the control",
                    "For an opaque model they are the only one available, so they are where the review effort goes.",
                ),
            ],
        },
        "note": "maya/formula/conformance.py and maya/services/models.py; ADR-007 states the one runtime exception MAYA concedes and no more. An undeclared parameter is placed off-centre inside its bounds for a differential run, so a comparison cannot miss a bug by landing on a round number.",
    },
    {
        "kind": "table",
        "kicker": "Composite models",
        "title": "A graph of member models, governed as one model",
        "rows": [
            ["Rule", "How it behaves"],
            [
                "Kinds",
                "ensemble, pipeline, router, residual, hierarchical; trained sequentially, in parallel or jointly",
            ],
            [
                "One contract",
                "The union of the members' contracts and the combiner's own inputs; two members wanting one name at different types is refused, naming the attribute",
            ],
            [
                "One parameter set",
                "Namespaced by member alias — base.sigma — with the combiner's own parameters bare; a member may borrow an approved set, frozen",
            ],
            [
                "Maturity",
                "Capped at the least mature member's, and the members blocking a promotion are named rather than left to be inferred",
            ],
            [
                "Structure",
                "A member is bound pinned or tracking; nesting is capped at four; cycles are refused; opacity propagates from any black-box member",
            ],
            [
                "Reproducible",
                "Per-member seeds derived from one seed; a bundle re-executes the whole composite, or states why it cannot",
            ],
        ],
        "col_w": [1.9, 9.7],
        "note": "maya/formula/composite.py and maya/formula/evaluate.py; tests/test_formula.py::test_composite_union_maturity_seeds_and_eval, tests/test_sdk_modes.py::test_a_composite_model_is_re_executed_by_the_bundle_verifier. One parameter set per composite is a recorded decision, not an accident.",
    },
    {
        "kind": "split",
        "kicker": "Models that already exist",
        "title": "Spreadsheets and vendor models, under the same wrapper",
        "left": {
            "head": "Spreadsheets as models",
            "items": [
                (
                    "Lifted into the IR",
                    "Arithmetic, standard functions, named cells and ranges, and VLOOKUP or HLOOKUP over constant tables.",
                ),
                (
                    "Everything else refused by cell",
                    "Named, never approximated with the nearest thing that parses.",
                ),
                (
                    "Checked twice",
                    "Against the workbook's own cached results, and against LibreOffice Calc recalculating it headless.",
                ),
                ("Not checked", "Workbooks saved by Microsoft Excel."),
            ],
        },
        "right": {
            "head": "Vendor models",
            "items": [
                (
                    "A kind of its own",
                    "A declared input contract, plus the vendor's name, product, version and supplied documentation.",
                ),
                (
                    "The same review and the same warrants",
                    "Contract validation, leakage certificate, checksum cycle, sealing.",
                ),
                (
                    "What cannot be verified is marked",
                    "The bundle says it cannot re-execute, rather than omitting the model from the inventory.",
                ),
                (
                    "Why bother",
                    "Completeness is what an examiner asks for, and the firm stays accountable for a model it bought.",
                ),
            ],
        },
        "note": "maya/formula/xlsx.py (tests/test_spreadsheet.py, tests/test_spreadsheet_libreoffice.py) and maya/services/models.py (tests/test_vendor_models.py). Spreadsheet import is v1 scope and the README says where it stops.",
    },
]

WARRANTS = [
    {
        "kind": "divider",
        "num": "5",
        "title": "Warrants and evidence",
        "sub": "A warrant is a named, versioned, permissioned licence to compute. The evidence around it is built to survive leaving the building.",
        "points": [
            "The training warrant and the checksum cycle",
            "The leakage certificate and the escrowed holdout",
            "Execution warrants, covenants and limits",
            "Bundles, and the verifier inside them",
            "Custody anchoring and the licence algebra",
        ],
    },
    {
        "kind": "flow",
        "kicker": "Training warrant",
        "title": "The checksum cycle that turns paperwork into a control",
        "steps": [
            (
                "Draw",
                "An approved model version against a pinned feature set; the input contract is checked and every miss is listed",
            ),
            ("Certify", "A signed leakage certificate is issued with the warrant, or refuses it"),
            ("Download", "Train and validation only; who, when, and the content hash are recorded"),
            (
                "Upload",
                "Parameters checked against that hash, their declared bounds, and any joint constraint",
            ),
            ("Seal", "Approval by policy; every referenced object becomes undeletable"),
        ],
        "box_h": 2.1,
        "items": [
            "Parameters fitted on data that does not match a checksum MAYA issued are flagged unverified_data and cannot be approved without an explicit written justification — which is how a judgement, as opposed to a fit, gets recorded honestly.",
            "Joint constraints catch what per-parameter bounds cannot: a violation is reported as the terms, their values, the computed total, and the reason the constraint exists.",
            "A warrant defaults to a 70 / 15 / 15 split, seed 42, an escrowed holdout and a year's expiry, all of them overridable and all of them recorded.",
            "Proved by tests/test_warrants.py::test_the_checksum_cycle_seal_score_execute_and_bundle and ::test_contract_mismatch_is_refused_listing_every_attribute.",
        ],
        "note": "maya/services/warrants.py. A warrant's read-time status — sealed, expired, revoked — is computed from its dates, so nobody has to remember to move a state.",
    },
    {
        "kind": "split",
        "kicker": "Look-ahead",
        "title": "The leakage certificate and the escrowed holdout",
        "left": {
            "head": "Leakage certificate",
            "items": [
                (
                    "The rule",
                    "Every row's knowledge time is at or before its event date plus the declared lag, one day by default.",
                ),
                (
                    "Three verdicts",
                    "certified; certified_with_exceptions, where every exception carries a justification; refused.",
                ),
                (
                    "Signed, with examples",
                    "Rows examined, the violations with up to twenty example rows, and each exception's reason. Without a signing backend it says it is unsigned and why.",
                ),
                (
                    "Proved",
                    "tests/test_warrants.py::test_leakage_certificate_refuses_late_knowledge.",
                ),
            ],
        },
        "right": {
            "head": "Escrowed holdout",
            "items": [
                (
                    "The default",
                    "The test partition is hashed and its row count fixed when the warrant is drawn, and it is not included in a download.",
                ),
                (
                    "Blind scoring",
                    "MAYA re-derives the split, refuses if the escrowed set has moved, evaluates the formula IR and returns metrics only.",
                ),
                (
                    "Counted",
                    "Every attempt is numbered on the warrant, because “scored forty times, best reported” is a fact a reviewer should be able to see.",
                ),
                (
                    "The one runtime exception",
                    "ADR-007: MAYA does not run models, except to score — and it scores the mathematics, not the artifact.",
                ),
            ],
        },
        "note": "maya/services/warrants.py. The certificate examines the rows the resolved frame carries a knowledge time for; a row with none is not examined, and the certificate says how many it read.",
    },
    {
        "kind": "table",
        "kicker": "Execution warrants",
        "title": "A live instrument, not a perpetual document",
        "rows": [
            ["Control", "Behaviour"],
            [
                "Drawn from",
                "A training warrant and an approved parameter set, or straight from a model that takes no parameters",
            ],
            [
                "Environments",
                "dev, uat, prod — each permitted explicitly, and an approval may be required only for prod",
            ],
            [
                "Covenants",
                "input_null_rate, input_range, input_psi, output_range, max_rows_per_day, staleness_days. A breach suspends the warrant at once, records a custody event and notifies the owner",
            ],
            [
                "Population drift",
                "input_psi computes a population stability index against a baseline fixed when the warrant was drawn, so the baseline cannot move later. Default ceiling 0.25 over ten bins",
            ],
            [
                "Limits",
                "max_calls_per_day, max_rows_per_call, max_rows_per_day — these throttle and record overage; they do not suspend",
            ],
            [
                "Reinstatement",
                "By the model owner or an administrator, with a written reason. Expiry and revocation fail every consuming call closed, naming the covenant or the contact",
            ],
            [
                "Offline use",
                "Permitted, and both the copy and the warrant are labelled unattested for good",
            ],
        ],
        "col_w": [2.0, 9.6],
        "note": "maya/services/execution.py; tests/test_security_regressions.py::test_each_covenant and ::test_execution_limits. A covenant on a model with more than one output must name the output it watches, or the warrant is refused: a covenant with nothing to compare against is worse than none.",
    },
    {
        "kind": "split",
        "kicker": "Evidence that leaves the building",
        "title": "The bundle, and the verifier inside it",
        "left": {
            "head": "What is in the archive",
            "items": [
                (
                    "The subject",
                    "Warrant, model version, formula IR and member IRs, the specification source, the code artifact and its report, parameters, the leakage certificate.",
                ),
                (
                    "The data and the environment",
                    "The training frame as Parquet, the feature-set definition and the pin's manifest with its member pins, the Python version and the resolved backends.",
                ),
                (
                    "The definition of the hash",
                    "MAYA's own canonical encoder and fragment chunker ship inside the bundle, because they are the definition and not a description of it.",
                ),
                (
                    "A signed manifest",
                    "Every file's digest, the data's content hash, the expected output hash, and whether re-execution is possible — with the reason when it is not.",
                ),
            ],
        },
        "right": {
            "head": "What verify.py does",
            "items": [
                (
                    "Needs Python, pyarrow and numpy",
                    "Nothing from MAYA, and no network.",
                ),
                (
                    "Bounds the archive first",
                    "Entry count, expanded size, compression ratio and path traversal are checked before a byte is read.",
                ),
                (
                    "Recomputes, then re-executes",
                    "Every file digest, the signature where a crypto library is present, the data's content hash from the shipped encoder, and the model's outputs against the expected hash.",
                ),
                (
                    "Refuses on one changed byte",
                    "A tampered bundle is refused before anything is served, not partly served.",
                ),
            ],
        },
        "note": "maya/services/bundle.py and maya/sdk/offline.py; tests/test_sdk_modes.py::test_a_tampered_bundle_is_refused_before_anything_is_read, tests/test_sc2_aged_warrant.py. Opening a bundle through the SDK evaluates the signed IR and never imports the reference code the bundle carries; anything the bundle does not hold is refused by name.",
    },
    {
        "kind": "split",
        "kicker": "Custody and terms",
        "title": "An audit chain that anchors, and vendor terms that propagate",
        "left": {
            "head": "The audit chain",
            "items": [
                (
                    "Hash-chained per entry",
                    "Each row's digest covers the previous digest and the entry's own fields, so a rewritten row breaks every row after it.",
                ),
                (
                    "Anchored out of the database",
                    "The chain head is signed, appended to a file and emitted as an event, hourly. RFC 3161 timestamping is opt-in because it sends the head to a third party.",
                ),
                (
                    "A timestamp is only as good as its check",
                    "The authority's own signature is verified against its CA certificate when one is configured, and left to the operator when it is not.",
                ),
                (
                    "It refuses to certify tampering",
                    "A chain that does not verify is not anchored. Verification names the sequence number where it broke.",
                ),
            ],
        },
        "right": {
            "head": "The licence algebra",
            "items": [
                (
                    "Terms travel with derivations",
                    "A derived object inherits the most restrictive of its sources' terms rather than the nearest one to hand.",
                ),
                (
                    "A breach is a refusal",
                    "Named: which source, and which clause.",
                ),
                (
                    "Proved",
                    "tests/test_custody.py::test_an_anchor_catches_a_rechained_rewrite and ::test_a_real_tsa_signature_is_verified_against_its_ca.",
                ),
                (
                    "The honest limit",
                    "An anchor is only as external as the file it is written to; point it at off-host or write-once storage.",
                ),
            ],
        },
        "note": "maya/persistence/repositories/special.py (the chain), maya/services/custody.py (the anchors), maya/security/licence.py (the algebra). On PostgreSQL an advisory lock serialises appends, so two writers cannot fork the chain.",
    },
]

PLATFORM = [
    {
        "kind": "divider",
        "num": "6",
        "title": "Governance and platform",
        "sub": "Workflow as data, one authorization function, one door to the database, one client library — each held by a gate rather than by good intentions.",
        "points": [
            "Workflow policy, and break-glass",
            "Workspaces and shadow replay",
            "Authorization and authentication",
            "Architecture, held by gates",
            "Persistence without migrations",
            "The gate ladder",
            "What is not built",
            "Where to read on",
        ],
    },
    {
        "kind": "split",
        "kicker": "Workflow",
        "title": "Policy is data, and governed like everything else",
        "left": {
            "head": "The engine",
            "items": [
                (
                    "One state machine, six object types",
                    "draft, in_review, changes_requested, approved, published, deprecated, retired, withdrawn — over feature, feature-set and model versions, parameter sets and both warrants.",
                ),
                (
                    "A transition is a record",
                    "Which states it leaves, the capability it needs, the roles allowed, the named checks to pass, and the approvals required as role and count.",
                ),
                (
                    "Validated when it is edited",
                    "An unreachable state, an unsatisfiable approval or an unknown condition is refused at edit time, so nothing fails open at approval time.",
                ),
                (
                    "Governed",
                    "A policy edit is versioned, diffed and approved, and its YAML projection round-trips byte-identically for whoever wants it in a repository.",
                ),
            ],
        },
        "right": {
            "head": "The awkward cases, handled",
            "items": [
                (
                    "Segregation of duties",
                    "Three levels — none, two_person, strict — shipped as the small_team, standard and regulated namespace presets. Under strict nobody who created, submitted or updated an object may approve it.",
                ),
                (
                    "Break-glass",
                    "Administrators only, a written reason of real length, the event marked forced, audited as its own action, and the owner notified whether or not they subscribed.",
                ),
                (
                    "Delegation",
                    "Only an approver may delegate, never to themselves, within dates and optionally by object type; the approval records who it was made on behalf of.",
                ),
                (
                    "Escalation",
                    "Five days in review is the shipped service level; an hourly sweep notifies the namespace owner once per overdue item, and warns thirty days before a warrant expires.",
                ),
            ],
        },
        "note": "maya/workflow/ (engine.py, policy.py, default_policies.yaml), maya/security/roles.py, maya/jobs/scheduler.py; tests/test_workflow_and_estate.py, tests/test_workflow_matrix.py, tests/test_delegation.py.",
    },
    {
        "kind": "split",
        "kicker": "Rehearsing a change",
        "title": "Workspaces, and a replay that reports numbers",
        "left": {
            "head": "Workspaces",
            "items": [
                (
                    "Copy-on-write over the catalog",
                    "Staging a change stores a proposed definition and copies nothing else; resolution inside the workspace reads the proposal in place of the version it would replace.",
                ),
                (
                    "Approval is the merge",
                    "And a base that moved underneath is a conflict, not a surprise.",
                ),
                (
                    "The recorded challenger",
                    "A non-binding memo attached to the review, which never approves, never blocks and never writes to a sealed object; the reviewer records whether they agreed.",
                ),
            ],
        },
        "right": {
            "head": "Shadow replay",
            "items": [
                (
                    "Every dependent warrant, re-scored",
                    "The feature set is resolved twice — as it is, and as proposed — and scored with the warrant's own model and parameters.",
                ),
                (
                    "Numbers, not a list of names",
                    "Rows added and removed, coverage, median, p95 and worst absolute shift, the worst row, and how much of the book moves past materiality.",
                ),
                (
                    "Bounded and stated",
                    "5,000 sampled rows, materiality from the model, the namespace or the default, and a daily row-comparison budget per namespace.",
                ),
                (
                    "A ceiling never says “nothing moved”",
                    "A namespace over budget gets an entry naming the shortfall, and the budget is spent against the audit log.",
                ),
            ],
        },
        "note": "maya/services/workspaces.py and maya/assistant/; tests/test_workspaces.py, tests/test_assistant.py. Study 03 in case_studies/ is this slide as a worked example: 60% of a mortgage book moves, priced before anyone approves the change.",
    },
    {
        "kind": "split",
        "kicker": "Access",
        "title": "One authorization function, and who you are",
        "left": {
            "head": "Authorization",
            "items": [
                (
                    "can(principal, action, object)",
                    "Nothing in the UI, the API, the SDK or the CLI goes around it.",
                ),
                (
                    "Roles are a ceiling",
                    "An access list cannot grant what the role does not permit.",
                ),
                (
                    "List order",
                    "Deny wins, then the most specific grant; separation of duties comes from the namespace preset.",
                ),
                (
                    "Grant conditions",
                    "Row filters, column masks and time bounds, applied on live and pinned data alike.",
                ),
            ],
        },
        "right": {
            "head": "Authentication",
            "items": [
                (
                    "Passwords",
                    "The derivation function and its parameters are stored with each hash and rehash upward on sign-in; lockout after repeated failures.",
                ),
                ("API keys", "Scoped, bound to an environment, expiring, revocable."),
                (
                    "Single sign-on",
                    "OIDC or SAML 2.0 with signed requests, logout in both directions; TOTP codes and WebAuthn keys as second factors.",
                ),
                (
                    "Principal cache",
                    "A session's principal is reused for two seconds, because one page makes several internal calls; a revocation applies at once locally and within that window elsewhere.",
                ),
            ],
        },
        "note": "maya/security/authz.py, roles.py, conditions.py; maya/services/auth.py, sso.py. Checked as a full role × action × state matrix, and every route is exercised as anonymous, as no-role and as administrator (tests/test_authz_matrix.py, tests/test_api_contract.py).",
    },
    {
        "kind": "table",
        "kicker": "Architecture",
        "title": "A layered modular monolith, with its boundaries enforced",
        "rows": [
            ["Rule", "How it holds"],
            [
                "The UI is an SDK client",
                "Nothing under maya.web imports anything but maya.sdk, and a gate plants a violation to prove it fails (tests/test_web.py::test_web_imports_only_the_sdk)",
            ],
            [
                "One door to the database",
                "No sqlalchemy import outside maya.persistence (tools/ci/import_boundaries.py)",
            ],
            [
                "SDK and API in parity",
                "Every one of 215 endpoints has an SDK method and every method an endpoint, checked both ways (tools/ci/sdk_parity.py)",
            ],
            [
                "Every table from one macro",
                "Paginated, searchable, sortable, exportable; a crawler gate refuses any other table (tools/ci/table_contract.py)",
            ],
            [
                "One startup script",
                "run_maya_web.py; several web processes on one node require PostgreSQL, and MAYA refuses them over SQLite",
            ],
            [
                "Jobs live in the database",
                "SKIP LOCKED on PostgreSQL, an in-process queue on SQLite; idempotent, cancellable, retried, and the same code either way",
            ],
        ],
        "col_w": [2.4, 9.2],
        "note": "maya/: core, config, persistence, security, resolution, formula, workflow, storage, services, jobs, assistant, observability, api, sdk, web, cli, testing. maya_delta/ sits beside it with no MAYA domain knowledge at all.",
    },
    {
        "kind": "bullets",
        "kicker": "Persistence",
        "title": "Two generated schema files, and no migrations",
        "items": [
            (
                "One typed metadata, two DDL files",
                "maya/persistence/schema/sqlite.sql and postgresql.sql are generated from the SQLAlchemy models; a gate regenerates both and fails on any diff, and a planted hand-edit is shown to trip it.",
            ),
            (
                "A mismatched database is refused at startup",
                "It is never upgraded in place (tests/test_workflow_and_estate.py::test_schema_mismatch_refuses_to_start).",
            ),
            (
                "The upgrade path is export, recreate, import",
                "The estate export reads the database as it is, so it still works across the schema change that made it necessary; a column it cannot fill is named rather than defaulted.",
            ),
            (
                "SQLite in the shipped configuration, PostgreSQL by setting one key, never mixed",
                "The whole suite has run on both; PostgreSQL 16, 17 and 18 so far, and not 14 or 15, which is the documented floor.",
            ),
        ],
        "note": "maya/persistence/; tools/ci/gen_schema.py. No migration tool means no half-applied migration, and it means the upgrade is a procedure somebody has to run — the trade is stated, not hidden.",
    },
    {
        "kind": "table",
        "kicker": "The gate ladder",
        "title": "One command, and never a remembered list",
        "rows": [
            ["Stage", "Gates"],
            [
                "Static, every run",
                "Lint; strict typing of maya/services; file size; both import boundaries; import cycles; public names per module; seam imports; SDK public symbols; version single source; no secrets; table contract; colour contrast; SDK↔API parity; UI↔SDK parity; the API contract snapshot; protocol literals; a security linter; schema drift",
            ],
            ["--tests", "The whole suite under a 90% line-coverage floor; 92.9% at this release"],
            ["--fallback", "The suite again with every Type A seam pinned to its pure fallback"],
            ["--security", "A dependency audit, and the sandbox escape tests"],
            ["--bench", "A benchmark regression of more than 10% needs a written note"],
        ],
        "col_w": [1.7, 9.9],
        "note": "tools/ci/gates.py. Each rung is shown to catch a planted fault (tests/test_api_and_gates.py, tests/test_gate_ladder.py). The ladder runs locally and in the pre-commit hook; there is no hosted CI, by decision.",
    },
    {
        "kind": "bullets",
        "kicker": "What is not built",
        "title": "Known gaps, named here rather than found later",
        "items": [
            "Only Linux is exercised, by decision, so SC-14 is not met and the Windows and macOS code paths have never run.",
            "SC-3, 200 users on one node, is not met reliably: three runs gave p95 0.34 s, 0.22 s and 0.43 s against 0.3 s.",
            "Feature-set operators beyond extend, subscriptions, enforced quotas, upload size limits, the SDK's object handles and the review screen's semantic diff are partly built or not built; the specification audit ranks every gap by what it costs a user.",
            "Resolution, search and the capacity targets were measured on SQLite only; nothing in §24.3 has been run on PostgreSQL and the per-pod figure has not been measured.",
            "A delta source is accepted by the catalog and no test in the suite exercises it.",
            "The assistant's hosted provider is tested against a stub of its client only; SAML back-channel logout is not supported.",
            "SC-9 has not been timed with a real person, there has been no external security review, and the restore drill has been performed on a small estate only.",
        ],
        "note": "README “Status”, the plan's milestone notes and docs/audit/ state each of these where it was promised. Of about 540 specification requirements, 195 are built and tested, 28 built but untested, 123 partly built and 84 not built.",
    },
    {
        "kind": "bullets",
        "kicker": "Where to read on",
        "title": "Everything on these slides has a source you can open",
        "items": [
            ("Specification", "docs/MAYA_Requirements_and_Design.md — the authority for every §."),
            (
                "Plan",
                "docs/IMPLEMENTATION_PLAN.md — each milestone with what it delivered and what it did not.",
            ),
            (
                "Measurements",
                "docs/BENCHMARKS.md, from the unedited result files in docs/benchmarks/.",
            ),
            (
                "Decisions and procedures",
                "docs/adr/ and docs/runbooks/, including the restore drill as performed.",
            ),
            (
                "Worked models",
                "case_studies/ — nine complete studies, each with its theory, its mathematics and the numbers from a recorded run.",
            ),
            ("Run it", "python run_maya_web.py, then python -m maya.cli feature quick prices.csv."),
        ],
        "note": "Every claim in this deck names a module or a test. Where a claim has neither, it is in the “what is not built” slide instead.",
    },
]

SLIDES = MODELS + WARRANTS + PLATFORM
