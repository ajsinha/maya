"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
# -*- coding: utf-8 -*-
"""MAYA — Detailed System Design deck. Harvard-Crimson theme (see theme.py)."""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.py")).read())

MONO = "Consolas"

def code(sl, x, y, w, lines, fs=9.5, title=None):
    """Monospace block sized from its own content."""
    LINE = 1.34
    lh = fs * LINE * 1.26 / 72.0   # measured against the render; over-sizing is harmless, under-sizing is a defect
    head = 0.32 if title else 0.0
    h = head + len(lines) * lh + 0.30
    rect(sl, x, y, w, h, fill=RGBColor(0xF4, 0xF2, 0xEF))
    rect(sl, x, y, 0.045, h, fill=SLATE)
    if title:
        tf = txt(sl, x + 0.22, y + 0.10, w - 0.4, 0.24)
        para(tf, title, size=9, color=CRIMSON, bold=True, first=True, space_after=0)
    tf = txt(sl, x + 0.22, y + head + 0.11, w - 0.4, h - head - 0.2)
    for i, ln in enumerate(lines):
        col = MUTED if ln.strip().startswith("#") else INK
        para(tf, ln if ln else " ", size=fs, color=col, font=MONO,
             first=(i == 0), space_after=0, line=1.34)
    return h

def steps(sl, x, y, w, items, h=1.45):
    n = len(items); gap = 0.20
    bw = (w - gap * (n - 1)) / n
    for i, (num, t, d) in enumerate(items):
        xx = x + i * (bw + gap)
        rect(sl, xx, y, bw, h, fill=WHITE, line=RULE)
        rect(sl, xx, y, bw, 0.05, fill=CRIMSON)
        tf = txt(sl, xx + 0.16, y + 0.16, bw - 0.32, h - 0.3)
        para(tf, num, size=14, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=2)
        para(tf, t, size=11, color=INK, bold=True, space_after=4)
        para(tf, d, size=8.5, color=SLATE, line=1.15)

# ============================================================ TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.35, fill=CRIMSON)
rect(sl, 0, 4.35, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.35, fill=CRIMSON_D)
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                    "assets", "logo", "maya-mark-white.png")
if os.path.exists(LOGO):
    sl.shapes.add_picture(LOGO, In(ML + 0.30), In(0.70), In(0.80), In(0.80))
tf = txt(sl, ML + 1.24, 0.99, CW - 1.04, 0.34)
para(tf, "MAYA  ·  MODEL & AI LIFECYCLE ASSURANCE PLATFORM",
     size=11, color=RGBColor(0xE8,0xB8,0xC0), bold=True, first=True, space_after=0)
tf = txt(sl, ML + 0.3, 1.62, CW * 0.88, 2.0)
para(tf, "Detailed System Design", size=44, color=WHITE, font=SERIF, first=True, space_after=4)
rect(sl, ML + 0.3, 3.28, 1.7, 0.035, fill=RGBColor(0xE8,0xB8,0xC0))
tf = txt(sl, ML + 0.3, 3.54, CW * 0.82, 0.8)
para(tf, "Component interfaces, algorithms, transaction boundaries, error semantics and operations — the level below the architecture",
     size=14, color=RGBColor(0xF4,0xDF,0xE3), italic=True, first=True, space_after=0, line=1.25)
