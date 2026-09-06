# ============================================================ CH 2
_state["chapter"] = "2 · One Estate, Many Kinds of Model"

# --------------------------------------------------------- what is there
# The "is it AI?" slide that used to sit between this one and the next has been
# folded into the note below. It made one point in two text columns and a
# hundred and eighty words, and the point is a caption on this table.
sl, y = content("A bank's estate is not one kind of thing",
                "The problem · what is actually there")
data = [["What it is", "How P is inhabited", "Trained?", "Roughly how many"],
        ["A pricing library — discount, bond, swaption", "from theory", "no", "hundreds"],
        ["A term-structure model, solved each morning", "a solver, against quotes", "no", "tens"],
        ["A scorecard on eight thousand rows", "a statistical estimator", "yes", "hundreds"],
        ["A network with twenty million weights", "a training run", "yes", "tens"],
        ["A fraud model refitted nightly on its own outcomes",
         "a training run that never stops", "yes, continuously", "a handful"],
        ["A language model somebody else hosts", "a configuration", "no", "growing"],
        ["A vendor black box under licence", "inside their binary", "unknowable", "dozens"],
        ["An expert-weighted scoring sheet", "a room full of people", "no", "dozens"],
        ["Four thousand spreadsheets", "cells", "no", "thousands"]]
th = table(sl, data, ML, y, CW, col_w=[4.5, 3.2, 1.5, 2.434],
           row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 1.45,
     "“Is it AI?” cuts across this list rather than along it. ",
     "Black–Scholes and a linear regression land in different buckets, though "
     "both have a closed form and only one of them has parameters at all; a "
     "linear regression and a language model land in the same one, though one "
     "is fitted from eight thousand rows you own and the other is configured "
     "around weights somebody else replaces on a Tuesday. One process is then "
     "expected to cover all of it, and a checklist with fields that make no "
     "sense for half the estate is one people answer “N/A” to until they stop "
     "reading the fields at all.")

# ---------------------------------------------------- the right question
sl, y = content("“How is P inhabited?” sorts it correctly",
                "The problem · the question that works")
# Nine rows for nine classes. T4 was absent for four milestones — the slide the
# whole thesis rests on was missing the class that separates a model trained
# once from a model that is still training, which is the distinction the
# monitoring and re-approval rules key on.
data = [["How P is inhabited", "Example", "Class", "Can it be fitted?"],
        ["it isn't — nothing to fill", "Black–Scholes", "T0", "asking is a TYPE ERROR"],
        ["a solver, against market quotes", "Hull–White", "T1", "yes — daily"],
        ["a statistical estimator", "a PD scorecard", "T2", "yes"],
        ["a training run", "a fraud network", "T3", "yes"],
        ["a training run that continues after release", "an adaptive fraud model",
         "T4", "yes — and it never stops"],
        ["a configuration around someone else's model", "a triage assistant", "T5", "configured"],
        ["inside a vendor's binary", "an AML score", "T6", "not reachable"],
        ["a room full of people", "an expert scorecard", "T7", "elicited"],
        ["rules somebody wrote down", "an underwriting policy", "T8", "authored"]]
th = table(sl, data, ML, y, CW, col_w=[4.3, 2.7, 1.1, 3.534],
           row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.26, CW, 1.25,
     "The class is DERIVED from that answer and never declared. ",
     "Two facts about the kernel go in — the kind of P and the procedure that "
     "inhabits it — and the order of the derivation is the whole of it: opaque "
     "is T6 before anything else is asked, a terminal P is T0, and train with "
     "adaptive set is T4 rather than T3. So asking a closed-form pricer for its "
     "training set is a type error rather than an empty field, and a rule set "
     "is not a second-class citizen squeezed into a schema designed for "
     "gradient descent.")

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
