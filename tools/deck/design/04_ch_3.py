# ============================================================ CH 3
divider("3", "Governance Subsystems", "Evidence, risk, regimes, lifecycle, validation, documentation.",
        ["Evidence append and chain", "Semiring evaluation", "The tiering algorithm",
         "Anti-gaming", "Institutions in code", "Lifecycle and baseline import"])

sl, y = content("Evidence engine — append and chain", "Governance · evidence")
h = code(sl, ML, y, CW * 0.60, [
 "with uow.lock(\"evidence_chain\"):        # serialises seq only",
 "    prev = evidence.head()",
 "    node = EvidenceNode(",
 "        seq = prev.seq + 1,",
 "        payload = {} if personal_data else payload,     # law L-18",
 "        payload_uri = delta.put(payload) if personal_data else None,",
 "        content_hash = sha256(canonical_json(...)),",
 "        prev_hash    = prev.chain_hash,",
 "        chain_hash   = sha256(f\"{seq}|{prev_hash}|{content_hash}|\"",
 "                              f\"{sorted(parent.chain_hash)}\"),",
 "    )",
 "    evidence.insert(node)                # INSERT-only database role",
], fs=9.5, title="APPEND PATH")
x = ML + CW * 0.64
tf = txt(sl, x, y, CW * 0.36, 3.5)
para(tf, "Chain over DAG — why both", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("The DAG expresses derivation", "what supports what"),
             ("The linear chain expresses order", "so deletion of a leaf and insertion into the past become detectable"),
             ("Anchored daily", "chain head written to WORM and an RFC-3161 timestamp — self-consistency of a chain an attacker controls proves nothing"),
             ("Personal data is never inline", "only an erasable pointer, so crypto-shredding leaves the chain valid")],
        size=11, gap=7, indent_size=9.5)

sl, y = content("One engine, six questions", "Governance · semiring evaluation")
h = code(sl, ML, y, CW * 0.55, [
 "def evaluate(claim, K: Semiring[T], valuation) -> T:",
 "    def go(node):",
 "        d = derivations[node]",
 "        if d.is_leaf: return valuation(node)",
 "        r = K.zero",
 "        for alt in d.alternatives:            # OR",
 "            t = K.one",
 "            for dep in alt.requires:          # AND",
 "                t = K.times(t, go(dep))",
 "            r = K.plus(r, t)",
 "        return r",
 "    return go(claim.root)                     # memoised",
], fs=9.5, title="core/evidence/engine.py")
x = ML + CW * 0.59
data = [["Semiring", "Used by"],
        ["boolean", "Lifecycle gates, warrant resolution"],
        ["why", "Examiner packs — what must be shown"],
        ["counting", "Corroboration depth"],
        ["trust", "Health score, AI-draft discounting"],
        ["cost", "Remediation planning, capacity"],
        ["freshness", "Document staleness"],
        ["— not built —", "ℕ[X], classification, regime admissibility"]]
th = table(sl, data, x, y, CW * 0.41, col_w=[1.6, 3.2], row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + th + 0.22, CW * 0.41, 0.95)
runs(tf, [("Without ℕ[X] there is no universal object, ", CRIMSON, True),
          ("so each semiring is its own traversal of the same memoised DAG rather than a "
           "homomorphic image of one. Six questions, one implementation — and the honest count.",
           INK, False)], size=10, first=True, space_after=0, line=1.22)
