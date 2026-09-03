# -*- coding: utf-8 -*-
exec(open(__file__.replace("slides.py","theme.py")).read())

# ============================================================ TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.45, fill=CRIMSON)
rect(sl, 0, 4.45, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.45, fill=CRIMSON_D)
tf = txt(sl, ML + 0.3, 0.92, CW, 0.34)
para(tf, "APPLIED CATEGORY THEORY  ·  MODEL RISK  ·  VERIFIED AUTOMATION",
     size=11, color=RGBColor(0xE8,0xB8,0xC0), bold=True, first=True, space_after=0)
tf = txt(sl, ML + 0.3, 1.40, CW * 0.88, 2.1)
para(tf, "Models as Parametric Kernels,", size=37, color=WHITE, font=SERIF, first=True, space_after=2)
para(tf, "Governance as Verified Automation", size=37, color=WHITE, font=SERIF, space_after=0)
rect(sl, ML + 0.3, 3.28, 1.7, 0.035, fill=RGBColor(0xE8,0xB8,0xC0))
tf = txt(sl, ML + 0.3, 3.55, CW * 0.82, 0.8)
para(tf, "A mathematical foundation for heterogeneous model estates — and a criterion for where AI may do the work",
     size=14.5, color=RGBColor(0xF4,0xDF,0xE3), italic=True, first=True, space_after=0, line=1.25)
