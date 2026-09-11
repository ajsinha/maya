# ============================================================ CH 20
_state["chapter"] = "20 · The Execution Plane"

sl, y = content("The warrant grammar — a product, not a union", "Execution · the contract")
tf = txt(sl, ML, y, CW, 0.62)
para(tf, "Every model a bank runs differs along exactly four independent axes. The grammar is their PRODUCT, "
         "so a new model technology is a new value in one vocabulary — not a new document type.",
     size=12.5, color=SLATE, first=True, space_after=0, line=1.3)
yy = y + 0.72
AXES = [("1  Parameter object  ·  8", "how P is inhabited",
         "none · calibration_set · estimated_coefficients · learned_weights · llm_configuration · rule_set · elicited_weights · opaque"),
        ("2  Realisation  ·  18", "how the kernel becomes runnable",
         "quantlib · onnx · pmml · pfa · estimator · rules · python.callable · container · rest · sql · spreadsheet · solver · sas · r · matlab · llm.prompt · llm.agent · descriptor_only"),
        ("3  Operation  ·  10", "what is asked of it",
         "score · fit · validate · backtest · explain · simulate · stress · optimise · generate · monitor"),
        ("4  Data binding  ·  12", "where its data comes from",
         "inline · request · feature_namespace · featureset · dataset_snapshot · delta_table · sql_query · stream · market_data · document_corpus · scenario_set · artifact")]
for i, (name, gloss, values) in enumerate(AXES):
    rect(sl, ML, yy, CW, 0.80, fill=PARCH if i % 2 == 0 else None,
         line=RGBColor(0xD8,0xD4,0xCF))
    rect(sl, ML, yy, 0.045, 0.80, fill=CRIMSON)
    tf = txt(sl, ML + 0.22, yy + 0.06, CW * 0.28, 0.68)
    para(tf, name, size=11.5, color=CRIMSON, bold=True, first=True, space_after=1)
    para(tf, gloss, size=9.5, color=MUTED, italic=True, space_after=0)
    tf = txt(sl, ML + CW * 0.30, yy + 0.10, CW * 0.68, 0.62)
    para(tf, values, size=9.5, color=INK, first=True, space_after=0, line=1.25)
    yy += 0.86

