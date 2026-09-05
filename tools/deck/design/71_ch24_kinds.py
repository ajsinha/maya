# ============================================================ CH 24
divider("24", "Every Kind of Model",
        "Seven shapes, one definition — and how each is saved, managed and served.",
        ["The matrix, on one page",
         "Regression, GARCH, closed-form",
         "Calibration and simulation",
         "Neural networks and LLMs"])

# ---------------------------------------------------------------------------
# The chapter's own helper. Every model slide answers the same three questions
# in the same three places, because the argument of the chapter is that the
# answers differ only in the medium -- and a reader can only see that if the
# layout holds still while the content changes.
# ---------------------------------------------------------------------------
# The last safe y for body content: the footer rule sits at SH - 0.55, and a
# block that ends on it is a block the audit reports as hitting the footer.
FLOOR = SH - 0.70


def aside(sl, x, y, w, lead, rest):
    """`note`, but sized from its own text rather than from a guess.

    The theme's note() takes a height and sets 10.5pt inside it. Six of these
    slides carry a longer aside than that assumption allows, and the overflow
    lands on the footer -- so this one measures first and shrinks the type only
    as far as it has to.
    """
    text = lead + rest
    inner = w - 0.5
    size = 10.5
    while size > 8.5 and y + text_h(text, inner * SAFETY, size, line=1.24) + 0.30 > FLOOR:
        size -= 0.25
    h = text_h(text, inner * SAFETY, size, line=1.24) + 0.28
    rect(sl, x, y, w, h, fill=PARCH)
    rect(sl, x, y, 0.045, h, fill=CRIMSON)
    tf = txt(sl, x + 0.26, y + 0.13, inner, h - 0.24)
    runs(tf, [(lead, CRIMSON, True), (rest, INK, False)],
         size=size, first=True, space_after=0, line=1.24)
    return h


def model_slide(title, kicker, facts, saves, manages, serves,
                lead="", rest=""):
    sl, y = content(title, kicker)
    th = table(sl, facts, ML, y, CW, col_w=[2.5, 4.5, 4.634],
               row_h=0.26, fs=10, hfs=10, bold_col0=True,
               first_col_color=CRIMSON)
    cy = y + th + 0.26
    cw2 = (CW - 0.28 * 2) / 3
    for i, (kick, head, body) in enumerate(
            [("SAVES", *saves), ("MANAGES", *manages), ("SERVES", *serves)]):
        card(sl, ML + i * (cw2 + 0.28), cy, cw2, 1.95, kick, head, body,
             title_size=12.5, body_size=9.5)
    if lead:
        aside(sl, ML, cy + 2.13, CW, lead, rest)
    return sl


# ------------------------------------------------------- the matrix up front
sl, y = content("Seven shapes of the same definition",
                "Every kind of model")
data = [["Model", "P is", "How P is filled", "parameter_kind",
         "fit_procedure", "Class"],
        ["Black-Scholes", "empty", "it isn't - nothing to fill", "none",
         "none", "T0"],
        ["Linear regression", "coefficients", "a statistical estimator",
         "estimated_coefficients", "estimate", "T2"],
        ["GARCH / ARIMA", "omega, alpha, beta", "maximum likelihood",
         "estimated_coefficients", "estimate", "T2"],
        ["Hull-White", "mean reversion, vol", "a solver, against market quotes",
         "calibration_set", "calibrate", "T1"],
        ["Monte Carlo XVA", "parameters + seed + paths",
         "calibration plus configuration", "calibration_set", "calibrate", "T1"],
        ["Neural network", "weights - millions", "a training run",
         "learned_weights", "train", "T3"],
        ["LLM application", "base model + prompt + corpus",
         "configuration and retrieval", "llm_configuration", "configure", "T5"],
        ["Vendor score", "exists, unreachable", "somebody else's problem",
         "opaque", "none", "T6"]]