tf = txt(sl, ML + 0.3, 4.90, CW * 0.55, 1.0)
para(tf, "Ashutosh Sinha", size=20, color=INK, bold=True, font=SERIF, first=True, space_after=3)
para(tf, "Independent Researcher", size=12, color=CRIMSON, space_after=1)
para(tf, "September 2026   ·   written to be sufficient to start coding from", size=10.5, color=MUTED)
x0 = ML + CW * 0.55
tf = txt(sl, x0, 4.82, CW * 0.45, 2.25)
para(tf, "CHAPTERS", size=9.5, color=CRIMSON, bold=True, first=True, space_after=6)
for i, c in enumerate(["Overview and design rules", "Core domain and registry",
                       "Governance subsystems", "Data and features",
                       "Execution and warrants", "Machine assistance",
                       "Interfaces", "Cross-cutting and operations"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=10.5, space_after=3)

# ============================================================ SCOPE
_state["chapter"] = "Front matter"
sl, y = content("What this document is, and what it is not", "Front matter · scope")
data = [["Document", "Level", "Answers"],
        ["03 — Requirements", "What must be true", "~200 numbered requirements, personas, regulatory traceability"],
        ["04 — Architecture", "What the containers are, and why", "Deployable units, bounded contexts, extensibility, failure modes"],
        ["14 — Detailed design  ← this deck", "What each component does internally",
         "Interfaces, algorithms, transaction boundaries, concurrency, error taxonomy, SLOs, capacity"],
        ["05–09 — Annexes", "Specific surfaces in depth", "Data model, warrants, features, UI, security"],
        ["11 — Adversarial review", "What was wrong with all of it", "27 findings; 17 required redesign — folded in here"]]
th = table(sl, data, ML, y, CW, col_w=[3.3, 3.0, 5.3], row_h=0.46, fs=11, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + th + 0.30, CW, 0.95, fill=PARCH)
rect(sl, ML, y + th + 0.30, 0.045, 0.95, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + th + 0.44, CW - 0.6, 0.75)
runs(tf, [("Test of adequacy. ", CRIMSON, True),
          ("An engineer who has read the architecture should be able to open this document and begin implementing a component "
           "without inventing an interface, guessing a transaction boundary, or deciding an error code. Where that is not yet "
           "true, it is a gap in this document rather than a decision left to the reader.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)

# ============================================================ CH 1
divider("1", "Overview and Design Rules", "Components, responsibilities, and the seven rules that bind them.",
        ["Component inventory", "Responsibility boundaries", "Seven design rules", "Process model"])

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

# ============================================================ CH 2
divider("2", "Core Domain and Registry", "The algebra in code, and the registry that indexes it.",
        ["The model algebra", "Trainability is derived", "Contract algebra",
         "The fibre registry", "Version creation", "Alias moves"])

sl, y = content("The model algebra", "Core domain · maya/domain/model_algebra.py")
h = code(sl, ML, y, CW * 0.56, [
 "@dataclass(frozen=True)",
 "class ParameterObject:",
 "    kind: ParameterKind          # none | calibration_set | learned_weights |",
 "                                 # llm_configuration | rule_set | opaque | ...",
 "    artifact_digest: str | None",
 "",
 "    @property",
 "    def is_terminal(self) -> bool:      # P ≅ I  — the T0 case",
 "        return self.kind == \"none\"",
 "",
 "    @property",
 "    def is_accessible(self) -> bool:    # False for vendor black boxes",
 "        return self.kind != \"opaque\"",
 "",
 "@dataclass(frozen=True)",
 "class ParametricKernel:              # a model:  f : P ⊗ X → Y",
 "    parameters: ParameterObject",
 "    input:  ObjectSpec",
 "    output: ObjectSpec",
 "    deterministic: bool              # law L-3",
], fs=9.5, title="THE DEFINITION, AS A TYPE")
x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.6)
para(tf, "Why it is shaped this way", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=9)
bullets(tf, [("Parameters are an object, not a blob", "P is first-class, so “no parameters” and “inaccessible parameters” are expressible states rather than nulls"),
             ("Determinism is stored and tested", "f commutes with copy — which is exactly the reproducibility replay in §8.2"),
             ("No framework, no I/O", "Fully unit-testable; the laws run in milliseconds over generated inputs"),
             ("Frozen dataclasses", "Immutability at the type level mirrors immutability at the storage level")],
        size=11.5, gap=8, indent_size=10)

sl, y = content("Trainability is derived, never declared", "Core domain · the classification")
h = code(sl, ML, y, CW, [
 "def trainability_class(self, fit: FitProcedure, adaptive: bool) -> str:",
 "    if not self.parameters.is_accessible:   return \"T6\"    # vendor black box",
 "    if self.parameters.is_terminal:         return \"T0\"    # analytic — P ≅ I",
 "    return {\"calibrate\": \"T1\", \"estimate\": \"T2\",",
 "            \"train\": \"T4\" if adaptive else \"T3\",",
 "            \"configure\": \"T5\", \"elicit\": \"T7\", \"author\": \"T8\"}[fit]",
], fs=10.5, title="maya/domain/model_algebra.py")
tf = txt(sl, ML, y + h + 0.30, CW * 0.47, 2.4)
para(tf, "What this buys", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, ["The class is a function of the parameter object and the fitting procedure — never an enum a user picks",
             "Mislabelled records become impossible, so the estate cannot quietly drift",
             "T0 and T6 are the two extremal cases and both fall out, rather than being special-cased"], size=11.5, gap=7)
x = ML + CW * 0.53
rect(sl, x, y + h + 0.30, CW * 0.47, 1.55, fill=PARCH)
rect(sl, x, y + h + 0.30, 0.045, 1.55, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + h + 0.44, CW * 0.47 - 0.5, 1.3)
runs(tf, [("The consequence that matters. ", CRIMSON, True),
          ("Asking a closed-form pricer for its training set is a type error, and the system can say so precisely. "
           "Every mandatory-field workaround that fills an inventory with meaningless records disappears at this line.",
           INK, False)], size=11.5, first=True, space_after=0, line=1.28)

sl, y = content("Contract algebra", "Core domain · reasoning about black boxes")
h = code(sl, ML, y, CW * 0.55, [
 "def refines(self, other: Contract) -> RefinementResult:",
 "    \"\"\"C' ⪯ C  iff  A ⊆ A'  and  (A ∧ G') ⊆ G.\"\"\"",
 "    weaker_assumption  = other.assumptions.implies(self.assumptions)",
 "    stronger_guarantee = (other.assumptions & self.guarantees) \\",
 "                            .implies(other.guarantees)",
 "    return RefinementResult(",
 "        holds = weaker_assumption and stronger_guarantee,",
 "        failing_clauses = [...],   # DR-7: always name what failed",
 "    )",
], fs=9.5, title="DECIDABLE SUBSTITUTABILITY")
x = ML + CW * 0.59
tf = txt(sl, x, y, CW * 0.41, 1.8)
para(tf, "A deliberately restricted predicate language", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "Conjunctions of interval constraints, set membership, metric comparisons and freshness bounds — chosen so refinement stays decidable.",
     size=11, color=SLATE, space_after=7, line=1.25)
runs(tf, [("Richer assumptions are recorded as ", SLATE, False), ("narrative", INK, True, True),
          (" and explicitly excluded from automated refinement — so nobody believes a check happened that did not.", SLATE, False)],
     size=11, line=1.25)
tf = txt(sl, ML, y + h + 0.32, CW, 0.4)
para(tf, "Where the four operations are used", size=13, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Operation", "Question it answers", "Used at"],
        ["Refinement  ⪯", "May version B replace version A?", "Every alias move — a proof obligation, not a meeting"],
        ["Composition  ⊗", "What does this model chain promise end to end?", "Composite warrants"],
        ["Conjunction  ∧", "Satisfy performance and fairness and latency together", "Merging viewpoints on one model"],
        ["Quotient  /", "Given the target and what we have, what must the missing piece guarantee?", "Turns a validation gap into a specification"]]
table(sl, data, ML, y + h + 0.72, CW, col_w=[2.0, 4.6, 5.0], row_h=0.34, fs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("The fibre registry, and why it fails at startup", "Core domain · extensibility")
h = code(sl, ML, y, CW * 0.58, [
 "class FibreRegistry:",
 "    def __init__(self, plugins: PluginLoader):",
 "        for ep in plugins.entry_points(\"maya.model_class\"):",
 "            f = ep.load()()",
 "            self._validate_total(f)      # law L-15",
 "            self._fibres[f.key] = f",
 "",
 "    def _validate_total(self, f) -> None:",
 "        missing = [n for n in (\"evidence_schema\", \"lifecycle\",",
 "                   \"default_monitors\", \"document_templates\",",
 "                   \"tiering_hints\", \"contract_template\")",
 "                   if not getattr(f, n)()]",
 "        if missing:",
 "            raise FibreIncomplete(f.key, missing)  # refuse to boot",
], fs=9.5, title="STARTUP TOTALITY CHECK")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.4)
para(tf, "Nine extension points", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "model class · regime · semiring · artifact format · validation test · metric · document template · warrant flavour · connector",
     size=11, color=SLATE, space_after=12, line=1.3)
para(tf, "Why refuse to boot?", size=12.5, color=INK, bold=True, font=SERIF, space_after=7)
para(tf, "A half-registered fibre would otherwise surface as a confusing runtime error weeks later, in the one place the platform has to be trustworthy. Failing loudly at startup is the cheaper failure.",
     size=11, color=SLATE, space_after=0, line=1.3)

sl, y = content("Version creation — the full path", "Core domain · registry")
steps(sl, ML, y, CW, [
    ("1", "Validate", "Manifest checked against the fibre's JSON Schema"),
    ("2", "Quarantine", "Artifact streamed to a no-execute, content-addressed store"),
    ("3", "Sandbox", "Malware, pickle opcodes, SCA, secrets, licence; then graph parse"),
    ("4", "Policy", "Format policy for the target environment; reject with an exception path"),
    ("5", "Features", "Declared inputs reconciled against the feature registry"),
    ("6", "Commit", "Version created immutable; artifact promoted, signed, attested"),
    ("7", "Evidence", "Nodes appended: artifact, introspection, scans, contract, manifest"),
], h=1.62)
rect(sl, ML, y + 1.92, CW, 1.05, fill=PARCH)
rect(sl, ML, y + 1.92, 0.045, 1.05, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + 2.06, CW - 0.6, 0.85)
runs(tf, [("Transaction boundary. ", CRIMSON, True),
          ("Steps 6–7 are one Postgres transaction plus an outbox row for the object-store promotion. If promotion fails the "
           "outbox retries; the version exists but is marked artifact_pending and cannot be aliased. ", INK, False),
          ("Partial visibility is preferable to a lost write.", CRIMSON, True)],
     size=12, first=True, space_after=0, line=1.28)

sl, y = content("Alias moves — the most dangerous operation", "Core domain · registry")
h = code(sl, ML, y, CW, [
 "with uow.transaction():",
 "    lock = advisory_lock(f\"alias:{model_id}:{env}\")     # serialise per (model, env)",
 "    ref  = new.contract.refines(cur.contract)            # law L-7",
 "    var  = substitutable(new.schema, cur.schema)         # law L-12",
 "    if not (ref.holds and var.ok):",
 "        raise AliasMoveRefused(ref, var, consumers=warrants.consumers_of(...))",
 "    if not policy.evaluate(\"gates.alias_move\", ctx).allow: raise PolicyDenied(...)",
 "",
 "    warrant_projection.rebuild(model_id, env, name, new)    # PRE-WARM before invalidate",
 "    aliases.point(model_id, env, name, new)",
 "    alias_history.append(cur, new, ref, var, actor, justification)",
 "    outbox.put(CacheInvalidate(...), AliasMoved(...))",
 "monitoring.schedule_post_move_comparison(model_id, env, window=\"P7D\")",
], fs=9.5, title="maya/registry/aliases.py")
tf = txt(sl, ML, y + h + 0.30, CW, 1.1)
runs(tf, [("Three things are happening. ", CRIMSON, True),
          ("Substitutability is a ", INK, False), ("proof", INK, True),
          (" — consumers cannot be broken and are not redeployed. Pre-warming before invalidating is the fix for the cache "
           "stampede found in adversarial review, so a hot alias is never served from an empty cache. And the automatic "
           "seven-day post-move comparison is SS1/23's parallel outcomes analysis, performed as infrastructure rather than as a project.",
           INK, False)], size=12, first=True, space_after=0, line=1.30)

# ============================================================ CH 3
divider("3", "Governance Subsystems", "Evidence, risk, regimes, lifecycle, validation, documentation.",
        ["Evidence append and chain", "Semiring evaluation", "The tiering algorithm",
         "Anti-gaming", "Institutions in code", "Lifecycle and baseline import"])

sl, y = content("Evidence engine — append and chain", "Governance · evidence")
h = code(sl, ML, y, CW * 0.60, [
 "with uow.lock(\"evidence_chain\"):        # serialises seq only",
 "    prev = evidence.head()",
 "    node = EvidenceNode(",
 "        seq = prev.seq + 1,",
 "        payload = {} if personal_data else payload,     # law L-18",
 "        payload_uri = delta.put(payload) if personal_data else None,",
 "        content_hash = sha256(canonical_json(...)),",
 "        prev_hash    = prev.chain_hash,",
 "        chain_hash   = sha256(f\"{seq}|{prev_hash}|{content_hash}|\"",
 "                              f\"{sorted(parent.chain_hash)}\"),",
 "    )",
 "    evidence.insert(node)                # INSERT-only database role",
], fs=9.5, title="APPEND PATH")
x = ML + CW * 0.64
tf = txt(sl, x, y, CW * 0.36, 3.5)
para(tf, "Chain over DAG — why both", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("The DAG expresses derivation", "what supports what"),
             ("The linear chain expresses order", "so deletion of a leaf and insertion into the past become detectable"),
             ("Anchored daily", "chain head written to WORM and an RFC-3161 timestamp — self-consistency of a chain an attacker controls proves nothing"),
             ("Personal data is never inline", "only an erasable pointer, so crypto-shredding leaves the chain valid")],
        size=11, gap=7, indent_size=9.5)

sl, y = content("One engine, nine questions", "Governance · semiring evaluation")
h = code(sl, ML, y, CW * 0.55, [
 "def evaluate(claim, K: Semiring[T], valuation) -> T:",
 "    def go(node):",
 "        d = derivations[node]",
 "        if d.is_leaf: return valuation(node)",
 "        r = K.zero",
 "        for alt in d.alternatives:            # OR",
 "            t = K.one",
 "            for dep in alt.requires:          # AND",
 "                t = K.times(t, go(dep))",
 "            r = K.plus(r, t)",
 "        return r",
 "    return go(claim.root)                     # memoised",
], fs=9.5, title="maya/evidence/query.py")
x = ML + CW * 0.59
data = [["Semiring", "Used by"],
        ["Boolean", "Lifecycle gates, warrant resolution"],
        ["Why(X)", "Examiner packs — what must be shown"],
        ["ℕ[X]", "Tier 1 audit reconstruction"],
        ["Trust", "Health score, AI-draft discounting"],
        ["Tropical", "Remediation planning, capacity"],
        ["Classification", "PII propagation"],
        ["Admissibility", "Which regulators accept it"],
        ["Freshness", "Document staleness"]]
table(sl, data, x, y, CW * 0.41, col_w=[1.6, 3.2], row_h=0.30, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + h + 0.28, CW, 0.95, fill=PARCH)
rect(sl, ML, y + h + 0.28, 0.045, 0.95, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + h + 0.42, CW - 0.6, 0.75)
runs(tf, [("Complexity, stated honestly. ", CRIMSON, True),
          ("Why-provenance is worst-case exponential in the number of alternatives. Controls: canonical form with absorption, "
           "memoisation, depth cap, and a hard 4,096-term cap beyond which evaluation degrades to Boolean ⊕ Trust and emits "
           "truncated=true. ", INK, False), ("A silently partial answer is never returned.", CRIMSON, True)],
     size=11.5, first=True, space_after=0, line=1.26)

sl, y = content("The tiering algorithm", "Governance · risk")
h = code(sl, ML, y, CW * 0.58, [
 "facts = FactCollector(model_id).collect()      # sourced where possible",
 "rules = rulesets.get(ruleset_version)          # immutable, versioned, tested",
 "",
 "m = Materiality(quantitative = rules.exposure_band(...),",
 "                qualitative  = rules.purpose_class(...)).join()",
 "",
 "c = Complexity.meet(data=..., methodology=..., implementation=...,",
 "                    use_intensity=..., interpretability=...,",
 "                    transparency=..., bias_potential=...)",
 "",
 "tier     = rules.tau(m, c)      # monotone — law L-4",
 "controls = rules.req(tier)      # Galois adjoint — law L-5",
 "",
 "return RiskAssessment(fact_snapshot=..., ruleset_version=...,",
 "                      rationale=rules.explain(m, c, tier),   # DR-4",
 "                      next_review_due=..., triggers=...)",
], fs=9.5, title="maya/risk/tiering.py")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.6)
para(tf, "Two axes, never one score", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Materiality and complexity are separate lattices. Collapsing them into a product lets a very complex model with modest exposure land beside a simple model with enormous exposure.",
     size=11, color=SLATE, space_after=10, line=1.26)
para(tf, "The guarantee", size=12.5, color=INK, bold=True, font=SERIF, space_after=7)
runs(tf, [("τ is monotone, so ", SLATE, False),
          ("nothing we can learn about a model that makes it more consequential or more complicated will ever move it into a lighter control regime.",
           INK, True), (" An unconstrained scoring formula cannot make that promise, and typically cannot even be checked.", SLATE, False)],
     size=11, line=1.26)

sl, y = content("Anti-gaming: where the facts come from", "Governance · risk")
data = [["Fact", "Source", "If unavailable"],
        ["exposure_measure", "Bound to a system of record — risk data mart, GL, portfolio system — with nightly reconciliation",
         "Marked unsourced; peer-cohort outlier detection applies; flagged on the model page"],
        ["purpose_class", "Human — but a change requires approval at the tier being LEFT, not the tier being entered", "—"],
        ["complexity components", "Derived from artifact introspection, feature contract and lineage where possible", "Human, with recorded rationale"]]
th = table(sl, data, ML, y, CW, col_w=[2.4, 5.4, 3.8], row_h=0.55, fs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + th + 0.30, CW * 0.48, 1.9)
para(tf, "The attack the obvious control misses", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "Tier is derived, traced and monotone — so overriding it is visible. But it is derived from facts, and understating an exposure lowers the tier through a perfectly valid, fully audited derivation.",
     size=11.5, color=SLATE, space_after=0, line=1.26)
x = ML + CW * 0.54
rect(sl, x, y + th + 0.30, CW * 0.46, 1.75, fill=PARCH)
rect(sl, x, y + th + 0.30, 0.045, 1.75, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + th + 0.44, CW * 0.46 - 0.5, 1.5)
para(tf, "Retrospective calibration", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=7)
runs(tf, [("Annually, tier assignments are back-tested against realised incidents, findings and losses. ", INK, False),
          ("A tier that never predicts anything is evidence of systematic understatement — not of a quiet portfolio.", INK, True)],
     size=11.5, space_after=0, line=1.26)

sl, y = content("Institutions in code", "Governance · regimes")
h = code(sl, ML, y, CW, [
 "def determine(model_id: str, inst: Institution) -> ScopeDetermination:",
 "    core   = CoreFacts.for_model(model_id)",
 "    local  = inst.translate(core)                    # the comorphism component",
 "    result = inst.sentences[\"is_model\"].evaluate(local)",
 "    return ScopeDetermination(",
 "        regime_key=inst.key, regime_version=inst.version,",
 "        determination = \"in_scope\" if result.value else \"out_of_scope\",",
 "        derivation = {\"sentence\": \"is_model\", \"evaluated\": result.value,",
 "                      \"failing_conjunct\": result.first_false_conjunct,",
 "                      \"facts\": local.as_dict(), \"citation\": result.citation},",
 "        obligations = [s.key for s in inst.sentences if s.is_obligation and s.evaluate(local).value])",
], fs=9.5, title="maya/regimes/engine.py")
tf = txt(sl, ML, y + h + 0.28, CW * 0.52, 1.9)
para(tf, "A determination is a derivation, not a flag", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "“Why is this out of scope?” is answered by the failing conjunct and a clause citation — the same answer, every time it is asked, including in five years by someone who was not there.",
     size=11.5, color=SLATE, space_after=0, line=1.26)
x = ML + CW * 0.56
rect(sl, x, y + h + 0.28, CW * 0.44, 1.75, fill=PARCH)
rect(sl, x, y + h + 0.28, 0.045, 1.75, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + h + 0.42, CW * 0.44 - 0.5, 1.5)
para(tf, "Law L-8 runs in CI", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=7)
runs(tf, [("Hypothesis generates inventory states. For each regime and sentence, evaluating natively and evaluating the translation must agree. ",
           INK, False), ("A disagreement is a defective encoding — exactly the bug that produces an indefensible scope determination.", INK, True)],
     size=11, space_after=0, line=1.26)

sl, y = content("Lifecycle, segregation of duties, and day one", "Governance · workflow")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Transitions are guarded, and guards explain", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.40, CW * 0.47, [
 "unmet = [g for g in t.guards",
 "         if not policy.evaluate(g, ctx).allow]",
 "sod   = sod_engine.violations(actor, t, m)",
 "if unmet or sod:",
 "    raise TransitionBlocked(unmet, sod)",
 "    # each entry carries a remediation link — DR-7",
], fs=9.5)
tf = txt(sl, ML, y + 0.40 + h + 0.26, CW * 0.47, 1.6)
para(tf, "Six SoD rules, checked twice", size=12, color=INK, bold=True, font=SERIF, first=True, space_after=6)
para(tf, "developer ≠ validator · owner not sole approver · no self-closure of findings · policy author ≠ publisher · overlay proposer ≠ approver · platform admin has no governance rights",
     size=10.5, color=SLATE, space_after=6, line=1.24)