tf = txt(sl, ML, yy + 0.24, CW, 0.5)
runs(tf, [("Extends the right way. ", CRIMSON, True),
          ("A model technology nobody anticipated is a new value in one vocabulary \u2014 almost always a runtime "
           "\u2014 not a new document type. Six of the nineteen run inside MAYA; the rest name an engine the bank "
           "already operates, and the warrant is what MAYA hands it.",
           INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

sl, y = content("The same document, at different coordinates", "Execution · one grammar")
COORDS = [["Model", "1  parameters", "2  runtime", "3  verb", "4  data"],
          ["Black swaption pricer", "none  (T0)", "quantlib", "score", "market_data"],
          ["Hull-White calibration", "calibration_set  (T1)", "quantlib", "fit", "dataset_snapshot"],
          ["Gradient-boosted PD", "learned_weights  (T3)", "onnx", "score", "feature_namespace"],
          ["KYC summariser", "llm_configuration  (T5)", "llm.prompt", "generate", "document_corpus"],
          ["Vendor AML engine", "opaque  (T6)", "descriptor_only", "score", "stream"]]
COORDS += [["Behaviour scorecard", "estimated_coefficients  (T2)", "pmml", "score", "feature_namespace"],
           ["Origination rule set", "rule_set  (T8)", "rules", "score", "request"]]
th = table(sl, COORDS, ML, y, CW, col_w=[3.0, 3.1, 2.4, 1.5, 1.7], row_h=0.42,
           fs=10.5, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + th + 0.26, CW, 0.86, fill=PARCH)
rect(sl, ML, y + th + 0.26, 0.045, 0.86, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + th + 0.38, CW - 0.6, 0.68)
runs(tf, [("The first two rows are the argument. ", CRIMSON, True),
          ("Same library, same runtime, and the grammar treats them completely differently — because the "
           "parameter axis differs. \u201cIs it AI?\u201d puts both in one bucket; \u201chow is P inhabited?\u201d separates them "
           "correctly, and that is what makes the evidence expectations right for each.", INK, False)],
     size=11, first=True, space_after=0, line=1.26)

sl, y = content("What the grammar refuses, and why", "Execution · admissibility")
data = [["Law", "Refuses", "Because"],
        ["L-W0", "a malformed document", "ten sections, a known verb, a runtime without its entry keys"],
        ["L-W1", "fit on T0 or T6", "T0's parameters come from theory; T6's are inside a vendor black box"],
        ["L-W2", "generate on a non-generative runtime", "an ONNX graph does not produce prose"],
        ["L-W3", "training from a non-bitemporal source", "it cannot be shown point-in-time correct, so it cannot be shown leak-free"],
        ["L-W4", "a fit with no parameter_object sink", "a fit produces a NEW parameter object, it does not edit the old one"],
        ["L-W5", "claimed determinism with no seed", "an LLM at 0.7 is not reproducible, and neither is an unseeded simulation"],
        ["L-W6", "fit on a descriptor-only model", "you cannot inhabit what nothing on this side can reach"],
        ["L-W7", "a backtest with no outcomes", "that is a re-score wearing a backtest's name"],
        ["L-W8", "a run that will not name its point in P", "a number produced at an unstated point in P is attributable to nothing"],
        ["L-W9", "a training read unbounded in either clock", "the set fixes the columns; the warrant must fix the period"],
        ["L-W10", "a featureset that misses what the kernel reads", "contravariance in inputs — L-12, one level out, checked at issuance against the register"],
        ["L-W11", "a calibration with no as-of", "yesterday's numbers and this morning's are not the same run"],
        ["L-W12", "parameters inside an artifact with no digest", "P would then be whatever that file happens to contain today"],
        ["L-W13", "a generative runtime pinned to a model name", "the name survives a provider's build change; the behaviour does not"]]
th = table(sl, data, ML, y, CW, col_w=[0.85, 3.35, 7.4], row_h=0.24, fs=8.5, hfs=9,
           bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + th + 0.10, CW, 0.44)
runs(tf, [("Validated before signed, never after. ", CRIMSON, True),
          ("A signature over a non-conforming document assures that it is authentic and not that it is usable, "
           "and an engine reads it as both.", INK, False)],
     size=10, first=True, space_after=0, line=1.18)

sl, y = content("Warrant resolution — the order of the checks",
                "Execution · the resolution path")
h = code(sl, ML, y, CW * 0.57, [
 "def resolve(urn, environment, principal, declared_use, verb=\"score\"):",
 "    name, semver, alias = parse_urn(urn)",
 "    m = self._model(urn, model_urn(name))       # the register, by URN",
 "    self._check_not_blocked(m)                  # a blocking finding restricts",
 "    grant = self._grant(m, environment, principal, declared_use)",
 "    version = self._version(m[\"urn\"], environment, semver,",
 "                            alias or grant[\"alias_name\"], urn)",
 "    if self.policy is not None:        # consulted last, and only to refuse",
 "        self.policy.check(\"warrant:resolve\", {...}, urn)",
 "    return self.builder.build(urn, m, version, grant, principal,",
 "                              declared_use, environment, self.epoch,",
 "                              verb=verb,",
 "                              parameter_set=self._point_of_p(urn, version))",
], fs=8.5, title="core/execution/warrants.py")
x = ML + CW * 0.61
tf = txt(sl, x, y, CW * 0.39, 3.4)
para(tf, "What the order is for", size=12.5, color=INK, bold=True, font=SERIF,
     first=True, space_after=6)
bullets(tf, [("Refuse before anything is loaded",
              "Entitlement, blocking findings and version status are all decided out of the register. No artifact is opened on this path"),
             ("Policy is consulted last, and only to refuse",
              "A gate that can only subtract cannot grant what the checks above it withheld"),
             ("Signed HMAC-SHA256, keyed per audience",
              "The key is derived from the principal the warrant is FOR, so a compromised engine forges warrants for itself and nobody else"),
             ("TTL and grace follow the tier",
              "60 s and zero grace at Tier 1; the TTL is jittered ±20% so a fleet does not re-resolve in lockstep")],
        size=10.5, gap=6, indent_size=9)
cy = y + h + 0.28
tf = txt(sl, ML, cy, CW * 0.50, 0.30)
para(tf, "Revocation — what actually propagates", size=12, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=0)
data = [["Path", "What it stops"],
        ["Withdraw the grant", "No further descriptor is minted for that principal"],
        ["Epoch bump on every revocation", "A descriptor minted under an older epoch is stale on its face — the counter is in-process, so a restart resets it"],
        ["The consumer's local revocation list", "Refused regardless of grace — grace extends currency, never ignorance"]]
table(sl, data, ML, cy + 0.34, CW * 0.50, col_w=[2.3, 3.5], row_h=0.30,
      fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
nx = ML + CW * 0.54
rect(sl, nx, cy, CW * 0.46, 1.86, fill=PARCH)
rect(sl, nx, cy, 0.045, 1.86, fill=CRIMSON)
tf = txt(sl, nx + 0.26, cy + 0.13, CW * 0.46 - 0.5, 1.62)
runs(tf, [("There is no cache, so there is no stampede. ", CRIMSON, True),
          ("Resolution reads four to six tables on every call. The Redis descriptor "
           "cache, single-flight coalescing, pre-warm-before-invalidate, the "
           "warrant_projection read model and a Kafka revocation event are "
           "designed and not built — docs/14 §27 — and the 50 ms p99 in the "
           "requirements is a target that nothing here measures. TTL jitter is "
           "built, which is the one piece that matters only once a cache exists.",
           INK, False)],
     size=10, first=True, space_after=0, line=1.22)

sl, y = content("Approved use, and the use nobody has compared it with",
                "Execution · designed, not built")
tf = txt(sl, ML, y, CW, 0.50)
runs(tf, [("SS1/23 asks the inventory to record intended use ", INK, False),
          ("compared to actual use", CRIMSON, True, True),
          (". Every input that comparison needs is recorded. The comparison itself is not written — "
           "so what follows on the right is a design, and is marked as one.", INK, False)],
     size=12, first=True, space_after=0, line=1.26)
tf = txt(sl, ML, y + 0.60, CW * 0.44, 0.30)
para(tf, "Built — the inputs", size=12, color=INK, bold=True, font=SERIF,
     first=True, space_after=0)
data = [["What", "Where"],
        ["Principal, environment and declared use, per grant", "warrant table, one row per entitlement"],
        ["A resolution whose declared use has no grant is refused", "core/execution/warrants.py"],
        ["Issue and revoke are evidence nodes with an actor", "the chain"],
        ["Scores and outcomes per version", "core/telemetry/collector.py, into Delta"]]
table(sl, data, ML, y + 0.94, CW * 0.44, col_w=[3.2, 2.4], row_h=0.34,
      fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.48
tf = txt(sl, x, y + 0.60, CW * 0.52, 0.30)
para(tf, "Designed — the six exceptions it would raise", size=12, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=0)
data = [["Exception", "Would become"],
        ["A portfolio that is not an approved use", "Finding, owner, due date"],
        ["Calls originating outside the approval's scope", "Finding + scope review"],
        ["Volume far above the assessed use", "Investigation task"],
        ["Inputs outside declared operating boundaries", "Contract assumption A is failing"],
        ["An approved use with no calls for 180 days", "Candidate for withdrawal"],
        ["A new principal resolving the warrant", "Entitlement review"]]
th = table(sl, data, x, y + 0.94, CW * 0.52, col_w=[4.0, 2.4], row_h=0.30,
           fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 0.94 + th + 0.18, CW * 0.52, 0.60)
runs(tf, [("None of this runs. ", CRIMSON, True),
          ("Use reconciliation is one of the eight screens in docs/14 §28 that are designed "
           "and not built; the boundary check on the left is the one part of it that is enforced today, "
           "at execution rather than in a report.", INK, False)],
     size=10, first=True, space_after=0, line=1.22)
