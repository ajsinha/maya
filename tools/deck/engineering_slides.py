"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
# -*- coding: utf-8 -*-
"""MAYA — Model and Feature Engineering deck.

The practitioner's deck: how a feature is defined, how a featureset is composed,
how a warrant carries both to an execution engine, and what comes back. Same
Harvard-Crimson theme as the other two (see theme.py).
"""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.py")).read())

MONO = "Consolas"


def code(sl, x, y, w, lines, fs=9.5, title=None):
    """Monospace block sized from its own content."""
    LINE = 1.34
    lh = fs * LINE * 1.26 / 72.0
    head = 0.32 if title else 0.0
    h = head + len(lines) * lh + 0.30
    rect(sl, x, y, w, h, fill=RGBColor(0xF4, 0xF2, 0xEF))
    rect(sl, x, y, 0.045, h, fill=SLATE)
    if title:
        tf = txt(sl, x + 0.22, y + 0.10, w - 0.4, 0.24)
        para(tf, title, size=9, color=CRIMSON, bold=True, first=True, space_after=0)
    tf = txt(sl, x + 0.22, y + head + 0.11, w - 0.4, h - head - 0.2)
    for i, ln in enumerate(lines):
        col = MUTED if ln.strip().startswith("#") else INK
        para(tf, ln if ln else " ", size=fs, color=col, font=MONO,
             first=(i == 0), space_after=0, line=1.34)
    return h


def steps(sl, x, y, w, items, h=1.45):
    """A numbered row of stages. The deck's way of saying 'in this order'."""
    n = len(items)
    gap = 0.20
    bw = (w - gap * (n - 1)) / n
    for i, (num, title, body) in enumerate(items):
        xx = x + i * (bw + gap)
        rect(sl, xx, y, bw, h, fill=WHITE, line=RULE)
        rect(sl, xx, y, bw, 0.05, fill=CRIMSON)
        tf = txt(sl, xx + 0.16, y + 0.16, bw - 0.32, h - 0.3)
        para(tf, num, size=14, color=CRIMSON, bold=True, font=SERIF,
             first=True, space_after=2)
        para(tf, title, size=11, color=INK, bold=True, space_after=4)
        para(tf, body, size=8.5, color=SLATE, line=1.15)


def node(sl, x, y, w, h, title, body, fill=WHITE, accent=CRIMSON,
         title_size=10.5, body_size=8.2):
    """One box in a process diagram: a name, and what it actually is."""
    rect(sl, x, y, w, h, fill=fill, line=RULE)
    rect(sl, x, y, w, 0.05, fill=accent)
    tf = txt(sl, x + 0.12, y + 0.14, w - 0.24, h - 0.26)
    para(tf, title, size=title_size, color=INK, bold=True, font=SERIF,
         first=True, space_after=3)
    para(tf, body, size=body_size, color=SLATE, line=1.14, space_after=0)


def note(sl, x, y, w, h, lead, rest, tail=""):
    """A parchment block with a crimson lead-in — the deck's aside."""
    rect(sl, x, y, w, h, fill=PARCH)
    rect(sl, x, y, 0.045, h, fill=CRIMSON)
    tf = txt(sl, x + 0.26, y + 0.13, w - 0.5, h - 0.24)
    parts = [(lead, CRIMSON, True), (rest, INK, False)]
    if tail:
        parts.append((tail, INK, True))
    runs(tf, parts, size=10.5, first=True, space_after=0, line=1.24)


# ============================================================ TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.35, fill=CRIMSON)
rect(sl, 0, 4.35, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.35, fill=CRIMSON_D)
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                    "assets", "logo", "maya-mark-white.png")
if os.path.exists(LOGO):
    sl.shapes.add_picture(LOGO, In(ML + 0.30), In(0.70), In(0.80), In(0.80))
tf = txt(sl, ML + 1.24, 0.99, CW - 1.04, 0.34)
para(tf, "MAYA  ·  MODEL & AI LIFECYCLE ASSURANCE PLATFORM",
     size=11, color=RGBColor(0xE8, 0xB8, 0xC0), bold=True, first=True, space_after=0)
tf = txt(sl, ML + 0.3, 1.62, CW * 0.88, 2.0)
para(tf, "Model and Feature Engineering", size=42, color=WHITE, font=SERIF,
     first=True, space_after=4)
rect(sl, ML + 0.3, 3.28, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.3, 3.54, CW * 0.84, 0.8)
para(tf, "How a feature is defined, how a featureset is composed, how a warrant "
         "carries both to an execution engine — and what has to come back",
     size=14, color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, first=True,
     space_after=0, line=1.25)
tf = txt(sl, ML + 0.3, 4.90, CW * 0.55, 1.0)
para(tf, "Ashutosh Sinha", size=20, color=INK, bold=True, font=SERIF,
     first=True, space_after=3)
