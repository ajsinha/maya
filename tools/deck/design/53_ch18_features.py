# ============================================================ CH 18
divider("18", "The Feature Platform",
        "Point-in-time correctness, version-namespaced serving, monitoring at scale.",
        ["The PIT assembly",
         "Three-layer verification",
         "Online store namespacing",
         "Monitoring pipeline"])

sl, y = content("Point-in-time assembly", "Data · the feature platform")
h = code(sl, ML, y, CW * 0.56, [
 "static = analyse_temporal_predicates(spine, views)   # LAYER 1",
 "if not (static.has_valid_time_bound and",
 "        static.has_transaction_time_bound):",
 "    raise AssemblyRejected(static.missing)   # rejected, not sampled",
 "",
 "df = spark.read(spine)",
 "for v in views:",
 "    df = df.join(pit_lateral(v, as_of), on=[\"entity_id\"], how=\"left\")",
 "",
 "snap   = delta.write(df, name=name)",
 "report = verify_pit(snap, spine, views, as_of)       # LAYER 2",
 "if not report.passed:",
 "    findings.raise_(severity=\"Critical\", category=\"leakage\", ...)",
], fs=9.5, title="core/features/assembly.py")
x = ML + CW * 0.60
h2 = code(sl, x, y, CW * 0.40, [
 "LEFT JOIN LATERAL (",
 "  SELECT <features>",
 "  FROM   <view> VERSION AS OF :dv   -- txn time",
 "  WHERE  entity_id  = s.entity_id",
 "    AND  event_ts  <= s.label_ts    -- valid time",
 "    AND  ingest_ts <= LEAST(          -- txn time, bounded by BOTH:",
 "           s.label_ts, :as_of)        -- saturates at the label",
 "  ORDER BY event_ts DESC, ingest_ts DESC",
 "  LIMIT 1",
 ") f ON true",
], fs=9, title="THE GENERATED JOIN")
tf = txt(sl, ML, y + max(h, h2) + 0.30, CW, 1.1)
runs(tf, [("Delta supplies the second clock. ", CRIMSON, True),
          ("VERSION AS OF gives the transaction-time axis natively — which is why Delta rather than a plain warehouse table is "
           "the right substrate for a regulated feature store. Because both clocks are recorded, the platform can also answer the "
           "question that arises when a source is restated: ", INK, False),
          ("which historical training sets, model versions and decisions used the superseded values?", INK, True),
          (" With one clock, that question is unanswerable.", INK, False)], size=12, first=True, space_after=0, line=1.28)

sl, y = content("Three layers, and what each actually proves", "Data · leakage verification")
data = [["Layer", "What it does", "What it proves"],
        ["1 · Static analysis", "Parses the assembly query and requires BOTH a valid-time and a transaction-time bound. An assembly lacking either is rejected outright",
         "A genuine proof for the dominant leakage class. This is the strong check"],
        ["2 · Stratified sampling", "Independent recomputation over strata across label period, entity type and label value",
         "Detects systematic violations at a stated statistical power. Does not prove absence"],
        ["3 · Adversarial injection", "CI injects a deliberately leaky feature the verifier must catch",
         "Proves the verifier still works — the failure mode that would otherwise be silent and catastrophic"]]
th = table(sl, data, ML, y, CW, col_w=[2.3, 5.0, 4.3], row_h=0.62, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + th + 0.30, CW, 1.15, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + th + 0.44, CW - 0.7, 0.95)
para(tf, "Law L-10, restated honestly", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=6)
runs(tf, [("“No assembly passes without a static temporal bound, and sampling detects systematic violations at stated power.”  ",
           WHITE, True),
          ("Weaker than the original wording — and true. Adversarial review rejected the single-layer claim, because a leak confined "
           "to a rare, high-value segment is exactly where sampling fails and where the damage is greatest.",
           RGBColor(0xF6,0xE0,0xE4), False)], size=11.5, space_after=0, line=1.26)

sl, y = content("The online store must be version-namespaced", "Data · the defect that reported green")
rect(sl, ML, y, CW, 1.30, fill=RGBColor(0x8B,0x2F,0x2F))
tf = txt(sl, ML + 0.35, y + 0.16, CW - 0.7, 1.05)
para(tf, "Finding C-2 — the most serious defect adversarial review found", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=6)
runs(tf, [("Contracts pinned feature view v7. The online store served whatever was latest. On a transformation change, a model "
           "would be served features it was never fitted on — ", RGBColor(0xF6,0xE0,0xE4), False),
          ("with the contract digest still matching and every monitor green.", WHITE, True),
          ("  Silently wrong production scoring, introduced by the very platform that exists to prevent it.", RGBColor(0xF6,0xE0,0xE4), False)],
     size=11.5, space_after=0, line=1.26)
