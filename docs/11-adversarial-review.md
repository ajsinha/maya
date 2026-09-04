# 11 — Adversarial Design Review

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Reviewed:** documents [00](00-mathematical-foundations.md)–[10](10-roadmap.md) and [ADRs 001–010](adr/INDEX.md).
**Posture:** adversarial. The objective was to *break* the design, not to confirm it.
**Outcome:** 27 findings — 6 critical, 9 high, 8 medium, 4 low — plus one architectural change mandated
by the sponsor. All are dispositioned; 23 required document changes, applied and cross-referenced below.

---

## 1. Method

Five attack lenses were applied in sequence. Each is a question that has historically destroyed systems
of this type.

| Lens | Question asked of every design claim |
|---|---|
| **L1 · Contradiction** | Do two stated guarantees conflict under some reachable state? |
| **L2 · Silent failure** | What fails in a way nobody notices for six months? |
| **L3 · Adversary** | What does a motivated insider or attacker do with this? |
| **L4 · Scale & cold start** | What breaks at 50,000 models, or on day one with 1,200 legacy models and no evidence? |
| **L5 · Overclaim** | Which stated guarantee is weaker than the words imply? |

**Severity scale**

| | Meaning |
|---|---|
| **Critical** | Breaks a load-bearing guarantee, or produces silently wrong governance outcomes |
| **High** | Causes incidents, data corruption, or adoption failure |
| **Medium** | Correctness or operability defect with a workaround |
| **Low** | Clarity, consistency, or hygiene |

---

## 2. Critical findings

### C-1 · The kill switch and the availability guarantee contradict each other
**Lens:** L1 · **Challenges:** [06 §1 G4 vs G5](06-warrants-and-execution.md), [ADR-007](adr/ADR-007-warrant-protocol.md)

The design asserts that a model is stoppable globally in under 60 seconds (`G4`), *and* that a descriptor
remains usable for a 900-second grace window if MAYA is unreachable (`G5`). These cannot both hold. An
attacker — or an ordinary network partition — that isolates an execution engine from MAYA converts the
grace window into a **15-minute window during which a revoked, known-harmful model keeps making
decisions**. Worse, the incident that motivates revocation (a bad market-data feed, a fairness breach) is
correlated with infrastructure stress, so the partition and the revocation are *likely to co-occur*.

**Disposition — redesign.** Revocation and staleness are separated into two independent mechanisms.

1. **Revocation floor.** SDKs maintain a locally persisted **revocation list**, refreshed on every
   successful resolution and on the event stream. A descriptor whose id, version, or model appears on the
   locally cached revocation list is refused **regardless of grace state**. Grace extends *authorisation
   currency*, never *revocation ignorance*.
2. **Severity-scaled TTL.** Tier 1 production descriptors carry `ttl = 60s`, `grace = 0s` by default.
   The grace window is an opt-in, per-grant, expiring concession, granted only where the consumer can
   evidence that fail-closed is more dangerous than fail-stale (real-time payment authorisation is the
   canonical case) — and those grants are themselves reported as a KRI.
3. **Revocation epoch on every response.** Any MAYA response — including telemetry acknowledgements —
   carries the current epoch, so an engine still talking to *any* MAYA endpoint learns of a revocation
   even if resolution is failing.
4. **Honest statement of the residual.** Worst case is now: a fully partitioned engine holding a
   pre-partition descriptor, for at most `ttl + grace`. With the defaults above that is 60 seconds for
   Tier 1. This is stated as a limitation rather than buried.

---

### C-2 · The online feature store is not versioned, silently defeating the feature contract
**Lens:** L2 · **Challenges:** [07 §6](07-feature-platform.md), [05 §7](05-data-model.md)

This is the most serious defect found. The design pins each model version to exact
`feature_view_version` records — and then describes an online store synced from the offline store with
"last-value-per-entity semantics". The online store has **no version dimension**.

