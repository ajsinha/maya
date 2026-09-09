"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

THE CONCEPTS DECK — twenty slides: the ideas, the formalism, the shape of the
system and the shape of the data. Nothing else.

**The audience.** An architect, a head of model risk with a quantitative
background, or an academic reader — somebody who wants to know whether the
ideas are sound before caring whether the software is good. So: no roadmap, no
business case, no screenshots, no build status. The design deck has all of
those and is 123 slides.

**The claim these slides have to earn.** That the governance controls are
consequences of a definition rather than a list of practices — that once you
say what a model *is*, precisely, most of the platform follows and the rest is
plumbing.
"""
# -*- coding: utf-8 -*-

_state["chapter"] = "MAYA · Concepts and Formalism"

# ============================================================ 1. TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.35, fill=CRIMSON)
rect(sl, 0, 4.35, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.35, fill=CRIMSON_D)
tf = txt(sl, ML + 0.3, 0.92, CW, 0.34)
para(tf, "CONCEPTS  ·  FORMALISM  ·  DESIGN  ·  DATA", size=11,
     color=RGBColor(0xE8, 0xB8, 0xC0), bold=True, first=True, space_after=0)
tf = txt(sl, ML + 0.3, 1.42, CW * 0.88, 2.1)
para(tf, "What a model is,", size=40, color=WHITE, font=SERIF, first=True,
     space_after=2)
para(tf, "and what follows from saying so", size=40, color=WHITE, font=SERIF,
     space_after=0)
rect(sl, ML + 0.3, 3.22, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.3, 3.50, CW * 0.82, 0.7)
para(tf, "The mathematical foundation under MAYA — in twenty slides",
     size=15, color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, first=True,
     space_after=0, line=1.25)
tf = txt(sl, ML + 0.3, 4.78, CW * 0.55, 1.0)
para(tf, "Ashutosh Sinha", size=20, color=INK, bold=True, font=SERIF,
     first=True, space_after=3)
para(tf, "September 2026", size=12, color=CRIMSON, space_after=1)
x0 = ML + CW * 0.56
tf = txt(sl, x0, 4.80, CW * 0.44, 1.5)
para(tf, "CONTENTS", size=9.5, color=CRIMSON, bold=True, first=True,
     space_after=7)
for i, c in enumerate(["The definition", "What it forces",
                       "The two clocks", "The design", "The data"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=11.5,
         space_after=5)
footer(sl)

# ============================================================ 2. THE QUESTION
sl, y = content("A question that sounds trivial", "1 · The definition")
tf = txt(sl, ML, y + 0.30, CW * 0.9, 1.0)
para(tf, "What is a model?", size=44, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=0)
tf = txt(sl, ML, y + 1.55, CW, 2.8)
runs(tf, [("Not which one. Not whose. ", INK, False),
          ("What one is", INK, True),
          (" — formally, generally, in a way that covers everything an "
           "institution has to govern: a Black–Scholes pricer, a "
           "gradient-boosted scorecard, a spreadsheet of elicited weights, a "
           "vendor black box, an authored rulebook, and a language model "
           "drafting a document.\n\n", INK, False)],
     size=14, first=True, space_after=0, line=1.30)
runs(tf, [("Every model-risk framework in production answers this with a "
           "LIST. ", CRIMSON, True),
          ("A list is not a definition: it cannot tell you whether the next "
           "artefact belongs on it, and it cannot tell you what follows once "
           "something does. That is why each new class of model — machine "
           "learning, then AI — arrives as a governance crisis rather than as "
           "an instance of something already understood.", INK, False)],
     size=14, space_after=0, line=1.30)

# ============================================================ 3. THE DEFINITION
sl, y = content("One definition, and everything else is a consequence",
                "1 · The definition")
rect(sl, ML, y + 0.15, CW, 1.35, fill=PARCH)
rect(sl, ML, y + 0.15, 0.05, 1.35, fill=CRIMSON)
tf = txt(sl, ML + 0.4, y + 0.45, CW - 0.8, 0.9)
para(tf, "f :  P  ⊗  X  ⟶  D(Y)", size=30, color=INK, font=SERIF, first=True,
     space_after=0)
h = table(sl, [
    ["Symbol", "Reads as", "Why it is separate"],
    ["P", "the parameter object — what was learned, calibrated, elicited or "
     "authored",
     "Because how P is inhabited is the ONLY thing that varies across the "
     "estate, and it is what governance actually differs on"],
    ["X", "the input object — the features the model reads, typed",
     "Because a change to X is a change to what the model IS, and must not be "
     "confusable with a change to the data flowing through it"],
    ["D(Y)", "a DISTRIBUTION over outputs, not a point",
     "Because a point estimate is a distribution somebody has already collapsed, "
     "and the collapsing is a decision that belongs on the record"],
    ["⊗", "the two arrive together and independently",
     "The same P with a different X is a different model; the same X with a "
     "different P is a different model"],
], ML, y + 1.68, CW, col_w=[0.9, 4.4, 6.4], row_h=0.32, fs=11, hfs=11)
tf = txt(sl, ML, y + 1.68 + h + 0.26, CW, 0.7)
runs(tf, [("This is the Kleisli category of a probability monad — "
           "Para(Stoch). ", CRIMSON, True),
          ("The name matters less than the consequence: models compose, and "
           "the composition is typed.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 4. TRAINABILITY
sl, y = content("How P is inhabited gives the only taxonomy that is derived",
                "1 · The definition")
h = table(sl, [
    ["", "P inhabited by", "Example", "Can it be fitted?"],
    ["T0", "nothing — theory fixes it", "Black–Scholes with given inputs; a "
     "Basel risk weight", "No — a TYPE ERROR"],
    ["T1", "calibration to observables", "implied volatility; a discount curve",
     "Yes — calibrate"],
    ["T2", "estimation from a sample", "OLS, logistic regression, GARCH",
     "Yes — estimate"],
    ["T3", "iterative training", "gradient boosting, neural networks",
     "Yes — train"],
    ["T5", "configuration", "thresholds and limits somebody set", "Yes — "
     "configure"],
    ["T6", "a vendor's parameters nobody can see", "a purchased bureau score",
     "No — a TYPE ERROR"],
    ["T7", "elicitation from experts", "scenario weights, expert scorecards",
     "Yes — elicit"],
    ["T8", "authoring", "a credit policy rulebook, an AML rule set",
     "Yes — author"],
], ML, y, CW, col_w=[0.6, 3.3, 5.0, 2.7], row_h=0.29, fs=10.5, hfs=10.5)
tf = txt(sl, ML, y + h + 0.24, CW, 0.9)
runs(tf, [("Never stored, never declared, always derived. ", CRIMSON, True),
          ("The class falls out of the kernel: a `calibration_set` inhabited by "
           "`calibrate` IS T1. And the class is not a label — it decides which "
           "operations the platform will admit. Asking to train a T0 model is "
           "refused with a reason, not a permission error.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 5. CONSEQUENCES
sl, y = content("What the definition forces, before anybody designs anything",
                "2 · What it forces")
q = (CW - 3 * 0.26) / 4
for i, (num, title, body) in enumerate([
    ("I", "A version is a digest, not a name",
     "If f is a function, two functions that differ anywhere are different "
     "objects. The identity of a version is a digest over its manifest — so a "
     "status change cannot move it, and an edit cannot hide."),
    ("II", "P and X are approved separately",
     "They arrive independently, so they change independently. A new parameter "
     "set is not a new model; a new input schema is."),
    ("III", "Composition must type-check",
     "If models compose, then an edge between two of them is a claim about "
     "types — and a claim that can be checked must be."),
    ("IV", "The output is a distribution",
     "Which makes “what did it say” answerable, and makes the collapse to a "
     "decision an act somebody performs rather than an artefact of the code."),
]):
    card(sl, ML + i * (q + 0.26), y, q, 3.05, num, title, body,
         title_size=13, body_size=10.5)
tf = txt(sl, ML, y + 3.25, CW, 0.9)
runs(tf, [("None of these is a policy choice. ", CRIMSON, True),
          ("Each is what the definition already said, written out. That is the "
           "test of a formalism: it should make you unable to build the wrong "
           "thing, rather than remind you not to.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 6. LAWS
sl, y = content("Twenty-one laws, and what a law is here",
                "2 · What it forces")
tf = txt(sl, ML, y, CW, 0.85)
runs(tf, [("A law is a property of the system stated as a proposition, with a "
           "test that executes it. ", CRIMSON, True),
          ("Not a principle in a document. If a law cannot be executed it is a "
           "hope, and this platform's own documentation says which of the "
           "twenty-one are hopes: eighteen run, three do not.", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["", "The law", "What it prevents"],
    ["L-2", "A version's digest never moves",
     "A model changing underneath an approval that was given for something else"],
    ["L-7", "A replacement's contract must REFINE the incumbent's",
     "A promotion that quietly narrows what consumers were promised"],
    ["L-10", "The point-in-time read admits only what was knowable",
     "Look-ahead leakage — the dominant silent failure in model development"],
    ["L-15", "Every fibre is total",
     "A model class arriving at run time with no governance path defined for it"],
    ["L-21", "Composition is typed",
     "A dependency graph that says one model feeds another when it does not"],
    ["L-W10", "A featureset must supply what the kernel declares it reads",
     "A model silently gaining a regressor and being treated as unchanged"],
], ML, y + 1.00, CW, col_w=[0.85, 5.0, 5.95], row_h=0.31, fs=11, hfs=11)
tf = txt(sl, ML, y + 1.00 + h + 0.24, CW, 0.6)
runs(tf, [("Six of twenty-one shown. ", CRIMSON, True),
          ("The laws are the acceptance criteria: they run in their own CI job, "
           "and a release that breaks one does not ship.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 7. TWO CLOCKS
sl, y = content("Two clocks, and the operator between them",
                "3 · The two clocks")
tf = txt(sl, ML, y, CW, 0.8)
runs(tf, [("Every fact carries two independent time coordinates: ", INK, False),
          ("the EVENT time at which it held in the world, and the INGEST time "
           "at which the recording system learned it.", CRIMSON, True)],
     size=14, first=True, space_after=0, line=1.28)
code(sl, ML, y + 0.95, CW * 0.60, [
    "knowable_by = min(label_ts, as_of)",
    "",
    "admissible = [ r for r in records",
    "               if r.event  <= label_ts",
    "              and r.ingest <= knowable_by ]",
], fs=12, title="THE POINT-IN-TIME READ")
x = ML + CW * 0.64
tf = txt(sl, x, y + 0.95, CW * 0.36, 3.0)
runs(tf, [("Bounding ingest by the MINIMUM ", INK, False),
          ("is the whole guarantee.", CRIMSON, True)],
     size=12.5, first=True, space_after=8, line=1.26)
para(tf, "It makes every observation time at or after the label date give the "
         "same answer: the row assembled the day a label matured, and the same "
         "row re-assembled a year later, are identical — however many "
         "restatements arrived in between.",
     size=12, color=INK, space_after=8, line=1.26)
para(tf, "Conflating the two clocks produces look-ahead leakage, which is the "
         "dominant silent failure mode in model development: the model "
         "backtests well and performs badly, and the gap is attributed to "
         "drift.",
     size=12, color=SLATE, space_after=0, line=1.26)
tf = txt(sl, ML, y + 3.55, CW * 0.60, 0.8)
runs(tf, [("Stated once, executed everywhere. ", CRIMSON, True),
          ("The published rule and the platform's own read are checked to admit "
           "the same rows.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ============================================================ 8. PIT ORDER
sl, y = content("Why the tie-break is content-based, and total",
                "3 · The two clocks")
tf = txt(sl, ML, y, CW, 1.0)
runs(tf, [("Two facts can share both clocks. ", CRIMSON, True),
          ("Then the read must still be deterministic, or “the same featureset "
           "version resolves to the same bytes” is false — and it is false in a "
           "way nobody notices until two implementations disagree.", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["Tie-break by", "What goes wrong"],
    ["Insertion order", "Depends on the storage engine, and changes when the "
     "table is rewritten or compacted"],
    ["A surrogate id", "Depends on who wrote first, which is a property of the "
     "pipeline rather than of the data"],
    ["Nothing", "Two point-in-time implementations break the tie opposite ways "
     "and both look correct"],
    ["CONTENT — a total order over the row's own values",
     "Nothing. The order is a function of the data, so a rewrite cannot change "
     "it and two implementations cannot disagree"],
], ML, y + 1.20, CW, col_w=[3.6, 8.2], row_h=0.34, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 1.20 + h + 0.28, CW, 1.0)
runs(tf, [("This is the sort of detail a formalism earns its keep on. ",
           CRIMSON, True),
          ("Nobody specifies a tie-break in a governance policy. But “same "
           "version, same bytes” is either true or it is not, and it is not "
           "true unless somebody decided this.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 9. WARRANT
sl, y = content("The warrant: authority as a signed, expiring document",
                "3 · The two clocks")
tf = txt(sl, ML, y, CW, 0.75)
runs(tf, [("A model does not run because somebody has permission. ",
           CRIMSON, True),
          ("It runs because a specific operation on a specific version, under "
           "specific parameters, was authorised — and the authorisation is a "
           "document an engine can verify without asking anybody.", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
wh = code(sl, ML, y + 0.95, CW, [
    "subject      urn @ version, manifest digest, trainability class",
    "operation    verb (score | fit | calibrate), determinism, seed",
    "parameters   the APPROVED set, by id and digest — or 'to_be_fitted'",
    "data         the featureset version, its slots, and the PIT rule as text",
    "constraints  what the contract assumes and guarantees",
    "authority    principal, declared use, environment, expiry, revocation",
    "signature    over all of it",
], fs=11.5, title="WHAT A WARRANT CARRIES")
tf = txt(sl, ML, y + 0.95 + wh + 0.26, CW, 1.1)
runs(tf, [("A GRANT says this principal may ask; a WARRANT is one signed, "
           "expiring answer to one asking. ", CRIMSON, True),
          ("Revoking the grant stops the next warrant rather than reaching into "
           "the last one — which is why the revocation floor is measured in "
           "seconds rather than in hope.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 10. REFUSAL
sl, y = content("Refusal as a first-class output", "3 · The two clocks")
tf = txt(sl, ML, y, CW, 1.0)
runs(tf, [("The interesting output of a governance platform is not the answer. "
           "It is the refusal. ", CRIMSON, True),
          ("An answer can be produced by a system that is not checking "
           "anything; a refusal cannot. So every refusal here names the clause "
           "that failed and what to do instead — because a refusal that says "
           "only “forbidden” teaches people to route around the platform.",
           INK, False)],
     size=13, first=True, space_after=0, line=1.28)
code(sl, ML, y + 1.25, CW, [
    "a T0 model cannot be fitted: its parameters come from theory, not",
    "from data — there is nothing to fit",
    "",
    "this edge carries nothing — a wire to nowhere, and the blast radius",
    "would follow it",
    "",
    "a number one person can both produce and bless is a preference, not",
    "an estimate",
], fs=11.5, title="THREE REFUSALS, VERBATIM")

# ============================================================ 11. DESIGN
sl, y = content("The shape of the system", "4 · The design")
band = 0.95
rect(sl, ML, y + 0.05, CW, band, fill=PARCH)
rect(sl, ML, y + 0.05, 0.05, band, fill=SLATE)
tf = txt(sl, ML + 0.32, y + 0.20, CW - 0.7, band - 0.25)
para(tf, "INTERFACES  —  one process", size=10.5, color=SLATE, bold=True,
     first=True, space_after=3)
para(tf, "/api/v1 (REST, RFC-9457 refusals) · server-rendered screens · Python "
         "SDK, standard library only", size=11.5, color=INK, space_after=0,
     line=1.22)
rect(sl, ML, y + 1.18, CW, 1.75, fill=CRIMSON)
tf = txt(sl, ML + 0.32, y + 1.35, CW - 0.7, 1.5)
para(tf, "THE DOMAIN  —  where the formalism lives", size=10.5,
     color=RGBColor(0xE8, 0xB8, 0xC0), bold=True, first=True, space_after=4)
para(tf, "algebra (the kernel, the trainability class) · features (two clocks, "
         "PIT assembly) · warrants (the grammar and its laws) · parameters "
         "(provenance and approval) · evidence (a hash chain) · fibres (a "
         "governance path per model class)",
     size=12, color=WHITE, space_after=0, line=1.24)
rect(sl, ML, y + 3.16, CW * 0.485, band, fill=PARCH)
rect(sl, ML, y + 3.16, 0.05, band, fill=SLATE)
tf = txt(sl, ML + 0.32, y + 3.31, CW * 0.485 - 0.55, band - 0.25)
para(tf, "CONTROL PLANE", size=10.5, color=SLATE, bold=True, first=True,
     space_after=3)
para(tf, "One relational schema. Anything a person reads one at a time is a row.",
     size=11.5, color=INK, space_after=0, line=1.22)
rect(sl, ML + CW * 0.515, y + 3.16, CW * 0.485, band, fill=PARCH)
rect(sl, ML + CW * 0.515, y + 3.16, 0.05, band, fill=SLATE)
tf = txt(sl, ML + CW * 0.515 + 0.32, y + 3.31, CW * 0.485 - 0.55, band - 0.25)
para(tf, "DATA PLANE", size=10.5, color=SLATE, bold=True, first=True,
     space_after=3)
para(tf, "A versioned table format. Anything whose volume scales with business "
         "events.", size=11.5, color=INK, space_after=0, line=1.22)
tf = txt(sl, ML, y + 4.32, CW, 0.6)
runs(tf, [("Separated by SIZE, not by ceremony. ", CRIMSON, True),
          ("And the data plane's table VERSIONS are the transaction-time axis "
           "— which is the mechanism behind L-10 rather than a storage choice.",
           INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ============================================================ 12. DECISIONS
sl, y = content("Four design decisions, and the argument for each",
                "4 · The design")
h = table(sl, [
    ["Decision", "The argument"],
    ["No foreign keys, no CHECK constraints, no triggers",
     "Integrity in two places is integrity that can disagree, and the version "
     "believed is the one with the friendlier error. A trigger that reports "
     "success while dropping the write is the worst available failure mode"],
    ["No migrations",
     "The schema is ONE typed declaration and the DDL for each dialect is "
     "generated from it. Two hand-maintained files can only report a "
     "divergence somebody has already shipped"],
    ["The expression IS the model, where it can be",
     "A closed-form model carries its own arithmetic in the register, so the "
     "equation, the generated code and the answer are derived from one syntax "
     "tree and cannot drift"],
    ["MAYA does not train and does not run",
     "It issues authority and records what came back. A register on the serving "
     "path is a register with an availability requirement, and a governance "
     "control nobody can afford to have fail is one that gets bypassed"],
], ML, y, CW, col_w=[4.0, 7.8], row_h=0.34, fs=11, hfs=11)
tf = txt(sl, ML, y + h + 0.26, CW, 0.7)
runs(tf, [("Each of these costs something, and the cost is stated where the "
           "decision is. ", CRIMSON, True),
          ("Dropping foreign keys means integrity rests on one layer being "
           "correct, with nothing beneath it to catch the fall.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 13. DATA MODEL
sl, y = content("The data, at the level that matters", "5 · The data")
h = table(sl, [
    ["Object", "Identity", "What it pins"],
    ["model", "a URN", "an owner, a legal entity, a purpose, a risk tier"],
    ["model version", "a DIGEST over its manifest",
     "the kernel: runtime, P's kind, X's schema, the expression or artifact"],
    ["feature", "a name, per entity",
     "a dtype, an owner, a retrieval policy. ONE definition, reused"],
    ["feature view version", "a namespace + a table version",
     "the actual bytes. v7 cannot be touched by writing v8"],
    ["featureset version", "a fill of a schema",
     "each slot bound to a feature, a view AND that view's version"],
    ["parameter set", "a digest over its values",
     "provenance (fitted/calibrated/declared), the warrant, the diagnostics"],
    ["warrant", "a signed document",
     "subject, verb, parameters by digest, the data read, expiry"],
    ["evidence node", "a hash chain entry",
     "what happened, who did it, and what the previous node was"],
], ML, y, CW, col_w=[2.5, 3.3, 6.0], row_h=0.30, fs=10.5, hfs=10.5)
tf = txt(sl, ML, y + h + 0.24, CW, 0.7)
runs(tf, [("Read the middle column downwards. ", CRIMSON, True),
          ("Almost every identity is a digest or a version pin rather than a "
           "name — because a stable name over moving contents is the failure "
           "this whole design exists to prevent.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 14. FEATURE OBJ
sl, y = content("A feature is an object, not a column", "5 · The data")
half = (CW - 0.34) / 2
card(sl, ML, y, half, 2.9, "WHAT IT CARRIES",
     "Identity, and a retrieval policy",
     "A name scoped to an entity, a dtype and a shape — scalar, vector, matrix "
     "— an owner, a business definition, and a sensitivity.\n\n"
     "And a RETRIEVAL POLICY: how a missing value is filled, how readings are "
     "normalised, how a value between two timestamps is aligned. It travels "
     "with the feature, because a fill strategy chosen at read time is a "
     "different number in every consumer.")
card(sl, ML + half + 0.34, y, half, 2.9, "WHAT FOLLOWS",
     "Reuse becomes checkable",
     "Two models reading `asset_vol` read ONE definition. A second definition "
     "would be a second answer to one question, and the two would drift "
     "invisibly.\n\n"
     "A DERIVED feature is `Z = f(X, Y)` with the expression stored: its "
     "ingest clock is the MAXIMUM over its inputs, which is arithmetic and "
     "therefore cannot be forgotten, and its lineage is walked whenever it is "
     "used — so a feature derived from the label is refused with the chain "
     "named.")
tf = txt(sl, ML, y + 3.10, CW, 0.9)
runs(tf, [("A featureset is the input object X, made an object. ", CRIMSON,
           True),
          ("It declares a schema of typed slots; a VERSION fills it, binding "
           "each slot to a feature, a view and that view's version. Swapping "
           "which feature fills a slot does not change the model's input space "
           "— it changes what the model was fitted on, which is a different "
           "event with a different control.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 15. EVIDENCE
sl, y = content("Evidence as a semiring, not a log", "5 · The data")
tf = txt(sl, ML, y, CW, 0.9)
runs(tf, [("Every governance act appends a node to a hash chain: what happened, "
           "who did it, and the digest of the node before. ", INK, False),
          ("The interesting part is what you can then COMPUTE over it.",
           CRIMSON, True)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["Question", "The semiring", "⊕ and ⊗"],
    ["Is this claim supported at all?", "BOOLEAN", "or, and"],
    ["How confident is the support?", "VITERBI (max-product)", "max, ×"],
    ["What is the shortest path to a gap?", "TROPICAL", "min, +"],
    ["Which evidence chains support it?", "WHY-PROVENANCE", "∪, ∪-of-products"],
], ML, y + 1.05, CW, col_w=[4.6, 4.0, 3.2], row_h=0.34, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 1.05 + h + 0.28, CW, 1.3)
runs(tf, [("One traversal, four answers. ", CRIMSON, True),
          ("The structure of the question is identical in each case — only the "
           "algebra changes — so a platform that implements the traversal once "
           "gets citation soundness, confidence, gap analysis and provenance "
           "from the same code. Four separate implementations would be four "
           "opportunities to disagree, and they would disagree in the direction "
           "of asserting support that is not there.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 16. FIBRES
sl, y = content("A governance path per model class, and totality",
                "5 · The data")
tf = txt(sl, ML, y, CW, 0.95)
runs(tf, [("A fibration over the trainability class. ", CRIMSON, True),
          ("Each class of model gets its own governance path — what evidence "
           "is required, which validations apply, what an approval means — and "
           "the fibration is checked TOTAL at start-up: every class the "
           "platform can derive has a path defined for it.", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
STEP_H = 1.55
steps(sl, ML, y + 1.15, CW, [
    ("L-15", "Totality, at start-up",
     "A model class arriving at run time with no governance path is a gap "
     "discovered by the model that has it, which is the worst possible time"),
    ("Derived", "Not declared",
     "The class comes from the kernel, so a fibre cannot be selected by "
     "somebody choosing the convenient one"),
    ("Nine", "Fibres today",
     "And the totality gate fails the build if a tenth class becomes derivable "
     "without a path"),
], h=STEP_H)
tf = txt(sl, ML, y + 1.15 + STEP_H + 0.30, CW, 0.9)
runs(tf, [("This is the answer to “what happens when a new kind of model "
           "arrives”. ", CRIMSON, True),
          ("Not a policy review. A totality failure at start-up, naming the "
           "class that has no path.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 17. AI
sl, y = content("Where AI sits in the same formalism", "5 · The data")
tf = txt(sl, ML, y, CW, 0.9)
runs(tf, [("An AI capability is a model: ", INK, False),
          ("P is a prompt and a configuration, X is the context it is given, "
           "and D(Y) is a distribution over text. ", CRIMSON, True),
          ("Nothing about the definition needed changing — which is the "
           "argument for having had one.", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["Tier", "The criterion", "The consequence"],
    ["A", "The output can be mechanically CHECKED by a named oracle",
     "Register it. The oracle is the control, and it runs every time"],
    ["B", "Every claim can be GROUNDED in evidence the platform holds",
     "Unsupported claims are REMOVED rather than flagged, and kept for the "
     "reviewer"],
    ["C", "Neither checkable nor groundable",
     "Deliberately NOT REGISTRABLE. A Tier C capability in a registry is one "
     "that will be wired into a decision one day"],
], ML, y + 1.05, CW, col_w=[0.7, 5.2, 5.9], row_h=0.34, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 1.05 + h + 0.28, CW, 1.1)
runs(tf, [("And the criterion for automation is the same one: ", CRIMSON, True),
          ("a machine may do the work exactly where an oracle can check the "
           "result or evidence can ground it. That is not an AI policy — it is "
           "the definition applied to a new inhabitant of P.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 18. COMPOSITION
sl, y = content("Composition, and the risk that does not compose",
                "5 · The data")
tf = txt(sl, ML, y, CW, 0.9)
runs(tf, [("Models compose — that is what the algebra gives. ", CRIMSON, True),
          ("An `input_to` edge asserts that one model's output arrives where "
           "another's input is read, and MAYA TYPE-CHECKS it: an edge supplying "
           "no field the target reads is refused, because the blast radius "
           "would follow it.", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["Relation", "Propagates?", "Why"],
    ["input_to", "YES", "its output is read as an input — change the source and "
     "the target's answer changes"],
    ["calibrated_by", "YES", "its parameters are solved by that model or "
     "procedure"],
    ["derives_from", "no", "built from it — lineage, not dependency"],
    ["challenger_of", "no", "built to argue with it. A challenger counted as a "
     "dependency would inflate every blast radius it appeared in"],
], ML, y + 1.05, CW, col_w=[2.4, 1.7, 7.7], row_h=0.32, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 1.05 + h + 0.26, CW, 1.1)
runs(tf, [("What does NOT compose is the risk. ", CRIMSON, True),
          ("Two individually validated models composed can be worse than "
           "either — an interaction premium that neither validation could have "
           "found. The composition is typed and checkable; the aggregate risk "
           "has a definition and no computation, and the documentation says so "
           "rather than implying otherwise.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 19. FALSIFY
sl, y = content("How to tell if this is wrong", "5 · The data")
tf = txt(sl, ML, y, CW, 0.85)
runs(tf, [("A formalism that cannot be falsified is a vocabulary. ",
           CRIMSON, True),
          ("These are the claims, and what would refute each:", INK, False)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["The claim", "What would refute it"],
    ["The definition covers every model a bank governs",
     "An artefact that decides something and cannot be written as f : P ⊗ X → "
     "D(Y) without distortion"],
    ["The trainability class is derivable, never declared",
     "Two models with identical kernels that a practitioner insists belong in "
     "different governance classes"],
    ["The laws are executable, not aspirational",
     "A law whose test passes on a system that violates it — which is why the "
     "three that do not run are named"],
    ["One operator, not four implementations",
     "A second point-in-time read anywhere in the platform. The case studies "
     "assert object identity, not agreement, precisely here"],
], ML, y + 0.95, CW, col_w=[4.6, 7.2], row_h=0.34, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 0.95 + h + 0.26, CW, 0.8)
runs(tf, [("The honest limitation. ", CRIMSON, True),
          ("This is a formalism with a reference implementation, not a theorem "
           "with a proof. Its evidence is that the implementation exists, that "
           "the laws execute, and that the places it does not hold are named.",
           INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 20. CLOSE
_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
tf = txt(sl, ML + 0.4, 1.15, CW * 0.84, 1.6)
para(tf, "Say precisely what a model is,", size=32, color=WHITE, font=SERIF,
     italic=True, first=True, space_after=6, line=1.22)
para(tf, "and most of the governance follows.", size=32,
     color=RGBColor(0xF4, 0xDF, 0xE3), font=SERIF, italic=True, space_after=0,
     line=1.22)
rect(sl, ML + 0.4, 3.30, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.4, 3.65, CW * 0.52, 2.4)
para(tf, "THE THREE IDEAS", size=10, color=RGBColor(0xE0, 0xA8, 0xB2),
     bold=True, first=True, space_after=10)
for line in ["f : P ⊗ X → D(Y) — and P is where estates differ",
             "Two clocks, and min(label, as_of) between them",
             "A law is a proposition with a test that executes it"]:
    para(tf, line, size=13.5, color=WHITE, space_after=8, line=1.22)
tf = txt(sl, ML + CW * 0.58, 3.65, CW * 0.42, 2.4)
para(tf, "WHERE THE DETAIL IS", size=10, color=RGBColor(0xE0, 0xA8, 0xB2),
     bold=True, first=True, space_after=10)
for line in ["docs/00 — the foundations and the law table",
             "docs/research/ — the paper, 33 pages",
             "The design deck — 123 slides, five parts"]:
    para(tf, line, size=12, color=RGBColor(0xF6, 0xE6, 0xE9), space_after=8,
         line=1.22)
footer(sl)
