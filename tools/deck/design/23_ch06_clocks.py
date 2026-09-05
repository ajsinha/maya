# ============================================================ CH 6
divider("6", "Two Clocks",
        "When a fact was true, when it became known — and the read that keeps "
        "them apart.",
        ["Why one clock cannot answer", "The as-of operator",
         "Four properties, one of which is reproducibility",
         "Alignment, and hiding nothing"])

# --------------------------------------------------------- why two clocks
sl, y = content("Every fact has two timestamps, and one of them is skipped",
                "Two clocks · the problem")
data = [["", "event_ts", "ingest_ts"],
        ["Answers", "when the fact was TRUE",
         "when it became KNOWN to us"],
        ["For a Q1 ratio", "31 March — the period it describes",
         "20 May — when they filed"],
        ["A restatement", "unchanged: still about Q1",
         "August — when the revision arrived"],
        ["Dropped by", "nobody", "almost every feature store"]]
th = table(sl, data, ML, y, CW, col_w=[2.1, 4.7, 4.834],
           row_h=0.34, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)

y2 = y + th + 0.32
h = code(sl, ML, y2, CW * 0.54, [
    "# the borrower revises Q1 downward, in August",
    "  event 31-Mar   ingest 20-May    dscr 1.20     ← what we knew in May",
    "  event 31-Mar   ingest 20-Aug    dscr 0.40     ← the restatement",
    "",
    "# building a training row for a decision made in MAY",
    "  one clock  →  0.40    (it is the current value for Q1)",
    "  two clocks →  1.20    (0.40 was not knowable in May)",
], fs=9.5, title="THE CASE THIS EXISTS FOR")
note(sl, ML + CW * 0.58, y2, CW * 0.42, h,
     "Train on 0.40 and the model learns to predict defaults from a number that "
     "exists BECAUSE the default already happened. ",
     "It scores beautifully in backtest and fails in production, and the failure "
     "looks like drift rather than what it is.")

# ------------------------------------------------------------ the operator
sl, y = content("The read, named as an operator", "Two clocks · AsOf")
h = code(sl, ML, y, CW * 0.56, [
    "AsOf(R, ℓ, a) =",
    "    argmax over (event_ts, ingest_ts) of",
    "    { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }",
    "",
    "#  ℓ  the label's moment — what the model could have known",
    "#  a  the assembly's as_of — what the PLATFORM could have known",
], fs=10, title="core/features/assembly.py")
note(sl, ML, y + h + 0.28, CW * 0.56, 1.9,
     "Both bounds, because they refuse different things. ",
     "`ℓ` is what the model could have known when the decision was made. `a` is "
     "what the platform could have known when the set was built, so a "
     "restatement arriving after assembly cannot creep into a re-run. Dropping "
     "either one admits a different leak, and the second is the one people drop.")

x = ML + CW * 0.60
data = [["Property", "Says"],
        ["Idempotent", "reading the result again returns it"],
        ["Commutes with projection",
         "the choice is made on the clocks alone, so fewer columns cannot change it"],
        ["Monotone in a",
         "a later read can only WIDEN what is admissible"],
        ["Saturating at ℓ", "every a ≥ ℓ gives the SAME ANSWER"]]
th = table(sl, data, x, y, CW * 0.40, col_w=[1.85, 3.49],
           row_h=0.30, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + th + 0.26, CW * 0.40, 0.6)
para(tf, "L-10 · tests/test_laws.py", size=9.5, color=MUTED, bold=True,
     font=MONO, first=True, space_after=0)

# ------------------------------------------------------------- saturation
sl, y = content("The fourth one is the reproducibility guarantee",
                "Two clocks · why min(ℓ, a) matters")
steps(sl, ML, y, CW, [
    ("01", "Assemble in May", "the row for a decision labelled in May reads "
                              "dscr = 1.20, the value knowable then"),
    ("02", "A restatement arrives", "August: the same Q1 figure, revised to "
                                    "0.40. Both rows are true and both stay"),
    ("03", "Re-assemble a year later", "the ingest bound is min(label, as_of), "
                                       "so it saturates at the label"),
    ("04", "The answer is identical", "1.20 — however many restatements arrived "
                                      "between, and however long ago it was"),
], h=1.75)
note(sl, ML, y + 2.05, CW, 1.55,
     "Without the min, a re-run quietly IMPROVES on the original. ",
     "That is the least useful kind of reproducibility: the numbers then agree "
     "with nothing, including themselves — a validator replaying a decision gets "
     "a better answer than the one that was made, cannot tell that is what "
     "happened, and reports agreement. The bound is one function call and it is "
     "the whole guarantee.")

# ------------------------------------------------------------- alignment
sl, y = content("Alignment: three of the five rules reach into the future",
                "Two clocks · and hiding nothing")
data = [["Rule", "Fills from", "Point-in-time safe"],
        ["none", "nothing", "yes"],
        ["flat_forward", "the last observation", "yes"],
        ["flat_backward", "the NEXT observation", "no"],
        ["linear", "both neighbours", "no"],
        ["nearest", "whichever is closer", "no"]]
th = table(sl, data, ML, y, CW * 0.52, col_w=[1.6, 2.9, 2.44],
           row_h=0.32, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)

x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 3.6)
para(tf, "They are not refused. They are stamped.", size=13, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=9)
para(tf, "Back-filling is the right answer for drawing a curve, for an "
         "explicitly retrospective backtest, for showing a history to a person "
         "— and wrong for training. Refusing it would push it into a "
         "spreadsheet where nothing can see it.",
     size=11, color=INK, space_after=9, line=1.26)
para(tf, "So a value carried backwards inherits the LATER observation's "
         "ingest_ts, because that is genuinely when it became knowable. An "
         "ordinary point-in-time read then excludes it, with nobody having to "
         "remember a flag.",
     size=11, color=INK, space_after=9, line=1.26)
para(tf, "The leakage is not caught by a check. It is made arithmetically "
         "impossible to hide.",
     size=11.5, color=CRIMSON, bold=True, space_after=0, line=1.26)

note(sl, ML, y + th + 0.30, CW * 0.52, 1.4,
     "Two bounds finish it. ",
     "A CARRY LIMIT bounds how far an observation may travel — a balance from "
     "eighteen months ago is not this month's balance. And interpolation will "
     "not EXTRAPOLATE from one side under the name of interpolating: a different "
     "act, with a different error, and doing it silently would hide which was "
     "done.")