Consequence: when feature view `sb_financials` advances from v7 to v8 with a changed transformation, the
online store begins serving v8 values. A model version whose contract pins v7 continues to resolve, its
contract digest still matches, every check passes — and it is now being served features computed by a
transformation it was never fitted on. This is precisely the training–serving skew the feature platform
exists to prevent, introduced by the platform itself, with **every guard reporting green**.

**Disposition — redesign.** The online store is namespaced by feature view version.

- Key layout becomes `fv:{feature_view_id}:v{version}:{entity_id}`.
- Contract resolution selects the namespace for the **pinned** version, not the latest.
- Publishing a new view version starts a **dual-write** period; the old namespace is retained until no
  active contract references it — which MAYA knows exactly, from the contract table.
- Namespace retirement is a governed action with a consumer-impact check, identical to feature deprecation.
- A new law, **L-17 (contract–serving agreement)**: for every active warrant, the online namespace served
  must equal the namespace pinned by its contract. Checked continuously, not at design time.

Cost is roughly `k ×` online storage, where `k` is the number of concurrently pinned versions per view —
in practice 1–2. That is the correct price.

#### Recurrence — the same failure, found twice more during the build

C-2 was recorded as a defect. It is better read as a **class**, and the evidence for that is that the
identical shape has since been found twice more, in code, in places the original disposition did not
reach. The shape is always this: **a stable identifier over moving contents.** Something names a thing;
the thing can change underneath the name; the digest of the namer does not move; every guard reports
green.

| Where | The pin that was not one | Found | Disposition |
|---|---|---|---|
| **Feature view** (the original C-2) | An online store keyed by entity, serving whatever was latest | Design review | The version *is* the serving namespace |
| **Featureset** — one level out from the view | A featureset version bound each slot to a **path**. A path is mutable: two writes produce two Delta versions and a read gets whichever is current, so a snapshot was reproducible only until somebody wrote to the view again | Building the featureset roll-forward | A binding now carries the **Delta version** alongside the namespace, and reads are pinned to it. `restated()` answers the neighbouring question a reviewer asks before comparing two runs: *has anything underneath this pin been written to since?* That is what makes *same featureset version → same bytes* true rather than true-until-Tuesday |
| **Composition** — one level in | A child named a parent, and a feature's definition is amendable. Amending a parent silently changed every child that composed it | Building the composition fold | A composition now stamps the parent's **`definition_version`**, and drift against it is **reported** on the resolved view. Note precisely what that is: resolution still reads the parent as it currently stands, because a child whose parent has moved is a thing to be told about rather than a read that should fail. It is a detector, not a freeze — and calling it a pin would repeat C-2's original error one abstraction higher |

**The gap this leaves.** Featuresets carry `composes` **without** the `definition_version` stamp, so a
composed featureset has no drift to report. That is the third instance of the class, still open.

**What the recurrence argues.** Three findings of one shape, in three subsystems, across a design
review and two implementation passes, is not three mistakes. It is a missing habit. The habit, stated
so it can be applied to the next new object rather than rediscovered in it: **whenever one governed
object names another, ask what the name resolves to at read time, and whether that can differ from
what it resolved to at write time.** If it can, either pin the resolution or report the drift — and say
in the document which of the two you did, because they are not the same guarantee and the word
"pinned" has now been used for both.

---

### C-3 · `model_version` immutability is enforced by a rule that silently discards writes
**Lens:** L2 · **Challenges:** [05 §4](05-data-model.md)

The DDL uses a Postgres `RULE ... DO INSTEAD NOTHING` to enforce version immutability. Three defects:

1. It **silently succeeds**. The application believes the write landed. `UPDATE` reports rows affected.
   No error surfaces. This is the worst possible failure mode for an integrity control.
2. It only triggers when `manifest_digest` changes. An `UPDATE` altering `input_schema` while leaving the
   digest untouched passes — so the projection can silently diverge from the manifest it projects.
3. Rules are a legacy mechanism with surprising interactions with `RETURNING` and triggers.

