# ============================================================ CH 4
divider("4", "The Definition",
        "f : P ⊗ X → D(Y). One line, and everything else derived from it.",
        ["The five words", "Why a distribution", "Trainability, derived",
         "What it dissolves"])

# ------------------------------------------------------------ the equation
sl, y = content("A model is a parametric kernel", "Foundations · the definition")
tf = txt(sl, ML, y, CW, 0.9, align=PP_ALIGN.CENTER)
para(tf, "f  :  P  ⊗  X  →  D(Y)", size=34, color=INK, font=MONO, first=True,
     space_after=0)

data = [["Term", "Is", "Commonly mistaken for"],
        ["f", "the kernel — the computation itself",
         "“the model”, which is the kernel AND a point of P"],
        ["P", "the parameter object: everything fitted, calibrated, configured "
             "or elicited",
         "“the weights”, which is one way of inhabiting it"],
        ["X", "the input object — a NAMED, versioned presentation of the data",
         "“the features”, which are its constituents rather than its identity"],
        ["⊗", "tensor: P and X arrive together and neither is privileged",
         "a function of X that happens to have settings"],
        ["D(Y)", "a DISTRIBUTION over outputs, not a value",
         "the answer, which is one draw or one summary of it"]]
th = table(sl, data, ML, y + 1.05, CW, col_w=[1.0, 5.4, 5.234],
           row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + 1.05 + th + 0.26, CW, 0.85,
     "Five words, and four of them are usually collapsed into two. ",
     "Most of the confusion in model governance is a consequence of that "
     "collapse rather than of anything difficult.")

# ------------------------------------------------------- why a distribution
sl, y = content("Why the target is a distribution and not a value",
                "Foundations · D(Y)")
tf = txt(sl, ML, y, CW * 0.54, 3.4)
para(tf, "Because most models do not return a number.", size=13, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=10)
for lead, rest in [
    ("A PD scorecard ", "returns a probability — which IS a distribution over "
                        "{default, not}, and treating it as a number is how a "
                        "calibration error becomes invisible."),
    ("A Monte Carlo engine ", "returns an estimate with a standard error. The "
                             "point estimate alone is a claim without its "
                             "uncertainty."),
    ("A GARCH ", "returns a variance — a statement about a distribution rather "
                 "than a draw from one."),
    ("An LLM ", "returns a sample. Two calls differ, and a design that assumes "
                "otherwise will be believed by whatever reads the result."),
]:
    runs(tf, [("→  ", CRIMSON, True), (lead, INK, True), (rest, SLATE, False)],
         size=10.5, space_after=8)

x = ML + CW * 0.58
note(sl, x, y, CW * 0.42, 2.2,
     "Making D(Y) part of the definition forces the question early. ",
     "A version declares its output kind — point estimate, probability, "
     "distribution, interval, ranking, text — and the warrant carries it, so an "
     "engine that receives a distribution and reports a mean has done something "
     "the record can name.")
note(sl, x, y + 2.40, CW * 0.42, 1.9,
     "It is also where determinism lives. ",
     "`deterministic` is a CLAIM about the map, and the grammar checks it: "
     "asserted without a pinned seed, from any runtime that executes code MAYA "
     "cannot read, it is refused rather than believed (L-W5).")

# ---------------------------------------------------- trainability derived
sl, y = content("The class falls out; nobody declares it",
                "Foundations · trainability")
h = code(sl, ML, y, CW * 0.52, [
    "parameter_kind   ×   fit_procedure   ⟹   trainability class",
    "",
    "none             ×   none            ⟹   T0   theory; nothing to fit",
    "calibration_set  ×   calibrate       ⟹   T1   solved against quotes",
    "estimated_coeffs ×   estimate        ⟹   T2   a statistical estimator",
    "learned_weights  ×   train           ⟹   T3   a training run",
    "         ... and adaptive        ⟹   T4   training that continues",
    "llm_configuration×   configure       ⟹   T5   somebody else's model",
    "rule_set         ×   none            ⟹   T8   rules, written down",
    "opaque           ×   none            ⟹   T6   inside a vendor binary",
], fs=9.5, title="core/domain/algebra.py")

x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 3.4)
para(tf, "Why derivation rather than declaration", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=9)
para(tf, "“Is this model trained?” is a question that invites the answer "
         "requiring least work — and the answer is then a field somebody typed, "
         "which every control keys on.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "The class here is a fact about the ARTIFACT rather than an opinion "
         "about it. Two facts go in and the class comes out, so it cannot be "
         "wrong without one of the two facts being wrong — and those are facts a "
         "reviewer can check.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "It is also what makes a refusal a type error rather than a policy: "
         "asking a T0 for its training set is incoherent, not disallowed.",
     size=11, color=SLATE, space_after=0, line=1.26)

# ------------------------------------------------------- what it dissolves
sl, y = content("Four problems that stop existing", "Foundations · consequences")
outs = [("“Which models need validating?”",
         "Every model. What DIFFERS is the evidence each can produce, and the "
         "class says which — so a T0 gets benchmarked against an independent "
         "implementation and a T3 gets replayed."),
        ("“Is a spreadsheet a model?”",
         "If it maps inputs to outputs under parameters, yes. rule_set × none "
         "⟹ T8, and it is governed like anything else rather than living in a "
         "separate register nobody reads."),
        ("“How do we validate an LLM?”",
         "P is a configuration: base model, prompt, corpus version, tools, "
         "guardrails. Each is versioned and pinned, so “what changed” has an "
         "answer that is not “the vendor did something”."),
        ("“What is a model change?”",
         "A change to f is a new version. A change to P is a new parameter "
         "set. A change to X is a model change too, and L-W10 is where that is "
         "enforced rather than remembered.")]
cw2 = (CW - 0.30) / 2
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 2) * (cw2 + 0.30), y + (i // 2) * 2.35, cw2, 2.15,
         f"0{i+1}", t, d)
