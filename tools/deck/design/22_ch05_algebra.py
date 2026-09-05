# ============================================================ CH 5
divider("5", "The Algebra",
        "One order for four questions, one fold for two levels, and the laws "
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
         "a hand-written slot loop"],
        ["An operating contract", "does the new contract refine the old one?",
         "refines() in core/domain/contracts.py"],
        ["A dependency edge", "does the source's output arrive where the target reads?",
         "IT DID NOT ASK"]]
th = table(sl, data, ML, y, CW, col_w=[2.6, 4.6, 4.434],
           row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.25,
     "Four implementations of one relation disagree eventually. ",
     "And the direction is predictable: toward PERMITTING MORE, because that is "
     "the direction in which nobody files a bug. The fourth row is the worst of "
     "them — a dependency graph whose edges were never checked, followed by a "
     "blast radius that trusted them. So the relation is written once, and "
     "everything that used to ask its own version of the question now asks it.")

# ------------------------------------------------------------- the order
sl, y = content("A ⊑ B — “A can stand in for B”", "The algebra · the order")
h = code(sl, ML, y, CW * 0.54, [
    "A ⊑ B   iff   A has every field B has,",
    "              each accepting AT LEAST what B's accepted",
    "",
    "# extra fields in A are fine — they are simply not read",
    "# a NARROWER acceptance is the regression, not a wider one",
], fs=10.5, title="core/domain/lattice.py")

note(sl, ML, y + h + 0.28, CW * 0.54, 1.55,
     "The design note had this backwards. ",
     "It said a refinement is “at a type no wider”, written from the intuition "
     "that a subtype is narrower. Standing in for something requires accepting "
     "at least what it accepted. The `accepts` relation in the code had it right "
     "all along, and writing the implementation found the error in the prose — "
     "which is the ordinary direction of that traffic.")

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
     "Two schemas whose shared slot carries two different dtypes have no meet — "
     "no schema accepts both a number and a string in one slot. The honest "
     "answer to “can one featureset serve both these models” is then no, with "
     "the slot named.")

# ---------------------------------------------------------- what it unified
sl, y = content("One relation, four questions", "The algebra · what it unified")
data = [["Question", "Before", "Now"],
        ["Featureset satisfies the kernel  (L-W10)", "a bespoke slot loop",
         "refines(resolved, kernel_inputs)"],
        ["Replacement is substitutable  (L-12)", "accepts_superset_of",
         "the same refines()"],
        ["Is this child a refinement of its parent?", "NOT ASKABLE", "A ⊑ B"],
        ["What must a featureset provide to serve both?", "NOT ASKABLE",
         "their meet"],
        ["What do two versions agree on?", "NOT ASKABLE", "their join"]]
th = table(sl, data, ML, y, CW, col_w=[4.6, 3.4, 3.634],
           row_h=0.34, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.15,
     "L-20, asserted over generated schemas. ",
     "Partial order, meet below both, join above both, idempotence, "
     "commutativity, associativity, absorption — and the link A ⊑ B ⟺ A ⊓ B = A "
     "that makes it a lattice ORDER rather than an order and two unrelated "
     "operations. Two of those four questions could not be asked at all before, "
     "and both are ones a practitioner asks out loud in a meeting.")

# -------------------------------------------------------------- the fold
sl, y = content("One fold, at two levels", "The algebra · composition")
h = code(sl, ML, y, CW * 0.56, [
    "compose([a, b, c])  =  merge(merge(a, b), c)",
    "                       then the object's own operations, last",
    "",
    "# left to right, RIGHTMOST WINS, {} the identity",
    "# associative — asserted, not assumed  (L-19)",
], fs=10.5, title="core/features/composition.py")

tf = txt(sl, ML, y + h + 0.30, CW * 0.56, 2.4)
para(tf, "Three things a monoid buys", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=8)
for item in [
    "Order of GROUPING does not matter, so “which order did we build this in” "
    "stops being a question with a consequence.",
    "Precedence is a PROPERTY rather than a preference: leftmost is least "
    "prominent, so a child of three parents has one answer rather than three.",
    "“A combination of features is a feature” is a STATEMENT — it is the "
    "closure of the fold, and it is why features and featuresets share one "
    "mechanism rather than two.",
]:
    runs(tf, [("→  ", CRIMSON, True), (item, SLATE, False)], size=10, space_after=7)

x = ML + CW * 0.60
data = [["Operation", "Refused when"],
        ["add", "the member already exists — say override"],
        ["drop", "no parent has it"],
        ["override", "no parent has it — say add"]]
th = table(sl, data, x, y, CW * 0.40, col_w=[1.4, 3.94],
           row_h=0.32, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + th + 0.28, CW * 0.40, 1.5,
     "Every operation is total. ",
     "None of the three is idempotent, deliberately: an operation that silently "
     "did nothing is one somebody believes happened, and the child then differs "
     "from what its author wrote with nothing to show for it.")

# ----------------------------------------------------------- commutation
sl, y = content("Independent edits commute — and nobody had checked",
                "The algebra · the law that was missing")
h = code(sl, ML, y, CW * 0.56, [
    "op₁ · op₂  =  op₂ · op₁      whenever they name DIFFERENT members",
    "",
    "drop(x) · add(x, τ)             =  id",
    "override(x, σ) · override(x, τ) =  override(x, σ)",
], fs=10.5, title="L-20 · tests/test_laws.py")
note(sl, ML, y + h + 0.30, CW * 0.56, 2.1,
     "This is what two people editing a shared featureset rely on. ",
     "If independent edits commute, the order their edits happened to arrive in "
     "carries no meaning — the difference between a merge and a conflict whose "
     "resolution is itself a decision nobody recorded. It was never tested, and "
     "a failure here could not have been found by testing one edit at a time.")

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.4)
para(tf, "What is NOT claimed", size=12.5, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=9)
para(tf, "Dependent edits are deliberately not claimed to commute.",
     size=11, color=INK, space_after=8, line=1.25)
para(tf, "override then drop of the same slot is not drop then override — the "
         "second order is refused outright. Stating the law only for "
         "independent edits is the honest form of it, and a law stated more "
         "widely than it holds is a law somebody will rely on where it does "
         "not.",
     size=10.5, color=SLATE, space_after=0, line=1.28)
