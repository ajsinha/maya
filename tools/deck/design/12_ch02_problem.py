# ============================================================ CH 2
divider("2", "One Estate, Many Kinds of Model",
        "Why “is it AI?” separates nothing useful, and what it costs to keep "
        "asking it.",
        ["What is actually in the estate", "The question that sorts it wrongly",
         "The question that sorts it correctly", "Asserted, not evidenced"])

# --------------------------------------------------------- what is there
sl, y = content("A bank's estate is not one kind of thing",
                "The problem · what is actually there")
data = [["What it is", "How P is inhabited", "Trained?", "Roughly how many"],
        ["A pricing library — discount, bond, swaption", "from theory", "no", "hundreds"],
        ["A term-structure model, solved each morning", "a solver, against quotes", "no", "tens"],
        ["A scorecard on eight thousand rows", "a statistical estimator", "yes", "hundreds"],
        ["A network with twenty million weights", "a training run", "yes", "tens"],
        ["A language model somebody else hosts", "a configuration", "no", "growing"],
        ["A vendor black box under licence", "inside their binary", "unknowable", "dozens"],
        ["An expert-weighted scoring sheet", "a room full of people", "no", "dozens"],
        ["Four thousand spreadsheets", "cells", "no", "thousands"]]
th = table(sl, data, ML, y, CW, col_w=[4.5, 3.2, 1.5, 2.434],
           row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 0.95,
     "One process is expected to cover all of it. ",
     "Most tooling covers the third and fourth rows well and leaves the rest to "
     "a spreadsheet — which is the spreadsheet the programme was bought to "
     "replace.")

# ---------------------------------------------------- the wrong question
sl, y = content("“Is it AI?” puts these in different buckets",
                "The problem · the question that sorts wrongly")
x1, x2 = ML, ML + CW * 0.52
tf = txt(sl, x1, y, CW * 0.46, 2.6)
para(tf, "Different buckets", size=13, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=10)
para(tf, "Black–Scholes  ·  a linear regression", size=13, color=INK,
     font=MONO, space_after=8)
para(tf, "One is “not AI” and one is “traditional statistics”, and the "
         "validation checklist differs — although both have a closed form, both "
         "have an operating boundary, and only one of them has parameters at "
         "all.",
     size=11, color=SLATE, space_after=0, line=1.28)

tf = txt(sl, x2, y, CW * 0.46, 2.6)
para(tf, "The same bucket", size=13, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=10)
para(tf, "a linear regression  ·  a large language model", size=13, color=INK,
     font=MONO, space_after=8)
para(tf, "Both are “models”, or on a bad day both are “AI”. One is fitted from "
         "eight thousand labelled rows you own; the other is configured around "
         "weights somebody else replaces on a Tuesday without telling you.",
     size=11, color=SLATE, space_after=0, line=1.28)

note(sl, ML, y + 2.85, CW, 1.55,
     "Everything downstream inherits the confusion. ",
     "A validation checklist with fields that make no sense for half the "
     "estate, so people write “N/A” and then stop reading the fields at all. "
     "And controls that are ceremony for some models and absent for others — "
     "the worse of the two, because it looks like coverage.")

# ---------------------------------------------------- the right question
sl, y = content("“How is P inhabited?” sorts it correctly",
                "The problem · the question that works")
data = [["How P is inhabited", "Example", "Class", "Can it be fitted?"],
        ["it isn't — nothing to fill", "Black–Scholes", "T0", "asking is a TYPE ERROR"],
        ["a solver, against market quotes", "Hull–White", "T1", "yes — daily"],
        ["a statistical estimator", "a PD scorecard", "T2", "yes"],
        ["a training run", "a fraud network", "T3", "yes"],
        ["a configuration around someone else's model", "a triage assistant", "T5", "configured"],
        ["inside a vendor's binary", "an AML score", "T6", "not reachable"],
        ["a room full of people", "an expert scorecard", "T7", "elicited"],
        ["rules somebody wrote down", "an underwriting policy", "T8", "authored"]]
th = table(sl, data, ML, y, CW, col_w=[4.3, 2.7, 1.1, 3.534],
           row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.26, CW, 1.05,
     "The class is DERIVED from that answer and never declared. ",
     "It falls out of two facts about the kernel, so asking a closed-form "
     "pricer for its training set is a type error rather than an empty field, "
     "and a rule set is not a second-class citizen squeezed into a schema "
     "designed for gradient descent.")

# ------------------------------------------------- asserted not evidenced
sl, y = content("The deeper failure: governance is asserted, not evidenced",
                "The problem · what nobody can check")
data = [["The claim", "Where it lives", "What connects it to reality"],
        ["“This model was validated in March”", "a spreadsheet cell", "nothing"],
        ["“That finding was closed”", "a ticket", "nothing"],
        ["“The champion is version 3.2.1”", "a deployment note", "nothing"],
        ["“These coefficients were approved”", "an email thread", "nothing"],
        ["“It was trained on Q1 data”", "a slide", "nothing"]]
th = table(sl, data, ML, y, CW, col_w=[4.4, 3.4, 3.834],
           row_h=0.34, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.32, CW, 1.55,
     "An examiner is shown a claim and asked to believe it. ",
     "So is the organisation's own risk committee: the second line is in the "
     "same position as the regulator, reading assertions it cannot check "
     "against artefacts it cannot reach. Every design decision in the rest of "
     "this deck is downstream of refusing that arrangement.")
