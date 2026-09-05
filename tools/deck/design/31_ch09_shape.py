# ============================================================ CH 9
divider("9", "The Shape of the Whole Thing",
        "Model, feature, featureset, warrant, parameters — and how they meet.",
        ["The five words",
         "The process end to end",
         "What each object is for",
         "Where the pins are"])

# ------------------------------------------------------------- the five words
sl, y = content("Five words, and how they hold together",
                "The shape of the whole thing")

# --- the equation is the organising device, so it goes first --------------
rect(sl, ML, y, CW, 1.26, fill=PARCH)
rect(sl, ML, y, 0.05, 1.26, fill=CRIMSON)
tf = txt(sl, ML, y + 0.14, CW, 0.62, align=PP_ALIGN.CENTER)
runs(tf, [("f", CRIMSON, True), (" :  ", INK, False),
          ("P", CRIMSON, True), ("  \u2297  ", INK, False),
          ("X", CRIMSON, True), ("  \u2192  ", INK, False),
          ("D(Y)", CRIMSON, True)],
     size=30, first=True, space_after=0)
EQ = [("f", "the KERNEL", "the shape of the computation"),
      ("P", "the PARAMETERS", "the numbers it runs with"),
      ("X", "the FEATURES", "what it reads"),
      ("D(Y)", "the OUTPUT", "a distribution, not a number")]
qw = (CW - 0.5) / 4
for i, (sym, name, gloss) in enumerate(EQ):
    xx = ML + 0.25 + i * qw
    tf = txt(sl, xx, y + 0.82, qw - 0.1, 0.40, align=PP_ALIGN.CENTER)
    runs(tf, [(f"{sym}  ", CRIMSON, True), (name, INK, True)],
         size=9.5, first=True, space_after=1)
    para(tf, gloss, size=8.2, color=SLATE, space_after=0, align=PP_ALIGN.CENTER)

# --- the five terms, each with the confusion it is usually mistaken for ---
CY = y + 1.50
CH = 2.56
cw = (CW - 4 * 0.16) / 5
TERMS = [
    ("Model", "The register entry: what this is for, who owns it, what tier it "
              "sits at.",
     "Not the code, and not the numbers. Those are its versions and its "
     "parameters."),
    ("Kernel", "One immutable version of the model \u2014 the morphism "
               "f : P \u2297 X \u2192 D(Y), pinned by digest.",
     "Not changed by training. Training picks a point in P; the shape stays."),
    ("Feature", "A meaning with an entity, a type, a shape and an owner. A "
                "featureset assembles them into X.",
     "Not a column. A column is where the values happen to sit today."),
    ("Parameters", "An inhabitant of P: the coefficients, weights or constants "
                   "the kernel runs with.",
     "Not a new model. A retrain gives a new parameter set, not a new version."),
    ("Warrant", "A signed, expiring document: this kernel, at that point in P, "
                "over that data, by whom, until when.",
     "Not an execution. MAYA issues it; an engine acts on it and MAYA never "
     "runs anything."),
]
for i, (name, is_, isnt) in enumerate(TERMS):
    xx = ML + i * (cw + 0.16)
    rect(sl, xx, CY, cw, CH, fill=WHITE, line=RULE)
    rect(sl, xx, CY, cw, 0.05, fill=CRIMSON)
    tf = txt(sl, xx + 0.14, CY + 0.16, cw - 0.28, CH - 0.32)
    para(tf, name, size=12, color=INK, bold=True, font=SERIF, first=True,
         space_after=5)
    para(tf, is_, size=8.6, color=INK, line=1.18, space_after=7)
    runs(tf, [("Not  ", CRIMSON, True), (isnt, SLATE, False)],
         size=8.2, line=1.16, space_after=0)

note(sl, ML, CY + CH + 0.20, CW, 0.80,
     "How they correlate. ",
     "A MODEL owns versions; each version is a KERNEL. A FEATURESET presents X. "
     "A fit inhabits P and returns PARAMETERS. A WARRANT is what names a "
     "kernel, a point in P and a source of X together \u2014 ",
     "which is why it is the only one of the five that can be acted on.")

# ---------------------------------------------------------- the big diagram
sl, y = content("Model, feature and warrant management",
                "The shape of the whole thing")

LANE_X = ML
LABEL_W = 1.20
FLOW_X = LANE_X + LABEL_W + 0.10
FLOW_W = CW - LABEL_W - 0.28      # room so the last tip clears the band
LH = 1.06                     # lane height
LGAP = 0.46                   # gap between lanes, where the join arrows sit
STEPS = 5
SGAP = 0.10
BW = (FLOW_W - SGAP * (STEPS - 1)) / STEPS

