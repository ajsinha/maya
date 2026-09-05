# ============================================================ CH 15
divider("15", "What MAYA Refuses, and Why",
        "The refusals are the product. Everything else is bookkeeping.",
        ["The refusals that matter",
         "What it deliberately will not do",
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

# -------------------------------------------------------------- the boundary
sl, y = content("Where the boundary is", "What MAYA refuses, and why")
card(sl, ML, y, CW * 0.315, 2.6, "1", "It does not compute",
     "No fitting, no calibration, no scoring. MAYA issues a warrant and takes "
     "delivery of the result. The engine shipped with it exists so a fresh "
     "deployment "
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
     "would be believed about the parts it does badly. Stating the boundary "
     "is what makes ",
     "the rest of it worth relying on.")
