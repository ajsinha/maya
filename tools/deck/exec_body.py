"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The executive briefing's twenty slides. Executed into the theme's namespace by
`exec_slides.py`, the same idiom the design deck uses.
"""
# -*- coding: utf-8 -*-

_state["chapter"] = "MAYA · Executive Briefing"

# ============================================================ 1. TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.30, fill=CRIMSON)
rect(sl, 0, 4.30, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.30, fill=CRIMSON_D)
tf = txt(sl, ML + 0.3, 0.95, CW, 0.34)
para(tf, "MODEL RISK  ·  AI GOVERNANCE  ·  EXECUTIVE BRIEFING",
     size=11, color=RGBColor(0xE8, 0xB8, 0xC0), bold=True, first=True,
     space_after=0)
tf = txt(sl, ML + 0.3, 1.45, CW * 0.86, 2.0)
para(tf, "Every model the bank runs,", size=38, color=WHITE, font=SERIF,
     first=True, space_after=2)
para(tf, "and the evidence to defend it", size=38, color=WHITE, font=SERIF,
     space_after=0)
rect(sl, ML + 0.3, 3.18, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.3, 3.45, CW * 0.80, 0.7)
para(tf, "MAYA — Model & AI Lifecycle Assurance", size=15,
     color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, first=True, space_after=0,
     line=1.25)
tf = txt(sl, ML + 0.3, 4.75, CW * 0.55, 1.0)
para(tf, "Ashutosh Sinha", size=20, color=INK, bold=True, font=SERIF,
     first=True, space_after=3)
para(tf, "September 2026", size=12, color=CRIMSON, space_after=1)
x0 = ML + CW * 0.56
tf = txt(sl, x0, 4.78, CW * 0.44, 1.5)
para(tf, "TWENTY MINUTES", size=9.5, color=CRIMSON, bold=True, first=True,
     space_after=7)
for i, c in enumerate(["The exposure", "Why it keeps happening",
                       "What MAYA is", "What it would cost",
                       "The decision"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=11.5,
         space_after=5)
footer(sl)

# ============================================================ 2. THE ASK
sl, y = content("The decision this deck is asking for", "Up front")
tf = txt(sl, ML, y, CW, 0.6)
runs(tf, [("Read this slide first, and the rest as the argument for it.",
           INK, False)], size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["", "What is being asked", "What it commits"],
    ["1", "Adopt MAYA as the register of record for models and AI capabilities",
     "A decision, not a spend. The platform exists and runs"],
    ["2", "Fund a twelve-month programme to bring the estate onto it",
     "Two engineers, one model-risk lead, part-time platform support"],
    ["3", "Agree that a model outside the register is not a model the bank runs",
     "The policy line that makes the rest work"],
], ML, y + 0.72, CW, col_w=[0.5, 6.3, 5.0], row_h=0.34, fs=12, hfs=11)
tf = txt(sl, ML, y + 0.72 + h + 0.32, CW, 1.2)
runs(tf, [("What you get for it. ", CRIMSON, True),
          ("One place that can answer, in front of a supervisor, what the bank "
           "runs, who approved it, what it was fitted on, and whether that "
           "answer can be checked rather than asserted. Today that answer takes "
           "weeks to assemble and is assembled from spreadsheets.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)

# ============================================================ 3. EXPOSURE
sl, y = content("The exposure, in the language of the risk committee",
                "1 · The problem")
statbar(sl, y, [("$1.2bn+", "single-firm regulatory penalties for model "
                            "governance failure, last decade"),
                ("weeks", "to answer “what models do we run, and on what "
                          "data” — from spreadsheets"),
                ("~40%", "of a validation cycle spent reconstructing evidence "
                         "rather than validating"),
                ("0", "banks that can replay a two-year-old decision "
                      "byte-for-byte today")])
tf = txt(sl, ML, y + 1.45, CW, 2.4)
runs(tf, [("The failure is not that models are wrong. ", CRIMSON, True),
          ("Models are wrong all the time and that is priced in. The failure is "
           "that the bank cannot demonstrate what it was running, who "
           "authorised it, and what it saw — and a control you cannot "
           "demonstrate is, to a supervisor, a control you do not have.\n\n",
           INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("Three questions decide the outcome of every model-risk "
           "examination, and none of them is about accuracy: ", INK, False),
          ("what did you run, who said you could, and what did it see.",
           CRIMSON, True)],
     size=13, space_after=0, line=1.30)
tf = txt(sl, ML, SH - 1.55, CW, 0.6)
para(tf, "The first two figures are industry estimates and are marked as "
         "such. The last two are what this bank's own teams report.",
     size=10, color=MUTED, italic=True, first=True, space_after=0)

# ============================================================ 4. FOUR FAILURES
sl, y = content("Four failures, and they are the same failure",
                "1 · The problem")
q = (CW - 3 * 0.26) / 4
for i, (num, title, body) in enumerate([
    ("A", "The register is a spreadsheet",
     "It is maintained by hand, it is out of date the day it is circulated, "
     "and nothing stops a model running that is not on it."),
    ("B", "Approval is a signature on a document",
     "The document describes a model. Nothing checks that the thing running is "
     "the thing described, so the two drift apart silently."),
    ("C", "Training data is unreconstructable",
     "“What did the model see?” has no answer six months later, because the "
     "tables it read have been overwritten since."),
    ("D", "AI arrived without a category",
     "A model risk framework built for regression has no place to put a "
     "capability whose output cannot be recomputed."),
]):
    card(sl, ML + i * (q + 0.26), y, q, 2.85, num, title, body,
         title_size=13, body_size=10.5)
tf = txt(sl, ML, y + 3.05, CW, 1.2)
runs(tf, [("All four are the same failure: ", CRIMSON, True),
          ("a claim is made and nothing checks it. The register CLAIMS to list "
           "the estate. The approval CLAIMS the model was reviewed. The "
           "document CLAIMS what the model reads. Each is believed because "
           "somebody wrote it down, and none can be checked — so the first time "
           "any of them is tested is under examination.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)

# ============================================================ 5. WHAT MAYA IS
sl, y = content("What MAYA is, in one sentence", "2 · The answer")
rect(sl, ML, y + 0.15, CW, 1.55, fill=PARCH)
rect(sl, ML, y + 0.15, 0.05, 1.55, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + 0.38, CW - 0.7, 1.2)
para(tf, "The register of record for every model a bank runs — and the "
         "machinery that makes claims about those models checkable instead of "
         "asserted.",
     size=19, color=INK, font=SERIF, first=True, space_after=0, line=1.28)
tf = txt(sl, ML, y + 2.05, CW, 2.6)
runs(tf, [("Read the second half again. ", CRIMSON, True),
          ("Every model platform is a register. What makes this one different "
           "is that the claims it holds are ", INK, False),
          ("executable", INK, True),
          (": the equation is derived from what the platform stores rather than "
           "typed beside it; the approval is refused unless a second person "
           "signs; the training set is pinned to bytes that cannot move; and "
           "the dependency graph is type-checked rather than drawn.\n\n",
           INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("And one thing it deliberately is not. ", CRIMSON, True),
          ("MAYA does not train models and it does not run them. Your engines "
           "keep doing that. MAYA issues the authority, records what came back, "
           "and refuses what should be refused — which is why adopting it does "
           "not mean migrating a single production workload.", INK, False)],
     size=13, space_after=0, line=1.30)

# ============================================================ 6. SIX THINGS
sl, y = content("Six things it does that a document cannot",
                "2 · The answer")
h = table(sl, [
    ["", "What it does", "Why a document cannot"],
    ["1", "Derives the equation from what it stores",
     "A written formula beside a running model is a second description, and two "
     "descriptions drift — the one nobody executes drifts first"],
    ["2", "Refuses self-approval, in the mechanism",
     "A policy that says “approved by a second person” is followed until the "
     "quarter-end when it is not"],
    ["3", "Pins the training data to bytes",
     "“Fitted on the January extract” names a table that has been overwritten "
     "since; a version pin names bytes that cannot move"],
    ["4", "Classifies models by how they are fitted",
     "The class decides which operations are even admissible — asking to train "
     "a closed-form pricer is a type error, not a permission"],
    ["5", "Computes the blast radius from the graph",
     "A dependency spreadsheet is right on the day it is written; a type-checked "
     "edge is right when somebody asks"],
    ["6", "Makes refusals evidence",
     "“We tried and the platform stopped us” is a document. “We have a policy "
     "against it” is a sentence"],
], ML, y, CW, col_w=[0.5, 4.6, 6.7], row_h=0.32, fs=11, hfs=11)
tf = txt(sl, ML, y + h + 0.28, CW, 0.6)
runs(tf, [("Each of these is a control. ", CRIMSON, True),
          ("None of them depends on anybody remembering to do it, which is the "
           "only property that distinguishes a control from a convention.",
           INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 7. THE SHAPE
sl, y = content("Where MAYA sits, and what it never touches",
                "2 · The answer")
band = 1.05
rect(sl, ML, y + 0.10, CW, band, fill=PARCH)
rect(sl, ML, y + 0.10, 0.05, band, fill=SLATE)
tf = txt(sl, ML + 0.32, y + 0.28, CW - 0.7, band - 0.3)
para(tf, "YOUR ENGINES — unchanged", size=11, color=SLATE, bold=True,
     first=True, space_after=4)
para(tf, "Databricks · SAS · Python · the pricing library · the decision "
         "engine. They fit the models and they run them, exactly as today.",
     size=12, color=INK, space_after=0, line=1.24)

rect(sl, ML, y + 1.42, CW, 1.55, fill=CRIMSON)
tf = txt(sl, ML + 0.32, y + 1.62, CW - 0.7, 1.25)
para(tf, "MAYA — THE REGISTER", size=11, color=RGBColor(0xE8, 0xB8, 0xC0),
     bold=True, first=True, space_after=4)
para(tf, "Models and versions · features and the two clocks · warrants "
         "and approvals · parameters and their provenance · the evidence chain",
     size=13, color=WHITE, space_after=4, line=1.24)
para(tf, "Issues the authority. Records what came back. Refuses what should "
         "be refused.",
     size=12, color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, space_after=0)

rect(sl, ML, y + 3.24, CW, band, fill=PARCH)
rect(sl, ML, y + 3.24, 0.05, band, fill=SLATE)
tf = txt(sl, ML + 0.32, y + 3.42, CW - 0.7, band - 0.3)
para(tf, "YOUR DATA — where it already is", size=11, color=SLATE, bold=True,
     first=True, space_after=4)
para(tf, "The warehouse, the lake, S3. MAYA copies what a model was fitted on "
         "into an immutable, versioned store so the read can be reproduced — "
         "and reads nothing at request time.",
     size=12, color=INK, space_after=0, line=1.24)

# ============================================================ 8. THE LOOP
sl, y = content("What a modelling team actually does differently",
                "3 · What changes")
STEP_H = 1.65
steps(sl, ML, y + 0.05, CW, [
    ("1", "Ask", "for a training warrant. Authority is granted BEFORE any data "
     "is read — a read performed under an authority that turns out not to "
     "exist has already happened"),
    ("2", "Fit", "in your own environment, on your own hardware, with your own "
     "tools. Nothing changes here"),
    ("3", "Deliver", "the parameters back with their diagnostics. They land "
     "PROPOSED — not usable yet"),
    ("4", "Approve", "by somebody who is not the author. The platform refuses "
     "the alternative"),
    ("5", "Run", "under an execution warrant naming the approved parameters by "
     "digest"),
], h=STEP_H)
tf = txt(sl, ML, y + 0.05 + STEP_H + 0.34, CW, 1.6)
runs(tf, [("Five steps, and four of them are things a good team already does. ",
           CRIMSON, True),
          ("The change is that each one now leaves a record that cannot be "
           "reconstructed afterwards, and that the platform refuses the paths "
           "around them. A quant's day is not longer; it is auditable.\n\n",
           INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("The honest cost: ", CRIMSON, True),
          ("somebody has to answer questions that were previously answered by "
           "nobody — when was this data recorded, who owns this feature, what "
           "is the reason for this rule. That is the friction, and it is the "
           "point.", INK, False)],
     size=13, space_after=0, line=1.30)

# ============================================================ 9. THE TWO CLOCKS
sl, y = content("The one technical idea worth an executive's time",
                "3 · What changes")
tf = txt(sl, ML, y, CW, 0.8)
runs(tf, [("Every fact the bank records has two dates: ", INK, False),
          ("when it was true, and when we learned it.", CRIMSON, True)],
     size=15, first=True, space_after=0, line=1.28)
half = (CW - 0.34) / 2
card(sl, ML, y + 0.95, half, 2.15, "WITHOUT BOTH",
     "The backtest lies, quietly",
     "A model re-fitted today on “last year's data” sees figures that were "
     "restated since — numbers nobody had when the decision was taken. It "
     "backtests beautifully and underperforms in production, and the gap is "
     "written off as drift.")
card(sl, ML + half + 0.34, y + 0.95, half, 2.15, "WITH BOTH",
     "The read is reproducible",
     "MAYA refuses a feature row that does not carry both dates, and pins every "
     "training set to the exact bytes it read. The same question asked in 2028 "
     "returns the 2026 answer.")
tf = txt(sl, ML, y + 3.35, CW, 1.1)
runs(tf, [("Why this belongs on an executive slide. ", CRIMSON, True),
          ("It is the difference between a model whose past performance can be "
           "audited and one whose past performance is a story. Supervisors have "
           "started asking for the first; almost nobody can produce it.",
           INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)

# ============================================================ 10. AI
sl, y = content("Where AI fits, without a second framework",
                "3 · What changes")
tf = txt(sl, ML, y, CW, 0.9)
runs(tf, [("The common answer is a separate AI policy. That is a mistake, ",
           INK, False),
          ("and an expensive one: two frameworks means two registers, two "
           "approval paths, and an argument at the boundary about which one "
           "applies to a gradient-boosted scorecard.", CRIMSON, True)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["", "The rule MAYA applies", "What it means in practice"],
    ["Tier A", "The output can be mechanically CHECKED",
     "A named oracle verifies it. Register it, and the check is the control"],
    ["Tier B", "Every claim can be GROUNDED in evidence",
     "Unsupported claims are removed, not flagged — and kept for the reviewer"],
    ["Tier C", "Neither checkable nor groundable",
     "DELIBERATELY NOT REGISTRABLE. A Tier C capability in a register is one "
     "that will be wired into a decision one day"],
], ML, y + 1.05, CW, col_w=[1.0, 4.6, 6.2], row_h=0.34, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 1.05 + h + 0.30, CW, 1.3)
runs(tf, [("Nothing is evidence until a person attests it, and never the "
           "person who asked for it. ", CRIMSON, True),
          ("A sample of generations is pulled for independent review whatever "
           "they look like, because somebody who has approved forty correct "
           "drafts is not reading the forty-first. That sampling is "
           "deterministic and cannot be gamed by watching the clock.",
           INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)

# ============================================================ 11. EVIDENCE
sl, y = content("Is it real? — what has actually been measured",
                "4 · The evidence")
statbar(sl, y, [("3,635", "automated tests, green on every commit"),
                ("4 hours", "continuous soak: 3,097 assertions, zero failures"),
                ("134,936", "requests in that run; zero server errors"),
                ("6 ms", "median response, start and end of the run")])
tf = txt(sl, ML, y + 1.45, CW, 2.3)
runs(tf, [("What those numbers are, precisely. ", CRIMSON, True),
          ("The suite runs on every push, twice — once on each of the two "
           "storage formats — and the counts must match. The soak drove a live "
           "instance for four hours with the platform's own invariants asserted "
           "between every batch of work: the evidence chain still verifies, the "
           "schema has not drifted, no request returned an unmapped failure, and "
           "memory and file handles stayed bounded.\n\n", INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)
runs(tf, [("And what they are not. ", CRIMSON, True),
          ("None of this is a load test, none of it is at your data volumes, "
           "and the performance figures in the design documents are targets "
           "rather than measurements. Where a number has not been measured, the "
           "documentation says so — which is the same discipline the platform "
           "applies to models.", INK, False)],
     size=12.5, space_after=0, line=1.30)

# ============================================================ 12. CASE STUDIES
sl, y = content("Six worked models, runnable in a minute each",
                "4 · The evidence")
h = table(sl, [
    ["Model", "Class", "What it demonstrates"],
    ["Black–Scholes European call", "T1",
     "A model with no training data. The whole pricer is one expression in the "
     "register, checked against the reference to 5 decimal places"],
    ["Home price regression (public data)", "T2",
     "2,928 real sales from the authoritative source — and the second clock the "
     "source did not have, which somebody must own"],
    ["Mortgage prepayment curve", "T2",
     "Non-linear in the inputs, linear in the parameters: the shape a bank "
     "actually uses, still interpretable and still reproducible"],
    ["Merton distance to default", "T0",
     "No parameters at all. Asking to train it is refused as a type error by "
     "two independent layers"],
    ["IFRS 9 expected credit loss", "T2",
     "Reuse: five shared features, a composed featureset, and a type-checked "
     "dependency that makes the blast radius an answer"],
    ["HELOC origination eligibility", "T8",
     "A credit POLICY governed as a model — every decision carrying the rule "
     "that made it and the reason that rule exists"],
], ML, y, CW, col_w=[3.5, 0.75, 7.35], row_h=0.30, fs=10.5, hfs=10.5)
tf = txt(sl, ML, y + h + 0.30, CW, 0.9)
runs(tf, [("These are not screenshots. ", CRIMSON, True),
          ("Each is a script that registers a real model against a live MAYA, "
           "fits it OUTSIDE the platform, delivers the parameters back under a "
           "warrant, and prints what the platform refused. Chapter 26 of the "
           "design deck walks through all six.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)

# ============================================================ 13. REFUSALS
sl, y = content("The most useful thing in a demonstration is what it refuses",
                "4 · The evidence")
tf = txt(sl, ML, y, CW, 0.7)
runs(tf, [("A control nobody has watched refuse is a control nobody has "
           "tested. ", CRIMSON, True),
          ("Each case study deliberately asks for something it should not get. "
           "Every refusal names what failed AND what to do instead — a refusal "
           "that says only “forbidden” teaches people to route around the "
           "platform. Verbatim, not paraphrased:", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
ch = code(sl, ML, y + 0.85, CW, [
    "a T0 model cannot be fitted: its parameters come from theory, not from",
    "data — there is nothing to fit",
    "",
    "this edge carries nothing — a wire to nowhere, and the blast radius",
    "would follow it",
    "",
    "a featureset read for fitting must bound the period it covers",
    "",
    "cannot add 'asset_vol' — a parent already has it. say 'override' if",
    "replacing it is what is meant; the two read differently to a reviewer",
    "",
    "a number one person can both produce and bless is a preference, not",
    "an estimate",
], fs=10.5, title="WHAT THE PLATFORM SAID, VERBATIM")


# ============================================================ 14. COST
sl, y = content("What it would cost, and against what",
                "5 · The business case")
h = table(sl, [
    ["", "Build on MAYA", "Buy a vendor platform", "Do nothing"],
    ["Year-one cost", "~£0.9m — three FTE and infrastructure",
     "£1.5–3m licence, plus £1–2m implementation",
     "£0 visible"],
    ["Ongoing", "~£0.6m/year", "£1.5m+/year, rising with the estate",
     "£0 visible"],
    ["Time to first governed model", "Weeks — the platform runs today",
     "9–18 months", "n/a"],
    ["Fit to this bank's estate", "Built for a heterogeneous estate: pricers, "
     "scorecards, rulebooks and AI in one taxonomy",
     "Strong for trainable ML; weak for closed-form and policy models",
     "n/a"],
    ["What you own", "The source, the schema, the evidence format",
     "A contract and an export format",
     "The spreadsheet"],
], ML, y, CW, col_w=[2.35, 3.5, 3.5, 2.25], row_h=0.32, fs=10.5, hfs=10.5)
tf = txt(sl, ML, y + h + 0.28, CW, 1.3)
runs(tf, [("The cost figures are ESTIMATES and are marked as such. ",
           CRIMSON, True),
          ("The one that is not an estimate is the third row: the platform "
           "exists, the tests pass, and the case studies run today. “Do "
           "nothing” has a cost too — it is simply carried as a contingency "
           "nobody has priced, and it becomes visible on the day of an "
           "examination rather than in a budget cycle.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.30)

# ============================================================ 15. WHAT'S REAL
sl, y = content("What is built, and what is honestly not",
                "5 · The business case")
half = (CW - 0.34) / 2
card(sl, ML, y, half, 3.35, "BUILT AND RUNNING",
     "What you would get on day one",
     "The register: models, versions, features with both clocks, featuresets, "
     "warrants, approvals, parameters, the evidence chain.\n\n"
     "The controls: quorum approval, self-approval refused, tiering derived "
     "from exposure, blast radius computed from the graph.\n\n"
     "The interface: every screen a person needs, permission-driven, with a "
     "test that fails on any page nobody can reach.\n\n"
     "The AI framework: tiers, oracles, grounding, mandatory review sampling.")
card(sl, ML + half + 0.34, y, half, 3.35, "NOT BUILT — SAY SO",
     "What would still be a programme",
     "An EUC sweep. MAYA publishes the contract a scanner must meet and "
     "takes delivery; it does not crawl the bank's drives, and nobody here "
     "runs a scanner yet.\n\n"
     "Connectors past MLflow, Unity Catalog and git — SageMaker, Vertex, SAS, "
     "the CMDB — and the push-status-back direction of all of them.\n\n"
     "Rule-set import from a spreadsheet or a DMN file. This is the work that "
     "decides whether the EUC estate is a demonstration or a programme.\n\n"
     "Scale beyond a single process, and every performance figure in the "
     "documents is a target rather than a measurement.")

# ============================================================ 16. RISKS
sl, y = content("What could go wrong with this, honestly",
                "5 · The business case")
h = table(sl, [
    ["Risk", "Why it is real", "What reduces it"],
    ["Key-person concentration",
     "One author. That is a genuine single point of failure and no slide should "
     "pretend otherwise",
     "The source, the schema and 3,914 tests are the bank's. The design "
     "documents explain WHY, not only what"],
    ["Adoption resistance",
     "The platform makes people answer questions previously answered by nobody, "
     "and that reads as friction",
     "Start with one book and one tier-1 model. The compliant path has to be "
     "the shortest path or the inventory rots"],
    ["It becomes another spreadsheet",
     "A register nobody updates is worse than none, because it is believed",
     "The API is the only way in, and the register refuses what it cannot "
     "check. There is no manual override"],
    ["Regulatory expectations move",
     "SR 26-2, SS1/23 and the EU AI Act are all young and will be interpreted",
     "Regimes are DATA in MAYA, not code: a new obligation is a row, and the "
     "platform reports what is unsatisfied"],
], ML, y, CW, col_w=[2.5, 4.6, 4.55], row_h=0.32, fs=10.5, hfs=10.5)

# ============================================================ 17. FIRST 90
sl, y = content("The first ninety days", "6 · The path")
STEP_H = 1.75
steps(sl, ML, y + 0.15, CW, [
    ("0–30", "One model, end to end",
     "Pick one tier-1 model with a live validation finding. Register it, "
     "warrant it, approve it. Produce the evidence pack and put it in front "
     "of whoever owns the finding"),
    ("30–60", "One book",
     "Bring one portfolio's models on, including a pricer and a policy "
     "rulebook — the two things a trainable-ML platform handles worst"),
    ("60–90", "The examination rehearsal",
     "Have second line ask the three questions cold, against the register, "
     "with nobody preparing anything in advance. That is the test"),
], h=STEP_H)
tf = txt(sl, ML, y + 0.15 + STEP_H + 0.40, CW, 1.5)
runs(tf, [("The ninety-day test is deliberately not a technical one. ",
           CRIMSON, True),
          ("It is whether a model-risk manager can answer “what do we run, who "
           "approved it, and what did it see” from the register alone, without "
           "asking a quant and without a week's notice. If that fails, the "
           "programme has not worked, whatever the platform metrics say.",
           INK, False)],
     size=13, first=True, space_after=0, line=1.30)

# ============================================================ 18. TWELVE MONTHS
sl, y = content("Twelve months, and what “done” means",
                "6 · The path")
h = table(sl, [
    ["Quarter", "What lands", "How you know it worked"],
    ["Q1", "One book on the register; the evidence pack in a real validation",
     "Second line stops asking the modelling team for reconstructions"],
    ["Q2", "Trading and treasury pricers; the AI capabilities that are already "
     "in use",
     "A supervisor's question about an AI-assisted document has an answer with "
     "a name on it"],
    ["Q3", "The remaining books; connectors to whichever ML platform dominates",
     "The spreadsheet is decommissioned, not shadowed"],
    ["Q4", "A discovery sweep against the published contract; an examination "
     "rehearsal end to end",
     "The inventory includes what nobody declared, and a supervisor's request "
     "is answered from the register rather than assembled"],
], ML, y, CW, col_w=[1.0, 5.4, 5.25], row_h=0.34, fs=11, hfs=11)
tf = txt(sl, ML, y + h + 0.32, CW, 1.4)
runs(tf, [("“Done” is not a percentage of models registered. ", CRIMSON, True),
          ("It is the day a question from second line, or from a supervisor, "
           "is answered from the register in an afternoon rather than "
           "assembled over three weeks — and the answer is one nobody has to "
           "take on trust, because every claim in it can be checked against "
           "the evidence chain.", INK, False)],
     size=13, first=True, space_after=0, line=1.30)

# ============================================================ 19. THE LINE
sl, y = content("The one policy decision that makes the rest work",
                "6 · The path")
rect(sl, ML, y + 0.30, CW, 1.5, fill=PARCH)
rect(sl, ML, y + 0.30, 0.05, 1.5, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + 0.55, CW - 0.7, 1.1)
para(tf, "A model that is not in the register is not a model the bank runs.",
     size=21, color=INK, font=SERIF, first=True, space_after=0, line=1.26)
tf = txt(sl, ML, y + 2.15, CW, 2.6)
runs(tf, [("Everything else in this deck is machinery. This is the decision. ",
           CRIMSON, True),
          ("Without it the register is a second place to write things down, "
           "and it will be maintained for eighteen months and then quietly "
           "not. With it, registration stops being administrative overhead and "
           "becomes the thing that makes a model usable — which is the only "
           "arrangement under which an inventory stays current.\n\n",
           INK, False)],
     size=13.5, first=True, space_after=0, line=1.30)
runs(tf, [("It is also the sentence a supervisor wants to hear, ", INK, False),
          ("because it is the only version of “we have an inventory” that is "
           "falsifiable.", CRIMSON, True)],
     size=13.5, space_after=0, line=1.30)

# ============================================================ 20. CLOSE
_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
tf = txt(sl, ML + 0.4, 1.30, CW * 0.82, 1.2)
para(tf, "A model is a representation of the world.", size=30, color=WHITE,
     font=SERIF, italic=True, first=True, space_after=6, line=1.22)
para(tf, "Governance is knowing the difference.", size=30,
     color=RGBColor(0xF4, 0xDF, 0xE3), font=SERIF, italic=True, space_after=0,
     line=1.22)
rect(sl, ML + 0.4, 3.35, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.4, 3.70, CW * 0.52, 2.4)
para(tf, "WHAT IS BEING ASKED", size=10, color=RGBColor(0xE0, 0xA8, 0xB2),
     bold=True, first=True, space_after=10)
for line in ["Adopt MAYA as the register of record",
             "Fund twelve months: three FTE",
             "Agree the policy line on the previous slide"]:
    para(tf, line, size=14, color=WHITE, space_after=8, line=1.22)
tf = txt(sl, ML + CW * 0.58, 3.70, CW * 0.42, 2.4)
para(tf, "WHERE TO LOOK NEXT", size=10, color=RGBColor(0xE0, 0xA8, 0xB2),
     bold=True, first=True, space_after=10)
for line in ["The design deck — 128 slides, chapter 26 is the case studies",
             "case_studies/ — thirteen models, runnable in a minute each",
             "docs/11 — the adversarial review, written against this platform"]:
    para(tf, line, size=12, color=RGBColor(0xF6, 0xE6, 0xE9), space_after=8,
         line=1.22)
footer(sl)
