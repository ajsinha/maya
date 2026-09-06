# ============================================================ CH 19
_state["chapter"] = "19 · Governance subsystems"

sl, y = content("Evidence engine — append and chain", "Governance · core/evidence/engine.py")
h = code(sl, ML, y, CW * 0.60, [
 "with self.repo.db.transaction():        # read the head, insert head+1",
 "    prev_seq, prev_hash = self.head()",
 "    stored = {} if personal_data else payload    # law L-18",
 "    content_hash = canonical_digest(",
 "        {..., \"payload\": stored,",
 "         \"recorded_by\": actor, \"trust\": trust})",
 "    self.repo.add({",
 "        \"seq\": prev_seq + 1, \"payload\": stored,",
 "        \"content_hash\": content_hash, \"prev_hash\": prev_hash,",
 "        \"chain_hash\": canonical_digest(",
 "            [seq, prev_hash, content_hash, parents])})",
 "# IntegrityError → jittered back-off, re-read the head, retry",
], fs=9.5, title="APPEND PATH")
x = ML + CW * 0.64
tf = txt(sl, x, y, CW * 0.36, 3.6)
para(tf, "Chain over DAG — why both", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("The DAG expresses derivation", "what supports what"),
             ("The chain expresses order", "so deleting a leaf or inserting into the past becomes detectable"),
             ("Who, and how much, are hashed", "segregation of duties is decided by reading recorded_by off these nodes; before it was hashed, one UPDATE turned that control off silently"),
             ("No lock — a retry", "the sequence race is lost, backed off with jitter, and re-run")],
        size=10.5, gap=6, indent_size=9.5)
note(sl, ML, y + h + 0.28, CW, 1.20,
     "Law L-18: the payload is discarded, not pointed at. ",
     "There is no payload_uri column, no per-subject key and no shred path here. “An erasable pointer” described a "
     "design nobody built, and reads as though the data is still retrievable under authority. Discarding is stronger "
     "for the law as stated — nothing to erase — and weaker for anybody who expected to resolve it later.")

sl, y = content("The anchor — because a chain that certifies itself certifies nothing",
                "Governance · core/evidence/anchor.py")
h = code(sl, ML, y, CW * 0.57, [
 "# scheduler job evidence.anchor",
 "agreement = evidence.verify_against_anchors()",
 "if not agreement[\"agrees\"]:",
 "    return refuse(...)          # never anchor over a broken chain",
 "evidence.anchor_head(actor=ctx.actor)",
 "",
 "# core/evidence/anchor.py — write-once, one file per head",
 "if self.store.exists(name):",
 "    if held[\"chain_hash\"] != chain_hash:",
 "        raise AnchorError(\"anchor_disagreement\", ...)",
 "    return {**held, \"written\": 0}     # idempotent re-run",
], fs=9.5, title="BUILT — WORMReader / WORMWriter, core/ports.py")
x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 2.4)
para(tf, "The property worth the slide", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=7)
runs(tf, [("Rewrite a node and re-link every hash after it, and ", INK, False),
          ("verify_chain reports the chain valid", INK, True),
          (". It is internally consistent, and that is all self-verification can ever ask. The anchor disagrees, "
           "because the head was written down before, on another medium. ", INK, False),
          ("tests/test_evidence_anchor.py", INK, False, False, MONO),
          (" asserts exactly that.", INK, False)],
     size=10.5, space_after=0, line=1.26)
note(sl, x, y + 2.60, CW * 0.40, 2.05,
     "And its four limits, stated in the code. ",
     "A directory is separation of medium, not enforcement — the read-only bit stops an accident, not an adversary. "
     "The medium is a deployment choice behind two ports, so S3 Object Lock changes nothing above the seam. Nothing "
     "before the first anchor can be contradicted. And RFC-3161 timestamping by an authority holding a key nobody here "
     "holds is not built.")

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
        ["polynomial  ℕ[X]", "The universal one — the rest substitute into it"]]
th = table(sl, data, x, y, CW * 0.41, col_w=[1.6, 3.2], row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + th + 0.18, CW * 0.41, 0.80)
runs(tf, [("Evaluate once in ℕ[X] ", CRIMSON, True),
          ("and every other answer is a substitution into it — law L-9. Freshness is the exception: its "
           "zero does not annihilate, so it is not a semiring, and a test says so.",
           INK, False)], size=10, first=True, space_after=0, line=1.22)
note(sl, ML, y + h + 0.62, CW, 0.95,
     "The cost of asking why, and its cap. ",
     "Why-provenance is worst-case exponential in the number of alternatives. Controls: absorption (a ⊕ ab = a), "
     "memoisation, and a hard 4,096-term cap beyond which evaluation stops accumulating and returns truncated=true. "
     "It marks the answer partial — it does not fall back to a cheaper semiring. The marker is the control.")

sl, y = content("Risk tiering — derived, monotone, and only as good as its facts",
                "Governance · risk")
