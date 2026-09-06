# ============================================================ CH 4
_state["chapter"] = "4 · The Definition"

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
        ["⊗", "P and X arrive together and neither is privileged",
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
    ("A PD scorecard ", "returns a probability — a distribution over "
                        "{default, not}. Treat it as a number and a "
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
note(sl, x, y, CW * 0.42, 1.80,
     "Making D(Y) part of the definition forces the question early. ",
     "A version declares its output kind — point estimate, probability, "
     "distribution, interval, ranking, text — and the warrant carries it, so an "
     "engine reporting the mean of a distribution has done something the record "
     "can name.")
note(sl, x, y + 2.00, CW * 0.42, 1.60,
     "It is also where determinism lives. ",
     "“Deterministic” is a CLAIM, checked before a warrant is signed. Asserted "
     "with no pinned seed, from a runtime MAYA cannot read, it is refused "
     "rather than believed — L-W5.")

# ---------------------------------------------------- trainability derived
sl, y = content("The class falls out; nobody declares it",
                "Foundations · trainability")
h = code(sl, ML, y, CW * 0.52, [
    "parameter_kind     ×  fit_procedure   ⟹  class",
    "",
    "none               ×  none            ⟹  T0  theory; nothing to fit",
    "calibration_set    ×  calibrate       ⟹  T1  solved against quotes",
    "estimated_coeffs   ×  estimate        ⟹  T2  a statistical estimator",
    "learned_weights    ×  train           ⟹  T3  a training run",
    "learned_weights    ×  train+adaptive  ⟹  T4  training that continues",
    "llm_configuration  ×  configure       ⟹  T5  somebody else's model",
    "opaque             ×  anything        ⟹  T6  inside a vendor binary",
    "elicited_weights   ×  elicit          ⟹  T7  a room full of people",
    "rule_set           ×  author          ⟹  T8  rules, written down",
], fs=9.5, title="core/domain/algebra.py")

x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 3.4)
para(tf, "Why derivation rather than declaration", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=9)
para(tf, "“Is this model trained?” invites the answer requiring least work — "
         "and the answer is then a field somebody typed, which every control "
         "keys on.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "The class is a fact about the artefact rather than an opinion about "
         "it: two facts go in, and both are facts a reviewer can check.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "It is also what makes a refusal a type error rather than a policy: "
         "asking a T0 for its training set is incoherent, not disallowed.",
     size=11, color=SLATE, space_after=0, line=1.26)

# ------------------------------------------------------- what it dissolves
sl, y = content("Four problems that stop existing", "Foundations · consequences")
outs = [("“Which models need validating?”",
         "Every model. What DIFFERS is the evidence each can produce: a T0 is "
         "benchmarked against an independent implementation, a T3 is replayed."),
        ("“Is a spreadsheet a model?”",
         "If it maps inputs to outputs under parameters, yes. rule_set × "
         "author ⟹ T8, governed like anything else rather than kept in a "
         "register nobody reads."),
        ("“How do we validate an LLM?”",
         "P is a configuration: base model, prompt, corpus version, tools, "
         "guardrails. Each is versioned and pinned, so “what changed” is not "
         "answered with “the vendor did something”."),
        ("“What is a model change?”",
         "A change to f is a new version. A change to P is a new parameter "
         "set. A change to X is a model change too — L-W10.")]
cw2 = (CW - 0.30) / 2
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 2) * (cw2 + 0.30), y + (i // 2) * 2.35, cw2, 2.15,
         f"0{i+1}", t, d)