para(tf, "Independent Researcher", size=12, color=CRIMSON, space_after=1)
para(tf, "September 2026   ·   the practitioner's deck", size=10.5, color=MUTED)
x0 = ML + CW * 0.55
tf = txt(sl, x0, 4.82, CW * 0.45, 1.90)
para(tf, "CHAPTERS", size=9.5, color=CRIMSON, bold=True, first=True, space_after=6)
for i, c in enumerate(["The shape of the whole thing",
                       "Engineering a feature",
                       "Composing a featureset",
                       "Warrants, and what comes back",
                       "What MAYA refuses, and why"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=10.5,
         space_after=3)
footer(sl)


# ============================================================ CH 1
divider("1", "The Shape of the Whole Thing",
        "Features, featuresets, warrants and parameters — and how they meet.",
        ["The process end to end", "What each object is for",
         "Where the pins are", "The two clocks"])

# ---------------------------------------------------------- the big diagram
sl, y = content("Model, feature and warrant management",
                "The shape of the whole thing")

BW, BH = 2.28, 0.86          # box width, height
GAP = 0.32
ROW1 = y + 0.10
ROW2 = ROW1 + 1.28
ROW3 = ROW2 + 1.28
ROW4 = ROW3 + 1.28

# --- row 1: the catalogue -------------------------------------------------
node(sl, ML, ROW1, BW, BH, "Feature",
     "a meaning, not a column: entity, shape, owner", accent=CRIMSON)
node(sl, ML + (BW + GAP), ROW1, BW, BH, "Derived feature",
     "Z = f(X, Y), declared and versioned", accent=CRIMSON)
node(sl, ML + 2 * (BW + GAP), ROW1, BW, BH, "Feature view version",
     "where values live: a Delta namespace that never moves", accent=SLATE)
node(sl, ML + 3 * (BW + GAP), ROW1, BW, BH, "Telemetry",
     "scores and outcomes, on two clocks", accent=SLATE)

# --- row 2: the selection -------------------------------------------------
node(sl, ML, ROW2, BW, BH, "Featureset",
     "a declared SCHEMA of named slots", accent=CRIMSON)
node(sl, ML + (BW + GAP), ROW2, BW, BH, "Featureset version",
     "fills each slot: feature + view version + Delta version",
     fill=PARCH, accent=CRIMSON)
node(sl, ML + 2 * (BW + GAP), ROW2, BW, BH, "Dataset snapshot",
     "assembled point-in-time, digested, PIT-verified", accent=SLATE)
node(sl, ML + 3 * (BW + GAP), ROW2, BW, BH, "Monitor",
     "evaluated from telemetry the platform holds", accent=SLATE)

# --- row 3: the model -----------------------------------------------------
node(sl, ML, ROW3, BW, BH, "Model",
     "the register entry: owner, purpose, tier", accent=CRIMSON)
node(sl, ML + (BW + GAP), ROW3, BW, BH, "Model version",
     "the kernel  f : P × X → D(Y), immutable", fill=PARCH,
     accent=CRIMSON)
node(sl, ML + 2 * (BW + GAP), ROW3, BW, BH, "Warrant",
     "signed, expiring, entitlement-bound: what may be run", fill=PARCH,
     accent=CRIMSON)
node(sl, ML + 3 * (BW + GAP), ROW3, BW, BH, "Execution engine",
     "outside MAYA. reads the warrant, runs nothing else", accent=SLATE)

# --- row 4: what comes back ----------------------------------------------
node(sl, ML, ROW4, BW, BH, "Parameter set",
     "an inhabitant of P. a fit makes one, not a version", accent=CRIMSON)
node(sl, ML + (BW + GAP), ROW4, BW, BH, "Approval",
     "a quorum whose depth follows the tier", accent=SLATE)
node(sl, ML + 2 * (BW + GAP), ROW4, BW, BH, "Evidence chain",
     "append-only, hash-linked: every act above", accent=GOLD)
node(sl, ML + 3 * (BW + GAP), ROW4, BW, BH, "Compiled document",
     "generated from the register, citations that resolve", accent=SLATE)

# --- the arrows that matter ----------------------------------------------
COL = [ML + i * (BW + GAP) for i in range(4)]
MID = [c + BW / 2 for c in COL]
# catalogue -> view -> featureset version
connect(sl, COL[0] + BW, ROW1 + BH / 2, COL[1], ROW1 + BH / 2, CRIMSON)
connect(sl, COL[1] + BW, ROW1 + BH / 2, COL[2], ROW1 + BH / 2, CRIMSON)
connect(sl, MID[2], ROW1 + BH, MID[1] + 0.5, ROW2, CRIMSON)
# schema -> version
connect(sl, COL[0] + BW, ROW2 + BH / 2, COL[1], ROW2 + BH / 2, CRIMSON)
# featureset version -> snapshot
connect(sl, COL[1] + BW, ROW2 + BH / 2, COL[2], ROW2 + BH / 2, SLATE)
# model -> version -> warrant -> engine
connect(sl, COL[0] + BW, ROW3 + BH / 2, COL[1], ROW3 + BH / 2, CRIMSON)
connect(sl, COL[1] + BW, ROW3 + BH / 2, COL[2], ROW3 + BH / 2, CRIMSON)
connect(sl, COL[2] + BW, ROW3 + BH / 2, COL[3], ROW3 + BH / 2, CRIMSON)
# featureset version -> warrant  (the join that makes a fit meaningful)
connect(sl, MID[1], ROW2 + BH, MID[2] - 0.4, ROW3, CRIMSON)
# engine -> parameter set  (what comes back)
connect(sl, MID[3], ROW3 + BH, MID[0] + 1.0, ROW4, CRIMSON)
# parameter set -> approval -> back up to warrant
connect(sl, COL[0] + BW, ROW4 + BH / 2, COL[1], ROW4 + BH / 2, SLATE)
connect(sl, MID[1] + 0.4, ROW4, MID[2], ROW3 + BH, SLATE)
# telemetry -> monitor
connect(sl, MID[3], ROW1 + BH, MID[3], ROW2, SLATE)

tf = txt(sl, ML, ROW4 + BH + 0.10, CW, 0.34)
runs(tf, [("Read the middle column downwards. ", CRIMSON, True),
          ("A featureset version and a model version meet in a warrant; the "
           "engine returns a parameter set; the parameter set is approved and "
           "the next warrant names it. Everything on the way leaves a node in "
           "the evidence chain.", SLATE, False)],
     size=10, first=True, space_after=0, line=1.2)
footer(sl)


# ------------------------------------------------------- what each object is for
sl, y = content("What each object is for", "The shape of the whole thing")
data = [["Object", "Answers", "Pinned by"],
        ["Feature", "what this signal MEANS — entity, shape, owner, definition",
         "nothing; it is a declaration"],
        ["Feature view version", "where the values ARE, at a Delta version that "
         "does not move", "a featureset version"],
        ["Featureset", "what X IS: a schema of named slots a kernel is defined "
         "over", "a model version's contract"],
        ["Featureset version", "which features fill that schema, and from which "
         "exact bytes", "a warrant, a snapshot"],
        ["Model version", "the kernel f : P × X → D(Y) — immutable once approved",
         "a warrant, an alias"],
        ["Warrant", "what may be run, by whom, until when, on what data",
         "signed; nothing pins it"],
        ["Parameter set", "an inhabitant of P: the numbers a fit produced",
         "a scoring warrant"]]
h = table(sl, data, ML, y, CW, col_w=[2.0, 5.7, 3.9], row_h=0.30, fs=10, hfs=10,
          bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + h + 0.24, CW, 0.86,
     "Read the third column. ",
     "Every object above is pinned by something further down, and a pin is "
     "always to a version rather than to a name. That is the single structural "
     "decision this platform makes over and over, and it is why ",
     "the same identifier resolves to the same bytes a year later.")
footer(sl)

# ------------------------------------------------------------- the two clocks
sl, y = content("Two clocks, never one", "The shape of the whole thing")
h = code(sl, ML, y, CW * 0.56, [
 "event_ts    when the fact was TRUE in the world",
 "ingest_ts   when the platform LEARNED it",
 "",
 "point-in-time rule:",
 "    event_ts  <= label_ts",
 "    ingest_ts <= as_of",
], fs=10)
tf = txt(sl, ML, y + h + 0.26, CW * 0.56, 2.2)
para(tf, "\u201cWhat did we know, and when did we know it\u201d is a different "
         "question from \u201cwhat was true\u201d, and a training set built "
         "without both answers only the second.",
     size=11.5, color=INK, first=True, space_after=8, line=1.26)
para(tf, "A row missing either clock is refused at the upload rather than two "
         "layers later during assembly \u2014 which is where it stops being "
         "fixable.",
     size=11, color=SLATE, space_after=0, line=1.24)

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 0.35)
para(tf, "Where the clocks decide the answer", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=0)
data = [["", ""],
        ["Assembly", "the latest fact true by the label date AND known by as_of"],
        ["Normalisation", "statistics fitted only from what was knowable then"],
        ["Derived features", "ingest_ts(Z) = max over the inputs"],
        ["Alignment", "a back-filled value carries the clock it became knowable at"],
        ["Telemetry", "a review of last quarter sees last quarter's population"]]