th = table(sl, data, ML, y, CW, col_w=[1.95, 2.15, 2.75, 2.55, 1.55, 0.68],
           row_h=0.28, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 0.92,
     "The class is never declared. ",
     "It is derived from the two columns before it, so asking a closed-form "
     "pricer for its training set is a type error rather than an empty field, "
     "and a rule set is not a second-class citizen squeezed into a schema "
     "designed for gradient descent. Everything that follows in this chapter "
     "is the same three questions -- how it is saved, managed and served -- "
     "asked of each row.")

# ------------------------------------------------------------------ the axis
sl, y = content("The only thing that actually differs: the medium of P",
                "Every kind of model")
data = [["Medium", "Size of P", "Lives in", "A refit is",
         "What replay compares"],
        ["A record", "tens of numbers", "the parameter register, as values",
         "a new parameter set", "the values, re-digested"],
        ["An artifact", "megabytes to gigabytes",
         "the content-addressed store, under data/artifacts",
         "a new model version", "the bytes, re-hashed"],
        ["A configuration", "a page of settings",
         "the register, plus artifacts for the prompt and corpus",
         "a new parameter set", "the assembly, field by field"],
        ["Nothing", "zero", "-", "not a thing that happens",
         "the inputs and the library version"]]
th = table(sl, data, ML, y, CW, col_w=[1.85, 2.05, 3.55, 2.15, 2.03],
           row_h=0.34, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.05,
     "Why the medium decides the unit of change. ",
     "For a regression the kernel is the equation and the coefficients are a "
     "point of P, so refitting moves the point. For a network the artifact IS "
     "P and is inseparably also the computation graph -- so retraining creates "
     "a new VERSION, not because it is more dangerous, but because the medium "
     "does not let the two be told apart, and pretending it does would let a "
     "graph change arrive labelled as a recalibration.")

# ---------------------------------------------------------------- regression
model_slide(
    "Linear regression - the ordinary case", "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "an intercept and two slopes", "the parameter register, as values"],
     ["Filled by", "ordinary least squares", "MAYA's own estimator runtime"],
     ["Kind / procedure", "estimated_coefficients / estimate", "class T2, derived"],
     ["Runtime", "estimator, family ols", "entry names target and regressors"]],
    ("Values, digested",
     "The coefficients are rows. The digest is re-derived from the values at "
     "resolve time, never compared against a stored copy of itself."),
    ("Reviewed one by one",
     "Each parameter set is approved by somebody who did not record it. The "
     "condition number is read before the R-squared."),
    ("Warrant names the set",
     "The descriptor carries the parameter set id and digest; an artifact "
     "binding would be a false statement, since there is no artifact."),
    lead="Read the condition number first. ",
    rest="In the thousands, the coefficients are a solution to this sample "
         "rather than a property of the world. MAYA does not decide whether a "
         "fit is any good -- it puts the number in front of somebody who can, "
         "and records that they looked.")

# --------------------------------------------------------------------- GARCH
model_slide(
    "GARCH and ARIMA - an iterative fit, and state at scoring time",
    "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "omega, alpha, beta", "the parameter register, as values"],
     ["Filled by", "maximum likelihood, iteratively", "estimator, family garch11"],
     ["Kind / procedure", "estimated_coefficients / estimate", "class T2, derived"],
     ["The catch", "it can fail while looking like it succeeded",
      "an unconverged fit is refused, not flagged"]],
    ("Values, plus convergence",
     "Iterations, log-likelihood and persistence are part of the result. A "
     "result that does not carry them is not reviewable."),
    ("Constrained during the fit",
     "alpha + beta < 1 is enforced while solving. Without it there is no "
     "unconditional variance and the forecast explodes."),
    ("State is supplied, not invented",
     "Scoring needs the last shock and last variance. The answer says which "
     "state it used and which it returns."),
    lead="ARMA, ARIMA and EGARCH sit in exactly this slot. ",
    rest="Same kind, same procedure, order (p, d, q) in the kernel entry. "
         "MAYA's captive engine implements ols and garch11 only -- fit the "
         "rest in your own engine and deliver the parameters back under the "
         "warrant. None of the governance changes, which is the point of "
         "separating the estimator from the register.")

