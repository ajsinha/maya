# ============================================================ CH 1
divider("1", "The Name, and What It Is For",
        "māyā is appearance: the representation that stands in for reality and "
        "is so easily mistaken for it.",
        ["What the word means", "The mark, and the oldest model there is",
         "Map and territory", "What that commits the platform to"])

# ------------------------------------------------------------ the word
sl, y = content("māyā — appearance, not illusion", "Philosophy · the name")
tf = txt(sl, ML, y, CW * 0.54, 3.4)
para(tf, "माया", size=44, color=CRIMSON, font=SERIF, first=True, space_after=12)
para(tf, "In Indian philosophy, māyā is the representation that stands in for "
         "reality. The usual translation — “illusion” — is too strong.",
     size=13, color=INK, space_after=10, line=1.3)
para(tf, "Māyā is not falsehood. It is a RENDERING of the world: useful, often "
         "necessary, and dangerous only when you forget that it is a rendering.",
     size=13, color=INK, space_after=10, line=1.3)
para(tf, "That is exactly what a model is — and the supervisory guidance says "
         "so in almost the same words.",
     size=13, color=INK, space_after=0, line=1.3)

x = ML + CW * 0.58
quote(sl, x, y + 0.15, CW * 0.42,
      "“Models are simplified representations of real-world relationships… "
      "based on assumptions that make them useful in estimating values and "
      "predicting events, but which also can have limitations and create model "
      "risk.”",
      "SR 26-2, §III")
note(sl, x, y + 1.75, CW * 0.42, 1.7,
     "Model risk is what happens when an organisation forgets the difference "
     "between the map and the territory. ",
     "The platform is named for the thing it governs, and for the discipline of "
     "never mistaking it for the world.")

# -------------------------------------------------------------- the mark
sl, y = content("A square inscribed in a circle", "Philosophy · the mark")
tf = txt(sl, ML, y, CW * 0.52, 3.6)
para(tf, "The oldest model there is.", size=14, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=10)
para(tf, "Archimedes estimated π by inscribing and circumscribing polygons and "
         "tightening the bound as the sides multiplied: a tractable figure "
         "standing in for one that cannot be computed directly.",
     size=12, color=INK, space_after=10, line=1.3)
para(tf, "Which gives the mark its reading:", size=12, color=INK,
     space_after=8, line=1.3)
for lead, rest in [
    ("The gap ", "between the square and the circle is the model error."),
    ("The four points ", "are where the model and the world agree."),
    ("Add sides ", "and the gap closes but never vanishes — no model becomes "
                  "the thing it represents."),
]:
    runs(tf, [("→  ", CRIMSON, True), (lead, INK, True), (rest, SLATE, False)],
         size=11, space_after=7)

x = ML + CW * 0.56
note(sl, x, y, CW * 0.44, 1.35,
     "That is māyā, and it is model risk, in one figure. ",
     "A logo is usually decoration. This one is the argument, and the argument "
     "is that error is not a defect to be eliminated but a quantity to be known.")

data = [["What the estate assumes", "What the figure says"],
        ["a validated model is correct", "it is wrong by a knowable amount"],
        ["more data closes the gap", "more sides close it and never to zero"],
        ["the model IS the risk", "the risk is forgetting it is a model"]]
th = table(sl, data, x, y + 1.60, CW * 0.44, col_w=[2.6, 2.74],
           row_h=0.34, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)

# ------------------------------------------------------ what it commits to
sl, y = content("What naming it that commits the platform to",
                "Philosophy · consequences")
outs = [("The gap is measured, not denied",
         "Every model carries an operating boundary — the domain it was "
         "validated in — and a warrant that runs outside it is refused rather "
         "than answered."),
        ("Representation is versioned",
         "A model is a rendering, and renderings are replaced. Immutable "
         "versions and a governed alias are what let the rendering change "
         "without the thing it renders appearing to."),
        ("Error has a direction",
         "Which is why an overlay register exists: an adjustment is somebody "
         "saying the map is wrong HERE, and that statement is worth keeping."),
        ("Nobody is asked to believe",
         "Evidence, not assertion. Every claim is bound to the artefact it "
         "rests on, because a governance system that asks for trust has "
         "reproduced the problem it was built to solve."),
        ("The word is not a metaphor",
         "It is the definition. A model is a map; governance is knowing the "
         "difference; and every refusal in this platform is an instance of "
         "that sentence."),
        ("And it applies to MAYA itself",
         "The platform is also a representation — of an estate. Its own "
         "documentation is compiled from the register rather than written, so "
         "the map of the maps cannot drift either.")]
cw2 = (CW - 0.30 * 2) / 3
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 3) * (cw2 + 0.30), y + (i // 3) * 2.30, cw2, 2.10,
         f"0{i+1}", t, d)