**Disposition — redesign.** Replace with a `BEFORE UPDATE` trigger that `RAISE EXCEPTION`s on any change
to an immutable column, and add a **generated** constraint asserting that the projected columns agree with
the manifest:

```sql
CREATE OR REPLACE FUNCTION model_version_immutable() RETURNS trigger AS $$
BEGIN
    IF (to_jsonb(OLD) - 'status' - 'updated_at')
       IS DISTINCT FROM (to_jsonb(NEW) - 'status' - 'updated_at') THEN
        RAISE EXCEPTION 'model_version % is immutable; create a new version', OLD.id
              USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_model_version_immutable
    BEFORE UPDATE ON model_version
    FOR EACH ROW EXECUTE FUNCTION model_version_immutable();
```

The same pattern replaces every "append-only" claim in the schema. **Silence is never an acceptable
enforcement mechanism for an integrity control.**

---

### C-4 · The evidence chain detects mutation but not deletion or history insertion
**Lens:** L3 · **Challenges:** [05 §10](05-data-model.md), [09 §4](09-security-compliance.md)

`evidence_node.chain_hash = H(content_hash ‖ sorted parent chain_hashes)` forms a Merkle **DAG**. A Merkle
DAG detects tampering with a node's *content* — but it has no global ordering, so:

- **Deleting a leaf** (an inconvenient failed test result) leaves every remaining hash valid.
- **Inserting** a node into the past leaves every remaining hash valid.
- Nothing binds the graph to wall-clock time, so a whole subgraph can be back-dated.

The `audit_log` table gets this right — it has `prev_hash` forming a linear chain — and the evidence graph,
which carries the higher-value claims, gets it wrong. That inconsistency is itself the tell.

**Disposition — redesign.**

1. Add a monotonic `seq bigint` and `prev_hash` to `evidence_node`, forming a **linear append chain over
   the DAG**. Node hash becomes `H(seq ‖ prev_hash ‖ content_hash ‖ sorted parent chain_hashes)`.
   Deletion or insertion now breaks the chain at a detectable point.
2. **Anchor** the daily chain head to WORM storage and to an internal RFC-3161 timestamping authority, so
   back-dating requires compromising two systems under different control.
3. Verification job walks the chain and **compares the head against the anchor**, not merely against
   itself — self-consistency of a chain an attacker controls proves nothing.
4. Database role separation: the application role holds `INSERT`/`SELECT` only; retention deletion runs
   under a distinct, dual-controlled role, and every such deletion writes a tombstone into the chain.

#### Recurrence — the chain verified while the record lied

Disposition 1 was implemented, and implemented **wrongly**, in a way that left the finding open while
looking closed. `verify_chain` walked the chain and re-linked each node's **stored** `content_hash`
rather than **re-deriving** it from the node's own fields. Re-linking proves the links are intact and
says nothing about whether the thing linked is still what was recorded — so an edited payload left a
chain that verified cleanly and a record that lied. Every property C-4 was raised to obtain was absent,
and the verification job reported valid.

Two things about how it was found are worth more than the defect.

**The scale suite found it, on its first run** — not a correctness test. The suite exists to assert that
things are still correct at a size where a good implementation and a bad one look different, and it
happened to be the first thing to walk a long chain with a mutated node in it.

**The unit test that should have caught it was passing for a reason other than its name.** It was named
for payload tampering and actually altered the *stored* content hash — which the re-linking
implementation did detect. So there was a green test called "detects a tampered payload" that had never
detected a tampered payload. That is the most expensive kind of test to own, because it converts an
absent control into a reported one, and no amount of running the suite reveals it.

**Disposition.** Verification now re-derives each node's content hash from its kind, subject, payload
and parents before checking any link, and the four checks run in order: sequence gap → `prev_hash` →
re-derived `content_hash` → `chain_hash`. The test was rewritten to do what it was named for, and
separate cases now cover an altered payload, an altered subject and an altered stored hash. Disposition
2 — anchoring the chain head to WORM and an RFC-3161 timestamp — **remains unbuilt**, so C-4 is
partially discharged rather than closed.