# --------------------------------------------------------- closed-form pricer
model_slide(
    "A closed-form pricer - where P is empty", "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "empty. P = I, the terminal object", "nothing is stored"],
     ["Filled by", "it isn't", "a fit warrant is refused: nothing_to_fit"],
     ["Kind / procedure", "none / none", "class T0, derived"],
     ["Runtime", "quantlib", "entry names instrument and pricing engine"]],
    ("Conventions, not numbers",
     "Day count, calendar and settlement days live in the kernel entry, "
     "immutable in the version. The library version is recorded per run."),
    ("Validated by benchmark",
     "Against an independent implementation across the strike and tenor grid. "
     "Backtesting has no meaning where nothing was fitted."),
    ("Inputs are the governed thing",
     "The curve, the volatility and the valuation date are pinned in the "
     "warrant. A date defaulted to the wall clock is refused."),
    lead="The risk moved from the model to its domain of applicability. ",
    rest="There is no performance to decay, because nothing was fitted. What "
         "can go wrong is use outside the envelope it was benchmarked in -- "
         "so the monitor watches the inputs, and a breach is a finding against "
         "the USE rather than against the mathematics.")

# ---------------------------------------------------------------- Hull-White
model_slide(
    "A calibrated term-structure model - daily, by exception",
    "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "mean reversion, a term structure of sigma",
      "the parameter register, one set per day"],
     ["Filled by", "a solver, against the swaption grid",
      "the bank's engine, under a fit warrant"],
     ["Kind / procedure", "calibration_set / calibrate", "class T1, derived"],
     ["Cadence", "every morning", "250 parameter sets, one approved kernel"]],
    ("A set per business day",
     "provenance = calibrated: the numbers reproduce a market rather than "
     "summarise a history, and every downstream reader branches on that."),
    ("Approved by envelope",
     "A published, versioned, case-tested policy accepts what fits and holds "
     "what does not. A gate with no refusing case is refused at publication."),
    ("Residuals, not accuracy",
     "There is no label to wait for. A climbing RMSE means the one-factor "
     "form is running out of grid -- a model finding, not a bad day."),
    lead="Nobody approves 250 calibrations a year. ",
    rest="Somebody approves the envelope once and looks at the eleven days it "
         "was breached. That is what 'recording new parameters is not a new "
         "model version' buys operationally -- and why calibrated is its own "
         "class rather than a kind of training.")

# --------------------------------------------------------------- Monte Carlo
model_slide(
    "A Monte Carlo engine - the seed is a parameter", "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "parameters, seed, path count, scheme, antithetic flag",
      "the parameter register, as values"],
     ["Filled by", "calibration plus deliberate configuration",
      "the bank's engine, under a fit warrant"],
     ["Kind / procedure", "calibration_set / calibrate", "class T1, derived"],
     ["Claim checked", "deterministic = true",
      "L-W5: refused if no seed is bound"]],
    ("Configuration is in P",
     "Paths, seed, scheme and antithetic each change the answer. If they are "
     "not in P they are not in the digest, the warrant or the replay."),
    ("Standard error is reviewed",
     "A Monte Carlo answer is an estimate with an interval. The convergence "
     "study attaches to the parameter set as evidence with an author."),
    ("The verb is simulate",
     "Drawing from the output distribution is a different operation from "
     "scoring. A warrant for score will not simulate."),
    lead="Eleven thousand tests could not catch it. ",
    rest="An engine reseeded per request instead of once at start-up passed "
         "every single-trade valuation, because a single valuation averages "
         "over paths either way. What changed was the correlation BETWEEN "
         "valuations in a netting set. No number of tests of that shape would "
         "have found it: every element of the suite had length one.")

