# ============================================================ CH 17
_state["chapter"] = "17 · Core domain and registry"

sl, y = content("The model algebra, and the class it derives",
                "Core domain · core/domain/algebra.py")
h = code(sl, ML, y, CW * 0.53, [
 "@dataclass(frozen=True)",
 "class ParameterObject:",
 "    kind: ParameterKind      # none | calibration_set |",
 "                             #   learned_weights | rule_set | opaque | ...",
 "    artifact_digest: str | None",
 "",
 "    @property",
 "    def is_terminal(self) -> bool:    # P ≅ I  — the T0 case",
 "        return self.kind == \"none\"",
 "",
 "@dataclass(frozen=True)",
 "class ParametricKernel:          # a model:  f : P ⊗ X → Y",
 "    parameters: ParameterObject",
 "    input: ObjectSpec ; output: ObjectSpec",
 "    deterministic: bool          # law L-3; typed once, compiled per dialect",
], fs=9.5, title="THE DEFINITION, AS A TYPE")
x = ML + CW * 0.56
h2 = code(sl, x, y, CW * 0.44, [
 "def trainability_class(self, fit, adaptive) -> str:",
 "    if not self.parameters.is_accessible:",
 "        return \"T6\"                  # vendor black box",
 "    if self.parameters.is_terminal:",
 "        return \"T0\"                  # analytic — P ≅ I",
 "    return {\"calibrate\": \"T1\", \"estimate\": \"T2\",",
 "            \"train\": \"T4\" if adaptive else \"T3\",",
 "            \"configure\": \"T5\", \"elicit\": \"T7\",",
 "            \"author\": \"T8\"}[fit]",
], fs=9.5, title="THE CLASS IS A FUNCTION, NOT A FIELD")
tf = txt(sl, x, y + h2 + 0.26, CW * 0.44, 1.9)
bullets(tf, [("Parameters are an object, not a blob", "“no parameters” and “inaccessible parameters” are states, not nulls"),
             ("The class is derived", "never an enum a user picks, so a mislabelled record is unreachable"),
             ("No framework, no I/O", "the laws run in milliseconds over generated inputs")],
        size=10.5, gap=6, indent_size=9.5)
note(sl, ML, y + h + 0.30, CW * 0.53, 1.25,
     "The consequence that matters. ",
     "Asking a closed-form pricer for its training set is a type error, and the system can say so precisely. Every "
     "mandatory-field workaround that fills an inventory with meaningless records disappears at this line.")

sl, y = content("Contract algebra — what the code really does",
                "Core domain · core/domain/contracts.py")
h = code(sl, ML, y, CW * 0.55, [
 "def refines(self, other: Contract) -> RefinementResult:",
 "    \"\"\"C' ⪯ C iff A ⊆ A' and (A ∧ G') ⊆ G. Law L-7.\"\"\"",
 "    weak   = [k for k, b in other._a().items()",
 "              if k in self._a() and not self._a()[k].weaker_than(b)]",
 "    strong = [k for k, b in other._g().items()",
 "              if k not in self._g() or not self._g()[k].stronger_than(b)]",
 "    return RefinementResult(holds = not weak and not strong,",
 "                            assumption_failures=tuple(weak),",
 "                            guarantee_failures=tuple(strong))",
], fs=9.5, title="WHAT THE CODE ACTUALLY DOES")
x = ML + CW * 0.59
tf = txt(sl, x, y, CW * 0.41, 2.2)
para(tf, "A clause is an interval or a set, not a predicate", size=12, color=INK, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "A Bound is a key with a minimum, a maximum or an allowed set. Refinement compares bounds key by key — it does not "
         "form A ∧ G' and does not evaluate a predicate language. There is no implication solver here, and the refusal names "
         "the failing keys rather than a clause.",
     size=10.5, color=SLATE, space_after=7, line=1.24)
runs(tf, [("Richer assumptions are recorded as ", SLATE, False), ("narrative", INK, True, True),
          (" and excluded from the check — so nobody believes a proof happened that did not.", SLATE, False)],
     size=10.5, line=1.24)
data = [["Operation", "What it is meant to answer", "What the code does today"],
        ["Refinement  ⪯", "May version B replace version A?", "Built, and enforced at every alias move"],
        ["Composition  ⊗", "What does this chain promise end to end?", "Unions assumptions and guarantees — it does not discharge the downstream's assumptions against the upstream's guarantees"],
        ["Conjunction  ∧", "Performance and fairness and latency together", "The same function as composition, under a second name. Right here, wrong there"],
        ["Quotient  /", "What must the missing piece guarantee?", "Drops the guarantee keys already held — a keyed difference, not a residual"]]
table(sl, data, ML, y + h + 0.34, CW, col_w=[1.9, 3.7, 6.0], row_h=0.44, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Every class is complete, or the platform does not start",
                "Core domain · the fibration")
