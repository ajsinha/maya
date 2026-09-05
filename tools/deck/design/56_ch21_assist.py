# ============================================================ CH 21
divider("21", "Machine Assistance",
        "Where AI does the work, where it may not, and why that is structural.",
        ["The capability contract",
         "The grounding gate",
         "Structural prohibition"])

sl, y = content("The capability contract", "Machine assistance · design")
h = code(sl, ML, y, CW * 0.58, [
 "class Capability(Protocol):",
 "    key: str",
 "    assist_tier: Literal[\"A\", \"B\"]   # \"C\" is unrepresentable",
 "    oracle_key: str | None            # required for tier A",
 "    def generate(self, ctx) -> Draft: ...",
 "",
 "def run(cap, ctx) -> CapabilityResult:",
 "    draft = cap.generate(ctx)",
 "    if cap.assist_tier == \"A\":",
 "        ok = oracles.get(cap.oracle_key).check(draft, ctx)",
 "        if not ok.holds:",
 "            return CapabilityResult(rejected=True, reason=ok.detail)",
 "    else:",
 "        draft = grounding_gate(draft, ctx)",
 "    ai_generations.record(cap, draft, ctx)",
 "    return CapabilityResult(draft=draft, requires_attestation=True)",
], fs=9.5, title="core/assist/capabilities.py")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.6)
para(tf, "Two tiers, one criterion", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("Tier A — verified", "A formal property checks the output. Encoding a regime, asserting equivalence, converting a format, generating probes, generating a query"),
             ("Tier B — grounded", "Every claim cites evidence; the citation is verified; a human attests. Documentation drafting, discovery, validation assistance")],
        size=11.5, gap=8, indent_size=10)
para(tf, "The criterion is not the model's capability, nor the task's sensitivity. It is whether the structure supplies a decision procedure.",
     size=11, color=SLATE, space_after=0, line=1.26)

sl, y = content("The grounding gate", "Machine assistance · citation verification")
h = code(sl, ML, y, CW * 0.58, [
 "def grounding_gate(draft, ctx) -> Draft:",
 "    for s in draft.sentences:",
 "        if not s.is_factual_claim: continue",
 "        supported = evidence.evaluate(",
 "            s.claim_ref, BOOLEAN,",
 "            valuation=lambda x: x in s.cited_evidence_ids)",
 "        if not supported:",
 "            draft.reject(s, missing=evidence.evaluate(s.claim_ref, WHY))",
 "    draft.numbers = interpolate_from_evidence(draft.number_slots, ctx)",
 "    draft.mark_unverified(draft.unmapped_sentences)",
 "    return draft",
], fs=9.5, title="core/assist/grounding.py")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.6)
para(tf, "Verification, not another model call", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Switch on exactly the cited identifiers, evaluate the claim's derivation in Boolean, and see whether it still holds. If it does, the citation is genuine. If not, the sentence is rejected — not flagged.",
     size=11.5, color=SLATE, space_after=10, line=1.26)
runs(tf, [("Numbers are never generated. ", CRIMSON, True),
          ("They are interpolated from evidence, which removes the entire class of hallucinated statistics.", INK, False)],
     size=11.5, space_after=10, line=1.26)
runs(tf, [("Unmapped sentences are marked, not hidden. ", CRIMSON, True),
          ("A quantified claim like “on all monitored slices” has no supporting term at all — and that is exactly the sentence human review reliably waves through.",
           INK, False)], size=11.5, line=1.26)

sl, y = content("Structural prohibition", "Machine assistance · the boundary")
h = code(sl, ML, y, CW * 0.52, [
 "assist_tier char(1) NOT NULL",
 "    CHECK (assist_tier IN ('A','B'))",
], fs=11.5, title="TIER C IS UNREPRESENTABLE IN THE SCHEMA")
tf = txt(sl, ML, y + h + 0.28, CW * 0.52, 2.3)
para(tf, "And no credential exists", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "No ai_capability principal is ever granted a lifecycle-transition scope in the IAM model. A capability cannot make a governance decision because it holds no credential to attempt one.",
     size=11.5, color=SLATE, space_after=10, line=1.26)
runs(tf, [("Policy erodes under commercial pressure from sensible people with good reasons. ", SLATE, False),
          ("Missing credentials do not.", INK, True)], size=11.5, line=1.26)
x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 0.35)
para(tf, "What a machine may never do here", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
data = [["Decision", "Why no oracle exists"],
        ["Conclude a validation", "Defined by standing and accountability, which a model has not"],
        ["Assign or override a tier", "The rule constitutes the standard"],
        ["Make a scope determination", "Discards the derivation that is the point"],
        ["Approve anything", "An accountable act with a signature behind it"],
        ["Accept residual risk", "Requires authority"],
        ["Close a finding", "Independent verification by someone who did not raise it"],
        ["Compute a metric", "Compute it, then let the model describe it"]]
table(sl, data, x, y + 0.40, CW * 0.44, col_w=[2.2, 3.4], row_h=0.34, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
