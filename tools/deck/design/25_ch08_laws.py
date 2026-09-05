# ============================================================ CH 8
divider("8", "The Laws, and Which of Them Run",
        "Twenty-one stated, fifteen executable, six not — and the six are named "
        "with the reason.",
        ["Why a law rather than a test", "What runs today",
         "What writing them found", "What does not run, and why"])

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
        ["Executable", "15", "14"],
        ["Enforcing", "yes, where applicable", "all, before the signature"]]
th = table(sl, data, x, y, CW * 0.42, col_w=[1.5, 1.9, 1.94],
           row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + th + 0.28, CW * 0.42, 1.9,
     "It was seven of nineteen. ",
     "The strongest claim this design makes is that the laws are the acceptance "
     "criteria, and a claim that is 37% true reads as 100% true to everybody who "
     "does not check. The count is now derived from the table's own rows by a "
     "test, so it cannot drift the way every other count in the repository has.")

# ------------------------------------------------------------ what runs
sl, y = content("The fifteen that run", "The laws · what is enforced")
data = [["Law", "Says", "Where"],
        ["L-1", "no state is reachable except along declared transitions, from two initial ones", "test_laws"],
        ["L-2", "hash(manifest(v)) is constant over a version's lifetime", "test_laws"],
        ["L-3", "a determinism claim is checked by executing twice", "test_laws"],
        ["L-4", "tiering is monotone in materiality and complexity", "test_risk"],
        ["L-5", "the control set is a Galois adjoint of the tier", "test_risk"],
        ["L-7", "an alias move requires contract refinement", "aliases.py"],
        ["L-8", "a regime's translation preserves truth", "regimes/"],
        ["L-9", "the provenance polynomial is universal", "test_laws"],
        ["L-10", "the as-of read saturates at the label", "test_laws"],
        ["L-12", "schema variance: contravariant in, covariant out", "schemas.py"],
        ["L-16", "no regime obliges and forbids the same term", "regimes/"],
        ["L-18", "no personal data inline in an evidence node", "evidence/"],
        ["L-19", "composition is a monoid", "test_composition"],
        ["L-20", "schemas form a lattice; independent edits commute", "test_laws"],
        ["L-21", "an input_to edge type-checks or does not exist", "test_laws"]]
th = table(sl, data, ML, y, CW, col_w=[0.9, 8.2, 2.534],
           row_h=0.27, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)

# ------------------------------------------------------- what they found
sl, y = content("What writing them found", "The laws · the return")
outs = [("L-W8 · a shipped example was wrong",
         "The Hull–White calibration warrant declared its parameters came from "
         "an artifact while its verb produced them. Two more examples were wrong "
         "the same way. Found on the day the law was written."),
        ("L-W11 and L-W13 · two more, the same day",
         "A VaR backtest that never said what it was calibrated as of, and both "
         "LLM examples naming a model family rather than a build. Three of "
         "thirteen shipped warrants were quietly under-specified."),
        ("L-1 · baselined was reachable by no edge",
         "Which looked like a violation and was not: it is a second INITIAL "
         "object, because an imported record must not enter through draft or the "
         "register would imply evidence was asserted when it was not."),
        ("L-9 · freshness is not a semiring",
         "(max, max) has no annihilating zero. So the universal property does "
         "not reach it, and a claim resting on a missing fact reports the "
         "freshness of the facts that are present."),
        ("L-20 · the design note was backwards",
         "It said a refinement is “at a type no wider”. Standing in for "
         "something requires accepting AT LEAST what it accepted. The code had "
         "it right; the prose did not."),
        ("L-10 · a per-model document quoted a global count",
         "The provenance lens reported the PLATFORM-WIDE chain length inside "
         "each model's document, so every model's document changed whenever "
         "anything happened anywhere.")]
cw2 = (CW - 0.30 * 2) / 3
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 3) * (cw2 + 0.30), y + (i // 3) * 2.30, cw2, 2.10,
         f"0{i+1}", t, d)

# ---------------------------------------------------------- what does not
sl, y = content("The six that do not run, and why", "The laws · the honest gap")
data = [["Law", "Why not"],
        ["L-6  abstraction soundness",
         "needs a replay that checks a document's quantitative claims against "
         "the register; the replay exists for validation episodes, not documents"],
        ["L-11  lens laws",
         "needs a `put`. The compiler regenerates whole documents, so there is "
         "no round trip — and building one to satisfy a law would be building "
         "the wrong thing"],
        ["L-13  evidence gluing",
         "no consistency radius is computed anywhere"],
        ["L-14  lax monoidality of risk",
         "typed composition gives it something to quantify over; the aggregate "
         "ρ and composite warrants are not built"],
        ["L-15  fibration completeness",
         "needs a plugin loader that refuses to boot on a partial fibre; model "
         "classes are strings on the register today"],
        ["L-17  contract–serving agreement",
         "needs an online store to compare against. Half exists: "
         "serving_namespaces computes what serving MUST read"]]
th = table(sl, data, ML, y, CW, col_w=[3.2, 8.434],
           row_h=0.38, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 1.05,
     "A law that is stated but not executed did not prevent anything. ",
     "Which is why they are listed here rather than only in a table nobody "
     "opens — and why the test file that runs the other fifteen carries this "
     "same list, so the gap is visible where somebody is already looking.")