tf = txt(sl, ML, y, CW, 0.62)
runs(tf, [("A risk tier is a number from 1 to 4, and nobody picks it. ", CRIMSON, True),
          ("It is derived from how consequential a model is (materiality) and how hard it is to reason about "
           "(complexity), and it decides how much control the model gets — approval quorum, scope of validation, "
           "cadence of monitoring.", INK, False)],
     size=12, first=True, space_after=0, line=1.26)
h = code(sl, ML, y + 0.72, CW * 0.56, [
 "facts = FactCollector(model_id).collect()   # sourced where possible",
 "rules = rulesets.get(ruleset_version)       # immutable, versioned",
 "m = Materiality(quantitative=..., qualitative=...).join()",
 "c = Complexity.meet(data=..., methodology=..., ...)",
 "tier     = rules.tau(m, c)      # monotone — law L-4",
 "controls = rules.req(tier)      # the controls it requires — law L-5",
 "return RiskAssessment(fact_snapshot=..., ruleset_version=...,",
 "                      rationale=rules.explain(m, c, tier))   # DR-4",
], fs=9.5, title="core/risk/tiering.py")
x = ML + CW * 0.60
tf = txt(sl, x, y + 0.72, CW * 0.40, 2.4)
para(tf, "Two axes, never one score", size=12, color=INK, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "Materiality and complexity are separate lattices. Collapsing them into a product lets a very complex model with modest exposure land beside a simple model with enormous exposure.",
     size=10.5, color=SLATE, space_after=8, line=1.24)
runs(tf, [("The map to the tier is monotone, so ", SLATE, False),
          ("nothing we can learn that makes a model more consequential or more complicated will ever move it into a lighter control regime.",
           INK, True), (" An unconstrained scoring formula cannot promise that, and usually cannot even be checked.", SLATE, False)],
     size=10.5, line=1.24)
note(sl, ML, y + 0.72 + h + 0.28, CW * 0.56, 1.60,
     "The attack the obvious control misses. ",
     "Overriding a derived tier is visible — but understating an exposure lowers it through a perfectly valid, fully "
     "audited derivation. So exposure binds to a system of record where one exists, an unsourced fact is marked and "
     "peer-cohort outlier detection applies, and a purpose_class change is approved at the tier being LEFT.")
note(sl, x, y + 0.72 + h + 0.28, CW * 0.40, 1.60,
     "Retrospective calibration. ",
     "Annually, tier assignments are back-tested against realised incidents, findings and losses. A tier that never "
     "predicts anything is evidence of systematic understatement — not of a quiet portfolio.")

sl, y = content("Version approval is a quorum, and its depth follows the tier",
                "Governance · approval")