h = code(sl, ML, y, CW * 0.58, [
 "FACETS = (\"evidence\", \"lifecycle\", \"metrics\", \"templates\")",
 "BASE   = (\"T0\", \"T1\", …, \"T8\")        # the nine classes",
 "",
 "def register(self, fibre):              # the extension point",
 "    if missing := fibre.missing_facets():",
 "        raise FibreError(\"partial_fibre\", …)",
 "",
 "def verify(self):                       # law L-15, at start-up",
 "    if gaps := self.totality():         # no fibre, or a partial one",
 "        raise FibreError(\"fibration_incomplete\", …)",
], fs=9.5, title="core/fibres/registry.py")
x = ML + CW * 0.62
tf = txt(sl, x, y, CW * 0.38, 3.4)
para(tf, "A fibre is what a class needs", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=7)
para(tf, "Four facets: what evidence it must carry, which lifecycle it follows, what can be monitored on it, what compiles for it. A new kind of model supplies a fibre and nothing else changes — no migration, no new table, no new screen.",
     size=11, color=SLATE, space_after=11, line=1.3)
para(tf, "The base is the trainability class", size=12.5, color=INK, bold=True, font=SERIF, space_after=7)
para(tf, "Not the model class, which is free text: a totality gate over free text is defeated by typing a word nobody registered. T0–T8 is derived from how P is inhabited, so the index cannot be typed wrong.",
     size=11, color=SLATE, space_after=11, line=1.3)
runs(tf, [("The fibre is not inert. ", CRIMSON, True),
          ("A performance monitor on a T0 pricer, or a calibration monitor on a T5 assembly, is refused ", INK, False),
          ("kind_not_answerable", INK, False, False, MONO),
          (" — the class decides what may be asked of it.", INK, False)],
     size=10.5, space_after=0, line=1.26)

sl, y = content("Version creation — what runs, and what is still design",
                "Core domain · registry")
steps(sl, ML, y, CW * 0.62, [
    ("1", "Validate", "Kernel spec parsed, class derived, unexplained parameters refused"),
    ("2", "Resolve", "Digest looked up in the content-addressed store; the store is the authority on its own contents"),
    ("3", "Commit", "Version inserted immutable, status draft, manifest digest computed"),
    ("4", "Evidence", "version_created appended to the chain"),
], h=1.70)
x = ML + CW * 0.65
listbox(sl, x, y, CW * 0.35, "Designed, not built",
        [("Quarantine to a no-execute store", SLATE, ""),
         ("Malware, pickle-opcode, SCA, secret and licence scans", SLATE, ""),
         ("Format policy per target environment", SLATE, ""),
         ("Declared inputs reconciled against the feature registry", SLATE, ""),
         ("Artifact promotion, signing and attestation", SLATE, "")],
        sub="core/artifacts/store.py hashes and stores; it does not scan",
        row=0.30)
note(sl, ML, y + 2.10, CW * 0.62, 1.55,
     "There is no outbox. ",
     "A two-phase commit with an outbox row for the object-store promotion, and an artifact_pending state that cannot "
     "be aliased, is the design. What runs is one insert followed by one evidence append — and the append opens its own "
     "transaction, so the two are not atomic. The transaction-boundary argument is a plan, not a property.")

sl, y = content("Alias moves — the most dangerous operation",
                "Core domain · core/registry/aliases.py")
h = code(sl, ML, y, CW, [
 "m   = catalogue.require(urn)",
 "new = versions.require(urn, to_semver)",
 "if new[\"status\"] != \"approved\": raise RegistryError(...)   # only approved versions",
 "self._check_not_blocked(m)                        # an open blocking finding stops it first",
 "",
 "proof = obligations(new, incumbent)               # L-7 refinement AND L-12 variance",
 "if not (proof[\"refinement\"][\"holds\"] and proof[\"variance\"][\"ok\"]):",
 "    raise RegistryError(f\"alias move refused: {reason}\")     # the refusal names the clause",
 "policy.check(\"alias:move\", {...})                 # policy may refuse; it may never permit",
 "",
 "aliases.point(...); history.add({..., **proof}); evidence.append(\"alias_moved\", ...)",
], fs=9.5, title="THE GOVERNED SWITCH")
tf = txt(sl, ML, y + h + 0.28, CW * 0.55, 1.6)
runs(tf, [("Substitutability is a proof, not a meeting. ", CRIMSON, True),
          ("Consumers bind to the alias, so they cannot be broken and are not redeployed. The proof is stored on the "
           "history row, which is what makes “why was this allowed” answerable a year later.", INK, False)],
     size=11, first=True, space_after=0, line=1.26)
note(sl, ML + CW * 0.58, y + h + 0.28, CW * 0.42, 1.60,
     "What is not here. ",
     "No advisory lock serialising per (model, environment), no transaction around the three writes, no cache "
     "pre-warm and no scheduled post-move comparison. Each was described as built and none is. The three writes "
     "in the last line are the ones to fix first.")
