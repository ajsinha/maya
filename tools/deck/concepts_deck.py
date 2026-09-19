"""
The concepts and formalism deck: the argument of the paper
(docs/research/models-as-parametric-kernels.tex), slide by slide, with each
construction marked for what MAYA 0.3.0 actually implements.

It replaces two decks of the previous build, Concepts and Formalism and
Models as Parametric Kernels. Both presented the same theory; one deck tied to
the paper is one place to keep the theory and its status honest.

The status register used here is the paper's. A construction is marked
*runs* only where a module implements it and a test exercises it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

CHAPTER = "MAYA · Concepts and Formalism"
TITLE = "Models as Parametric Kernels — Concepts and Formalism"
SUBJECT = "The theory behind MAYA, and what version 0.3.0 implements of it"

OPENING = [
    {"kind": "title", "kicker": "CONCEPTS AND FORMALISM  ·  THE PAPER, IN SLIDES",
     "title": ["Models as parametric kernels"],
     "sub": "A definition, an order, an operator and a polynomial — and what MAYA 0.3.0 implements of each.",
     "agenda": ["Declared facts, and why they rot", "The kernel and its parameter object",
                "One order", "One operator", "One polynomial",
                "What must still be declared, and where automation belongs"]},

    {"kind": "cards", "kicker": "The diagnosis", "title": "Four facts that are usually typed in, and rot",
     "cols": 4,
     "cards": [("D1", "Kind is declared", "“ML model”, “pricer”, “other” — and a closed-form pricer is asked for its training set."),
               ("D2", "Fit is declared", "“This may replace that”, “this feature set serves that model”: four code paths for one relation."),
               ("D3", "Currency is declared", "What a training row could have known is written into a query, and never checked."),
               ("D4", "Support is declared", "Prose records that a version was validated; nothing computes what the conclusion rests on.")],
     "note": "The paper's thesis: each is a fact about structure recorded as a fact about opinion, and each can be derived — by a definition, an order, an operator and a polynomial."},

    {"kind": "table", "kicker": "How to read this deck", "title": "Every construction carries its status in MAYA 0.3.0",
     "rows": [["Mark", "Meaning"],
              ["Runs", "A module implements it and a named test exercises it"],
              ["Partly", "A narrower form is implemented; the slide says which part"],
              ["Not implemented", "Stated and argued in the paper; nothing in MAYA 0.3.0 executes it"]],
     "col_w": [2.4, 9.3],
     "note": "The previous build carried twenty-one laws in tests/test_laws.py. That file did not survive the rebuild of September 2026, and none of its laws is claimed here. A law that is stated and not executed prevents nothing."},
]

KERNEL = [
    {"kind": "divider", "num": "1", "title": "The kernel",
     "sub": "A model is a morphism of Para(Stoch): a parameter object P and a kernel f : P ⊗ X → Y. Training is one way of inhabiting P, not part of being a model.",
     "points": ["The definition", "Trainability from how P is inhabited",
                "Points of P, and what a version is"]},

    {"kind": "split", "kicker": "Definition", "title": "A model is a machine with dials, kept separate from the machinery",
     "left": {"head": "In the paper",
              "items": [("(P, f) with f : P ⊗ X → Y", "X is the input object, Y the output, P the parameter object; f may be stochastic."),
                        ("Composition accumulates parameters", "(P, f) then (Q, g) has parameter object Q ⊗ P: nothing is absorbed."),
                        ("A fitting morphism φ : D → P", "Estimation, calibration, training, elicitation and authorship are different φ into one kind of thing.")]},
     "right": {"head": "In MAYA 0.3.0 — partly",
               "items": [("Roles in the formula IR", "Every input is a feature, a parameter or a constant (maya/formula/ir.py: input_contract, parameter_inputs)."),
                         ("Q ⊗ P, as alias namespacing", "A composite's one parameter set is namespaced by member alias (maya/formula/evaluate.py; tests/test_formula.py::test_composite_union_maturity_seeds_and_eval)."),
                         ("Points of P are not versions", "Parameter sets version separately from model versions; several may exist for one version (specification §8.4, §8.6).")]}},

    {"kind": "table", "kicker": "Trainability", "title": "The paper derives nine classes; MAYA derives one split",
     "rows": [["Class", "P and φ", "In MAYA 0.3.0"],
              ["T0 Analytical", "P terminal; nothing to fit", "Partly: derived — a model with no parameter inputs takes an execution warrant directly (maya/services/execution.py); no committed test exercises it"],
              ["T1–T3 Calibrated, estimated, learned", "A solver, an estimator, a training run", "Not distinguished: all need a training warrant and an approved parameter set"],
              ["T4 Adaptive", "P moves in production", "Not implemented"],
              ["T5 Configured", "Base model, prompt, corpus, tools", "Not implemented"],
              ["T6 Opaque", "P exists and is unreachable", "Partly: the declared kind vendor; what cannot be verified is marked (tests/test_vendor_models.py)"],
              ["T7 Elicited, T8 Authored", "A panel's weights; a rule set", "Not implemented"]],
     "col_w": [2.6, 3.0, 6.1],
     "note": "Model kinds in MAYA are declared, not derived: formula, black_box, composite, vendor (maya/services/models.py). Only the T0 row is computed, and permissively: a model with no closed-form body passes as non-trainable whatever parameters it declares (a finding of the paper, not fixed)."},
]

ORDER = [
    {"kind": "divider", "num": "2", "title": "One order",
     "sub": "A ⊑ B, read “A can stand in for B”. Substitution, feature-set adequacy and composability are one comparison, and its meet is partial — informatively.",
     "points": ["The schema order and its lattice", "Four questions, one relation",
                "Aggregate risk does not compose"]},

    {"kind": "split", "kicker": "The order", "title": "Provide everything the other provided, and be no fussier about it",
     "left": {"head": "In the paper",
              "items": [("A ⊑ B", "Every field of B is in A, with the same type, nullable if B's is, and bounds at least as wide."),
                        ("A lattice on finite fragments", "The meet ⊓ widens shared fields; the join narrows; the empty schema is the top; there is no bottom."),
                        ("The meet is partial", "Two schemas that give one name two types have no lower bound — so no feature set can serve both.")]},
     "right": {"head": "In MAYA 0.3.0 — partly",
               "items": [("Feature set serves model", "Presence and numeric type only, every miss listed; bounds and nullability are not compared (maya/services/warrants.py: validate_contract)."),
                         ("The partial meet is deployed", "A composite's contract is the union of its members'; two members wanting one name at different types are refused, naming it (maya/formula/composite.py: union_contract)."),
                         ("Not implemented", "The join, the lattice laws as tests, and a type check on pipeline edges.")]},
     "note": "tests/test_warrants.py::test_contract_mismatch_is_refused_listing_every_attribute; tests/test_formula.py::test_composite_union_maturity_seeds_and_eval."},

    {"kind": "table", "kicker": "One relation", "title": "Four questions the paper answers with one comparison",
     "rows": [["Question", "As the order", "In MAYA 0.3.0"],
              ["May version v′ replace v?", "in(v′) ⊑ in(v), outputs provided", "Partly: each version bump is classified breaking, behavioral or additive (maya/services/catalog.py: change_class)"],
              ["Does feature set F serve model k?", "S(F) ⊑ in(k)", "Partly: presence and numeric type"],
              ["Does edge a → b compose?", "out(a) ⊑ in(b)", "Not implemented as a check"],
              ["Can one F serve k₁ and k₂?", "S(F) ⊑ in(k₁) ⊓ in(k₂)", "Runs for composite members: the union contract, refused when the meet does not exist"]],
     "col_w": [3.2, 3.2, 5.3]},

    {"kind": "split", "kicker": "Aggregate risk", "title": "The risk of the whole is not a function of the risks of the parts",
     "left": {"head": "The theorem",
              "items": [("No compositional, fragility-sensitive risk assignment", "Over any join-semilattice with two elements."),
                        ("The obstruction is the copy map", "One curve feeding two pricers and two curves feeding one each have equal constituent risks and unequal fragility."),
                        ("So a correct aggregate is at best lax", "Report the join and attribute the difference to what is shared.")]},
     "right": {"head": "In MAYA 0.3.0",
               "items": [("No aggregate risk number is computed", "Which is what the theorem says cannot honestly be done."),
                         ("What composes is an order", "A composite's maturity is capped at its lowest member's, and the blocking members are named (maya/formula/composite.py: capped_maturity)."),
                         ("Shared dependency is visible, not scored", "Lineage edges answer what depends on what (specification §19).")]},
     "note": "The theorem is mathematics and needs no implementation. MAYA respects it by refusing to state a magnitude, not by computing one."},
]

OPERATOR = [
    {"kind": "divider", "num": "3", "title": "One operator",
     "sub": "The point-in-time read as an operator, AsOf(R, ℓ, a), whose knowledge bound is min(ℓ, a). Its fourth property — saturation at the label — is reproducibility.",
     "points": ["Two clocks", "The operator and its four properties",
                "What MAYA implements instead", "A worked restatement"]},

    {"kind": "split", "kicker": "The operator", "title": "Use the latest fact true by the decision date and known by it",
     "left": {"head": "In the paper",
              "items": [("Adm(R, ℓ, a)", "Rows with event ≤ ℓ and knowledge ≤ min(ℓ, a); AsOf picks the latest of them."),
                        ("Four properties", "Idempotent; commutes with projection; monotone in a; saturating: for every a ≥ ℓ the read is the read at ℓ."),
                        ("Saturation is reproducibility", "A row re-assembled a year later is the row assembled originally, whatever arrived since.")]},
     "right": {"head": "In MAYA 0.3.0 — partly",
               "items": [("A scalar knowledge cut", "Rows known after as_of_known are dropped, then the latest knowledge per key wins (maya/resolution/resolver.py: bitemporal_cut)."),
                         ("A certificate, not a selection", "The signed leakage certificate checks each row's knowledge time ≤ its event date + lag, and refuses unjustified exceptions."),
                         ("Reproducibility by pinning", "A pin freezes the bytes and records its as_of_known; saturation is not what delivers it.")]},
     "note": "The paper proves the relation: where the certificate is clean, the cut returns exactly AsOf's row; a later rebuild is reproducible or refused. Tests: test_sc11_point_in_time_after_restatement, test_leakage_certificate_refuses_late_knowledge."},

    {"kind": "table", "kicker": "Worked example", "title": "Accounts dated 31 March, filed 20 May, restated in August",
     "intro": "A borrower's debt-service ratio: 1.20 as filed, 0.40 as restated. A decision was taken on 15 June. Both rows are true and both are kept, with one event time and two knowledge times.",
     "rows": [["Read", "What it returns for the June decision"],
              ["One clock (latest value)", "0.40 — a number that exists because the default happened"],
              ["The paper's AsOf, at any later date", "1.20, and still 1.20 when rebuilt in 2028"],
              ["MAYA, pinned with as_of_known = 15 June", "1.20, frozen in the pin"],
              ["MAYA, resolved later with as_of_known after August", "0.40 — and the leakage certificate, with a 60-day lag, flags the August row and refuses it unless justified"]],
     "col_w": [4.2, 7.5],
     "note": "The difference is the point of the slide: the operator constructs the right row, while MAYA detects the wrong one and relies on the pin and a recorded knowledge instant to keep the right one."},
]

POLYNOMIAL = [
    {"kind": "divider", "num": "4", "title": "One polynomial",
     "sub": "Annotate evidence with the free commutative semiring ℕ[X], and every question about what a claim rests on becomes a pushforward along a homomorphism.",
     "points": ["Universality of ℕ[X]", "What MAYA computes instead",
                "A negative result, and where it bites"]},

    {"kind": "table", "kicker": "In the paper — not implemented", "title": "One traversal, a different question for each semiring",
     "rows": [["Semiring", "⊕, ⊗", "Question answered"],
              ["𝔹", "∨, ∧", "Is the claim supported at all?"],
              ["ℕ", "+, ×", "How many independent derivations support it?"],
              ["PosBool(X)", "absorptive ∪, pairwise ∪", "Which minimal evidence sets suffice?"],
              ["ℕ[X]", "+, ×", "Exactly how was it derived?"],
              ["([0,1], max, ×)", "max, ×", "With what confidence?"],
              ["(ℝ⁺ ∪ {∞}, min, +)", "min, +", "At what least cost can a gap be closed?"]],
     "col_w": [3.0, 3.2, 5.5],
     "note": "MAYA 0.3.0 has no evidence derivation structure and no semiring evaluation. Lineage is recorded as typed edges (specification §19); nothing evaluates it as a polynomial."},

    {"kind": "split", "kicker": "In MAYA 0.3.0", "title": "Three valuations over what a derivation rests on",
     "left": {"head": "Implemented — runs",
              "items": [("Licence terms", "The most restrictive over the leaf sources (maya/security/licence.py: combine; tests/test_custody.py)."),
                        ("Non-causality", "True if any operand is non-causal (maya/resolution/algebra.py)."),
                        ("Knowledge clock of a feature-set row", "The maximum of its members' knowledge times (maya/resolution/featureset.py).")]},
     "right": {"head": "And the negative result, in practice",
               "items": [("(max, max) is not a semiring", "Its zero does not annihilate, so a missing annotation behaves as the identity."),
                         ("MAYA shows the same shape", "An undeclared licence counts as unrestricted; a null knowledge time is ignored."),
                         ("A finding", "project, compose, coalesce, aggregate, resample and case drop the knowledge-time column: rows of such derived features carry none, and the certificate cannot examine them.")]},
     "note": "The finding was made while writing the paper and is not fixed in 0.3.0. The repair the paper gives: adjoin a fresh zero meaning no derivation, and a missing annotation stops reading as no restriction."},
]

BOUNDARY = [
    {"kind": "table", "kicker": "What must still be declared", "title": "Derived, declared with an oracle, or irreducibly declared",
     "rows": [["Construction", "In the paper", "In MAYA 0.3.0"],
              ["Tiering and control adequacy", "A monotone τ; a Galois connection between tiers and controls", "Not implemented"],
              ["Regimes as institutions", "The satisfaction condition as a test of an encoding", "Not implemented"],
              ["Contracts (A, G)", "Operating boundary A, performance envelope G", "Partly, as covenants: a breach suspends the warrant (tests/test_security_regressions.py::test_each_covenant)"],
              ["Probe-relative identity", "Equivalence is as strong as the probe set", "Partly: spec–code conformance on sampled inputs, and sampled agreement is not proof (maya/formula/conformance.py)"],
              ["Fibrations; rule-set reachability", "Evidence indexed by kind; shadowed rules decided", "Not implemented"],
              ["Approval, validation, residual risk", "Irreducibly declared: they constitute the standard", "Declared by an accountable person, recorded in workflow"]],
     "col_w": [3.0, 4.2, 4.5]},

    {"kind": "table", "kicker": "Automation", "title": "A machine may generate wherever acceptance is checked",
     "intro": "If an output can be checked by an oracle, the generator's error rate decides throughput, not correctness. Where a fact constitutes the standard, there is nothing to check it against.",
     "rows": [["Task", "Oracle", "In MAYA 0.3.0"],
              ["Bind a feature set to a model", "The contract check", "Runs (validate_contract)"],
              ["Assemble training data without look-ahead", "The leakage certificate", "Runs"],
              ["Lift a spreadsheet into the IR", "The workbook's results and LibreOffice Calc", "Runs (tests/test_spreadsheet*.py)"],
              ["Reproduce a result", "The bundle's verify.py, re-executing", "Runs (tests/test_sdk_modes.py)"],
              ["Code matches the documented mathematics", "Sampled conformance", "Partly: sampled"],
              ["Conclude a validation; approve", "None exists", "A person, with the assistant's memo as a recorded challenge"]],
     "col_w": [3.6, 3.6, 4.5],
     "note": "The assistant never approves, blocks or writes to a sealed object; the reviewer records whether they agreed (tests/test_assistant.py::test_submission_queues_a_memo_that_cannot_block_or_edit). Its Claude provider is tested against a stub only."},

    {"kind": "table", "kicker": "The register", "title": "What the paper claims, and what MAYA 0.3.0 executes",
     "rows": [["Construction", "Status", "Where"],
              ["Parameters separate from the kernel; Q ⊗ P for composites", "Runs", "maya/formula/ir.py, evaluate.py"],
              ["Trainability classes T0–T8", "Partly: T0 derived, T6 declared", "maya/services/execution.py, models.py"],
              ["Schema order, lattice, four questions", "Partly: contract check, partial meet", "maya/services/warrants.py, formula/composite.py"],
              ["No compositional aggregate risk", "Respected: no number computed", "formula/composite.py: capped_maturity"],
              ["AsOf with min(ℓ, a) and saturation", "Partly: scalar cut and certificate", "maya/resolution/resolver.py, services/warrants.py"],
              ["Provenance over ℕ[X]", "Not implemented; three support valuations", "maya/security/licence.py, resolution/"],
              ["Tiering, institutions, fibrations, rule sets", "Not implemented", "—"],
              ["Contracts; the automation boundary", "Partly: covenants. Runs: the recorded challenger", "services/execution.py, maya/assistant/"]],
     "col_w": [4.4, 3.6, 3.7]},

    {"kind": "bullets", "kicker": "Limitations", "title": "What would falsify the account, and what the implementation does not show",
     "items": ["No implementation study: a large test suite shows a system is internally consistent, not that building on this foundation is easier. There is no user evaluation and no deployment at a supervised institution.",
               "The derivations still read declarations — IR roles, knowledge times, licence terms. The declared surface shrinks; it does not vanish.",
               "Much of the theory is not implemented in 0.3.0, and the slides say which. Availability of a construction in the paper is not evidence of its use.",
               "The account is falsified by an artefact class that is not a (P, φ) pair without distortion, a question about fit that is not an instance of ⊑, or practitioners who cannot act on the refusals it produces."]},

    {"kind": "bullets", "kicker": "Conclusion", "title": "A definition, an order, an operator and a polynomial",
     "items": ["What kind of artefact this is derives from how its parameter object is inhabited — in MAYA, only the analytical case is computed so far.",
               "Whether one thing fits where another did derives from one order — in MAYA, a contract check and a partial meet that refuses by name.",
               "What a training row could have known derives from an operator — in MAYA, a knowledge cut, a signed certificate and a pin.",
               "What a claim rests on derives from a polynomial — in MAYA, three valuations over the sources, and a gap this paper found.",
               "Where a fact constitutes the standard, it stays declared, by someone accountable — and that is where the machine stops."],
     "note": "Paper: docs/research/models-as-parametric-kernels.tex (CC BY-NC-ND 4.0, docs/research/LICENSE). Not legal, regulatory or financial advice (NOTICE §4)."},
]

SLIDES = OPENING + KERNEL + ORDER + OPERATOR + POLYNOMIAL + BOUNDARY