rect(sl, ML, y + h + 0.28, CW, 0.95, fill=PARCH)
rect(sl, ML, y + h + 0.28, 0.045, 0.95, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + h + 0.42, CW - 0.6, 0.75)
runs(tf, [("Complexity, stated honestly. ", CRIMSON, True),
          ("Why-provenance is worst-case exponential in the number of alternatives. Controls: absorption "
           "(a ⊕ ab = a), memoisation, and a hard 4,096-term cap beyond which evaluation stops accumulating "
           "and returns truncated=true. ", INK, False),
          ("It marks the answer partial — it does not fall back to a cheaper semiring. The marker is the control.", CRIMSON, True)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("The tiering algorithm", "Governance · risk")
h = code(sl, ML, y, CW * 0.58, [
 "facts = FactCollector(model_id).collect()      # sourced where possible",
 "rules = rulesets.get(ruleset_version)          # immutable, versioned, tested",
 "",
 "m = Materiality(quantitative = rules.exposure_band(...),",
 "                qualitative  = rules.purpose_class(...)).join()",
 "",
 "c = Complexity.meet(data=..., methodology=..., implementation=...,",
 "                    use_intensity=..., interpretability=...,",
 "                    transparency=..., bias_potential=...)",
 "",
 "tier     = rules.tau(m, c)      # monotone — law L-4",
 "controls = rules.req(tier)      # Galois adjoint — law L-5",
 "",
 "return RiskAssessment(fact_snapshot=..., ruleset_version=...,",
 "                      rationale=rules.explain(m, c, tier),   # DR-4",
 "                      next_review_due=..., triggers=...)",
], fs=9.5, title="core/risk/tiering.py")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.6)
para(tf, "Two axes, never one score", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Materiality and complexity are separate lattices. Collapsing them into a product lets a very complex model with modest exposure land beside a simple model with enormous exposure.",
     size=11, color=SLATE, space_after=10, line=1.26)
para(tf, "The guarantee", size=12.5, color=INK, bold=True, font=SERIF, space_after=7)
runs(tf, [("τ is monotone, so ", SLATE, False),
          ("nothing we can learn about a model that makes it more consequential or more complicated will ever move it into a lighter control regime.",
           INK, True), (" An unconstrained scoring formula cannot make that promise, and typically cannot even be checked.", SLATE, False)],
     size=11, line=1.26)

sl, y = content("Anti-gaming: where the facts come from", "Governance · risk")
data = [["Fact", "Source", "If unavailable"],
        ["exposure_measure", "Bound to a system of record — risk data mart, GL, portfolio system — with nightly reconciliation",
         "Marked unsourced; peer-cohort outlier detection applies; flagged on the model page"],
        ["purpose_class", "Human — but a change requires approval at the tier being LEFT, not the tier being entered", "—"],
        ["complexity components", "Derived from artifact introspection, feature contract and lineage where possible", "Human, with recorded rationale"]]
th = table(sl, data, ML, y, CW, col_w=[2.4, 5.4, 3.8], row_h=0.55, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + th + 0.30, CW * 0.48, 1.9)
para(tf, "The attack the obvious control misses", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Tier is derived, traced and monotone — so overriding it is visible. But it is derived from facts, and understating an exposure lowers the tier through a perfectly valid, fully audited derivation.",
     size=11.5, color=SLATE, space_after=0, line=1.26)
x = ML + CW * 0.54
rect(sl, x, y + th + 0.30, CW * 0.46, 1.75, fill=PARCH)
rect(sl, x, y + th + 0.30, 0.045, 1.75, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + th + 0.44, CW * 0.46 - 0.5, 1.5)
para(tf, "Retrospective calibration", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=7)
runs(tf, [("Annually, tier assignments are back-tested against realised incidents, findings and losses. ", INK, False),
          ("A tier that never predicts anything is evidence of systematic understatement — not of a quiet portfolio.", INK, True)],
     size=11.5, space_after=0, line=1.26)

sl, y = content("Institutions in code", "Governance · regimes")
h = code(sl, ML, y, CW, [
 "def determine(model_id: str, inst: Institution) -> ScopeDetermination:",
 "    core   = CoreFacts.for_model(model_id)",
 "    local  = inst.translate(core)                    # the comorphism component",
 "    result = inst.sentences[\"is_model\"].evaluate(local)",
 "    return ScopeDetermination(",
 "        regime_key=inst.key, regime_version=inst.version,",
 "        determination = \"in_scope\" if result.value else \"out_of_scope\",",
 "        derivation = {\"sentence\": \"is_model\", \"evaluated\": result.value,",
 "                      \"failing_conjunct\": result.first_false_conjunct,",
 "                      \"facts\": local.as_dict(), \"citation\": result.citation},",
 "        obligations = [s.key for s in inst.sentences if s.is_obligation and s.evaluate(local).value])",
], fs=9.5, title="core/regimes/engine.py")
tf = txt(sl, ML, y + h + 0.28, CW * 0.52, 1.9)
para(tf, "A determination is a derivation, not a flag", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "“Why is this out of scope?” is answered by the failing conjunct and a clause citation — the same answer, every time it is asked, including in five years by someone who was not there.",
     size=11.5, color=SLATE, space_after=0, line=1.26)
x = ML + CW * 0.56
rect(sl, x, y + h + 0.28, CW * 0.44, 1.75, fill=PARCH)
rect(sl, x, y + h + 0.28, 0.045, 1.75, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + h + 0.42, CW * 0.44 - 0.5, 1.5)
para(tf, "Law L-8 runs in CI", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=7)
runs(tf, [("Hypothesis generates inventory states. For each regime and sentence, evaluating natively and evaluating the translation must agree. ",
           INK, False), ("A disagreement is a defective encoding — exactly the bug that produces an indefensible scope determination.", INK, True)],
     size=11, space_after=0, line=1.26)

sl, y = content("Lifecycle, segregation of duties, and day one", "Governance · workflow")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Transitions are guarded, and guards explain", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.40, CW * 0.47, [
 "unmet = [g for g in t.guards",
 "         if not policy.evaluate(g, ctx).allow]",
 "sod   = sod_engine.violations(actor, t, m)",
 "if unmet or sod:",
 "    raise TransitionBlocked(unmet, sod)",
 "    # each entry carries a remediation link — DR-7",
], fs=9.5)
tf = txt(sl, ML, y + 0.40 + h + 0.26, CW * 0.47, 1.6)
para(tf, "Four SoD rules, read from the chain", size=12, color=INK, bold=True, font=SERIF, first=True, space_after=6)
para(tf, "creator ≠ approver · creator ≠ promoter · creator ≠ concluder of its validation · raiser ≠ closer of a finding",
     size=10.5, color=SLATE, space_after=6, line=1.24)