tf = txt(sl, ML, y, CW, 0.48)
runs(tf, [("Attesting the model ", INK, False), ("record", INK, True),
          (" is not approving the ", INK, False), ("version", INK, True),
          (". The version is the thing that runs, so it carries its own quorum, and the tier sets its depth.",
           INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
data = [["Tier", "Who must sign", "Why"],
        ["1 and 2", "model_risk_manager AND validator",
         "The same rule (L-5) that decides every other control set: depth of control follows the tier"],
        ["3 and 4", "one authorised person",
         "Saying so beats pretending a scheduling heuristic deserves the ceremony of a capital model"],
        ["no tier", "— refused outright —",
         "Approving first and assessing afterwards is how a model chooses its own control depth"]]
th = table(sl, data, ML, y + 0.58, CW, col_w=[1.3, 3.4, 6.9], row_h=0.62, fs=10.5,
           bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 0.58 + th + 0.24, CW * 0.48, 1.7)
para(tf, "Three refusals worth the code", size=12, color=INK, bold=True, font=SERIF,
     first=True, space_after=6)
bullets(tf, [("One decline closes it", "the version returns to its author, and the decline is counted before the quorum is"),
             ("No signing twice under two roles", "a quorum is a number of people, not a number of hats"),
             ("Signing is its own permission", "a validator signs a quorum and may never approve alone")],
        size=10, gap=5, indent_size=9)
note(sl, ML + CW * 0.53, y + 0.58 + th + 0.24, CW * 0.47, 1.45,
     "The schema does half of it. ",
     "UNIQUE (approval, role) enforces one signature per role. The other half — that one person may not sign twice "
     "under two hats — cannot be a constraint and lives in the service, because it is about people rather than rows.")

sl, y = content("A scope determination that can be defended",
                "Governance · regimes")
tf = txt(sl, ML, y, CW, 0.46)
runs(tf, [("Three regimes are encoded: SR 26-2, SS1/23, the EU AI Act. ", CRIMSON, True),
          ("Each is an institution — its own vocabulary, its obligations written in that vocabulary, and a "
           "translation from MAYA's facts into it. A regime activates only if the translation preserves truth.",
           INK, False)],
     size=12, first=True, space_after=0, line=1.26)
h = code(sl, ML, y + 0.58, CW, [
 "def determine(model_id: str, inst: Institution) -> ScopeDetermination:",
 "    local  = inst.translate(CoreFacts.for_model(model_id))   # the translation",
 "    result = inst.sentences[\"is_model\"].evaluate(local)",
 "    return ScopeDetermination(",
 "        regime_key=inst.key, regime_version=inst.version,",
 "        determination = \"in_scope\" if result.value else \"out_of_scope\",",
 "        derivation = {\"evaluated\": result.value,",
 "                      \"failing_conjunct\": result.first_false_conjunct,",
 "                      \"facts\": local.as_dict(), \"citation\": result.citation},",
 "        obligations = [s.key for s in inst.sentences if s.holds(local)])",
], fs=9.5, title="core/regimes/engine.py")
tf = txt(sl, ML, y + 0.58 + h + 0.28, CW * 0.52, 1.68)
para(tf, "A determination is a derivation, not a flag", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "“Why is this out of scope?” is answered by the failing conjunct and a clause citation — the same answer every time it is asked, including in five years by somebody who was not there.",
     size=11.5, color=SLATE, space_after=0, line=1.26)
note(sl, ML + CW * 0.56, y + 0.58 + h + 0.28, CW * 0.44, 1.60,
     "Law L-8, and its weaker quantifier. ",
     "core/regimes/translation.py::satisfaction_condition requires evaluating natively and evaluating the translation "
     "to agree — over six probe states spanning the corners, not over generated states — and a regime that fails it "
     "cannot be activated. The quantifier is stated rather than hidden.")

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
          ("Each rule names the payload field carrying the identity it is about: a finding is raised "
           "against the model, while closing one concerns the finding. A rule that looks in the wrong "
           "place ", SLATE, False),
          ("finds nothing and permits everything", INK, True),
          (" — a control reporting success.", SLATE, False)],
     size=10.5, space_after=0, line=1.24)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Baseline import — the day-one problem", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
steps(sl, x, y + 0.42, CW * 0.47, [
    ("1", "Imported", "Bulk / connector"),
    ("2", "Baselined", "Tiered, owner confirmed, debt recorded"),
    ("3", "Gate bites", "On the next MATERIAL change"),
], h=1.30)
note(sl, x, y + 2.00, CW * 0.47, 1.55,
     "Why this exists. ",
     "On import, 1,200 legacy models arrive with no evidence. Without a baseline path every gate fails, every "
     "dashboard is red, and the programme dies by month seven. Debt is a tracked burn-down with a board-approved "
     "expiry — never rendered in the same colour as a breach.")

sl, y = content("Versioned gates — changing a control without weakening it quietly",
                "Governance · policy")
h = code(sl, ML, y + 0.06, CW * 0.53, [
 "# a rule is a PREDICATE, not a program",
 "blocking_findings == 0 and tier is not None",
 "  and all(d in accepted for d in required_docs)",
 "",
 "# whitelisted at the AST: comparison, membership,",
 "#   and / or / not, any / all, six functions.",
 "# NO loops, assignment, def, attribute access,",
 "#   subscripting.",
], fs=9, title="core/policy/language.py")
tf = txt(sl, ML, y + 0.06 + h + 0.22, CW * 0.53, 1.25)
runs(tf, [("A gate is a predicate, not a program. ", CRIMSON, True),
          ("A control written in a general-purpose policy language has to be run to be understood, "
           "and a reviewer signing one off cannot run it.", INK, False)],
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
table(sl, data, x, y + 0.06, CW * 0.43, col_w=[2.6, 2.7], row_h=0.70, fs=9, hfs=9.5,
      bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + 3.60, CW, 0.70, fill=CRIMSON)
tf = txt(sl, ML + 0.32, y + 3.71, CW - 0.64, 0.56)
runs(tf, [("The honest boundary. ", WHITE, True),
          ("Policy tightens; the code's invariants are the floor. A rule runs in addition to the "
           "registry's checks, never instead of them — because replacing an invariant with a line of "
           "configuration means a typo can weaken the platform while the deployment looks successful.",
           RGBColor(0xF6,0xE0,0xE4), False)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("Documentation — two kinds, held apart", "Governance · documentation")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Compiled — what the register knows", size=12.5, color=CRIMSON, bold=True,
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
para(tf, "Attached — what a person wrote", size=12.5, color=CRIMSON, bold=True,
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
         "printed — not their replacement. Re-hashed on read: what was accepted is what is served.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

note(sl, ML, y + 3.62, CW, 0.98,
     "Why both. ",
     "A platform that only compiles cannot hold the paper the quant actually wrote; one that only stores files is a "
     "share drive with a database in front. Held apart, the register can say which is which — and a rejected document "
     "stays on file with its reason, because the papers that did not pass are the ones a supervisor asks about.")
