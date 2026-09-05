# ============================================================ CH 18
divider("18", "The Feature Platform",
        "Point-in-time correctness, version-namespaced serving, monitoring at scale.",
        ["The PIT assembly",
         "Three-layer verification",
         "Serving what the contract pinned",
         "Monitoring, and its telemetry"])

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
para(tf, "What law L-10 claims, exactly", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=6)
runs(tf, [("“No assembly passes without a static temporal bound, and sampling detects systematic violations at stated power.”  ",
           WHITE, True),
          ("Detection, not absence: a leak confined to a rare, high-value segment is exactly where sampling fails and where the "
           "damage is greatest. Layer 1 is the only one that proves something about the data.",
           RGBColor(0xF6,0xE0,0xE4), False)], size=11.5, space_after=0, line=1.26)

sl, y = content("Serving must read the version the contract pinned",
                "Data · training–serving skew")
rect(sl, ML, y, CW, 1.10, fill=RGBColor(0x8B,0x2F,0x2F))
tf = txt(sl, ML + 0.35, y + 0.16, CW - 0.7, 0.88)
runs(tf, [("The failure this prevents. ", WHITE, True),
          ("A contract pins feature view v7; an online store serving “latest” hands the model features it was never "
           "fitted on — ", RGBColor(0xF6,0xE0,0xE4), False),
          ("with the contract digest still matching and every monitor green.", WHITE, True),
          ("  Silently wrong production scoring, introduced by the platform that exists to prevent it.",
           RGBColor(0xF6,0xE0,0xE4), False)],
     size=11.5, first=True, space_after=0, line=1.26)
h = code(sl, ML, y + 1.35, CW * 0.46, [
 "key = f\"fv:{feature_view_id}:v{version}:{entity_id}\"",
], fs=11, title="THE VERSION IS PART OF THE KEY")
x = ML + CW * 0.50
data = [["Phase", "Behaviour"],
        ["Publish v(n+1)", "Begin dual-write to both namespaces"],
        ["Steady state", "Serving reads the namespace PINNED BY THE CONTRACT, never “latest”"],
        ["Retire v(n)", "Only when zero active contracts reference it — a governed action with consumer-impact check"]]
table(sl, data, x, y + 1.30, CW * 0.50, col_w=[1.7, 4.3], row_h=0.40, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 2.50, CW * 0.46, 1.6)
runs(tf, [("Law L-17 is a runtime check, not a design-time one. ", CRIMSON, True),
          ("The namespace served must equal the namespace pinned, compared continuously, because nothing "
           "inspectable before deployment can see this. ", INK, False),
          ("Half of it exists today: ", CRIMSON, True),
          ("the contract computes what serving must read, and no online store exists yet to read it. "
           "The other half arrives with the store.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

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

sl, y = content("Telemetry — the other half of monitoring", "Data · ingestion")
tf = txt(sl, ML, y, CW, 0.50)
runs(tf, [("A monitor that has to be ", INK, False), ("handed", INK, True),
          (" its rows is a monitor somebody has to remember to feed. Ingestion is the other half — and it "
           "is two streams, never one, because the gap between them is what delayed labels reason about.",
           INK, False)],
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
data = [["Rule", "The failure it prevents"],
        ["Idempotent on the digest of the batch's own rows",
         "Collectors deliver at least once, and double-counting a redelivered batch reports a population that never existed"],
        ["A row without its OWN timestamp is refused",
         "Stamping it with the batch's arrival time is how every window silently becomes wrong"],
        ["The sample rate travels on every row",
         "A statistic that cannot say what population it speaks for"],
        ["Labels join at READ time, and unlabelled rows come back unlabelled",
         "The monitor decides maturity per row; a join that dropped the unlabelled would have decided for it"],
        ["A drift monitor's reference window is STATED",
         "“What is this drifting from” belonging to whoever ran it rather than to the record"]]
table(sl, data, ML, y + 2.00, CW, col_w=[3.6, 8.0], row_h=0.44, fs=10, hfs=10.5,
      bold_col0=True, first_col_color=CRIMSON)