---

### C-5 · Day-one adoption fails: 1,200 imported models are all non-compliant
**Lens:** L4 · **Challenges:** [10 Phase 1](10-roadmap.md) — an omission, not an error

The design describes steady-state operation beautifully and never addresses the cold start. On import
day, 1,200 existing models arrive with no evidence graph, no feature contracts, no reproducible runs, and
documentation in Word files. Every gate fails. Every dashboard is red. Every KRI breaches. The MRM office
concludes the platform is broken; developers conclude it blocks them; the programme dies in month seven.

This is the single most likely cause of failure for the whole initiative, and it was absent from the design.

**Disposition — new capability.** A first-class **Baseline Import** mode.

- Imported models enter status `baselined`: in the inventory, tiered, and governed *going forward*, but
  explicitly **not** asserting historical evidence.
- Every baselined model carries a **compliance debt record**: which evidence is absent, its materiality,
  and a dated plan to close it. Debt is a tracked, reportable, burn-down quantity — not a breach.
- Gates operate in **grandfathered mode**: the *next* material change to a baselined model requires full
  evidence. Existing use is not blocked; change is.
- Dashboards separate **debt** from **breach** on every view. A Tier 1 model with baseline debt and a Tier
  1 model with a missed validation must never render the same colour.
- Debt has a board-approved expiry per tier (Tier 1: 18 months; Tier 2: 30 months), after which it becomes
  a breach.

Without this, the platform is technically correct and organisationally unusable.

---

### C-6 · `descriptor_only` warrants make governance dependent on client honesty
**Lens:** L3 · **Challenges:** [06 §3](06-warrants-and-execution.md) — an overclaim

The `descriptor_only` flavour exists because most of a bank's estate runs in engines that will never be
replaced. But such an engine receives a signed descriptor and then does whatever it likes: it can skip
boundary checks, ignore the feature contract, cache the artefact indefinitely, and never send telemetry.
The design presents this as governed execution. **It is governed *resolution* with unverified execution**,
and the difference matters.

**Disposition — accept the limitation, close what can be closed, and say so plainly.**

1. **Engine certification.** Each execution engine is registered as a principal with a certification level:
   `attested` (uses a MAYA SDK, verified build, signs its telemetry), `cooperating` (custom integration,
   sends telemetry, unverified), `opaque` (resolves only). Certification level is an **input to model risk
   tiering** — an opaque engine raises the effective complexity of every model it runs.
2. **Liveness as a control.** A principal that resolves but never reports telemetry is an exception,
   detected and raised. Silence is evidence.
3. **Signed telemetry** from attested engines; unsigned telemetry is retained but marked lower-trust — and
   the evidence semiring propagates that trust automatically ([00 §9.2](00-mathematical-foundations.md)).
4. **Policy.** Tier 1 consumer-impacting models may not be granted `opaque`-tier warrants without a dated,
   approved migration plan.
5. **Documentation change.** [06](06-warrants-and-execution.md) now states this limitation explicitly rather
   than implying uniform enforcement.

---

## 3. High findings

### H-1 · Cache stampede on alias move will breach the warrant latency SLA
**Lens:** L4 · **Challenges:** [04 §15](04-architecture.md), `NFR-PERF-002`

Alias move invalidates cached descriptors for a model. For a model at 14,000 requests/second, every
in-flight consumer misses simultaneously and hits Postgres. The p99 target of 50 ms is breached by orders
of magnitude, and the database is the failure point — during a *governed, routine* operation.

**Fix.** (i) **Pre-warm before invalidate**: build and sign the new descriptor, write it to cache, *then*
flip the pointer — the cache is never empty. (ii) **Single-flight coalescing** per `(urn, principal, env)`
so concurrent misses produce one backend call. (iii) **TTL jitter** of ±20% to prevent synchronised
expiry. (iv) **Stale-while-revalidate** on the resolver: serve the previous descriptor for up to 5 s while
the new one is built. Added to [04 §15](04-architecture.md) and [06 §6](06-warrants-and-execution.md).

