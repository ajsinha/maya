# ============================================================ CH 16
divider("16", "Architecture and Design Rules",
        "Components, responsibilities, and the seven rules that bind them.",
        ["Component inventory",
         "Responsibility boundaries",
         "Seven design rules",
         "Process model"])

sl, y = content("Component inventory", "Overview · structure")
LAYERS = [
    ("Interfaces", NAVY, ["maya-web (static)", "REST API v1", "SDK / CLI", "Event stream"]),
    ("Governance subsystems", CRIMSON, ["Registry", "Evidence engine", "Risk & tiering", "Regimes & policy",
                                        "Lifecycle", "Validation", "Doc compiler", "Overlays"]),
    ("Data & execution", RGBColor(0x2D,0x50,0x16), ["Feature platform", "Monitoring", "Warrant service", "Machine assistance"]),
    ("Core domain — no I/O, no framework", RGBColor(0x1F,0x3A,0x5F),
     ["model_algebra", "contracts", "schemas", "identity", "composition"]),
    ("Platform", RGBColor(0x4A,0x3A,0x1F), ["config", "db & outbox", "telemetry", "plugin loader", "sandbox client"]),
]
yy = y + 0.02
for name, col, mods in LAYERS:
    hh = 0.80 if len(mods) > 5 else 0.62
    rect(sl, ML, yy, CW, hh, fill=WHITE, line=RULE)
    rect(sl, ML, yy, 0.05, hh, fill=col)
    tf = txt(sl, ML + 0.24, yy + 0.10, 2.9, hh - 0.2)
    para(tf, name, size=11, color=col, bold=True, first=True, space_after=0, line=1.1)
    per = 4 if len(mods) <= 5 else 4
    for j, m in enumerate(mods):
        mx = ML + 3.30 + (j % per) * ((CW - 3.45) / per)
        my = yy + 0.11 + (j // per) * 0.32
        rect(sl, mx, my, (CW - 3.45) / per - 0.10, 0.27, fill=PARCH)
        tfm = txt(sl, mx, my + 0.045, (CW - 3.45) / per - 0.10, 0.22, align=PP_ALIGN.CENTER)
        para(tfm, m, size=8.5, color=INK, first=True, space_after=0)
    yy += hh + 0.13
tf = txt(sl, ML, yy + 0.06, CW, 0.4)
runs(tf, [("Dependency rule, enforced in CI. ", CRIMSON, True),
          ("Arrows point downward only. The core domain imports nothing from MAYA; interfaces import everything and are imported by nothing.",
           INK, False)], size=11.5, first=True, space_after=0)

sl, y = content("Responsibility boundaries", "Overview · what each component does not own")
data = [["Component", "Owns", "Does NOT own"],
        ["Core domain", "The algebra: kernels, contracts, schema lattice, probe equivalence", "Persistence, HTTP, orchestration"],
        ["Registry", "Models, versions, artifacts, aliases, fibres, introspection", "Whether a version may be promoted"],
        ["Evidence engine", "Append chain, semiring evaluation, gluing", "What evidence means for a gate"],
        ["Risk & tiering", "Lattices, τ, control adequacy, derivation traces", "Overriding a tier — that is workflow"],
        ["Regimes & policy", "Institutions, comorphisms, Rego gates, MTL obligations", "Executing a transition"],
        ["Lifecycle", "State machines, transitions, approvals, segregation of duties", "Guard content — that is policy"],
        ["Validation", "Plans, test execution, findings, remediation", "Computing metrics at scale"],
        ["Feature platform", "Registry, materialisation, PIT, contracts, skew", "Model semantics"],
        ["Monitoring", "Monitor definitions, evaluation, breaches, health", "Deciding consequences"],
        ["Warrant service", "Resolution, signing, revocation, telemetry ingest", "Any governance decision — it reads a projection"],
        ["Machine assistance", "Capabilities, grounding, citation checking, oracles", "Any governance state transition"]]
table(sl, data, ML, y, CW, col_w=[2.4, 4.9, 4.3], row_h=0.315, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Seven design rules", "Overview · what binds every component")
rules = [("DR-1", "Ports, not internals", "A component exposes a Protocol and is consumed only through it. No cross-component imports of internals."),
         ("DR-2", "Domain is pure", "Domain logic is synchronous and side-effect free. I/O lives in adapters at the component edge."),
         ("DR-3", "Idempotent writes", "Every write path is idempotent given an Idempotency-Key or a natural key."),
         ("DR-4", "Derivations are written", "Every derived value is persisted with its derivation record, in the same transaction."),
         ("DR-5", "One transaction owner", "Nothing outside platform/db opens a transaction. Components receive a UnitOfWork."),
         ("DR-6", "No bare failures", "Every externally visible failure maps to the error taxonomy. Never an unmapped 500."),
         ("DR-7", "Blocking must explain", "Anything that blocks a user returns why, and a link to remediate it.")]
cw = (CW - 0.26 * 3) / 4
for i, (n, t, d) in enumerate(rules):
    card(sl, ML + (i % 4) * (cw + 0.26), y + (i // 4) * 2.35, cw, 2.15, n, t, d)

sl, y = content("Process model", "Overview · deployable units")
data = [["Unit", "Scaling", "Why it is separate", "Fails independently?"],
        ["maya-web", "Static, CDN + 2 pods", "Separate process and pipeline (ADR-011); the API is the only interface", "Yes — stops human review only"],
        ["maya-api", "3–10 pods, CPU-bound", "The bulk of the domain; deploys together for transactional integrity", "—"],
        ["maya-warrants", "10–100 pods, regional", "10× tighter SLA; reads only the warrant projection; survives control-plane outage", "Yes — by design"],
        ["maya-worker", "Queue-depth autoscaled", "Long-running, retryable, at-least-once", "Yes"],
        ["maya-sandbox", "Job per task, gVisor", "Never runs untrusted code in-process with the control plane", "Yes"],
        ["Spark / Databricks", "Cluster-managed", "Data-plane compute: PIT joins, materialisation, monitoring", "Yes"]]
th = table(sl, data, ML, y, CW, col_w=[2.2, 2.3, 5.2, 2.5], row_h=0.42, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + th + 0.28, CW, 0.90, fill=PARCH)
rect(sl, ML, y + th + 0.28, 0.045, 0.90, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + th + 0.42, CW - 0.6, 0.7)
runs(tf, [("The one asymmetry. ", CRIMSON, True),
          ("Governance must not become the bank's single point of failure. If the control plane is down, already-authorised "
           "production scoring continues; only new issuance and governance changes stop.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)
