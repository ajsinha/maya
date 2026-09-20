"""
The capabilities deck, parts 4–6: governance, one model carried end to end, and
what MAYA does not do.

Part 5 walks ``case_studies/06-ifrs9-expected-credit-loss/`` from a blank
namespace to a suspended execution warrant, including everywhere MAYA refused
the work. Every figure is from that study's recorded run.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

GOVERNANCE = [
    {
        "kind": "divider",
        "num": "4",
        "title": "Governance that holds",
        "sub": "Workflow you operate rather than configure in a file; a change rehearsed before it lands; and a warrant that is a live licence rather than a certificate in a drawer.",
        "points": [
            "Workflow, and the awkward cases",
            "Workspaces and shadow replay",
            "The checksum cycle",
            "Execution warrants and covenants",
            "Evidence that leaves the building",
        ],
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
                    "draft, in_review, changes_requested, approved, published, deprecated, retired, withdrawn — over feature, feature-set and model versions, parameter sets and both warrants.",
                ),
                (
                    "Checks and approvals by name",
                    "A transition lists the states it leaves, the capability it needs, the named checks to pass, and the approvals required as a role and a count — with a count that may apply only in production.",
                ),
                (
                    "Refused at edit time",
                    "An unreachable state, an unsatisfiable approval or an unknown condition is rejected when the policy is saved, so nothing fails open when it matters.",
                ),
            ],
        },
        "right": {
            "head": "The awkward cases",
            "items": [
                (
                    "Segregation of duties",
                    "Three levels, shipped as small-team, standard and regulated presets; under the strictest, nobody who created, submitted or updated an object may approve it.",
                ),
                (
                    "Break-glass",
                    "Administrators only, a written reason of real length, marked forced on the record, audited as its own action, and the owner told whether or not they subscribed.",
                ),
                (
                    "Delegation and escalation",
                    "Only an approver may delegate, never to themselves, within dates; the approval records whose behalf it was on. Five days in review is the shipped service level, swept hourly.",
                ),
            ],
        },
        "note": "maya/workflow/ and maya/security/roles.py; tests/test_workflow_matrix.py, tests/test_delegation.py. The YAML projection round-trips byte-identically for whoever wants policy in a repository, but the database is the authority.",
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
                    "Staging a change stores a proposed definition and copies nothing else; resolution inside the workspace reads the proposal in place of the version it would replace.",
                ),
                (
                    "Approval is the merge",
                    "And a base that moved underneath is a conflict, not a surprise.",
                ),
                (
                    "A recorded challenger on the review",
                    "A non-binding memo that never approves, never blocks and never writes to a sealed object; the reviewer records whether they agreed with it.",
                ),
            ],
        },
        "right": {
            "head": "Shadow replay",
            "items": [
                (
                    "Every dependent warrant re-scored",
                    "The feature set is resolved as it is and as proposed, and both are scored with the warrant's own model and parameters.",
                ),
                (
                    "Numbers, not a list of names",
                    "Rows added and removed, coverage, median, p95 and worst absolute shift, and how much of the book moves past materiality.",
                ),
                (
                    "Bounded, and the bound is stated",
                    "A sample size, a materiality taken from the model, the namespace or the default, and a daily comparison budget — a namespace over budget gets an entry naming the shortfall rather than a quiet “nothing moved”.",
                ),
            ],
        },
        "note": "maya/services/workspaces.py; tests/test_workspaces.py. Study 03 in case_studies/ is this as a worked example: a prepayment change proposed under a live model, and 60% of the book moves.",
    },
    {
        "kind": "flow",
        "kicker": "Training",
        "title": "The checksum cycle that turns paperwork into a control",
        "steps": [
            (
                "Draw",
                "An approved model against a pinned feature set; the contract is checked and every miss listed",
            ),
            ("Certify", "A signed leakage certificate is issued with the warrant, or refuses it"),
            ("Download", "Train and validation only; who, when and the content hash recorded"),
            (
                "Upload",
                "Parameters checked against that hash, their bounds and any joint constraint",
            ),
            ("Seal", "Approval by policy; every referenced object becomes undeletable"),
        ],
        "box_h": 2.1,
        "items": [
            "The test partition is escrowed: it is hashed and its row count fixed when the warrant is drawn, and it is not in the download. MAYA scores uploaded parameters against it, returns metrics only, and numbers every attempt on the warrant.",
            "Parameters fitted on data that matches no checksum MAYA issued are flagged and cannot be approved without an explicit written justification — which is how a judgement, as distinct from a fit, gets recorded honestly rather than disguised as one.",
            "Proved end to end by tests/test_warrants.py::test_the_checksum_cycle_seal_score_execute_and_bundle.",
        ],
        "note": "maya/services/warrants.py; ADR-007 states the one runtime exception MAYA concedes — it scores the mathematics, never the uploaded artifact, and refuses outright for a declared black box.",
    },
    {
        "kind": "table",
        "kicker": "Execution",
        "title": "A live licence: it expires, it is revoked, and it suspends itself",
        "rows": [
            ["Control", "Behaviour"],
            [
                "Environments",
                "dev, uat, prod — each permitted explicitly, and an approval may be required only for prod",
            ],
            [
                "Covenants",
                "input_null_rate, input_range, input_psi, output_range, max_rows_per_day, staleness_days. A breach suspends the warrant at once, writes a custody event and notifies the owner",
            ],
            [
                "Population drift",
                "A population stability index against a baseline fixed when the warrant was drawn, so the baseline cannot move later; the default ceiling is 0.25",
            ],
            [
                "Limits",
                "Calls and rows per day, rows per call — these throttle and record overage; they do not suspend",
            ],
            [
                "Reinstatement",
                "By the model owner or an administrator, with a written reason. A covenant that names no output on a multi-output model is refused at creation",
            ],
            [
                "Offline use",
                "Permitted, and both the copy and the warrant are labelled unattested for good",
            ],
        ],
        "col_w": [2.0, 9.6],
        "note": "maya/services/execution.py; tests/test_security_regressions.py::test_each_covenant. A revoked, expired or suspended warrant fails every consuming call closed, naming the covenant that broke or the person to contact.",
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
                    "Warrant, model version and mathematics, the specification source, the code artifact and its report, parameters, the leakage certificate, the training frame, the feature-set pin's manifest and its member pins, the Python version and the resolved backends.",
                ),
                (
                    "The definition of the hash",
                    "MAYA's own canonical encoder ships inside the bundle, because it is the definition rather than a description of one.",
                ),
                (
                    "A signed manifest",
                    "Every file's digest, the data's content hash, the expected output hash, and whether re-execution is possible — with the reason when it is not.",
                ),
            ],
        },
        "right": {
            "head": "What the verifier does",
            "items": [
                ("Needs Python, pyarrow and numpy", "Nothing from MAYA, and no network."),
                (
                    "Bounds the archive first",
                    "Entry count, expanded size, compression ratio and path traversal, before a byte is read.",
                ),
                (
                    "Recomputes, then re-executes",
                    "Every file digest, the signature, the data's content hash using the shipped encoder, and the model's outputs against the expected hash.",
                ),
                (
                    "Refuses on one changed byte",
                    "A tampered bundle is refused before anything is served, not partly served.",
                ),
            ],
        },
        "note": "maya/services/bundle.py, maya/sdk/offline.py; tests/test_sdk_modes.py::test_a_tampered_bundle_is_refused_before_anything_is_read, tests/test_sc2_aged_warrant.py, which reproduces a warrant aged two years in the fixture.",
    },
]

STUDY = [
    {
        "kind": "divider",
        "num": "5",
        "title": "One model, end to end",
        "sub": "IFRS 9 expected credit loss: a composite of three fitted members and two committee judgements, carried from a blank namespace to a suspended execution warrant — including everywhere MAYA said no.",
        "points": [
            "The problem, and the formula",
            "Three members and a combiner",
            "Three refusals, quoted",
            "A judgement, approved as one",
            "The score that flatters, and the test that does not",
            "The finding nobody flattered",
            "The covenant, and what was left behind",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "The problem",
        "title": "Four terms, three of them models and two of them judgements",
        "intro": "A bank carries an allowance for expected credit loss. The allowance is a probability of "
        "default, times a loss given default, times an exposure at default — lifted to a lifetime "
        "figure when credit risk has increased significantly since origination.",
        "items": [
            (
                "The mathematics",
                "ECL = h · PD₁₂ · LGD · EAD, where h is the lifetime multiple φ when PD₁₂ / PD₀ exceeds the threshold θ, and 1 otherwise.",
            ),
            (
                "Three of the four terms are fitted models",
                "A probability of default, a loss given default and an exposure at default — each a member with its own mathematics, its own parameters and its own document.",
            ),
            (
                "Two of them are not models at all",
                "θ and φ are judgements. They are what an impairment committee actually argues about, and there is no data to fit them to.",
            ),
            (
                "The data",
                "520 accounts over 24 months to June 2025: 12,480 rows of exposures, cut three business days after each month end, and 12,480 rows of outcomes known a year and a day later. Realised default rate 8.41%, mean loss given default 12.8%, total realised loss £18.3m — and 92.4% of rows with no loss at all.",
            ),
        ],
        "note": "case_studies/06-ifrs9-expected-credit-loss/. Every feed is synthetic, produced by the make_data.py beside it from a seeded recipe stated in that file, and committed so a reader can open exactly what MAYA was given.",
    },
    {
        "kind": "table",
        "kicker": "The composite",
        "title": "Three members, one combiner, one warrant",
        "rows": [
            ["Member", "Mathematics", "Fitted on", "Parameters"],
            [
                "pd_12m",
                "A logistic in arrears, utilisation and loan-to-value",
                "8,761 training rows",
                "Four weights",
            ],
            [
                "lgd_secured",
                "A logistic in collateral coverage, capped at three times the drawn balance",
                "The 747 rows that actually defaulted",
                "Two weights",
            ],
            [
                "ead_ccf",
                "Drawn balance plus a conversion factor times the undrawn commitment",
                "The same 747 rows, by least squares through the origin",
                "One factor",
            ],
            [
                "combine",
                "The stage test and the lifetime lift: the product of the three, multiplied by φ when the ratio exceeds θ",
                "Not fitted — decided",
                "sicrThreshold, lifetimeFactor",
            ],
        ],
        "col_w": [1.5, 4.6, 2.9, 2.6],
        "note": "An ensemble composite, registered as one model with one contract and one parameter set. The conversion factor fitted to 0.349 where the data was generated at 0.55 — a gap the study names as a suspect and does not quietly correct.",
    },
    {
        "kind": "bullets",
        "kicker": "The first finding",
        "title": "A contract that could not see the combiner's own parameters",
        "items": [
            (
                "What MAYA did wrong",
                "The input contract for a composite was the union of its members' contracts. The combiner's own parameters — the threshold and the lifetime multiple — belonged to no member, so they were declared nowhere and a warrant could seal without them.",
            ),
            (
                "What that would have cost",
                "A sealed warrant for a model whose two most contested numbers were not part of the thing being approved: precisely the failure the platform exists to prevent.",
            ),
            (
                "What was changed",
                "A composite's contract is now the union of its members' contracts and the combiner's own inputs, and the seal refuses while any of them is unfitted.",
            ),
            (
                "Why it is on this slide",
                "Writing the studies has been the most productive source of platform defects so far — twelve, each fixed with a test that would fail without the fix, and each named in the study that found it.",
            ),
        ],
        "note": "case_studies/06-ifrs9-expected-credit-loss/README.md §4 and setup_composite.py; README, “Case studies”. A worked model is a test somebody has to live inside, which is why the defects it finds are the ones a unit test does not.",
    },
    {
        "kind": "bullets",
        "kicker": "Three refusals",
        "title": "Where MAYA said no, and why each no was right",
        "items": [
            (
                "Sealing with three members fitted and the combiner empty",
                "“A trainable model's warrant seals only with an approved parameter set; still to fit: the combiner's own parameters.” The threshold and the multiple are inputs to the number, so the warrant does not seal without them.",
            ),
            (
                "Registering half the committee's decision",
                "“Parameters out of bounds: missing parameter 'lifetimeFactor'.” A parameter set is a set: a partial upload is not a smaller decision, it is an incomplete one.",
            ),
            (
                "Approving a judgement as though it were a fit",
                "“Blocked by check(s): data_verified_or_justified — unverified_data: the checksum does not match any download MAYA issued; approve only with an explicit justification.” The committee's numbers were not fitted on anything, so no checksum could match — and the approval went through only with a written justification naming the minuted date.",
            ),
        ],
        "note": "case_studies/06-ifrs9-expected-credit-loss/README.md §5, quoting the errors from a recorded run. The third refusal is the important one: the platform does not forbid a judgement, it forbids an unmarked one.",
    },
    {
        "kind": "split",
        "kicker": "The judgement",
        "title": "A committee decision, stored as an approved parameter set",
        "left": {
            "head": "What was approved",
            "items": [
                (
                    "sicrThreshold 3.0",
                    "A twelve-month probability of default three times its value at origination is the committee's threshold for a significant increase in credit risk.",
                ),
                (
                    "lifetimeFactor 2.8",
                    "The ratio of lifetime to twelve-month expected loss on this book's average remaining life, from the December 2025 lifetime study.",
                ),
                (
                    "With the reason attached",
                    "The rationale is part of the parameter set, not an email about it, and the approval carries the justification for its unverified data.",
                ),
            ],
        },
        "right": {
            "head": "And when it changed",
            "items": [
                (
                    "A second set, superseding the first",
                    "The evidence two slides on moved the threshold to 12.0. That is a new approved parameter set, and the warrant names which one produced the reported figure.",
                ),
                (
                    "The first is retained, not deleted",
                    "A governance record that deleted the judgement it replaced would be less useful than no record at all.",
                ),
                (
                    "MAYA has no “committee” object",
                    "It has approvals by role and count, and a parameter set that carries its reason. The committee is a fact about the firm; the record is a fact about the model.",
                ),
            ],
        },
        "note": "case_studies/06-ifrs9-expected-credit-loss/ (fit_parameters.py, study.py). The workflow primitive is an approval requirement of a role and a count, with the strictness set by the namespace's separation-of-duties preset.",
    },
    {
        "kind": "stats",
        "kicker": "The score that flatters",
        "title": "Blind scoring says the model is worse than no allowance at all",
        "stats": [
            ("1,860", "rows escrowed: hashed at the warrant, never downloaded"),
            ("£9,499", "the model's per-account RMSE, MAE £4,108"),
            ("£6,879", "RMSE of predicting no allowance at all"),
            ("92.4%", "of accounts realise no loss whatever"),
        ],
        "items": [
            "The model is worse by that measure, and it should be. When nine accounts in ten lose nothing, a per-account error rewards predicting zero, and a model that predicts a small positive allowance everywhere is punished for it.",
            "A per-account error cannot distinguish a well-levelled allowance from a badly levelled one, which is the only question an impairment allowance is asked.",
            "This is what blind scoring is for: the developer never received these rows, MAYA scored them and returned metrics only, and each of the three attempts is numbered on the warrant.",
        ],
        "note": "case_studies/06-ifrs9-expected-credit-loss/README.md §6, from a recorded run. The study publishes the unflattering number and then explains why it is the wrong question, rather than choosing a metric that flatters.",
    },
    {
        "kind": "stats",
        "kicker": "The test that does not",
        "title": "At portfolio level the allowance is 2.67 times the loss",
        "stats": [
            ("£42.4m", "allowance the model implies over 10,620 rows"),
            ("£15.9m", "loss actually realised on the same accounts"),
            ("2.67×", "coverage at the committee's threshold of 3.0"),
            ("82.8%", "of accounts in stage 2, carrying 99.5% of the allowance"),
        ],
        "rows": [
            ["Threshold θ", "Accounts in stage 2", "Coverage of realised loss"],
            ["1.5", "98.2%", "2.69×"],
            ["2.0", "95.2%", "2.69×"],
            ["3.0  — the committee's", "82.8%", "2.67×"],
            ["5.0", "57.3%", "2.55×"],
            ["8.0", "37.4%", "2.29×"],
            ["12.0  — where it moved to", "23.3%", "2.00×"],
            ["20.0", "12.1%", "1.63×"],
            ["40.0  — minimises the gap", "4.9%", "1.31×"],
        ],
        "col_w": [4.1, 3.7, 3.8],
        "note": "case_studies/06-ifrs9-expected-credit-loss/check_portfolio.py, from a recorded run. The threshold was moved to 12.0 — a defensible view of credit risk — and not to 40.0, which minimises the gap: choosing 40.0 would be fitting a judgement to an outcome, and the threshold exists to express a view rather than to calibrate a number.",
    },
    {
        "kind": "bullets",
        "kicker": "The finding nobody flattered",
        "title": "The threshold explains part of the gap, and not the rest of it",
        "intro": "Even at a threshold of 40, where only one account in twenty is in stage 2, the allowance "
        "is still 31% above the loss realised on the same accounts. The grid shows the over-provision "
        "surviving every threshold, so it is not the threshold.",
        "items": [
            (
                "The study wrote the finding down instead of closing it",
                "“The residual over-provision of 100% is not explained by the threshold — the grid shows it persists at any threshold — and is to be investigated in the members.”",
            ),
            (
                "Two suspects, each named in its own document",
                "The loss-given-default member measures collateral coverage against the balance drawn today rather than against the exposure at default, which overstates coverage on exactly the accounts with the largest undrawn limits. And the conversion factor is one figure for the whole book, fitted at 0.349 where the data was generated at 0.55.",
            ),
            (
                "Neither is fixed in this version",
                "So the study says the allowance is not to be taken as unbiased, and the model version's known-weaknesses section says the same thing to anyone who opens it later.",
            ),
            (
                "The scope it also declined to blur",
                "Stages 1 and 2 only; no forward-looking macroeconomic overlay; lifetime loss as a flat multiple rather than a term structure; and three factors multiplied as if independent when they are positively correlated in stress — so the allowance understates loss in exactly the conditions where it matters.",
            ),
        ],
        "note": "case_studies/06-ifrs9-expected-credit-loss/README.md §7 and §11. An open finding recorded against an approved model is the shape of an honest governance record; a closed one that was never investigated is the shape of a tidy one.",
    },
    {
        "kind": "split",
        "kicker": "In service, and afterwards",
        "title": "The covenant that took it out of service, and what it left behind",
        "left": {
            "head": "Three covenants, and the one that fired",
            "items": [
                (
                    "What was watched",
                    "An output range on the loss figure, a population stability index on arrears, and a null rate of exactly zero on the origination probability — because the stage test divides by it, so one missing value is not a degraded estimate but an account with no stage at all.",
                ),
                (
                    "The breach, quoted",
                    "“Warrant suspended: population stability index of 'arrears' 10.979 > 0.25: the inputs this warrant sees are no longer the population it was fitted on.”",
                ),
                (
                    "What that does",
                    "The warrant suspends itself, a custody event is written, the owner is notified, and every consuming call fails closed naming the contact. Reinstatement needs a written reason.",
                ),
            ],
        },
        "right": {
            "head": "The record, when it was over",
            "items": [
                (
                    "Five approved parameter sets",
                    "Including the superseded committee decision, kept.",
                ),
                ("Three holdout scoring attempts", "Each numbered on the warrant."),
                ("Sixteen custody events", "On the warrant alone."),
                ("Eighty-seven audit entries", "Hash-chained, and verified unbroken."),
                ("Seventeen lineage nodes", "From the two source files to the execution warrant."),
                (
                    "A typeset manifest",
                    "Naming the parameter set behind the reported figure — which is the question somebody asks two years later.",
                ),
            ],
        },
        "note": "case_studies/06-ifrs9-expected-credit-loss/get_execution_warrant.py and show_estate.py, from a recorded run. None of this is a report MAYA was asked to produce; it is what the platform had already written down.",
    },
]

CLOSE = [
    {
        "kind": "divider",
        "num": "6",
        "title": "What MAYA does not do",
        "sub": "A design without stated losses is a sales pitch, so the last two slides are the ones a buyer would otherwise have to find out for themselves.",
        "points": [
            "Non-goals, by decision",
            "What is measured and what is not",
            "In one slide",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "What MAYA does not do",
        "title": "Stated here rather than discovered later",
        "items": [
            (
                "It does not train models and does not serve predictions",
                "Training runs on your compute. The single runtime exception is scoring an escrowed holdout, and even that evaluates the mathematics rather than running your code.",
            ),
            (
                "It will be beaten on serving latency, streaming freshness, raw scale and connector breadth",
                "Where sub-10 ms serving is needed, the answer is MAYA governing the definition and a serving layer consuming a sealed execution warrant — not MAYA growing a serving tier.",
            ),
            (
                "Only Linux is exercised, and there is no dedicated benchmark host",
                "So the three-platform criterion is not met, and SC-3 — 200 users on one node — is not met reliably: three runs gave p95 0.34 s, 0.22 s and 0.43 s against 0.3 s.",
            ),
            (
                "Parts of the specification are not built",
                "Feature-set operators beyond extend, subscriptions, enforced quotas, the SDK's object handles and the review screen's semantic diff among them. The specification audit ranks every gap by what it costs a user.",
            ),
            (
                "And four risks have no clean fix",
                "Two-store consistency on pin, Python's concurrency ceiling, execution that happens outside MAYA, and the fact that a catalog nobody seeds is an empty shop. Each is mitigated and none is removed.",
            ),
        ],
        "note": "README, “Deliberate non-goals”, “Out of scope by decision” and “Not yet”; docs/BENCHMARKS.md; docs/audit/. A design without stated losses is a sales pitch.",
    },
    {
        "kind": "bullets",
        "kicker": "In one slide",
        "title": "Evidence, not assertion",
        "items": [
            "Definitions are code and data is a consequence: a version freezes how, a pin freezes what, and a pin returns the same bytes forever.",
            "Model mathematics is structured data, so the document cannot drift from the code and a reviewer is told what changed mathematically.",
            "A warrant is a live licence: it expires, it is revoked, and it suspends itself the moment its inputs stop resembling what it was fitted on.",
            "A bundle proves itself on a machine that has never heard of MAYA, and refuses on one changed byte.",
            "Nine models have been carried all the way through, and the platform kept the refusals, the superseded judgement and the finding nobody could explain.",
            "What it does not do is written down in the same place as what it does.",
        ],
        "note": "Specification: docs/MAYA_Requirements_and_Design.md · Measurements: docs/BENCHMARKS.md · Worked models: case_studies/ · Run it: python run_maya_web.py",
    },
]

SLIDES = GOVERNANCE + STUDY + CLOSE
