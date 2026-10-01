<p align="center">
  <img src="assets/logo/maya-lockup.svg" alt="MAYA — Model &amp; AI Lifecycle Assurance" width="100%">
</p>

<h1 align="center">MAYA</h1>

<h3 align="center">Model &amp; AI Lifecycle Assurance</h3>

<p align="center"><strong><em>Evidence, not assertion.</em></strong></p>

<p align="center">
  <a href="#status--read-this-first">Status</a> ·
  <a href="#whats-shipped">What's shipped</a> ·
  <a href="#the-name">The name</a> ·
  <a href="#what-makes-it-different">What makes it different</a> ·
  <a href="#getting-started">Getting started</a> ·
  <a href="docs/design/MAYA_Requirements_and_Design.md">Specification</a>
</p>

---

**MAYA** is the system of record for quantitative **features**, **feature sets**, **models**, and the **warrants** that license a model to be trained or run. Definition, data, documentation, approval and evidence live in one place, so any number a model produced can be rebuilt exactly, years later, by someone who was not there.

It exists because four things are true in almost every quantitative shop, and each of them is a reproducibility failure waiting to be discovered by someone who is not on your side:

1. Feature logic lives in notebooks and SQL snippets, so two teams compute "adjusted close" differently and neither is wrong.
2. Training data is a file on a share drive. When results are challenged, nobody can produce the exact rows used.
3. A model's mathematics lives in a PDF, its code in a repo, its parameters in a spreadsheet, and the three drift apart.
4. Nothing binds *this model version* + *this data version* + *these parameters* into one auditable, transferable object.

The **warrant** is MAYA's distinguishing primitive. A *training warrant* freezes a model version against a feature set version and receives the parameters that training produced. An *execution warrant* packages a model, its parameters and its input contract into a licence that can be handed to a downstream system or a regulator — and, because it is a live instrument rather than a document, withdrawn on a Friday afternoon when the model is found to be wrong. Warrants make *who was allowed to run what, on which data, with whose approval* a query rather than an archaeology project.

