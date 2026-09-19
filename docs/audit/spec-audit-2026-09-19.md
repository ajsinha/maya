# MAYA specification audit: rev 2.3 against `develop` @ b30a428 (2026-09-19)

> **Status since the audit.** Fixed, each with a test:
> gap 1, the review queue, SLA aging and break-glass report now name only what the
> caller may read (`tests/test_read_scoping.py`);
> gap 2, the lineage graph leaves out what the caller may not read and counts it in
> `hidden` (same file);
> gap 5, a training warrant stores what a bare or undated feature-set reference
> resolved to, and logs what was given (`tests/test_runbook_defects.py`).
> Found while writing the paper and fixed: a model that declares parameters —
> closed-form or black box — can no longer get an execution warrant without a named,
> approved parameter set (same file).
> The restore drill has been performed on SQLite and PostgreSQL 17 and recorded in
> [the runbook](../runbooks/restore-drill.md#5-record-the-result), which answers part of
> gap 33, and `bench_capacity.py` has been run ([BENCHMARKS](../BENCHMARKS.md)), which
> answers part of gap 34. Everything else below stands as written; line numbers are as
> of b30a428.

This audit was read-only; no repository file was edited. Every section §1–§30 was checked against maya/, maya_delta/, tools/ and tests/. §1–§9 and §26–§30 were audited directly, §10–§16 and §17–§25 by two parallel sub-audits. Their detailed tables are appended below, and the top findings of each were re-verified by reading code.
Excluded as out of scope by the owner's decision: Windows/macOS (SC-14), live Claude API, a dedicated benchmark host, SC-9, and an external security review.
**Caveat:** during the audit another session had uncommitted changes in the working tree (api/routers/catalog.py, cli/__main__.py, core/backends.py, persistence/estate.py, repositories/base.py, resolution/shapes.py, sdk/resources.py, services/access.py, custody.py, execution.py). No verdict depends on them, but some line numbers may shift.

## Counts (approximately 540 requirements; each table row or screen counts as one)

| Class | §1–9, §26–30 | §10–16 | §17–25 | Total |
|---|---|---|---|---|
| Built and tested | ~45 | 82 | 68 | **~195** |
| Built, untested | 5 | 10 | 13 | **28** |
| Partially built | 22 | 44 | 57 | **123** |
| Not built | 11 | 35 | 38 | **84** |
| Deliberately superseded | 2 | 3 | 5 | **10** |

## Consolidated gaps, sorted by importance to a user of the platform
Detail (spec quote, file:line, what is missing) is in the section tables below; the IDs refer to them.

### Security and correctness (fix first)
1. **Workflow queue, aging and break-glass leak across namespaces.** `GET /workflow/queue|aging|break-glass` (maya/api/routers/workflow.py:20-32; workflow_service.py:~150-181) do no read check. Any signed-in user sees every in-review object and break-glass event in every namespace. [W-series, §10/§11] S
2. **Lineage leaks object names across namespaces.** `GET /api/v1/lineage` (api/routers/admin.py:275, services/ops.py:205) takes no principal and applies no read filter. [§19] S
3. **No upload expansion or size limits.** Zip bombs are possible in bundle verify and .xlsx import; CSV, Parquet, artifact and bundle uploads have no size cap and are read whole into memory. There are no API rate limits, timeouts or load shedding. [§13.2, §18.1, §21.1, §24.4] M
4. **The `delta` source reads any server path, ignores its version and stamps knowledge time = now on every read.** A past `as_of_known` therefore returns nothing, the feature can't be reproduced point in time, the path is unchecked by any ACL, and there is no test. [A7, §5.2] M
5. **A bare name is never logged and moves under a warrant.** `Ref.is_bare` is never called. A training warrant stores the feature-set ref verbatim and re-resolves it on every download and holdout score, so "latest" silently changes. [A2, §4] S–M
6. **The workflow `when` condition only understands `"prod"`.** Any other string, including the spec's own `env == 'prod'`, silently makes the approval always required, and the validator accepts it. (engine.py:236-237) [W1, §10.2] S
7. **Composite-warrant controls are written but not wired in.** `member_seeds`, `check_structure` (depth 4 and cycles) and `is_partially_opaque` are called only from unit tests. Sealing needs just one approved parameter set, not one per trainable member, and there is no outstanding-members report. [A3, §8.7, §9.5] M
8. **Composite access propagation is not built:** read on every member, and no granting of members you don't own. [A5, §8.7] M
9. **Escrowed holdout isn't escrowed.** The test split is recomputed live each time, with no hash taken at issue. Only closed-form IR can be scored; there is no prediction-function or artifact scoring. [A6, §29.4] M

### Core user-facing functionality
10. **FeatureSet algebra (§6.8) is only `extend`.** ∪, ∩, ∖, ⋈, `override`, pivot/unpivot and `sample` are not built. [A1] L
11. **The review screen (§10.3, §10.6) lacks** the semantic diff, the impact list of dependents and their owners, SoD strictness and outstanding approvals, and it may show a policy from the wrong scope (web/routes/workflow.py:46). M
12. **`tracking` bindings do nothing.** Neither a child feature/set nor a composite is marked for re-approval when the parent or member bumps. Member deprecation doesn't warn composites, and member-warrant revocation doesn't flag composite execution warrants. [A4, A16] M
13. **Subscriptions are not built.** The `subscriptions` table exists but is unused. [A8, §5.7, D-2] M
14. **The SDK doesn't match §18.2.4.** There are no object handles (`feat.version().pin()`, `pin.to_arrow()`), typed models, `job.wait()` on a handle, `await job`, or training-data context manager. Event streams (`Events.stream`, `Jobs.events`) block until timeout. There is no cache, ETag, presigned or resumable download, or auto-idempotency. [§18.2] L
15. **§16.4 interaction principles are missing:** the pin preview (rows, fill report, storage estimate, cost) before commit, disabled-with-reason controls, and a request-access button. Cast preview isn't exposed in the API, SDK or UI. Access requests (§11.5) are not built. M
16. **No quota, cost or retention.** `quota_bytes` is stored and never enforced. There is no pin footprint estimate, cost estimate or roll-up, cold tier, retired-pin archive, or fragment GC (report only). [A10–A12, §7.3, §29.3] M
17. **Feature-set composition (§6.7, §6.3, §6.2) is thin.** There are no nested-set members, fork, set-version diff, or cost estimate. There are no global boolean filter, point-in-time universe from another feature, or per-member alignment override. [A9, A13, A14] M
18. **CLI gaps (§18.3):** `featureset build`, `model validate`, `warrant create` and `admin user|role|grant|policy` are missing. S–M
19. **Bundle (§18.4) omits** the uploaded code artifact, the feature-set definition, and member pins' data and manifests. M
20. **Catalog facets (§16.2) cover namespace only.** Type, owner, status, tag and freshness are missing. S

### Next tier
21. **Execution manifest:** no PDF, no live-input policy, and the composite DAG is not resolved. [A15] M
22. **Parameter upload** accepts no NPZ, Pickle (scanned) or ONNX. [A17] M
23. **Assistant:** there is no drafting of a feature definition or spec sections. [A18] M
24. **Shadow replay** covers training warrants, not execution warrants. It has one global materiality threshold and no per-namespace budget. [A19] S–M
25. **Covenants:** there is no PSI covenant. [A20] S
26. **Missing notifications:** on a covenant breach and at 30 days before expiry, the model manager is not notified; neither is the owner on a failed quality check. [A20–A22] S
27. **Change class** is not surfaced on dependents, and no test covers it. [A23] S–M
28. **Freshness contract:** the pre-pin staleness warning is not built. [A24] S
29. **Job fairness** has no per-user cap or weighting. Jobs run as threads inside the web process, not worker processes, and there is no backpressure or cache (§15). M
30. **Lineage canvas (§16.3):** collapse, filters, hover detail, overlays, canvas authoring, the review overlay and clustering are missing. L
31. **Auth (§12):** missing items:
    - password history and maximum age;
    - concurrent-session caps and reset tokens;
    - per-key rate limit, key rotation and client credentials;
    - credentials for service accounts;
    - admin break-glass login in `mode: sso`.

    M
32. **Editors (§17):** the expression editor, BibTeX, spell check, find/replace, figure upload and LSP are missing. Bracket matching is claimed but the addon is not vendored. Tectonic has no resource cap or network isolation. M–L
33. **Observability (§20):** about half the listed metrics are missing, there are no SLO rules, and five runbooks are missing. Integrity verification is not scheduled, and there is nowhere to record a restore-drill result. M
34. **Config (§22, §24):** unknown keys are accepted, there is no typed schema, and code defaults are used silently. There is no container build and no worker-only process or S3 topology. `bench_capacity.py` has never been run. M
35. **§25:** there is no plugin or entry-point framework, no S3/Azure/GCS, no email/Slack/Teams, and none of the five integrations. L
36. **Low:** visual node editor [A25], `custom(fn)` rule [A26], warrant shape ignored [A27], tensor grid in the UI [A28], artifact smoke sample and packages [A29], object-store Parquet path [A30], composite aliases [A31], composite DAG diff [A32], post-pin compaction, space-filling-curve sort and stats skipping [A33].

### Built but untested (selection)
- JSON upload; duplicate-upload warning; feature-level equivalence flag; delta source.
- Default-admin-password startup refusal; session timeouts; API-key CIDR allowlist; job retry and dead-letter; startup reaper; inert-grant warning.
- Minimum sandbox tier refusal; refusal to approve a draft PDF; version-skew 426; refusal over plain HTTP; `connect()` profile resolution; CSP and X-Frame-Options headers; SSE content.

## Spec statements that contradict the code or the spec itself (need revision markers)
- **§20** "expand-migrate-contract… backward-compatible schema" and **§23** "migration dry-run" contradict §14.3, ADR-012 and ADR-023. **§5.1** "from the first migration" makes the same slip.
- **§5.4** says steps compile to Arrow kernels. **§13.1/§15.1** promise Polars and DuckDB, and **§13.4** lists `frames`/`pushdown` seams with a "pyarrow" fallback. In fact resolution is pandas throughout, and those seams are reported but unused.
- **§7.1** layout (`pin_id/as_of` partitions, Z-order, 128 MB, "compacts after every pin", `/featuresets/`) doesn't match the fragment-partitioned `pins/<ns>/<name>` store (storage/lake.py:1-12) with scheduled maintenance.
- **§13.1** names APScheduler and a Redis driver; neither is used.
- **§13.3** promises admin break-glass login during an IdP outage, but `mode: sso` refuses all password logins.
- **§14** package layout (`mappers/`, `locks.py`, `seed.py`) and **§22.1/§22.3** (`domain/`, `ports/`) differ from ADR-001.
- **§16.7** threshold paging and whole-set multi-sort were superseded by ADR-016 without a spec marker.
- **§24.5 and §25** FTS5/tsvector rows lack the Revision 2.2 own-index marker (ADR-019).
- **§18.1** event names and URLs differ from the code (`feature_version.approved` and others).
- **§18.2.6** says there is a separate `maya-sdk` distribution; there isn't one.
- **§18.2.7** says "UI tests against the fake".
- **§23/§24.5** hosted CI conflicts with ADR-002.
- **§22** complexity limit is 10; the code uses 12.
- The `application.properties` layer versus the `application.local.yaml` overlay.
- **§25** model runtime conflicts with ADR-007.
- **§26.1** says "All ten success criteria"; there are eighteen.
- **§26.3** says ADRs are created "during Phase 0" and referenced from code. They arrived after 0.3.0 and no code cites them.
- **§30 A:** `spec_documents` and `workflow_instances` don't exist, and `feature_pins.delta_path` is absent. `feature_set_members`, `composite_members` and `subscriptions` exist in the schema but are never read or written, because members live in version JSON.
- **`namespace_read`** behaves like `public_read`, since namespaces have no membership (§11).
- **SC-14 and §24.5:** three-platform parity needs a marker pointing at ADR-014.
- **Stale docs, not spec:**
  - The README "Promised… not delivered" paragraph and the IMPLEMENTATION_PLAN still say the fallback matrix (gate 11b), `maya.testing` and the synthetic market dataset are missing. All exist since f53f838, as do `public_symbols.py` and `cycle_check.py`.
  - web/static/css/tokens.css:38 has a stale crimson-deep comment.

---

# Audit §1–§9, §26–§29 (lead auditor)

## Gaps (Not built / Partial / Built-untested)

| # | Imp | Class | Spec | What exists | Missing | Size |
|---|---|---|---|---|---|---|
| A1 | high | Not built | §6.8 FeatureSet algebra: "`project`, `S₁ ∪ S₂`, `S₁ ∩ S₂`, `S₁ ∖ S₂`, `S₁ ⋈ S₂`, `override`, `pivot/unpivot`, `sample(S, spec)`" | Only `extends` with `drop_attributes`/`add_members`/`attribute_rules`/filters/grid/alignment override: maya/services/featuresets.py:43-69. No operator field in feature-set definitions at all | Row-wise union/intersect/difference of sets, column-wise ⋈ of two sets, pivot/unpivot, seeded `sample`; cascade pin "walks the tree" over those operators | L |
| A2 | high | Not built | §4 "A bare name resolves to the latest approved version, and MAYA logs that resolution"; refs.py docstring claims "the resolution is recorded" | maya/services/catalog.py:78-91 resolves; `Ref.is_bare` (maya/services/refs.py:41) is never called | No record of which version a bare ref resolved to. Worse: a training warrant stores `featureset_ref` verbatim (maya/services/warrants.py:153) and `training_frame` re-resolves it on every download/score (warrants.py:253-262), so a bare ref silently moves to a newer approved version | S–M |
| A3 | high | Partial | §9.1/§9.5 composites under one warrant: "cannot be sealed until every trainable member has an accepted parameter set… reports which members are outstanding"; "single seed from which per-member seeds are derived deterministically" | `formula/composite.py:113 member_seeds`, `:157 check_structure`, `:168 is_partially_opaque` exist and are unit-tested (tests/test_formula.py:142-158) but **no service calls them**. `warrants.seal` (warrants.py:443-462) only requires ≥1 approved parameter set overall | Per-member outstanding report and seal gate; per-member seeds on the warrant/manifest; nesting-depth cap 4 and cycle check wired into model submission; per-member metrics view | M |
| A4 | high | Not built | §8.7 "a member reference may be `tracking`… a member bump marks the composite for re-approval"; §5.8 "`tracking` (latest approved parent, with the child marked for re-approval whenever the parent takes a breaking or behavioral bump)" | `binding` validated (catalog.py:236-239, composite.py:43); `needs_reapproval` column used only for duplicate detection (features.py:383) | Nothing reacts to a parent/member version approval: no child/composite flagged, no dependents notified | M |
| A5 | high | Not built | §8.7 "a user needs read on the composite and on every member, and the composite's owner cannot grant access to a member they do not own; MAYA names the members blocking the grant" | access.py has no composite logic | Access propagation for composites | M |
| A6 | high | Partial | §29.4 "the test partition is materialized, hashed and escrowed… uploads either the fitted parameters or a prediction function" | score_holdout recomputes the test split from a live `resolve_ref` each time (warrants.py:373-404); only closed-form IR can be scored (`predict` raises for black box, warrants.py:406-410) | Escrowed partition hash recorded at issue and checked at score; scoring of a code artifact / prediction function in the sandbox | M |
| A7 | high | Partial | §5.2 `delta` source "Existing Delta table + optional version" | feature_data.py:113-119 reads `src["path"]` with no version and stamps `_knowledge_time = now()` on every read | Version pinning; a knowledge time that is not "now" (as written, any `as_of_known` in the past filters every row out, so a delta-sourced feature cannot be reproduced point-in-time); ACL on the path (any designer can point at any Delta table on the server); **no test at all** | M |
| A8 | high | Not built | §5.7 "Subscribe to a feature and be notified when a new version is approved or a dependent pin is created"; D-2 "a browsable, subscribable object" | `subscriptions` table defined (persistence/models/operations.py:149) and never read or written | Subscribe API/SDK/UI and the notification fan-out | M |
| A9 | med | Not built | §6.7 "A feature set may include another feature set as a member (one level of nesting)… can be forked into a draft, diffed against another version attribute by attribute, and carries a cost estimate" | members are always parsed as features (featuresets.py:258-266, 283-293); feature diff exists only for features (features.py:550) | Nested set members; fork; set version diff; cost estimate | M |
| A10 | med | Not built | §7.3 "A pin's storage footprint is estimated before it is created and charged against a namespace quota… cold pins move to an infrequent-access tier… retired pins can be archived to a compressed bundle" | `quota_bytes` stored (access.py:130-158, identity.py:117) and never enforced | Estimate, quota enforcement, cold tier, archive of retired pins | M |
| A11 | med | Partial | §29.3 "a garbage collector that is provably safe against sealed pins" | ops.py:175-192 reports orphan fragments; "never deleted automatically" | Any GC (even admin-triggered) | S–M |
| A12 | med | Not built | §5.8 "the resolution planner uses these [laws] to fuse steps and prune reads, and states the rewrite in the plan"; "the cost estimate rolls up through the tree"; "derivation depth is capped (default 16, configurable)"; "Two modes: `virtual`… and `materialized`" | Depth caps are constants (catalog.py:27, featuresets.py:35); plan lists steps only | Rewrites/pushdown, cost roll-up, configurable cap, virtual/materialized mode flag | M |
| A13 | med | Partial | §6.3 "filter globally (date range, symbol universe, a boolean expression over its own attributes) or per member… compiled into the read plan… partition pruning… Universe filters may reference another feature ('in_sp500 as of the row date')" | resolution/featureset.py:148-165: start/end and a static universe list, applied post-hoc in pandas; per-attribute filter exists (:72) | Global boolean expression, feature-referencing (point-in-time) universe, pushdown | M |
| A14 | med | Partial | §6.2 "four alignment modes, declared once per feature set and overridable per member" | One alignment per set (featureset.py:93-147) | Per-member alignment override | S |
| A15 | med | Partial | §9.2 execution warrant "resolution policy for live inputs… MAYA renders it as a human-readable execution manifest (PDF and JSON)"; §9.5 "An execution warrant over a composite resolves the whole DAG: the manifest names the member models, their parameter sets… execution order" | execution.py:163-179 JSON manifest; composite = the raw IR node | PDF manifest; live-input policy; per-member resolution in the manifest | M |
| A16 | med | Not built | §9.5 "revoking a warrant on a member model also flags every composite execution warrant that embeds it, with the member named"; §8.7 "Deprecating a member warns every composite that contains it" | revoke cascades only to exec warrants of the same training warrant (warrants.py:464-483); deprecation warns warrant owners only (models.py:417-424) | Composite-aware propagation | S–M |
| A17 | med | Partial | §9.1 "an upload that accepts JSON, NPZ, Pickle (scanned), or ONNX weights with a declared schema"; "an SDK context manager that downloads, verifies and yields Arrow tables" | upload_parameters takes a `values` dict only (warrants.py:295); SDK `TrainingWarrants.data` returns bytes (sdk/resources.py:680) | NPZ/Pickle-scan/ONNX ingestion; the context manager | M |
| A18 | med | Partial | §29.8 assistant "in four places: drafting a feature definition from a description and a sample file; lifting a formula IR…; drafting the spec document sections…; and… recorded challenger" | Only the challenger (services/assistant.py, assistant/rules.py) | Feature drafting, spec-section drafting (IR lifting exists as deterministic parsers, not assistant) | M |
| A19 | med | Partial | §29.2 "re-runs every affected **execution** warrant… count of rows crossing a declared materiality threshold… Gated by a per-namespace budget" | workspaces.py replays training warrants; one global `workspaces.shadow.materiality` (workspaces.py:47-48) | Execution-warrant replay, per-model declared materiality, per-namespace budget | S–M |
| A20 | med | Partial | §29.5 "Input covenants bound… (population stability index, null rate, range, staleness)… A breach suspends the warrant, notifies the owner **and the model manager**" | COVENANT_KINDS lacks PSI (execution.py:31); breach notifies owner only (execution.py:348-351) | PSI covenant; model-manager notification | S |
| A21 | med | Partial | §9.4 "Thirty days before expiry MAYA notifies the owner and the model manager" | expire_sweep notifies owner only, execution warrants only (execution.py:388-404) | Model manager; training warrants | S |
| A22 | med | Partial | §5.5 "A failing check blocks a pin, blocks promotion… and raises an alert to the owner" | `_fail_pin` audits only (feature_data.py:341-346) | Owner notification on failure | S |
| A23 | med | Partial | §4 "surfaces the classification on every dependent object so a feature set owner sees exactly what a member change will do to them" | change_class shown on the feature's own versions (catalog/feature.html:24, compare.html:11) | Surfacing on dependents; no test asserts change_class at all | S–M |
| A24 | med | Partial | §5.2 "Every source binding records a freshness contract (`expected_lag`, `schedule`) so MAYA can flag a stale feature before someone pins it" | `freshness` popped from the hash (catalog.py:201); a `freshness_within` quality check exists (resolution/quality.py:130) | Source-level freshness contract and pre-pin staleness warning | S |
| A25 | low | Not built | §8.1 "a visual node editor for non-programmers" | none | Node editor | L |
| A26 | low | Not built | §5.3 rule `custom(fn)` | rules.py:106-108 refuses: "none are registered in this build" | Registered sandboxed fill functions | M |
| A27 | low | Partial | §6.5/§9.1 "The requested shape is part of the download and part of the warrant" | `spec.shape` stored (warrants.py:171) but `data()` always ships tabular Parquet (warrants.py:264-286) | Shape honoured on warrant download | S |
| A28 | low | Partial | §7.2 Rule 2 "MAYA can render it as a labelled grid in the UI" | axis manifest built (resolution/shapes.py:41) | Tensor grid rendering in the UI | S |
| A29 | low | Partial | §8.3 "smoke execution in a sandbox against a small sample from the declared feature set"; "a file or a small package" | smoke sample is synthetic uniform(0.5,1.5) (models.py:312-316); artifact decoded as one file (models.py:333) | Feature-set sample; multi-file packages | S–M |
| A30 | low | Partial | §5.2 `parquet`: "Uploaded file or object-store path" | upload only | Object-store path source | S |
| A31 | low | Partial | §8.7 "aliasing where two members want the same attribute under different names" | union_contract accepts `aliases` (composite.py:59) but `_contract` never passes them (models.py:238-242) | Alias declaration in the composite node | S |
| A32 | low | Partial | §8.7 "The model diff viewer renders a composite as its DAG" | textual structural statements (formula/diff.py:132) | DAG rendering | S–M |
| A33 | low | Partial | §7.1 "compacts on a schedule and after every pin", Z-order / space-filling-curve sort (§7.4), per-file min/max stats "for file skipping" | scheduled maintenance (registry.py:57); stats written (maya_delta/files.py:101) but read pruning is partition-only (files.py:52) | Post-pin compaction; SFC sort; stats-based skipping | M |
| U1 | med | Built-untested | §5.2 `json` uploads (feature_data.py:86-90); upload dedupe warning `duplicate_upload_of` (features.py:250); feature-level equivalence flag (features.py:377-384); `allow_non_causal` path (warrants.py:237) outside end-to-end cert tests; `delta` source (see A7) | — | Tests | S |

## Built and tested (terse)
Bitemporal ingest log and as_of_known (SC-11); content-addressed fragments (SC-12); canonical hashing; quality contract blocks pin and promotion (`quality_passes` check); 10 of 11 fill rules with bounds and fill report; non-causal marking; transform pipeline (13 steps); feature algebra typecheck/execute (12 operators); inheritance pinned/tracking + D-7 prod block; scratch namespace and `maya feature quick`; cast preview; compare; clone; download in 5 formats + 3 CSV encodings with manifest; feature-set precedence with "layer that won" in preview; broadcast join; refusal of unaggregated extra index; cascade pin all-or-nothing; materialize_policy always/on_demand/never; withheld attributes named and null; project(extend) equivalence; formula IR, parse/render/diff/codegen; black-box node; artifact 6-rung ladder; parameter bounds; spec template + \mayaformula + re-review; maturity cap for composites; deprecation needs successor/statement; training warrant contract/leakage cert (signed)/checksum cycle/unverified_data override; clone family; execution warrant token/environments/limits/covenants/suspend/reinstate/expiry fail-closed with contact; vendor models; licence algebra on export/grant/derivation; custody anchors; conformance testing; spreadsheets; SoD presets; SQLite prod guard + banner; job reaper.

## Contradictions in §1–§9, §26–§30 (revision-marker candidates)
- §5.1 "exist from the first migration" — there are no migrations (§14.3).
- §5.4 "compiles to Arrow compute kernels" — resolution/transforms.py runs on pandas.
- §7.1 layout `pin_id=<uuid>/as_of=<date>` partitions, Z-order, 128 MB target, "compacts… after every pin", feature-set pins "under /featuresets/" — the store is `pins/<ns>/<name>` partitioned by fragment hash (storage/lake.py:1-12), maintenance is scheduled.
- §26.1 Phase 6 "All ten success criteria" — there are eighteen.
- §26.3 "Each becomes a numbered ADR in docs/adr/ during Phase 0" — ADRs arrived after 0.3.0; code cites none (plan §10).
- §30 A: `feature_set_members`, `composite_members`, `subscriptions` exist in the schema but are never used (members live in the version JSON); `spec_documents`/`spec_document_versions`, `workflow_instances` do not exist; `feature_pins` has no `delta_path`.
- §2 SC-14/§24.5 three-platform parity vs ADR-014 (owner decision) — needs a revision marker, not a gap.

---
# Spec-vs-code audit: §10 to §16 (plus §30 A/B)

Spec: `docs/MAYA_Requirements_and_Design.md` rev 2.3. Branch `develop` @ b30a428. Read-only audit.
Paths are relative to `/home/ashutosh/PycharmProjects/maya`. Sizes: S (hours to a day), M (days), L (a week or more).
Importance means importance to a user.

## 1. Counts per class (174 requirements checked)

| Section | Built+tested | Built-untested | Partially built | Not built | Superseded |
|---|---|---|---|---|---|
| §10 Workflow (10.1 to 10.6) | 14 | 0 | 10 | 5 | 0 |
| §11 Authorization | 8 | 1 | 7 | 4 | 0 |
| §12 Authentication | 14 | 4 | 3 | 6 | 0 |
| §13 Architecture and §13.4 register | 11 | 2 | 4 | 4 | 1 (search, rev 2.2) |
| §14 Persistence | 10 | 1 | 2 | 0 | 1 (FTS, rev 2.2) |
| §15 Concurrency, jobs, caching | 8 | 1 | 3 | 4 | 0 |
| §16 Web UI (16 to 16.7) | 17 | 1 | 15 | 12 | 1 (table threshold, ADR-016, no spec marker) |
| **Total** | **82** | **10** | **44** | **35** | **3** |

The counts are approximate: each row of a feature table or screen inventory counts as one requirement.

**Headline:** the core engines are real and well tested: workflow-as-data, `can()` with ceiling, ACL order and conditions, SSO/MFA, API keys, the seam resolver, schema generation and the estate path, the job queue, locks and sagas, and the table macro. What is missing is mostly around them:
- the §10.3 review experience (semantic diff and impact list on the review screen);
- the §16.3 canvas interactions (overlays, filters, collapse, authoring, focus-plus-context);
- the §16.4 interaction principles (pin preview, disabled controls showing their reason, request-access);
- §11.5 access requests;
- §15 fairness, backpressure and caches;
- several §12 auth config behaviours (password history and age, concurrent sessions, reset tokens, key rate limits and rotation, client credentials).

The plan marks M5 "delivered" even though its own deliverables list includes a semantic diff per object type, the four canvas overlay modes and focus-plus-context. Neither the diff on the review screen nor the canvas features exist.

---

## 2. Not built / Partially built / Built-untested

### §10 Workflow and approval engine

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| W1 | §10.2 `approvals: [... {role: model_owner, count: 1, when: "env == 'prod'"}]` | Partial | `maya/workflow/engine.py:245-252` `_requirements` honours only the literal `when == "prod"` (namespace `production` flag); `default_policies.yaml:115` uses `"prod"` | Expression conditions. **Hazard:** any other `when` string, including the spec's own `env == 'prod'`, is silently treated as *always required*. `policy.validate` (`maya/workflow/policy.py:55-80`) does not reject an unknown `when`. | S | med |
| W2 | §10.2 `on_enter_in_review: notify(model_manager, channel: [inbox, email])` | Partial | `engine.py:296-313` writes `notifications` rows (inbox) | No email or any channel beyond the inbox. No SMTP anywhere (`grep smtp` finds nothing). | M | med |
| W3 | §10.3 "A reviewer sees a **semantic diff** against the previously approved version — schema, policy, formula, code, spec document" | Partial | Feature compare at `/catalog/features/{ns}/{name}/compare` and model diff at `/models/{ns}/{name}/diff` (`maya/web/templates/models/diff.html`) exist as separate pages | `workflow/review.html` shows no diff at all. No feature-set, parameter-set or warrant diff. No spec-document diff. | L | high |
| W4 | §10.3 "plus the impact list: every dependent feature set, warrant and model, and who owns each" | Not built (on review) | Workspace impact only (`maya/web/routes/workspaces.py:44`); the lineage canvas separately | No impact list on the review screen, and owners are not shown anywhere | M | high |
| W5 | §10.3 "Reviewers can comment inline on any element" | Partial | `comments.anchor` column; `workflow_service.comment(anchor=...)` | UI (`_history.html`) offers only a whole-object comment. Nothing lets a reviewer anchor a comment to an element. | M | med |
| W6 | §10.4 break-glass "notifies the model owner **and a configured distribution list** immediately" | Not built | Owner is notified (`engine.py:299-300`) | No distribution-list setting and no delivery to one | S | med |
| W7 | §10.4 break-glass report "reviewed monthly" | Partial | `/workflow/break-glass` (last N days) | No review or sign-off record. The report is also visible to **every** signed-in user (see C1). | S | low |
| W8 | §10.5 campaigns: "pin these forty features as of 31 March… **one approval covering the campaign**" | Partial | `workflow_service.run_campaign` loops `dispatch_transition` per item; per-item status and one audit row are tested (`test_campaign_reports_per_item`) | No campaign-level approval. Pin campaigns are impossible (transitions only). No "every model touching a changed feature" selector. The UI (`workflow/campaigns.html`) only lists items `in_review`, so its publish and deprecate options can never apply. | M | med |
| W9 | §10.6 diagram shows "how long they have been there, and which transitions are currently blocked and by which check" | Not built | `policy.js` draws states with counts only | Time-in-state and blocked-by-check overlays | M | med |
| W10 | §10.6 "A reviewer sees the policy… including which SoD strictness is in force and which approvals are still outstanding and from whom" | Partial | `review.html` lists the available transitions with their approval and check requirements | No SoD level and no outstanding-approvals list. **Bug:** `web/routes/workflow.py:46-47` picks the first active policy of the type **regardless of scope**, so a namespace-scoped policy may be shown wrongly. Plan M5 exit criterion "configuration visible on the review screen" is not met. | S | high |
| W11 | §10.6 "edited as structured controls with validation as you type" | Partial | `maya/web/static/js/policy.js`: states, transitions, roles, checks and approvals are structured | SLA and notification routing are a raw JSON textarea (`policy.js:143-147`). Validation runs on a button press, not as you type. | S | low |
| W12 | §10.6 "a transition with no approver who could ever satisfy it" refused | Partial | `policy.py:70-73` refuses an approval role that does not exist | Does not check that any user or group actually holds the role | S | low |
| W13 | §10.6 preview: *"this would block 14 objects currently in review"*; plan M5 exit: "A policy edit that would strand objects is **refused** at edit time, naming the count and the objects" | Partial | `workflow_service.preview` reports stranded and no-exit states; tested via `population` | Does not evaluate checks or approvals against in-flight items. Stranding is **reported, not refused** (`draft_policy` refuses only on `validate` errors). Objects are not named. | M | med |
| W14 | §10.6 policy edit "drafted, **diffed against the active version**, approved…" | Not built | Draft, second-admin activation and retention are built and tested | No diff between draft and active policy | S | med |
| W15 | §10.6 plan M5 deliverable "Semantic diff per object type" | Not built | see W3 | see W3 | L | high |

### §11 Authorization

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| A1 | §11 "Nothing in the UI, API, SDK or CLI bypasses [can()]" | Partial (contradiction) | `can()` guards objects everywhere else | `GET /workflow/queue`, `/workflow/aging` and `/workflow/break-glass` (`maya/api/routers/workflow.py:20-32`) and the campaigns page return **every in-review object ref in every namespace** to any authenticated user. `WorkflowService.queue` (`maya/services/workflow_service.py:171-192`) does no read check (the docstring says "that this user could act on"). This leaks the names of objects in private namespaces. | S | high |
| A2 | §11 "the decision — allow or deny, and the rule that decided — is logged for sensitive actions" | Partial | Denials of approve/pin/seal/grant/revoke are audited durably (`maya/services/access.py:72-75`) | Allows are not logged with their deciding rule | S | low |
| A3 | §11.1 namespace default `private` \| `namespace_read` \| `public_read` | Partial | `authz.py:162-170` | `namespace_read` and `public_read` behave identically. There is no namespace-membership concept, so "namespace read" means read by everyone. | S | med |
| A4 | §11.1 "retired objects are readable only with an explicit audit grant" | Not built | `FROZEN_STATES={"sealed","retired"}` blocks writes only (`authz.py:46,108`) | Retired objects stay readable by anyone who could read before. No "audit" grant type. | S | med |
| A5 | §11.2 inert grant "the UI says so when it is created" | Built-untested | `inert_grant_reason` (`authz.py:189`), stored in `grants.inert_reason` and shown in `admin/grants.html:14` | No test references `inert` | S | low |
| A6 | §11.3 "unless a pin carries its own tighter grant" | Not built | Grants apply to features, feature sets, models, warrants and namespaces only (`access.py:19-24 KINDS`) | Pin-level grants | M | med |
| A7 | §11.5 "Groups are managed locally or mapped from SSO claims" | Partial | Local groups; SSO `group_role_map` maps claims to **roles** | SSO groups are not synced into MAYA groups, so group grants cannot target IdP groups | S | low |
| A8 | §11.5 "Service accounts are principals with roles and grants, no interactive login, and mandatory credential expiry" | Partial | `users.is_service` blocks password login (`maya/services/auth.py:84`) | API keys are issued only by the caller for itself (`auth.create_api_key(p, …)`), so a service account can never obtain a credential. No OAuth2 client credentials (see K8). | M | med |
| A9 | §11.5 "Access requests are a workflow: a user clicks *request access*, the owner receives an approval item" | Not built | 90-day default grant expiry (`access.py:217`) | No request-access action, item or approval; `grep request_access` finds nothing | M | high |
| A10 | §11.5 "time-boxed… with a renewal reminder" | Not built | Expiry is evaluated lazily (`authz._live`) | No reminder sweep | S | med |
| A11 | §11.5 "Every grant, change and expiry is an audit event" | Partial | Grant and revoke are audited | Expiry is never recorded as an event | S | low |
| A12 | §11.5 "each owner receives a quarterly access recertification list… letting them revoke in bulk" | Partial, untested | `access.recertification` and `admin/grants.html:33-37` | No bulk revoke (per-row only), no quarterly prompt or notification, no test (`grep recertification tests` finds nothing) | S | med |

### §12 Authentication

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| K1 | `password_policy: {require_classes: 3, history: 5, max_age_days: 90}` | Partial | `auth.check_policy` min_length (config) and a hard-coded 3 classes (`auth.py:274-280`) | No password history, no max age or expiry, `require_classes` not configurable | S | med |
| K2 | `session: {concurrent_sessions: 3}` | Not built | idle and absolute timeouts exist (`auth.py:47-48,202`) | No concurrent-session cap | S | med |
| K3 | idle and absolute session timeouts | Built-untested | `auth._resolve_session` | No test found for expiry | S | med |
| K4 | "In any deployment where `environment != dev`, MAYA refuses to start with the default password unless `allow_default_admin_password`" | Built-untested | `maya/services/platform.py:136-140` (key is `app.allow_default_admin_password`) | No test of the refusal | S | med |
| K5 | "Password reset uses single-use, time-limited tokens" | Not built | Admin reset with `must_change_password` (`access.py:356-366`) | Self-service reset tokens | M | med |
| K6 | API key "optional CIDR allowlist" | Built-untested | `auth.py:228,366-371` | No test (`grep cidr tests` finds nothing) | S | low |
| K7 | API key "its own rate-limit budget" | Not built | none (no rate limiter anywhere; `QuotaExceeded` is used only for warrant limits) | per-key budget | M | med |
| K8 | "OAuth2 client credentials" for service principals | Not built | none | client-credentials grant | M | med |
| K9 | "keys unused for a configurable period are reported for revocation" | Not built | `last_used_at` is tracked | report | S | low |
| K10 | "rotation reminder"; "Creating, **rotating**, scoping and revoking keys is itself an SDK capability" | Not built (rotation) | create, list, revoke in SDK (`maya/sdk/resources.py:186`) | rotate endpoint, reminder | S | med |
| K11 | "mandatory expiry no further out than the namespace policy permits" | Partial | Global `auth.api_keys.max_days` (`auth.py:311`) | Per-namespace maximum | S | low |
| K12 | Admin "list and terminate sessions" | Built-untested (functionally) | `auth.list_sessions` and `terminate_session`; `/admin/sessions/{id}/end` | Only the authz contract test touches the route; no behavioural test that a terminated session is dead | S | med |
| K13 | "IdP unreachable → existing sessions continue, new logins fail **with a break-glass path for administrators**" (§13.3) | Partial | `hybrid` mode keeps DB login | In `mode: sso`, `_precheck` refuses **all** password logins (`auth.py:79-82`), admins included, so there is no break-glass path. See C4. | S | med |
| K14 | Refusal at start for SAML without `xmlsec` | Built+tested | — | — | — | — |

### §13 Architecture and §13.4 register

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| R1 | §13.1 Compute: "Apache Arrow + Polars for in-process resolution; DuckDB for pushdown SQL over Parquet/Delta" | Not built (contradiction) | Resolution is pandas throughout (`maya/resolution/*.py`, `feature_data.py:329` records `pandas` version). `frames` (polars) and `pushdown` (duckdb) seams are resolved and reported but **never consumed** (`grep Backends.selected` finds no frames or pushdown). | Polars/DuckDB paths, or a revision marker | L | low |
| R2 | §13.4.2 `maya/core/frames` fallback "Arrow compute kernels via `pyarrow`" | Contradiction | `maya/core/backends.py:88` declares fallback `pandas` | Align spec or code | S | low |
| R3 | §13.4.2 `maya/storage/blob`: "S3 / Azure Blob / GCS" preferred | Not built | `LocalBlobStore` only (`maya/storage/blobs.py:25`); seam `blob` is hard-wired `local` | Object-store backends | L | med |
| R4 | §13.4.2 `maya/jobs/queue`: "Redis driver"; §13.1 "Redis/Celery is a pluggable driver"; §13.1 "APScheduler for cron" | Not built / contradiction | DB queue (`maya/jobs/queue.py`); own interval `Scheduler` (`maya/jobs/scheduler.py`) | Redis driver; APScheduler not used | M | low |
| R5 | §13.4.3 rule 6 "A Type A seam's suite runs twice" | Not built (except `maya_delta`) | maya_delta conformance on both backends | Fallback matrix (gate 11b), which the README admits | M | low |
| R6 | §13.4.3 rule 1 "One resolver… no second place a backend can be chosen" | Partial | `backends.py` covers 19 seams | `security/sandbox` and `security/sso` from the register are resolved elsewhere (`sandbox_tier()`, `sso.check_startup`), not in the resolver. `procstat` fallback is `os`, not the spec's `/proc`/`sysctl`/Job Objects. `calendars` has no optional-library path. | S | low |
| R7 | §13.2 "Uploads stream to the object store, are scanned and hashed… never buffered whole in memory" | Partial | `LocalBlobStore.put_stream` exists | API handlers do `data = await file.read()` (`maya/api/routers/catalog.py:62,69,102`, `registry.py:76,87`, `admin.py:362`; web `workbench.py:231`). No scanning. | M | med |
| R8 | §13.2 "Resolution (preview, download, pin)… runs in a worker with progress streamed" | Partial | Pins are jobs | Preview and download run synchronously in the request threadpool (`catalog.py:192-205`) | M | low |
| R9 | §13.3 "a worker dies mid-pin → … the job is retried idempotently" | Built-untested | `JobQueue.reap` (`queue.py:234-241`), called at primary start | No test of `reap`. It requeues **all** `running` jobs at startup, which is safe only while jobs run only in the primary. | S | med |
| R10 | §13.3 object-store-down / Delta-down named degradations | Built-untested | Behaviour is plausible from the code; no test simulates either outage | tests | S | low |
| R11 | §13.4.3 labelled typesetting fallback | Built+tested | `models.py:465-477 check_true_build` | — | — | — |

### §14 Persistence

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| P1 | §14.2 "Optimistic concurrency via a `row_version` column on every mutable aggregate, so two users editing one draft produce a clear conflict" | Partial | Column on every table (`models/base.py:45`); `Repository.update(expected_version=)` (`repositories/base.py:193-208`) | Only the web feature-draft edit passes it (`web/routes/workbench.py:190`); tested only there (`test_web_workbench.py:45-52`). Feature-set drafts, model drafts and all API/SDK draft updates are last-writer-wins. | S | med |
| P2 | §14.2 "Audit **and lineage** tables are append-only, enforced by a database rule" | Partial | Triggers on `audit_events` only (`maya/persistence/schema.py:35-44`) | `lineage_edges`, `workflow_events` and `approvals` have no rule | S | low |
| P3 | §14.1 "SQLite… MAYA says so plainly in the UI, including its concurrency ceiling" | Built-untested | `base.html:25-27` banner | No test asserts the banner | S | low |

### §15 Concurrency, jobs, caching

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| J1 | §15.1 "Pin materialization, exports, LaTeX, integrity scans → background jobs on **worker processes**"; §13 "separate API and worker fleets under load" | Partial | Jobs run on threads inside the primary web process (`queue.py:216-224`, `platform.py:83-88`) | No worker-process mode or separate worker fleet | M | med |
| J2 | §15.1 "per-user concurrent jobs, per-namespace concurrent resolutions, resolution thread pool… No unbounded pool exists" | Not built | `jobs.workers`, DB pool size and overflow, `server.workers` | The per-user and per-namespace caps and a resolution pool | M | med |
| J3 | §15.2 "**fair** — a per-user concurrency cap and a weighted queue so one person's fifty-feature campaign cannot starve everyone else" | Not built | `claim_next` is strict FIFO by `created_at` (`repositories/special.py:75-90`) | fairness | M | high |
| J4 | §15.2 "**retryable** — exponential backoff with jitter, capped attempts, then a dead-letter state" | Built-untested | `queue.py:180-189` | No job-retry or dead-letter test (only webhooks' is tested) | S | med |
| J5 | §15.4 "Three caches: authorization decisions…, metadata reads (invalidated by `row_version`), resolved plans keyed by definition hash. Pin data… cacheable forever" | Partial | 2-second principal cache (`auth.py:43`), API-key secret cache | No metadata cache, no resolved-plan cache, no pin-data cache | M | low |
| J6 | §15.4 backpressure: queue-depth or memory shedding, "honest wait estimate", per-job memory estimate rejected up front | Not built | nothing (`grep backpressure/shed/estimate` finds nothing) | all of it | L | med |
| J7 | §15.2 "Users see their jobs in a live panel" | Partial | `/admin/jobs` and `_job.html` poll `/ui/jobs/{id}` every 700 ms (`static/js/app.js:133-154`) | Not SSE (see U2) | S | low |
| J8 | §16.4 "the user can navigate away and be notified on completion" | Not built | Notifications exist for workflow, covenants, expiry and similar | No notification on job completion or failure | S | med |

### §16 Web UI

| # | Spec | Class | What exists | What is missing | Size | Imp. |
|---|---|---|---|---|---|---|
| U1 | §16.1 "global command palette (`⌘K`) that searches every object by name, tag, owner and lineage" | Partial | Ctrl/⌘-K focuses the nav search box (`app.js:92-93`); the index covers name, tag, namespace and description (`search_index.py:32`) | No palette overlay with live results; no owner or lineage search | M | med |
| U2 | §16 "SSE for live progress… the route proxies that stream to the browser over SSE" | Partial | API `/jobs/{id}/events` SSE (`api/routers/admin.py:340-356`) | UI polls instead | S | low |
| U3 | §16.1 "Every object page has the same five-tab shape" | Partial | Feature, feature set, model and training warrant use `tabs()` | The execution warrant page has no tabs. Others add extra tabs (acceptable). | S | low |
| U4 | §16.2 Catalog "faceted filters (namespace, type, owner, status, tag, freshness)" | Partial | Namespace select only (`catalog/features.html:10`) | type, owner, status, tag and freshness facets | M | high |
| U5 | §16.2 Catalog "pin browser" | Partial | Per-object Pins tab | No catalog-wide pin browser | S | low |
| U6 | §16.2 Catalog "comparison view" | Partial | Feature version compare only | Feature set and model comparison views (model diff is separate) | S | low |
| U7 | §16.2 Workbench "feature set builder (**drag** members…)" | Partial | Form-based builder (`workbench/fs_builder.html`) | Drag interaction | S | low |
| U8 | §16.2 Workbench "upload wizard with schema inference **and cast-failure preview**"; §16.4 "Changing a data type shows how many rows would fail" | Not built (UI) | `features.cast_preview` service (`maya/services/features.py:238-242`) and `resolution.types.cast_preview` (tested in `test_resolution_core.py:141`) | Not exposed by the API, SDK or UI (`grep cast_preview maya/web maya/sdk maya/api` finds nothing) | S | med |
| U9 | §16.2 Admin "SSO config" | Partial | Read-only effective config and the SAML SP metadata download (`admin/config.html`) | No SSO config screen | M | low |
| U10 | §16.2 Admin "feature flags" | Not built | none | screen and flags | M | low |
| U11 | §16.2 Admin "namespaces **and quotas**" | Not built (quota) | `namespaces.quota_bytes` is stored and editable (`access.py:130-158`) | **Never enforced**: no code reads it to refuse a pin or upload. A config value that is parsed but not acted on. | S | med |
| U12 | §16.2 Warrants "execution manifest preview" | Partial | Manifest shown on the issued warrant (`warrants/execution.html:25`) | No preview before issuing | S | low |
| U13 | §16.3 edge `extends` "with the override count on the label"; `operand_of` "numbered where order matters" | Partial | Edge styles per type (`static/js/lineage.js:48-58`); operand label passes through if present | No override count | S | low |
| U14 | §16.3 "Collapse an inheritance chain to a single node with a depth badge, then expand it" | Not built | — | — | M | med |
| U15 | §16.3 "Filter by object type, namespace, status or pinned-only" | Not built | Only direction and depth selectors (`lineage.html`) | — | S | med |
| U16 | §16.3 "Hover an operator node to see its typing rules and collision policy; hover an `extends` edge to see the override diff" | Not built | — | — | M | low |
| U17 | §16.3 overlays: freshness, approval status, access, cost | Not built | — | all four (plan M5 lists "four overlay modes" as delivered) | M | med |
| U18 | §16.3 "Selecting two features and choosing an operator opens the definition editor prefilled"; "Selecting a subtree offers cascade pin" | Not built | Click only re-roots (`lineage.js:61-66`) | canvas authoring and cascade pin | M | med |
| U19 | §16.3 "A change in review renders as an overlay — added green, changed amber, removed struck through" | Not built | — | — | M | med |
| U20 | §16.3 "beyond ~300 visible nodes switch to a focus-plus-context layout… namespace clusters with counts" | Not built | Only a status message "large graph: narrow the depth" (`lineage.js:40`) | clustering | M | low |
| U21 | §16.3 canvas itself (Cytoscape, operator diamonds, typed edges, click to re-root, direction toggle) | Built-untested (client) | Lineage data tested (`test_features.py:204`); page render tested (`test_web.py:163`) | The Cytoscape rendering is not exercised in the headless-browser tests | S | low |
| U22 | §16.4 "Pinning shows row counts, fill report, storage estimate and cost **before the button becomes active**" | Not built | The pin form is a plain submit (`catalog/feature.html:70-81`); preview is a separate workbench page | pre-pin preview and gating | M | high |
| U23 | §16.4 "Sealing shows exactly what becomes immutable" | Partial | Generic `data-confirm="Seal? The warrant becomes immutable."` (`warrants/training.html:22`) | an itemised preview | S | low |
| U24 | §16.4 "Controls the user cannot use are shown disabled with the reason and a *request access* action, rather than hidden" | Not built (contradicted) | Templates **hide** controls: `{% if f.can_pin %}`, `p.can_retire` and similar (`catalog/feature.html:70`, `_rows.html:44`) | disabled-with-reason and request-access (see A9) | M | high |
| U25 | §16.4 "Dependent objects and their owners are one click away from any definition change" | Partial | Lineage tab (downstream) on object pages | Owners not shown; no dependents panel in the designer or review | S | med |
| U26 | §16.5 "Tables support keyboard paging and column-level sort **and filter**" | Partial | Keyboard sort and paging (`table.js:110-121`); global search | Per-column filter | S | low |
| U27 | §16.7 "the choice remembered **per table per user**" | Partial | `localStorage` per browser (`table.js:29-30`) | per-user (server-side) memory | S | low |
| U28 | §16.7 "CSV **and Arrow** export of the current view" | Partial | CSV export (`table.js:338-355`) | Arrow export | S | low |
| U29 | §16.7 "Beyond a configurable threshold the macro switches… to cursor pagination"; multi-column sort "applied to the whole result set" | Superseded (ADR-016; README "Not yet") | Server mode is per list, single-key sort on the server's sortable columns | Spec §16.7 carries no revision marker (see C9) | — | low |

---

## 3. Spec statements that contradict the code or other spec sections (candidates for revision markers)

- **C1 (§11 vs code: security).** "Nothing… bypasses `can()`." The workflow queue, aging and break-glass endpoints expose every in-review object ref and every forced approval to any authenticated user (`maya/api/routers/workflow.py:20-32`, `maya/services/workflow_service.py:171-192`). Fix the code, not the spec.
- **C2 (§10.2 example vs engine).** The spec's `when: "env == 'prod'"` is not supported. The engine treats any `when` other than `"prod"` as unconditional, and the validator accepts it. Either document the `"prod"` literal in §10.2 or implement expressions and validate them.
- **C3 (§13.1 and §15.1 vs code).** "Arrow + Polars in-process; DuckDB pushdown" and "Arrow/Polars/DuckDB kernels, multi-threaded in native code". Resolution is pandas. The `frames` and `pushdown` seams are reported on health, in `/readyz` and in provenance but select nothing, so provenance records a `polars`/`duckdb` choice that never ran. Needs a revision marker, or wire the seams.
- **C4 (§13.4.2 frames row vs code).** Spec fallback "Arrow compute kernels via pyarrow"; code fallback `pandas` (`maya/core/backends.py:88`).
- **C5 (§13.3 vs §12).** §13.3 says IdP unreachable leaves "a break-glass path for administrators". §12 says SSO failures never fall back to DB login unless `mode: hybrid`, and the code refuses all password logins in `sso` mode. Under `mode: sso` there is no break-glass path. One of the two needs a revision.
- **C6 (§13.1 vs code).** "APScheduler for cron" and "Redis/Celery is a pluggable driver". The code has its own `Scheduler` and no Redis driver. The §13.4.2 queue row also lists a Redis driver.
- **C7 (§14 package layout vs code).** The listed `mappers/`, `locks.py` and `persistence/seed.py` do not exist. Locks live in `session.py:103`, seeding in `maya/services/seed.py`, and repositories return dicts rather than domain entities. §14 also says repositories expose "intention-revealing methods… not a generic query builder", but `repositories/base.py` is a generic filter DSL (`list(**filters)` with `__ge`, `__in`, `__isnull`). Revise the prose.
- **C8 (§15.1 vs code).** "Background jobs on worker processes": jobs are threads in the primary web process. §13's "separate API and worker fleets" deployment does not exist.
- **C9 (§16.7 vs ADR-016 and README).** Threshold-switched server paging and multi-column whole-set sort are superseded in practice (server paging per list, one sort key) by ADR-016 and the README "Not yet". §16.7 has no *Revision* marker saying so.
- **C10 (§16.4 vs templates).** "shown disabled with the reason… rather than hidden". Templates hide unavailable actions. Either implement it or revise.
- **C11 (§11.1 vs code).** `namespace_read` is indistinguishable from `public_read` because namespaces have no members. Spec wording implies a narrower audience.
- **C12 (plan M5 status vs code).** `docs/IMPLEMENTATION_PLAN.md` M5 says "delivered", but its deliverables include a semantic diff per object type, "four overlay modes, focus-plus-context beyond ~300 nodes" and a diffed policy. Its exit criteria include "strand… refused at edit time, naming the count and the objects" and "configuration visible on the review screen". None of these is built (W3, W10, W13, W14, U17, U20). The M5 status note should list them as not delivered.
- **C13 (Appendix A vs schema).** The `spec_documents` and `spec_document_versions` tables do not exist: the spec document lives in `model_versions` columns. `workflow_instances` is realised as `workflow_events` plus `approvals`. The outline should say so.
- **C14 (Appendix B vs code, minor).** `own` → Approve is "policy" in Appendix B; `LEVEL_ALLOWS["own"]` grants `approve` outright, limited only by the role ceiling and SoD. Also, in a non-private namespace, review actions (approve, pin, seal) are allowed by role capability alone with no grant (`authz.py:163-168`). That is a deliberate rule not stated in §11.2 or Appendix B.
- **C15 (stale comment).** `maya/web/static/css/tokens.css:38` says "spec §16.6 says #A51C30". The spec (rev 2.2) now says `#E07A8E`.
- **C16 (§14.1 `NUMERIC(38,12)` type name).** Implemented as `Money` (`maya/persistence/types.py:70`). Fine; noted only because the spec says "`decimal` mapped to…".

---

## 4. Built+tested (one line each)

§10:
- Policy-as-data engine (`maya/workflow/engine.py`, `policy.py`).
- Canonical states on all six object types.
- Namespace-scoped policies (`test_a_namespace_policy_sets_its_own_review_deadline`).
- Named checks that block and name themselves.
- `{role, count}` approvals accumulate across rounds.
- SoD at three strictness levels (`test_separation_of_duties_by_preset`).
- SLA in review.
- Blocking comments block approval.
- Delegation with a date range, logged, `on_behalf_of` on the approval (`test_delegation.py`).
- Escalation to the namespace owner, once (`test_overdue_items_escalate_once`).
- Aging report.
- Break-glass: admin only, written reason, permanent `force_approved`, owner notified, report (`test_break_glass_is_loud_and_permanent`).
- Campaign per-item status, partial failure and one audit row.
- Instance history view; edit-time validation (unknown state, check or role, unreachable state, unapprovable); policy versioned with second-admin activation and old version retained; YAML byte-identical round trip both ways.

§11:
- `can()` role ceiling (`test_role_ceiling_is_never_exceeded`).
- ACL resolution order (`test_acl_resolution_order`, `test_authz_matrix.py`).
- Grant levels, expiry and deny.
- Sealed and retired objects refuse writes.
- Version access follows the governing object.
- Feature-set partial view with withheld attributes named (`test_featureset_proofs.py:130`).
- Row filter, column mask and time bound (`test_conditions.py`).
- API key role subset no wider than the holder (`test_api_key_scope_never_widens`).

§12:
- One `auth.mode` switch: db, sso, hybrid (`test_hybrid_keeps_password_login_and_sso_mode_refuses_it`).
- OIDC code flow with PKCE, ID-token checks.
- SAML signed assertions, signed requests, SLO both ways; OIDC logout both ways.
- SAML-without-xmlsec startup refusal.
- JIT provisioning and group→role remap at each login; unmapped groups denied.
- Lockout.
- MFA: TOTP, WebAuthn, role-required enrollment.
- Bootstrap admin with `must_change_password` and warnings in the banner, health page and startup log.
- Argon2id/scrypt/PBKDF2 recorded per hash, rehash upward.
- API key format with env segment, hashed, shown once, namespace and action scope, expiry, immediate revocation (`test_api_key_scope_environment_and_revocation`).
- Principal cache window (`test_principal_cache.py`).
- CSRF (`test_csrf_is_required`).
- Auth events audited.

§13:
- UI → SDK only, enforced by a gate (`test_web_imports_only_the_sdk`, planted violation).
- Persistence import boundary.
- One seam resolver reported in the banner, health page and `/readyz`.
- Fallbacks logged.
- Seams pinnable by `seams.<name>`.
- Backend set written into pin, warrant and bundle provenance.
- Type B canonical and chunker byte-fixed (`test_foundation.py`, `test_canonical_fast.py`).
- maya_delta conformance on both backends.
- KDF seam recorded; crypto refuses rather than downgrading.
- Typeset draft render watermarked and refused for approval.
- Observability: Prometheus, OTel spans, trace id from request to audit row to job.

§14:
- `sqlalchemy` confined to `maya/persistence` by a gate.
- Unit of work.
- Portable JSON, UUID, UTC and Money types (`test_postgres_ddl_uses_native_types`, PG runs).
- SQLite WAL, busy_timeout and write mutex.
- SQLite refuses `server.workers > 1` (`test_sqlite_refuses_several_web_processes`).
- `created_*` and `updated_*` columns.
- Audit append-only triggers and hash chain with tamper detection.
- Two generated DDL files and drift gate (`test_shipped_schema_files_match_the_metadata`, `test_hand_edit_is_detected`).
- Schema-hash refusal at startup (`test_schema_mismatch_refuses_to_start`).
- Estate export, `init-db --force`, import via the CLI, including reading a foreign-schema DB (rev 2.3).

§15:
- Multiple uvicorn web processes over PG (`test_web_processes.py`).
- PG `SKIP LOCKED` / SQLite in-process queue.
- Job record fields and states.
- Idempotency key dedupe, including under concurrency (`test_concurrency.py:117-133`).
- Cooperative cancellation with cleanup (`test_a_cascade_cancelled_mid_job_rolls_back…`).
- Trace id per job.
- Named advisory locks with sorted-order cascade.
- Pin saga with nothing visible before the metadata commit (`test_concurrency.py`).

§16:
- Jinja, vendored Bootstrap/jQuery/Cytoscape/KaTeX/CodeMirror, no build step, CSP with no inline script.
- Six-area mega-menu with icon and description per entry (`test_the_mega_menu_opens_on_hover_and_navigates`).
- Feature, feature-set, model and training-warrant object pages with the tab shape.
- Feature designer with preview and fill report.
- Upload wizard with schema inference.
- Download dialog with format and CSV array encoding.
- Model editor with LaTeX, formula, Python and parameters; spec PDF export; model diff viewer.
- Warrant wizards with contract validation; warrant detail with custody; parameter upload with metrics.
- Workflow: queue, review, campaigns, delegations, aging, break-glass pages.
- Admin: users, roles, groups, sessions, namespaces, grants, sources, storage, jobs, audit, health, config, custody, events, webhooks.
- Tokens exactly as the §16.6 table (light and dark), Bootstrap re-pointed, contrast gate.
- Status pills with glyph and word; live regions for job progress; phone and responsive layout (`test_the_phone_layout_collapses…`).
- Table macro: 25/50/100/250/All, "showing x–y of N", debounced search with highlight and removed count, shift multi-sort (client), column hide, CSV export, keyboard sort and paging, empty state.
- SC-17 table-contract gate with a planted-violation test.

---
# MAYA spec §17–§25 vs code — read-only audit

Spec: `docs/MAYA_Requirements_and_Design.md` rev 2.3. Branch `develop` @ b30a428. **The working
tree had uncommitted changes from another session while I audited** (`maya/sdk/resources.py`,
`maya/cli/__main__.py`, `maya/services/access.py` and others: a new feature-pins paging endpoint, CLI
`--allow-drop`, CLI `--local` starting job workers only). None of them change a verdict below, but
some line numbers in `access.py` may move.
Out of scope by owner decision, and not counted: Windows/macOS support and CI (and so the macOS/Windows
sandbox rows of §17.2 and SC-14), live Claude API, a dedicated benchmark host (SC-3 verdict),
SC-9, and the external security review.

Tags: **BT** Built+tested · **BU** Built-untested · **PB** Partially built · **NB** Not built ·
**DS** Deliberately superseded (a revision marker or an ADR says so).

## 1. Counts

| Class | Count |
|---|---|
| Built+tested (BT) | 68 (§4 bullets; several bullets group closely related clauses) |
| Built-untested (BU) | 13 |
| Partially built (PB) | 57 |
| Not built (NB) | 38 |
| Deliberately superseded (DS) | 5 |
| **Total requirements classified** | **181** (plus 15 spec contradictions in §3) |

The largest gaps are in three places. **§18.2 SDK ergonomics and network features**: no handles,
no typed models, no cache, no presigned or resumable downloads, no ETag, and the literal §18.2.4
sample does not run. **§21 operational security controls**: no rate limits, no export quotas, no
upload expansion limits, and namespace classification is stored but drives nothing. **§25
extensibility**: no plugin framework. The workflow, warrant, bundle, audit and sandbox core is
solid and well tested.

---

## 2. Gaps (NB / PB / BU)

Size: S (< 1 day), M (days), L (a week or more). Imp = importance to a user.

### §17 Embedded editors

| # | Spec (quote) | Class | What exists | What is missing | Size | Imp |
|---|---|---|---|---|---|---|
| 17-1 | §17.1 "A model version cannot reach `approved` on a draft render" | BU | `maya/services/models.py:466-477` `check_true_build` refuses a draft outside dev | Only the positive case is tested (`tests/test_typeset.py:65`). No test that a draft is refused when `typeset.require_true_build` holds or outside dev | S | med |
| 17-2 | §17.1 draft "refuses it anywhere the PDF is evidence: … an execution manifest, an export bundle" | PB | The bundle carries `model/spec.tex`, never a PDF (`maya/services/bundle.py:239`) | No explicit refusal anywhere. It holds only because the PDF is never included. The spec should say so | S | low |
| 17-3 | §17.1 "a section outline with completeness indicators" | PB | Completeness pills (`maya/web/templates/models/model.html:82`); `specdoc.outline()` (`maya/formula/specdoc.py:83`) | `outline()` is never called: no navigable outline pane | S | low |
| 17-4 | §17.1 "figure and table upload; BibTeX bibliography; spell check; find and replace" | NB | CodeMirror 5 core plus python/stex modes only (`maya/web/static/vendor/codemirror/`) | All four. No search addon, so find and replace is the browser's own. No `\includegraphics` asset path, no `.bib` handling, no spell check | M | med |
| 17-5 | §17.1 "full version history with side-by-side diff" (of the document) | PB | Model diff returns `spec_changed: bool` (`maya/services/models.py:~499`) | No text diff of `spec_latex` between versions | S | med |
| 17-6 | §17.1 "comments anchored to line ranges" | PB | Workflow comments take a free-text `anchor` (`maya/services/workflow_service.py:207`) | No line-range anchoring or display in the editor | M | low |
| 17-7 | §17.1 "Compilation is capped (time, memory, output size), runs with no network and no shell escape" | PB | Timeout and `--untrusted` (`maya/core/typeset.py:71-88`) | No memory or output-size cap. Tectonic is not network-isolated, and it downloads its bundle on first use (README says so) | S | med |
| 17-8 | §17.1 live preview "within ~200 ms" | BU | `maya/web/static/js/editors.js` (180 ms debounce, KaTeX) | No browser test exercises the preview | S | low |
| 17-9 | §17.2 "bracket matching, multi-file tabs" | PB | `editors.js:74` sets `matchBrackets: true` | **The matchbrackets addon is not vendored**, so the option is silently ignored (`codemirror.js` has no `matchBrackets`). The file's header comment claims bracket matching. No multi-file tabs | S | low |
| 17-10 | §17.2 "language intelligence through a pinned Pyright/LSP worker … against MAYA's own stub package" | NB | — | No LSP worker, no completion, no hover, no inline diagnostics, no stub package | L | med |
| 17-11 | §17.2 rung 1 "Parse and lint (`ruff`), with a MAYA rule set" | PB | `maya/formula/artifact.py:48-70` runs `ruff --select E9,F` | Only F821/E9 fail the rung. The rung passes silently when ruff is absent (it records "not run"). No MAYA rule set | S | low |
| 17-12 | §17.2 rung 3 "the list is administrator-configurable per namespace" | PB | Fixed `DEFAULT_ALLOWLIST` (`artifact.py:30`); `validate_artifact(..., allowlist=None)` | No setting or namespace field feeds it. `models.py:336` never passes one | S | med |
| 17-13 | §17.2 tier "recorded on every validation report **and every warrant that depended on one**" | PB | On the report (`models.py:343`); on the metric and health page | Training and execution warrants do not record the tier of the artifact they depend on | S | med |
| 17-14 | §17.2 "MAYA **refuses to start** in a non-dev environment at a tier below the configured minimum" | BU | `maya/services/platform.py:127-134` (`sandbox.min_tier`) | No test of the refusal | S | med |
| 17-15 | §17.3 one grammar for "feature transforms, feature set filters, ACL row filters, workflow check conditions" | PB | `maya/resolution/expr.py` used by transforms, featureset, algebra, conditions and catalog | Workflow check conditions are named Python checks, not expressions | S | low |
| 17-16 | §17.3 expression editor "with autocomplete over available attributes, inline type checking, and a live three-row result preview" | NB | Plain `<input>` fields (`workbench/fs_builder.html:56`, `admin/grants.html:27`) | The whole editor | M | med |

### §18.1 REST API

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 18.1-1 | Endpoint table (`…/versions/{v}:resolve -> job`, `…/pins/{pin}/data`, `featuresets/{id}/pins:cascade`, `warrants/{id}:seal`) | PB | Equivalent functions at other paths: `/features/{ns}/{name}/pins`, `/feature-data?ref=`, `cascade` flag, `/warrants/training/{id}/seal` (`maya/api/routers/`) | No resolve-as-a-job endpoint (draft-preview is synchronous). The spec table describes URLs that do not exist, so it needs a revision marker | S (docs) | low |
| 18.1-2 | "`If-Match`/`ETag` optimistic concurrency on mutations" | NB | No ETag or If-Match anywhere in `maya/` | All of it. `ConflictError` exists but is never raised from an ETag | M | med |
| 18.1-3 | "idempotency keys on every POST that creates work" | PB | Only `POST …/pins` for features and feature sets (`maya/api/routers/catalog.py:163,250`); the queue dedupes (`maya/jobs/queue.py:97-113`) | Artifact upload (a validation job), warrant creation, bundle export, integrity and other job-creating POSTs | S | med |
| 18.1-4 | "Data endpoints stream Arrow IPC by default and negotiate … through `Accept`" | PB | `format=` query parameter (arrow, parquet, json, ndjson, csv); **default parquet** | No `Accept` negotiation. Default is not Arrow | S | low |
| 18.1-5 | "Rate limits are per principal and per namespace, with headers stating the remaining budget" | NB | Only warrant daily quotas (`maya/services/execution.py:257`) | No API rate limiting at all. §24.4 ("keep one grid job from starving interactive users") depends on it | M | **high** |
| 18.1-6 | SSE on `/jobs/{id}/events` and `/events/stream` | BU | `maya/api/routers/admin.py:339`, `events.py:32` | Stream content never tested (only the anonymous refusal, `tests/test_api_contract.py:111`) | S | low |

### §18.2 Python SDK

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 18.2-1 | §18.2.1(2) "Request and response models are Pydantic classes generated from the same OpenAPI document" | NB | Methods return plain `dict` (`maya/sdk/resources.py`) | Generated models and the `generated/` package | L | med |
| 18.2-2 | §18.2.1(3) "a small hand-written layer … provides the handles and verbs people actually want (`feature.pin(...)`, `warrant.data(...)`)" | NB | Flat resource methods only | `FeatureHandle`, `PinHandle`, `WarrantHandle`, `JobHandle` (no `handles.py`) | M | **high** |
| 18.2-3 | §18.2.2 "OIDC device flow … an active device-flow token in the local keyring" | NB | — | Device flow and keyring | M | med |
| 18.2-4 | §18.2.2 credential resolution order, `MAYA_DEBUG_AUTH`, `~/.maya/config.toml` profile with `api_key_env` | BU | `maya/sdk/client.py:206-222` | No test of `connect()` resolution or profiles. `default_namespace` and `cache_dir` in a profile are read by nothing | S | med |
| 18.2-5 | §18.2.2 key "refused with a clear error if the URL is plain HTTP outside `localhost`" | BU | `client.py:196` `_refuse_plain_http` | No test | S | med |
| 18.2-6 | §18.2.3 "`pip install maya-sdk` brings in a client of a few megabytes and nothing else"; §18.2.6 "depends only on `httpx`, `pydantic` and `pyarrow`" | NB | One `maya` distribution (`pyproject.toml`); the SDK imports `maya.core.*` and `maya.observability.tracing` (`transport.py:65`) | A separate SDK distribution. ADR-001 records it as not delivered | M | med |
| 18.2-7 | §18.2.3 "A download returns a short-lived, single-use presigned URL … a config flag routes the stream back through the API" | NB | Every byte goes through the API tier (`raw=True` responses) | Presigned URLs, direct object-store reads, the fallback flag. There is no object store to presign from (local FS only, see 25-3) | L | med |
| 18.2-8 | §18.2.3 "Ranged, resumable downloads with content-hash verification on completion" | NB | — | Range requests and resume | M | med |
| 18.2-9 | §18.2.3 "Column projection, date-range and universe filters are pushed to the server, and Arrow IPC is zstd-compressed on the wire" | NB | `features.preview(start,end)` only | Projection and filters on `download`, and zstd on the wire | M | med |
| 18.2-10 | §18.2.3, §18.2.5 "The local cache is keyed by content hash"; "Pinned data is cached locally by content hash and verified on read" | NB | No `cache.py` | The whole cache, and the shared-cache pattern for grid fleets in §24.4 | M | med |
| 18.2-11 | §18.2.3 "custom CA bundles are configurable, optional mTLS …, SSE falls back to polling …, connection pooling" | PB | httpx honours `HTTPS_PROXY` and pools; `Client(verify=)` only (`client.py:62`) | `connect()` and `AsyncClient` take no CA option. No mTLS (`cert=`). No SSE client to fall back from | S | med |
| 18.2-12 | §18.2.3 "Connect, read and total timeouts are separate and configurable" | PB | One `timeout`; connect fixed at 10 s (`client.py:73`); `TransportError` is distinct from a refusal (`transport.py:39`) | Separate read and total timeouts | S | low |
| 18.2-13 | §18.2.4 `import maya; my = maya.connect(profile="prod")` | NB | `maya/__init__.py` is empty; the SDK is `maya.sdk` | `maya.connect`, `maya.Client` and `maya.offline` at the top level | S | **high** (first line of every example fails) |
| 18.2-14 | §18.2.4 `for f in my.features.list(...): print(f.name, f.latest_version.version_no)` | PB | `features.list()` returns a list of dicts; the lazy iterator is a separate `features.iter()` | Attribute access and `latest_version` | S | med |
| 18.2-15 | §18.2.4 `feat.clone(name=…)`, `draft.extend(parent=…, binding="pinned")`, `draft.override(resolution=…)`, `draft.submit(note=…)` | NB (as written) | Functional equivalents: `features.clone(ref, name, extend=)`, `features.update_draft`, `features.transition(ref, v, "submit")` | The handle verbs | M | med |
| 18.2-16 | §18.2.4 `feat.version(4).pin(...)` → `job.wait(progress=print)` → `pin.to_arrow(shape=…)` / `.to_polars()` / `.to_pandas()` / `.to_file()` | PB | `features.pin(ref, version_no, pin_name, as_of, as_of_known)` and `Client.wait(job, progress=)` (`client.py:112`); `download()` returns bytes | `to_arrow`, `to_polars`, `to_pandas` and `to_file`. `wait` returns a job dict, not a pin | M | **high** |
| 18.2-17 | §18.2.4 "`await job` in the async client" | NB | `AsyncClient` has no `wait` at all | An async wait | S | med |
| 18.2-18 | §18.2.4 `my.warrants.training.create(model=, featureset=, split=, seed=, holdout=)` | PB | `my.training.create(namespace, name, model, featureset, spec={})` (`resources.py:~668`) | The `warrants.training` namespace, and keyword args in place of a spec dict | S | med |
| 18.2-19 | §18.2.4 `with warrant.data(shape="tensor") as ds: … ds.X, ds.y` | PB | `Client.training_data(id)` downloads, verifies the checksum and returns `(table, manifest)` (`client.py:132`) | Context manager, `shape=` (tensor), X/y split | S | med |
| 18.2-20 | §18.2.4 `with my.workspace("…") as ws: ws.features.get(…).override(…); ws.shadow_replay().summary(); ws.submit_for_review()` | PB | `workspaces.create/stage/shadow_replay/submit` | Context manager, a scoped `ws.features`, `.summary()` | S | med |
| 18.2-21 | §18.2.4 namespaces "`features`, `featuresets`, `models`, `parameters`, `warrants.training`, `warrants.execution`, `workflow`, `lineage`, `jobs`, `namespaces`, `admin`" | PB | `training`, `execution`, `access.lineage`; parameter transitions sit under `training` (`client.py:34-51`) | `parameters`, `warrants.*`, `lineage` as namespaces | S | low |
| 18.2-22 | §18.2.5 "Every `list()` returns a lazy iterator …; `list(...).page()` exposes raw pages" | PB | Separate `.iter()` and `.page()` methods | `list()` is eager (one unpaged call) | S | low |
| 18.2-23 | §18.2.5 retries "on 429, 502, 503, 504 and connection resets with exponential backoff and jitter" | PB | `SyncTransport.call` (`transport.py:81-102`) | No jitter (deterministic sleeps). **`AsyncTransport` never retries**. Untested | S | med |
| 18.2-24 | §18.2.5 "Every create-work call sends a client-generated idempotency key" | NB | Sent only if the caller passes `idempotency_key=` (`resources.py:468-474, 543-549`) | Automatic generation | S | med |
| 18.2-25 | §18.2.5 "Mutations send `If-Match` … and raise `ConflictError`" | NB | — | See 18.1-2 | M | med |
| 18.2-26 | §18.2.5 "`job.wait()`, `job.progress()`, `job.cancel()`, and an SSE-backed event stream" | PB | `Client.wait`, `jobs.cancel` | No `progress()`. **`Events.stream()` and `Jobs.events()` (`resources.py:949,1040`) make a buffered GET of an SSE stream**: `events.stream` runs up to 7,200 polls server-side, so the SDK call blocks until the 120 s client timeout and raises `TransportError`. Unusable as a stream | S | med |
| 18.2-27 | §18.2.5 "Every data download checks the server-issued checksum" | PB | Training data verified (`client.py:132-141`) | `features.download` and `featuresets.download` hand back unverified bytes | S | med |
| 18.2-28 | §18.2.5 "Version skew … the server refuses a client older than the supported window" | BU | `maya/api/app.py:25,103-107` (HTTP 426) | No test | S | low |
| 18.2-29 | §18.2.6 package layout (`config.py`, `auth.py`, `transport/`, `generated/`, `resources/`, `handles.py`, `cache.py`, `errors.py`, `testing.py`) | PB | `client.py`, `transport.py`, `resources.py`, `io.py`, `offline.py`, `replay.py`; errors in `maya/core/errors.py`; testing in `maya/testing/` | The rest | — | low |
| 18.2-30 | §18.2.7 "`maya.testing` ships an in-memory fake implementing the same protocol" | PB | `maya/testing/kit.py`: a real throwaway platform (SQLite in a tmpdir), tested (`tests/test_testing_kit.py`); record/replay tested | Not in-memory and not a fake: it needs the whole server package | M | low |
| 18.2-31 | §18.2.7 "Our own UI tests run against the fake" | NB | UI tests run against a real in-process platform. The no-backdoor property is enforced by the import-boundary gate instead | The UI suite on the fake. Better to revise the spec: the gate is a stronger proof | S (docs) | low |

### §18.3 CLI (checked against `maya/cli/__main__.py:290-360`)

| # | Command | Class | Note |
|---|---|---|---|
| 18.3-1 | `maya featureset build` | NB | No such subcommand | 
| 18.3-2 | `maya model validate` | NB | `model push` validates implicitly; there is no re-validate or report command |
| 18.3-3 | `maya warrant create` | NB | Warrants can be created only through the UI or SDK |
| 18.3-4 | `maya admin user\|role\|grant\|policy` | NB | `admin` has only `init-db`, `export-estate`, `import-estate`, `verify-integrity` |
| 18.3-5 | `maya export bundle maya://warrant/train/…@v1` (by URI) | PB | Takes a warrant **id** (`export_bundle`, `bundle.py:198` `require(id)`); a URI is not resolved |

Sizes: S each; 18.3-4 is M. Importance: med for CI and scripting users (`warrant create` and
`admin grant` are the ones scripts want).

### §18.4 Reproducibility bundle

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 18.4-1 | bundle contains "code artifact, … feature set definition, every member pin's data and manifest" | PB | Warrant, certificate, model version, IR, spec.tex, parameters, environment, `data/training.parquet` (the joined training frame), generated reference model, `verify.py`, signed manifest (`maya/services/bundle.py:135-175, 226-245`) | The uploaded **code artifact** (only the IR-generated reference model is included), the **feature set definition**, and **each member pin's own data and manifest**. A regulator cannot rebuild the frame from member pins | M | med |

### §19 Lineage, provenance and audit

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 19-1 | Edge types "`extends`, `overrides`, `operand_of`, `composite_member`, `derived_from`, `member_of`, `pinned_as`, `trained_on`, `parameterized_by`, `executed_under`, `superseded_by`" | PB | Nine are written (`features.py:411-418`, `feature_data.py:313`, `warrants.py:163,327`, `execution.py:140`, `models.py:413`, `featuresets.py:228-582`) | `overrides` and `superseded_by` are never written. Only `operand_of` is asserted by a test (`tests/test_features.py:204`) | S | med |
| 19-2 | Lineage read authorization (implied by §11, and by "nothing else is so much as named" in search) | PB (**security**) | `GET /lineage` → `ops.lineage(root, …)` (`maya/api/routers/admin.py:275-278`, `maya/services/ops.py:205`) | **No principal is passed and no read filter is applied.** Any signed-in user can walk the graph from any ref and learn names of features, models and warrants in namespaces they cannot read. Search filters by read permission; lineage does not | S | **high** |
| 19-3 | "answered in milliseconds" | BU | Recursive walk (`lineage_edges.walk`) | Never measured | S | low |
| 19-4 | "Impact analysis runs **before** a change is submitted … and the review screen shows it to the approver" | PB | `workspaces.impact` (`maya/services/workspaces.py:154`), shown in the workspace UI | A plain feature or model version submitted outside a workspace gets no impact analysis on its review screen | M | med |
| 19-5 | Audit "queryable in the UI with saved views, exportable as CSV or JSON, and retained per policy (default seven years)" | PB | Audit explorer with server paging and CSV export (`table.js` exportCsv; `web/routes/admin.py:378`) | Saved views, JSON export, a retention policy setting | S | low |
| 19-6 | "A model's *Decisions* view reads as a narrative" | PB | "History & Comments" tab (`model.html:130`) | A narrative Decisions view | M | low |

### §20 Observability and operations

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 20-1 | Metrics list | PB | HTTP rate, latency and status per route; job runs, duration and state counts; sessions; authz denials; pins sealed and bytes; webhook backlog; build, seam and tier info (`maya/observability/metrics.py`, `services/registry.py:94-113`); tested (`tests/test_observability.py:43`) | Job wait time, resolution rows and bytes per second, Delta file counts and small-file ratio, DB pool utilization and slow-query count, cache hit rates, and **pins and bytes per namespace** (no namespace label) | M | med |
| 20-2 | Traces "from HTTP request through service, plan, resolution, storage read and job execution" | PB | Spans only for HTTP (`api/app.py:87`) and jobs (`jobs/queue.py:156`), tested | Service, plan, resolution and storage spans. "Why did this pin take 40 minutes" gets one opaque job span | M | med |
| 20-3 | Logs "always carrying request id, trace id, actor and object reference … log level configurable per module at runtime" | PB | JSON formatter with trace and span id (`maya/observability/logs.py:16-27`) | request id, actor and object ref in log lines; per-module runtime levels (only the root level, set at startup) | S | med |
| 20-4 | SLOs, "Each SLO has an alert with a runbook link" | NB | — | No alert rules or SLO definitions shipped (no Prometheus rules file) | S | med |
| 20-5 | Runbooks "stuck job, orphaned pin partition, Delta small-file explosion, database failover, IdP outage, sandbox escape suspicion, storage quota exhaustion, restore drill, default-password remediation" | PB | 9 runbooks (`docs/runbooks/`): stuck jobs/pins, SSO outage, restore drill, and others | Delta small-file explosion, database failover, sandbox escape suspicion, storage quota exhaustion, default-password remediation (orphaned partitions only partly, inside the stuck-pins runbook) | S | med |
| 20-6 | Backup: "continuous WAL archiving plus nightly full backups, RPO 5 minutes, RTO 1 hour" | PB | Backup procedure in `maya/web/guides/operations-guide.md:139+` | Nothing in the product and no stated RPO/RTO procedure. Unmeasured | S (docs) | med |
| 20-7 | "a quarterly restore drill … The drill result is recorded and visible" | PB | `docs/runbooks/restore-drill.md`; `admin verify-integrity` (tested, `tests/test_cli.py:243`) | No drill performed (README). Nowhere in the product records or shows a drill result | S | med |
| 20-8 | Upgrades "Rolling, backward-compatible one version back … expand-migrate-contract" | contradiction → see §3 | Estate export → recreate → import (ADR-012, ADR-023) | — | — | — |

### §21 Security and model risk governance

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 21-1 | "grants cannot exceed the granter's own level; every grant audited and recertified" | BU | `maya/services/access.py` `grant` (requires `grant` on the object; only admins grant `admin`); `/access/recertification` | No test of the grant ceiling or of recertification | S | med |
| 21-2 | Exfiltration: "per-namespace export quotas; optional watermarking of exported manifests" | NB | `quota_bytes` column on namespaces (`access.py` create/update; `persistence/models/identity.py:117`) is **stored and never read** | Quota enforcement, manifest watermarking | M | med |
| 21-3 | Tampering: "periodic integrity verification" | PB | `verify-integrity` on demand (CLI, API, admin page) | Not scheduled. The scheduler runs escalation, expiry, lake maintenance and custody anchoring only (`services/registry.py:55-60`) | S | med |
| 21-4 | Credentials: "secrets from environment or a vault" | PB | Environment variables (`password_env`, `MAYA_SECRET_KEY`), sealed secretbox | No vault reference | M | low |
| 21-5 | Uploads: "Content-type sniffing, size and expansion limits, path normalization, quarantine-then-scan, storage by content hash" | PB | Blobs by content hash; 20 MB cap on `.xlsx` only (`maya/formula/xlsx.py:43,580`) | No size cap on CSV/Parquet ingest, bundle verify or artifact upload. **No zip expansion limit**: `.xlsx` via openpyxl, and `bundles/verify` reads every member (`bundle.py` `_untrusted` `z.read`), a zip-bomb vector. No sniffing, no quarantine | M | **high** |
| 21-6 | "strict CSP with no inline script, `X-Frame-Options: DENY`" | BU | Set on every response (`maya/api/app.py:110-117`); CSP scripts are `'self'` only (styles allow `'unsafe-inline'`) | No test asserts the headers (CSRF is tested, `tests/test_web.py:146`) | S | med |
| 21-7 | DoS: "Rate limits, per-job memory ceilings, queue depth shedding, request timeouts, bounded pools" | PB | Bounded DB pool (`persistence/engine.py:25-33`); sandbox memory caps | Rate limits (18.1-5), memory ceilings for resolution and pin jobs, queue shedding, request timeouts | M | **high** |
| 21-8 | §21.2 classification "drives export controls, masking defaults and retention" | NB | `classification` stored and shown (`access.py`; `admin/namespaces.html:10,23`) | It drives nothing. No reader outside create, update and display | M | med |
| 21-9 | §21.2 "where a feature could contain [personal data], the namespace is marked and exports require an additional approval" | NB | — | The flag and the approval | M | low |
| 21-10 | §21.2 "TLS 1.2+ in transit; encryption at rest" | PB | Delegated: the server speaks plain HTTP behind a TLS proxy (ops guide:67) | Nothing in code enforces TLS on the server side. Fine as a deployment decision, but the spec should say so | S (docs) | low |
| 21-11 | §21.3 "Inventory: a complete, queryable register … exportable on demand" | PB | Model list with server paging and CSV export | A register view or export with dependencies and use | S | med |
| 21-12 | §21.3 "records monitoring outcomes against the model version" | NB | Execution `report` records runs and rows only | Monitoring-outcome records | M | med |
| 21-13 | §21.3 "Change control: every version change classified" | PB | `catalog.change_class` for feature definitions (`services/catalog.py:210`) | No classification for model version changes | S | low |

### §22 Engineering standards

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 22-1 | "Functions under 50 lines, cyclomatic complexity under 10, enforced by `ruff`"; "inheritance depth capped at 3" | PB | `max-complexity = 12`, `max-statements = 50` (`pyproject.toml`); 8 `noqa: C901/PLR0915` | Complexity threshold is 12, not 10. No inheritance-depth check | S | low |
| 22-2 | "Public interfaces are protocols in a `ports` module" | PB | Only `maya_delta` `_Backend(Protocol)`; ADR-001 says there is no `ports/` | See §3 | — | low |
| 22-3 | "`mypy --strict` on the domain and service layers" | PB | `tools/ci/typecheck.py` targets `maya/services` only | There is no domain layer; `resolution/`, `security/`, `workflow/` are unchecked | M | low |
| 22-4 | "No silent config defaults — an unset required setting fails at startup" (also §24.2 "fails at startup on an unknown key") | PB | Required: `app.environment`, `db.dialect`, `auth.mode`, `storage.root`, the DB fields, `app.secret_key` outside dev (`maya/config/__init__.py:25-95`) | `settings.get(key, default)` supplies code defaults everywhere else. **Unknown keys are accepted.** No typed schema with description and validator | M | med |
| 22-5 | "Architecture decisions recorded as numbered ADRs … referenced from the code they govern" | NB | 28 ADRs | `grep ADR-0 maya maya_delta tools` finds **0** references | S | low |
| 22-6 | "Docstrings on every public class and method" | BU | Most public methods in `sdk/resources.py` have none | No gate | S | low |

### §23 Testing and release engineering

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 23-1 | "90% line coverage on `domain/` and `resolution/`" | PB | Global `--cov-fail-under=90` (`tools/ci/gates.py`) | No per-package floor | S | low |
| 23-2 | Repository suite "against real SQLite *and* real PostgreSQL", "Full suite green on both" as a gate | PB | PG runs on demand (`MAYA_TEST_PG_URL`) | Not in the gate ladder. The 13 newest tests have run on SQLite only (README) | S | med |
| 23-3 | Gate 11b fallback matrix | BU | `tools/ci/gates.py --fallback` (FALLBACKS, `MAYA_TEST_EXTRA_ARGV` in `tests/conftest.py:48`) | No evidence it has run green. **README and plan still say "not built"** (stale docs) | S | low |
| 23-4 | "Release. … migration dry-run on a production-shaped copy, canary deployment, and a rollback tested in staging" | NB / contradiction | — | See §3. At most: an estate export/import dry-run and a rollback rehearsal | S | low |

### §24 Deployment, configuration and capacity

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 24-1 | Clustered topology "N API pods …, M job worker pods, … S3-compatible object store" | NB | One host: a primary process (jobs, scheduler, webhooks) plus N web processes (`run_maya_web.py:101-171`), tested | No worker-only process role, no multi-host coordination (a second host would also run a scheduler), no S3 | L | med |
| 24-2 | "Containers are built reproducibly with pinned dependencies and run as a non-root user" | NB | No Dockerfile or container build | All of it | S | med |
| 24-3 | Layers "defaults in code → `application.yaml` → `application.properties` → environment variables → command-line flags" | PB | yaml, `application.local.yaml` overlay, env, `--key=value` (`core/properties_configurator.py`) | `application.properties` is not a layer (the local.yaml overlay replaces it) | S (docs) | low |
| 24-4 | "Every setting is declared in a typed schema with a description, a default and a validator" | NB | Ad-hoc `settings.get/int/bool` | The schema (see 22-4) | M | med |
| 24-5 | §24.3 per-pod users, pin write 50 MB/s, object counts, 1,000 jobs/h, cold start < 30 s, 2 TB table | BU | `tools/bench/bench_capacity.py` written | Never run: no result files in `docs/benchmarks/`. SC-4, SC-5 and 100k search measured on SQLite only | S (run it) | med |
| 24-6 | §24.4 "One inbound port, 443, HTTPS only; HTTP is refused outside `localhost`" | PB | The SDK refuses credentials over HTTP (18.2-5) | The server serves plain HTTP (TLS at the proxy); nothing refuses non-TLS | S | low |
| 24-7 | §24.4 "shared, content-hash-keyed cache directory … the recommended pattern for grid fleets" | NB | — | See 18.2-10 | — | med |
| 24-8 | §24.5 "a test asserts that two objects differing only in case cannot collide on a case-insensitive filesystem" | NB | Lake tables at `root/kind/namespace/name` (`maya/storage/lake.py:62`); names allow mixed case (`services/refs.py:23`) | No test. On a case-insensitive filesystem (also SMB or NTFS mounts on Linux) `Prices` and `prices` share one directory | S | low (Linux-only scope) |

### §25 Extensibility and integrations

| # | Spec | Class | Exists | Missing | Size | Imp |
|---|---|---|---|---|---|---|
| 25-1 | "Every axis of variation is a registered plugin …, discovered by entry point, configured by name. … listed on an admin page with its status. Untrusted plugins run under the same sandbox" | NB | Fixed internal registries (rule dict in `resolution/rules.py:220`, `FORMATS` in `resolution/shapes.py:35`, seams in `core/backends.py`); no `entry_points` anywhere | Plugin discovery, declared config schema, admin listing, plugin sandboxing | L | med |
| 25-2 | Source drivers "sql, csv, parquet, json, delta, derived, python" | BT | All present (`feature_data.py:115` delta) | Not as protocol plugins | — | — |
| 25-3 | Storage "Delta on local FS, S3, Azure Blob, GCS" | NB (cloud) | Local filesystem only | S3, Azure, GCS | L | med |
| 25-4 | Export formats "… Excel" | PB | arrow, parquet, json, ndjson, csv | Excel export | S | low |
| 25-5 | Notifiers "In-app inbox, email, webhook, Slack, Teams" | PB | Inbox and signed webhooks | Email, Slack, Teams | M | med |
| 25-6 | Integrations: Git sync of definitions as YAML, Airflow/Prefect operators, Jupyter extension, BI connectors, OpenLineage emitter | NB | Workflow policies round-trip as YAML (not definitions) | All five (the spec calls them "worth building early", not a gate) | L | low |

---

## 3. Contradictions: candidates for revision markers

1. **§20 Upgrades "Migrations run in an expand-migrate-contract pattern" and "backward-compatible one version back for … schema"** contradicts §14.3 and ADR-012/023 (no migrations; upgrade = estate export → recreate → import). No revision marker in §20.
2. **§23 Release "migration dry-run on a production-shaped copy"** has the same conflict with §14.3. A replacement would be an "estate export/import dry-run".
3. **§19 Audit "not an administrator, not a migration — can edit"**: harmless, but it names migrations that cannot exist.
4. **§24.5 "Full-text search | SQLite FTS5 … Detected at startup; MAYA's own inverted index is the fallback"** and **§25 table "Search index | PostgreSQL FTS, SQLite FTS5"** both contradict the Revision 2.2 marker at §14 (line 1010) and ADR-019: the own index is the only implementation, not a fallback. Neither row carries the marker.
5. **§22.3 package layout draws `maya/domain/` and `maya/ports/`**, and §22.1 says "Public interfaces are protocols in a `ports` module". Neither exists; ADR-001 says "the drawing is older than the code". The spec has no marker.
6. **§18.2.6 SDK package layout, and §18.2.3/§18.2.6 "`pip install maya-sdk` … depends only on httpx, pydantic, pyarrow"**: ADR-001 records the separate SDK distribution as not delivered. The spec has no marker.
7. **§18.1 endpoint table**: the `:resolve`, `:cascade` and `:seal` verb URLs and `/features/{id}/pins/{pin}/data` do not exist; the real paths differ (`/feature-data?ref=`, a `cascade` flag, `/warrants/training/{id}/seal`). The committed OpenAPI snapshot is the de facto authority.
8. **§18.1 event names** (`feature.version.approved`, `warrant.parameters.uploaded`, `model.deprecated`) do not match the code: `feature_version.approved`, `warrant.parameters_uploaded`, `model_version.deprecated` (`maya/observability/events.py:17-36`).
9. **§18.2.7 "Our own UI tests run against the fake"** is contradicted by the actual design: a real in-process platform, with the import-boundary gate as the no-backdoor proof. §23's CI-pipeline row lists that gate too.
10. **§23 CI pipeline "A pull request cannot merge on a red pipeline"** and **§24.5 "PostgreSQL in CI: Mandatory on Linux"**: ADR-002 decided there is no hosted CI (local gates plus a pre-commit hook), and PostgreSQL is not in the gate ladder.
11. **§22.1 "cyclomatic complexity under 10"** vs `pyproject.toml` `max-complexity = 12`.
12. **§24.2 "`application.properties`" layer** vs the shipped `application.local.yaml` overlay.
13. **§25 Model runtime "Python; ONNX and PMML as v2.2 candidates"** vs ADR-007 (no model runtime except blind scoring). The marker belongs on the §25 row.
14. **§17.2 editor "bracket matching"**: the code and `editors.js` comments claim it, but the addon is absent (a code bug more than a spec issue).
15. **README and IMPLEMENTATION_PLAN are stale against the code** (not the spec). Both say the fallback matrix (gate 11b) is not built, but `gates.py --fallback` exists. The M8 note says "`maya.testing` fakes … the synthetic market dataset … not delivered", but `maya/testing/kit.py` and `market.py` and their tests exist. `docs/runbooks/README.md` says `--local` "starts … the webhook dispatcher and the scheduler", which the uncommitted CLI change now stops.

---

## 4. Built+tested (terse)

- §17 CodeMirror 5 vendored, no build step (DS, Rev 2.2, ADR-020)
- §17.1 Tectonic true build; draft watermarked on every page with `draft_render` metadata (`tests/test_typeset.py`)
- §17.1 firm template, required sections, completeness blocks submission (`test_warrants.py::test_model_submission_is_blocked_by_an_incomplete_spec`)
- §17.1 `\mayaformula` / `\mayaref` expansion (`test_formula.py:222`)
- §17.1 compile failure surfaced with its first TeX error and log (`test_typeset.py:54`)
- §17.2 six-rung ladder, each rung's refusal (`tests/test_sandbox.py`)
- §17.2 Linux `strong` tier by an escape probe, declared on the health page and in the report (`test_sandbox.py:27`, `test_sandbox_linux.py`)
- §17.2 no network, CPU/memory/wall/output caps, read-only filesystem in the child (`test_sandbox.py:70-102`)
- §17.2 determinism probe warns (`test_sandbox.py:88`)
- §17.2 artifacts content-hashed and immutable, report attached to the version
- §17.3 one restricted expression grammar for transforms, feature-set filters, row filters (`resolution/expr.py`; `test_conditions.py`, `test_resolution_*`)
- §18.1 `/api/v1`, OpenAPI generated, `/api/v1/docs` reference, contract snapshot gate (`test_gate_ladder.py:46`)
- §18.1 cursor pagination (`test_paging.py`)
- §18.1 RFC 9457 problem documents with stable `type` (`test_api_contract.py:115`)
- §18.1 202 plus job for pins; idempotent double-submit (`test_concurrency.py:117,133`)
- §18.1 webhooks HMAC-signed, retry, dead-letter, SSRF refusal, durable events in the same transaction (`test_observability.py:120-200`)
- §18.2.1 SDK↔API parity gate both ways (`tools/ci/sdk_parity.py`; `test_api_and_gates.py`); UI↔SDK parity gate
- §18.2.2 API key `maya_<env>_<id>_<secret>`, KDF hash, expiry, scope, revocation (`test_api_and_gates.py::test_api_key_scope_environment_and_revocation`)
- §18.2.2 web tier uses the user's session token, `channel: web`, no shared key (`test_web.py::test_web_imports_only_the_sdk`)
- §18.2.2 anonymous callers reach health endpoints only (`test_api_contract.py:102`)
- §18.2.3 `http` and `inproc` transports; `record`/`replay` sync and async, no credentials in cassettes (`test_sdk_modes.py:37-147`)
- §18.2.3 network failure raises a distinct `TransportError` (CLI exit 3)
- §18.2.4 cascade pin over a feature set (`test_cli.py:146`, `test_warrants.py`)
- §18.2.4 parameter upload and blind holdout scoring (`test_warrants.py::test_the_checksum_cycle_seal_score_execute_and_bundle`)
- §18.2.4 workspace shadow replay and submit (`test_workspaces.py`)
- §18.2.4 sync `Client` and `AsyncClient` from one resource source; web uses the async one
- §18.2.5 training-data checksum verified and recorded for parameter upload
- §18.2.5 bitemporal `as_of`/`as_of_known` on pin, preview and download (SC-11 test)
- §18.2.5 typed error hierarchy mapped from problem `type` (`test_sdk_modes.py:60`)
- §18.2.5, §18.2.3 `maya.offline(bundle)` serves the read API with no network (`test_sdk_modes.py:225-278`)
- §18.2.7 recorded-fixture mode; `maya.testing` throwaway platform plus pytest plugin (`test_testing_kit.py`)
- §18.3 `feature list|show|upload|pin|download|diff`, `quick` (`test_cli.py:77-127`)
- §18.3 `featureset pin|download` (`test_cli.py:146`)
- §18.3 `model push|diff` (`test_cli.py:163`)
- §18.3 `warrant fetch|upload-params|seal` (`test_cli.py:181`)
- §18.3 `job watch|cancel` (`test_cli.py:231`)
- §18.3 `export bundle|verify` (`test_cli.py:181`)
- §18.3 `--json` and meaningful exit codes 0/1/2/3 (`test_cli.py:77,88,95`)
- §18.4 signed bundle, `verify.py` recomputes every hash, offline verify, re-executes composites, a tampered byte refused (`test_sdk_modes.py:176,278`; `test_warrants.py`)
- §19 lineage written in the creating transaction (operand_of asserted)
- §19 provenance record: definition hash, engine and library versions, backend set, actor, wall clock, plan, inputs, content hash (SC-1 test)
- §19 audit append-only by DB trigger, hash-chained, tamper detected, anchored to an external file, webhook and TSA (`test_workflow_and_estate.py`, `test_custody.py`)
- §19 audit carries actor, principal type, channel, time, object, action, detail, request/trace id, IP
- §19 comments, approval rationales and break-glass recorded (`test_workflow_and_estate.py`)
- §20 Prometheus exposition, token-protected (`test_observability.py:43,60`)
- §20 W3C trace from request to audit row and job; OTLP export (`test_observability.py:71,90`)
- §20 `/healthz`, `/readyz`, health page with schema, queue, workers and degraded modes (`test_api_and_gates.py`, `test_web_processes.py`)
- §20 `admin verify-integrity` re-reads every pin and the chain (`test_cli.py:243`, `test_features.py`)
- §20 version single source (gate)
- §21.1 Python artifact sandbox (above); read-only least-privilege SQL (`test_sql_source.py`)
- §21.1 role ceiling (`test_foundation.py::test_role_ceiling_is_never_exceeded`, `test_authz_matrix.py`)
- §21.1 downloads audited with manifest and checksum; column masks and row filters on every path (`test_conditions.py`)
- §21.1 KDF passwords, MFA (TOTP, WebAuthn) and required-for-roles, short-lived sessions, lockout (`test_sso_mfa.py`, `test_webauthn.py`)
- §21.1 CSRF tokens (`test_web.py:146`)
- §21.3 documentation mandatory; limitations and assumptions sections block approval; SoD enforced (`test_workflow_matrix.py`); reproducibility (SC-1, SC-2 `test_sc2_aged_warrant.py`); policy per namespace
- §22.1 file-size gate 1500/1200/800 (`tools/ci/file_size.py`, planted-violation test)
- §22.2 `MayaError` hierarchy with code, message, context; no bare `except` (ruff E722)
- §22.4 Python not shell for gates; CHANGELOG ritual
- §23 Hypothesis property tests (`test_properties.py`, `test_resolution_algebra.py`)
- §23 API contract snapshot; authorization matrix (SC-7); concurrency suite; SC-1 reproducibility
- §23 benchmark regression gate (`gates.py --bench`, `tools/bench/regress.py`)
- §23 Playwright headless Chrome with screenshots (`test_browser.py`)
- §23 pip-audit, bandit SAST, sandbox escape suite (`gates.py --security`, `tools/ci/sast.py`)
- §23 synthetic market dataset (`maya/testing/market.py`, `test_market_dataset.py`)
- §24.1 laptop topology; single node, several web processes over PostgreSQL (`test_web_processes.py`)
- §24.2 `--key=value` highest precedence; effective config admin page with sources, secrets redacted; secrets not in the tracked file (`test_foundation.py`)
- §24.3 SC-4, SC-5, 100k search measured (`docs/BENCHMARKS.md`)
- §24.5 `spawn`, `__main__` guard, banner, signal and atexit drain (`run_maya_web.py`); tzdata and event-loop seams on the health page; exclusive-create Delta commits (`maya_delta/pure/log.py`, conformance suite); `.gitattributes`
- §25 source drivers (sql, csv, parquet, json, delta, derived, python); resolution rules (ffill, bfill, linear, spline, constant, zero, window mean, as-of); calendars (NYSE, LSE, TARGET, ISO); auth providers (DB, OIDC, SAML2); workflow checks

## 5. Deliberately superseded (DS)
- §17 CodeMirror 6 → 5 (Rev 2.2, ADR-020)
- §24.5 and §25 FTS5/tsvector → own inverted index (Rev 2.2 at §14, ADR-019); the §24.5 and §25 rows lack the marker
- §25 model runtime ONNX/PMML → ADR-007 (no runtime except blind scoring)
- §20 and §23 migrations → §14.3 and ADR-012/023 (no migrations); the §20 and §23 text lacks the marker
- §23 hosted CI → ADR-002 (local gate ladder plus pre-commit hook)