table(sl, data, x, y + 0.42, CW * 0.40, col_w=[1.35, 3.55], header=False,
      row_h=0.30, fs=9.5, bold_col0=True, first_col_color=CRIMSON)
footer(sl)


# ============================================================ CH 2
divider("2", "Engineering a Feature",
        "A meaning, a shape, a lineage, and an owner who answers for it.",
        ["Not always a number", "Derived features", "The leakage rules",
         "Sealing and ownership"])

# ------------------------------------------------------------ dimensionality
sl, y = content("A feature is not always a number", "Engineering a feature")
h = code(sl, ML, y, CW * 0.52, [
 '{"name": "usd_curve", "entity": "book_id",',
 ' "dtype": "numeric",',
 ' "shape": [10],',
 ' "components": ["1m","3m","6m","1y","2y",',
 '                "3y","5y","7y","10y","30y"]}',
], fs=9.5)
data = [["Shape", "Kind", "Example"],
        ["[]", "scalar", "debt service coverage"],
        ["[10]", "vector", "a curve at ten tenors"],
        ["[10, 10]", "matrix", "the correlation between them"],
        ["[5, 10, 10]", "tensor", "that matrix under five scenarios"]]
table(sl, data, ML, y + h + 0.28, CW * 0.52, col_w=[1.3, 1.2, 4.4],
      row_h=0.30, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)

