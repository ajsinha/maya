# ============================================================ CH 5
_state["chapter"] = "5 · The Algebra"

# ------------------------------------------- the problem, and what it bought
# Two slides, merged. One listed the four places that asked the question and
# the four ways they answered it; the next listed the five questions the single
# relation now answers. They are the same list read forwards and backwards, and
# the "new" column is the only part of either that a reader had to be told
# twice.
sl, y = content("Four implementations of one relation, and what replaced them",
                "The algebra · why, and what it unified")
data = [["The question somebody was asking", "How it used to be answered",
         "Now"],
        ["Is the replacement version substitutable?  (L-12)",
         "substitutable(), in core/domain/schemas.py", "refines()"],
        ["Does the featureset provide what the kernel reads?  (L-W10)",
         "a hand-written loop over the fields", "the same refines()"],
        ["Does the new operating boundary refine the old one?",
         "refines(), in core/domain/contracts.py", "the same refines()"],
        ["Does the source's output arrive where the target reads?  (L-21)",
         "IT DID NOT ASK", "A ⊑ B"],
        ["Is this child a refinement of its parent?",
         "could not be asked at all", "A ⊑ B     new"],
        ["What must a featureset provide to serve both models?",
         "could not be asked at all", "their meet     new"],
        ["What do two versions agree on?",
         "could not be asked at all", "their join     new"]]
th = table(sl, data, ML, y, CW, col_w=[5.0, 3.6, 3.034],
           row_h=0.34, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.80,
     "Four implementations of one relation disagree eventually, and the "
     "direction is predictable: toward PERMITTING MORE, because that is the "
     "direction in which nobody files a bug. ",
     "The fourth row was the worst — a dependency graph whose edges were never "
     "checked. L-20 states the structure the one relation has, and the test "
     "asserts it over generated schemas: the order — a preorder, and a partial "
     "order on canonical form — meet below both, join above "
     "both, idempotence, commutativity, associativity, absorption, and the link "
     "A ⊑ B ⟺ A ⊓ B = A that makes it a lattice ORDER rather than an order and "
     "two unrelated operations. The three marked new are questions a "
     "practitioner asks out loud in a meeting and nothing could answer.")

# ------------------------------------------------------------- the order
sl, y = content("A ⊑ B — “A can stand in for B”", "The algebra · the order")
h = code(sl, ML, y, CW * 0.54, [
    "A ⊑ B   iff   A has every field B has,",
    "              each accepting AT LEAST what B's accepted",
    "",
    "# a slot is one named field of a schema",
    "# extra fields in A are fine — they are simply not read",
    "",
    "# reflexive and transitive. A ⊑ B and B ⊑ A gives the same fields",
    "# as a SET, so it is a preorder — and a partial order on the",
    "# name-sorted canonical form every constructor here produces",
], fs=10.5, title="core/domain/lattice.py")

note(sl, ML, y + h + 0.28, CW * 0.54, 1.35,
     "The direction surprises people. ",
     "A subtype is usually the NARROWER thing, so “A refines B” sounds as "
     "though A should accept less. It is the other way round: to stand in for "
     "B, A must accept everything B accepted.")

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 0.4)
para(tf, "Join always; meet when it can", size=13, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=10)
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

note(sl, x, yy + 0.05, CW * 0.42, 1.55,
     "So it is a join-semilattice with PARTIAL meets, ",
     "rather than a lattice outright — and the partiality is informative. Two "
     "schemas whose shared field carries two different types have no meet at "
     "all. The honest answer to “can one featureset serve both these models” "
     "is then no, with the field named.")

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
