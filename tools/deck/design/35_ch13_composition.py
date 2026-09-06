# ============================================================ CH 13
_state["chapter"] = "13 · How things compose"

# ------------------------------------------------------------- relations
sl, y = content("Five relations, and the two that carry consequence",
                "Composition · the vocabulary")
data = [["Relation", "Means", "Propagates", "Type-checked"],
        ["derives_from", "built from it: a variant, a recalibration for another "
                         "book. Lineage, not dependency", "no", "no"],
        ["input_to", "this model's OUTPUT is read as an input by that one",
         "YES", "YES \u2014 or flagged unchecked"],
        ["calibrated_by", "its parameters are solved by that model or procedure",
         "yes", "no — no wire"],
        ["challenger_of", "built to argue with it", "no", "no"],
        ["benchmark_for", "a reference point to judge it against", "no", "no"]]
th = table(sl, data, ML, y, CW, col_w=[2.1, 6.2, 1.6, 1.734],
           row_h=0.36, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 1.55,
     "The first two are the ones people conflate, and it costs both answers. ",
     "“What did we base this on” and “what breaks if this changes” are different "
     "questions. A challenger counted as a dependency inflates every blast "
     "radius — the set of models a change reaches — it appears in; a variant counted as one makes a change to the "
     "parent look like a change to a book it never touched.")

# --------------------------------------------------------------- the check
# Two slides, merged. "Two questions this makes answerable" spent half a slide
# on shared dependency, which is the whole of the slide after this one; what it
# had that nothing else did — distance, worst tier reached, the cycle refusal —
# is a note.
sl, y = content("An edge between models is type-checked",
                "Composition · the one that composes")
# The rule as it now stands. It used to ask whether the source's output could
# stand in for the target's ENTIRE input, which refused the ordinary case: a PD
# model feeding an ECL stack that also reads LGD, EAD and a discount curve was
# refused "PD does not provide lgd".
h = code(sl, ML, y, CW * 0.54, [
    "shared = the names output(A) and input(B) have in common",
    "refines( output(A),  input(B) restricted to shared )",
    "",
    "# shared is empty        \u2192 a wire to nowhere: refused",
    "# a shared field clashes \u2192 refused, and it names the field",
    "# B reads more besides   \u2192 fine: another edge carries it,",
    "#                          or the caller supplies it",
    "# either end unversioned \u2192 recorded, type_checked = 0",
], fs=9.5, title="L-21 \u00b7 THE CHECK")
note(sl, ML, y + h + 0.28, CW * 0.54, 1.42,
     "At least one shared field, and every shared field type-checks. ",
     "Asking the source to satisfy the whole of the target\u2019s input refused "
     "the ordinary shape of a model network and admitted only the degenerate "
     "case where a model reads nothing but its predecessor. What B reads from "
     "elsewhere is not this edge\u2019s business \u2014 ",
     "and the composite\u2019s schema now says what the caller must still supply.")

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 4.0)
para(tf, "input_to is a claim about types.", size=13, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=9)
para(tf, "A\u2019s output is read as an input by B \u2014 a discount curve into "
         "a pricer, a PD model into an ECL stack. MAYA moves no data and runs "
         "no model: the edge is a statement about two entries in the REGISTER, "
         "which is exactly why it can be checked at all.",
     size=11, color=INK, space_after=9, line=1.26)
para(tf, "And where it could not be checked, it says so.", size=12,
     color=CRIMSON, bold=True, font=SERIF, space_after=8)
para(tf, "An edge either end of which has no version yet is recorded with the "
         "type check SKIPPED \u2014 you cannot always add models in dependency "
         "order \u2014 and carries type_checked = 0 to say which kind it is.",
     size=11, color=INK, space_after=9, line=1.26)
para(tf, "Until that flag it was indistinguishable from a checked edge, and "
         "travelled through blast radius as though somebody had validated it: a "
         "control reporting success it had not performed. So \u201ca dependency "
         "edge type-checks or does not exist\u201d is overstated, and the flag "
         "is what makes the exception visible.",
     size=10.5, color=SLATE, space_after=0, line=1.26)

note(sl, ML, y + h + 0.28 + 1.42 + 0.26, CW, 0.88,
     "What the edge makes answerable. ",
     "A blast radius follows only the propagating edges and returns each model "
     "with its DISTANCE, so the immediately affected are separable from those "
     "two hops away, and with the worst TIER reached \u2014 one Tier 1 model is "
     "not five Tier 4s. A cycle is refused at the edge that would close it, "
     "naming the path that already exists.")

# -------------------------------------------------- why it cannot add up
sl, y = content("Why there is no single model-risk number",
                "Composition · the impossibility")
h = code(sl, ML, y, CW * 0.54, [
    "Network 1:   A ──→ B          one curve, two consumers",
    "             A ──→ C",
    "",
    "Network 2:   A  ──→ B         two INDEPENDENTLY BUILT curves",
    "             A' ──→ C",
    "",
    "# every marginal is identical.  the joints are not.",
], fs=10, title="TWO NETWORKS, IDENTICAL PARTS")
note(sl, ML, y + h + 0.30, CW * 0.54, 1.85,
     "No function of the parts distinguishes these. ",
     "Aggregating requires the parts to compose, and shared dependency is "
     "exactly where composition fails: copying a dependency is not duplicating "
     "it, and no rule that reads models one at a time can tell. Any single "
     "figure either "
     "double-counts the shared curve or ignores it, and a committee cannot "
     "decompose it to find out which.")

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 3.6)
para(tf, "So the board pack refuses to produce one", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=9)
para(tf, "And says so IN the pack, rather than leaving an absence — a reader "
         "who came looking for the number finds the reason instead.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "What it reports is the indicators, each against a limit somebody set, "
         "with the exceptions named. That is what a committee can act on; a "
         "number they cannot decompose is a number they cannot act on.",
     size=11, color=SLATE, space_after=8, line=1.26)
runs(tf, [("What it does answer is the supervisor\u2019s actual question",
           CRIMSON, True),
          (" \u2014 \u201ccommon dependencies and shared assumptions\u201d "
           "\u2014 model by model, as a list rather than a paragraph.",
           SLATE, False)],
     size=11, space_after=8, line=1.26)
para(tf, "A theorem arriving as a product decision rather than a footnote.",
     size=11, color=INK, space_after=0, line=1.26)