### H-2 · `maya-warrants` reading the control-plane schema directly is unacceptable coupling
**Lens:** L1 · **Challenges:** [04 §3, §10](04-architecture.md)

The warrant service is described as independently deployable and independently available — yet it queries the
control plane's normalised tables. A control-plane migration breaks the warrant plane, which is the one
component that must never break; and the deployment independence is fictional.

**Fix.** The warrant service reads **only** a dedicated `warrant_projection` read model — a flat, versioned,
denormalised table maintained by the control plane through the outbox. Its schema is a published contract
with its own version, changed under expand/contract discipline. The warrant service holds no knowledge of any
other table. This also removes the join cost from the hot path. Reflected in [04 §3](04-architecture.md)
and [05 §9](05-data-model.md).

### H-3 · Immutable evidence and GDPR erasure are in direct conflict
**Lens:** L1 · **Challenges:** [05 §10](05-data-model.md) vs [07 §7](07-feature-platform.md)

Evidence nodes are append-only and hash-chained. Data-subject erasure requires deletion. If any evidence
payload contains personal data, the two requirements are irreconcilable and the design does not say which
wins.

**Fix — structural, not procedural.** **Evidence nodes never contain personal data.** They contain
hashes, counts, statistics, and pointers. Any payload that could contain personal data lives in Delta,
referenced by `payload_uri`, encrypted under a per-subject key. Erasure destroys the key
(crypto-shredding); the payload becomes unrecoverable; **the hash chain remains valid**, because it is
computed over `content_hash`, not content. The erasure itself is written into the chain as an event. A
`contains_personal_data boolean` column is added to `evidence_node` with a `CHECK` constraint forbidding
inline payloads when true. Now both obligations hold simultaneously and provably.

### H-4 · Circular and forward foreign-key references make the schema uncreatable as written
**Lens:** L5 · **Challenges:** [05 §4, §8](05-data-model.md)

`model_version.fitting_run_id → run` while `run.model_id → model`; `finding.breach_id → breach` while
`breach.finding_id → finding`; `validation.report_document_id → document` while
`document.model_version_id → model_version`. The DDL as presented does not execute in the order given, and
two of these cycles cannot be resolved by ordering alone.

**Fix.** Cyclic pairs use `DEFERRABLE INITIALLY DEFERRED` constraints, created in a dedicated migration
step after all tables exist. `breach ↔ finding` is additionally denormalised: `finding.breach_id` is
retained and `breach.finding_id` is dropped in favour of a view, since the relationship is 1:0..1 from
breach to finding. Missing tables identified alongside — `probe_set`, `lifecycle_definition`, `document`
ordering — are supplied. See F-3.

### H-5 · Row-level security is bypassable by the table owner
**Lens:** L3 · **Challenges:** [05 §4](05-data-model.md), [09 §3.3](09-security-compliance.md)

`ENABLE ROW LEVEL SECURITY` does not apply to the table owner or to superusers. If the application
connects as the schema owner — the common default in migration-managed applications — RLS silently does
nothing, and the "defence in depth" claim is false while appearing true.

**Fix.** `ALTER TABLE ... FORCE ROW LEVEL SECURITY` on every scoped table; a dedicated non-owner
application role; a migration-only role that is not used at runtime; and a **negative test in CI** that
asserts a cross-entity read returns zero rows under the application role. Untested isolation is assumed
isolation.

### H-6 · PIT verification by sampling is presented as proof
**Lens:** L5 · **Challenges:** [07 §2.1](07-feature-platform.md), law L-10

The verifier samples rows and asserts agreement. Sampling gives probabilistic detection of *systematic*
leakage. It cannot establish absence, and a leak confined to a rare, high-value segment — exactly where it
does most damage — may well be missed. Law L-10 as stated overclaims.

