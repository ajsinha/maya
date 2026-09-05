# ============================================================ CH 5
divider("5", "The Algebra",
        "One order for five questions, one fold for two levels, and the laws "
        "that make both checkable.",
        ["Four implementations of one relation", "Schemas as a lattice",
         "The fold, and what it buys", "Independent edits commute"])

# ------------------------------------------------- the problem it solves
sl, y = content("Four places asked one question, four different ways",
                "The algebra · why")
data = [["Where", "What it asked", "How it answered"],
        ["An alias move", "is the replacement version substitutable?",
         "substitutable() in core/domain/schemas.py"],
        ["A fit warrant", "does the featureset provide what the kernel reads?",
         "a hand-written loop over the fields"],
        ["An operating contract", "does the new boundary a version is valid "
         "in refine the old one?",
         "refines() in core/domain/contracts.py"],
        ["A dependency edge", "does the source's output arrive where the target reads?",
         "IT DID NOT ASK"]]
th = table(sl, data, ML, y, CW, col_w=[2.6, 4.6, 4.434],
           row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.15,
     "Four implementations of one relation disagree eventually. ",
     "And the direction is predictable: toward PERMITTING MORE, because that "
     "is the direction in which nobody files a bug. The fourth row is the "
     "worst — a dependency graph whose edges were never checked. So the "
     "relation is written once, and everything now asks it.")

# ------------------------------------------------------------- the order
sl, y = content("A ⊑ B — “A can stand in for B”", "The algebra · the order")
h = code(sl, ML, y, CW * 0.54, [
    "A ⊑ B   iff   A has every field B has,",
    "              each accepting AT LEAST what B's accepted",
    "",
    "# a slot is one named field of a schema",
    "# extra fields in A are fine — they are simply not read",
], fs=10.5, title="core/domain/lattice.py")

note(sl, ML, y + h + 0.28, CW * 0.54, 1.35,
     "The direction surprises people. ",
     "A subtype is usually the NARROWER thing, so “A refines B” sounds as "
     "though A should accept less. It is the other way round: to stand in for "
     "B, A must accept everything B accepted.")

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 0.4)
para(tf, "It is a lattice", size=13, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=10)
rows = [("meet  A ⊓ B",
         "the UNION of the fields, widened to accept both — what a featureset "
         "must provide to serve two models at once"),
        ("join  A ⊔ B",
         "the INTERSECTION, narrowed to what both accepted — what a consumer of "
         "either may rely on"),
        ("top",
         "the empty schema: it demands nothing, so everything can stand in for it")]
yy = y + 0.50
for name, meaning in rows:
    tf = txt(sl, x, yy, CW * 0.42, 0.9)
    para(tf, name, size=10.5, color=INK, bold=True, font=MONO, first=True,
         space_after=3)
    para(tf, meaning, size=9.5, color=SLATE, space_after=0, line=1.2)
    yy += 1.00

note(sl, x, yy + 0.05, CW * 0.42, 1.35,
     "Meet is PARTIAL, informatively. ",
     "Two schemas whose shared field carries two different types have no "
     "meet. The honest answer to “can one featureset serve both these models” "
     "is then no, with the field named.")

# ---------------------------------------------------------- what it unified
sl, y = content("One relation, five questions", "The algebra · what it unified")
data = [["Question", "Answered by", ""],
        ["Does this featureset provide what the kernel reads?  (L-W10)",
         "refines(resolved, kernel_inputs)", ""],
        ["Is the replacement version substitutable?  (L-12)",
         "the same refines()", ""],
        ["Is this child a refinement of its parent?", "A ⊑ B", "new"],
        ["What must a featureset provide to serve both models?", "their meet",
         "new"],
        ["What do two versions agree on?", "their join", "new"]]
th = table(sl, data, ML, y, CW, col_w=[5.4, 5.0, 1.234],
           row_h=0.34, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.30,
     "L-20 states the structure, and the test asserts it over generated "
     "schemas. ",
     "Partial order, meet below both, join above both, idempotence, "
     "commutativity, associativity, absorption — and the link A ⊑ B ⟺ A ⊓ B = A "
     "that makes it a lattice ORDER rather than an order and two unrelated "
     "operations. The three marked new could not be asked at all before, and "
     "all three are questions a practitioner asks out loud in a meeting.")

# -------------------------------------------------------------- the fold
sl, y = content("One fold, at two levels", "The algebra · composition")
h = code(sl, ML, y, CW * 0.56, [
    "compose([a, b, c])  =  merge(merge(a, b), c)",
    "                       then the child's own add / drop / override",
    "",
    "# left to right, RIGHTMOST WINS, {} the identity",
    "# a monoid: an identity, and grouping that does not matter  (L-19)",
], fs=10.5, title="core/features/composition.py")

tf = txt(sl, ML, y + h + 0.30, CW * 0.56, 2.4)
para(tf, "Three things a monoid buys", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=8)
for item in [
    "Order of GROUPING does not matter, so “which order did we build this in” "
    "stops being a question with a consequence.",
    "Precedence is a PROPERTY rather than a preference: leftmost is least "
    "prominent, so a child of three parents has one answer rather than three.",
    "“A combination of features is a feature” becomes a statement about the "
    "fold, which is why features and featuresets share one mechanism.",
]:
    runs(tf, [("→  ", CRIMSON, True), (item, SLATE, False)], size=10, space_after=7)

x = ML + CW * 0.60
data = [["Edit a child may make", "Refused when"],
        ["add", "the member already exists — say override"],
        ["drop", "no parent has it"],
        ["override", "no parent has it — say add"]]
th = table(sl, data, x, y, CW * 0.40, col_w=[1.9, 3.44],
           row_h=0.32, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + th + 0.28, CW * 0.40, 1.5,
     "None of the three is idempotent, deliberately. ",
     "An operation that silently did nothing is one somebody believes happened, "
     "and the child then differs from what its author wrote with nothing to "
     "show for it.")

# ----------------------------------------------------------- commutation
sl, y = content("Independent edits commute",
                "The algebra · what two editors rely on")
h = code(sl, ML, y, CW * 0.56, [
    "op₁ · op₂  =  op₂ · op₁      whenever they name DIFFERENT members",
    "",
    "drop(x) · add(x, τ)             =  id",
    "override(x, σ) · override(x, τ) =  override(x, σ)",
], fs=10.5, title="L-20")
note(sl, ML, y + h + 0.30, CW * 0.56, 1.75,
     "This is what two people editing a shared featureset rely on. ",
     "If independent edits commute, the order their edits happened to arrive in "
     "carries no meaning. That is the difference between a merge and a conflict "
     "whose resolution is itself a decision nobody recorded — and it is not a "
     "property one edit at a time can demonstrate.")

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.4)
para(tf, "What is NOT claimed", size=12.5, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=9)
para(tf, "Dependent edits are deliberately not claimed to commute.",
     size=11, color=INK, space_after=8, line=1.25)
para(tf, "override then drop of the same field is not drop then override — "
         "the second order is refused outright. A law stated more widely than "
         "it holds is a law somebody will rely on where it does not.",
     size=10.5, color=SLATE, space_after=0, line=1.28)
