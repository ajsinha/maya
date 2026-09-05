# ============================================================ SCOPE
_state["chapter"] = "Front matter"
sl, y = content("Who this is for, and where to stop reading",
                "Front matter · scope")
data = [["If you are", "Read", "And you can stop after"],
        ["a model developer or a quant",
         "Parts I, III and V — philosophy, the objects, the examples",
         "chapter 15, having seen every refusal you will meet"],
        ["a validator or model risk manager",
         "Parts I, II and III — and chapter 24 for the evidence each class can "
         "produce", "chapter 15"],
        ["a supervisor or an auditor",
         "Part I, then chapters 7, 8 and 14 — evidence, the laws, and what a "
         "pack contains", "chapter 14"],
        ["an engineer building on it",
         "all of it, and chapter 16 onward is the level below the architecture",
         "nowhere; chapter 23 is the operations"],
        ["deciding whether to buy or build",
         "Part I and chapter 24", "chapter 24"]]
th = table(sl, data, ML, y, CW, col_w=[3.2, 5.2, 3.234],
           row_h=0.42, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.25,
     "Part I is nine slides and answers a question the rest of the deck "
     "assumes. ",
     "If you read nothing else, read that — the whole design is downstream of "
     "one sentence about what a model is, and the sections that look like "
     "engineering decisions are consequences of it rather than choices made "
     "beside it.")

sl, y = content("What this document is, and what it is not",
                "Front matter · scope")
data = [["Document", "Level", "Answers"],
        ["03 — Requirements", "what must be true",
         "~200 numbered requirements, personas, regulatory traceability"],
        ["04 — Architecture", "what the containers are, and why",
         "deployable units, bounded contexts, extensibility, failure modes"],
        ["This deck", "the whole thing, at the level a person reads",
         "the philosophy, the mathematics, the objects, the design, and worked "
         "examples of each"],
        ["14 — Detailed design", "what each component does internally",
         "interfaces, algorithms, transaction boundaries, concurrency, SLOs"],
        ["00 — Foundations", "why any of it is true",
         "the definitions, the theorems, and the law table with what runs"],
        ["11 — Adversarial review", "what was wrong with all of it",
         "27 findings; 17 required redesign — folded in here"]]
th = table(sl, data, ML, y, CW, col_w=[3.1, 3.3, 5.234],
           row_h=0.40, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.15,
     "Test of adequacy. ",
     "A practitioner who has read Parts I to III should be able to register a "
     "model, compose a featureset and issue a warrant without guessing; and an "
     "engineer who has read Part IV should be able to open a component and begin "
     "implementing without inventing an interface. Where that is not true it is "
     "a gap in this deck rather than a decision left to the reader.")
