# ============================================================ CH 16
# The chapter divider is gone; the footer still has to say where the reader is.
_state["chapter"] = "16 · Architecture and design rules"

sl, y = content("Component inventory", "Overview · structure")
LAYERS = [
    ("Interfaces", NAVY, ["routes/ (Flask UI)", "REST API v1", "Python SDK / CLI", "notify (outbound)"]),
    ("Governance subsystems", CRIMSON, ["Registry", "Evidence engine", "Risk & tiering", "Regimes & policy",
                                        "Lifecycle", "Validation", "Doc compiler", "Overlays"]),
    ("Data & execution", RGBColor(0x2D,0x50,0x16), ["Feature platform", "Monitoring", "Warrant service", "Machine assistance"]),
    ("Core domain — no I/O, no framework", RGBColor(0x1F,0x3A,0x5F),
     ["algebra", "contracts", "schemas", "identity", "lattice"]),
    ("Platform", RGBColor(0x4A,0x3A,0x1F), ["config", "db (schema + repos)", "core/log", "core/ports.py", "scheduler"]),
]
yy = y + 0.02
for name, col, mods in LAYERS:
    hh = 0.80 if len(mods) > 5 else 0.62
    rect(sl, ML, yy, CW, hh, fill=WHITE, line=RULE)
    rect(sl, ML, yy, 0.05, hh, fill=col)
    tf = txt(sl, ML + 0.24, yy + 0.10, 2.9, hh - 0.2)
    para(tf, name, size=11, color=col, bold=True, first=True, space_after=0, line=1.1)
    per = 4
    for j, m in enumerate(mods):
        mx = ML + 3.30 + (j % per) * ((CW - 3.45) / per)
        my = yy + 0.11 + (j // per) * 0.32
        rect(sl, mx, my, (CW - 3.45) / per - 0.10, 0.27, fill=PARCH)
        tfm = txt(sl, mx, my + 0.045, (CW - 3.45) / per - 0.10, 0.22, align=PP_ALIGN.CENTER)
        para(tfm, m, size=8.5, color=INK, first=True, space_after=0)
    yy += hh + 0.13
tf = txt(sl, ML, yy + 0.06, CW, 0.55)
runs(tf, [("The dependency rule, and what actually holds it. ", CRIMSON, True),
          ("Arrows point downward only: the core domain imports nothing from MAYA, interfaces import everything and are "
           "imported by nothing. ", INK, False),
          ("tests/test_import_discipline.py", INK, False, False, MONO),
          (" walks every import and fails the suite on a crossing. It is a test, not a pipeline — this repository has no CI, "
           "no linter and no type checker, so the rule holds for as long as somebody runs pytest.", INK, False)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("Responsibility boundaries", "Overview · what each component does not own")
data = [["Component", "Owns", "Does NOT own"],
        ["Core domain", "The algebra: kernels, contracts, schema lattice, probe equivalence", "Persistence, HTTP, orchestration"],
        ["Registry", "Models, versions, artifacts, aliases, fibres, introspection", "Whether a version may be promoted"],
        ["Evidence engine", "The append-only chain, semiring evaluation, provenance", "What evidence means for a gate"],
        ["Risk & tiering", "The two lattices, tier derivation, control adequacy, traces", "Overriding a tier — that is workflow"],
        ["Regimes & policy", "Regimes as institutions, their translations, versioned gates", "Executing a transition"],
        ["Lifecycle", "State machines, transitions, approvals, segregation of duties", "Guard content — that is policy"],
        ["Validation", "Plans, test execution, findings, remediation", "Computing metrics at scale"],
        ["Feature platform", "Registry, materialisation, PIT, contracts, skew", "Model semantics"],
        ["Monitoring", "Monitor definitions, evaluation, breaches, health", "Deciding consequences"],
        ["Warrant service", "Resolution, signing, revocation, telemetry ingest", "Any governance decision — it reads a projection"],
        ["Machine assistance", "Capabilities, grounding, citation checking, oracles", "Any governance state transition"]]
table(sl, data, ML, y, CW, col_w=[2.4, 4.9, 4.3], row_h=0.315, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Seven design rules, and what enforces each", "Overview · what binds every component")
rules = [("DR-1", "Ports, not internals", "A component is consumed through a Protocol in core/ports.py, never through another component's internals."),
         ("DR-2", "Domain is pure", "Domain logic is synchronous and side-effect free; I/O lives in adapters at the edge. The one rule with a test."),
         ("DR-3", "Idempotent where claimed", "There is no Idempotency-Key header. Idempotency is per path, from a natural key: a redelivered telemetry batch and a re-run anchor write nothing."),
         ("DR-4", "Derivations are written", "A derived value is persisted with its derivation record — the tier rationale, the alias proof, the PIT report."),
         ("DR-5", "One transaction owner", "db/database.py owns the only re-entrant transaction(). The evidence append is its one caller, because read-the-head-then-insert is why it exists."),
         ("DR-6", "No bare failures", "Each subsystem's common.py defines its error with a code and as_problem(). Never an unmapped 500."),
         ("DR-7", "Blocking must explain", "Anything that blocks a user returns why, and a remediation string saying what would unblock it.")]
cw = (CW - 0.26 * 3) / 4
for i, (n, t, d) in enumerate(rules):
    card(sl, ML + (i % 4) * (cw + 0.26), y + (i // 4) * 2.30, cw, 2.10, n, t, d)
note(sl, ML + 3 * (cw + 0.26), y + 2.30, cw, 2.10,
     "Six are conventions. ",
     "Only DR-2 is mechanised. The rest are held by review — indistinguishable from enforcement until somebody "
     "does not keep one.")

sl, y = content("Process model — one process today, five units by design",
                "Overview · deployment")
data = [["Unit", "Status", "Why it is separate", "Fails independently?"],
        ["Flask app (routes/)", "Built — one process", "UI and REST API v1 are served by the same app; the API is the only interface", "—"],
        ["Scheduler loop", "Built — in-process thread", "Twelve jobs on a timer, off by default and enabled in config", "No — shares the process"],
        ["Sandbox child", "Built — fork + rlimits", "An artifact's bugs must not become the platform's; CPU and address space bounded", "Yes"],
        ["maya-warrants", "Designed, not built", "10× tighter SLA; would read only the warrant projection", "By design, once split"],
        ["Cluster data plane", "Designed, not built", "PIT joins and materialisation run in-process on pandas + deltalake today", "—"]]
th = table(sl, data, ML, y, CW, col_w=[2.4, 2.3, 5.1, 2.4], row_h=0.46, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.30,
     "The one asymmetry, and it is a design not a deployment. ",
     "Governance must not become the bank's single point of failure: if the control plane is down, already-authorised "
     "production scoring should continue and only new issuance and governance changes stop. Today one process holds "
     "both, so that separation is a property of the drawing rather than of the estate. It is written here as the "
     "target, in the tense it has earned.")
