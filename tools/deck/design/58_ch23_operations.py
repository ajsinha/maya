# ============================================================ CH 23
divider("23", "Cross-cutting and Operations",
        "Transactions, concurrency, errors, SLOs, capacity, testing.",
        ["Transactions and the outbox",
         "Concurrency and idempotency",
         "Error taxonomy",
         "SLOs and signals",
         "Capacity",
         "Testing"])

sl, y = content("Transactions and the outbox", "Cross-cutting · consistency")
h = code(sl, ML, y, CW * 0.52, [
 "with uow.transaction() as tx:      # ONE Postgres transaction",
 "    ...domain mutations...",
 "    tx.evidence.append(...)        # same transaction — DR-4",
 "    tx.audit.write(...)            # same transaction",
 "    tx.outbox.put(event)           # the only way out",
 "",
 "# commit → relay → Kafka / Delta / cache invalidation",
], fs=10, title="db/database.py")
tf = txt(sl, ML, y + h + 0.28, CW * 0.52, 2.2)
para(tf, "Rules that follow", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, ["Nothing outside platform/db opens a transaction — components receive a UnitOfWork",
             "A derived value and its derivation record commit together, or neither does",
             "Every Delta write carries outbox_id and MERGEs on it, so at-least-once delivery is safe",
             "Nightly reconciliation compares outbox(done) against Delta counts — with a defined repair action, not merely an alert"],
        size=11, gap=6)
x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 0.35)
para(tf, "Partitioning and retention", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Table", "Partition", "Retention"],
        ["audit_log", "Monthly, separate database", "10 y, WORM"],
        ["evidence_node", "Monthly", "Life + 10 y"],
        ["ai_generation", "Monthly", "3 y"],
        ["inference_log (Delta)", "By date, clustered by model_urn", "Per regulatory class"]]
table(sl, data, x, y + 0.40, CW * 0.44, col_w=[2.2, 2.6, 1.6], row_h=0.42, fs=9.5, hfs=10, bold_col0=True, first_col_color=CRIMSON)
rect(sl, x, y + 2.55, CW * 0.44, 1.15, fill=PARCH)
rect(sl, x, y + 2.55, 0.045, 1.15, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 2.69, CW * 0.44 - 0.5, 0.95)
runs(tf, [("Audit lives on its own database. ", CRIMSON, True),
          ("It is write-heavy and cannot be lost; evidence traversal is read-heavy and recursive. On one primary they compete.",
           INK, False)], size=11, first=True, space_after=0, line=1.24)

sl, y = content("Concurrency, idempotency, caching", "Cross-cutting · correctness under load")
data = [["Hazard", "Control"],
        ["Concurrent alias moves", "Postgres advisory lock per (model, environment)"],
        ["Concurrent version creation", "Unique (model_id, semver); content-addressed artifacts deduplicate"],
        ["Evidence chain contention", "Short lock around seq allocation only; append is O(1)"],
        ["Duplicate API submissions", "Idempotency-Key with a 24-hour replay of the original response"],
        ["Lost updates on inventory edits", "ETag / If-Match; 412 returns a field-level diff"],
        ["Duplicate outbox delivery", "MERGE on outbox_id"],
        ["Concurrent materialisation", "Delta ACID; view version pinned per job"]]
