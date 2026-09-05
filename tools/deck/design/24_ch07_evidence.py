# ============================================================ CH 7
divider("7", "Evidence, and Six Questions from One Traversal",
        "An append-only chain, a semiring per question, and the one object "
        "that makes them a single computation.",
        ["Why there is no audit log", "The chain, and what verification means",
         "Six semirings", "The polynomial underneath"])

# -------------------------------------------------------- no audit log
sl, y = content("There is no separate audit log, and that is deliberate",
                "Evidence · one record")
tf = txt(sl, ML, y, CW * 0.54, 2.9)
para(tf, "Two records of who did what are two records that can disagree.",
     size=13, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=10)
para(tf, "So the evidence chain — the append-only, hash-linked record of every "
         "act — IS the audit log. The consolidation is load-bearing rather than "
         "tidy: segregation of duties is decided by READING THE CHAIN, which "
         "only works if the chain is the record.",
     size=11.5, color=INK, space_after=9, line=1.28)
para(tf, "“Has this person already acted incompatibly on this model?” is a "
         "query over the same rows that prove what happened. A second "
         "who-did-what table would answer it from a copy, and the copy is what "
         "goes stale.",
     size=11, color=SLATE, space_after=0, line=1.28)

x = ML + CW * 0.58
h = code(sl, x, y, CW * 0.42, [
    "evidence_node:",
    "  seq · kind · subject_type · subject_id",
    "  payload · parents",
    "  contains_personal_data · trust",
    "  recorded_at · recorded_by",
    "  content_hash · prev_hash · chain_hash",
], fs=9.5, title="ONE TABLE, TWO STRUCTURES")
note(sl, x, y + h + 0.26, CW * 0.42, 1.75,
     "Each node names its parents, and the parents say what supports what. ",
     "The seq / prev_hash chain is separate and linear: it says what order "
     "things happened in, which is what makes deleting a node or inserting into "
     "the past detectable.")

# ---------------------------------------------------------- verification
sl, y = content("Verification re-derives; it does not re-link",
                "Evidence · what verification means")
steps(sl, ML, y, CW, [
    ("01", "Sequence gaps", "a missing seq is a deletion, and the chain says so"),
    ("02", "prev_hash", "each node links the one before it"),
    ("03", "RE-DERIVED content_hash",
     "recomputed from the node's own kind, subject, payload and parents"),
    ("04", "chain_hash", "the link over all three"),
], h=1.70)
note(sl, ML, y + 2.00, CW, 1.60,
     "The third step is the one that is easy to get wrong. ",
     "Re-linking the STORED content hash proves the links are intact and says "
     "nothing about whether what was linked is still what was recorded: an "
     "edited payload leaves a chain that verifies and a record that lies. "
     "Recomputing the hash from the node's own contents answers the second "
     "question, and it is a different question.")

# ------------------------------------------------------------- semirings
sl, y = content("One traversal, six questions", "Evidence · semirings")
data = [["Semiring", "its “add”", "its “multiply”", "The question it answers"],
        ["boolean", "or", "and", "is this claim supported at all?"],
        ["why", "union, then absorption", "pairwise union",
         "what is the MINIMAL set of facts that supports it?"],
        ["counting", "+", "×", "how many independent derivations support it?"],
        ["trust", "max", "×", "how far do we trust the best route to it?"],
        ["cost", "min", "+", "what is the cheapest way to establish it?"],
        ["freshness", "max", "max", "how recent is the evidence behind it?"]]
th = table(sl, data, ML, y, CW, col_w=[1.7, 2.4, 2.0, 5.534],
           row_h=0.32, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 1.25,
     "The last row is not a semiring, and the platform says so. ",
     "(max, max) has no annihilating zero — max(0, 5) is 5, not 0 — so it is "
     "a “take the newest” used twice rather than an algebra. The consequence: a "
     "claim resting on a MISSING fact reports the freshness of the facts that "
     "are present rather than reporting that it has none.")

# ------------------------------------------------------------ polynomial
sl, y = content("Evaluate once, then substitute — ℕ[X]",
                "Evidence · the universal object")
h = code(sl, ML, y, CW * 0.54, [
    "# evaluate the derivation ONCE, keeping the facts as symbols",
    "poly = evaluate(claim, derivations, POLYNOMIAL, variable)",
    "",
    "# every other answer is a substitution into that result",
    "boolean  = pushforward(poly, is_present,  BOOLEAN)",
    "trust    = pushforward(poly, trust_of,    TRUST)",
    "cost     = pushforward(poly, cost_of,     COST)",
    "",
    "#   L-9 :  eval_K(claim)  ==  h( eval_ℕ[X](claim) )",
], fs=9.5, title="core/evidence/semirings.py")
note(sl, ML, y + h + 0.28, CW * 0.54, 1.35,
     "Checked over 200 random derivation graphs against five semirings. ",
     "That turns “the same traversal answers a different question for each” "
     "from a design intention into a theorem the build runs.")

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 3.6)
para(tf, "What the polynomial keeps that Boolean throws away", size=12.5,
     color=CRIMSON, bold=True, font=SERIF, first=True, space_after=9)
para(tf, "COEFFICIENTS count how many distinct derivations produce the same "
         "combination of facts. EXPONENTS count how many times one fact is used "
         "within a single derivation.",
     size=11, color=INK, space_after=8, line=1.26)
para(tf, "Boolean provenance loses both, which is why it cannot tell a claim "
         "resting on one document from a claim resting on four — and “how "
         "corroborated is this” is exactly what a reviewer is asking.",
     size=11, color=SLATE, space_after=8, line=1.26)
para(tf, "The same construction annotates DERIVED FEATURES, where the ingest "
         "clock obeys the same algebra rather than a rule somebody could "
         "forget.",
     size=11, color=INK, space_after=0, line=1.26)
