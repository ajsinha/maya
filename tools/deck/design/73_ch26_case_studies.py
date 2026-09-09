"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Chapter 26 — the six worked case studies in `case_studies/`.

Every number on these slides is printed by a script somebody can run against a
live MAYA in about a minute. That is the point of the chapter: the rest of the
deck argues, and this part is checkable.
"""
# -*- coding: utf-8 -*-

divider("26", "Six Worked Case Studies",
        "Six real banking models, registered end to end — fitted outside MAYA, "
        "governed inside it.",
        ["What they are", "The boundary they draw", "Each one, and its point",
         "What the platform refused", "What they do not cover"])

# --------------------------------------------------------------- the set
sl, y = content("Six models, chosen to cover the taxonomy",
                "Case studies · the set")
h = table(sl, [
    ["#", "Model", "Class", "Domain", "Why this one"],
    ["1", "Black–Scholes European call", "T1", "Markets",
     "A model with NO training data. The whole pricer — normal CDF included — "
     "is one expression in the register"],
    ["2", "Home price regression (Ames)", "T2", "Retail collateral",
     "REAL public data from its authoritative source, and the second clock the "
     "source did not have"],
    ["3", "Mortgage prepayment (CPR)", "T2", "Treasury / ALM",
     "Non-linear in the inputs, linear in the parameters: exponential ramp plus "
     "a cubic S-curve"],
    ["4", "Merton distance to default", "T0", "Wholesale credit",
     "NO parameters at all. Asking to train it is a type error, refused twice "
     "by two independent layers"],
    ["5", "IFRS 9 expected credit loss", "T2", "Impairment",
     "REUSE: five features it did not define, a composed featureset, and a "
     "type-checked dependency edge"],
    ["6", "HELOC origination eligibility", "T8", "Retail credit",
     "A policy RULEBOOK governed as a model — checked, trialled, published, "
     "approved by a second person"],
], ML, y, CW, col_w=[0.35, 2.5, 0.6, 1.6, 6.55], row_h=0.30, fs=10, hfs=10)
tf = txt(sl, ML, y + h + 0.22, CW, 0.6)
runs(tf, [("The trainability class is derived, never declared. ", CRIMSON, True),
          ("These six span T0 (parameters from theory), T1 (calibrated to "
           "market), T2 (estimated from a sample) and T8 (authored as rules) — "
           "and the class decides which operations the platform will admit.",
           INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ------------------------------------------------------------ the boundary
sl, y = content("What the scripts do, and what MAYA does",
                "Case studies · the boundary")
tf = txt(sl, ML, y, CW, 0.7)
runs(tf, [("MAYA is a register. It does not train models and it does not run "
           "them. ", CRIMSON, True),
          ("Each script plays the bank's own modelling engine: it fits in its "
           "own process, with its own arithmetic, and talks to MAYA only to ask "
           "permission and to record what it did. The console marks every line "
           "as one or the other.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
STEP_H = 1.55
steps(sl, ML, y + 0.95, CW, [
    ("1", "Ask", "a TRAINING warrant from MAYA — authority before any data is "
     "read"),
    ("2", "Fit", "LOCALLY, outside MAYA, in the bank's own environment"),
    ("3", "Deliver", "the parameters back under that warrant. They land "
     "PROPOSED"),
    ("4", "Approve", "by somebody who is not the author. Self-approval is "
     "refused"),
    ("5", "Run", "under an EXECUTION warrant — locally again. MAYA is not in "
     "the loop"),
], h=STEP_H)
tf = txt(sl, ML, y + 0.95 + STEP_H + 0.26, CW, 0.6)
runs(tf, [("Nothing calls the captive engine or the captive estimator. ",
           CRIMSON, True),
          ("MAYA ships both for demonstrations, and using either in a case "
           "study would teach the opposite of the boundary these exist to draw.",
           INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ------------------------------------------------- 1 and 4: the two extremes
sl, y = content("The two extremes: a calibrated pricer and a model with no parameters",
                "Case studies · 1 and 4")
half = (CW - 0.34) / 2
card(sl, ML, y, half, 3.05, "CASE 1 · T1 · CALIBRATED",
     "Black–Scholes European call",
     "No training data exists for an option pricer, and none is needed. One "
     "number is calibrated to market: implied volatility.\n\n"
     "The whole model — including an Abramowitz–Stegun approximation of the "
     "normal CDF — is ONE EXPRESSION in the register, checked against math.erf "
     "to 4.8e-06 before anything is registered. No artifact to lose, no library "
     "version to disagree with.\n\n"
     "Calibrating one flat vol to the at-the-money quote reprices the wings "
     "badly. That RMSE is recorded as a STATED LIMITATION on the parameter set, "
     "so the reviewer reads it before approving.")
card(sl, ML + half + 0.34, y, half, 3.05, "CASE 4 · T0 · NOTHING TO FIT",
     "Merton distance to default",
     "Five observables, a closed form, no parameter object at all. P is the "
     "terminal object.\n\n"
     "Asking for a training warrant is not a permissions problem — it is a TYPE "
     "ERROR, and two independent layers say so differently:\n\n"
     "grammar: \"a T0 model cannot be fitted: its parameters come from theory, "
     "not from data\"\n\n"
     "register: \"nothing a fit could have produced — record them with "
     "provenance 'declared'\", which points at the honest alternative rather "
     "than only saying no.")

# --------------------------------------------------------- 2 and 3: the data
sl, y = content("Real public data, and a curve a bank actually uses",
                "Case studies · 2 and 3")
half = (CW - 0.34) / 2
card(sl, ML, y, half, 3.05, "CASE 2 · T2 · ESTIMATED",
     "Home price regression, on public data",
     "2,928 real sales from Dean De Cock's own file at jse.amstat.org — the "
     "authoritative source, not a mirror. No synthetic fallback: if the "
     "download fails the script stops.\n\n"
     "The regression is unremarkable and is not the point. The SOURCE CARRIES "
     "ONE CLOCK and MAYA requires two, so a 45-day recording lag is an "
     "assumption somebody has to own — written on the feature view, on the "
     "parameter set and in the specification.\n\n"
     "Condition number 229,832, reported beside R². It is the number that says "
     "whether the coefficients mean anything individually.")
card(sl, ML + half + 0.34, y, half, 3.05, "CASE 3 · T2 · ESTIMATED",
     "Mortgage prepayment curve",
     "CPR rises along an exponential seasoning ramp and responds to refinancing "
     "incentive along a cubic S-curve.\n\n"
     "NON-LINEAR IN THE INPUTS, LINEAR IN THE PARAMETERS — so least squares "
     "fits it, the fit is deterministic and reproducible, and every coefficient "
     "keeps a standard error and an interpretation.\n\n"
     "The curve is INSIDE the registered expression rather than in a feature "
     "pipeline beside it. Otherwise the model is linear on paper and non-linear "
     "in reality, and the part a supervisor asks about lives somewhere nobody "
     "governs.")

# ------------------------------------------------------------- 5: the reuse
sl, y = content("Reuse: what happens when two models share ground",
                "Case studies · 5")
tf = txt(sl, ML, y, CW, 0.55)
runs(tf, [("Case study 5 — IFRS 9 expected credit loss. ", CRIMSON, True),
          ("Three kinds of reuse, and they are different things. This is where "
           "model risk actually lives: not in any single model, but in what "
           "depends on what.", INK, False)],
     size=12, first=True, space_after=0, line=1.26)
h = table(sl, [
    ["Kind of reuse", "What it means", "What the platform does about it"],
    ["Features, shared not copied",
     "Five features already existed against the obligor entity; this model "
     "finds them rather than redefining them",
     "A second definition of asset_vol would be a second answer to one "
     "question, and the two would drift invisibly"],
    ["The featureset is COMPOSED",
     "ecl_inputs folds merton_inputs and adds four slots, resolving to nine — "
     "five never typed out",
     "Operations are total: an `add` of a slot a parent already has is refused, "
     "because an operation that silently did nothing is one somebody believes "
     "happened"],
    ["The models are RELATED",
     "The Merton PD is written back as a feature and read here, so the "
     "input_to edge carries something",
     "MAYA TYPE-CHECKS THE EDGE. The first attempt was refused: an edge "
     "supplying no field the target reads is “a wire to nowhere, and the "
     "blast radius would follow it”"],
], ML, y + 0.72, CW, col_w=[2.6, 4.2, 4.8], row_h=0.30, fs=10.5, hfs=10.5)
tf = txt(sl, ML, y + 0.72 + h + 0.24, CW, 0.6)
runs(tf, [("And then the blast radius is an answer rather than a recollection. ",
           CRIMSON, True),
          ("A change to the Merton model reaches one model, at tier 2, distance "
           "1 — computed from the graph. `input_to` propagates; `challenger_of` "
           "deliberately does not, because a challenger counted as a dependency "
           "would inflate every blast radius it appeared in.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ------------------------------------------------------------ 6: the rulebook
sl, y = content("A credit policy is a model, and this is what governing one looks like",
                "Case studies · 6")
tf = txt(sl, ML, y, CW, 0.55)
runs(tf, [("Case study 6 — HELOC origination eligibility, class T8. ",
           CRIMSON, True),
          ("Parameters that are AUTHORED rather than fitted. A rulebook that "
           "declines an application and has to be explained to the person it "
           "refused is doing exactly what a scorecard does — and a register "
           "that governs the scorecard but not the rulebook is governing the "
           "easier half.", INK, False)],
     size=12, first=True, space_after=0, line=1.26)
RULE_H = 1.6
steps(sl, ML, y + 0.80, CW, [
    ("CHECK", "against the schema",
     "a rule reading a field the version does not declare is REFUSED, before "
     "anybody can approve it"),
    ("TRIAL", "over sample rows",
     "no warrant, no record — an author reading their own draft back. Reports "
     "which rules never fired"),
    ("PUBLISH", "as a parameter set",
     "lands PROPOSED. A change to a threshold is a new parameter set, not a "
     "new model version"),
    ("EXPLAIN", "in English",
     "ONE rendering, so the model card, the committee paper and the export "
     "pack cannot differ"),
], h=RULE_H)
tf = txt(sl, ML, y + 0.80 + RULE_H + 0.24, CW, 0.9)
runs(tf, [("Two things MAYA requires, and both are load-bearing. ",
           CRIMSON, True),
          ("An `otherwise` clause, so no application falls through to a "
           "behaviour nobody wrote down. And a `because` on every rule — "
           "without one a rule cannot be defended to a supervisor, reviewed by "
           "whoever owns the policy, or retired later, because nobody knows "
           "what it was for. Every decision carries the rule that fired and "
           "that rule's reason, which under most consumer-credit regimes is "
           "the obligation rather than the decision itself.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# --------------------------------------------------------- what refused
sl, y = content("What the platform refused, on purpose",
                "Case studies · the refusals")
tf = txt(sl, ML, y, CW, 0.5)
runs(tf, [("A control nobody has watched refuse is a control nobody has "
           "tested. ", CRIMSON, True),
          ("Every case study deliberately asks for something it should not "
           "get, and prints the refusal with its remediation.", INK, False)],
     size=12, first=True, space_after=0, line=1.26)
h = table(sl, [
    ["Case", "What was attempted", "What MAYA said"],
    ["1", "A calibration warrant naming a featureset that does not exist; then "
     "the author of a parameter set approving their own numbers",
     "no featureset '…'; and a number one person can both produce and bless is "
     "a preference, not an estimate"],
    ["2", "A training read bounded in only one clock",
     "L-W9 — a featureset read for fitting must bound the period it covers"],
    ["3", "A training warrant against a featureset lacking a regressor",
     "L-W10 — adding a regressor is a model change, not a data change"],
    ["4", "A fit on a model with no parameters; then writing the numbers in "
     "anyway",
     "a T0 model cannot be fitted; and there is nothing a fit could have "
     "produced — use provenance 'declared'"],
    ["5", "Adding a featureset slot a parent already has; and an input_to edge "
     "carrying nothing",
     "say 'override' if replacing it is what is meant; and an edge that "
     "supplies no field the target reads is a wire to nowhere"],
    ["6", "A rule reading a field the version does not declare",
     "refused at check — a rule that never fires still appears in the model "
     "card and nobody reading it can tell"],
], ML, y + 0.68, CW, col_w=[0.6, 4.9, 6.1], row_h=0.30, fs=10, hfs=10)

# ------------------------------------------------------------ honest limits
sl, y = content("What the case studies do not show", "Case studies · the limits")
tf = txt(sl, ML, y, CW, 0.5)
runs(tf, [("Stated, because a demonstration that only shows what works is a "
           "sales pitch.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.26)
bullets(txt(sl, ML, y + 0.66, CW, 3.5), [
    "No monitoring, validation or findings. These build a model up to its "
    "first approved parameter set; what happens over its life — drift, "
    "breaches, revalidation, the worklist — is a separate demonstration.",
    "Only case study 2 uses real market data. Cases 1, 3, 4, 5 and 6 are "
    "synthetic from data-generating processes stated in the scripts, and each "
    "says so in the first paragraph of its data section.",
    "Nothing is deployed. A version is approved and a warrant is issued; no "
    "engine is wired to anything.",
    "Case 6 records an honest finding rather than hiding it: MAYA ISSUES a fit "
    "warrant for a T8 rule set. The grammar refuses a fit only for T0 and T6, "
    "so the refusal lives one layer down in the runtime. The control holds "
    "because the fit cannot execute — but the grammar is the layer that should "
    "have said no.",
    "Three classes are still uncovered: T3 (iteratively trained), T6 (a "
    "vendor's parameters nobody can see) and T5/T7 (configured, elicited).",
], size=12, gap=11)
