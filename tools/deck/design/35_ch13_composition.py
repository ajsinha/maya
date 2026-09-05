# ============================================================ CH 13
divider("13", "How Things Compose",
        "Features compose. Featuresets compose. Models compose — by one "
        "relation that is type-checked rather than asserted.",
        ["Five relations, two that propagate", "input_to is a type claim",
         "Blast radius and shared dependency", "Why aggregate risk cannot add up"])

# ------------------------------------------------------------- relations
sl, y = content("Five relations, and the two that carry consequence",
                "Composition · the vocabulary")
data = [["Relation", "Means", "Propagates", "Type-checked"],
        ["derives_from", "built from it: a variant, a recalibration for another "
                         "book. Lineage, not dependency", "no", "no"],
        ["input_to", "this model's OUTPUT is read as an input by that one",
         "YES", "YES"],
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
sl, y = content("An edge between models is type-checked",
                "Composition · the one that composes")
tf = txt(sl, ML, y, CW * 0.54, 3.4)
para(tf, "input_to is a claim about types.", size=13, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=10)
para(tf, "A's output is read as an input by B — a discount curve into a pricer, "
         "a PD model into an ECL stack. The claim is that whatever A produces "
         "arrives where B reads it.",
     size=12, color=INK, space_after=9, line=1.28)
para(tf, "MAYA moves no data and runs no model. The edge is a statement about "
         "two entries in the REGISTER, and the wire it describes is carried by "
         "whichever engine runs the two ends.",
     size=12, color=INK, space_after=9, line=1.28)
para(tf, "Which is why it can be checked at all: the check is on two declared "
         "schemas, not on a pipeline this platform does not operate.",
     size=11, color=SLATE, space_after=0, line=1.28)

x = ML + CW * 0.58
h = code(sl, x, y, CW * 0.42, [
    "refines( output_schema(source),",
    "         input_schema(target) )",
    "",
    "# extra outputs      → fine, simply unread",
    "# a missing output   → a wire to nowhere: refused",
    "# a narrowed output  → the same failure L-12",
    "#                      names at an alias move",
], fs=9.5, title="L-21 · THE CHECK")
note(sl, x, y + h + 0.28, CW * 0.42, 1.6,
     "An edge nobody checks is an opinion. ",
     "A blast radius over it follows dependencies that may not exist, and a "
     "chain of models has no schema anybody can derive. Checked, the composite's "
     "type is ",
     "DERIVED rather than declared.")

# -------------------------------------------------------- what it answers
sl, y = content("Two questions this makes answerable",
                "Composition · what it is for")
x1, x2 = ML, ML + CW * 0.52
tf = txt(sl, x1, y, CW * 0.46, 3.2)
para(tf, "What breaks if I change this?", size=13, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=9)
para(tf, "Only propagating edges are followed, and each model comes back with "
         "its DISTANCE — so the immediately affected are visible separately "
         "from those two hops away.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "The worst tier reached is reported too. A change touching one Tier 1 "
         "model is not the same as one touching five Tier 4s, and a count alone "
         "cannot tell you which happened.",
     size=11, color=SLATE, space_after=0, line=1.26)

tf = txt(sl, x2, y, CW * 0.46, 3.2)
para(tf, "What do these two rest on in common?", size=13, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=9)
para(tf, "Two models fed by the same curve are "
         "NOT two independent risks — and a network that copies a dependency is "
         "not the same as one that duplicates it.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "That difference is precisely why an aggregate risk figure cannot "
         "simply add up, and why supervisors ask about “common dependencies and "
         "shared assumptions”. Here it has an answer instead of a paragraph.",
     size=11, color=SLATE, space_after=0, line=1.26)

note(sl, ML, y + 3.45, CW, 1.15,
     "A cycle is refused. ",
     "A model whose output is its own input has no defined value, and a blast "
     "radius over it does not terminate — so the edge that would close the cycle "
     "is the one that is refused, naming the path that already exists.")

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
para(tf, "A theorem arriving as a product decision rather than a footnote.",
     size=11, color=INK, space_after=0, line=1.26)
