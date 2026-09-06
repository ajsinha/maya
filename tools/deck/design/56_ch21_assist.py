# ============================================================ CH 21
_state["chapter"] = "21 · Machine Assistance"

sl, y = content("The capability contract", "Machine assistance · registration")
h = code(sl, ML, y, CW * 0.58, [
 "def register(self, capability_key, description, tier, base_model,",
 "             prompt_digest, owner, oracle_key=None, ...):",
 "    if tier == \"C\":",
 "        raise AssistError(\"advisory_not_registrable\", ...)",
 "    if tier not in TIERS:",
 "        raise AssistError(\"unknown_tier\", ...)",
 "    if tier == TIER_A and not oracle_key:",
 "        raise AssistError(\"oracle_required\", ...)",
 "    if oracle_key and not oracles.get(oracle_key):",
 "        raise AssistError(\"unknown_oracle\", ...)",
 "    ...",
 "    self.capabilities.add(row)",
 "    self.evidence.append(\"ai_capability_registered\", ...)",
], fs=9.5, title="core/assist/capabilities.py — register()")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.6)
para(tf, "Two tiers, one criterion", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("Tier A — verified", "A formal property checks the output. Encoding a regime, asserting equivalence, converting a format, generating probes, generating a query"),
             ("Tier B — grounded", "Every claim cites evidence; the citation is verified; a human attests. Documentation drafting, discovery, validation assistance")],
        size=11.5, gap=8, indent_size=10)
para(tf, "The criterion is not the model's capability, nor the task's sensitivity. It is whether the structure supplies a decision procedure.",
     size=11, color=SLATE, space_after=8, line=1.26)
runs(tf, [("Both rules are enforced at registration, not at use. ", CRIMSON, True),
          ("A capability that claims its output is mechanically checkable must name the check; "
           "“we validate the output” without naming what validates it is the sentence that precedes every AI incident.",
           INK, False)], size=11, line=1.26)

sl, y = content("The grounding gate — claims are removed, not marked",
                "Machine assistance · citation verification")
h = code(sl, ML, y, CW * 0.56, [
 "def gate(claims, known_evidence):",
 "    \"\"\"(kept, rejected). Rejected claims never reach the output.\"\"\"",
 "    known = set(known_evidence)",
 "    checked  = [verify_claim(c, known) for c in claims]",
 "    kept     = [c for c in checked if c[\"verified\"]]",
 "    rejected = [c for c in checked if not c[\"verified\"]]",
 "    return kept, rejected",
 "",
 "def assemble(kept):",
 "    \"\"\"The published text: the surviving claims, and nothing else.\"\"\"",
 "    return \"\\n\\n\".join(c[\"text\"] for c in kept if c.get(\"text\"))",
], fs=9.5, title="core/assist/grounding.py")
x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.6)
para(tf, "Why removal and not a flag", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "A document whose unsupported sentences are marked is a document where the marks are what gets skimmed past — and the sentence still reads as though the platform said it. A claim citing nothing is not grounded, however true it happens to be.",
     size=11, color=SLATE, space_after=9, line=1.26)
runs(tf, [("The rejected claims are kept, separately. ", CRIMSON, True),
          ("ai_generation.rejected_claims is a column. A reviewer sees what the model tried to assert and could not support, "
           "which is a more useful artifact than an annotated draft: it is the list of places it was making things up.",
           INK, False)], size=11, space_after=9, line=1.26)
runs(tf, [("What it may cite is fixed before it is asked. ", CRIMSON, True),
          ("The evidence is gathered from the register first, capped at forty nodes, and the prompt is assembled from that — "
           "so a citation the model invents has nowhere to land.", INK, False)],
     size=11, line=1.26)

sl, y = content("Tier C is refused in code — and the schema does not help",
                "Machine assistance · the boundary")
h = code(sl, ML, y, CW * 0.52, [
 "-- db/schema/sqlite.sql",
 "tier  TEXT NOT NULL      -- unconstrained",
 "",
 "# core/assist/capabilities.py",
 "if tier == \"C\":",
 "    raise AssistError(\"advisory_not_registrable\", ...)",
], fs=10.5, title="WHERE TIER C IS ACTUALLY REFUSED")
tf = txt(sl, ML, y + h + 0.26, CW * 0.52, 2.5)
runs(tf, [("The schema does not prohibit it. ", CRIMSON, True),
          ("There are no CHECK constraints in either dialect and ai_capability.tier is unconstrained TEXT, so the "
           "prohibition is application code at one call site. That is a weaker claim than “unrepresentable”, and it is "
           "the true one: anything writing that table directly is stopped by nothing.", INK, False)],
     size=11, first=True, space_after=10, line=1.26)
runs(tf, [("A capability holds no credential at all. ", CRIMSON, True),
          ("It is not a principal. Every generation is attributed to the person who asked for it, lands drafted, "
           "and carries no weight anywhere until somebody else attests it — self-attestation is refused by name.",
           INK, False)], size=11, line=1.26)
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