runs(tf, [("Read from the evidence chain, not a second table. ", CRIMSON, True),
          ("A rule may name the payload field carrying the identity it is about — a finding is raised "
           "against the model, while the act concerns one finding. Without that, raiser ≠ closer was ",
           SLATE, False),
          ("inert over HTTP", INK, True),
          (": it searched under the finding's own id, found nothing, and permitted everything.", SLATE, False)],
     size=10.5, space_after=0, line=1.24)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Baseline import — the day-one problem", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
steps(sl, x, y + 0.42, CW * 0.47, [
    ("1", "Imported", "Bulk / connector"),
    ("2", "Baselined", "Tiered, owner confirmed, debt recorded"),
    ("3", "Gate bites", "On the next MATERIAL change"),
], h=1.30)
rect(sl, x, y + 2.00, CW * 0.47, 1.55, fill=PARCH)
rect(sl, x, y + 2.00, 0.045, 1.55, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 2.14, CW * 0.47 - 0.5, 1.3)
runs(tf, [("Why this exists. ", CRIMSON, True),
          ("On import, 1,200 legacy models arrive with no evidence. Without a baseline path every gate fails, every dashboard is "
           "red, and the programme dies by month seven. Debt is a tracked burn-down with a board-approved expiry — ", INK, False),
          ("never rendered in the same colour as a breach.", INK, True)], size=11, first=True, space_after=0, line=1.24)

sl, y = content("Versioned gates — changing a control without weakening it quietly",
                "Governance · policy")
tf = txt(sl, ML, y, CW, 0.52)
runs(tf, [("A gate that cannot change without a release is a gate people work around. A gate that ", INK, False),
          ("can", INK, True),
          (" change without one is a gate that can be ", INK, False),
          ("weakened", CRIMSON, True),
          (" without one, which is worse. Everything here makes the first possible without making the second silent.", INK, False)],
     size=12, first=True, space_after=0, line=1.26)
