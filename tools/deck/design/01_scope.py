# ============================================================ SCOPE
_state["chapter"] = "Front matter"
sl, y = content("Who this is for, and where to stop reading",
                "Front matter · scope")
# The third column is the LAST chapter the second column sends you to. It used
# to say "chapter 15" for a reader told to read Part V, which begins fifty-one
# slides later — the kind of contradiction that makes a reader distrust every
# table after it.
data = [["If you are", "Read", "The last chapter you need"],
        ["a model developer or a quant",
         "Parts I, III and V — the philosophy, the objects, the examples",
         "chapter 25 — the end of it"],
        ["a validator or model risk manager",
         "Parts I, II and III, then chapter 24 for the evidence each kind of "
         "model can produce", "chapter 24"],
        ["a supervisor or an auditor",
         "Part I, then chapters 7, 8 and 14 — evidence, the laws, what a pack "
         "contains", "chapter 14"],
        ["an engineer building on it",
         "all of it; chapter 16 onward is the level below the architecture",
         "chapter 25, and chapter 23 is the operations"],
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
note(sl, ML, y + th + 0.30, CW, 0.95,
     "Test of adequacy. ",
     "Parts I to III should leave a practitioner able to register a model and "
     "authorise a run without guessing; Part IV should leave an engineer able "
     "to open a component and start. Where that is not true it is a gap in "
     "this deck.")

# ------------------------------------------------------------- vocabulary
# Every term the deck leans on, defined before Part I rather than in the
# chapter that happens to need it first. A reader meeting "fibre" or "L-W10" on
# slide ninety has been failed by the deck; a reader who can turn back to one
# page has not.
#
# The list is chosen by DIFFICULTY rather than by prominence. An earlier pass
# defined "risk tier" and "two clocks", which the deck names in their own
# chapters anyway, and left `fibre`, `lens`, `overlay`, `contract`, `alias` and
# the grant/entitlement distinction undefined everywhere.
sl, y = content("Thirteen terms, defined before they are used",
                "Front matter · vocabulary")
data = [["Term", "What it means in this deck"],
        ["Model (parametric kernel)",
         "f : P ⊗ X → D(Y). Parameters P, inputs X, a distribution over "
         "outputs Y."],
        ["P, the parameter object",
         "The numbers or rules that decide what the model does. Empty for an "
         "analytical pricer; weights for a network; a rule set for a policy."],
        ["Trainability class, T0–T8",
         "Derived from how P is inhabited, never declared. T0 nothing to fit · "
         "T1 calibrated · T2 estimated · T3 trained · T4 still training · "
         "T5 configured · T6 opaque · T7 elicited · T8 authored."],
        ["Fibre",
         "What one trainability class is given: an evidence schema, a "
         "lifecycle, a metric set and a template set. No fibre may be empty "
         "(L-15), so a new kind of model is a fibre and nothing else."],
        ["Alias",
         "A governed name — #champion — that points at whichever version is "
         "approved today. A consumer holds the alias; it never holds a version."],
        ["Operating contract",
         "The boundary a version was validated inside. A replacement must "
         "REFINE it, and a run outside it is refused rather than answered."],
        ["Grant, and entitlement",
         "A grant is the standing entitlement: this principal, this "
         "environment, this declared use. A warrant is a short-lived "
         "credential minted against one, so revocation has something to bite."],
        ["Warrant",
         "A signed, expiring instruction authorising one act, on one model "
         "version, by one principal, for a stated use."],
        ["Overlay",
         "A post-model adjustment to an output. Legitimate briefly; an overlay "
         "renewed past its limit is an unversioned model change, and is raised "
         "as a finding."],
        ["Lens",
         "A function from platform state to prose PLUS the evidence it rested "
         "on. Documentation sections are lenses rather than templates, so a "
         "section cannot describe a state that no longer holds."],
        ["Refusal",
         "A machine-readable “no”: a code, what failed, and what to do about "
         "it. Never a bare error."],
        ["Law (L-1…L-21, L-W0…L-W13)",
         "A stated property with a test that runs. The L-W family are "
         "warrant-admissibility laws."],
        ["Semiring",
         "An algebra with an “add” and a “multiply”. Swapping the pair lets "
         "ONE graph traversal answer different questions."]]
table(sl, data, ML, y, CW, col_w=[2.6, 9.034],
      row_h=0.28, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