# ------------------------------------------------------------ neural network
model_slide(
    "A neural network - where P becomes an artifact", "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "about 20 million weights",
      "data/artifacts/9f/2c/9f2c... - the file's name IS its sha256"],
     ["Filled by", "a training run, outside MAYA",
      "exported to onnx or safetensors, then uploaded"],
     ["Kind / procedure", "learned_weights / train", "class T3, derived"],
     ["Runtime", "onnx", "digest verified before the graph is loaded"]],
    ("Content-addressed bytes",
     "Same weights twice stores once; an artifact cannot be edited in place, "
     "because edited bytes are a different address."),
    ("Retraining is a new version",
     "The artifact is P and is also the graph. The old artifact stays, so a "
     "replay of last March still finds the file that made the decision."),
    ("The warrant says what it is",
     "Format, size, executes_on_load, held_by_maya and a fetch path. An "
     "engine holding the warrant needs nothing else."),
    lead="Two formats execute code when they load. ",
    rest="torchscript and tar carry code, so they load in the sandbox and "
         "nowhere else; onnx, safetensors, pmml, pfa, json and gguf do not. "
         "The list is closed and there is no pickle -- 'we will work it out at "
         "load time' is how a pickle gets deserialised in a control plane.")

# --------------------------------------------------------------------- LLM
model_slide(
    "An LLM application - where P is an assembly you configured",
    "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "base model, prompt, corpus version, tools, decoding, guardrails",
      "the register, plus artifacts for prompt and corpus"],
     ["Filled by", "configuration and retrieval, not fitting",
      "provenance = declared: somebody chose these"],
     ["Kind / procedure", "llm_configuration / configure", "class T5, derived"],
     ["Runtime", "llm.prompt, or llm.agent if it acts",
      "stochastic: a determinism claim is refused"]],
    ("The prompt is an artifact",
     "Stored, hashed, named by hash. A prompt edited in a config file is a "
     "model change that left no trace, and this is where that stops."),
    ("The base model moves",
     "Provider version is in P, so a gateway upgrade no longer matches the "
     "recorded configuration -- a finding, not a silent change."),
    ("Output is drafted, not decided",
     "Held until a person attests it, ungrounded claims dropped first, and a "
     "sample of accepted drafts pulled for review regardless."),
    lead="Self-hosting turns this back into the previous slide. ",
    rest="The checkpoint goes into the artifact store as safetensors or gguf, "
         "addressed by its hash, and held_by_maya becomes true. The 8 GiB cap "
         "is deliberate: a governance platform is not a model store of last "
         "resort. An adapter is a different matter -- a LoRA is small, and it "
         "IS the thing you trained.")

# ------------------------------------------------------------- what it proves
sl, y = content("What did not have to change", "Every kind of model")
outs = [("One definition, seven media",
         "f : P (x) X -> D(Y) took a closed-form pricer, a daily calibration, "
         "a 20-million-weight network and a prompt assembly without a "
         "special case in the register."),
        ("The class is derived, not declared",
         "Nobody self-reported 'is this trained?'. The class falls out of how "
         "P is inhabited, which is a fact about the artifact rather than an "
         "opinion about it."),
        ("The unit of change follows the medium",
         "Values refit into a new parameter set; an artifact refits into a new "
         "version. That is a consequence of the medium, not a policy choice."),
        ("Warrants did not fork",
         "One grammar, four vocabularies. simulate and generate are verbs it "
         "already had, and the laws that check them are the same laws."),
        ("Evidence is uniform",
         "The same append-only chain records a calibration, a training run and "
         "a drafted paragraph, so one query answers 'what happened to this "
         "model' across all of them."),
        ("The seventh one fitted without a redesign",
         "Which is the only evidence for the definition that counts. A "
         "taxonomy that needs a new branch per model family is a list.")]
cw2 = (CW - 0.30 * 2) / 3
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 3) * (cw2 + 0.30), y + (i // 3) * 2.30, cw2, 2.10,
         f"0{i+1}", t, d)