x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 3.4)
para(tf, "The component order IS the axis order", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=8)
para(tf, "A curve whose tenors came back alphabetically would be a different "
         "curve \u2014 and one nobody would notice was wrong. Resolution "
         "preserves insertion order and never sorts.",
     size=11, color=INK, space_after=10, line=1.25)
para(tf, "The names are what make composition mean something. \u201cDrop the "
         "50-year point\u201d is an operation on a name; on an anonymous array "
         "it is an operation on an index, and an index is not a meaning.",
     size=11, color=SLATE, space_after=10, line=1.25)
para(tf, "A declared shape is checked against the values that arrive. A shape "
         "nobody verifies is a comment, and a model given ten tenors where it "
         "expected eleven produces an answer rather than an error.",
     size=11, color=SLATE, space_after=0, line=1.25)
footer(sl)

# ---------------------------------------------------------- derived features
sl, y = content("Derived features, and the four rules", "Engineering a feature")
h = code(sl, ML, y, CW * 0.50, [
 "lot_to_living_ratio = lot_size_sqft / living_area_sqft",
 "property_age        = year(event_ts) - year_built",
 "log_living_area     = log(living_area_sqft)",
 "",
 "# arithmetic, comparison, nine total functions,",
 "# the row's own clock. whitelisted at the AST,",
 "# so what cannot be expressed cannot be smuggled in.",
], fs=9)
note(sl, ML, y + h + 0.26, CW * 0.50, 1.14,
     "MAYA transforms features it holds; ",
     "it does not run models. Computing x / y over a stored column is the same "
     "class of act as the null rate it already reports for every "
     "materialisation. ",
     "Running a kernel is not.")