**Fix — three-layer verification, honestly labelled.** (i) **Static analysis** of the assembly query for
temporal predicates: an assembly lacking both a valid-time and a transaction-time bound is *rejected*, not
sampled. This is the strong check and it is a proof for the class of leakage that matters most. (ii)
**Stratified sampling** with strata over label period, entity type and *label value*, giving stated
detection power. (iii) **Adversarial injection** in CI. Law L-10 restated: *no assembly passes without a
static temporal bound, and sampling detects systematic violations at stated power* — a weaker but true
claim.

### H-7 · Delta partitioning by `model_urn` will produce partition explosion
**Lens:** L4 · **Challenges:** [05 §12](05-data-model.md)

`PARTITIONED BY (DATE(occurred_at), model_urn)` at 50,000 models × 365 days yields ~18 million partitions
and a metadata problem that dwarfs the data problem, with catastrophic small-file behaviour.

**Fix.** Partition by date only; use **liquid clustering** on `(model_urn, occurred_at)` for pruning.
Ingest via Kafka → Structured Streaming with a 60-second trigger, optimised writes and auto-compaction.
The 50,000 events/second target is restated honestly as **sustained ingest with ~60–90 second visibility
latency**, not real-time; monitoring queries tolerate this, and anything that cannot is served from the
event stream instead of the table.

### H-8 · Tier gaming is only partly mitigated
**Lens:** L3 · **Challenges:** [09 T5](09-security-compliance.md), [04 §13.2](04-architecture.md)

Tier is derived, traced, and monotone — all good — but it is derived *from facts*, and several facts are
human-entered. Understating an exposure measure or selecting a lower purpose class lowers the tier through
a perfectly valid, fully audited derivation. The control catches override but not **input manipulation**,
which is the easier and more deniable attack.

**Fix.** (i) Exposure measures are **sourced**, not typed: bound to a system of record with a reconciliation
job, and flagged `unsourced` where that is impossible. (ii) `purpose_class` changes require approval at the
tier being *left*, not the tier being entered. (iii) **Outlier detection** across peer models: an artefact
whose declared exposure is far below its cohort is flagged. (iv) **Retrospective calibration**: annually,
tier assignments are back-tested against realised incidents, findings and losses — a tier that never
predicts anything is evidence of systematic understatement.

### H-9 · Single Postgres primary is a structural scaling ceiling
**Lens:** L4 · **Challenges:** [04 §12](04-architecture.md)

Inventory reads, evidence-graph traversals, audit-log writes and warrant projection maintenance all land on
one primary. Evidence traversal is recursive and read-heavy; audit is write-heavy and cannot be lost;
they compete.

**Fix.** (i) Audit log on a **separate physical database** with synchronous replication, removing the
write competition and simplifying its distinct retention and role model. (ii) Read-replica routing for all
traversal and reporting queries, with an explicit staleness budget shown in the UI. (iii) Evidence graph
partitioned by month with a rolling materialised closure for hot subgraphs. (iv) Stated capacity model and
the trigger point at which the evidence graph moves to a dedicated store — deliberately *not* done
prematurely.

---

## 4. Medium findings