h = code(sl, ML, y + 1.55, CW * 0.46, [
 "key = f\"fv:{feature_view_id}:v{version}:{entity_id}\"",
], fs=11, title="THE FIX — VERSION IS PART OF THE KEY")
x = ML + CW * 0.50
data = [["Phase", "Behaviour"],
        ["Publish v(n+1)", "Begin dual-write to both namespaces"],
        ["Steady state", "Serving reads the namespace PINNED BY THE CONTRACT, never “latest”"],
        ["Retire v(n)", "Only when zero active contracts reference it — a governed action with consumer-impact check"]]
table(sl, data, x, y + 1.50, CW * 0.50, col_w=[1.7, 4.3], row_h=0.40, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 2.70, CW * 0.46, 1.3)
runs(tf, [("Law L-17 checks this in production, continuously. ", CRIMSON, True),
          ("The namespace served must equal the namespace pinned. C-2 was invisible to every design-time check, so its guard is a runtime one.",
           INK, False)], size=11.5, first=True, space_after=0, line=1.26)

sl, y = content("Monitoring pipeline", "Data · evaluation at scale")
boxes = [("inference_log\nDelta + CDF", RGBColor(0x4A,0x3A,0x1F)), ("Incremental reader\nchanged partitions only", SLATE),
         ("Metric compute\nSpark · per monitor × slice", SLATE), ("observations\nDelta", RGBColor(0x4A,0x3A,0x1F)),
         ("Threshold ladder\nper tier", SLATE), ("Correlated finding", CRIMSON), ("Warrant restriction", RGBColor(0x2D,0x50,0x16))]
