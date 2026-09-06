# ============================================================ CH 18
_state["chapter"] = "18 · The feature platform"

sl, y = content("Point-in-time assembly", "Data · core/features/assembly.py")
h = code(sl, ML, y, CW * 0.54, [
 "gate = static_check(req)                       # LAYER 1",
 "if not gate.passed:",
 "    raise AssemblyRejected(gate.detail)        # rejected, not sampled",
 "",
 "rows   = self._join(spine, views, as_of)       # per view, per row",
 "report = verify_sampled(rows, self._recompute) # LAYER 2",
 "report.leakage = detect_leakage(rows)          # purity screen",
 "",
 "self._persist(name, rows, as_of, report, ...)  # Delta + evidence",
], fs=9.5, title="THE ASSEMBLY")
x = ML + CW * 0.57
h2 = code(sl, x, y, CW * 0.43, [
 "knowable_by = min(label_ts, as_of)",
 "eligible = [r for r in records",
 "            if r[VALID_TIME]  <= label_ts",
 "            and r[INGEST_TIME] <= knowable_by]",
 "return max(eligible,",
 "           key=lambda r: (r[VALID_TIME],",
 "                          r[INGEST_TIME]))",
], fs=9.5, title="THE POINT-IN-TIME READ")
tf = txt(sl, ML, y + max(h, h2) + 0.28, CW, 1.6)
runs(tf, [("Two clocks, and the min is the reproducibility guarantee. ", CRIMSON, True),
          ("Valid time is what was true by the label; transaction time is what was knowable by it. Bounding ingest by ",
           INK, False),
          ("min(ℓ, a)", INK, False, False, MONO),
          (" makes every a ≥ ℓ give the same answer: the row assembled the day the label matured and the same row "
           "re-assembled a year later are identical, however many restatements arrived in between. Delta supplies the "
           "second clock — a version pinned per view, read through ", INK, False),
          ("deltalake", INK, False, False, MONO),
          (". There is no Spark here: the join is a Python loop over the rows of a pinned Delta version, which is the "
           "same operator at a smaller scale and is where a cluster engine would go.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.28)

sl, y = content("Three layers, and what each actually proves", "Data · leakage verification")
data = [["Layer", "What it does", "What it proves"],
        ["1 · Static analysis", "Requires BOTH a valid-time and a transaction-time bound on the assembly. Missing either and it is rejected outright",
         "A genuine proof for the dominant leakage class. This is the strong check"],
        ["2 · Sampling", "One recomputation of 200 sampled rows by a second code path, compared against the assembled values. Rows are bucketed by label value only",
         "Implementation drift between the two paths. NOT a wrong rule: both paths would be wrong together"],
        ["3 · Injection", "tests/test_features.py plants a deliberately leaky feature the verifier must catch",
         "That the verifier still works — the failure mode that would otherwise be silent"]]
th = table(sl, data, ML, y, CW, col_w=[2.0, 5.4, 4.2], row_h=0.72, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + th + 0.28, CW, 1.55, fill=CRIMSON)
tf = txt(sl, ML + 0.35, y + th + 0.40, CW - 0.7, 1.32)
para(tf, "What layer 2 does not claim", size=13.5, color=WHITE, bold=True, font=SERIF, first=True, space_after=5)
runs(tf, [("The sample is 200, hard-coded; the stratum is the label value and nothing else; and no power computation "
           "exists anywhere in the repository. ", WHITE, True),
          ("So “detects systematic violations at a stated statistical power” was a claim about a number nobody computes. "
           "It catches the two paths disagreeing. A leak confined to a rare, high-value segment is exactly where it fails, "
           "and layer 1 remains the only one that proves something about the data.",
           RGBColor(0xF6,0xE0,0xE4), False)], size=11, space_after=0, line=1.26)

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
], fs=11, title="THE VERSION WOULD BE PART OF THE KEY")
x = ML + CW * 0.50
data = [["Phase", "Behaviour"],
        ["Publish v(n+1)", "Begin dual-write to both namespaces"],
        ["Steady state", "Serving reads the namespace PINNED BY THE CONTRACT, never “latest”"],
        ["Retire v(n)", "Only when zero active contracts reference it — a governed action with consumer-impact check"]]
table(sl, data, x, y + 1.30, CW * 0.50, col_w=[1.7, 4.3], row_h=0.40, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 2.55, CW * 0.46, 1.8)
runs(tf, [("Law L-17 is one of the five that do not run. ", CRIMSON, True),
          ("It is a runtime check by nature: the namespace served must equal the namespace pinned, compared "
           "continuously, because nothing inspectable before deployment can see it. ", INK, False),
          ("Half of it exists: ", CRIMSON, True),
          ("core/features/contracts.py computes what serving must read. There is no online store to compare it "
           "against, so the table on the right is the design and not the behaviour.", INK, False)],
     size=11, first=True, space_after=0, line=1.26)

sl, y = content("Monitoring reads two streams, and the gap between them is the point",
                "Data · telemetry and evaluation")
bw = (CW - 0.5) / 2
rect(sl, ML, y, bw, 1.00, fill=WHITE, line=RULE)
rect(sl, ML, y, bw, 0.05, fill=CRIMSON)
tf = txt(sl, ML + 0.26, y + 0.16, bw - 0.52, 0.80)
para(tf, "scores", size=13, color=CRIMSON, bold=True, font=MONO, first=True, space_after=3)
para(tf, "What the model produced, when it produced it. entity_id · scored_at · score",
     size=10.5, color=SLATE, space_after=0, line=1.2)
rect(sl, ML + bw + 0.5, y, bw, 1.00, fill=WHITE, line=RULE)
rect(sl, ML + bw + 0.5, y, bw, 0.05, fill=NAVY)
tf = txt(sl, ML + bw + 0.76, y + 0.16, bw - 0.52, 0.80)
para(tf, "outcomes", size=13, color=NAVY, bold=True, font=MONO, first=True, space_after=3)
para(tf, "What actually happened, learned later. entity_id · label · label_ts",
     size=10.5, color=SLATE, space_after=0, line=1.2)
data = [["Ingestion rule", "The failure it prevents"],
        ["Idempotent on the digest of the batch's own rows",
         "Collectors deliver at least once; double-counting a redelivered batch reports a population that never existed"],
        ["A row without its OWN timestamp is refused",
         "Stamping it with the batch's arrival time is how every window silently becomes wrong"],
        ["The sample rate travels on every row",
         "A statistic that cannot say what population it speaks for"],
        ["Labels join at READ time, and unlabelled rows come back unlabelled",
         "The monitor decides maturity per row; a join that dropped the unlabelled would have decided for it"],
        ["A drift monitor's reference window is STATED",
         "“What is this drifting from” belonging to whoever ran it rather than to the record"]]
th = table(sl, data, ML, y + 1.20, CW * 0.60, col_w=[2.9, 4.1], row_h=0.50, fs=9.5, hfs=10,
           bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.63
tf = txt(sl, x, y + 1.20, CW * 0.37, 1.5)
para(tf, "Delayed labels are the hard part", size=12, color=INK, bold=True, font=SERIF, first=True, space_after=6)
para(tf, "A monitor declares a label_delay; performance is computed only over the vintage cohort whose outcome window "
         "has closed, and an immature cohort is refused rather than reported.",
     size=10.5, color=SLATE, space_after=6, line=1.24)
runs(tf, [("An AUC on immature outcomes is worse than no AUC", INK, True),
          (" — it is confidently wrong in a direction nobody checks.", SLATE, False)], size=10.5, line=1.24)
data = [["Class", "Default metrics"],
        ["T1 calibrated", "Calibration error, arbitrage-free checks"],
        ["T2 / T3", "KS, AUC, PSI, Hosmer–Lemeshow"],
        ["T4 adaptive", "Parameter-change magnitude"],
        ["T5 foundation", "Groundedness, hallucination rate"],
        ["T6 opaque", "Own-outcomes divergence"],
        ["T8 authored", "Rule-fire distribution, exception rate"]]
table(sl, data, x, y + 3.05, CW * 0.37, col_w=[1.5, 3.0], row_h=0.30, fs=9.5, hfs=9.5,
      bold_col0=True, first_col_color=CRIMSON)