h = code(sl, ML, y + 0.62, CW * 0.53, [
 "# a rule is a PREDICATE, not a program",
 "blocking_findings == 0 and tier is not None",
 "  and all(d in accepted for d in required_docs)",
 "",
 "# whitelisted at the AST: comparison, membership,",
 "#   and / or / not, any / all, six functions.",
 "# NO loops, assignment, def, attribute access,",
 "#   subscripting.",
], fs=9, title="core/policy/language.py")
tf = txt(sl, ML, y + 0.62 + h + 0.22, CW * 0.53, 1.25)
runs(tf, [("Rego was the obvious answer and was not taken. ", CRIMSON, True),
          ("A gate written in a general language is a program, and a reviewer signing off a "
           "governance control would have to run it to know what it does.", INK, False)],
     size=10.5, first=True, space_after=0, line=1.24)
x = ML + CW * 0.57
data = [["Property", "What it prevents"],
        ["A fact the gate does not publish is refused when the rule is WRITTEN",
         "A rule failing at the moment of a governance decision"],
        ["A policy ships with its cases, and one must REFUSE",
         "A policy nobody has shown to be a gate"],
        ["Publishing replays the OUTGOING version's cases against the new rule",
         "A loosened gate discovered rather than decided"],
        ["Authoring and publishing are separate; a published version supersedes, never edits",
         "One person changing a control end to end"]]
table(sl, data, x, y + 0.62, CW * 0.43, col_w=[2.6, 2.7], row_h=0.70, fs=9, hfs=9.5,
      bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + 4.02, CW, 0.70, fill=CRIMSON)
tf = txt(sl, ML + 0.32, y + 4.13, CW - 0.64, 0.56)
runs(tf, [("The honest boundary. ", WHITE, True),
          ("Policy tightens; the code's invariants are the floor. A rule runs in addition to the "
           "registry's checks, never instead of them — because replacing an invariant with a line of "
           "configuration means a typo can weaken the platform while the deployment looks successful.",
           RGBColor(0xF6,0xE0,0xE4), False)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("Documentation — two kinds, held apart", "Governance \u00b7 documentation")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Compiled \u2014 what the register knows", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.42, CW * 0.47, [
 "gen = [lens.render(ctx) for lens in template]",
 "doc.stale = ev.digest != prev.evidence_digest",
 "# a lens that cannot fill its section says so,",
 "# so a gap in the evidence is visible, not blank",
], fs=9.5)
tf = txt(sl, ML, y + 0.42 + h + 0.26, CW * 0.47, 1.6)
para(tf, "Four kinds, fifteen lenses. Every section records the evidence it rested on, so "
         "citation soundness is a Boolean evaluation rather than a claim. Staleness is computed "
         "from the chain head at compile time, never remembered.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Attached \u2014 what a person wrote", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
h2 = code(sl, x, y + 0.42, CW * 0.47, [
 "digest, size = store.put(bytes)   # sha256 IS the key",
 "version_id = current_version(urn) # not the model",
 "...",
 "refuse_if(actor == row.attached_by, \"self_review\")",
 "refuse_if(not accept and not note, \"reason_required\")",
], fs=9.5)
tf = txt(sl, x, y + 0.42 + h2 + 0.26, CW * 0.47, 1.6)
para(tf, "Filed against the version it describes, because an MDD describes the coefficients it "
         "printed \u2014 not their replacement. Re-hashed on read: what was accepted is what is served.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

rect(sl, ML, y + 3.62, CW, 0.98, fill=PARCH)
rect(sl, ML, y + 3.62, 0.045, 0.98, fill=CRIMSON)
tf = txt(sl, ML + 0.26, y + 3.76, CW - 0.5, 0.8)
runs(tf, [("Why both. ", CRIMSON, True),
          ("A platform that only compiles cannot hold the paper the quant actually wrote; one that only "
           "stores files is a share drive with a database in front. Held apart, the register can say which "
           "is which \u2014 and ", INK, False),
          ("a rejected document stays on file with its reason", INK, True),
          (", because the papers that did not pass are the ones a supervisor asks about.", INK, False)],
     size=11, first=True, space_after=0, line=1.24)
