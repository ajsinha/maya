# ============================================================ SCOPE
_state["chapter"] = "Front matter"
sl, y = content("Who this is for, and where to stop reading",
                "Front matter · scope")
data = [["If you are", "Read", "You can stop after"],
        ["a model developer or a quant",
         "Parts I, III and V — the philosophy, the objects, the examples",
         "chapter 15"],
        ["a validator or model risk manager",
         "Parts I, II and III, then chapter 24 for the evidence each kind of "
         "model can produce", "chapter 15"],
        ["a supervisor or an auditor",
         "Part I, then chapters 7, 8 and 14 — evidence, the laws, what a pack "
         "contains", "chapter 14"],
        ["an engineer building on it",
         "all of it; chapter 16 onward is the level below the architecture",
         "nowhere — chapter 23 is the operations"],
        ["deciding whether to buy or build",
         "Part I and chapter 24", "chapter 24"]]
th = table(sl, data, ML, y, CW, col_w=[3.2, 5.6, 2.834],
           row_h=0.42, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 0.95,
     "Part I answers a question the rest of the deck assumes. ",
     "If you read nothing else, read that: the whole design is downstream of "
     "one sentence about what a model is.")

sl, y = content("What this document is, and what it is not",
                "Front matter · scope")
data = [["Document", "Level", "Answers"],
        ["03 — Requirements", "what must be true",
         "numbered requirements, personas, regulatory traceability"],
        ["04 — Architecture", "what the containers are, and why",
         "deployable units, bounded contexts, failure modes"],
        ["This deck", "the whole thing, at the level a person reads",
         "the philosophy, the mathematics, the objects, the design, and a "
         "worked example of each"],
        ["14 — Detailed design", "what each component does internally",
         "interfaces, algorithms, transaction boundaries, concurrency, SLOs"],
        ["00 — Foundations", "why any of it is true",
         "the definitions, the theorems, and the law table with what runs"]]
th = table(sl, data, ML, y, CW, col_w=[3.1, 3.3, 5.234],
           row_h=0.40, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.15,
     "Test of adequacy. ",
     "A practitioner who has read Parts I to III should be able to register a "
     "model, assemble its inputs and authorise a run without guessing; an "
     "engineer who has read Part IV should be able to open a component and "
     "start implementing. Where that is not true it is a gap in this deck "
     "rather than a decision left to the reader.")

# ------------------------------------------------------------- vocabulary
# Every term the deck leans on, defined before Part I rather than in the
# chapter that happens to need it first. A reader meeting "T2" or "L-W10" on
# slide ninety has been failed by the deck; a reader who can turn back to one
# page has not.
sl, y = content("Ten terms, defined before they are used",
                "Front matter · vocabulary")
data = [["Term", "What it means in this deck"],
        ["Model (parametric kernel)",
         "f : P ⊗ X → D(Y). Parameters P, inputs X, a distribution over "
         "outputs Y."],
        ["P, the parameter object",
         "The numbers or rules that decide what the model does. Empty for an "
         "analytical pricer; weights for a network; a rule set for a policy."],
        ["Trainability class, T0–T8",
         "Derived from how P is inhabited, never declared. T0 has no "
         "parameters at all; T8 is authored rules."],
        ["Warrant",
         "A signed document authorising one specific act, on one specific "
         "model version, by one principal, for a stated use."],
        ["Refusal",
         "A machine-readable “no”: a code, what failed, and what to do about "
         "it. Never a bare error."],
        ["Risk tier, 1–4",
         "Derived from materiality and complexity; decides how much control "
         "the model gets."],
        ["Law (L-1…L-21, L-W0…L-W13)",
         "A stated property with a test that runs. The L-W family are "
         "warrant-admissibility laws."],
        ["Two clocks",
         "Event time (when a fact was true) and ingest time (when it became "
         "known)."],
        ["Featureset",
         "A named, versioned schema that a training or scoring input must "
         "fill."],
        ["Semiring",
         "An algebra with an “add” and a “multiply”. Swapping the pair lets "
         "ONE graph traversal answer different questions."]]
table(sl, data, ML, y, CW, col_w=[3.0, 8.634],
      row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
