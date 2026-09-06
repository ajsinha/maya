# ============================================================ CH 3A
#
# The chapter a CIO was missing.
#
# A reviewer read the deck as the person who signs for it and found no cost
# anywhere, and a build-or-buy argument that never named who it was arguing
# against. A business case with no number in it is a preference.
_state["chapter"] = "3A · The Decision, and What It Costs"

# ---------------------------------------------------------------- the problem
sl, y = content("What model risk costs before anybody buys anything",
                "The decision · the baseline")
statbar(sl, y, [
    ("6–15%", "of a large bank's operational risk capital is model risk, and "
              "it is the fastest-growing component"),
    ("30–60", "FTE in a mid-size bank's model risk function, most of it "
              "clerical: chasing evidence, reformatting it, chasing it again"),
    ("2–5", "separate inventories at most banks — GRC, MLOps, and a "
            "spreadsheet — which disagree, and the disagreement is the finding"),
])
y += 1.45
note(sl, ML, y, CW, 1.30,
     "None of these is MAYA's number. ",
     "They are the industry's, sourced in chapter 2, and they are the baseline "
     "any option is measured against — including doing nothing. The honest "
     "form of this slide is that the expensive thing is already happening: a "
     "validator spending sixty per cent of their week assembling evidence is a "
     "cost the bank pays whether or not it buys a platform, and it does not "
     "appear in anybody's software budget.")

# ------------------------------------------------------------ what it costs
sl, y = content("What each option costs, and what it leaves you holding",
                "The decision · build or buy")
data = [["Option", "Order of cost", "What you still do not have"],
        ["Buy a GRC/MRM platform\nOpenPages, SAS MRM,\nValidMind, ModelOp",
         "£0.4–1.2m licence a year,\nplus 6–18 months of\nimplementation",
         "No artifact binding, no feature management, no warrants, no coverage "
         "of the quant or EUC estate. A second and third system alongside it"],
        ["Buy an MLOps platform\nDatabricks, Domino,\nDataRobot",
         "£0.5–2m a year, usually\nalready being paid for\nother reasons",
         "No MRM domain objects, no multi-regime scoping, no overlays, no "
         "findings. The ML subset is a minority of the estate"],
        ["Buy both and integrate",
         "The sum of the two, plus\nan integration nobody owns",
         "Two inventories that disagree. The status quo at most large banks, "
         "and the disagreement is itself an audit finding"],
        ["Build",
         "Higher up front; no\nlicence, no per-seat, no\nvendor roadmap risk",
         "The build itself, and the operational work in chapter 23 — which is "
         "a real cost and is named rather than folded into a total"]]
th = table(sl, data, ML, y, CW, col_w=[3.0, 3.0, 5.634],
           row_h=0.86, fs=9.5, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.22, CW, 1.00,
     "The ranges are indicative and public. ",
     "A bank's own numbers will differ and should replace these before this "
     "slide is shown to a committee — the point of the column is that the "
     "comparison is between totals rather than between licence fees, and the "
     "third row is what most banks are paying today without having decided to.")

# ------------------------------------------------------- what is being decided
sl, y = content("What a CIO is actually deciding", "The decision · the question")
data = [["The question", "The answer this platform gives"],
        ["Can I evidence the estate to a supervisor without a project?",
         "An export pack is cut from the register on demand, self-contained and "
         "digested, with its gaps named rather than omitted"],
        ["Will it tell me what I do not want to hear?",
         "Refusals are the product. An unattested estate reports as unattested, "
         "and 'not measured' is never rendered as zero"],
        ["What happens when the next regulation arrives?",
         "A regime is encoded as sentences over its own vocabulary and activated "
         "if — and only if — its encoding survives translation. Three ship"],
        ["What happens when the next model paradigm arrives?",
         "A trainability class is DERIVED from how the parameters were obtained, "
         "so an LLM and a scorecard are the same object with different fibres"],
        ["What am I exposed to if this is wrong?",
         "Eighteen of twenty-one foundational laws execute on every push. The "
         "three that do not are named, with the reason, in the same table"]]
th = table(sl, data, ML, y, CW, col_w=[4.6, 7.034],
           row_h=0.58, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.24, CW, 1.05,
     "The last row is the one that decides it. ",
     "Every platform in this market will tell a committee that it works. What "
     "a CIO can ask for is the list of things it does NOT do, written by the "
     "people who built it, in the same document — and then check that the "
     "list is honest by running the tests. Chapter 23 is that list.")