tf = txt(sl, ML + 0.3, 4.95, CW * 0.55, 1.0)
para(tf, "Ashutosh Sinha", size=21, color=INK, bold=True, font=SERIF, first=True, space_after=3)
para(tf, "Independent Researcher", size=12.5, color=CRIMSON, space_after=1)
para(tf, "September 2026   ·   a conversation, not a conclusion", size=11, color=MUTED)
x0 = ML + CW * 0.56
tf = txt(sl, x0, 4.98, CW * 0.44, 1.4)
para(tf, "CONTENTS", size=9.5, color=CRIMSON, bold=True, first=True, space_after=7)
for i, c in enumerate(["The problem", "A formal foundation",
                       "Automation and its oracles", "Discussion"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=11.5, space_after=5)

# ============================================================ THE QUESTION
_state["chapter"] = "Front matter"
_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=PARCH)
rect(sl, 0, 0, 0.30, SH, fill=CRIMSON)
tf = txt(sl, ML + 0.5, 1.55, CW * 0.86, 1.3)
para(tf, "There is a question that sounds trivial", size=17, color=SLATE, italic=True, font=SERIF, first=True, space_after=6)
para(tf, "and turns out to be the hardest one in the room.", size=17, color=SLATE, italic=True, font=SERIF, space_after=0)
tf = txt(sl, ML + 0.5, 3.05, CW * 0.86, 1.1)
para(tf, "What is a model?", size=52, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
rect(sl, ML + 0.5, 4.42, 2.0, 0.035, fill=CRIMSON)
tf = txt(sl, ML + 0.5, 4.75, CW * 0.78, 1.3)
para(tf, "Not which one. Not whose. What one is — formally, generally, in a way that covers everything an organisation has to govern.",
     size=14, color=INK, first=True, space_after=10, line=1.3)
runs(tf, [("Two things follow from getting this right. A whole category of expensive software failure disappears — and ",
           SLATE, False), ("we learn where a machine may safely do the governing work.", CRIMSON, True)],
     size=14, space_after=0, line=1.3)
footer(sl)

# ============================================================ CH 1
divider("1", "The Problem", "Why heterogeneous model estates defeat the tools built to manage them.",
        ["The population", "Four pathologies", "A definition problem, not a product problem"])

sl, y = content("The population that must be governed as one thing", "The problem")
data = [["Artefact", "Where its parameters come from", "Refresh", "Trained?"],
        ["Black–Scholes pricer", "Financial theory", "Never", "No"],
        ["Volatility surface (SABR)", "Solved against market quotes", "Daily", "No"],
        ["PD scorecard", "Statistical estimation on a sample", "Annual", "Arguably"],
        ["Fraud classifier", "Gradient boosting on transactions", "Weekly", "Yes"],
        ["Adaptive AML threshold", "Updates itself in production", "Continuous", "Yes"],
        ["Narrative-drafting LLM", "Base model + prompt + corpus + tools", "On change", "No"],
        ["Third-party credit score", "Contractually unavailable", "Vendor", "Unknowable"],
        ["Country-risk scorecard", "A committee of nine people", "Annual", "No"],
        ["Allocation spreadsheet", "Somebody wrote a formula", "Ad hoc", "No"]]
th = table(sl, data, ML, y, CW, col_w=[3.0, 3.7, 1.5, 1.4], row_h=0.335, bold_col0=True,
      align=[PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.CENTER])
tf = txt(sl, ML, y + th + 0.26, CW, 0.7)
runs(tf, [("Three of these nine are trained. ", CRIMSON, True),
          ("All nine carry the same obligation: inventory, classify by materiality, challenge independently, monitor, document, control change. "
           "A large bank runs 800–3,000 of them.", INK, False)], size=13, first=True, space_after=0, line=1.3)

sl, y = content("Four pathologies with a single root cause", "The problem")
paths = [("P1", "The training assumption",
          "Tooling assumes train → register → deploy. Asking a closed-form pricer for its training set is not a missing value — it is a category error the system cannot express."),
         ("P2", "Schema rigidity",
          "When artefact kind is a column, every new kind is a migration touching every module. So new kinds are never added, and the newest artefacts are silently excluded."),
         ("P3", "Scope as a boolean",
          "Regulatory applicability is several facts, one per regulator, disagreeing by design. Modelled as a checkbox, every regulatory revision forces re-architecture."),
         ("P4", "Evidence as assertion",
          "The record states a model was validated. Nothing establishes that the model described is the model executing. The claim is unfalsifiable.")]
cw = (CW - 0.28 * 3) / 4
for i, (n, t, b) in enumerate(paths):
    card(sl, ML + i * (cw + 0.28), y + 0.05, cw, 2.75, n, t, b)
rect(sl, ML, y + 3.10, CW, 0.90, fill=PARCH)
rect(sl, ML, y + 3.10, 0.05, 0.90, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + 3.27, CW - 0.6, 0.65)
runs(tf, [("Root cause.  ", CRIMSON, True),
          ("There is no formal answer to ", INK, False), ("what is a model?", INK, True, True),
          ("  Every system therefore invents an informal one, and every informal one is wrong in a different way.", INK, False)],
     size=13, first=True, space_after=0)

sl, y = content("A definition problem, not a product problem", "The problem")
bw = (CW - 0.9) / 2
rect(sl, ML, y, bw, 2.35, fill=WHITE, line=RULE, lw=1.0)
rect(sl, ML, y, bw, 0.055, fill=NAVY)
tf = txt(sl, ML + 0.28, y + 0.26, bw - 0.56, 1.9)
para(tf, "Governance platforms", size=15, color=INK, bold=True, font=SERIF, first=True, space_after=9)
runs(tf, [("Strong: ", NAVY, True), ("workflow, approvals, findings, reporting.", SLATE, False)], size=11.5, space_after=7)
runs(tf, [("Structurally cannot: ", CRIMSON, True), ("see the artefact. The record asserts; nothing verifies. The claim is unfalsifiable.", SLATE, False)], size=11.5, space_after=0)
rect(sl, ML + bw + 0.9, y, bw, 2.35, fill=WHITE, line=RULE, lw=1.0)
rect(sl, ML + bw + 0.9, y, bw, 0.055, fill=NAVY)
tf = txt(sl, ML + bw + 1.18, y + 0.26, bw - 0.56, 1.9)
para(tf, "ML / MLOps platforms", size=15, color=INK, bold=True, font=SERIF, first=True, space_after=9)
runs(tf, [("Strong: ", NAVY, True), ("artefact lineage, telemetry, reproducibility.", SLATE, False)], size=11.5, space_after=7)
runs(tf, [("Structurally cannot: ", CRIMSON, True), ("express materiality, approved use, independent challenge or overlay — and never see 60–80% of the estate.", SLATE, False)], size=11.5, space_after=0)
rect(sl, ML + bw + 0.10, y + 0.90, 0.70, 0.55, fill=CRIMSON)
tf = txt(sl, ML + bw + 0.10, y + 1.01, 0.70, 0.4, align=PP_ALIGN.CENTER)
para(tf, "GAP", size=12, color=WHITE, bold=True, first=True, space_after=0)
tf = txt(sl, ML, y + 2.72, CW, 1.2)
runs(tf, [("Two families of tools each solve half a problem, and everyone assumes the gap is a product opportunity. ", INK, False, False, SERIF),
          ("Sometimes it is. Sometimes the gap is where a definition should be — and no amount of product fills it.", CRIMSON, True, False, SERIF)],
     size=15.5, first=True, space_after=0, line=1.32)

# ============================================================ CH 2
divider("2", "A Formal Foundation", "Six pillars, each admitted only because it pays rent.",
        ["What a model is", "The trainability classification", "Composition and the copy map",
         "An impossibility result", "Contracts, fibrations, institutions", "Evidence over a semiring"])

sl, y = content("The rent test", "A formal foundation · method")
rect(sl, ML, y, CW, 1.0, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + 0.18, CW - 0.7, 0.75)
para(tf, "An abstraction earns its place only if it delivers a property we would otherwise hand-build, hand-check or hand-migrate — and only if that property is stated as an executable law.",
     size=15, color=WHITE, italic=True, font=SERIF, first=True, space_after=0, line=1.25)
data = [["Pillar", "Mathematics", "Property delivered"],
        ["What is a model?", "Markov categories + Para construction", "One definition for nine model classes; training becomes optional by construction"],
        ["How do they compose?", "Symmetric monoidal categories", "Typed composition; blast radius; aggregate risk as lax monoidality"],
        ["Reasoning about black boxes", "Contracts; Galois connections; Yoneda", "Runtime boundary checks; substitution by proof; provably sound summaries"],
        ["Indexing everything", "Fibrations / Grothendieck", "New model kinds require no schema migration"],
        ["Many regulators at once", "Institutions (Goguen–Burstall)", "New regulators require no migration; scope becomes a citable derivation"],
        ["Evidence and risk", "Semirings, lattices, bitemporal algebra", "One evidence engine answers nine questions by swapping the arithmetic"]]
th = table(sl, data, ML, y + 1.22, CW, col_w=[2.6, 3.3, 5.6], row_h=0.44, fs=11, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 1.22 + th + 0.24, CW, 0.4)
para(tf, "None of the mathematics is new. The contribution is the assembly, plus the results it makes visible.",
     size=11.5, color=SLATE, italic=True, first=True, space_after=0)

sl, y = content("What is a model, formally?", "A formal foundation · pillar 1")
rect(sl, ML, y, CW, 1.25, fill=PARCH)
rect(sl, ML, y, 0.05, 1.25, fill=CRIMSON)
tf = txt(sl, ML + 0.40, y + 0.17, CW - 0.8, 0.45, align=PP_ALIGN.CENTER)
para(tf, "f  :  P ⊗ X  →  Y", size=26, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
tf = txt(sl, ML + 0.40, y + 0.70, CW - 0.8, 0.5, align=PP_ALIGN.CENTER)
runs(tf, [("a ", SLATE, False), ("parameter object", INK, True), (" P — the dials — an ", SLATE, False),
          ("input", INK, True), (" X, an ", SLATE, False), ("output", INK, True),
          (" Y, and a kernel consuming parameters and input to produce output, possibly at random", SLATE, False)],
     size=12, first=True, space_after=0)
tf = txt(sl, ML, y + 1.55, CW * 0.47, 2.4)
para(tf, "Why a Markov category, not plain functions", size=13.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("Copying is explicit", "One output feeding two consumers is visible structure — decisive two slides from now"),
             ("Discarding is explicit", "Outputs need not be used, which is what makes exposure a separate quantity"),
             ("Determinism is a property", "f commutes with copy — and that is exactly the reproducibility test")], size=12, gap=8)
x = ML + CW * 0.53
tf = txt(sl, x, y + 1.55, CW * 0.47, 2.4)
para(tf, "The move that does the work", size=13.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
runs(tf, [("Separating ", SLATE, False), ("P", CRIMSON, True), (" from ", SLATE, False), ("f", CRIMSON, True),
          (" replaces an unanswerable question — ", SLATE, False), ("“what kind of model is this?”", INK, True, True),
          (" — with a precise one:", SLATE, False)], size=12.5, space_after=10, line=1.25)
rect(sl, x, y + 2.62, CW * 0.47, 0.60, fill=CRIMSON)
tf = txt(sl, x + 0.2, y + 2.75, CW * 0.47 - 0.4, 0.4, align=PP_ALIGN.CENTER)
para(tf, "How do the dials get set?", size=15, color=WHITE, bold=True, font=SERIF, first=True, space_after=0)

sl, y = content("Nine kinds of artefact, one kind of thing", "A formal foundation · the classification")
data = [["", "Class", "Parameter object P", "How P is filled — the fitting morphism φ", "Example"],
        ["T0", "Analytic", "empty — terminal object", "It is not. The fitting question is vacuous.", "Black–Scholes, SA-CCR"],
        ["T1", "Calibrated", "calibration parameters", "A solver, against market instruments, daily", "SABR vol surface"],
        ["T2", "Estimated", "coefficients", "A statistical estimator on a sample", "PD scorecard, PPNR"],
        ["T3", "Learned", "weights, hyperparameters", "A training algorithm", "Fraud classifier"],
        ["T4", "Adaptive", "parameters indexed by time", "A process, running continuously", "Adaptive AML threshold"],
        ["T5", "Foundation-based", "weights, prompt, corpus, tools", "Configuration and retrieval", "Narrative drafting"],
        ["T6", "Opaque", "exists but inaccessible", "External and unavailable", "Bureau credit score"],
        ["T7", "Elicited", "weights or thresholds", "An elicitation protocol over a panel", "Country-risk scorecard"],
        ["T8", "Authored", "the rule set", "Somebody wrote it down", "AML scenarios, EUCs"]]
th = table(sl, data, ML, y, CW, col_w=[0.55, 1.75, 2.7, 4.1, 2.5], row_h=0.325, fs=10.5, hfs=10.5,
      align=[PP_ALIGN.CENTER]+[PP_ALIGN.LEFT]*4, first_col_color=CRIMSON, bold_col0=True)
tf = txt(sl, ML, y + th + 0.26, CW, 0.6)
runs(tf, [("T0 is not a degenerate model — it is the case P ≅ I. ", CRIMSON, True),
          ("Asking it for a training set is a type error, and the system can now say so. T6 is characterised by ", INK, False),
          ("inaccessibility", INK, True, True),
          (" of P — which is exactly why only behavioural evidence is obtainable from a vendor model.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.3)

def node(sl, x, yy, w, h, label, sub, fill=WHITE, line=CRIMSON):
    rect(sl, x, yy, w, h, fill=fill, line=line, lw=1.2)
    tfn = txt(sl, x + 0.06, yy + 0.05, w - 0.12, h - 0.10,
              align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    para(tfn, label, size=10.5, color=INK, bold=True, first=True, space_after=0)
    para(tfn, sub, size=8, color=MUTED, align=PP_ALIGN.CENTER, space_after=0)
def arrow(sl, x1, y1, x2, y2):
    c = sl.shapes.add_connector(1, In(x1), In(y1), In(x2), In(y2))
    c.line.color.rgb = SLATE; c.line.width = Pt(1.5)

sl, y = content("Aggregate risk cannot be computed from the parts", "A formal foundation · an impossibility result")
tf = txt(sl, ML, y, CW, 0.42)
runs(tf, [("Supervisory guidance requires aggregate risk reflecting ", INK, False),
          ("“interactions and dependencies among models; reliance on common assumptions, data, or methodologies.”", CRIMSON, True, True),
          ("  In practice, aggregates are computed as the maximum of component ratings.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
by = y + 0.70
rect(sl, ML, by, CW * 0.46, 1.95, fill=WHITE, line=RULE)
tf = txt(sl, ML + 0.25, by + 0.13, CW * 0.46 - 0.5, 0.3)
para(tf, "NETWORK 1  —  one curve, two consumers", size=10, color=CRIMSON, bold=True, first=True, space_after=0)
node(sl, ML + 0.35, by + 0.68, 1.5, 0.56, "A  curve", "risk a", fill=PARCH_D)
node(sl, ML + 2.55, by + 0.50, 1.15, 0.48, "B", "risk b")
node(sl, ML + 2.55, by + 1.15, 1.15, 0.48, "C", "risk b")
arrow(sl, ML+1.85, by+0.97, ML+2.55, by+0.71); arrow(sl, ML+1.85, by+0.97, ML+2.55, by+1.36)
tf = txt(sl, ML + 3.92, by + 0.68, 1.32, 0.85)
para(tf, "fragility = 2", size=11.5, color=CRIMSON, bold=True, first=True, space_after=2)
para(tf, "one failure,", size=8.5, color=MUTED, space_after=0)
para(tf, "two outputs lost", size=8.5, color=MUTED, space_after=0)
x2 = ML + CW * 0.54
rect(sl, x2, by, CW * 0.46, 1.95, fill=WHITE, line=RULE)
tf = txt(sl, x2 + 0.25, by + 0.13, CW * 0.46 - 0.5, 0.3)
para(tf, "NETWORK 2  —  two independent curves", size=10, color=NAVY, bold=True, first=True, space_after=0)
node(sl, x2 + 0.35, by + 0.50, 1.5, 0.48, "A  curve", "risk a", fill=PARCH_D)
node(sl, x2 + 0.35, by + 1.15, 1.5, 0.48, "A′ curve", "risk a", fill=PARCH_D)
node(sl, x2 + 2.55, by + 0.50, 1.15, 0.48, "B", "risk b")
node(sl, x2 + 2.55, by + 1.15, 1.15, 0.48, "C", "risk b")
arrow(sl, x2+1.85, by+0.71, x2+2.55, by+0.71); arrow(sl, x2+1.85, by+1.36, x2+2.55, by+1.36)
tf = txt(sl, x2 + 3.92, by + 0.68, 1.32, 0.85)
para(tf, "fragility = 1", size=11.5, color=NAVY, bold=True, first=True, space_after=2)
para(tf, "one failure,", size=8.5, color=MUTED, space_after=0)
para(tf, "one output lost", size=8.5, color=MUTED, space_after=0)
rect(sl, ML, y + 2.90, CW, 1.30, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + 3.03, CW - 0.7, 1.1)
para(tf, "Theorem.  No risk assignment is both compositional and sensitive to shared dependency.",
     size=15, color=WHITE, bold=True, font=SERIF, first=True, space_after=7)
runs(tf, [("Both networks contain the same component risks {a, b, b}, so any compositional measure gives them the same aggregate. They are plainly not equally exposed.  ",
           RGBColor(0xF6,0xE0,0xE4), False),
          ("The difference is exactly one thing: Network 1 copies. Shared dependency is the copy map — invisible in ordinary function composition, explicit in a Markov category.",
           WHITE, True)], size=11.5, space_after=0, line=1.25)

sl, y = content("Contracts, fibrations, institutions", "A formal foundation · pillars 3–5")
cw3 = (CW - 0.5 * 2) / 3
items = [("Contracts", "Assume–guarantee algebra",
          "An operating boundary is an assumption A; a performance envelope is a guarantee G. Outside A, G is formally void — a much stronger statement than “results may be unreliable”.",
          "Substitution becomes a proof obligation: the replacement's contract must refine the incumbent's. Decidable, not a judgement call."),
         ("Fibrations", "Grothendieck construction",
          "Make “kind of model” the index of a family, not a column. Each kind supplies its own fibre: evidence schema, lifecycle, metrics, templates.",
          "Conservative extension: adding a fibre leaves every existing fibre untouched. New kinds — including ones not yet invented — are a plugin, not a migration."),
         ("Institutions", "Goguen–Burstall, 1992",
          "A regulator is a logical system: its own vocabulary, its own sentences, its own notion of truth over an inventory. Regimes are institutions; translations are comorphisms.",
          "The satisfaction condition — truth is invariant under change of notation — gives a falsifiable consistency test for a regulatory encoding.")]
for i, (t, sub, body, res) in enumerate(items):
    x = ML + i * (cw3 + 0.5)
    rect(sl, x, y, cw3, 3.5, fill=WHITE, line=RULE)
    rect(sl, x, y, cw3, 0.055, fill=CRIMSON)
    tfc = txt(sl, x + 0.26, y + 0.26, cw3 - 0.52, 3.1)
    para(tfc, t, size=16, color=INK, bold=True, font=SERIF, first=True, space_after=3)
    para(tfc, sub, size=10, color=CRIMSON, bold=True, space_after=11)
    para(tfc, body, size=11, color=SLATE, space_after=11, line=1.25)
    runs(tfc, [("Result: ", CRIMSON, True), (res, INK, False)], size=11, line=1.25)

sl, y = content("Evidence over a semiring: one engine, nine questions", "A formal foundation · pillar 6")
tf = txt(sl, ML, y, CW, 0.42)
runs(tf, [("Governance claims have a fixed shape: this rests on that ", INK, False), ("AND", CRIMSON, True),
          (" that; this can be met by this route ", INK, False), ("OR", CRIMSON, True),
          (" that. Keep the shape, swap the arithmetic, and the same computation answers a different question.", INK, False)],
     size=12.5, first=True, space_after=0)
data = [["Semiring", "⊕ , ⊗", "Governance question it answers"],
        ["Boolean", "∨ , ∧", "Is the claim supported at all?  →  gate evaluation"],
        ["Natural numbers", "+ , ×", "How many independent derivations corroborate it?"],
        ["Why-provenance", "∪ , pairwise ∪", "Which minimal evidence sets suffice?  →  what to show an examiner"],
        ["Polynomials ℕ[X]", "+ , ×", "Exactly how was it derived?  →  full audit reconstruction"],
        ["([0,1], max, ×)", "max , ×", "With what confidence?  →  trust scoring"],
        ["Tropical (min, +)", "min , +", "Cheapest path to close this gap?  →  remediation planning"],
        ["Security lattice", "⊓ , ⊔", "What classification does the conclusion inherit?"],
        ["Regime sets", "∩ , ∪", "For which regulators is this evidence admissible?"],
        ["(Time, max, max)", "max , max", "As of when is this claim current?  →  staleness"]]
th = table(sl, data, ML, y + 0.52, CW, col_w=[2.4, 1.9, 7.2], row_h=0.305, fs=11, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 0.52 + th + 0.24, CW, 0.55)
runs(tf, [("ℕ[X] is universal. ", CRIMSON, True),
          ("Compute once in polynomials; every other answer follows by homomorphism. Nine capabilities, one implementation — and they cannot disagree. Hold on to this: it returns in the next chapter.",
           INK, False)], size=12.5, first=True, space_after=0)

# ============================================================ CH 3 — AI
divider("3", "Automation and Its Oracles", "The structure was built for governance. It answers a question nobody asked it.",
        ["The wrong question and the right one", "Verified automation",
         "Which tasks are oracle-backed", "Grounding as a computation",
         "What admits no oracle", "Models governing models"])

sl, y = content("The wrong question, and the right one", "Automation · the criterion")
bw = (CW - 0.7) / 2
rect(sl, ML, y, bw, 1.55, fill=WHITE, line=RULE)
rect(sl, ML, y, bw, 0.055, fill=MUTED)
tf = txt(sl, ML + 0.28, y + 0.26, bw - 0.56, 1.2)
para(tf, "What everyone asks", size=14, color=SLATE, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "“Is the model good enough for this task?”", size=13, color=SLATE, italic=True, space_after=7)
para(tf, "Answered by benchmarks, pilots, and a review process whose control is “a competent human checks it”.",
     size=11, color=MUTED, space_after=0, line=1.22)
rect(sl, ML + bw + 0.7, y, bw, 1.55, fill=WHITE, line=CRIMSON, lw=1.3)
rect(sl, ML + bw + 0.7, y, bw, 0.055, fill=CRIMSON)
tf = txt(sl, ML + bw + 0.98, y + 0.26, bw - 0.56, 1.2)
para(tf, "What we should ask", size=14, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "“Do I have a check?”", size=13, color=INK, italic=True, bold=True, space_after=7)
para(tf, "Answered by the structure. Either a decision procedure exists for this task, or it does not — and that is a fact about the domain, not about the model.",
     size=11, color=SLATE, space_after=0, line=1.22)
rect(sl, ML, y + 1.90, CW, 1.05, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + 2.06, CW - 0.7, 0.8)
para(tf, "Deploy AI where the formalism gives you a mechanical check on the AI's output. Use humans where it does not.",
     size=16, color=WHITE, italic=True, font=SERIF, first=True, space_after=0, line=1.25)
tf = txt(sl, ML, y + 3.20, CW, 1.0)
runs(tf, [("This criterion is not generally available. ", INK, True),
          ("It is available here because the constructions of the last chapter are decision procedures: the satisfaction condition checks a regulatory encoding, "
           "Why-provenance checks a citation, contract refinement checks a substitution, probe-relative equivalence checks a behavioural claim. "
           "Elsewhere, “the model might be wrong” is managed with review and hope. Here, for a meaningful fraction of the work, it is managed with a test.",
           SLATE, False)], size=12.5, first=True, space_after=0, line=1.3)

sl, y = content("Verified automation", "Automation · the proposition")
rect(sl, ML, y, CW, 1.55, fill=PARCH)
rect(sl, ML, y, 0.05, 1.55, fill=CRIMSON)
tf = txt(sl, ML + 0.40, y + 0.16, CW - 0.8, 1.3)
para(tf, "Proposition (Automation admissibility).", size=14, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=6)
para(tf, "If a task is oracle-backed, the soundness of verified automation is independent of the generator: no incorrect output is accepted, whatever produced it. The generator's error rate determines throughput, not correctness.",
     size=12.5, color=INK, space_after=6, line=1.28)
para(tf, "If a task is not oracle-backed, the correctness of the output is exactly the correctness of the generator.",
     size=12.5, color=INK, space_after=0, line=1.28)
tf = txt(sl, ML, y + 1.85, CW * 0.47, 2.2)
para(tf, "In plain terms", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "If you can check an answer, it does not matter very much who or what produced it. A wrong answer is caught and discarded; the only cost is wasted effort.",
     size=12, color=SLATE, space_after=8, line=1.28)
para(tf, "If you cannot check the answer, then trusting the answer is trusting the producer — and no amount of process changes that.",
     size=12, color=SLATE, space_after=0, line=1.28)
x = ML + CW * 0.53
rect(sl, x, y + 1.85, CW * 0.47, 2.2, fill=WHITE, line=RULE)
tf = txt(sl, x + 0.26, y + 2.02, CW * 0.47 - 0.52, 1.9)
para(tf, "Why this reframes the debate", size=13, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, ["Model capability stops being the deciding variable",
             "Hallucination becomes a throughput cost, not a risk",
             "Base-model upgrades stop being governance events for checked tasks",
             "The boundary is a property of the domain — stable as models improve"], size=11.5, gap=6)

sl, y = content("Which governance tasks are oracle-backed", "Automation · the map")
data = [["Task", "The oracle", "From"],
        ["Encode a regulatory regime", "The satisfaction condition holds for the proposed translation", "Institutions"],
        ["Assert two versions behave alike", "Equivalence on the declared probe set", "Probe-relative Yoneda"],
        ["Substitute one version for another", "Contract refinement", "Contract algebra"],
        ["Re-express an artefact in another format", "Probe equivalence plus numerical tolerance", "Contract algebra"],
        ["Claim documentary support for an assertion", "Boolean evaluation of the derivation under the cited set", "Provenance semirings"],
        ["Assemble fitting evidence without leakage", "Causal admissibility over two clocks", "Bitemporal algebra"],
        ["Propose a remediation plan", "None needed — the plan is computed in the tropical semiring", "Provenance semirings"],
        ["Propose a probe", "It executes and discriminates, or it does not", "—"],
        ["Propose a query", "It parses, type-checks and returns, or it does not", "—"]]
th = table(sl, data, ML, y, CW, col_w=[4.4, 5.4, 1.8], row_h=0.365, fs=11, bold_col0=True, first_col_color=CRIMSON)
cy = y + th + 0.26
rect(sl, ML, cy, CW, 0.95, fill=PARCH)
rect(sl, ML, cy, 0.045, 0.95, fill=CRIMSON)
tf = txt(sl, ML + 0.30, cy + 0.14, CW - 0.6, 0.75)
runs(tf, [("The first row inverts an apparent weakness. ", CRIMSON, True),
          ("Encoding a forty-page supervisory statement is expensive expert work — the practical objection to the whole institutions approach. "
           "It is also a task language models are unusually good at, and the output is checkable. Generation becomes cheap; verification is mechanical; "
           "the expert moves from authoring to adjudicating something that has already passed a consistency test.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.25)

sl, y = content("Grounding verification is a computation, not a judgement", "Automation · the sharpest result")
tf = txt(sl, ML, y, CW, 0.70)
runs(tf, [("The dominant failure of machine-generated governance text is the unsupported assertion. The standard mitigation — retrieval with citations — leaves ", INK, False),
          ("“does this source actually support this claim?”", CRIMSON, True, True),
          (" to a further model call. Over an annotated derivation structure, it is arithmetic.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
rect(sl, ML, y + 0.80, CW, 0.95, fill=PARCH)
rect(sl, ML, y + 0.80, 0.05, 0.95, fill=CRIMSON)
tf = txt(sl, ML + 0.40, y + 0.94, CW - 0.8, 0.75)
para(tf, "Proposition (Citation soundness).", size=13.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=5)
para(tf, "A cited evidence set S supports a claim c if and only if the claim's derivation evaluates to true in the Boolean semiring when exactly the identifiers in S are switched on — equivalently, iff S contains a minimal support of c.",
     size=12, color=INK, space_after=0, line=1.28)
tf = txt(sl, ML, y + 1.96, CW, 0.35)
para(tf, "Worked: a drafted paragraph, checked", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=0)
rect(sl, ML, y + 2.33, CW, 0.62, fill=WHITE, line=RULE)
tf = txt(sl, ML + 0.26, y + 2.46, CW - 0.52, 0.45)
para(tf, "“Version 3.2.1 was approved for small-business origination following independent validation, which found discrimination within tolerance on all monitored slices.”",
     size=12, color=INK, italic=True, first=True, space_after=0, line=1.2)
tf = txt(sl, ML, y + 3.10, CW * 0.48, 1.3)
runs(tf, [("Cites  ", MUTED, False), ("S = { VR, APPR }", NAVY, True, False, "Consolas")], size=11.5, first=True, space_after=6)
para(tf, "Derivation:  (T₁·T₂·T₃·REP) · VR · (APPR + APPR′)", size=10.5, color=SLATE, space_after=6)
runs(tf, [("Under S the test factors are false, so the product is ", SLATE, False), ("false", CRIMSON, True),
          (". The citation is incomplete — rejected, with the missing identifiers named.", SLATE, False)], size=11, line=1.22)
x = ML + CW * 0.52
rect(sl, x, y + 3.10, CW * 0.48, 1.28, fill=PARCH)
rect(sl, x, y + 3.10, 0.045, 1.28, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 3.23, CW * 0.48 - 0.5, 1.1)
runs(tf, [("And the second clause. ", CRIMSON, True),
          ("“On all monitored slices” is a quantified claim with no supporting monomial at all. It is rejected as unsupported rather than published as plausible — "
           "and it is exactly the sentence human review reliably misses, because it reads like the rest.", INK, False)],
     size=11, first=True, space_after=0, line=1.22)

sl, y = content("What admits no oracle — a category, not a caution", "Automation · the boundary")
rect(sl, ML, y, CW, 1.15, fill=PARCH)
rect(sl, ML, y, 0.05, 1.15, fill=CRIMSON)
tf = txt(sl, ML + 0.40, y + 0.15, CW - 0.8, 0.95)
para(tf, "Observation (Constitutivity).", size=13.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=5)
para(tf, "For a derived quantity defined as f(facts) by a versioned rule f — a risk tier, a control requirement, a scope determination — there is no automation question about computing it. Evaluating f is deterministic. The automation question arises only for supplying the facts, and for proposing f.",
     size=12, color=INK, space_after=0, line=1.28)
tf = txt(sl, ML, y + 1.42, CW * 0.47, 3.0)
para(tf, "This reframes the usual debate", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=8)
runs(tf, [("“Should we let a model assign risk tiers?” is malformed. ", CRIMSON, True),
          ("Assigning a tier is not a generation task — it is arithmetic on a rule everyone agreed to. A spreadsheet could do it.",
           SLATE, False)], size=12, space_after=9, line=1.28)
para(tf, "The real questions are: where do the facts come from — checkable by reconciliation — and who chose the rule, which is an exercise of authority.",
     size=12, color=SLATE, space_after=9, line=1.28)
runs(tf, [("Automating the second is not risky-but-tempting. It is a category error, because ", SLATE, False),
          ("a rule that constitutes a standard cannot be checked against that standard.", INK, True)], size=12, line=1.28)
x = ML + CW * 0.53
tf = txt(sl, x, y + 1.42, CW * 0.47, 0.32)
para(tf, "No oracle exists — human decision only", size=13, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
data = [["Decision", "Why no oracle"],
        ["Conclude a validation", "Effective challenge is defined by standing and accountability, which a model has not"],
        ["Assign or override a tier", "The rule constitutes the standard"],
        ["Make a scope determination", "Discards the derivation that is the point"],
        ["Approve anything", "An accountable act with a signature behind it"],
        ["Accept residual risk", "Requires authority"],
        ["Close a finding", "Independent verification by a person who did not raise it"],
        ["Compute a metric", "Do not ask a language model for a Gini coefficient"]]
table(sl, data, x, y + 1.78, CW * 0.47, col_w=[2.1, 3.8], row_h=0.30, fs=9.5, hfs=10, bold_col0=True)

sl, y = content("Models governing models — is that circular?", "Automation · stratification")
tf = txt(sl, ML, y, CW, 0.4)
runs(tf, [("A platform that governs AI, using AI, sounds like it should collapse. It does not — and the reason is structural, not good intentions.", INK, False)],
     size=12.5, first=True, space_after=0)
gy = y + 0.60
rect(sl, ML, gy, CW * 0.52, 1.55, fill=CRIMSON)
tf = txt(sl, ML + 0.30, gy + 0.16, CW * 0.52 - 0.6, 1.25)
para(tf, "The governing layer  G", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=6)
para(tf, "The classification map, the evidence structure, the institutions, the lifecycle categories. None of it is AI. None of it is an element of the governed population.",
     size=11.5, color=RGBColor(0xF6,0xE0,0xE4), space_after=0, line=1.25)
rect(sl, ML, gy + 1.80, CW * 0.52, 1.55, fill=NAVY)
tf = txt(sl, ML + 0.30, gy + 1.96, CW * 0.52 - 0.6, 1.25)
para(tf, "The governed population  A", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=6)
para(tf, "Every model the bank runs — and every AI assistant the platform uses. Each has a parameter object, a fitting morphism, a contract, a classification, evidence.",
     size=11.5, color=RGBColor(0xDC,0xE4,0xEE), space_after=0, line=1.25)
c = sl.shapes.add_connector(1, In(ML + CW*0.26), In(gy + 1.80), In(ML + CW*0.26), In(gy + 1.55))
c.line.color.rgb = WHITE; c.line.width = Pt(2)
x = ML + CW * 0.56
tf = txt(sl, x, gy, CW * 0.44, 3.4)
para(tf, "One dependency crosses the strata", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "If an assistant drafts a regime encoding, part of the governing layer was produced with help from the governed one. Naming this rather than hiding it:",
     size=11.5, color=SLATE, space_after=9, line=1.25)
runs(tf, [("The dependency is mediated by an oracle that is itself not machine-produced — the satisfaction condition is a theorem, evaluated mechanically.",
           INK, False)], size=11.5, space_after=12, line=1.25)
rect(sl, x, gy + 1.75, CW * 0.44, 0.75, fill=PARCH_D)
tf = txt(sl, x + 0.2, gy + 1.88, CW * 0.44 - 0.4, 0.55, align=PP_ALIGN.CENTER)
para(tf, "Generation may cross the strata.", size=13, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=3)
para(tf, "Acceptance may not.", size=13, color=CRIMSON, bold=True, font=SERIF, align=PP_ALIGN.CENTER, space_after=0)
tf = txt(sl, x, gy + 2.68, CW * 0.44, 0.7)
para(tf, "Put another way: a machine may propose anything and decide nothing.",
     size=11.5, color=SLATE, italic=True, first=True, space_after=0, line=1.25)

# ============================================================ CH 4
divider("4", "Discussion", "What follows, what is missing, and what I would like to argue about.",
        ["A worked example", "Limitations", "The generalisation", "Questions"])

sl, y = content("One estate, five artefacts, one apparatus", "Discussion · worked example")
ny = y + 0.35
node(sl, ML, ny + 0.95, 1.75, 0.60, "A  curve", "T1 · calibrated", fill=PARCH_D)
node(sl, ML + 2.45, ny + 0.10, 1.75, 0.60, "B  pricer", "T1")
node(sl, ML + 2.45, ny + 1.80, 1.75, 0.60, "C  XVA", "T1")
node(sl, ML + 4.90, ny + 0.95, 1.75, 0.60, "L  drafting", "T5 · foundation")
node(sl, ML + 4.90, ny + 2.30, 1.75, 0.60, "S  scorecard", "T2 · estimated")
arrow(sl, ML+1.75, ny+1.25, ML+2.45, ny+0.40); arrow(sl, ML+1.75, ny+1.25, ML+2.45, ny+2.10)
arrow(sl, ML+4.20, ny+0.40, ML+4.90, ny+1.25); arrow(sl, ML+4.20, ny+2.10, ML+4.90, ny+1.25)
x = ML + 7.2
tf = txt(sl, x, y, CW - 7.2, 4.2)
para(tf, "One apparatus, five different answers", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=9)
bullets(tf, [("Aggregate risk", "A is copied to B and C. The composite risk strictly exceeds the join of the parts; the premium is attributable to the shared curve."),
             ("Plural scope", "Under a narrow regime L is out of scope as generative; under a broad one it is in; under product-safety law S alone is high-risk. Four correct answers to four different questions."),
             ("Evidence", "The claim “C is authorised” evaluated in Why-provenance returns what to show an examiner; in max–max it exposes any document predating today's recalibration."),
             ("Automation", "Four tasks here are oracle-backed and may be generated by anything. Two — what tier C occupies, whether L's residual risk is acceptable — are not automation questions at all.")],
        size=11, gap=7, indent_size=9.5)

sl, y = content("Limitations, stated rather than discovered", "Discussion · what this does not establish")
lims = [("No implementation study",
         "The account is conceptual. I have not shown that a system built this way is cheaper to build or operate. That is the missing evidence and the natural sequel."),
        ("Expressiveness is imperfect",
         "Stateful simulation engines and agentic systems fit only by absorbing state into the input object — faithful but inelegant. Coalgebra or open games may be the better home. Unsettled."),
        ("Formalising regulation is lossy",
         "An institution encoding is a claim about a regulation, not the regulation. What you gain is that the claim is explicit, citable and testable for consistency. What you do not gain is being right."),
        ("Oracles are necessary, not sufficient",
         "The proposition guarantees no incorrect output is accepted. It says nothing about what a fluent unchecked output does to the human attesting to it. Fluency reads as quality; it is not."),
        ("The boundary may be drawn too conveniently",
         "Constitutivity classifies the decisions that matter most as human-only — a comfortable conclusion for anyone who wants humans to keep them. I believe the argument; I note that I would.")]
cw2 = (CW - 0.3 * 2) / 3
for i, (t, d) in enumerate(lims):
    card(sl, ML + (i % 3) * (cw2 + 0.3), y + (i // 3) * 2.52, cw2, 2.32, f"0{i+1}", t, d)
rect(sl, ML + 2 * (cw2 + 0.3), y + 2.52, cw2, 2.32, fill=CRIMSON)
tf = txt(sl, ML + 2 * (cw2 + 0.3) + 0.26, y + 2.68, cw2 - 0.52, 2.10)
para(tf, "What would falsify it", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=7)
bullets(tf, ["An artefact class that resists presentation as a (P, φ) pair",
             "A compositional yet fragility-sensitive risk measure",
             "An oracle-backed task where automation did worse than manual work",
             "Practitioners unable to use the derivations at all"],
        size=10, gap=6, color=RGBColor(0xF6,0xE0,0xE4), bullet_color=RGBColor(0xE8,0xB8,0xC0))

sl, y = content("The generalisation", "Discussion")
tf = txt(sl, ML, y + 0.15, CW, 2.1)
para(tf, "Wherever an organisation is deciding how much of a judgement-laden process to hand to a language model, the useful first question is not how good the model is.",
     size=19, color=INK, font=SERIF, first=True, space_after=16, line=1.3)
para(tf, "It is: what, in this domain, could ever tell us that the answer was wrong?",
     size=22, color=CRIMSON, bold=True, font=SERIF, space_after=0, line=1.28)
rect(sl, ML, y + 2.05, CW, 0.035, fill=RULE)
tf = txt(sl, ML, y + 2.35, CW * 0.47, 1.8)
para(tf, "If there is an answer", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Generation is nearly free, because acceptance is checked. Model choice becomes an efficiency question. Capability improvements are upside, not governance events. Build aggressively.",
     size=12, color=SLATE, space_after=0, line=1.28)
x = ML + CW * 0.53
tf = txt(sl, x, y + 2.35, CW * 0.47, 1.8)
para(tf, "If there is not", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "No review process rescues you, because the reviewer faces the same absence of a standard. Either build the structure that supplies one — which is what this paper is about — or keep the decision with a person who can be held to account.",
     size=12, color=SLATE, space_after=0, line=1.28)

sl, y = content("Questions I would like to argue about", "Discussion")
qs = [("01", "Is the constitutivity argument right?",
       "I claim a rule that defines a standard cannot be checked against that standard, so tiering and approval admit no oracle. Is there a construction I am missing — a meta-standard, a revealed-preference oracle from historical outcomes?"),
      ("02", "Where else does the oracle criterion apply?",
       "Clinical decision support, insurance reserving, public eligibility determination — same shape, heterogeneous artefacts under one obligation. Does the criterion survive contact with domains that have weaker formal structure?"),
      ("03", "Does fluency defeat us anyway?",
       "Citation checking covers claims. It does not cover the effect of a polished artefact on the person attesting to it. Is measuring reviewer edit distance enough, or is there a better instrument?"),
      ("04", "What is the right home for agents?",
       "Stateful, action-taking systems fit this account awkwardly. Coalgebra? Open games? Or is the honest answer that agentic governance needs a different foundation than model governance?"),
      ("05", "Would practitioners actually use it?",
       "A scope determination as a failing conjunct with a citation is more defensible than a checkbox with a comment — if anyone reads it. That is an empirical claim about human factors and I cannot settle it from the armchair."),
      ("06", "Is “propose anything, decide nothing” stable?",
       "Commercial pressure will push assistants toward deciding, from sensible people with good reasons. Is an architectural prohibition — no credential for a governance transition — enough, or does it erode?")]
cw2 = (CW - 0.3 * 2) / 3
for i, (n, t, d) in enumerate(qs):
    card(sl, ML + (i % 3) * (cw2 + 0.3), y + (i // 3) * 2.52, cw2, 2.32, n, t, d)

_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
tf = txt(sl, ML + 0.4, 1.95, CW * 0.82, 2.2)
para(tf, "A machine may propose anything", size=34, color=WHITE, font=SERIF, first=True, space_after=6)
para(tf, "and decide nothing.", size=34, color=WHITE, font=SERIF, space_after=0)
rect(sl, ML + 0.4, 3.72, 1.6, 0.035, fill=RGBColor(0xE8,0xB8,0xC0))
tf = txt(sl, ML + 0.4, 4.00, CW * 0.72, 1.4)
para(tf, "Ashutosh Sinha", size=18, color=WHITE, bold=True, first=True, space_after=4)
para(tf, "Independent Researcher   ·   ajsinha@gmail.com", size=12, color=RGBColor(0xF2,0xD8,0xDC), space_after=14)
para(tf, "Full treatment — including the impossibility proof, the conservative-extension and satisfaction-condition results, the semiring construction for assurance evidence, and what was deliberately not adopted — in the accompanying paper.",
     size=10.5, color=RGBColor(0xE8,0xC4,0xCA), line=1.3)

import sys
prs.save(sys.argv[1])
print("slides:", len(prs.slides._sldIdLst))
