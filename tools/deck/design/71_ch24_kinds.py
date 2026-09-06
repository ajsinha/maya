# ============================================================ CH 24
_state["chapter"] = "24 · Every Kind of Model"

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
sl, y = content("Eight shapes of the same definition",
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
        ["Rule set", "ordered rules, first match wins",
         "somebody wrote them down", "rule_set", "author", "T8"],
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
        ["A document", "tens of rules", "the register, as a parsed tree",
         "a new parameter set", "the canonical form, re-digested"],
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

# ------------------------------------------------- where P is a record
sl, y = content("Where P is a record — an estimate, a calibration, and a seed",
                "Every kind of model")
data = [["Model", "P is", "Filled by", "Kind · class", "What review reads first"],
        ["Linear regression", "an intercept and two slopes",
         "ordinary least squares, in MAYA's estimator",
         "estimated_coefficients · T2",
         "the condition number, before the R-squared"],
        ["GARCH / ARIMA", "omega, alpha, beta",
         "maximum likelihood; an unconverged fit is refused",
         "estimated_coefficients · T2",
         "convergence, and alpha + beta < 1, enforced while solving"],
        ["Hull-White", "mean reversion, a term structure of sigma",
         "a solver against the swaption grid, one set a morning",
         "calibration_set · T1",
         "the residuals - there is no label to wait for"],
        ["Monte Carlo XVA", "parameters, seed, paths, scheme, antithetic",
         "calibration plus deliberate configuration",
         "calibration_set · T1",
         "the standard error, and any determinism claim"]]
th = table(sl, data, ML, y, CW, col_w=[1.7, 2.4, 3.2, 2.1, 2.6],
           row_h=0.24, fs=8.5, hfs=9, bold_col0=True, first_col_color=CRIMSON)
cy = y + th + 0.22
cw2 = (CW - 0.28 * 2) / 3
for kick, head, body in [
        ("SAVES", "Values, digested",
         "Rows in the parameter register. The digest is re-derived from the "
         "values at resolve time, never compared against a stored copy of itself."),
        ("MANAGES", "One review, or one envelope",
         "Where sets are rare, each is approved by somebody who did not record "
         "it. Where there are 250 a year, a versioned, case-tested envelope "
         "accepts what fits and holds what does not - and a gate with no "
         "refusing case is refused at publication."),
        ("SERVES", "The warrant names the set",
         "The descriptor carries the parameter set id and digest. An artifact "
         "binding would be a false statement, since there is no artifact.")]:
    i = ["SAVES", "MANAGES", "SERVES"].index(kick)
    card(sl, ML + i * (cw2 + 0.28), cy, cw2, 1.62, kick, head, body,
         title_size=12, body_size=9)
aside(sl, ML, cy + 1.76, CW,
      "An estimate and a calibration differ in what the numbers are for, not in the mathematics. ",
      "An estimate summarises a history; a calibration reproduces a market, and "
      "provenance says which - so calibrated is its own class rather than a kind "
      "of training, and nobody approves 250 calibrations a year. The captive "
      "engine implements ols and garch11 only: fit the rest in your own engine, "
      "deliver the parameters back under the warrant, and none of the governance "
      "changes.")

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

# ---------------------------------------------------------------- rule set
model_slide(
    "An authored rule set - where P is a document somebody wrote",
    "Every kind of model",
    [["", "What it is", "Where it lands"],
     ["P", "ordered rules, first match wins, a stated otherwise",
      "the parameter register, as a parsed document"],
     ["Filled by", "authorship - nothing was fitted",
      "provenance = declared: somebody wrote these"],
     ["Kind / procedure", "rule_set / author", "class T8, derived"],
     ["Runtime", "rules", "a condition is a tree, not an expression string"]],
    ("The parsed form is what is digested",
     "Reformatting the document is not a new parameter set. Reordering the "
     "rules is, because first match wins and order is meaning."),
    ("Approved like any other P",
     "By somebody other than the author. Every rule carries a because - a rule "
     "with no stated reason cannot be defended, reviewed, or retired later."),
    ("A refusal no spreadsheet gives you",
     "A rule an earlier rule already covers can never fire. Publishing is "
     "refused: rule_unreachable, naming the rule that shadows it."),
    lead="A rule that never fires never produces a wrong answer. ",
    rest="It appears in the model card, gets cited in a committee paper and "
         "survives every review - a control reporting success while doing "
         "nothing. The analysis is deliberately sound and incomplete: it calls "
         "a rule unreachable only when a SINGLE earlier rule covers it, because "
         "a check that cries wolf is a check somebody turns off.")
