# ============================================================ CH 20
divider("20", "The Execution Plane",
        "How a governed model actually gets run — and stopped.",
        ["The warrant grammar",
         "Resolution algorithm",
         "Caching and stampede control",
         "Revocation",
         "Use reconciliation"])

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
           "\u2014 not a new document type. Six of the eighteen run inside MAYA; the rest name an engine the bank "
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

sl, y = content("Warrant resolution", "Execution · the hot path")
h = code(sl, ML, y, CW * 0.60, [
 "def resolve(req) -> WarrantDescriptor:",
 "    principal = authn.verify(req.token)      # workload identity",
 "    key = (req.urn, principal.id, req.environment, req.declared_use_id)",
 "",
 "    if (d := local_lru.get(key)) and d.fresh(): return d",
 "    if revocations.contains(d): raise Revoked(...)   # floor beats every cache",
 "",
 "    with singleflight(key):                  # coalesce concurrent misses",
 "        row = warrant_projection.get(req.urn, req.environment)  # ONLY table read",
 "        if row.revoked:                     raise Revoked(...)",
 "        ent = row.entitlements.get(principal.id)",
 "        if ent is None or ent.model_use_id != req.declared_use_id:",
 "                                            raise NoEntitlement(...)",
 "        if row.governance_snapshot.blocking_findings: raise Restricted(...)",
 "        d = sign(build_descriptor(row, ent, req))",
 "        redis.setex(key, ttl_with_jitter(row.tier), d)",
 "    return d",
], fs=9, title="core/execution/warrants.py")
x = ML + CW * 0.64
tf = txt(sl, x, y, CW * 0.36, 3.7)
para(tf, "How p99 < 50 ms is met", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("Never touch the primary", "warrant_projection is served from a read replica — and it is the ONLY table this service knows"),
             ("Common case is a Redis GET", "plus one signature check — HMAC-SHA256 today, Ed25519 the production target"),
             ("Two cache tiers", "in-process LRU in front of Redis"),
             ("Schema decoupling", "the projection is a published contract with its own version, so a control-plane migration cannot break the one component that must never break")],
        size=11, gap=7, indent_size=9.5)

sl, y = content("Stampede control and revocation", "Execution · the two failure modes")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Stampede — a routine operation, not an incident", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Control", "What it prevents"],
        ["Pre-warm before invalidate", "The cache is never empty for a hot alias"],
        ["Single-flight coalescing", "N concurrent misses become one backend call"],
        ["TTL jitter ±20%", "Synchronised expiry across the fleet"],
        ["Stale-while-revalidate 5 s", "A latency cliff during rebuild"]]
th = table(sl, data, ML, y + 0.40, CW * 0.47, col_w=[2.2, 3.3], row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 0.40 + th + 0.20, CW * 0.47, 1.4)
runs(tf, [("Why it matters. ", CRIMSON, True),
          ("An alias move on a model taking 14,000 requests/second causes every in-flight consumer to miss simultaneously. "
           "Without pre-warming, a governed, routine operation takes the database down.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Revocation — four propagation paths", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
data = [["Path", "Latency"],
        ["Redis revocation set → resolvers fail closed", "immediate"],
        ["Kafka event → SDKs drop the descriptor", "≈ 1 s"],
        ["Epoch on every response → polling engines re-resolve", "≤ 30 s"],
        ["TTL expiry → fully partitioned engine", "≤ 60 s (Tier 1)"]]
th = table(sl, data, x, y + 0.40, CW * 0.47, col_w=[4.0, 1.5], row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
cy = y + 0.40 + th + 0.20
rect(sl, x, cy, CW * 0.47, 1.50, fill=PARCH)
rect(sl, x, cy, 0.045, 1.50, fill=CRIMSON)
tf = txt(sl, x + 0.26, cy + 0.14, CW * 0.47 - 0.5, 1.25)
runs(tf, [("The revocation floor. ", CRIMSON, True),
          ("SDKs persist a local revocation list. A descriptor on that list is refused ", INK, False),
          ("regardless of grace state", INK, True),
          (". Grace extends authorisation currency; it never extends revocation ignorance. Tier 1 default grace is zero.", INK, False)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("Approved use versus actual use", "Execution · the capability nobody else has")
tf = txt(sl, ML, y, CW, 0.45)
runs(tf, [("SS1/23 asks the inventory to record intended use ", INK, False), ("compared to actual use", CRIMSON, True, True),
          (". Warrant telemetry makes that observable rather than aspirational. A nightly job compares the observed context "
           "distribution against approved model_use rows.", INK, False)], size=12.5, first=True, space_after=0, line=1.28)
data = [["Exception", "Example", "Becomes"],
        ["Off-label portfolio", "223 calls for a portfolio that is not an approved use", "Finding, owner, due date"],
        ["Unapproved geography", "Calls originating outside the approval's scope", "Finding + scope review"],
        ["Volume anomaly", "40× expected daily volume — suggests a new, unassessed use", "Investigation task"],
        ["Boundary violation rate", "0.26% of inputs outside declared operating boundaries", "Contract assumption A is failing"],
        ["Dormant approval", "An approved use with zero calls for 180 days", "Candidate for withdrawal"],
        ["Undeclared consumer", "A new principal resolving the warrant", "Entitlement review"]]
table(sl, data, ML, y + 0.62, CW, col_w=[2.7, 5.6, 3.3], row_h=0.38, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