| ID | Finding | Disposition |
|---|---|---|
| **M-1** | **`Para(Stoch)` handles adaptive (T4) models awkwardly.** A time-indexed parameter object is not an object of the category; the paper admits this, [00](00-mathematical-foundations.md) does not. | Caveat added to [00 §4.2](00-mathematical-foundations.md). T4 is modelled as a *sequence* of models with a governed change process, plus a coalgebraic treatment noted as future work. Consistency between paper and design docs restored. |
| **M-2** | **Provenance polynomials can blow up exponentially** on wide OR-structures; "mitigated by depth limits" understates it. | Complexity stated: `Why(X)` is worst-case exponential in the number of alternative derivations. Mitigations made concrete — canonical form with absorption, memoisation, a hard term cap that degrades to `Boolean ⊕ Trust` with an explicit truncation marker rather than silently. |
| **M-3** | **Outbox → Delta writes are not idempotent.** At-least-once delivery duplicates rows. | Every Delta write carries an `outbox_id`; writers use `MERGE` on it. Reconciliation compares outbox rows marked done against Delta counts and has a **defined repair action**, not merely an alert. |
| **M-4** | **Composite warrants may re-resolve members mid-execution**, producing an internally inconsistent valuation chain. | A composite pins **all** members at first resolution and holds them for the execution's declared lifetime; the pinned set is recorded so the result is attributable. Long-running composites renew as a set or fail. |
| **M-5** | **Law L-6 (summary soundness) only checks machine-parseable claims.** Narrative assertions are unverified, and the law implies otherwise. | Restated: soundness is checked for **quantitative claims in structured sections**. Narrative sections carry an explicit `unverified_narrative` marker and require human attestation. Honest scope. |
| **M-6** | **No FinOps model.** GenAI token spend, Spark compute and sandbox fleet costs are unbounded and unattributed. | Cost is a first-class dimension: per-warrant budgets already exist; added per-model and per-business-unit cost attribution, showback, and cost as a monitored metric with thresholds. |
| **M-7** | **Deletion of a model is undefined.** Retention, legal hold and erasure interact; the design covers decommissioning but never *deletion*. | Explicit retention state machine: `decommissioned → archived → (legal hold?) → purge-eligible → purged`, with purge requiring dual control and writing a tombstone. Legal hold blocks every transition. |
| **M-8** | **Notification storms.** A single upstream failure raises findings on every downstream model, mailing hundreds of owners. | Findings are **correlated**: a root-cause finding with downstream *impact records*, not N independent findings. Notification is to the root owner plus a digest to affected owners. Suppression windows and deduplication keys defined. |

---

## 5. Low findings

| ID | Finding | Disposition |
|---|---|---|
| **F-1** | `docs/README.md` duplicates orientation content now in the root `README.md`. | `docs/README.md` reduced to a navigation index; the root `README.md` is the single front door. |
| **F-2** | Trainability class is stored on both `model_class` and `model`, with the override rule unstated. | Documented: the class default applies unless explicitly overridden, and an override requires a recorded reason. |
| **F-3** | `probe_set`, `lifecycle_definition` and `document` are referenced before definition in [05](05-data-model.md). | DDL supplied and ordering corrected. |
| **F-4** | ADR-008 conflicts with the sponsor's architecture mandate (see §6). | Superseded by [ADR-011](adr/ADR-011-decoupled-frontend.md). |

---

## 6. Mandated architectural change: decoupled front end

The sponsor requires that **the UI and the backend run as separate, concurrent processes, with the UI
consuming backend services**. [ADR-008](adr/ADR-008-server-rendered-ui.md) specified a server-rendered
Jinja2 application and is therefore **superseded** by [ADR-011](adr/ADR-011-decoupled-frontend.md).

This is a genuine improvement for three reasons the original ADR undervalued, and it carries four costs
that must be designed for rather than discovered.

**Gains.** The API becomes the *only* interface, so it is exercised by the product itself and cannot rot
behind a privileged server-side path — which was a real risk in the original design. Front end and backend
scale, deploy and fail independently. The UI becomes replaceable without touching the backend.

**Costs, and how they are handled.**

| Cost | Design response |
|---|---|
| **Authentication moves into the browser** | OIDC Authorization Code + PKCE; tokens held in memory, never `localStorage`; refresh via a `__Host-` prefixed, `SameSite=Strict`, `HttpOnly` cookie against a minimal token-broker endpoint |
| **Governance logic could leak into the client** | Principle **P4′** — the client renders decisions, it never derives them. Every gate verdict, tier, obligation and eligibility flag arrives from the API *with its rationale*. Enforced by review and by API design: endpoints return `allowed` plus `deny_reason[]`, never the raw facts a client would need to compute a verdict |
| **CORS and CSRF surface** | Strict origin allow-list; bearer tokens on the API (no ambient cookie authority, so CSRF does not apply to API calls); the token-broker endpoint is the only cookie-bearing surface and is CSRF-protected |
| **Evidence-grade rendering** | Server-side rendering of documents, reports and export packs is **retained** as an API capability returning HTML/PDF, so an artefact taken into a meeting or an examination is produced by the backend, not assembled by a browser |

