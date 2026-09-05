# ============================================================ CH 12
divider("12", "Warrants, and What Comes Back",
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
th = table(sl, data, x, y + 0.40, CW * 0.42, col_w=[0.95, 4.55], row_h=0.29, fs=9,
           hfs=9, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 0.40 + th + 0.20, CW * 0.42, 1.1)
para(tf, "MAYA does not fit anything. It signs this and waits.",
     size=11.5, color=INK, bold=True, first=True, space_after=6, line=1.24)
para(tf, "The estimation happens in an execution engine \u2014 the same "
         "boundary drawn everywhere else here.",
     size=10.5, color=SLATE, space_after=0, line=1.24)

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