th = table(sl, data, ML, y, CW * 0.53, col_w=[2.6, 4.0], row_h=0.36, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.57
tf = txt(sl, x, y, CW * 0.43, 0.35)
para(tf, "Cache inventory", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Cache", "TTL", "Invalidation"],
        ["Warrant descriptor (Redis)", "60 s – 1 h by tier", "Pre-warm, then swap"],
        ["Warrant descriptor (LRU)", "≤ TTL", "Epoch bump"],
        ["Inventory summary", "materialised", "Domain event"],
        ["Rendered documents", "indefinite", "evidence_digest change"],
        ["Blast-radius closure", "24 h", "Edge change"],
        ["Policy bundles", "version", "On publish"]]
table(sl, data, x, y + 0.40, CW * 0.43, col_w=[2.3, 1.7, 1.9], row_h=0.34, fs=9.5, hfs=10, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Error taxonomy", "Cross-cutting · never a bare 500")
data = [["Code", "HTTP", "Meaning", "Client action"],
        ["validation_failed", "422", "Payload or manifest invalid", "Fix and retry"],
        ["artifact_rejected", "422", "Scan or format policy refused it", "Convert format, or request an expiring exception"],
        ["transition_blocked", "409", "Lifecycle guards unmet", "Follow deny_reason[].remediation_url"],
        ["policy_denied", "403", "A gate refused", "As above"],
        ["no_entitlement", "403", "No grant for this principal and use", "Request a grant"],
        ["use_not_approved", "403", "Declared use is not an approved use", "Seek approval"],
        ["restricted", "423", "Blocking finding or suspension", "Remediate, or break-glass"],
        ["revoked", "410", "Warrant revoked", "Stop — do not retry"],
        ["step_up_required", "403", "Re-authentication needed", "Re-authenticate with intent"],
        ["precondition_failed", "412", "ETag mismatch", "Refetch, merge, retry"],
        ["quota_exceeded", "429", "Rate, quota or cost budget", "Back off"],
        ["evidence_truncated", "200 + flag", "Provenance term cap reached", "Narrow the query"]]
th = table(sl, data, ML, y, CW, col_w=[2.5, 1.2, 4.2, 3.7], row_h=0.275, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + th + 0.24, CW, 0.5)
runs(tf, [("Anything unmapped ", INK, False),
          ("is logged with a correlation id and returned as internal_error carrying that id", INK, True),
          (" — so the user and support are looking at the same event, not two different ones.", INK, False)],
     size=11.5, first=True, space_after=0)

sl, y = content("SLOs and golden signals", "Operations")
data = [["SLO", "Target", "Error budget"],
        ["Warrant resolution availability", "99.99%", "4.3 min / month"],
        ["Warrant resolution p99 (cached)", "< 50 ms", "1% of requests"],
        ["Control plane availability", "99.9%", "43 min / month"],
        ["Inventory read p95", "< 500 ms", "5%"],
        ["Training-set build (1B × 500)", "< 30 min", "10%"],
        ["Document compile p95", "< 60 s", "5%"],
        ["Evidence chain verification", "Daily, zero breaks", "Zero tolerance"]]
table(sl, data, ML, y, CW * 0.50, col_w=[3.0, 1.6, 1.7], row_h=0.36, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.54
tf = txt(sl, x, y, CW * 0.46, 0.35)
para(tf, "Golden signals, per component", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
tf = txt(sl, x, y + 0.42, CW * 0.46, 2.6)
bullets(tf, [("Warrant service", "resolutions/s · cache hit ratio · p50/p99 · denial rate · revocation lag · degraded-mode volume"),
             ("Control plane", "request rate · latency · error rate by taxonomy code · transaction duration · outbox lag"),
             ("Workers", "queue depth · job duration · retry rate · sandbox failures"),
             ("Data plane", "job duration · rows processed · small-file count · skew divergence · PIT rejections")],
        size=11, gap=6, indent_size=9.5)
rect(sl, x, y + 3.10, CW * 0.46, 0.85, fill=PARCH)
rect(sl, x, y + 3.10, 0.045, 0.85, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 3.23, CW * 0.46 - 0.5, 0.70)
para(tf, "Ten runbooks: chain verification failure · outbox lag · stampede · Delta small files · sandbox escape · policy gridlock · revocation failure · base-model drift · key rotation · regional failover",
     size=10, color=INK, first=True, space_after=0, line=1.22)

sl, y = content("Capacity and testing", "Operations · sizing and assurance")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Capacity model", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Dimension", "Year 1", "Year 3"],
        ["Models", "1,500", "5,000"],
        ["Versions", "8,000", "40,000"],
        ["Evidence nodes", "4 M", "25 M"],
        ["Postgres (ex-audit)", "120 GB", "600 GB"],
        ["Audit rows", "60 M", "400 M"],
        ["Delta features", "15 TB", "80 TB"],
        ["Inference log rows", "8 B", "60 B"],
        ["Warrant resolutions, peak", "400/s", "2,500/s"]]
table(sl, data, ML, y + 0.40, CW * 0.47, col_w=[2.9, 1.4, 1.4], row_h=0.31, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Test suites and what each proves", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Suite", "Proves"],
        ["Unit", "Domain algebra correctness (≥90% on domain/)"],
        ["Laws — the executable ones", "L-4, L-5, L-7, L-12, L-18, L-19 and the eleven warrant laws. The rest are stated and not yet executable, and 00 §12 says which"],
        ["Integration", "Repository and service paths against real infrastructure"],
        ["Contract", "API matches the spec; SDK round-trips"],
        ["Adversarial", "Leakage injection · RLS negative tests · stampede load · malicious artifacts"],
        ["Migration", "Up and down against production-shaped data"],
        ["Performance", "The SLOs, or the build fails"]]
th = table(sl, data, x, y + 0.40, CW * 0.47, col_w=[1.8, 4.0], row_h=0.36, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 0.40 + th + 0.20, CW * 0.47, 0.9)
runs(tf, [("Why adversarial tests are not optional. ", CRIMSON, True),
          ("A PIT verifier that silently stops detecting leakage, or an RLS policy that silently stops isolating, is a catastrophic "
           "invisible regression. Both are tested by injecting the failure they must catch.", INK, False)],
     size=10.5, first=True, space_after=0, line=1.24)
