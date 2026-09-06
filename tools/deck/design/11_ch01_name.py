# ============================================================ CH 1
# The chapter divider is gone. It was 27-47 words of "IN THIS CHAPTER" bullets
# restating the titles of the four slides immediately after it, and the part
# divider already lists the chapters. What the divider actually carried was the
# footer's chapter name, so that is set here directly.
_state["chapter"] = "1 · The Name, and What It Is For"

# ------------------------------------------------------------ the word
sl, y = content("māyā — appearance, not illusion", "Philosophy · the name")
tf = txt(sl, ML, y, CW * 0.54, 3.4)
para(tf, "माया", size=44, color=CRIMSON, font=SERIF, first=True, space_after=12)
para(tf, "In Indian philosophy, māyā is the representation that stands in for "
         "reality. The usual translation — “illusion” — is too strong. Māyā is "
         "not falsehood: it is a RENDERING of the world, useful, often "
         "necessary, and dangerous only when you forget that it is a rendering.",
     size=13, color=INK, space_after=10, line=1.3)
para(tf, "Which is what a model is — and the supervisory guidance says so in "
         "almost the same words.",
     size=13, color=INK, space_after=0, line=1.3)

x = ML + CW * 0.58
quote(sl, x, y + 0.15, CW * 0.42,
      "“Models are simplified representations of real-world relationships… "
      "based on assumptions that make them useful in estimating values and "
      "predicting events, but which also can have limitations and create model "
      "risk.”",
      "SR 26-2, §III")
note(sl, x, y + 1.75, CW * 0.42, 1.35,
     "Model risk is what happens when an organisation forgets the difference "
     "between the map and the territory. ",
     "The platform is named for the thing it governs.")

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
     "The argument it makes is that error is not a defect to be eliminated but "
     "a quantity to be known.")

data = [["What the estate assumes", "What the figure says"],
        ["a validated model is correct", "it is wrong by a knowable amount"],
        ["more data closes the gap", "more sides close it and never to zero"],
        ["the model IS the risk", "the risk is forgetting it is a model"]]
th = table(sl, data, x, y + 1.60, CW * 0.44, col_w=[2.6, 2.74],
           row_h=0.34, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)

# The four-card slide that used to follow is gone. Two of its cards — the gap
# is measured, and nobody is asked to believe — are the first and second of the
# five positions in chapter 3, stated twice. The two that were not restated
# there are kept, here, in the space the table left.
note(sl, x, y + 1.60 + th + 0.28, CW * 0.44, 1.75,
     "What naming it that commits the platform to. ",
     "A rendering gets replaced, so versions are immutable and a governed "
     "alias — #champion, pointing at whichever version is approved today — "
     "carries the name instead. And it applies to MAYA itself: the platform is "
     "a representation of an estate, so its own documentation is compiled from "
     "the register rather than written, and the map of the maps cannot drift "
     "either.")
