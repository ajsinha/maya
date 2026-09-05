# ============================================================ CH 8
divider("8", "The Laws, and Which of Them Run",
        "Twenty-one stated, sixteen executable, five not — and the five are "
        "named with the reason.",
        ["Why a law rather than a test", "What runs, and what does not",
         "What the laws refuse"])

# ------------------------------------------------------ why laws at all
sl, y = content("A law is a claim about the system, not about a function",
                "The laws · why")
tf = txt(sl, ML, y, CW * 0.54, 3.0)
para(tf, "The difference matters when something changes.", size=13,
     color=CRIMSON, bold=True, font=SERIF, first=True, space_after=10)
para(tf, "A unit test says “this function returns 4”. Somebody who changes the "
         "function updates the test, and both are consistent and both may be "
         "wrong.",
     size=11.5, color=INK, space_after=8, line=1.28)
para(tf, "A law says “no state is reachable except along declared "
         "transitions”. Somebody who adds an edge does not get to update that "
         "sentence — the sentence is the requirement, and the test computes "
         "whether it still holds.",
     size=11.5, color=INK, space_after=8, line=1.28)
para(tf, "So a law is tested as it is STATED, not as the implementation "
         "happens to behave. A test written from the code proves only that the "
         "code agrees with itself.",
     size=11.5, color=CRIMSON, bold=True, space_after=0, line=1.28)

x = ML + CW * 0.58
data = [["", "Foundational", "Warrant admissibility"],
        ["Stated", "21", "14"],
        ["Executable", "16", "14"],
        ["Enforcing", "yes, where applicable", "all, before the signature"]]
th = table(sl, data, x, y, CW * 0.42, col_w=[1.5, 1.9, 1.94],
           row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + th + 0.28, CW * 0.42, 1.55,
     "Sixteen of twenty-one is the honest number. ",
     "The strongest claim this design makes is that the laws are the acceptance "
     "criteria, and a claim only partly true reads as wholly true to everybody "
     "who does not check. The number is computed from the table's own rows, so "
     "it cannot drift.")

# --------------------------------------------------- what runs, what does not
sl, y = content("Sixteen of the twenty-one run; five do not",
                "The laws · what is enforced")
left = [["Law", "What it says"],
        ["L-1", "no state is reachable except along declared transitions"],
        ["L-2", "a version's content hash never moves over its lifetime"],
        ["L-3", "a determinism claim is checked by executing twice"],
        ["L-4", "tiering is monotone in materiality and complexity"],
        ["L-5", "the required controls and the tier determine each other"],
        ["L-7", "an alias move requires the new contract to refine the old"],
        ["L-8", "a regulatory regime's translation preserves truth"],
        ["L-9", "one traversal answers every provenance question"]]
right = [["Law", "What it says"],
         ["L-10", "the as-of read saturates at the moment of the decision"],
         ["L-12", "a replacement accepts at least what it replaced"],
         ["L-15", "every trainability class has its own evidence and metrics"],
         ["L-16", "no regulatory regime obliges and forbids one term"],
         ["L-18", "no personal data inside an evidence node"],
         ["L-19", "composition is associative, with an identity"],
         ["L-20", "schemas form a lattice; independent edits commute"],
         ["L-21", "a dependency edge type-checks or does not exist"]]
hw = CW * 0.49
h1 = table(sl, left, ML, y, hw, col_w=[0.7, 5.0],
           row_h=0.30, fs=9, hfs=9, bold_col0=True, first_col_color=CRIMSON)
table(sl, right, ML + CW * 0.51, y, hw, col_w=[0.7, 5.0],
      row_h=0.30, fs=9, hfs=9, bold_col0=True, first_col_color=CRIMSON)

data = [["Not built", "Why not"],
        ["L-6  abstraction soundness",
         "nothing compares a generated summary with what it summarises; the "
         "replay that could exists for validation episodes, not documents"],
        ["L-11  lens laws",
         "documentation is regenerated whole rather than edited back, so there "
         "is no round trip to test"],
        ["L-13  evidence gluing", "no consistency radius is computed anywhere"],
        ["L-14  lax monoidality of risk",
         "there is no aggregate risk measure over composed models, and no "
         "interaction premium"],
        ["L-17  contract–serving agreement",
         "there is no online feature store to compare against; half of it "
         "exists — what serving must read is computed"]]
table(sl, data, ML, y + h1 + 0.26, CW, col_w=[2.6, 9.034],
      row_h=0.30, fs=9, hfs=9, bold_col0=True, first_col_color=CRIMSON,
      head_fill=SLATE)

# ------------------------------------------------------- what they refuse
sl, y = content("What the laws refuse — and one thing they cannot",
                "The laws · what they catch")
outs = [("A run that will not say which numbers it used  ·  L-W8",
         "Fitting does not change the kernel, so a run declining to name the "
         "point of P it runs at produces a number attributable to nothing. "
         "Three of the shipped warrant examples were under-specified this way "
         "until the law ran."),
        ("A calibration with no as-of moment  ·  L-W11",
         "A calibration reproduces a market rather than summarising a history, "
         "so the moment it was solved for is part of what it means. Without the "
         "stamp, staleness is silent: yesterday's fit prices today's book and "
         "nothing says which market it came from."),
        ("A generative model named by family, not by build  ·  L-W13",
         "A family name covers weights the host replaces on its own schedule, "
         "unannounced. A warrant carrying only the family describes a model "
         "that can change between two runs while every field of the document "
         "stays identical."),
        ("And one thing the laws cannot reach  ·  L-9",
         "Freshness is not a semiring — (max, max) has no annihilating zero — "
         "so a claim resting on a MISSING fact reports the freshness of the "
         "facts that are present. The limit is stated rather than hidden.")]
cw2 = (CW - 0.30) / 2
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 2) * (cw2 + 0.30), y + (i // 2) * 2.35, cw2, 2.15,
         f"0{i+1}", t, d)
