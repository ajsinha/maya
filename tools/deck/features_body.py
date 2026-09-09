"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

THE FEATURE PLATFORM DECK — twenty slides on features and featuresets.

**The audience.** A data or feature-platform engineer, and the model-risk
person who has to sign off on what a model was fitted on. Somebody who has
probably built or bought a feature store and wants to know what this one does
differently — and the answer is not "it stores features".

**The thread.** A feature store answers *what is the value*. A register has to
answer *what was the value, as far as anybody knew, on the day that decision
was taken* — and then prove the answer is the same one it gave last year.
Everything on these slides falls out of that difference: two clocks, version
pins, composition that type-checks, and a retrieval API that pins rather than
reads the head.
"""
# -*- coding: utf-8 -*-

_state["chapter"] = "MAYA · Feature & Featureset Management"

# ============================================================ 1. TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.35, fill=CRIMSON)
rect(sl, 0, 4.35, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.35, fill=CRIMSON_D)
tf = txt(sl, ML + 0.3, 0.92, CW, 0.34)
para(tf, "FEATURES  ·  FEATURESETS  ·  COMPOSITION  ·  VERSIONING  ·  RETRIEVAL",
     size=11, color=RGBColor(0xE8, 0xB8, 0xC0), bold=True, first=True,
     space_after=0)
tf = txt(sl, ML + 0.3, 1.42, CW * 0.88, 2.1)
para(tf, "Not what the value is —", size=40, color=WHITE, font=SERIF,
     first=True, space_after=2)
para(tf, "what was knowable when", size=40, color=WHITE, font=SERIF,
     space_after=0)
rect(sl, ML + 0.3, 3.22, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.3, 3.50, CW * 0.82, 0.7)
para(tf, "The MAYA feature platform, in twenty slides",
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
for i, c in enumerate(["The feature", "The two clocks", "Composition",
                       "Versioning", "Retrieval"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=11.5,
         space_after=5)
footer(sl)

# ============================================================ 2. THE GAP
sl, y = content("What a feature store answers, and what a register must",
                "1 · The feature")
half = (CW - 0.34) / 2
card(sl, ML, y, half, 2.55, "A FEATURE STORE",
     "What is the value?",
     "Serve the current value fast, and keep a history so a training job can "
     "look backwards. Correct, useful, and solves the engineering problem.\n\n"
     "It answers a question about the DATA.")
card(sl, ML + half + 0.34, y, half, 2.55, "A REGISTER",
     "What was knowable, when?",
     "What was the value as far as anybody KNEW on the day that decision was "
     "taken — and prove it is the same answer given last year, after three "
     "restatements have landed.\n\n"
     "It answers a question about the DECISION.")
tf = txt(sl, ML, y + 2.80, CW, 1.7)
runs(tf, [("Those are different questions, and the second is strictly harder. ",
           CRIMSON, True),
          ("A history of values tells you what a row says now about the past. "
           "It does not tell you what the row SAID in the past — because the "
           "row has since been corrected, and the correction overwrote the "
           "thing a model was actually fitted on.\n\n", INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("Everything on the next eighteen slides falls out of that "
           "difference.", INK, True)],
     size=13, space_after=0, line=1.30)

# ============================================================ 3. THE OBJECT
sl, y = content("A feature is an object, not a column", "1 · The feature")
h = table(sl, [
    ["What it carries", "Why it is on the FEATURE rather than the consumer"],
    ["name, scoped to an ENTITY",
     "`asset_vol` means one thing for an obligor and another for a pool. The "
     "entity is part of the identity"],
    ["dtype and SHAPE — scalar, [12], [3,3]",
     "A twelve-month balance vector and a 3×3 correlation matrix are features, "
     "not twelve and nine columns somebody has to reassemble correctly"],
    ["owner, business definition, source system",
     "“Who do I ask what this means” has a name in it, and the answer does not "
     "depend on who you ask"],
    ["sensitivity, PII, protected basis",
     "The fairness and privacy questions are answerable by query rather than "
     "by an interview"],
    ["a RETRIEVAL POLICY — fill, normalisation, alignment",
     "A fill strategy chosen at read time is a different number in every "
     "consumer. Travelling with the feature makes it one number"],
], ML, y, CW, col_w=[4.0, 7.8], row_h=0.32, fs=11, hfs=11)
tf = txt(sl, ML, y + h + 0.28, CW, 0.9)
runs(tf, [("The retrieval policy is the one people are surprised by. ",
           CRIMSON, True),
          ("Two teams reading the same feature and filling missing values "
           "differently are reading two different features, and nothing in a "
           "column-shaped world can tell them so.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 4. TWO CLOCKS
sl, y = content("Two clocks on every row — and a row missing either is refused",
                "2 · The two clocks")
tf = txt(sl, ML, y, CW, 0.75)
runs(tf, [("event_ts", CRIMSON, True),
          (" — when the fact was TRUE in the world.        ", INK, False),
          ("ingest_ts", CRIMSON, True),
          (" — when the recording system LEARNED it.", INK, False)],
     size=15, first=True, space_after=0, line=1.28)
ch = code(sl, ML, y + 0.85, CW, [
    "{\"entity_id\": \"C1\", \"event_ts\": 100.0, \"ingest_ts\": 110.0, \"dscr\": 1.20}",
    "{\"entity_id\": \"C2\", \"event_ts\": 100.0, \"ingest_ts\": 110.0, \"dscr\": 2.10}",
    "",
    "# THE RESTATEMENT — same entity, same event time, later ingest, worse number",
    "{\"entity_id\": \"C1\", \"event_ts\": 100.0, \"ingest_ts\": 900.0, \"dscr\": 0.40}",
], fs=11, title="THREE ROWS, AND THE THIRD IS THE WHOLE PROBLEM")
tf = txt(sl, ML, y + 0.85 + ch + 0.22, CW, 1.8)
runs(tf, [("A set built before ingest 900 must still see 1.20; one built "
           "after must see 0.40. ", CRIMSON, True),
          ("Both are correct, and one clock can only give whichever number is "
           "there now. A row missing either is refused at the UPLOAD, because "
           "two layers later it has stopped being fixable.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 5. THE OPERATOR
sl, y = content("One operator, and the minimum is the guarantee",
                "2 · The two clocks")
ch = code(sl, ML, y, CW * 0.58, [
    "knowable_by = min(label_ts, as_of)",
    "",
    "admissible = [ r for r in records",
    "               if r.event  <= label_ts",
    "              and r.ingest <= knowable_by ]",
], fs=12.5, title="THE POINT-IN-TIME READ")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.2)
runs(tf, [("Why the MINIMUM", CRIMSON, True)],
     size=13, first=True, space_after=8, line=1.24)
para(tf, "Bounding ingest by min(label, as_of) makes every observation time at "
         "or after the label date give the same answer.",
     size=12, color=INK, space_after=8, line=1.26)
para(tf, "The row assembled the day a label matured, and the same row "
         "re-assembled a year later, are identical — however many restatements "
         "arrived in between.",
     size=12, color=INK, space_after=8, line=1.26)
para(tf, "Bound by as_of alone and the set changes every time you rebuild it. "
         "Bound by label alone and it leaks.",
     size=12, color=SLATE, space_after=0, line=1.26)
tf = txt(sl, ML, y + ch + 0.26, CW * 0.58, 1.6)
runs(tf, [("Ties are broken by CONTENT. ", CRIMSON, True),
          ("Two facts can share both clocks, and then the order must still be "
           "deterministic — so the tie-break is a total order over the row's "
           "own values, not insertion order and not a surrogate id. Either of "
           "those lets two implementations disagree while both look correct.",
           INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 6. VIEWS
sl, y = content("Where values live: one upload is one view VERSION",
                "3 · Versioning")
tf = txt(sl, ML, y, CW, 0.8)
runs(tf, [("A feature is a definition. A ", INK, False),
          ("view", CRIMSON, True),
          (" is where its values live, and a ", INK, False),
          ("view version", CRIMSON, True),
          (" is one materialisation of them — its own namespace, its own bytes.",
           INK, False)],
     size=13.5, first=True, space_after=0, line=1.28)
ch = code(sl, ML, y + 0.95, CW, [
    "features/{entity}/{view}/v7      <- v7 is its own namespace",
    "features/{entity}/{view}/v8      <- writing v8 CANNOT touch what v7 serves",
], fs=12, title="A VERSION IS A NAMESPACE, NOT A FLAG")
tf = txt(sl, ML, y + 0.95 + ch + 0.24, CW, 2.2)
runs(tf, [("Half a version is not something anybody can pin, ", CRIMSON, True),
          ("so one upload becomes one version — atomic, and either wholly there "
           "or not there.\n\n", INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("The failure this prevents, five times over: ", CRIMSON, True),
          ("a stable NAME whose contents moved. A featureset that bound a view "
           "by path was reproducible until somebody wrote to that view again — "
           "and nothing announced it, because the path was still valid and the "
           "read still worked.", INK, False)],
     size=13, space_after=0, line=1.30)

# ============================================================ 7. DERIVED
sl, y = content("Derived features: Z = f(X, Y), with the lineage kept",
                "4 · Composition")
ch = code(sl, ML, y, CW * 0.56, [
    "maya.features.derive(",
    "    name=\"cltv\", dtype=\"numeric\",",
    "    expression=\"(first_lien + line) / property_value\",",
    "    description=\"combined loan to value\")",
], fs=11, title="ONE DEFINITION, IN THE CATALOGUE")
x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.3)
runs(tf, [("Two things happen without asking.", CRIMSON, True)],
     size=13, first=True, space_after=8, line=1.24)
para(tf, "Its ingest clock is the MAXIMUM over its inputs — which is "
         "arithmetic, and therefore cannot be forgotten by whoever writes the "
         "pipeline.",
     size=12, color=INK, space_after=8, line=1.26)
para(tf, "Its lineage is walked whenever it is used, so a feature derived from "
         "the label is refused with the derivation chain named rather than with "
         "a bare no.",
     size=12, color=INK, space_after=0, line=1.26)
tf = txt(sl, ML, y + ch + 0.26, CW * 0.56, 1.9)
runs(tf, [("Why this matters more than it looks. ", CRIMSON, True),
          ("A CLTV computed one way in origination and another way in "
           "monitoring is the ordinary way a policy limit turns out not to have "
           "been applied — and both systems pass their own tests. One "
           "definition, in the catalogue, is the only fix that scales.",
           INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 8. FEATURESET
sl, y = content("A featureset is the input object X, made an object",
                "4 · Composition")
STEP_H = 1.70
steps(sl, ML, y + 0.05, CW, [
    ("SCHEMA", "typed slots",
     "A featureset DECLARES named slots with types. By the schema order, that "
     "is exactly what a model kernel is defined over"),
    ("VERSION", "the schema filled",
     "Each slot bound to a feature, a VIEW, and that view's VERSION. Not a "
     "path — a path is mutable"),
    ("PIN", "same version, same bytes",
     "One featureset version resolves to the same rows on every read, "
     "permanently. That is the property everything else rests on"),
], h=STEP_H)
tf = txt(sl, ML, y + 0.05 + STEP_H + 0.35, CW, 2.0)
runs(tf, [("The separation does three things. ", CRIMSON, True),
          ("Swapping which feature fills a slot does not change the model's "
           "input space — it changes what the model was fitted on, which is a "
           "different event with a different control. A version that cannot "
           "fill the schema is refused, because adding a slot is a change to X "
           "and therefore a MODEL change rather than a data change. And because "
           "every binding pins a version, a stable identifier over moving "
           "contents — the failure this whole design exists to prevent — "
           "becomes impossible rather than unlikely.", INK, False)],
     size=13, first=True, space_after=0, line=1.30)

# ============================================================ 9. COMPOSITION
sl, y = content("Inheritance and composition: a left-to-right fold",
                "4 · Composition")
ch = code(sl, ML, y, CW, [
    "maya.featuresets.define(",
    "    name=\"ecl_inputs\", entity=\"obligor\", slots={},",
    "    composes=[\"merton_inputs\"],                       # the parent",
    "    operations=[{\"op\": \"add\", \"name\": \"pd_horizon\", \"value\": \"numeric\"},",
    "                {\"op\": \"add\", \"name\": \"lgd\",        \"value\": \"numeric\"}])",
    "",
    "# resolves to 9 slots — five inherited and never typed out here",
], fs=11, title="COMPOSED, NOT REWRITTEN")
tf = txt(sl, ML, y + ch + 0.26, CW, 2.1)
runs(tf, [("Parents fold left to right, and the RIGHTMOST WINS. ",
           CRIMSON, True),
          ("A set's own operations apply last, and are therefore the most "
           "prominent thing about it — which is right, because they are what "
           "this set says that its parents did not.\n\n", INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("Change the parent and the child changes with it, ", INK, False),
          ("by construction rather than by somebody remembering. That is the "
           "difference between reuse and copying, and it is the whole reason to "
           "compose rather than restate.", CRIMSON, True)],
     size=13, space_after=0, line=1.30)

# ============================================================ 10. TOTALITY
sl, y = content("Every operation is total — a no-op is refused",
                "4 · Composition")
h = table(sl, [
    ["Operation", "Refused when", "Because"],
    ["add", "a parent already has that slot",
     "“say 'override' if replacing it is what is meant; the two read "
     "differently to a reviewer and should”"],
    ["override", "no parent has it",
     "“say 'add' if introducing it is what is meant”"],
    ["drop", "none of the parents has it",
     "“a drop that quietly does nothing leaves a child differing from what its "
     "author believed they wrote”"],
], ML, y, CW, col_w=[1.6, 3.6, 6.6], row_h=0.34, fs=11.5, hfs=11)
tf = txt(sl, ML, y + h + 0.32, CW, 2.2)
runs(tf, [("An operation that silently did nothing is one somebody believes "
           "happened. ", CRIMSON, True),
          ("That is the entire argument, and it is the same argument as “no "
           "step may report success while doing nothing” applied to schema "
           "composition.\n\n", INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("Two more guards. ", CRIMSON, True),
          ("A set that composes itself through a cycle is refused with the "
           "cycle drawn; and the composition depth is bounded, because a "
           "featureset nobody can hold in their head is one nobody reviews.",
           INK, False)],
     size=13, space_after=0, line=1.30)

# ============================================================ 11. LATTICE
sl, y = content("The schema order — what makes substitutability computable",
                "4 · Composition")
tf = txt(sl, ML, y, CW, 0.85)
runs(tf, [("Field u ACCEPTS field v when they share a dtype, u is nullable if "
           "v is, and u's bounds are no narrower. ", INK, False),
          ("Lift that to schemas and you have a partial order — and with it, a "
           "lattice.", CRIMSON, True)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["", "Reads as", "What it answers"],
    ["A ⊒ B", "A refines B — anywhere B is expected, A will do",
     "Is this featureset version a safe REPLACEMENT for that one? (L-7, at "
     "promotion)"],
    ["A ⊓ B", "meet — the union of fields, each widened",
     "What is the weakest schema BOTH of these satisfy?"],
    ["A ⊔ B", "join — the intersection, each narrowed",
     "What can a consumer rely on if it might receive either?"],
    ["no meet", "a shared field with two dtypes",
     "These two cannot be reconciled, and the refusal names the field"],
], ML, y + 1.00, CW, col_w=[1.3, 4.3, 6.2], row_h=0.32, fs=11, hfs=11)
tf = txt(sl, ML, y + 1.00 + h + 0.26, CW, 0.9)
runs(tf, [("One relation, four questions. ", CRIMSON, True),
          ("Substitutability, admissibility, refinement and contract "
           "compatibility are the same computation — and answering them with "
           "four separate implementations is four opportunities to disagree, "
           "in the direction of permitting more.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 12. RESTATEMENT
sl, y = content("Restatement is REPORTED, never silently absorbed",
                "5 · Versioning")
tf = txt(sl, ML, y, CW, 0.9)
runs(tf, [("A pin says what a read returns. It does not say the world stood "
           "still. ", CRIMSON, True),
          ("Those are two different questions and MAYA answers them "
           "separately.", INK, False)],
     size=13.5, first=True, space_after=0, line=1.28)
half = (CW - 0.34) / 2
card(sl, ML, y + 1.05, half, 2.25, "THE READ",
     "pinned, and unchanged",
     "A read at featureset version 3 returns exactly what version 3 is. New "
     "data written underneath does not change it, cannot change it, and does "
     "not need to be excluded by anybody remembering to exclude it.")
card(sl, ML + half + 0.34, y + 1.05, half, 2.25, "THE QUESTION BESIDE IT",
     "restated() — has the ground moved?",
     "Answerable per view and per featureset slot: HAS anything under this pin "
     "been written to since? A validator comparing two runs asks this before "
     "comparing anything, and a replay reports it separately from whether the "
     "test still passes.")
tf = txt(sl, ML, y + 3.55, CW, 0.8)
runs(tf, [("The distinction matters most when it is inconvenient. ",
           CRIMSON, True),
          ("A replay that silently followed a restatement would report that a "
           "validation reproduces when it does not — a finding about the data "
           "presented as a finding about the test.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 13. TRAINING SET
sl, y = content("A training set is a snapshot, not a query",
                "5 · Versioning")
ch = code(sl, ML, y, CW, [
    "snapshot = maya.featuresets.training_set(",
    "    \"cpr_inputs\", version=1,",
    "    spine=[{\"entity_id\": \"POOL-001\", \"label_ts\": 1767225600.0}, ...],",
    "    as_of=1767225600.0)",
], fs=11.5, title="YOU SUPPLY THE SPINE AND THE AS-OF; THE SET SUPPLIES THE COLUMNS")
tf = txt(sl, ML, y + ch + 0.26, CW, 2.6)
runs(tf, [("What comes back is an immutable, digested, named object ",
           CRIMSON, True),
          ("with its point-in-time report attached and the exact table versions "
           "it read recorded on it. A fit warrant pins the snapshot, so the "
           "engine recomputes nothing and the validator re-reads exactly what "
           "the fit saw.\n\n", INK, False)],
     size=13, first=True, space_after=0, line=1.30)
runs(tf, [("Verified in three layers, and each proves something different: ",
           CRIMSON, True),
          ("a static check that the assembly is bounded in BOTH clocks; a "
           "sampled independent recomputation that does not reuse the assembly "
           "path; and a purity screen for features that could only have been "
           "known after the label. A set that fails is refused, not flagged — "
           "and a fit on a snapshot the verifier rejected is refused too.",
           INK, False)],
     size=13, space_after=0, line=1.30)

# ============================================================ 14. SDK 1
sl, y = content("Retrieval via the SDK: define, load, compose, fill",
                "6 · Retrieval")
code(sl, ML, y, CW, [
    "from maya_sdk import Maya",
    "maya = Maya(\"https://maya.internal\", \"a.mehta\", \"…\")",
    "",
    "maya.features.define(name=\"dscr\", entity=\"borrower\", dtype=\"numeric\",",
    "                     description=\"debt service coverage\",",
    "                     owner=\"person/a.mehta\", shape=None)",
    "maya.features.derive(name=\"cltv\", expression=\"(a + b) / v\")",
    "",
    "maya.features.create_view(name=\"borrower_facts\", entity=\"borrower\",",
    "                          owner=\"person/a.mehta\", features=[\"dscr\", \"ltv\"])",
    "maya.views.materialise(\"borrower_facts\", rows=rows)   # one upload = one version",
    "",
    "maya.featuresets.define(name=\"pd_inputs\", entity=\"borrower\",",
    "                        slots={\"coverage\": \"numeric\"},",
    "                        label_slot=\"defaulted\", outcome_window_days=365)",
    "maya.featuresets.fill(\"pd_inputs\", bindings={\"coverage\": \"dscr\"})",
], fs=10.5, title="THE WRITE PATH — STANDARD LIBRARY ONLY, NO DEPENDENCIES")
tf = txt(sl, ML, SH - 1.22, CW, 0.6)
runs(tf, [("The SDK is deliberately dependency-free. ", CRIMSON, True),
          ("A governance client with a dependency tree moves the deployment "
           "problem into somebody else's build pipeline rather than solving it.",
           INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ============================================================ 15. SDK 2
sl, y = content("Retrieval via the SDK: reading, at a pin",
                "6 · Retrieval")
code(sl, ML, y, CW, [
    "maya.featuresets.resolved(\"ecl_inputs\")        # slots, parents folded in",
    "maya.featuresets.get(\"ecl_inputs\")             # the versions and their pins",
    "maya.features.lineage(\"cltv\")                  # what it rests on, and what rests on it",
    "",
    "maya.views.as_of(\"borrower_facts\", version=3,  # the PIT read, explained",
    "                 label_ts=…, as_of=…)          # row by row. Writes nothing",
    "",
    "maya.featuresets.data(\"pd_inputs\", version=1,  # bulk, to a file",
    "                      into=\"train.parquet\", format=\"parquet\")",
    "maya.featuresets.parts(\"pd_inputs\", version=1) # each namespace AND its pin,",
    "                                               # so an engine can pull in parallel",
], fs=10.5, title="THE READ PATH")
tf = txt(sl, ML, y + 2.85, CW, 1.5)
runs(tf, [("Every read uses the PINNED version, never the head. ",
           CRIMSON, True),
          ("What comes out is what a version IS, rather than what its path has "
           "since become — which is the difference between a training set you "
           "can defend and one you can only describe.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 16. BULK
sl, y = content("The one layer where the rules invert", "6 · Retrieval")
tf = txt(sl, ML, y, CW, 0.95)
runs(tf, [("Every other surface here moves small documents. Feature values are "
           "not small, ", INK, False),
          ("and an API that turns a few million rows into JSON objects spends "
           "most of its time and nearly all of its memory on punctuation.",
           CRIMSON, True)],
     size=13, first=True, space_after=0, line=1.28)
h = table(sl, [
    ["Format", "For", "Why it is offered"],
    ["arrow", "an execution engine", "zero-copy, incremental in both directions"],
    ["parquet", "disk and hand-off", "under half of NDJSON for the same rows"],
    ["ndjson", "anything at all", "the lowest common denominator that streams"],
    ["json", "a page", "HARD-CAPPED, because a browser is not a data pipe"],
], ML, y + 1.15, CW, col_w=[1.4, 3.4, 7.0], row_h=0.32, fs=11.5, hfs=11)
tf = txt(sl, ML, y + 1.15 + h + 0.28, CW, 1.5)
runs(tf, [("Nothing is materialised whole. ", CRIMSON, True),
          ("Reads iterate record batches straight off the files and writes "
           "parse a batch at a time, so peak memory is one batch rather than "
           "one dataset. And a batch is sized by CELLS rather than rows — "
           "sixteen thousand rows of six columns is a few megabytes, and "
           "sixteen thousand rows of two thousand columns is not.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)

# ============================================================ 17. SOURCES
sl, y = content("Values are uploaded, or PULLED — never read through",
                "6 · Retrieval")
tf = txt(sl, ML, y, CW, 0.85)
runs(tf, [("A feature view can name a SQL query, a file, S3 or GCS. ",
           INK, False),
          ("MAYA then COPIES from it into its own versioned store — it does "
           "not serve off it.", CRIMSON, True)],
     size=13.5, first=True, space_after=0, line=1.28)
half = (CW - 0.34) / 2
card(sl, ML, y + 1.00, half, 2.35, "IF MAYA READ THROUGH",
     "The pin would be a fiction",
     "The warehouse is somebody else's, and it has the property that matters "
     "here: it is MUTABLE. Once August's restatement lands, May's row is gone, "
     "and no read-time rule recovers what the June decision saw.\n\n"
     "The query would not fail. It would return the restated number and say "
     "nothing.")
card(sl, ML + half + 0.34, y + 1.00, half, 2.35, "SO MAYA PULLS",
     "and bitemporalises what it got",
     "SQL through SQLAlchemy; files, S3 and GCS through pyarrow. What arrives "
     "is written into MAYA's own store as an ordinary, immutable, pinnable "
     "version.\n\n"
     "It costs a copy. It is the only arrangement under which the point-in-time "
     "operator survives contact with somebody else's warehouse.")
tf = txt(sl, ML, y + 3.60, CW, 0.7)
runs(tf, [("A read-only statement check happens at DECLARATION, ", CRIMSON,
           True),
          ("not at first use — so a source that could write is refused before "
           "anybody has pointed it at production.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 18. GOVERNANCE
sl, y = content("What the platform refuses, and why each one exists",
                "6 · Retrieval")
h = table(sl, [
    ["Refused", "The reason, in the platform's own words"],
    ["A feature row missing either clock",
     "refused at the upload rather than two layers later during assembly, where "
     "it stops being fixable"],
    ["A featureset that does not cover the kernel's inputs (L-W10)",
     "adding a regressor is a MODEL change, not a data change"],
    ["A fitting read bounded in only one clock (L-W9)",
     "a featureset read for fitting must bound the period it covers"],
    ["Retiring a view version something pins",
     "the retirement guard names WHO is pinning it — retirement is a consumer "
     "question, not a housekeeping one"],
    ["A derived feature that reads the label",
     "refused with the derivation chain named, rather than with a bare no"],
    ["A composition operation that changes nothing",
     "an operation that silently did nothing is one somebody believes happened"],
], ML, y, CW, col_w=[4.6, 7.2], row_h=0.32, fs=11, hfs=11)
tf = txt(sl, ML, y + h + 0.26, CW, 0.7)
runs(tf, [("Each refusal names what failed AND what to do instead. ",
           CRIMSON, True),
          ("A refusal that says only “forbidden” teaches people to route around "
           "the platform, which is worse than not having refused.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ 19. NOT BUILT
sl, y = content("What this feature platform is not", "6 · Retrieval")
tf = txt(sl, ML, y, CW, 0.6)
runs(tf, [("Named, because a platform slide that lists only capabilities is a "
           "brochure.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.26)
bullets(txt(sl, ML, y + 0.72, CW, 3.6), [
    "NOT an online feature store. Reading at request latency is deliberately "
    "the engine's problem — MAYA will not sit on the serving path, because a "
    "governance control with an availability requirement is one that gets "
    "bypassed on the day it matters.",
    "NOT a compute engine. There is no Spark here: the point-in-time join is a "
    "Python loop over the rows of a pinned version. That is the same operator "
    "at a smaller scale, and it is where a cluster engine would go.",
    "NOT a transformation framework. The expression language is arithmetic, "
    "comparison and nine functions — deliberately not enough to be a "
    "programming language. Anything beyond it is materialised elsewhere and "
    "loaded, with its provenance recorded.",
    "NOT incremental at scale. Monitoring materialises a table into a "
    "single-process frame; the scale half of that requirement does not hold, "
    "and the documentation says so rather than implying otherwise.",
    "Serving skew is detected by ATTESTATION, not observation: the engine says "
    "which namespaces and pins it read, and MAYA compares. That is a smaller "
    "claim than seeing for itself, and it is the honest one.",
], size=11.5, gap=10)

# ============================================================ 20. CLOSE
_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
tf = txt(sl, ML + 0.4, 1.15, CW * 0.84, 1.7)
para(tf, "A stable name over moving contents", size=31, color=WHITE,
     font=SERIF, italic=True, first=True, space_after=6, line=1.22)
para(tf, "is the failure this exists to prevent.", size=31,
     color=RGBColor(0xF4, 0xDF, 0xE3), font=SERIF, italic=True, space_after=0,
     line=1.22)
rect(sl, ML + 0.4, 3.35, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.4, 3.70, CW * 0.52, 2.4)
para(tf, "THE FOUR IDEAS", size=10, color=RGBColor(0xE0, 0xA8, 0xB2),
     bold=True, first=True, space_after=10)
for line in ["Two clocks on every row, refused without both",
             "min(label_ts, as_of) — one operator, stated once",
             "A binding pins a feature, a view AND its version",
             "Compose rather than restate; every operation total"]:
    para(tf, line, size=13, color=WHITE, space_after=8, line=1.22)
tf = txt(sl, ML + CW * 0.58, 3.70, CW * 0.42, 2.4)
para(tf, "WHERE THE DETAIL IS", size=10, color=RGBColor(0xE0, 0xA8, 0xB2),
     bold=True, first=True, space_after=10)
for line in ["docs/07 — the feature platform, in full",
             "docs/15, 16, 17 — featuresets, composition, the algebra",
             "case_studies/05 — reuse, composition and a typed edge"]:
    para(tf, line, size=12, color=RGBColor(0xF6, 0xE6, 0xE9), space_after=8,
         line=1.22)
footer(sl)