bw = (CW - 0.22 * (len(boxes) - 1)) / len(boxes)
for i, (t, col) in enumerate(boxes):
    xx = ML + i * (bw + 0.22)
    rect(sl, xx, y + 0.10, bw, 0.85, fill=col)
    tfb = txt(sl, xx + 0.08, y + 0.18, bw - 0.16, 0.70, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    for j, line in enumerate(t.split("\n")):
        para(tfb, line, size=9 if j else 10, color=WHITE, bold=(j == 0), first=(j == 0),
             align=PP_ALIGN.CENTER, space_after=0)
    if i < len(boxes) - 1:
        connect(sl, xx + bw, y + 0.525, xx + bw + 0.22, y + 0.525)
tf = txt(sl, ML, y + 1.20, CW * 0.47, 2.4)
para(tf, "Delayed labels are the hard part", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Credit outcomes mature over months. Monitors declare a label_delay; performance metrics are computed on vintage cohorts whose outcome window has closed, and the UI shows both the metric and the maturity of the cohort it came from.",
     size=11.5, color=SLATE, space_after=8, line=1.26)
runs(tf, [("Reporting an AUC on immature outcomes is worse than reporting nothing", INK, True),
          (" — it is confidently wrong in a direction nobody checks.", SLATE, False)], size=11.5, line=1.26)
x = ML + CW * 0.53
tf = txt(sl, x, y + 1.20, CW * 0.47, 0.35)
para(tf, "Metric sets are seeded per trainability class", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Class", "Default metrics"],
        ["T1 calibrated", "Calibration error, arbitrage-free checks"],
        ["T2 / T3", "KS, AUC, PSI, Hosmer–Lemeshow"],
        ["T4 adaptive", "Parameter-change magnitude, parallel outcomes analysis"],
        ["T5 foundation", "Groundedness, hallucination rate, human edit distance"],
        ["T6 opaque", "Own-outcomes divergence"],
        ["T8 authored", "Rule-fire distribution, exception rate"]]
table(sl, data, x, y + 1.58, CW * 0.47, col_w=[1.7, 4.0], row_h=0.32, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Telemetry — monitoring's missing half", "Data · ingestion")
tf = txt(sl, ML, y, CW, 0.50)
runs(tf, [("Monitors could always be evaluated. They had to be ", INK, False), ("handed", INK, True),
          (" their rows — which made monitoring something somebody remembered to do, and left the "
           "scheduler able only to record that a monitor had stopped.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
bw = (CW - 0.5) / 2
rect(sl, ML, y + 0.62, bw, 1.15, fill=WHITE, line=RULE)
rect(sl, ML, y + 0.62, bw, 0.05, fill=CRIMSON)
tf = txt(sl, ML + 0.26, y + 0.76, bw - 0.52, 0.95)
para(tf, "scores", size=13, color=CRIMSON, bold=True, font=MONO, first=True, space_after=3)
para(tf, "What the model produced, when it produced it. entity_id · scored_at · score",
     size=10.5, color=SLATE, space_after=0, line=1.2)
rect(sl, ML + bw + 0.5, y + 0.62, bw, 1.15, fill=WHITE, line=RULE)
rect(sl, ML + bw + 0.5, y + 0.62, bw, 0.05, fill=NAVY)
tf = txt(sl, ML + bw + 0.76, y + 0.76, bw - 0.52, 0.95)
para(tf, "outcomes", size=13, color=NAVY, bold=True, font=MONO, first=True, space_after=3)
para(tf, "What actually happened, learned later. entity_id · label · label_ts",
     size=10.5, color=SLATE, space_after=0, line=1.2)
tf = txt(sl, ML, y + 1.90, CW, 0.42)
runs(tf, [("Two streams, never one. ", CRIMSON, True),
          ("The gap between them is precisely what the delayed-label discipline reasons about, so "
           "flattening them would take that reasoning away before it started.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)
data = [["Rule", "The failure it prevents"],
        ["Idempotent on the digest of the batch's own rows",
         "Real collectors deliver at least once. A monitor that double-counts a redelivered batch reports a population that never existed"],
        ["A row without its OWN timestamp is refused",
         "Stamping it with the batch's arrival time is how every window silently becomes wrong"],
        ["The sample rate travels on every row",
         "A statistic that cannot say what population it speaks for"],
        ["The join happens at READ time against a stated moment, and unlabelled rows come back unlabelled",
         "A cohort that looks complete and is not — the monitor decides maturity per row, and a join that dropped the unlabelled would decide for it"],
        ["A drift monitor's reference window is STATED",
         "“What is this drifting from” being part of whoever ran it rather than part of the record"]]
table(sl, data, ML, y + 2.40, CW, col_w=[3.6, 8.0], row_h=0.50, fs=10, hfs=10.5,
      bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Version approval is a quorum, and its depth follows the tier",
                "Governance · approval")
tf = txt(sl, ML, y, CW, 0.48)
runs(tf, [("The model ", INK, False), ("record", INK, True),
          (" was attested by several people while the ", INK, False), ("version", INK, True),
          (" — the thing that actually runs — was approved by one.", INK, False)],
     size=12.5, first=True, space_after=0, line=1.28)
data = [["Tier", "Who must sign", "Why"],
        ["1 and 2", "model_risk_manager AND validator",
         "The same adjunction (L-5) that decides every other control set. Depth of control follows materiality"],
        ["3 and 4", "one authorised person",
         "Saying so beats pretending a scheduling heuristic deserves the ceremony of a capital model"],
        ["no tier", "— refused outright —",
         "Approving first and assessing afterwards would be a way of choosing your own control depth, and it is the obvious way to game a rule like this one"]]
th = table(sl, data, ML, y + 0.58, CW, col_w=[1.3, 3.4, 6.9], row_h=0.62, fs=10.5,
           bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 0.58 + th + 0.24, CW * 0.48, 1.7)
para(tf, "Three refusals worth the code", size=12, color=INK, bold=True, font=SERIF,
     first=True, space_after=6)
bullets(tf, [("One decline closes it", "the version returns to its author, and the decline is counted before the quorum is"),
             ("No signing twice under two roles", "a quorum is a number of people, not a number of hats"),
             ("Signing is its own permission", "a validator signs a quorum and may never approve alone")],
        size=10, gap=5, indent_size=9)
x = ML + CW * 0.53
rect(sl, x, y + 0.58 + th + 0.24, CW * 0.47, 1.45, fill=PARCH)
rect(sl, x, y + 0.58 + th + 0.24, 0.045, 1.45, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 0.58 + th + 0.36, CW * 0.47 - 0.5, 1.22)
runs(tf, [("The schema does half of it. ", CRIMSON, True),
          ("UNIQUE (approval, role) enforces one signature per role. The other half — that one "
           "person may not sign twice under two hats — ", INK, False),
          ("cannot be a constraint", INK, True),
          (" and lives in the service, because it is about people rather than about rows.",
           INK, False)], size=10.5, first=True, space_after=0, line=1.22)

sl, y = content("Featuresets — X becomes an object", "Data \u00b7 the feature platform")
tf = txt(sl, ML, y, CW * 0.56, 0.35)
para(tf, "A featureset declares a schema; a version fills it", size=12.5,
     color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.42, CW * 0.56, [
 "inflation   slots: {gb_index, us_index, daily_index}",
 "",
 "@v1  gb_index\u2192UKRPI  us_index\u2192USCPI  daily\u2192DAILY_INFL",
 "@v2  gb_index\u2192UKRPI  us_index\u2192USCPI  daily\u2192EUHICP",
 "",
 "# the model reads daily_index, and always did.",
 "# a version that CANNOT fill the schema is refused:",
 "# it is a different set, or it is a model change.",
], fs=9.5)
tf = txt(sl, ML, y + 0.42 + h + 0.26, CW * 0.56, 1.8)
para(tf, "Every slot pins the feature AND the feature view version supplying it. A set "
         "that named views without pinning them would resolve to different bytes next "
         "month with its digest unchanged \u2014 finding C-2, one level out from the view.",
     size=10.5, color=SLATE, first=True, space_after=6, line=1.24)
para(tf, "The set owns the shape; the warrant owns the window. Otherwise \u201csame "
         "features, 2019\u201323 vs 2020\u201324\u201d would be two featuresets.",
     size=10.5, color=SLATE, space_after=0, line=1.24)

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 0.35)
para(tf, "Derived features: Z = f(X, Y)", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["Rule", "What it prevents"],
        ["Lineage is transitive", "A primitive retired under something deriving from it"],
        ["ingest_ts(Z) = max(inputs)", "A value appearing knowable before its inputs were"],
        ["No slot from the label", "Leakage with a division sign in front"],
        ["Certification is the meet", "Laundering an uncertified input"]]
table(sl, data, x, y + 0.42, CW * 0.40, col_w=[1.75, 2.55], row_h=0.32, fs=9.5,
      hfs=9.5, bold_col0=True, first_col_color=CRIMSON)

rect(sl, ML, y + 4.02, CW, 0.72, fill=PARCH)
rect(sl, ML, y + 4.02, 0.045, 0.72, fill=CRIMSON)
tf = txt(sl, ML + 0.26, y + 4.14, CW - 0.5, 0.6)
runs(tf, [("The language is small on purpose. ", CRIMSON, True),
          ("Arithmetic, nine total functions, the row\u2019s own clock \u2014 whitelisted at the "
           "AST, so what cannot be expressed cannot be smuggled in. MAYA transforms features it "
           "holds; ", INK, False),
          ("it does not run models.", INK, True)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("The parameter object \u2014 an inhabitant of P",
                "Data \u00b7 the feature platform")
tf = txt(sl, ML, y, CW * 0.52, 0.35)
para(tf, "Fitting does not change the kernel", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.42, CW * 0.52, [
 "f : P \u2297 X \u2192 D(Y)      the kernel",
 "fit           picks a point in P",
 "",
 "\u21d2 a fit produces a PARAMETER SET,",
 "  not a model version.",
 "",
 "warrant(fit)   model_version \u00d7 featureset@v \u00d7 window",
 "warrant(score) model_version \u00d7 parameter_set@v",
], fs=9.5)
tf = txt(sl, ML, y + 0.42 + h + 0.26, CW * 0.52, 1.9)
para(tf, "Minting a model version per retrain would make \u201cthe model changed\u201d mean two "
         "different things. But a parameter set changes behaviour, so it is immutable, "
         "versioned, and cannot be run on until somebody other than whoever recorded it "
         "has approved \u2014 the gate that governs versions, applied to the other half of the pair.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

x = ML + CW * 0.57
tf = txt(sl, x, y, CW * 0.43, 0.35)
para(tf, "Three routes, three depths of governance", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=0)
data = [["Provenance", "Evidence", "Governed"],
        ["fitted", "A warrant MAYA issued", "Each set"],
        ["calibrated", "Market data, daily", "The procedure"],
        ["declared", "A person\u2019s assertion", "Attestation"]]
table(sl, data, x, y + 0.42, CW * 0.43, col_w=[1.35, 1.95, 1.35], row_h=0.32,
      fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 1.95, CW * 0.43, 1.9)
para(tf, "The middle row is why provenance is not cosmetic: a Hull\u2013White model "
         "recalibrated every morning would drown the register if each day needed a "
         "committee. The bottom row is the model that never trains \u2014 a closed form "
         "arrives with its parameters, and L-W1 refuses it a fit warrant as a type error.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

rect(sl, ML, y + 4.02, CW, 0.72, fill=PARCH)
rect(sl, ML, y + 4.02, 0.045, 0.72, fill=CRIMSON)
tf = txt(sl, ML + 0.26, y + 4.14, CW - 0.5, 0.6)
runs(tf, [("Accepted only against a warrant we issued. ", CRIMSON, True),
          ("No back door. Without it, ", INK, False),
          ("\u201cwhich data produced these numbers\u201d has no answer", INK, True),
          (", and the lineage the pinned versions and bitemporal clocks exist to establish "
           "stops one step short of the thing it was for.", INK, False)],
     size=11, first=True, space_after=0, line=1.24)