para(tf, "Checked at the API and re-checked nightly — a role change creates a retrospective conflict the point-in-time check never sees.",
     size=10.5, color=SLATE, space_after=0, line=1.24)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Baseline import — the day-one problem", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
steps(sl, x, y + 0.42, CW * 0.47, [
    ("1", "Imported", "Bulk / connector"),
    ("2", "Baselined", "Tiered, owner confirmed, debt recorded"),
    ("3", "Gate bites", "On the next MATERIAL change"),
], h=1.30)
rect(sl, x, y + 2.00, CW * 0.47, 1.55, fill=PARCH)
rect(sl, x, y + 2.00, 0.045, 1.55, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 2.14, CW * 0.47 - 0.5, 1.3)
runs(tf, [("Why this exists. ", CRIMSON, True),
          ("On import, 1,200 legacy models arrive with no evidence. Without a baseline path every gate fails, every dashboard is "
           "red, and the programme dies by month seven. Debt is a tracked burn-down with a board-approved expiry — ", INK, False),
          ("never rendered in the same colour as a breach.", INK, True)], size=11, first=True, space_after=0, line=1.24)

sl, y = content("Documentation — two kinds, held apart", "Governance \u00b7 documentation")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "Compiled \u2014 what the register knows", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.42, CW * 0.47, [
 "gen = [lens.render(ctx) for lens in template]",
 "doc.stale = ev.digest != prev.evidence_digest",
 "# a lens that cannot fill its section says so,",
 "# so a gap in the evidence is visible, not blank",
], fs=9.5)
tf = txt(sl, ML, y + 0.42 + h + 0.26, CW * 0.47, 1.6)
para(tf, "Four kinds, fifteen lenses. Every section records the evidence it rested on, so "
         "citation soundness is a Boolean evaluation rather than a claim. Staleness is computed "
         "from the chain head at compile time, never remembered.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "Attached \u2014 what a person wrote", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
h2 = code(sl, x, y + 0.42, CW * 0.47, [
 "digest, size = store.put(bytes)   # sha256 IS the key",
 "version_id = current_version(urn) # not the model",
 "...",
 "refuse_if(actor == row.attached_by, \"self_review\")",
 "refuse_if(not accept and not note, \"reason_required\")",
], fs=9.5)
tf = txt(sl, x, y + 0.42 + h2 + 0.26, CW * 0.47, 1.6)
para(tf, "Filed against the version it describes, because an MDD describes the coefficients it "
         "printed \u2014 not their replacement. Re-hashed on read: what was accepted is what is served.",
     size=10.5, color=SLATE, first=True, space_after=0, line=1.24)

rect(sl, ML, y + 3.62, CW, 0.98, fill=PARCH)
rect(sl, ML, y + 3.62, 0.045, 0.98, fill=CRIMSON)
tf = txt(sl, ML + 0.26, y + 3.76, CW - 0.5, 0.8)
runs(tf, [("Why both. ", CRIMSON, True),
          ("A platform that only compiles cannot hold the paper the quant actually wrote; one that only "
           "stores files is a share drive with a database in front. Held apart, the register can say which "
           "is which \u2014 and ", INK, False),
          ("a rejected document stays on file with its reason", INK, True),
          (", because the papers that did not pass are the ones a supervisor asks about.", INK, False)],
     size=11, first=True, space_after=0, line=1.24)

# ============================================================ CH 4
divider("4", "Data and Features", "Point-in-time correctness, version-namespaced serving, monitoring at scale.",
        ["The PIT assembly", "Three-layer verification", "Online store namespacing", "Monitoring pipeline"])

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
], fs=9.5, title="maya/features/assembly.py")
x = ML + CW * 0.60
h2 = code(sl, x, y, CW * 0.40, [
 "LEFT JOIN LATERAL (",
 "  SELECT <features>",
 "  FROM   <view> VERSION AS OF :dv   -- txn time",
 "  WHERE  entity_id  = s.entity_id",
 "    AND  event_ts  <= s.label_ts    -- valid time",
 "    AND  ingest_ts <= :as_of        -- txn time",
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

# ============================================================ CH 5
divider("5", "Execution and Warrants", "How a governed model actually gets run — and stopped.",
        ["The warrant grammar", "Resolution algorithm", "Caching and stampede control",
         "Revocation", "Use reconciliation"])

sl, y = content("The warrant grammar — a product, not a union", "Execution · the contract")
tf = txt(sl, ML, y, CW, 0.62)
para(tf, "Every model a bank runs differs along exactly four independent axes. The grammar is their PRODUCT, "
         "so a new model technology is a new value in one vocabulary — not a new document type.",
     size=12.5, color=SLATE, first=True, space_after=0, line=1.3)
yy = y + 0.72
AXES = [("1  Parameter object", "how P is inhabited",
         "none · calibration_set · estimated_coefficients · learned_weights · llm_configuration · rule_set · elicited_weights · opaque"),
        ("2  Realisation", "how the kernel becomes runnable",
         "quantlib · onnx · pmml · python.callable · container · sql · spreadsheet · rules · solver · llm.prompt · llm.agent · descriptor_only"),
        ("3  Operation", "what is asked of it",
         "score · fit · validate · backtest · explain · simulate · stress · optimise · generate · monitor"),
        ("4  Data binding", "where its data comes from",
         "request · feature_namespace · dataset_snapshot · market_data · document_corpus · stream · scenario_set · sql_query")]
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
           "\u2014 not a new section, not a new document type, and not a change to anything that already works.",
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
           ["Credit-memo agent", "llm_configuration  (T5)", "llm.agent", "generate", "document_corpus"],
           ["Treasury spreadsheet", "rule_set  (T8)", "spreadsheet", "score", "request"],
           ["VaR backtest", "calibration_set  (T1)", "python.callable", "backtest", "dataset_snapshot"]]
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
tf = txt(sl, ML, y, CW, 0.56)
para(tf, "The load-bearing laws are not invented for the grammar. They fall out of the algebra: the trainability "
         "class is DERIVED from how the parameter object is inhabited, so what a class admits is what the class means.",
     size=12.5, color=SLATE, first=True, space_after=0, line=1.3)
data = [["Law", "Refuses", "Because"],
        ["L-W1", "fit on T0 or T6", "T0's parameters come from theory; T6's are inside a vendor black box"],
        ["L-W2", "generate on a non-generative runtime", "an ONNX graph does not produce prose"],
        ["L-W3", "training from a non-bitemporal source", "it cannot be shown point-in-time correct, so not shown leak-free"],
        ["L-W4", "a fit with no parameter_object sink", "a fit produces a NEW parameter object, it does not edit the old one"],
        ["L-W5", "claimed determinism with no seed", "an LLM at temperature 0.7 is not reproducible, and would be believed"],
        ["L-W6", "fit on a descriptor-only model", "you cannot inhabit what nothing on this side can reach"],
        ["L-W7", "a backtest with no outcomes", "that is a re-score wearing a backtest's name"]]
th = table(sl, data, ML, y + 0.66, CW, col_w=[1.1, 3.6, 6.9], row_h=0.44, fs=10.5,
           bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + 0.66 + th + 0.24, CW, 0.72, fill=PARCH)
rect(sl, ML, y + 0.66 + th + 0.24, 0.045, 0.72, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + 0.66 + th + 0.36, CW - 0.6, 0.56)
runs(tf, [("Validated before signed, never after. ", CRIMSON, True),
          ("A signature over a non-conforming document would assure that it is authentic and not that it is "
           "usable — and an engine would reasonably read it as both.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

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
], fs=9, title="maya/warrants/resolver.py")
x = ML + CW * 0.64
tf = txt(sl, x, y, CW * 0.36, 3.7)
para(tf, "How p99 < 50 ms is met", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=8)
bullets(tf, [("Never touch the primary", "warrant_projection is served from a read replica — and it is the ONLY table this service knows"),
             ("Common case is a Redis GET", "plus one Ed25519 verification"),
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
table(sl, data, ML, y + 0.40, CW * 0.47, col_w=[2.2, 3.3], row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + 2.25, CW * 0.47, 1.4)
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
table(sl, data, x, y + 0.40, CW * 0.47, col_w=[4.0, 1.5], row_h=0.36, fs=10.5, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
rect(sl, x, y + 2.20, CW * 0.47, 1.50, fill=PARCH)
rect(sl, x, y + 2.20, 0.045, 1.50, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 2.34, CW * 0.47 - 0.5, 1.25)
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

# ============================================================ CH 6
divider("6", "Machine Assistance", "Where AI does the work, where it may not, and why that is structural.",
        ["The capability contract", "The grounding gate", "Structural prohibition"])

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
], fs=9.5, title="maya/ai/runner.py")
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
], fs=9.5, title="maya/ai/grounding.py")
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

# ============================================================ CH 7
divider("7", "Interfaces", "One API, consumed identically by the UI, the SDK and every engine.",
        ["API conventions", "Resource surface", "Front-end design", "SDK and events"])

sl, y = content("API conventions", "Interfaces · the contract")
data = [["Concern", "Decision", "Why"],
        ["Base", "/api/v1, OpenAPI 3.1, JSON", "One versioned contract; the UI has no privileged path"],
        ["Errors", "RFC 9457 problem+json with code, deny_reason[], remediation_url", "DR-6 and DR-7 — blocking must always explain"],
        ["Pagination", "Keyset with cursor / next_cursor", "Stable paging over 50,000 models"],
        ["Concurrency", "ETag + If-Match; 412 returns a field-level diff", "The UI shows a real conflict dialog instead of overwriting"],
        ["Idempotency", "Idempotency-Key on POST, 24-hour replay window", "Safe retry on flaky networks — DR-3"],
        ["Shaping", "?expand= and ?fields=", "One request per screen instead of N+1 chatter"],
        ["Derivations", "GET /derivations/{id} on every derived value", "Powers the universal [why?] affordance"],
        ["Time travel", "?as_of= on inventory reads", "Examiner questions about a past date"],
        ["Events", "GET /events (SSE)", "Task inbox, breaches, job progress without polling"],
        ["Deprecation", "Two minor versions of overlap; Sunset headers", "Clients are never surprised"]]
table(sl, data, ML, y, CW, col_w=[1.9, 4.6, 5.1], row_h=0.325, fs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Resource surface", "Interfaces · endpoints")
data = [["Group", "Endpoints"],
        ["Models", "/models · /models/{urn} · /uses · /assumptions · /limitations · /relationships · /blast-radius · /scope-determinations"],
        ["Versions", "/models/{urn}/versions · /versions/{id} · /compare · /contract · /reproducibility"],
        ["Aliases", "/models/{urn}/environments/{env}/aliases/{name} · /history"],
        ["Risk", "/models/{urn}/assessments · /assessments/{id} · /tiering/rulesets · /tiering/simulate"],
        ["Features", "/features · /feature-views · /feature-views/{id}/versions · /contracts · /training-sets"],
        ["Runs", "/runs · /runs/{id}/metrics · /artifacts · /runs/{id}/replay"],
        ["Validation", "/validations · /validations/{id}/tests · /findings · /findings/{id}/remediation"],
        ["Overlays", "/overlays · /overlays/{id}/measurements"],
        ["Monitoring", "/monitors · /observations · /breaches · /health/{urn}"],
        ["Warrants", "/warrants · /v1/resolve (warrant service) · /warrants/{id}/revoke · /telemetry"],
        ["Documents", "/documents/compile · /documents/{id} · /documents/{id}/render · /export-packs"],
        ["Policy", "/policies · /policies/evaluate · /obligations"],
        ["Assistance", "/ai/capabilities · /ai/{capability}/draft · /ai/generations/{id}/attest"],
        ["Admin", "/model-classes · /lifecycles · /templates · /regimes · /connectors · /users"]]
table(sl, data, ML, y, CW, col_w=[1.8, 9.8], row_h=0.275, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Front end and SDK", "Interfaces · clients")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "maya-web — a separate process", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Concern", "Design"],
        ["Auth", "OIDC + PKCE; access token in memory only; refresh via __Host- SameSite=Strict cookie"],
        ["Logic", "P4′ — the client renders decisions, never derives them"],
        ["Client", "Generated from OpenAPI; pinned by openapi.lock.json; drift fails the build"],
        ["Forms", "Generated in-browser from the fibre's JSON Schema — a new model class needs no front-end release"],
        ["Documents", "Fetched as server-rendered HTML/PDF, never assembled client-side"]]
table(sl, data, ML, y + 0.40, CW * 0.47, col_w=[1.3, 4.4], row_h=0.44, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "SDK — the compliant path must be the shortest", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
tf = txt(sl, x, y + 0.42, CW * 0.47, 2.0)
bullets(tf, ["Resolve and verify the descriptor signature",
             "Fetch features per the contract; check freshness",
             "Check operating boundaries before scoring",
             "Emit signed telemetry",
             "Maintain the local revocation list"], size=11.5, gap=7)
rect(sl, x, y + 2.35, CW * 0.47, 1.35, fill=PARCH)
rect(sl, x, y + 2.35, 0.045, 1.35, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 2.49, CW * 0.47 - 0.5, 1.1)
runs(tf, [("The design point. ", CRIMSON, True),
          ("A developer who uses the SDK gets governance for free and cannot forget a step. If the compliant path is slower than "
           "the non-compliant one, the inventory rots — so the SDK ships in Phase 1, not later.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)

# ============================================================ CH 8
divider("8", "Cross-cutting and Operations", "Transactions, concurrency, errors, SLOs, capacity, testing.",
        ["Transactions and the outbox", "Concurrency and idempotency", "Error taxonomy",
         "SLOs and signals", "Capacity", "Testing"])

sl, y = content("Transactions and the outbox", "Cross-cutting · consistency")
h = code(sl, ML, y, CW * 0.52, [
 "with uow.transaction() as tx:      # ONE Postgres transaction",
 "    ...domain mutations...",
 "    tx.evidence.append(...)        # same transaction — DR-4",
 "    tx.audit.write(...)            # same transaction",
 "    tx.outbox.put(event)           # the only way out",
 "",
 "# commit → relay → Kafka / Delta / cache invalidation",
], fs=10, title="maya/platform/db.py")
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
        ["Laws L-1…L-18", "The formal properties hold under generated inputs"],
        ["Integration", "Repository and service paths against real infrastructure"],
        ["Contract", "API matches the spec; SDK round-trips"],
        ["Adversarial", "Leakage injection · RLS negative tests · stampede load · malicious artifacts"],
        ["Migration", "Up and down against production-shaped data"],
        ["Performance", "The SLOs, or the build fails"]]
table(sl, data, x, y + 0.40, CW * 0.47, col_w=[1.8, 4.0], row_h=0.36, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 3.10, CW * 0.47, 0.9)
runs(tf, [("Why adversarial tests are not optional. ", CRIMSON, True),
          ("A PIT verifier that silently stops detecting leakage, or an RLS policy that silently stops isolating, is a catastrophic "
           "invisible regression. Both are tested by injecting the failure they must catch.", INK, False)],
     size=10.5, first=True, space_after=0, line=1.24)

# ============================================================ CLOSING
_state["chapter"] = "Closing"
sl, y = content("What this design commits to", "Closing")
outs = [("Immutability is enforced, not asserted",
         "Triggers that raise, append-only database roles, a chain anchored outside the system. Silence is never an acceptable enforcement mechanism."),
        ("Every derived value carries its derivation",
         "Tier, status, scope, health — each written with its inputs, rule version and rationale, in the same transaction."),
        ("Extension without migration",
         "Model classes are fibres, regulators are institutions. Nine plugin points. A new kind of model needs no DDL and no front-end release."),
        ("Governance is not a single point of failure",
         "If the control plane is down, authorised scoring continues. Only new issuance and changes stop."),
        ("The compliant path is the fast path",
         "SDK-first, schema-generated forms, compiled documentation. If governance is slower than the workaround, the inventory rots."),
        ("The theory is tested",
         "Eighteen laws as property tests. A failing law fails the build — which is what stops a foundation decaying into decoration.")]
cw2 = (CW - 0.30 * 2) / 3
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 3) * (cw2 + 0.30), y + (i // 3) * 2.30, cw2, 2.10, f"0{i+1}", t, d)

_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
if os.path.exists(LOGO):
    sl.shapes.add_picture(LOGO, In(ML + 0.38), In(1.62), In(0.92), In(0.92))
tf = txt(sl, ML + 0.4, 2.70, CW * 0.82, 1.6)
para(tf, "Detailed System Design", size=38, color=WHITE, font=SERIF, first=True, space_after=6)
para(tf, "Evidence, not assertion.", size=17, color=RGBColor(0xF2,0xD8,0xDC), italic=True, font=SERIF, space_after=8)
rect(sl, ML + 0.4, 4.02, 1.6, 0.035, fill=RGBColor(0xE8,0xB8,0xC0))
tf = txt(sl, ML + 0.4, 4.30, CW * 0.74, 1.5)
para(tf, "Ashutosh Sinha", size=18, color=WHITE, bold=True, first=True, space_after=4)
para(tf, "Independent Researcher   ·   ajsinha@gmail.com", size=12, color=RGBColor(0xF2,0xD8,0xDC), space_after=14)
para(tf, "Full document: docs/14-detailed-design.md   ·   Architecture: docs/04-architecture.md   ·   Adversarial review: docs/11-adversarial-review.md",
     size=10.5, color=RGBColor(0xE8,0xC4,0xCA), line=1.3)
para(tf, "© 2026 Ashutosh Sinha. All rights reserved. Proprietary and confidential — see LICENSE and NOTICE. "
         "Not legal, regulatory or financial advice.",
     size=8.5, color=RGBColor(0xD8,0xA0,0xAC), space_before=10, line=1.25)

import sys
prs.save(sys.argv[1] if len(sys.argv) > 1 else "MAYA-System-Design.pptx")
print("slides:", len(prs.slides._sldIdLst))