[![Status](https://img.shields.io/badge/status-specification%20complete-blue.svg)](docs/design/MAYA_Requirements_and_Design.md)
[![Implementation](https://img.shields.io/badge/implementation-v1.0.0-green.svg)](docs/design/IMPLEMENTATION_PLAN.md)
[![Python](https://img.shields.io/badge/python-3.13-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

---

## The name

**māyā** (माया) — in Indian philosophy, *māyā* is **appearance**: the representation that stands in
for reality and is so easily mistaken for it. The usual translation, "illusion", is too strong. Māyā
is not falsehood. It is a *rendering* of the world — useful, often necessary, and dangerous only when
you forget that it is a rendering.

That is exactly what a model is. The supervisory guidance says so in almost the same words:

> *"Models are simplified representations of real-world relationships… based on assumptions that make
> them useful in estimating values and predicting events, but which also can have limitations and
> create model risk."*
> — SR 26-2, §III

Model risk is what happens when an organisation forgets the difference between the map and the
territory. The platform is named for the thing it governs, and for the discipline of never mistaking
it for the world.

| | |
|---|---|
| **Name** | MAYA — from Sanskrit *māyā* (माया), *appearance*, *representation* |
| **Tagline** | Model & AI Lifecycle Assurance |
| **Slogan** | **Evidence, not assertion.** |
| **Principle** | A model is a representation of the world. Governance is knowing the difference. |

### The mark

![The MAYA mark — a square inscribed in a circle](assets/logo/maya-mark-128.png)

A **square inscribed in a circle** — the oldest model there is. Archimedes estimated π by inscribing
and circumscribing polygons and tightening the bound as the sides multiplied: a tractable figure
standing in for one that cannot be computed directly.

The **gap** between the square and the circle is the model error. The **four points** are where the
model and the world agree. Add sides and the gap closes but never vanishes — no model becomes the
thing it represents.

That is māyā, and it is model risk, in one figure.

---

## Status — read this first

**Version 1.0.0 (2026-09-26), built from specification revision 2.6.**
The whole spine runs through the web UI, the REST API, the SDK and the CLI:
source → feature → feature set → pin → model → training warrant → parameter set →
execution warrant → reproducibility bundle. On top of it, 1.0.0 adds the model governance
a model risk function works in: findings and remediation, materiality tiers, periodic
review that suspends overdue models, monitoring, champion and challenger, fairness and
explainability evidence, SR 11-7 and SS1/23 inventory exports, LLM application governance,
and connectors to MLflow, SageMaker, OpenLineage, Snowflake and Databricks. The SDK's own
version, `CLIENT_VERSION`, is 1.0.0 as well: it gained a method for each of those.

| | |
|---|---|
| **Specification** | [`docs/design/MAYA_Requirements_and_Design.md`](docs/design/MAYA_Requirements_and_Design.md) — the authority |
| **Plan** | [`docs/design/IMPLEMENTATION_PLAN.md`](docs/design/IMPLEMENTATION_PLAN.md) — each milestone marked with what it delivered and what it did not |
| **Shipped** | [What's shipped](#whats-shipped), below — every capability with the tests that prove it |
| **Measured** | [`docs/quality/BENCHMARKS.md`](docs/quality/BENCHMARKS.md) — SC-4, SC-5, 100k-object search and the four §24.3 capacity targets pass; SC-3 is not met reliably |
| **Changes** | [`docs/CHANGELOG.md`](docs/CHANGELOG.md) |
| **Audited** | [`docs/quality/audit/spec-audit-2026-09-19.md`](docs/quality/audit/spec-audit-2026-09-19.md) — revision 2.3 read against the code, requirement by requirement: of about 540, some 195 were built and tested, 28 built but untested, 123 partly built and 84 not built. The gaps were ranked; every ranked gap has since been closed but for one clause of gap 14, and the header says which |
| **Decisions and operations** | [`docs/design/adr/`](docs/design/adr/) — 28 architecture decision records; [`docs/operations/runbooks/`](docs/operations/runbooks/) — fifteen runbooks, the nine §20 asks for among them, the restore drill performed and recorded |
| **Code** | `maya/` (the platform), `maya_delta/` (the lakehouse layer), `run_maya_web.py` |
| **Tests** | 2,068 on Linux: 2,058 pass on SQLite and 10 are skipped (the eight Keycloak tests, `tests/test_sso_keycloak.py`, opt-in with `MAYA_TEST_KEYCLOAK_URL`, and the two multi-process server tests, which need PostgreSQL). The suite last ran green on PostgreSQL 16, 17 and 18 at 1,262 tests; the ones added since have run on SQLite only. With every Type A seam pinned to its fallback (`gates.py --fallback`) it passed at 1,150 tests and has not been rerun since. They include real-browser tests in headless Chrome, a multi-process server, a worker process, LibreOffice Calc as a judge of spreadsheet lifts, and a real `openssl` timestamp authority. Line coverage was 92.9% at 0.3.0, with a 90% floor in `gates.py --tests`. `python -m pytest -q` |
| **Gates** | `python tools/ci/gates.py`: all green — lint, strict typing of `maya/services`, file size, both import boundaries, import cycles, public names per module, seam imports, SDK public symbols, version single source, no secrets, table contract, colour contrast, SDK↔API parity for 246 endpoints, UI↔SDK parity, the API contract snapshot, protocol literals, bandit, schema drift. `--tests`, `--fallback`, `--security` and `--bench` add the suite with coverage, the fallback matrix, pip-audit with the sandbox tests, and the benchmark regression check |

### Out of scope by decision

Three things the specification or the plan asks for will not be done, by the owner's
decision. They are stated as decisions, not as work in progress, and each costs
something that should be read plainly:

- **The assistant is not tested against the live Claude API.** With
  `assistant.provider: claude` the request — Claude Opus 5, structured JSON output,
  server-side refusal fallbacks — is verified against a stub of the Anthropic client,
  and only against that. Whether the live service answers the way the stub does is
  unproven. The deterministic `rules` provider, the default, is unaffected. The same holds
  for a *live* evaluation run of an LLM application: it goes through the same client, and
  is tested against a stub; recorded runs are unaffected. Both can also go through the AI
  gateway (`assistant.provider: llm`; any `anthropic`, `openai`, `azure_openai`, `bedrock`
  or `ollama` version for a live run), where each provider is tested against its own stub.
- **Windows and macOS are not exercised.** Only Linux is. The specification's SC-14 —
  the full suite green on all three — is therefore not met, and the code paths that
  exist only for the other two (`sandbox-exec` at `moderate` on macOS, the wall-clock
  `minimal` tier on Windows, the `tzdata` package Windows depends on for time zones)
  have never run. There is no
  hosted CI either: the gate ladder runs locally, in the pre-commit hook on every commit
  and as `python tools/ci/gates.py --tests`.
- **There is no dedicated benchmark host.** Every figure in
  [docs/quality/BENCHMARKS.md](docs/quality/BENCHMARKS.md) comes from one shared workstation. SC-3,
  200 users on one node, is not met reliably there: on PostgreSQL with 8 web processes,
  three runs gave p95 0.34 s, 0.22 s and 0.43 s against 0.3 s, at 93–97 requests/s with
  no errors. Without a quiet host that verdict will not be settled either way.

### Not yet — stated so nobody has to discover it

- **The connectors have not met a live service.** MLflow and SageMaker import, the
  OpenLineage export and the Snowflake and Databricks sources are tested against the
  documents those systems publish and a recorded HTTP exchange — not against a running
  MLflow server, an AWS account, an OpenLineage consumer or a warehouse.
- **The 1.0.0 additions have run on SQLite only.** The suite last ran green on PostgreSQL
  before them; run it with `MAYA_TEST_PG_URL` before relying on PostgreSQL.

- **PostgreSQL 14 and 15 have not been run.** The whole suite passes on PostgreSQL
  16.15, 17.11 and 18.6, as well as SQLite; 14 is the documented floor. Run it with
  `MAYA_TEST_PG_URL=postgresql+psycopg://user@host/db python -m pytest`; each test
  platform gets its own freshly created database.
- **Single sign-on is proven against one real IdP, Keycloak 26.4.** Single sign-on is
  OIDC or SAML 2.0 (`auth.sso.protocol: oidc | saml2`, SP-initiated; the IdP must sign
  assertions). Against Keycloak 26.4.7, driven in headless Chrome, OIDC sign-in with
  group-mapped roles, SAML sign-in with signed requests, single logout started from MAYA
  and logout started from Keycloak all worked, and so did OIDC logout both ways:
  signing out of MAYA ended the Keycloak session (`auth.sso.post_logout_redirect_uri`),
  and ending a session in Keycloak's admin console ended the MAYA session by back
  channel. The security guide has the settings. Keycloak's "sign out all sessions" of a
  user was seen to send a logout token for one of that user's sessions only. No
  commercial IdP (Okta, Entra ID, ADFS) has been tried, and Keycloak only over http on
  loopback. Not supported: SAML back-channel (SOAP) logout, so a SAML IdP that signs
  someone out without their browser does not reach MAYA. The simulated-IdP tests attack
  every SAML, OIDC and logout-token check on its own. Second factors are
  TOTP and WebAuthn keys/passkeys, tested with a software ES256 authenticator, not
  hardware. Attestation is not requested, so MAYA does not claim a key is
  hardware-backed.
- **A sign-out can take two seconds to reach another web process.** A signed-in
  session's principal is reused for `auth.session.principal_cache_seconds` (default 2),
  because one page makes several internal calls. A sign-out, revocation or access
  change applies at once in the process that made it, and up to that long later in the
  others. Set it to 0 where that window matters more than the page cost.
- **A feature-set pin that is not written is only as readable as its replay.** Under a
  namespace's `materialize_policy` of `on_demand` or `never`, a pin is sealed by the
  hash of its output and rebuilt from its member pins when read. If a later MAYA ever
  resolved those inputs differently by one byte, the read would fail with
  `integrity_error` rather than serve other numbers — safe, but unavailable. `always`,
  the default, has no such dependency.
- **The `strong` sandbox tier is Linux-only.** On Linux, bubblewrap namespaces, a
  seccomp-bpf filter and a cgroup v2 scope are applied unprivileged, and the tier is
  claimed only when a probe child fails to escape. macOS would run at `moderate`
  (`sandbox-exec`); Windows at `minimal` (Job Objects are not built).
- **True PDF builds need Tectonic on each server.** Install the static binary (verified
  here with Tectonic 0.17.0 on Linux) and specification PDFs are real LaTeX builds;
  without it they are watermarked drafts, and `typeset.require_true_build` forbids
  approval on a draft outside dev. Tectonic downloads its TeX bundle on first use: an
  air-gapped server must be given a cached bundle.
- **§24.3 is measured on SQLite, on one workstation.** Pin write throughput (59.7 MB/s,
  51.4 on a second run, against 50 — a narrow pass), job throughput, cold start,
  100k-object search, and 20k feature sets, 10k models and 100k pins without degradation
  all pass ([BENCHMARKS](docs/quality/BENCHMARKS.md#capacity-243)); none has been run on
  PostgreSQL. The per-pod figure and Delta table size (2 TB per
  feature) have not been measured. Several web processes need PostgreSQL; MAYA refuses
  them over SQLite.
- **The specification is not fully built.** The audit above ranked what was partly built
  or missing by what it costs a user. Every ranked gap has since been closed — the
  feature-set algebra, subscriptions, enforced quotas, upload and archive limits, the
  SDK's object handles, the review screen's semantic diff, the fragment collector and
  the rest — but for one clause of gap 14: a pin download still takes every byte through
  the API tier rather than through a presigned object-store URL, because there is no
  object store to presign from. What remains beyond the ranking is the long tail of the
  audit's own per-requirement tables, which nobody has re-walked since 2026-09-19. This
  README's *What's shipped* lists only what is built and tested.
- **Server-side paging is per page, not per threshold.** Features, feature sets, models,
  audit, events and jobs always page from the server; smaller tables stay client-side. In
  server mode a table sorts on the columns the server can order by (name, update time,
  sequence), one key at a time, and its search runs on the server's fields (name and
  description, or actor/action/object for audit), then highlights matches in what is
  shown. Lists filtered row by row for authorization (features, feature sets, models,
  warrants) count their exact total in the database, one count per namespace and
  ownership group. The
  table script was exercised in headless Chrome against a harness, not in a user's browser.
- **Spreadsheet import is v1 scope.** Arithmetic, standard functions, named cells and ranges,
  and VLOOKUP/HLOOKUP over constant tables lift into the formula IR; everything else is refused
  by cell. Every supported construct, the lookups and a multi-sheet model have been checked
  against LibreOffice Calc's own results (recalculated headless). They have not been
  checked against workbooks saved by Microsoft Excel.
- **Custody anchors are only as external as you make them.** The chain head is signed,
  appended to `custody.anchor.file` and emitted as a webhook event hourly; RFC 3161
  timestamping is off by default. Point the file at WORM or off-host storage: on the
  same disk as the database it only raises the bar. A timestamp authority's own
  signature is checked, through `openssl ts -verify`, only when
  `custody.anchor.tsa_ca_file` names its CA certificate; without it MAYA checks the
  token's status and imprint and leaves the signature to you.
- **Search is MAYA's own inverted index**, identical on SQLite and PostgreSQL: ranked,
  prefix-matched, every term required, filtered by read permission, kept current in the
  writing transaction. PostgreSQL `tsvector` and SQLite FTS5 are not used. CodeMirror 5
  instead of 6 and the corrected dark `--maya-crimson-deep` token are recorded in the
  specification as revision 2.2.

---

## What's shipped

The implementation plan's milestones, as delivered. Each row names where the capability
lives and the tests that prove it; a capability without a test that exercises it is not
listed, because on this platform an untested claim is an assertion. What a milestone
promised and did not deliver is marked in
[the plan](docs/design/IMPLEMENTATION_PLAN.md#6-milestones), milestone by milestone.

| Capability | Where it lives | Proved by |
|---|---|---|
| **M0** The gate ladder, each gate seen to fail on a planted violation | `tools/ci/` | `tests/test_api_and_gates.py` (`test_gate_fails_on_a_planted_violation`, `test_web_import_boundary_fails_when_web_reaches_past_the_sdk`, `test_schema_drift_gate_fails_after_a_hand_edit`) |
| **M0** Type B seams: canonical bytes and content-defined fragments, MAYA's own implementation authoritative | `maya/core/canonical.py`, `maya/core/chunker.py` | `tests/test_foundation.py` (`test_canonical_bytes_are_fixed`, `test_chunker_is_content_defined`), `tests/test_properties.py` |
| **M0** Configuration with no secret in the tracked file and no silent default | `maya/core/properties_configurator.py`, `config/` | `tests/test_foundation.py` (`test_tracked_config_carries_no_secret`, `test_local_overlay_wins_and_no_silent_defaults`), `tests/test_core_utilities.py` |
| **M1** Two generated schema files, drift refused, a mismatched database refused at startup | `maya/persistence/models/`, `maya/persistence/schema/` | `tests/test_foundation.py` (`test_shipped_schema_files_match_the_metadata`, `test_hand_edit_is_detected`), `tests/test_workflow_and_estate.py` (`test_schema_mismatch_refuses_to_start`) |
| **M1** The upgrade path with no migrations: estate export → recreate → import | `maya/persistence/estate.py` | `tests/test_workflow_and_estate.py` (`test_estate_round_trip_and_audit_tamper_detection`, `test_a_database_from_another_schema_still_exports_and_loads`, `test_a_required_column_the_estate_cannot_fill_is_named`) |
| **M1** Hash-chained audit, tampering detected | `maya/persistence/repositories/` | `tests/test_workflow_and_estate.py` (`test_estate_round_trip_and_audit_tamper_detection`), `tests/test_api_and_gates.py` (`test_denials_are_audited_even_though_they_roll_back`) |
| **M1** One authorization function, the role ceiling, the ACL order | `maya/security/authz.py`, `maya/security/roles.py` | `tests/test_foundation.py` (`test_role_ceiling_is_never_exceeded`, `test_acl_resolution_order`), `tests/test_api_contract.py` (every route as anonymous, no-role and administrator), `tests/test_workflow_matrix.py` |
| **M1** Stored-KDF passwords that rehash upward; a signer that refuses rather than downgrades | `maya/core/kdf.py`, `maya/core/crypto.py` | `tests/test_foundation.py` (`test_kdf_records_its_algorithm_and_rehashes_upward`, `test_crypto_refuses_rather_than_downgrading`) |
| **M1** Sessions, API keys, lockout; the two-second principal cache | `maya/services/auth.py` | `tests/test_api_and_gates.py` (`test_lockout_after_repeated_failures`, `test_api_key_scope_environment_and_revocation`), `tests/test_principal_cache.py` |
| **M1** OIDC and SAML 2.0 single sign-on, logout in both directions, TOTP and WebAuthn | `maya/security/oidc.py`, `maya/security/saml.py`, `maya/security/passkeys.py`, `maya/services/sso.py` | `tests/test_sso_mfa.py`, `tests/test_oidc_logout.py`, `tests/test_saml.py`, `tests/test_saml_slo.py`, `tests/test_webauthn.py`; against Keycloak 26.4, `tests/test_sso_keycloak.py` (opt-in) |
| **M1** The table contract, every table from one macro | `maya/web/templates/`, `tools/ci/table_contract.py` | `tests/test_web.py` (`test_only_the_macro_emits_tables`), `tests/test_browser.py` (`test_a_server_paged_table_pages_searches_and_sorts`) |
| **M1** The UI as an SDK client, with no private path | `maya/web/`, `sdk/maya/sdk/` | `tests/test_web.py` (`test_web_imports_only_the_sdk`, `test_every_page_renders`), `tests/test_web_journeys.py`, `tests/test_web_catalog_models.py`, `tests/test_web_workbench.py` |
| **M2** `maya_delta`: one conformance suite on both backends, cross-backend reads, refusal by name (SC-16) | `maya_delta/` | `tests/test_maya_delta.py` |
| **M2** Lake compaction and vacuum that change nothing anyone can read | `maya_delta/`, `maya/services/ops.py` | `tests/test_lake_maintenance.py` |
| **M3** Byte-identical re-resolution, with the negative case (SC-1) | `maya/services/features.py`, `maya/storage/lake.py` | `tests/test_features.py` (`test_sc1_repin_is_byte_identical_and_changed_data_is_not`) |
| **M3** Point-in-time after a restatement (SC-11); an unchanged month costs its delta (SC-12) | `maya/resolution/resolver.py`, `maya/core/chunker.py` | `tests/test_features.py` (`test_sc11_point_in_time_after_restatement`, `test_sc12_unchanged_month_costs_under_five_percent`), `tests/test_properties.py` (`test_a_restatement_never_overwrites`) |
| **M3** Resolution rules, calendars, quality contracts that block a pin | `maya/resolution/` | `tests/test_resolution_core.py`, `tests/test_resolution_edges.py`, `tests/test_resolution_grouped.py`, `tests/test_features.py` (`test_quality_contract_blocks_the_pin`) |
| **M3** The feature algebra; every logical type round-trips in every format | `maya/resolution/algebra.py`, `maya/resolution/shapes.py` | `tests/test_resolution_algebra.py` (`test_property_round_trip`, `test_tensor_round_trip_every_format`) |
| **M3** Sources: files, read-only SQL, a sandboxed Python producer | `maya/services/sources.py` | `tests/test_sql_source.py`, `tests/test_python_source.py`, `tests/test_features.py` (`test_unsupported_source_is_refused_by_name`) |
| **M3** The scratch namespace and `maya feature quick` | `maya/services/features.py`, `maya/cli/` | `tests/test_features.py` (`test_scratch_quick_feature_has_zero_ceremony`), `tests/test_cli.py` (`test_quick_upload_and_restatement`) |
| **M3** Catalog search, filtered by read permission | `maya/persistence/search_index.py` | `tests/test_search.py` |
| **M4** Feature sets: policy precedence, alignment, broadcast, refusal of an unaggregated index | `maya/resolution/featureset.py`, `maya/services/featuresets.py` | `tests/test_resolution_algebra.py` (`test_featureset_precedence_layers_and_broadcast`, `test_featureset_refuses_unaggregated_extra_index`) |
| **M4** Cascade pin that rolls back entirely | `maya/services/featuresets.py` | `tests/test_warrants.py` (`test_cascade_rolls_back_entirely_on_a_member_failure`), `tests/test_cli.py` (`test_featureset_pin_cascade_and_download_shapes`) |
| **M4** Pin materialization `always`, `on_demand`, `never`, one hash for all three | `maya/services/featuresets.py` | `tests/test_materialization.py` |
| **M4** Grant conditions: row filters, column masks, time bounds | `maya/security/conditions.py` | `tests/test_conditions.py` |
| **M5** Workflow as data: edit-time validation, governed activation, byte-identical YAML, break-glass, campaigns | `maya/workflow/`, `maya/services/workflow_service.py` | `tests/test_workflow_and_estate.py` |
| **M5** Every transition, every role; separation of duties per preset; delegation and escalation | `maya/workflow/engine.py` | `tests/test_workflow_matrix.py`, `tests/test_delegation.py` |
| **M5** Workspaces and shadow replay; approval is the merge | `maya/services/workspaces.py` | `tests/test_workspaces.py` |
| **M6** The formula IR: parse, render, evaluate, diff, codegen, lift, composites, conformance | `maya/formula/` | `tests/test_formula.py`, `tests/test_language_tables.py` |
| **M6** The compute-kernel wizard: mathematics in, the typed IR with its hash and one self-contained Python function out, creating nothing | `maya/formula/codegen.py` (`to_python_kernel`), `maya/services/models.py` (`kernel`), `/models/kernel` | `tests/test_compute_kernel.py` (`test_the_kernel_is_one_function_and_nothing_else`, `test_the_kernel_and_the_reference_module_compute_the_same_thing`, `test_the_wizard_page_translates_and_carries_its_work_to_the_designer`) |
| §8.4 Joint parameter constraints, checked on upload where per-parameter bounds are | `maya/formula/ir.py` (`constraint_errors`), `maya/services/warrants.py` (`check_constraints`) | `tests/test_formula.py` (`test_a_model_can_declare_a_constraint_bounds_cannot_express`) |
| **M6** Artifact validation, one refusal per rung; the Linux sandbox attacked | `maya/security/sandbox.py`, `maya/security/sandbox_runner.py` | `tests/test_sandbox.py`, `tests/test_sandbox_linux.py` |
| **M6** Specification documents: true Tectonic builds, labelled drafts without it | `maya/core/typeset.py`, `maya/formula/specdoc.py` | `tests/test_typeset.py`, `tests/test_warrants.py` (`test_model_submission_is_blocked_by_an_incomplete_spec`) |
| **M6** Spreadsheets as models, checked against the workbook and against LibreOffice Calc | `maya/formula/xlsx.py` | `tests/test_spreadsheet.py`, `tests/test_spreadsheet_libreoffice.py` |
| **M7** Warrants: the checksum cycle, the leakage certificate, blind scoring, covenants that suspend, unattested offline copies | `maya/services/warrants.py`, `maya/services/execution.py` | `tests/test_warrants.py` (`test_the_checksum_cycle_seal_score_execute_and_bundle`, `test_leakage_certificate_refuses_late_knowledge`), `tests/test_security_regressions.py` (`test_each_covenant`) |
| **M7** Signed bundles that verify offline, re-execute composites and fail on one changed byte | `maya/services/bundle.py`, `sdk/maya/sdk/offline.py` | `tests/test_warrants.py`, `tests/test_sdk_modes.py` (`test_a_composite_model_is_re_executed_by_the_bundle_verifier`, `test_a_tampered_bundle_is_refused_before_anything_is_read`), `tests/test_cli.py` (`test_warrant_fetch_params_seal_bundle_and_offline_verify`) |
| **M8** SDK record/replay, sync and async; `maya.offline(bundle)` | `sdk/maya/sdk/replay.py`, `sdk/maya/sdk/offline.py` | `tests/test_sdk_modes.py` |
| **M8** Server-side cursor paging | `maya/services/paging.py`, `maya/web/routes/tables.py` | `tests/test_paging.py` |
| **M8** The CLI end to end, integrity verification | `maya/cli/` | `tests/test_cli.py` (`test_verify_integrity`) |
| **M8** Several web processes on one node over PostgreSQL | `maya/server.py`, `run_maya_web.py` | `tests/test_web_processes.py` |
| **M8** Metrics, tracing, events, signed webhooks | `maya/observability/`, `maya/services/webhooks.py` | `tests/test_observability.py` |
| §29.6 Licence algebra and custody anchors, with the TSA's signature checked | `maya/security/licence.py`, `maya/services/custody.py` | `tests/test_custody.py` (`test_an_anchor_catches_a_rechained_rewrite`, `test_a_real_tsa_signature_is_verified_against_its_ca`) |
| §29.8 The assistant as a recorded challenger | `maya/assistant/`, `maya/services/assistant.py` | `tests/test_assistant.py` (the Claude provider against a stub only) |
| The gate ladder: typing, cycles, symbol and API snapshots, the fallback matrix, UI↔SDK parity, bandit, pip-audit, benchmark regression | `tools/ci/gates.py` | `tests/test_gate_ladder.py` (each rung caught planting a fault); `gates.py --fallback` ran the whole suite with every Type A seam on its fallback |
| Read scoping of the review queue, SLA aging, break-glass report and lineage | `maya/services/workflow_service.py`, `maya/services/ops.py` | `tests/test_read_scoping.py` |
| `maya.testing`: a throwaway platform for users' own tests, and a synthetic market dataset | `maya/testing/` | `tests/test_testing_kit.py`, `tests/test_market_dataset.py` |
| The restore drill, on SQLite and PostgreSQL 17 | `docs/operations/runbooks/restore-drill.md` | Performed and recorded in the runbook, §5 |
| Measured against §3 and §24.3 | `tools/bench/` | Not tests: [docs/quality/BENCHMARKS.md](docs/quality/BENCHMARKS.md), from the result files in `docs/quality/benchmarks/` |
| **1.0.0** Findings register: severity, owner, due date, history; nobody closes their own fix | `maya/services/governance.py`, `/governance` | `tests/test_governance.py` (`test_a_finding_is_raised_remediated_and_closed_by_someone_independent`, `test_the_owner_does_not_accept_the_risk_in_their_own_model`) |
| **1.0.0** Materiality tiers from measured drivers and the firm's questionnaire (`config/tiering.yaml`) | `maya/services/governance.py` | `tests/test_governance.py` (`test_the_tier_is_derived_and_an_override_that_lowers_it_is_flagged`, `test_the_questionnaire_drives_the_tier_and_refuses_answers_it_does_not_offer`, `test_the_points_rule_sums_answers_and_places_them_by_threshold`) |
| **1.0.0** Periodic review: an overdue review suspends live warrants; a review lifts only those | `maya/services/governance.py` | `tests/test_governance.py` (`test_an_overdue_review_suspends_live_warrants_and_a_review_lifts_only_those`) |
| **1.0.0** Monitoring dashboards: warrants graded ok, watch or breach; server-drawn charts | `maya/services/monitoring.py`, `maya/web/charts.py`, `/monitoring` | `tests/test_governance.py` (`test_monitoring_reads_reports_as_series_and_grades_the_warrant`, `test_chart_geometry_keeps_bounds_on_the_scale`), `tests/test_web_catalog_models.py` (`test_monitoring_pages_draw_the_series`) |
| **1.0.0** Black boxes scored blind in the sandbox from their validated artifact | `maya/services/warrants.py` | `tests/test_vendor_models.py` (`test_a_black_box_with_a_validated_artifact_is_scored_blind_in_the_sandbox`) |
| **1.0.0** Champion and challenger on the same sealed holdout, paired bootstrap interval | `maya/services/challenges.py`, `/governance/challenges` | `tests/test_challenges.py` (`test_the_verdict_needs_the_whole_interval_on_one_side`, `test_a_challenger_is_scored_on_the_champions_rows_and_decided_independently`, `test_warrants_on_different_holdouts_are_not_compared`) |
| **1.0.0** Fairness by segment (small segments suppressed) and permutation importance | `maya/services/evidence.py` | `tests/test_challenges.py` (`test_segments_suppress_small_groups_and_flag_the_worst`, `test_evidence_on_the_holdout_names_the_driver_and_counts_an_attempt`) |
| **1.0.0** Regulatory inventory export, SR 11-7 and SS1/23 layouts, XLSX/CSV/JSON | `maya/services/inventory.py` | `tests/test_governance.py` (`test_the_inventory_exports_in_each_layout_and_counts_what_it_leaves_out`), `tests/test_llm.py` (`test_llm_applications_appear_in_the_inventory`) |
| **1.0.0** LLM applications: sealed versions, evaluation sets, guardrails, approval on evidence | `maya/services/llm.py`, `/llm` | `tests/test_llm.py`, `tests/test_web_catalog_models.py` (`test_an_llm_application_from_registration_to_approval_through_forms`) |
| **1.0.0** Connectors: MLflow and SageMaker import, OpenLineage export, Snowflake and Databricks sources | `maya/services/integrations.py`, `maya/persistence/external.py`, `/integrations` | `tests/test_integrations.py` |
| **1.0.0** The normal quantile `ncdfinv` in the formula IR; derived features keep `_knowledge_time` | `maya/formula/`, `maya/resolution/algebra.py` | `tests/test_formula.py` (`test_the_normal_quantile_is_an_operator_not_a_reciprocal`), `tests/test_resolution_algebra.py` (`test_every_operator_carries_the_knowledge_clock`) |

**Promised by the plan and not delivered.** SC-9 — a new designer publishing a first
model in under an hour, timed with a real person — has not been measured, and no
external security review has been done: neither can be done by the project itself. The
three-platform matrix is out of scope by decision (above). The plan marks each where it
was promised; the [specification audit](docs/quality/audit/spec-audit-2026-09-19.md) lists what
the specification asks for beyond the plan's milestones and is not yet built.

---

## What makes it different

No product occupies this position today (spec §27 compares MAYA head-to-head against feature stores, lakehouse versioning, ML registries, catalogs and model-risk tools). Five things are the reason.

- **Definitions are code; data is a consequence.** MAYA stores *how* a number is produced and materialises values only when asked. A **version** freezes *how*; a **pin** freezes *what*. A version resolved a hundred times may return different values as its source moves; a pin returns the same bytes forever. *(§4)*
- **A closed algebra over features and feature sets.** `union`, `intersect`, `compose`, `coalesce`, `extend`, `override`, `project`, `aggregate` — every operator takes features and yields a *feature definition*, not a one-off result, so a derived object is an ordinary object: named, versioned, pinnable, permissioned, and visible in lineage. Inheritance stores a **diff, not a copy**, so a fix to a parent reaches every child. *(§5.8, §6.8)*
- **Model mathematics as structured data.** A model's formula is a typed **expression tree**, not a LaTeX string and not prose. From it MAYA type-checks inputs against the bound feature set, renders the specification document, emits a reference implementation, and **diffs two model versions mathematically** — telling a reviewer *"the discount factor changed from continuous to simple compounding"* rather than showing a text diff. Where a model genuinely has no closed form, it is recorded as a **declared black box** rather than pretended otherwise. *(§8.1)*
- **Bitemporality from the first migration.** Every row carries an *event time* and a *knowledge time*. A vendor restatement is a new knowledge-time row, never an overwrite, so *"what did we know on 31 March"* stays answerable and a backtest cannot silently consume restated values. MAYA can then **prove** the absence of look-ahead and issue a signed **leakage certificate** against the warrant. Point-in-time correctness exists elsewhere as a join semantic; nobody issues a certificate. *(§5.1, §29.1)*
- **Evidence that survives leaving the building.** A pin's content hash is computed over a *canonical* Arrow representation, not over file bytes, so two pins of the same data hash identically even across engine versions. `maya export bundle` produces a signed archive — warrant, model, formula IR, code, parameters, every member pin, the pinned environment — with a `verify.py` that recomputes every hash **and re-executes**, on a machine with no MAYA access at all. *(§7.2, §18.4, §28.7)*

---

## The shape of the thing

```
Source ──▶ Feature ──▶ FeatureSet ──▶ ⟨pin⟩ ──┐
  sql        definition   attribute            ├──▶ Training Warrant ──▶ Parameter Set
  csv        + versions   mapping              │         │                      │
  parquet        │        + alignment          │         ▼                      ▼
  json           ▼                             │    (train offline,      Execution Warrant
  delta      Feature Pin ──────────────────────┘     upload params)       ── the licence
  derived    (materialised,                                                  you hand to
  python      content-addressed)        Model ──▶ Composite Model         a downstream
                                        formula · code · LaTeX             system, or
                                                                          to a regulator
```

Features and feature sets are **closed under their operators**, so the algebra loops back into the same flow: a derived feature re-enters as an ordinary feature. A composite model is an ordinary model and takes **one** warrant over **one** feature set, however many members it has.

---

## Ten innovations, and what each costs

Specification §29 states each of these precisely enough to build, and honestly about its price. They are listed here because they are the reason MAYA is worth building rather than buying.

| # | Innovation | Cost, stated |
|---|---|---|
| 29.1 | **Bitemporal features + leakage certificate** — signed proof a training set has no look-ahead | Two columns everywhere, a second index dimension, ~20–30% storage. Phase 1 or never |
| 29.2 | **Shadow replay** — re-run every dependent model on the proposed change and report the *numeric* shift, not a list of names | Compute, and a sampling strategy honest about coverage |
| 29.3 | **Content-addressed materialization** — a pin is a manifest of shared fragments; a month-end pin costs its delta | A fragment index and a GC provably safe against sealed pins. Phase 1 or never |
| 29.4 | **Escrowed holdout and blind scoring** — the developer never receives the test partition; MAYA scores and counts the attempts | MAYA must execute scoring — a narrow, bounded step into runtime |
| 29.5 | **Warrants with covenants** — machine-checked bounds whose breach *suspends* the warrant and fails every consuming call closed | A monitoring loop and a clear false-positive story |
| 29.6 | **Licence algebra + tamper-evident custody** — vendor terms propagate as the most restrictive of a derivation's operands; the audit chain anchors externally | Legal input on vocabulary; one external dependency |
| 29.7 | **Spec–code conformance testing** — differentially test the uploaded Python against a reference generated from the documented mathematics | An IR interpreter, and honesty that sampled agreement is not proof |
| 29.8 | **The assistant as a recorded challenger** — never approves, never blocks, never writes to a sealed object; its memo is attached and the human records whether they agreed | Prompt and output governance, and a strict no-write boundary |
| 29.9 | **Spreadsheets as first-class models** — lift an Excel formula graph into the IR and govern it like anything else | Scope v1 narrowly and refuse the rest loudly |
| 29.10 | **Vendor models under the same wrapper** — register the black box, mark what cannot be verified as unverifiable rather than omitting it | Low to build, high in value: completeness is what an examiner asks for |

---

## Deliberate non-goals

Stated because a design without stated losses is a sales pitch. MAYA **does not train models and does not serve predictions** (§2). It will be beaten on online serving latency, streaming freshness, raw scale, connector breadth and out-of-the-box regulatory report templates (§27.4). Where a firm needs sub-10 ms serving, the right answer is MAYA governing the definition and a serving layer consuming a sealed execution warrant — not MAYA growing a serving tier.

Four risks have no clean fix and are accepted with mitigation rather than waved away: two-store consistency on pin, Python's concurrency ceiling, execution that happens outside MAYA, and the fact that a catalog nobody seeds is an empty shop (§28.11).

---

## Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.13 (`.python-version`) | Matches the estate; `.venv` is git-ignored |
| API | FastAPI + Pydantic v2, OpenAPI 3.1 | Typed contracts, generated spec, async where it helps |
| Platforms | **Windows, Linux and macOS, equally first-class** | Not "Linux, and it probably works elsewhere" — the specification requires all three green before a release (SC-14). By the owner's decision only Linux is exercised, so SC-14 is not met, and there is no hosted CI (see *Out of scope by decision*) |
| ORM | SQLAlchemy 2.0, typed | Confined to one package, enforced by a gate (`tools/ci/import_boundaries.py`) |
| Schema | **Two generated DDL files, no migration framework** | One typed metadata is the source; `schema/postgresql.sql` and `schema/sqlite.sql` are generated from it and CI fails on drift. Two files maintained by hand are two files that will disagree |
| Database | PostgreSQL 14+ in production, SQLite for laptop and dev | Full suite green on both, or the build fails. Run so far on PostgreSQL 16, 17 and 18, not 14 or 15 |
| Compute | Apache Arrow + Polars in process, DuckDB for pushdown | Columnar, zero-copy, releases the GIL |
| Lakehouse | **`maya_delta`** — native `deltalake` preferred, MAYA's own pure-Python Delta as fallback | ACID and time travel with no JVM and no Spark, and no hard dependency on someone else's build matrix having a wheel for the platform in front of us |
| UI | Jinja2 + **Bootstrap 5** + **jQuery**, vendored, **no build pipeline**, Harvard Crimson | Renders air-gapped. A developer moves between MAYA and DishtaYantra without relearning the layout grammar |
| Startup | One entry point: `python run_maya_web.py` | A second way to start a server is a second set of startup invariants to get wrong |
| Dependency seams | **Nineteen** optional or native components sit behind named MAYA seams, resolved once at startup by `maya/core/backends.py` and reported in the banner and on the health page | A capability must not vanish because a wheel does not exist for the interpreter in front of us |
| LaTeX | Tectonic in a sandboxed worker | Deterministic PDFs, no system TeX |
| Observability | OpenTelemetry, Prometheus, structured JSON logs | Vendor-neutral |

Full rationale in spec §13.1; deployment topologies — laptop, single node, clustered, air-gapped — in §24.1, all four from one artifact with only configuration differing.

### Dependency seams

`maya_delta` is not a special case. Spec **§13.4** states the rule for the whole stack:
where a capability comes from something that might not be installed, MAYA depends on its
own named seam and never on the component directly — one resolver, resolved once at
startup, reported in the banner and on the health page, pinnable by configuration, and
**recorded in every pin's provenance** so a result nobody can reproduce for want of
knowing which implementation produced it never happens.

The part that matters is not the list but the **polarity** — which side is authoritative:

- **Type A — native preferred, pure fallback.** `maya_delta`, JSON, frames, pushdown, the
  PostgreSQL driver, full-text search, compression, the tz database. Absence costs
  throughput, not capability.
- **Type B — MAYA's implementation is authoritative; a native one is only an
  accelerator.** Everything feeding a content hash: the canonicalizer and the fragment
  chunker. Here an accelerator that disagrees is a *defect in the accelerator*, and CI
  byte-compares rather than tests. Get this polarity backwards and two pins of identical
  data hash differently depending on which machine wrote them — SC-1 passes on each
  machine separately while being false across them.
- **Type C — substitutable, never downgraded.** Signing, object store, job queue. A
  hand-rolled fallback signer is how a governance platform ships a vulnerability, so
  absence here is a **refusal with a named reason**, not a quiet substitution. The
  sandbox and SSO follow the same polarity without sitting in the resolver: each is
  settled by its own module, because a sandbox tier is verified by a probe child rather
  than by an import. SAML without `xmlsec` fails at *startup* with the package named,
  rather than at the first person's login.

§13.4.4 lists what is deliberately **not** proxied — Arrow, SQLAlchemy, FastAPI, the
database engines — and why, because a pattern applied everywhere stops being a decision.

---

## Repository layout

```
run_maya_web.py            # the one supported way to start MAYA
config/application.yaml    # tracked, no secrets; application.local.yaml overlay is git-ignored
maya/
├── core/                  # version, configurator (from DishtaYantra), seams: backends,
│                          #   djson, canonical, chunker, kdf, crypto, compress, typeset, calendars
├── config/                # typed settings over the configurator
├── persistence/           # SQLAlchemy and nowhere else
│   ├── models/            #   the ORM metadata: the single source of the schema
│   ├── repositories/      #   dict-returning repositories, hash-chained audit, job claim
│   └── schema/            #   sqlite.sql, postgresql.sql, both GENERATED
├── security/              # roles matrix, can(), grant conditions, licences, OIDC, SAML,
│                          #   WebAuthn, the per-platform sandbox
├── resolution/            # expressions, rules, grids, transforms, quality, algebra, shapes
├── formula/               # formula IR, parser, LaTeX, evaluator, diff, codegen, artifacts
├── workflow/              # engine, policy validation, default policies
├── storage/               # blob store, LakeStore (fragments over maya_delta)
├── services/              # use cases: features, featuresets, models, warrants, …
├── jobs/                  # queue, workers and the maintenance scheduler
├── assistant/             # the recorded challenger: deterministic rules, and Claude (opt-in)
├── observability/         # metrics, tracing, structured logs, the event stream
├── api/                   # FastAPI routers under /api/v1
├── sdk/                   # the only client: Client, AsyncClient, inproc and http transports
├── web/                   # Jinja2 + vendored Bootstrap 5/jQuery; imports maya.sdk only
├── cli/                   # python -m maya.cli …
└── server.py              # the application factory each web process runs (server.workers)
maya_delta/                # Delta Lake: native (delta-rs) and pure-Python backends
tools/ci/                  # the gates, in Python so they run on every OS
tools/bench/               # the benchmarks behind docs/quality/BENCHMARKS.md
case_studies/              # nine worked models, each a folder of runnable steps, out of a
                           #   numbered catalogue of fifty (see below)
tools/docs/                # build_spec.py: the specification's .docx and .pdf from the Markdown
docs/                      # the specification, the plan, BENCHMARKS.md, CHANGELOG.md
└── benchmarks/            #   the unedited JSON result of every benchmark run
tests/                     # the suite; test_sso_keycloak.py runs only against a live
                           #   Keycloak (MAYA_TEST_KEYCLOAK_URL)
```

Two structural rules are worth stating in the README because they are load-bearing and non-negotiable (§14, §13, §16):

- **One door to the database.** Any module outside `maya.persistence` importing `sqlalchemy` fails the build.
- **The UI is an SDK client, with no private path to the backend.** Nothing under `maya.web` imports anything but `maya.sdk`. Any screen we can build, a customer can script, because the screen used the same methods — and a capability missing from the SDK cannot be quietly special-cased into the UI to hit a deadline.

- **Every table is paginated, searchable and sortable.** One macro produces every table in the product, and a template crawler fails the build on any `<table>` that did not come from it.
- **A proxied package is imported only inside its own seam.** No `deltalake` import outside `maya_delta`, no `orjson` outside `core/djson`. Which backend is running is a configuration fact reported at startup, never a scattered `try: import`.

All four are checked by non-overridable CI gates, not by review discipline. A gate that exists only in a review checklist has already been skipped.

---

## The interface

A governance platform lives or dies on whether people would rather use it than a
notebook (§28.1), so the UI is a first-class deliverable rather than a skin over the API.

**Harvard Crimson, used as a signal rather than a wash.** `#A51C30` is the primary —
measured at **7.48:1** against white, which clears WCAG AAA for body text — over a
parchment canvas, with a lightened crimson in dark mode at **5.67:1** because the brand
value itself measures only 2.44:1 on a dark background. The full token set is in spec
§16.6; a CI gate recomputes every foreground/background pair and fails below AA, because
a palette checked once by hand is a palette that drifts on the next well-meaning tweak.
Crimson marks the primary action, the active location, focus, and brand-bearing
headings — nothing else. Status is never carried by colour alone: every pill has a glyph
and a word.

**Every table, without exception, paginates, searches and sorts.** Rows-per-page
dropdown at 25 / 50 / 100 / 250 / All, remembered per table per user; search across
visible columns with the removed count stated; sort on every ordered column, applied to
the *whole result set* rather than the visible page; column show/hide; export of the
current view honouring the active filter and sort; keyboard paging for accessibility.
Tables that can grow without bound (features, feature sets, models, audit, events, jobs)
page from the server with signed cursors — the same macro, the same controls — and the
API offers the same paging on every large list (`?page_size=&cursor=&sort=`). Spec §16.7 — and a crawler gate, because a rule that is merely
written down is a rule that holds until the first deadline.

**Workflow is something you operate, not something you configure in a file.** State
machines render with the live population on them — how many objects sit in each state,
how long they have been there, which transitions are blocked and by which check.
Policies are authored in a structured editor that refuses an unreachable state, an
unsatisfiable approval or an unknown check *at edit time*, and previews the change
against the live population before it is saved. The policy is itself versioned, diffed,
approved and audited, because a governance system whose own rules can be changed
silently does not govern anything. YAML remains — as an import/export projection for
GitOps, not as a second authority. Spec §10.6.

---

## Case studies

`case_studies/` holds worked models, each one a real problem carried through MAYA end to end:
features defined and approved, data pinned point-in-time, a model registered with its
specification document, a warrant drawn, parameters approved, an execution warrant sealed, and
a covenant that takes the model out of service when its inputs stop resembling what it was
built on.

Each study is a folder of small scripts sharing the project's MAYA — the estate
`config/application.yaml` configures, each study in its own namespace — so you can run one
step, open the web UI on what it made, and run the next. Everything goes through `maya.sdk.Client`
as a named user with that user's roles, which is why the refusals in them are real: when a
study shows a feature designer being refused permission to approve her own feature, that is
the capability matrix saying no, not a script pretending. `case_studies/README.md` has the
full layout, and every study's own README carries its theory, its mathematics and the numbers
from a recorded run.

```bash
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py            # ~11 seconds
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_features.py --reset
```

**Built so far**

| | Study | Domain | Model type | What it is really about |
| --- | --- | --- | --- | --- |
| 01 | [Retail credit PD scorecard](case_studies/01-retail-credit-pd-scorecard/) | Retail credit risk | Fitted logistic | Bitemporality. A leakage certificate that refuses every row of a panel, and the written exception that lets the work proceed |
| 02 | [Scheduled mortgage cashflow](case_studies/02-mortgage-cashflow/) | Mortgage ALM | Closed-form, no fit | Whether the code the desk runs *is* the mathematics that was approved. A valid implementation with the commonest mortgage bug in it, caught |
| 03 | [Mortgage prepayment](case_studies/03-mortgage-prepayment/) | Mortgage valuation | Fitted hazard | A change proposed underneath a live model, priced before anyone approves it: 60% of the book moves |
| 04 | [HELOC exposure at default](case_studies/04-heloc-exposure/) | Retail secured credit | Composite router | Two members with different functional forms, a parameter set each, and a seal that refuses while half the composite is unfitted |
| 05 | [European option pricing](case_studies/05-option-pricing/) | Equity derivatives | Closed-form, calibrated | A parameter nobody can observe, and a conformance test that passes on a narrow domain and fails on the whole chain |
| 06 | [IFRS 9 expected credit loss](case_studies/06-ifrs9-expected-credit-loss/) | Impairment | Composite with its own parameters | Committee judgements as approved parameter sets, and a portfolio test that finds a 2.67× over-provision the per-account error cannot see |
| 07 | [Card-fraud neural network](case_studies/07-neural-network/) | Card fraud | Declared black box | What is left to hold to account when the mathematics is unreadable |
| 10 | [Factor models, CAPM to Fama–French](case_studies/10-factor-models/) | Asset management | Simple then multiple regression | Two versions of one model: MAYA's semantic diff, a contract that grew, and the maturity ladder from candidate to retired |
| 11 | [Nelson–Siegel yield curve](case_studies/11-nelson-siegel-curve/) | Fixed income, rates | Closed-form, non-linearly calibrated | A planted bug that a recalibration absorbs exactly, so only MAYA's blind score against the specification can see it |
| 09 | [Basel IRB regulatory capital](case_studies/09-basel-irb-capital/) | Regulatory capital | Closed-form, prescribed | A formula proved by reconciliation: a finding, a fix, independent closure, tier 1, a review and the SR 11-7 inventory row |
| 19 | [Vendor bureau score](case_studies/19-vendor-bureau-score/) | Retail credit | Bought black box, from MLflow | Imported with its signature, scored blind in the sandbox, fairness by region, and drift from *ok* to *breach* |
| 42 | [Demand elasticity](case_studies/42-demand-elasticity/) | Retail pricing | Linear vs log–log | Champion and challenger on the same escrowed rows, a paired interval, an independent decision |
| 45 | [Gompertz–Makeham mortality](case_studies/45-gompertz-makeham-mortality/) | Actuarial | Non-linear mortality law | A unisex table's systematic bias by sex, hidden by the MAE ratio, and the risk accepted in writing |
| 49 | [LLM complaint triage](case_studies/49-llm-complaint-triage/) | Operations | LLM application | Sealed prompt versions, an evaluation set, guardrails that catch personal data, approval on evidence |

**The rest of the fifty**, each chosen for a distinct thing it makes MAYA do — the numbers are
final, so a folder is never renumbered. `case_studies/README.md` says what each one adds.

| Group | Studies |
| --- | --- |
| **Retail and wholesale credit** | 12 LGD and recovery · 13 credit card behavioural scoring · 14 collections roll-rate · 15 low-default portfolio · 16 auto residual value · 17 AML transaction monitoring · 18 AML segmentation |
| **ALM and treasury** | 20 deposit beta · 21 deposit decay · 22 LCR outflow rates · 23 funds transfer pricing · 24 interest-rate risk in the banking book |
| **Pricing** | 25 volatility surface (SABR) · 26 Hull–White short rate · 27 curve bootstrapping · 28 CDS hazard bootstrapping · 29 bond duration and convexity · 30 American option lattice · 31 Monte Carlo exotics · 32 convertible bond |
| **Market risk** | 08 ARIMA and GARCH · 33 historical-simulation VaR · 34 expected shortfall / FRTB · 35 EWMA covariance · 36 stress scenarios · 37 CVA exposure · 38 mean-variance optimisation · 39 Black–Litterman |
| **Economics** | 40 inflation nowcast · 41 GDP nowcast · 43 Okun's law |
| **Life sciences** | 44 Cox survival · 46 gene-expression classifier · 47 pharmacokinetics · 48 SIR epidemic |
| **Operations** | 50 spreadsheet-lifted provision overlay |

Every input feed is synthetic, generated by the `make_data.py` beside it from a seeded recipe
stated in that file's docstring, and committed so a reader can open exactly what MAYA was
given. No real borrower, loan, patient or counterparty appears anywhere in the folder.

Writing them has been the most productive source of defects in the platform: around a dozen
so far, each fixed with a test that would fail without the fix. Several are named in the
study that found them; the rest are in the commit history rather than in a study's own
words, which is the weaker arrangement and is why the count is approximate.

---

## Getting started

**New to MAYA? Follow [`docs/getting-started/QUICKSTART.md`](docs/getting-started/QUICKSTART.md)** — a step-by-step guide from
nothing to MAYA running with demonstration data, in about fifteen minutes, with what you
should see at every step and what to do if you don't. The short version, for the impatient:

```bash
python3.13 -m venv .venv && .venv/bin/pip install -e ./sdk -r requirements.txt -r requirements-dev.txt
python run_maya_web.py                 # http://127.0.0.1:8600 — the landing page, then
                                       #   Sign in as admin / maya-dev-admin
```

`/` is the landing page until somebody signs in and the dashboard afterwards, and signing
out returns to it: a visitor who has not been told what MAYA is should not be handed a
password box. Change the admin password after the first sign-in. MAYA forces that change only when
`auth.password.force_change` is `true`; it is off by default, since with SSO it is rarely wanted. To switch the database, set `db.dialect` in
`config/application.yaml`, set `MAYA_DB_DIALECT`, or pass
`python run_maya_web.py --db.dialect=postgresql`, then supply `db.postgresql.*`, with the
password from `MAYA_PG_PASSWORD` or `config/application.local.yaml`. The schema is created
from the matching `.sql` file on first start, and verified by hash on every start.

```bash
python -m maya.cli feature quick prices.csv        # a scratch feature in one command
python -m maya.cli admin export-estate --out e.mayabundle   # the upgrade path, with
python -m maya.cli admin init-db --force                    #   no migrations (§14.3)
python -m maya.cli admin import-estate --in e.mayabundle
python -m maya.cli export verify bundle.zip        # offline; needs no MAYA
python tools/ci/gates.py --tests                   # the gate ladder
git config core.hooksPath .githooks                # commit-msg and pre-commit hooks
```

**Writing a client?** [`docs/reference/API_GUIDE.md`](docs/reference/API_GUIDE.md) walks the REST API end to end with examples that are run by the test suite; the live reference is at `/api/v1/docs`. SDK: `from maya.sdk import connect`.

---

## Security posture

Specified before it is built, which is the only order that works (§12, §21):

- **No silent defaults.** Where a value materially changes behaviour — authentication mode, database URL, storage root, sandbox enablement — there is no default at all outside dev, and MAYA fails at startup naming the setting.
- **Secrets never in a tracked file.** `config/application.yaml` is tracked and carries no secret; `config/application.local.yaml` is git-ignored and is where a real one belongs.
- **The default admin password is a speed bump, not a door.** MAYA refuses to start with it outside dev unless explicitly allowed.
- **User Python is hostile until proved otherwise.** Static validation, import allowlist, a sandboxed subprocess with no network, no credentials and resource caps — and a determinism probe, because non-determinism undermines every reproducibility claim MAYA makes.
- **The sandbox tier is declared, not assumed.** Three operating systems do not have equivalent isolation primitives, so MAYA resolves a tier at startup — `strong` on Linux only when a probe child verifies a bubblewrap jail with an unmapped user, a seccomp filter and a cgroup v2 scope; `moderate` on macOS (`sandbox-exec`) or on Linux with part of that; `minimal` on Windows, where Job Objects and restricted tokens are not built, and wherever the primitives are missing — names it on the health page, refuses to start below the configured minimum outside dev, and records it permanently on every artifact validated under it. A reviewer needs to know what the green tick was worth.
- **The audit log cannot be edited.** Append-only, hash-chained, with the chain head anchored externally. Nothing in MAYA — not an administrator, not a migration — can alter an entry.

---

## Legal

© 2026 Ashutosh Sinha. All rights reserved. MAYA — including all source code, specification and design documents, data models, algorithms, build tooling, brand assets, the MAYA name and the MAYA mark — is the exclusive property of Ashutosh Sinha. This software is **proprietary and confidential**; unauthorized copying, modification, distribution, or use, in whole or in part, is strictly prohibited without express written permission. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY ARISING FROM THE USE OF THIS SOFTWARE.

---

## Contact

**Ashutosh Sinha** · ajsinha@gmail.com · https://github.com/ajsinha/maya

---

**MAYA** — Model &amp; AI Lifecycle Assurance · *Evidence, not assertion.* · © 2026 Ashutosh Sinha
