# ============================================================ CH 9
divider("9", "The Shape of the Whole Thing",
        "The objects have been defined. This is how they MEET — and where the "
        "pins are that stop any of them moving underneath the others.",
        ["The process, end to end",
         "What each object is for",
         "Where the pins are"])


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