L1 = y + 0.06
L2 = L1 + LH + LGAP
L3 = L2 + LH + LGAP

TINT1 = RGBColor(0xFA, 0xF4, 0xF5)
TINT2 = RGBColor(0xF6, 0xF3, 0xEF)
TINT3 = RGBColor(0xF3, 0xF4, 0xF6)


def col(i):
    return FLOW_X + i * (BW + SGAP)


# --- lane 1: the data -----------------------------------------------------
lane(sl, LANE_X, L1, CW, LH, "Feature", "what the model reads", TINT1, CRIMSON)
for i, (t, b) in enumerate([
        ("Define", "a meaning: entity, shape, owner"),
        ("Derive", "Z = f(X, Y), lineage recorded"),
        ("Materialise", "values into a pinned Delta version"),
        ("Declare a set", "a SCHEMA of named slots"),
        ("Publish v1", "slots filled, every binding pinned")]):
    stage(sl, col(i), L1 + 0.09, BW, LH - 0.18, t, b,
          WHITE if i < 4 else PARCH_D, RULE)

# --- lane 2: the model ----------------------------------------------------
lane(sl, LANE_X, L2, CW, LH, "Model", "what will run", TINT2, CRIMSON)
for i, (t, b) in enumerate([
        ("Register", "owner, purpose, legal entity"),
        ("Assess", "the tier, which sets the control depth"),
        ("Create version", "the kernel f : P \u00d7 X \u2192 D(Y)"),
        ("Approve", "a quorum whose size follows the tier"),
        ("Point an alias", "refused unless the contract refines")]):
    stage(sl, col(i), L2 + 0.09, BW, LH - 0.18, t, b,
          WHITE if i != 2 else PARCH_D, RULE)

# --- lane 3: execution ----------------------------------------------------
lane(sl, LANE_X, L3, CW, LH, "Execution", "outside MAYA", TINT3, SLATE)
for i, (t, b) in enumerate([
        ("Fit warrant", "model version \u00d7 featureset version \u00d7 window"),
        ("Engine runs", "MAYA signs it and waits"),
        ("Parameter set", "an inhabitant of P comes back"),
        ("Approve it", "by somebody other than who recorded it"),
        ("Score warrant", "names the model AND the parameter set")]):
    stage(sl, col(i), L3 + 0.09, BW, LH - 0.18, t, b,
          WHITE if i not in (0, 4) else PARCH_D, RULE)

# --- the joins: the only vertical arrows, and each one is a claim ---------
JOIN1 = col(4) + BW * 0.42
down(sl, JOIN1, L1 + LH + 0.05, LGAP - 0.10, CRIMSON)
tf = txt(sl, FLOW_X, L1 + LH + 0.11, JOIN1 - FLOW_X - 0.14, 0.26)
para(tf, "the featureset version a fit will read  \u2192", size=8,
     color=CRIMSON, italic=True, first=True, space_after=0,
     align=PP_ALIGN.RIGHT)

JOIN2 = col(2) + BW * 0.42
down(sl, JOIN2, L2 + LH + 0.05, LGAP - 0.10, CRIMSON)
tf = txt(sl, FLOW_X, L2 + LH + 0.11, JOIN2 - FLOW_X - 0.14, 0.26)
para(tf, "the model version it is issued against  \u2192", size=8,
     color=CRIMSON, italic=True, first=True, space_after=0,
     align=PP_ALIGN.RIGHT)

# --- the band everything lands in ----------------------------------------
BAND = L3 + LH + 0.20
rect(sl, ML, BAND, CW, 0.44, fill=CRIMSON)
tf = txt(sl, ML + 0.20, BAND + 0.09, CW - 0.4, 0.30)
runs(tf, [("Evidence chain   ", WHITE, True),
          ("every act above appends a node \u2014 append-only, hash-linked, and "
           "verified by re-deriving each node rather than re-reading it",
           RGBColor(0xF4, 0xDF, 0xE3), False)],
     size=9.5, first=True, space_after=0)

tf = txt(sl, ML, BAND + 0.58, CW, 0.42)
runs(tf, [("Left to right within a lane; downward where one lane hands "
           "something to the next. ", CRIMSON, True),
          ("The two vertical arrows are the whole design: a featureset version "
           "and a model version meet in a fit warrant, and the parameter set "
           "that comes back is what the next warrant names.", SLATE, False)],
     size=9.5, first=True, space_after=0, line=1.2)

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