x = ML + CW * 0.54
tf = txt(sl, x, y, CW * 0.46, 0.32)
para(tf, "Four rules, each because the alternative fails quietly", size=12,
     color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
data = [["Rule", "What it prevents"],
        ["Lineage is the transitive closure",
         "a primitive retired under something deriving from it"],
        ["ingest_ts(Z) = max(inputs)",
         "the easiest way to leak the future: a value appearing knowable "
         "before its inputs were"],
        ["No slot may derive from the label",
         "leakage with a division sign in front of it"],
        ["Certification is the meet",
         "deriving from an uncertified feature to launder it"]]
table(sl, data, x, y + 0.40, CW * 0.46, col_w=[2.3, 3.1], row_h=0.30, fs=9,
      hfs=9, bold_col0=True, first_col_color=CRIMSON)
footer(sl)

# ------------------------------------------------------------------ leakage
sl, y = content("The one that gets refused", "Engineering a feature")
h = code(sl, ML, y, CW * 0.54, [
 "feature: price_per_sqft",
 "inputs:  [sale_price, living_area_sqft]",
 "         # sale_price is the featureset's LABEL",
 "",
 "409  'price_per_sqft' is computed from 'sale_price',",
 "     which this featureset declares as its label \u2014 a",
 "     feature derived from the label leaks the answer",
 "     into the training set.",
], fs=9)
tf = txt(sl, ML, y + h + 0.28, CW * 0.54, 1.5)
para(tf, "The check walks the WHOLE lineage, not the immediate inputs: a "
         "derivation of a derivation of the label is still the label.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "And it runs before the view is resolved, so the message is "
         "\u201cyou cannot train on the answer\u201d rather than "
         "\u201cno view supplies that\u201d.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 3.6)
para(tf, "Why this one matters more than it looks", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=8)
para(tf, "A model trained on a feature derived from its own label performs "
         "extraordinarily in validation and fails on the first case it has not "
         "already seen.",
     size=11, color=INK, space_after=10, line=1.25)
para(tf, "It is not caught by any metric, because every metric agrees the model "
         "is excellent. It is caught by knowing what the column was made from "
         "\u2014 which is why the lineage is recorded rather than inferred.",
     size=11, color=SLATE, space_after=10, line=1.25)
para(tf, "The same argument produces the ingest-clock rule, the point-in-time "
         "assembly rule, and the refusal to normalise without an as_of. They "
         "are one idea applied four times.",
     size=11, color=SLATE, space_after=0, line=1.25)
footer(sl)

# --------------------------------------------------- sealing and ownership
sl, y = content("Sealed, ephemeral, owned", "Engineering a feature")
card(sl, ML, y, CW * 0.315, 2.5, "1", "Sealed",
     "Final: no amendment, no further versions, no change of owner \u2014 and "
     "still composable. That combination is the point. A parent that cannot "
     "move is a parent worth building on, and evolution moves to a child where "
     "it stays visible.")
card(sl, ML + CW * 0.343, y, CW * 0.315, 2.5, "2", "Ephemeral",
     "A time to live, then destroyed. Cannot be sealed \u2014 permanent and "
     "temporary are not two flags that happen to be set. Cannot be composed "
     "from: a child that resolves today and dangles tomorrow. Its rows go; its "
     "evidence stays.")
card(sl, ML + CW * 0.686, y, CW * 0.314, 2.5, "3", "Owned",
     "Two facts kept apart. The CREATOR is history and never moves. The OWNER "
     "is a responsibility, transferred by name with the handover witnessed. An "
     "owner field that quietly becomes a leaver's username is how a model ends "
     "up accountable to nobody.")
note(sl, ML, y + 2.72, CW, 0.92,
     "Sealing is its own permission. ",
     "Whoever may define a thing is not automatically who may end it, so it "
     "sits with the second line. Breaking a seal is administrators-only and "
     "needs a reason \u2014 ",
     "a seal anybody could lift would not be a seal.")
footer(sl)


# ============================================================ CH 3
divider("3", "Composing a Featureset",
        "A schema, versions that fill it, and one fold that does both.",
        ["Schema and constituents", "The composition monoid",
         "Rolling forward", "Retrieval policy"])

# ----------------------------------------------------- schema vs constituents
sl, y = content("A featureset declares a schema; a version fills it",
                "Composing a featureset")
h = code(sl, ML, y, CW * 0.56, [
 "featureset: inflation",
 "schema:  gb_index: numeric",
 "         us_index: numeric",
 "         daily_index: numeric",
 "",
 "@v1   gb_index\u2192UKRPI  us_index\u2192USCPI  daily\u2192DAILY_INFL",
 "@v2   gb_index\u2192UKRPI  us_index\u2192USCPI  daily\u2192EUHICP",
], fs=9.5)
tf = txt(sl, ML, y + h + 0.28, CW * 0.56, 1.8)
para(tf, "@v2 draws on a different feature entirely, and a model defined over "
         "inflation does not change: it reads daily_index, and always did.",
     size=11.5, color=INK, first=True, space_after=9, line=1.25)
para(tf, "A version that CANNOT fill the schema is refused. It is not a version "
         "of this featureset \u2014 it is a different one, or it is a model "
         "change, and the register decides which so nobody has to remember.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 0.32)
para(tf, "Every binding pins exactly", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["", ""],
        ["feature", "which signal fills the slot"],
        ["view", "which view supplies its values"],
        ["view_version", "which version of that view"],
        ["delta_version", "which write to that path"],
        ["namespace", "the resolved Delta location"]]
table(sl, data, x, y + 0.40, CW * 0.40, col_w=[1.5, 3.4], header=False,
      row_h=0.29, fs=9.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + 2.32, CW * 0.40, 1.30,
     "A path is mutable. ",
     "A set that named views without pinning them would resolve to different "
     "bytes next month with its digest unchanged \u2014 which is adversarial "
     "finding C-2, ",
     "one level out from the view.")
footer(sl)

# ------------------------------------------------------------ the monoid
sl, y = content("Composition: one fold, two objects", "Composing a featureset")
h = code(sl, ML, y, CW * 0.54, [
 "compose([a, b, c])  =  merge(merge(a, b), c)",
 "                       then the object's OWN operations",
 "",
 "merge is associative;  {} is its identity",
 "  \u21d2 composition is a MONOID",
 "  \u21d2 'a combination of features is a feature'",
 "     is a statement, not an aspiration",
], fs=9.5)
tf = txt(sl, ML, y + h + 0.26, CW * 0.54, 1.5)
para(tf, "Left to right, the rightmost wins, and an object\u2019s own "
         "operations are applied last \u2014 because if a parent could "
         "override a child, naming a parent would be an act of surrender.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "Inheriting from one parent and combining several are the same "
         "operation at different arities, so there is one mechanism and "
         "inheritance is the one-parent case.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 0.32)
para(tf, "Every operation is total", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["Refused", "Because"],
        ["drop of something absent",
         "a drop that quietly does nothing leaves a child differing from what "
         "its author wrote"],
        ["add of something present",
         "say override \u2014 the two read differently to a reviewer and should"],
        ["override of something absent", "say add"],
        ["a cycle", "there is no fixed point to resolve to"],
        ["an ephemeral parent", "it resolves today and dangles tomorrow"]]
table(sl, data, x, y + 0.40, CW * 0.42, col_w=[2.0, 3.5], row_h=0.29, fs=9,
      hfs=9, bold_col0=True, first_col_color=CRIMSON)
footer(sl)

# ------------------------------------------------------------- retrieval
sl, y = content("What MAYA does to values on the way out",
                "Composing a featureset")
steps(sl, ML, y, CW, [
    ("1", "Align", "onto a chosen axis, filling gaps by a stated rule"),
    ("2", "Fit", "statistics from what was knowable at the as_of \u2014 on "
                 "OBSERVED values, before anything is filled"),
    ("3", "Fill", "the gaps, reporting how much of each column was invented"),
    ("4", "Normalise", "everything, including what was filled, and return the "
                       "statistics with the data"),
], h=1.42)
tf = txt(sl, ML, y + 1.62, CW * 0.52, 1.6)
para(tf, "The order is the point.", size=12, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=6)
para(tf, "Fitting the normalisation AFTER filling would shrink the spread by "
         "exactly the amount that was invented, because every filled cell sits "
         "at the centre and pulls the variance down.",
     size=11, color=INK, space_after=0, line=1.25)
x = ML + CW * 0.56
tf = txt(sl, x, y + 1.62, CW * 0.44, 1.6)
para(tf, "And the as_of is not optional.", size=12, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=6)
para(tf, "A z-score fitted over the whole column encodes what the mean turned "
         "out to be, including the part that had not happened when the row was "
         "scored. The leaky answer is the one somebody would get by accident, "
         "so it is the one that must not be the default.",
     size=11, color=INK, space_after=0, line=1.25)
note(sl, ML, y + 3.42, CW, 0.92,
     "Attached as default behaviour, overridden by the request. ",
     "Parents, then the object, then the caller \u2014 the same left-to-right "
     "fold, merged column by column, so a parent that fills three columns and a "
     "child that normalises one ",
     "end up doing both.")
footer(sl)

# --------------------------------------------------------------- alignment
sl, y = content("Aligning onto an axis, and the leakage that cannot hide",
                "Composing a featureset")
data = [["Rule", "Fills from", "Safe for training"],
        ["flat_forward", "the last observation", "yes"],
        ["flat_backward", "the next observation", "no"],
        ["linear", "both neighbours", "no"],
        ["nearest", "whichever is closer", "no"]]
h = table(sl, data, ML, y, CW * 0.50, col_w=[1.6, 2.9, 2.2], row_h=0.30,
          fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + h + 0.26, CW * 0.50, 1.8)
para(tf, "The last three reach into the future. They are right for drawing a "
         "curve or for an explicitly retrospective backtest, and wrong for "
         "training.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "They are not refused. They are stamped honestly.",
     size=11.5, color=CRIMSON, bold=True, space_after=0, line=1.25)

x = ML + CW * 0.54
h2 = code(sl, x, y, CW * 0.46, [
 "grid  t=0   100.0   ingest_ts 0.0",
 "grid  t=1   400.0   ingest_ts 3.0   \u2190 filled from t=3",
 "grid  t=2   400.0   ingest_ts 3.0",
 "grid  t=3   400.0   ingest_ts 3.0",
 "",
 "# a point-in-time read at as_of = 1",
 "# excludes rows 2 and 3 by the ORDINARY rule",
], fs=9)
tf = txt(sl, x, y + h2 + 0.26, CW * 0.46, 1.6)
para(tf, "A value derived from a later observation inherits that "
         "observation\u2019s ingest clock, because that is genuinely when it "
         "became knowable.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "The leakage is not caught by a check. It is made arithmetically "
         "impossible to hide, by the bitemporal machinery already here.",
     size=11, color=SLATE, space_after=0, line=1.25)
footer(sl)


# ============================================================ CH 4
divider("4", "Warrants, and What Comes Back",
        "A featureset version and a model version meet; a parameter set returns.",
        ["The fit warrant", "The parameter object", "The scoring warrant",
         "Three routes to P"])

# ---------------------------------------------------------- the fit warrant
sl, y = content("The fit warrant", "Warrants, and what comes back")
h = code(sl, ML, y, CW * 0.54, [
 '"operation":  {"verb": "fit"},',
 '"parameters": {"kind": "estimated_coefficients",',
 '               "source": {"binding": "to_be_fitted"}},',
 '"data": {',
 '  "inputs":  [{"binding":   "featureset",',
 '               "featureset": "nj_home_core", "version": 1,',
 '               "window": {"from": "2019-01-01",',
 '                          "to":   "2024-12-31"},',
 '               "as_of":  "2025-01-15"}],',
 '  "outputs": [{"sink": "parameter_object"}]}',
], fs=9)
note(sl, ML, y + h + 0.24, CW * 0.54, 1.00,
     "The set fixes the columns; the warrant fixes the period. ",
     "That is why window and as_of are here and not in the featureset \u2014 ",
     "one set trains 2019\u201323 and 2020\u201324 without becoming two sets.")

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 0.32)
para(tf, "Five checks before it is signed", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["Law", "Asks"],
        ["L-W1", "is 'fit' meaningful for this class? T0 has nothing to fit, and "
                 "the refusal says so"],
        ["L-W10", "does the featureset provide what the kernel declares it reads?"],
        ["L-W3", "is the binding one that can answer 'what was known at t'?"],
        ["L-W9", "is the read bounded in BOTH clocks?"],
        ["L-W4", "does it say where the parameters go?"]]
table(sl, data, x, y + 0.40, CW * 0.42, col_w=[0.95, 4.55], row_h=0.29, fs=9,
      hfs=9, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 2.42, CW * 0.42, 1.1)
para(tf, "MAYA does not fit anything. It signs this and waits.",
     size=11.5, color=INK, bold=True, first=True, space_after=6, line=1.24)
para(tf, "The estimation happens in an execution engine \u2014 the same "
         "boundary drawn everywhere else here.",
     size=10.5, color=SLATE, space_after=0, line=1.24)
footer(sl)

# ------------------------------------------------------- the parameter object
sl, y = content("A fit produces a parameter set, not a model version",
                "Warrants, and what comes back")
h = code(sl, ML, y, CW * 0.52, [
 "f : P \u2297 X \u2192 D(Y)     the kernel",
 "fit                 picks a point in P",
 "",
 "\u21d2 the kernel did not change.",
 "\u21d2 minting a model version per retrain would make",
 "  'the model changed' mean two different things.",
], fs=9.5)
tf = txt(sl, ML, y + h + 0.26, CW * 0.52, 1.9)
para(tf, "But a parameter set does change behaviour \u2014 so it is immutable, "
         "versioned, and an alias cannot point at it until somebody other than "
         "whoever recorded it has approved.",
     size=11, color=INK, first=True, space_after=9, line=1.25)
para(tf, "Accepted ONLY against a warrant MAYA issued, and only when it names "
         "the featureset version that produced it. Without that, \u201cwhich "
         "data produced these numbers\u201d has no answer.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 0.32)
para(tf, "Three routes to P, governed to three depths", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=0)
data = [["Route", "Evidence", "Governed"],
        ["fitted", "a warrant MAYA issued", "each set"],
        ["calibrated", "market data, often daily", "the procedure"],
        ["declared", "a person\u2019s assertion", "attestation"]]
table(sl, data, x, y + 0.40, CW * 0.44, col_w=[1.4, 2.5, 1.6], row_h=0.30,
      fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 1.90, CW * 0.44, 2.0)
para(tf, "The middle row is why provenance is not cosmetic: a Hull\u2013White "
         "model recalibrated every morning would drown the register if each day "
         "needed a committee.",
     size=10.5, color=SLATE, first=True, space_after=9, line=1.24)
para(tf, "The bottom row is the model that never trains. A closed form arrives "
         "with its parameters and its kernel is ready from the first day \u2014 "
         "and L-W1 refuses it a fit warrant, so nobody has to remember which "
         "models train.",
     size=10.5, color=SLATE, space_after=0, line=1.24)
footer(sl)

# ------------------------------------------------------- the scoring warrant
sl, y = content("The run warrant, and why it is determined",
                "Warrants, and what comes back")
h = code(sl, ML, y, CW * 0.56, [
 '"operation":  {"verb": "score", "deterministic": true},',
 '"parameters": {"kind":   "estimated_coefficients",',
 '               "source": {"binding": "parameter_set",',
 '                          "parameter_set": "01a06d51f9c3",',
 '                          "digest": "sha256:c4e7\u2026"}},',
 '"data": {"inputs":  [{"binding": "request"}],',
 '         "outputs": [{"sink": "response"}]}',
], fs=9)
tf = txt(sl, ML, y + h + 0.28, CW * 0.56, 1.7)
para(tf, "Model version AND parameter set, both pinned. The run is determined: "
         "same kernel, same point in P, same input, same answer.",
     size=11.5, color=INK, first=True, space_after=9, line=1.25)
para(tf, "L-W8 refuses each of to_be_fitted and parameter_set in the "
         "other\u2019s position. A fit that claims to read parameters has the "
         "direction backwards; a score that will not name its inhabitant "
         "produces a number attributable to nothing.",
     size=10.5, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.6)
para(tf, "What the appraiser gets", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=9)
para(tf, "A number whose provenance runs all the way back:",
     size=11, color=INK, space_after=8, line=1.24)
for step in ["the parameter set that produced it",
             "the featureset version it was fitted from",
             "the pinned Delta namespaces beneath that",
             "the rows that were true and known on a stated date"]:
    runs(tf, [("\u2192  ", CRIMSON, True), (step, SLATE, False)],
         size=10.5, space_after=5)
para(tf, "Not a claim about lineage. A chain of pins, each of which resolves.",
     size=11, color=INK, bold=True, space_before=8, space_after=0, line=1.24)
footer(sl)


# ============================================================ CH 5
divider("5", "What MAYA Refuses, and Why",
        "The refusals are the product. Everything else is bookkeeping.",
        ["The refusals that matter", "What it deliberately will not do",
         "Where the boundary is"])

# ------------------------------------------------------------ the refusals
sl, y = content("The refusals that matter", "What MAYA refuses, and why")
data = [["Refused", "Because"],
        ["a training set with either clock unbounded",
         "it cannot be shown point-in-time correct, so it cannot be shown not "
         "to have leaked"],
        ["a feature derived from the label",
         "leakage with a division sign in front of it; every metric will agree "
         "the model is excellent"],
        ["normalising without an as_of",
         "the leaky answer is the one somebody would get by accident, so it "
         "must not be the default"],
        ["a featureset that does not cover the kernel\u2019s inputs",
         "adding a regressor is a model change, not a data change"],
        ["a fit warrant for a T0 model",
         "its parameters come from theory; asking it to fit is a type error"],
        ["parameters with no warrant behind them",
         "\u2018which data produced these numbers\u2019 would have no answer"],
        ["a version approved before its model is assessed",
         "the tier decides how many signatures the approval needs"],
        ["an upload missing entity_id or either clock",
         "accepting it moves the failure two layers from where it was caused"]]
h = table(sl, data, ML, y, CW, col_w=[4.6, 7.0], row_h=0.30, fs=10, hfs=10,
          bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + h + 0.22, CW, 0.86,
     "Every refusal carries a remediation. ",
     "\u201cPolicy violation\u201d tells somebody nothing they can act on, so "
     "each of these names what to do instead \u2014 ",
     "a gate people cannot satisfy is a gate people route around.")
footer(sl)

# -------------------------------------------------------------- the boundary
sl, y = content("Where the boundary is", "What MAYA refuses, and why")
card(sl, ML, y, CW * 0.315, 2.6, "1", "It does not compute",
     "No fitting, no calibration, no scoring. MAYA issues a warrant and takes "
     "delivery of the result. The captive engine exists so a fresh deployment "
     "can demonstrate the whole governed path against real artifacts \u2014 not "
     "so anybody runs an estate on it.")
card(sl, ML + CW * 0.343, y, CW * 0.315, 2.6, "2", "It does not transform",
     "The expression language is small on purpose. Anything needing a library, "
     "a join or a model is declared external: the definition, the lineage and "
     "the leakage check are still kept, and the register says plainly that the "
     "platform did not compute the values.")
card(sl, ML + CW * 0.686, y, CW * 0.314, 2.6, "3", "It does not choose",
     "No feature selection, no importance ranking, no suggestion engine. It "
     "records what you chose, pins it so it cannot move underneath you, and "
     "refuses the combinations that are type errors.")
note(sl, ML, y + 2.82, CW, 0.94,
     "A platform that claimed to do all three ",
     "would be believed about the parts it does badly. Stating the boundary is "
     "what makes the rest of it worth relying on \u2014 ",
     "and every honest gap is written down in the implementation plan.")
footer(sl)

# ============================================================ CLOSING
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
rect(sl, ML + 0.4, 1.10, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.4, 1.40, CW * 0.80, 2.6)
para(tf, "One idea, applied everywhere", size=34, color=WHITE, font=SERIF,
     first=True, space_after=14)
para(tf, "A pin is to a version, never to a name. A clock records when something "
         "became knowable, not when it was written down. A refusal says what to "
         "do instead. And what the platform will not do is written down beside "
         "what it will.",
     size=15, color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, space_after=0,
     line=1.32)
tf = txt(sl, ML + 0.4, 4.30, CW * 0.74, 1.5)
para(tf, "Ashutosh Sinha", size=18, color=WHITE, bold=True, first=True,
     space_after=4)
para(tf, "Independent Researcher   \u00b7   ajsinha@gmail.com", size=12,
     color=RGBColor(0xF2, 0xD8, 0xDC), space_after=14)
para(tf, "Featuresets and parameters: docs/15-featuresets-and-parameters.md   "
         "\u00b7   Composition and retrieval: docs/16-features-composed-and-shaped.md   "
         "\u00b7   Feature platform: docs/07-feature-platform.md",
     size=10.5, color=RGBColor(0xE8, 0xC4, 0xCA), line=1.3)
para(tf, "\u00a9 2026 Ashutosh Sinha. All rights reserved. Proprietary and "
         "confidential \u2014 see LICENSE and NOTICE. Not legal, regulatory or "
         "financial advice.",
     size=8.5, color=RGBColor(0xD8, 0xA0, 0xAC), space_before=10, line=1.25)


import sys
prs.save(sys.argv[1] if len(sys.argv) > 1 else "MAYA-Model-and-Feature-Engineering.pptx")
print("slides:", len(prs.slides._sldIdLst))
