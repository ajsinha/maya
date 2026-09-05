# ============================================================ CH 2
divider("2", "Core Domain and Registry", "The algebra in code, and the registry that indexes it.",
        ["The model algebra", "Trainability is derived", "Contract algebra",
         "The fibre registry", "Version creation", "Alias moves"])

sl, y = content("The model algebra", "Core domain · core/domain/algebra.py")
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
], fs=10.5, title="core/domain/algebra.py")
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
     size=11, color=SLATE, space_after=12, line=1.3)
runs(tf, [("Not built. ", CRIMSON, True),
          ("A model class is a string on the register today; there is no plugin loader and no "
           "totality check, so L-15 is stated and not enforced. The extensibility that ", INK, False),
          ("is", INK, True),
          (" built is the warrant grammar's: a new model technology is a new value in one "
           "vocabulary, not a new document type.", INK, False)],
     size=10.5, space_after=0, line=1.26)

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
], fs=9.5, title="core/registry/aliases.py")
tf = txt(sl, ML, y + h + 0.30, CW, 1.1)
runs(tf, [("Three things are happening. ", CRIMSON, True),
          ("Substitutability is a ", INK, False), ("proof", INK, True),
          (" — consumers cannot be broken and are not redeployed. Pre-warming before invalidating is the fix for the cache "
           "stampede found in adversarial review, so a hot alias is never served from an empty cache. And the automatic "
           "seven-day post-move comparison is SS1/23's parallel outcomes analysis, performed as infrastructure rather than as a project.",
           INK, False)], size=12, first=True, space_after=0, line=1.30)