Full design in [ADR-011](adr/ADR-011-decoupled-frontend.md) and the revised [08 — UI/UX](08-ui-ux.md).

---

## 7. What survived the review

Stating this matters as much as the findings; a review that criticises everything is as useless as one
that criticises nothing.

| Design element | Verdict |
|---|---|
| `Para(Stoch)` model definition and the trainability classification | **Held.** No artefact in the taxonomy resisted presentation as a `(P, φ)` pair. The T4 awkwardness is a modelling inelegance, not a failure |
| Non-compositional aggregate risk (theorem in [00 §5.2](00-mathematical-foundations.md)) | **Held.** Attempts to construct a compositional yet fragility-sensitive measure failed, as the theorem requires |
| Fibration-based extensibility | **Held**, and strengthened: fibre totality checking at load time closes the half-implemented-class gap |
| Institutions for plural regulatory scope | **Held.** The strongest element of the design. Survived a deliberate attempt to construct conflicting regime determinations — the satisfaction condition caught the constructed defect, which is exactly its purpose |
| Semiring evidence engine | **Held**, with an honest complexity bound (M-2) |
| Postgres / Delta split | **Held**, with H-7 and H-9 corrections |
| Overlay (PMA) register | **Held.** No defects found; remains a genuine differentiator |
| Sandbox-only artifact loading | **Held.** The most robust security decision in the design |
| Laws-as-tests discipline | **Held in principle, and the build has tested the principle.** C-2, C-3 and H-6 would each have been caught earlier had the corresponding law existed. Since the review, thirteen more laws have been added: L-17 (contract–serving agreement), L-18 (no personal data in evidence nodes), **L-19** (composition is a monoid), and the eleven warrant-admissibility laws L-W0…L-W10 — of which L-W8 caught a real error in a shipped example on the day it was written. The honest qualification is in [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces): only seven of the nineteen foundational laws are executable today, and a law that is stated but not executed did not prevent anything. C-4's recurrence above is what that costs |

---

## 8. Disposition summary

| Severity | Count | Redesign | Doc change only | Accepted with statement |
|---|---|---|---|---|
| Critical | 6 | 5 | 0 | 1 (C-6) |
| High | 9 | 7 | 1 | 1 (H-6, rescoped) |
| Medium | 8 | 4 | 4 | 0 |
| Low | 4 | 1 | 3 | 0 |
| **Total** | **27** | **17** | **8** | **2** |

Two findings — **C-2** (unversioned online store) and **C-5** (day-one adoption) — would each,
independently, have been sufficient to cause the programme to fail. C-2 would have produced silently wrong
production scoring with every monitor green. C-5 would have produced organisational rejection in month
seven. Neither was visible from inside the original design; both were found by asking the adversarial
questions systematically rather than reviewing for correctness.

That is the argument for running this review before writing code, and again after each major phase.
It is scheduled accordingly in [12 — Implementation Plan](12-implementation-plan.md).

## 9. What the build has since said about the review

Two findings have **recurred** — the same shape, in code, after the disposition was written. They are
recorded in place, above, rather than in a separate log, because a finding whose recurrence lives
somewhere else is a finding a reader will believe is closed.

| Finding | What recurrence showed |
|---|---|
| **C-2** | It is a *class*, not a defect. The same stable-identifier-over-moving-contents shape appeared at the featureset level and again at the composition level, and one instance of it is still open (a composed featureset stamps no parent version). The generalised habit is stated at the end of C-2 |
| **C-4** | A disposition can be implemented and still be absent. Verification re-linked a stored hash instead of re-deriving it, so the control reported valid on a record that had been edited — and the unit test named for exactly that case was asserting something else |

Neither was found by re-reading this document. C-2's recurrences were found by building the next
object; C-4's was found by the scale suite. **A review is a way of noticing a class, and the build is
where you find out how many members it has.**

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
