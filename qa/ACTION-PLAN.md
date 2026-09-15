<!--
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
-->

# QA pass 1 — the action plan

**166 findings, grouped into twelve batches by what has to change rather than by
where it was found.** A batch is a coherent edit: one decision, one pattern, one
sweep, one re-run. Several findings in different sections turn out to be the
same defect, and fixing them apart would mean deciding the same thing twice and
possibly differently.

Every id below is a runnable case. `python -m qa.regression_suite.scenario_run
--only <id>` reproduces it, and the same command is how a fix is checked —
there is no separate reproduction to write, and no finding here rests on a
description of a defect rather than on one.

**The order is not severity.** It runs smallest-and-sharpest first, so the
early batches build confidence in the loop before the large mechanical one, and
the two batches that need the most care come last. Drill once per batch.

---

## The order

| | Batch | Findings | Why here |
|---|---|---|---|
| **1** | **C** — Identity compared with `==` instead of `same_person` | 5 | smallest, sharpest, and a segregation-of-duties hole |
| **2** | **D** — A read scoped on `?urn=` and unscoped on `/{id}` | 6 | four instances of one leak, one helper closes them |
| **3** | **B** — A control that is built, wired, documented and never fires | 21 | the recurring defect; every fix is connect-or-delete |
| **4** | **A** — A required field accepted blank, absent or impossible | 37 | one pattern, ~37 sites, mechanical once the first is written |
| **5** | **F** — Authority bands, delegation, quorum and conditions | 9 | a tier 1 version was approved by one person |
| **6** | **E** — The evidence chain's edges: checkpoint, anchor, timestamp | 14 | what an investigation rests on |
| **7** | **H** — HTTP conventions: paging, projection, headers, refusal shape | 6 | one adoption problem behind six symptoms |
| **8** | **I** — Concurrency, the scheduled batch and delivery | 7 | a half-run batch is worse than no batch |
| **9** | **G** — Documents: compile, dossier, pack, review, search | 20 | the pack is what leaves the building |
| **10** | **K** — Deletion, compaction and the operational tools | 4 | the reclaim path is unreachable today |
| **11** | **L** — Distributed evaluation, monitoring and parameter provenance | 11 | narrower blast radius, needs the most care |
| **12** | **J** — Lifecycle and workflow correctness | 26 | largest, most independent, safest to do last |

---

## 1. Batch C — Identity compared with `==` instead of `same_person`

`principal == other` where the platform has `same_person`. Two spellings of
one identity defeat segregation of duties, and this is the same defect the
review recorded once already. One sweep, one helper, one discipline test that
fails the build on a bare `==` against an identity.

| Case | What it found |
|---|---|
| `QA-GOV-145` | a delegation recorded for 'person/risk' grants nothing to the principal who authenticates as 'risk': `held_by` matches the principal column as a STRING, so the two spellings of one human … |
| `QA-PLT-150` | the raiser closed their own factual objection by writing their name as 'person/validator' instead of 'validator'. The check is `raised_by == actor`, not `same_person`, so seven characters… |
| `QA-PLT-195` | a generation created by `system` was attested by `system`. Attestation is a person taking responsibility for machine output, and the `created_by` is-not-system carve-out — which exists so… |
| `QA-PLT-2700` | 10 duties comparison(s) use `==`/`!=` on an identity rather than `same_person`, so each is stepped around by writing the same human the other way: core/authz/breakglass.py:151 if actor ==… |
| `QA-PLT-2702` | the person who asked for a break-glass elevation authorised it by writing their name as 'person/risk' instead of 'risk'. Dual authorisation with one person is one person, and the check is… |

## 2. Batch D — A read scoped on `?urn=` and unscoped on `/{id}`

The same shape on four registers: `?urn=` passes the model to the authoriser
and `/{id}` does not. A finding id, a document id and a search result are all
identifiers that travel in notifications and board packs, so the caller
holding one is routinely somebody the scope was meant to stop.

| Case | What it found |
|---|---|
| `QA-AM-079` | the answer is short by 7 and says nothing about it: no count of what scope removed, and no `detail` saying the total is partial — so a reader reconciling against an estate-wide pack sees … |
| `QA-AM-080` | the urn path refused 'out_of_scope' and the id path answered 200 with the finding — severity 'High', owner 'person/owner', 'The other entity's model failed challenge'. The route authorise… |
| `QA-PLT-122` | the report names the dimensions and not the rows — a version's entity is its model's, and no policy here expresses that |
| `QA-PLT-134` | `GET /api/v1/documents/{document_id}` authorises `document:read` with NO model, while `GET /api/v1/documents?urn=` passes one and refuses this reader 'out_of_scope'. So a principal scoped… |
| `QA-PLT-176` | `search(principal=None)` with an authoriser wired returned 1 result(s) across 1 document(s) — `_visible` applies the filter only `if self.authz is not None and principal is not None`, so … |
| `QA-PLT-335` | a key scoped to `model:read` alone read 4 route(s) that take no permission — ['/api/v1/document-kinds', '/api/v1/document-subjects', '/api/v1/model-relations', '/api/v1/export-packs']. Th… |

## 3. Batch B — A control that is built, wired, documented and never fires

The recurring defect of this codebase, at **21** instances. A control exists,
is wired, is documented, and never runs: no route reaches it, the code it
raises is in no status map, the vocabulary offers a state nothing writes, or a
key is read that nothing writes. Fix each by either connecting it or deleting
it — a control nobody can reach is worse than an absent one, because the
documentation says it is there.

| Case | What it found |
|---|---|
| `QA-AM-1314` | published as not-distributable but absent from the test catalogue, so no monitor can ever carry it and the refusal can never fire: calibration.hosmer_lemeshow |
| `QA-AM-4720` | no route binds a monitor to a version: `MonitorIn` has no version field, the create route never passes `model_version_id`, and seeding the defaults created 0 monitor(s) with none either. … |
| `QA-FX-385` | `note_revocation` accepts a `warrant_id`, and the id moves: two resolutions of one grant minted 01a0a27c618aeb7e… and 01a0a27c618b5977…, so an id noted from one never matches the one `exe… |
| `QA-FX-401` | `clamp` is one of the 3 policies a version may declare (['clamp', 'flag', 'reject']) and it is accepted at registration, and the word does not appear anywhere in the execution engine. The… |
| `QA-FX-405` | a contract clause whose key no input supplies is correctly not a violation, and `Contract.unchecked_inputs` names it — ['ltv'] — but the engine only LOGS it. `ExecutionResult` carries `bo… |
| `QA-GOV-192` | with no use register wired the trigger answers None, which the reading renders as *did not fire* — indistinguishable from a model nobody added a use to. `_cannot_check` exists for exactly… |
| `QA-GOV-193` | with no breach register wired the trigger answers None, which reads as *no breach since the assessment* — the one answer a monitoring-off estate must not be given |
| `QA-GOV-200` | the sweep found the stale assessment and raised no finding. `_raise` calls `raise_finding(model_id=..., title=..., severity=..., source=..., detail=..., actor=...)` and the register's sig… |
| `QA-GOV-4608` | the consumer reading reports nothing downstream for a model that is read by another — the graph reaches 1 model(s) under the key `reaches`, and `consumers()` reads `reached` |
| `QA-PLT-092` | refused with a bare RuntimeError carrying no code, no detail and no remediation, so `Routes.guard` cannot map it and a route reaching it answers 500. Latent rather than live: the folded t… |
| `QA-PLT-097` | the repository refuses 'append_only' with a detail and a remediation, and neither half of the taxonomy receives it: NOT in STATUS, NOT caught by Routes.guard. It is a bare RuntimeError, s… |
| `QA-PLT-098` | 7 anchor and WORM refusal codes are mapped in STATUS — ['anchor_disagreement', 'anchor_unreadable', 'chain_broken', 'nothing_to_anchor', 'worm_overwrite_refused', 'worm_unreadable', 'worm… |
| `QA-PLT-110` | an unwritable anchor root raises a bare PermissionError with no code, no detail and no remediation — `put` catches nothing around `write_bytes`, while `get` wraps its OSError as `worm_unr… |
| `QA-PLT-111` | the refusal is correct and its remediation says *configure one under `evidence.timestamps`* — and nothing reads that key. `ChainTimestamps` is constructed with `authority=None, verifier=N… |
| `QA-PLT-143` | 'superseded' is one of the 4 states the review vocabulary publishes at GET /api/v1/document-review/asks, and no code path in `core/docs/review.py` writes it — `comment` opens, `resolve` w… |
| `QA-PLT-163` | the service serves the pack and NO ROUTE reaches it: `open_share` is called from nowhere but a unit test, so a share can be created, listed and revoked and never opened. Tried /api/v1/exp… |
| `QA-PLT-229` | a manifest declaring `manifest_version: 99` — a version this build does not write (it writes 1) — was restored without a word, while a manifest missing a SECTION is refused by name. The v… |
| `QA-PLT-268` | a sweep saying nothing about recall was admitted. The contract tests `"recall_known" not in sweep`, and the route model declares it `Optional[bool] = None`, so `model_dump()` always suppl… |
| `QA-PLT-2801` | 28 actionable refusal code(s) of 773 raise sites carry an explicitly empty remediation, so a caller who did something they could have done differently is told what and not what instead: a… |
| `QA-PLT-4701` | `core_state` reads ['documents'] from the model context, which does not carry it — the context holds ['alias_history', 'assessment', 'assumptions', 'attachment_status', 'attachments', 'ch… |
| `QA-PLT-4780` | a write carrying the CURRENT tag was refused 'precondition_unevaluable', so no conditional write can succeed |

## 4. Batch A — A required field accepted blank, absent or impossible

Fix at the SERVICE, not the route. A body model can only refuse a field that
is absent; `"   "` is present. Every one of these is a required value the
register accepted as blank, absent, negative or outside a closed vocabulary —
and each leaves a row that reads as governed. The pattern is already written
down in `raise_finding`: strip, then refuse, naming what the field is for.

| Case | What it found |
|---|---|
| `QA-AM-019` | an episode with a failed test concluded 'approved_with_conditions' and NO conditions. `_check_approvable` runs only for 'approved', so the route the failure refusal points a validator tow… |
| `QA-AM-1701` | an episode that examined nothing concluded 'approved_with_conditions'; the no-results check guards 'approved' alone, so an unexamined model can be passed under a neighbouring outcome |
| `QA-AM-195` | accepted at definition and refused at evaluation ('validation_refused'): `define` tests only that the threshold dict is non-empty, so a monitor written with the wrong vocabulary reads as … |
| `QA-AM-198` | `escalate_after: -1` was accepted and stored: nothing validates the field, and 0 already means *never escalate*, so a negative is a number with no reading that goes into the escalation ar… |
| `QA-AM-251` | an AUC over a stated sample of 0 was accepted and the observation says nothing about it: `sample_size` defaults to 0, so *the job did not say* and *it computed this over nothing* are the … |
| `QA-AM-626` | expected a refusal (overlay_refused/owner_required/validation_error) and the answer carried no error code: 201 {"id":"01a09b8f5b39b0a5aa432afe6f63","model_id":"01a09b8f5b352a7819b27f29f30… |
| `QA-AM-631` | expected a refusal (validation_error/supervisor_required/matter_refused/regime_refused) and the answer carried no error code: 201 {"id":"01a09b8f5b506d55238e557b4304","reference":"SUP-202… |
| `QA-AM-632` | expected a refusal (validation_error/owner_required/matter_refused/regime_refused) and the answer carried no error code: 201 {"id":"01a09b8f5b561cf199b921e80017","reference":"SUP-7ca2197d… |
| `QA-AM-646` | a board pack was cut with no period; the figures in it describe no stated span of time |
| `QA-AM-701` | a replay ran against no episode |
| `QA-AM-743` | a test reported over no observations at all; a metric computed from nothing reads as a metric |
| `QA-AM-801` | a campaign was opened with nothing to cite it by |
| `QA-FX-4850` | the browser upload control offers '.json' and the API will not read 'json': `accept_attribute` builds its list from a hand-written tuple rather than from UPLOAD_FORMATS, so the two vocabu… |
| `QA-FX-700` | a feature with no name was accepted, and a feature nobody can name is one nobody can cite |
| `QA-FX-701` | a feature with no owner was accepted, and an unowned feature is one nobody maintains |
| `QA-FX-702` | a feature of an unknown dtype was accepted, and the dtype decides how every later comparison behaves |
| `QA-FX-703` | a feature with no entity was accepted, and the entity is what a row is keyed on |
| `QA-FX-704` | a feature with no description was accepted, and a business definition is what stops two teams meaning different things by one name |
| `QA-FX-705` | a negative ttl was accepted, and a negative lifetime is a row that expired before it arrived |
| `QA-FX-800` | expected a refusal (validation_error/parameter_refused/name_required) and the answer carried no error code: 201 {"id":"01a09b8f641b04d2bffb565966c5","model_id":"01a09b8f6414272fae9ae9d5b9… |
| `QA-FX-807` | 500 — an unknown id crashed the review |
| `QA-FX-900` | a featureset nobody can name was created |
| `QA-FX-901` | a featureset was created with nothing to key rows on |
| `QA-FX-941` | an elicitation with no facilitator; the one role that makes a panel's answer attributable |
| `QA-FX-954` | expected a refusal (feature_refused/reason_required/validation_error/discovery_refused) and the answer carried no error code: 200 {"id":"01a09b8f64d143eef0118dbdff8e","view_name":"tv-783f… |
| `QA-GOV-017` | a model was registered belonging to no legal entity, so no entity-scoped principal can reach it and nobody is accountable for it |
| `QA-GOV-080` | these are not semvers and were accepted: ['1.0', 'v1.0.0', '1.0.0.0', 'one.two.three', '', '1.0.x'] |
| `QA-GOV-2200` | a ceiling was recorded with no currency, so the number means whatever the reader assumes |
| `QA-GOV-514` | expected a refusal (unknown_role/validation_error/authority_refused/lifecycle_refused) and the answer carried no error code: 201 {"id":"01a09b8f67ec73569c81d8537461","name":"band-230fe8a1… |
| `QA-GOV-520` | a ceiling was accepted with no currency; the comparison it governs is then between a number and an amount |
| `QA-GOV-525` | a campaign opened over nobody; it completes immediately and reads as a clean recertification |
| `QA-PLT-158` | `max_reads: 0` was stored as None: the guard is `if max_reads`, and zero is falsy, so asking for NO permitted reads produces a share with NO LIMIT — the exact inverse of the request, and … |
| `QA-PLT-159` | `max_reads: -1` was accepted and the share is born exhausted: nothing validates the field, so a typo produces a link that refuses every read and reads on the register as one somebody used up |
| `QA-PLT-162` | an expired share reports -10.0 days left: a negative number sorts on a list as the link with the longest to run |
| `QA-PLT-518` | a negative page size was accepted |
| `QA-PLT-5406` | a share was revoked with no reason recorded — `revoke` strips the reason and never checks it, so the record says a firm stopped serving a supervisor a copy and not why |
| `QA-PLT-5903` | an operator outside the closed set was accepted and behaved as `eq` — so a caller asking for `like` gets exact match semantics, and a filter that means something different from what was w… |

## 5. Batch F — Authority bands, delegation, quorum and conditions

Publishing one authority band replaces the shipped rows, so every tier the
matrix does not reach loses its quorum — a tier 1 version was approved by one
person. The rest of this group is the same register: a delegation with no
band, a role deleted while a band names it, a condition reference unique
estate-wide but numbered per model.

| Case | What it found |
|---|---|
| `QA-GOV-118` | a band was published with an empty stage, so one step of the sequence is satisfied by nobody |
| `QA-GOV-126` | publishing one tier 3 band removed the shipped bands ['tier-1', 'tier-2'] from the matrix: the matrix is `published or DEFAULT_BANDS`, so the first band a firm publishes silently drops th… |
| `QA-GOV-127` | a tier 1 version was approved by ONE person. `banded()` returns `required_for(urn)` whenever ANY matrix is published, and that answer carries `required_roles: []` for a model no band reac… |
| `QA-GOV-132` | a figure attested as at a date a year away decides today's band: the amount reads 1000.0 and the band is 'bd-3f307677'. `amount_for` takes the greatest `as_at` and nothing refuses one in … |
| `QA-GOV-140` | a 1 USD ceiling signed off a 250,000,000 exposure because no band is published: `refuse_beyond_delegation` runs only inside `if approval.get('band')`, and nothing in the estate view says … |
| `QA-GOV-165` | `conditions` reads 2, an integer. `for_model` builds `{"conditions": rows, ...}` and then spreads `**self.evaluate(urn)` over it, and `evaluate` answers `conditions: len(rows)` — so the s… |
| `QA-GOV-217` | the override was accepted and no route that lists principals says an exception was made: `conflicts_allowed` goes onto the evidence chain payload and onto no column, so listing who holds … |
| `QA-GOV-225` | the role 'role-8de6ce58' was deleted while a published band names it as a required signature: `_awaited_by_a_quorum` reads the open attestation and version_approval tables only, so the ma… |
| `QA-GOV-4620` | the second model in the estate to be approved on terms crashes with 500: the reference is numbered per model and the unique index is over the whole table, so COND-0001 can exist once. Con… |

## 6. Batch E — The evidence chain's edges: checkpoint, anchor, timestamp

The checkpoint loses touch with the chain four ways, the anchors bound it from
below and nothing bounds it from above, and two node columns sit outside the
content hash. None of these is exploitable without database access; all of
them are what an investigation would rest on.

| Case | What it found |
|---|---|
| `QA-PLT-014` | the checkpoint was moved to seq 511, five hundred beyond a chain that ends at 11, and the cheap check answers valid over 0 node(s) checked. `repo.since(mark)` returns nothing, `_walk` ove… |
| `QA-PLT-016` | both ['engine', 'scheduler'] record the checkpoint as `report['length']` (11) rather than the head sequence (11). They agree here only because this chain is contiguous from 1. After any r… |
| `QA-PLT-017` | twelve verifications wrote 12 checkpoint row(s) (0 → 12) and nothing in `EvidenceEngine` removes one. Only `first('seq', desc=True)` is ever read, so every row but the newest is dead weig… |
| `QA-PLT-019` | the chain was restored to seq 10 and the checkpoint still reads 13, three ahead of it. The cheap check answers valid over 0 node(s) — `since(mark)` finds nothing past a mark the chain no … |
| `QA-PLT-025` | 4 node(s) appended above the newest anchor (seq 12) were deleted, and nothing notices: the full walk is valid over 12 node(s) and the anchors agree over 1 of them. An anchor bounds the ch… |
| `QA-PLT-026` | 1 anchor(s) were deleted from /tmp/maya-qa-vawjm7kh/data/worm and `verify_against_anchors` answers anchored=0, agrees=1: 'no anchors written yet, so the chain is self-certified and nothin… |
| `QA-PLT-027` | the entire anchor root was removed and the next anchor recreated it (/tmp/maya-qa-sjtc7p8l/data/worm) and wrote seq 13 into it, reporting written=1. `FilesystemWORM.put` opens with `root.… |
| `QA-PLT-034` | an authority returned a token dated a year ahead of the request and it was stored and read back with state 'unverified' and no remark. `stamp` records `requested_at` alongside the token a… |
| `QA-PLT-035` | a token whose validity ended nine years ago was stored and is counted in coverage: 1 of 1 anchored head(s) 'carry a token'. Nothing in `stamp` looks at the token at all — not `genTime`, n… |
| `QA-PLT-039` | the bytes under sha256:4cadb37ba59f5b2b… were replaced. `GET /api/v1/artifacts/{digest}/verify` re-hashes and reports intact=False with recomputed sha256:c6b2fe0c1ae01eb7…, and `GET /api/… |
| `QA-PLT-099` | a node's `recorded_at` was moved by 9,999 seconds and the chain still verifies: the timestamp is outside the content hash, so WHEN a governance act was recorded can be rewritten with a si… |
| `QA-PLT-100` | 'contains_personal_data' was flipped on a node and the chain still verifies: it sits outside the content hash, so the chain hash does not move and the anchors cannot see it either. The fl… |
| `QA-PLT-103` | a claim resting on a present fact and a MISSING one answers freshness 1000.0, the same as one resting on that fact and a stale one. FRESHNESS is (max, max) with `zero = 0.0`, so an absent… |
| `QA-PLT-117` | the trigger refuses the raw UPDATE, which is correct — and `tests/test_postgres_dialect.py::test_a_tampered_payload_breaks_the_chain_on_postgres_too` performs exactly that UPDATE through … |

## 7. Batch H — HTTP conventions: paging, projection, headers, refusal shape

One root: the conventions were built and almost nothing adopted them.
`conventions.page` has one caller, `project()` empties every listing that does
not name its rows `rows`, nothing sets `Retry-After`, and the most-used
`not_found` builder omits its remediation.

| Case | What it found |
|---|---|
| `QA-PLT-089` | `?fields=` discards the rows of 12 of 12 listings sampled, and keeps none: ['/api/v1/models', '/api/v1/features', '/api/v1/featuresets', '/api/v1/warrants', '/api/v1/principals', '/api/v1… |
| `QA-PLT-090` | one guarded write dispatched 1 GET(s) to its own path through the router. The precondition is real and this is what it costs: every `If-Match` write is two trips through routing, authoris… |
| `QA-PLT-358` | `?fields=invented_field` answers 2 empty object(s) with 200 and no refusal. The only thing distinguishing it from a listing of rows that genuinely have no values is `projected_to: ['inven… |
| `QA-PLT-360` | page one and page two share 1 row(s) after one registration between the two reads: ['maya://model/hc-b3676b18']. `/models` pages with LIMIT/OFFSET, so an insert that sorts before the boun… |
| `QA-PLT-361` | 4 refusal code(s) map to 429 — ['budget_exhausted', 'cost_limit_reached', 'quota_limit_reached', 'rate_limit_reached'] — and no route or service anywhere sets a `Retry-After` header. The … |
| `QA-PLT-362` | 1 of 5 coded refusal(s) omit a part: ["unknown model (not_found): missing ['remediation']"] |

## 8. Batch I — Concurrency, the scheduled batch and delivery

Races and the batch that turns derived conditions into records. A lock while
RECORDING a job's result aborts the whole pass; deduplication is keyed on a
title somebody edits; two sweeps mint one reference.

| Case | What it found |
|---|---|
| `QA-GOV-083` | approving an approved version wrote a second `version_approved` node: the chain now says this version was approved 2 times, and an examiner counting approvals counts decisions that were n… |
| `QA-PLT-063` | 1 of 4 racing writes answered 500 with no code: Internal Server Error |
| `QA-PLT-087` | a caller who abandons a request every 15 minutes keeps the key alive indefinitely: eleven abandonments later it is 0.00 hours old by `started_at` and the 24-hour sweep does not reach it. … |
| `QA-PLT-240` | a lock while RECORDING the second job's result aborted the whole batch with RuntimeError: database is locked. `Scheduler._one` wraps `job.run(context)` in a try — one job must not stop fo… |
| `QA-PLT-246` | `_already_raised` matches `f['title'] == title`, so a finding whose title a person edited is no longer recognised as the one the job raised: the check answers False and the next run raise… |
| `QA-PLT-251` | 1 reference(s) are held by more than one row after two concurrent sweeps: ['DISC-0004']. `ingest` mints `DISC-{n:04d}` from a count of the rows already there, so two sweeps that read the … |
| `QA-PLT-254` | 30 failure(s) recorded and summarised, and recovery sends — all correct. What is not: `_deliver` calls `transport.send` outside any try, and the contract that makes that safe is that a ch… |

## 9. Batch G — Documents: compile, dossier, pack, review, search

`gaps.md` reads a key nothing writes, an unreadable source is reported as an
absence, and the coverage figure a reader is told to check first can be moved
four ways that have nothing to do with filing readable documents. The pack is
what leaves the building.

| Case | What it found |
|---|---|
| `QA-PLT-130` | the monitoring service raised while this pack was cut and `gaps.md` does not mention it. `ContextBuilder` records what it could not read under `ctx['unreadable']`; `ExportPacker.build` re… |
| `QA-PLT-132` | a document row whose `subjects` list is empty falls back to the model id alone, so a new version — the event a document most needs to notice — leaves it reporting 'nothing has been record… |
| `QA-PLT-138` | a 'declared' parameter set names a featureset version the register cannot resolve, and the dossier records no gap for it. `_pin` returns (None, None) for an unresolvable id — the same val… |
| `QA-PLT-139` | both states print the same sentence: "a fitted set that does not name the featureset version it came from — 'what data produced these numbers' has no answer from here". It is false for th… |
| `QA-PLT-140` | the attachment register raised for every subject and the dossier records 1 gap(s) all saying 'nothing is filed here; expected the methodology, and the literature the approach'. `_attached… |
| `QA-PLT-144` | a resolved comment was withdrawn, erasing the answer somebody gave it |
| `QA-PLT-145` | a comment was withdrawn with no reason at all and the record now reads state='withdrawn' resolution=''. `resolve` refuses exactly this — 'closing a comment needs a sentence about what was… |
| `QA-PLT-146` | `withdraw_comment` authorises `document:read` where `comment` authorises `document:review`. Somebody else is stopped by the register rather than by the route — 'not_your_comment' — so the… |
| `QA-PLT-148` | a comment was resolved citing 'evidence-node-that-never-existed', which is in no chain, and the act was recorded with `changed_the_record: true` — it is `bool(evidence_id)` with no existe… |
| `QA-PLT-152` | `pack_too_large` is raised at source line 90 and `self._zip(members)` runs at line 89 — the whole archive is built, compressed and held in memory before its size is measured against the 2… |
| `QA-PLT-154` | two attachments named 'report.pdf' whose digests agree on bytes 7:15 produced 1 archive member(s) — ['attachments/AAAAAAAA-report.pdf'] — while attachments/index.json lists 2. The name is… |
| `QA-PLT-169` | the same bytes filed twice — as `application/pdf` and as `text/plain` — move coverage from 0.0 to 0.5, because `text_indexed` is `media_type in TEXT_MEDIA` and the media type is whatever … |
| `QA-PLT-170` | a text-bearing PDF filed under its true media type is counted unread and stays unread: `text_indexed` is written once in `attach()` as `media_type in TEXT_MEDIA` and no route in the API w… |
| `QA-PLT-171` | an estate with nothing filed and a reader who may see nothing both answer coverage 0.0 over 0 document(s) with the identical sentence: 'no document has been filed against any model you ca… |
| `QA-PLT-172` | a search narrowed to one model answers 0 match(es) over 0 document(s) searched and 1 unread, while `GET /api/v1/document-search/coverage` — the figure the search's own detail line tells a… |
| `QA-PLT-173` | superseding an unread PDF with a 31-byte text note moved coverage from 0.0 to 1.0 (1 unread → 0) while the content it measured became unreachable: a term inside the superseded document no… |
| `QA-PLT-174` | a document the register rejected — state 'rejected', reviewed with 'wrong figure, do not use' — is returned by search with its text quoted back: 'the rejected figure is 99.9 percent'. `_c… |
| `QA-PLT-177` | the case itself raised ImportError: cannot import name '_match' from 'core.docs.search' (/home/ashutosh/PycharmProjects/maya/core/docs/search.py) | Traceback (most recent call last): File… |
| `QA-PLT-179` | `tests/test_documentation_links.py` asks each absolute link for its status and fails only on 404 — the comment says 3xx means the route exists, which is right, and a 500 is treated the sa… |
| `QA-PLT-4933` | a new version left the document reporting that nothing has been recorded since it was compiled, so the worklist's stale-document item never appears |

## 10. Batch K — Deletion, compaction and the operational tools

Compaction cannot complete on any store that has ever held an artifact, a GOES
disposition cannot fire, and every non-SQLite dialect is handed PostgreSQL
instructions.

| Case | What it found |
|---|---|
| `QA-DEL-054` | the GOES disposition on `model_limitation` and `model_assumption` cannot fire through the delete route. Both rows carry a NOT NULL `model_version_id` ({'model_limitation': False, 'model_a… |
| `QA-DEL-071` | the first sweep marked 2 candidate(s) and the second raised 'malformed_digest': 'sha256:c5605778ec7d8f64d896739d668272c40da8df6e8b83c543e3fbf2bb37b4b73f.fmt' is. The marks include the `<d… |
| `QA-PLT-093` | a raw UPDATE landed during a fold and the fold went on answering 'fold-495e2985' while the table said 'renamed by a raw statement'. `_refuse_write_while_folding` is called from `Repositor… |
| `QA-PLT-222` | the tool branches on `not dialect.startswith('sqlite')` and every non-SQLite dialect is told about `pg_dump` and `pg_basebackup`. An operator on MySQL, Oracle or a typo in the URL is hand… |

## 11. Batch L — Distributed evaluation, monitoring and parameter provenance

The distributed and monitoring edges, plus parameter provenance: a submission
that is computed and not judged, an evaluation that leaves no trace, an epoch
that moves once per grant.

| Case | What it found |
|---|---|
| `QA-AM-064` | the case itself raised IntegrityError: (sqlite3.IntegrityError) NOT NULL constraint failed: dataset_snapshot.as_of [SQL: INSERT INTO dataset_snapshot (name, delta_table, delta_version, ro… |
| `QA-AM-1312` | the submission computed 3.9385 and the outcome carries no comparison to the threshold at all — no breach, no status, not even the threshold it was supposedly compared against. `posture()`… |
| `QA-AM-1313` | the submitted evaluation left no trace on the monitor; the estate-wide sweep computes numbers the register does not keep |
| `QA-AM-270` | the plan digest is recomputed at submit time and the SUBMISSION's partition count is inside the digested plan, so a job that splits its scan differently from the 64 the plan defaulted to … |
| `QA-AM-404` | the case itself raised AttributeError: 'Nothing' object has no attribute 'debts' | Traceback (most recent call last): File "/home/ashutosh/PycharmProjects/maya/qa/regression_suite/scenari… |
| `QA-FX-232` | the delivery path does not refuse a fitted set over a terminal parameter object, so the type error is enforced on the warrant route only |
| `QA-FX-237` | the case itself raised TypeError: ParameterRegister._refuse_unverified_snapshot() missing 1 required positional argument: 'provenance' | Traceback (most recent call last): File "/home/ash… |
| `QA-FX-238` | the case itself raised TypeError: ParameterRegister._refuse_unverified_snapshot() missing 1 required positional argument: 'provenance' | Traceback (most recent call last): File "/home/ash… |
| `QA-FX-382` | a descriptor carrying no revocation epoch bypasses the floor entirely: `_refuse_stale_epoch` returns early when `stamped is None`, and all four shapes of absence — no `authority`, no `rev… |
| `QA-FX-386` | withdrawing one model's authority moved the estate-wide epoch by 4 (0 → 4), one per grant. `revoke_model` loops `revoke`, and `revoke` does `self.epoch += 1` — so a model with forty grant… |
| `QA-FX-387` | revoking a model nobody holds a grant on reports `revoked: 0` and leaves the epoch at 0. `revoke_model` advances the counter inside the per-grant loop, so an empty withdrawal advances it … |

## 12. Batch J — Lifecycle and workflow correctness

Ordinary workflow correctness — an episode, a waiver, a decommission, a
recertification behaving wrongly at an edge. Individually small, collectively
the largest group, and the one a user meets.

| Case | What it found |
|---|---|
| `QA-AM-006` | the episode concluded and its reading still reports `independent` on the strength of a validator suspended before the conclusion; nothing in the record says so, so a supervisor reading th… |
| `QA-AM-024` | accepted at open and discovered only at replay ('validation_refused'): the episode carries a pin to 'snap-does-not-exist' for as long as nobody replays it, and the failure lands on whoeve… |
| `QA-AM-026` | one validator is recorded twice: ['person/validator', 'person/validator'] and the capacity view has them carrying 8 episodes. The capacity view appends the episode once per entry, so a du… |
| `QA-AM-027` | an episode opened a week overdue is stored with that date and read by nothing: the queue and the backlog both compute what falls due from the re-validation triggers, so `due_at` is writte… |
| `QA-AM-031` | value 0.0 passed a threshold declaring max -0.5: the evaluator returns on `min` and never reads `max`, so a validator who declares a band gets one end of it checked and the detail — 0 mee… |
| `QA-AM-089` | an acknowledgement refused `beyond_the_due_date` still recorded its plan — `plan_for` runs before the date check — so acknowledging again with NO plan is accepted. A refused act left a du… |
| `QA-AM-117` | a finding closed with `{"note": ""}`: the check is `if not evidence`, which is truthiness on the dict and not on anything in it, so a closure with nothing written down is recorded as evid… |
| `QA-AM-138` | a finding under root 01a09c9a5cbe610db80174ba5067 was moved to root 01a09c9a5cc01f60ccb5a8995814 by a call that never mentioned the first: `attach` writes `root_id` without asking whether… |
| `QA-AM-173` | a waiver whose window had already run became 'active': `expires_at` is set at PROPOSE time and `approve` does not check it, so a waiver that waited out its own window in the approval queu… |
| `QA-AM-180` | renewing shortened the window by 50 days: `renew` sets `expires_at` to now + days rather than extending from the existing expiry, so renewing a waiver early takes time away from it under … |
| `QA-AM-187` | a proposal whose window ran out is still 'proposed' after the expiry sweep, which only looks at active waivers. It stays proposed for ever and can still be approved into an exception that… |
| `QA-AM-401` | an item expiring at this instant is already a breach; every other window in this platform leaves the boundary itself inside |
| `QA-AM-407` | a monitor evaluated exactly 3 cadences ago is already reported stalled. `overdue_by` is 3 - 1 = 2 cadences and the guard is `overdue_by < cadence * (MULTIPLE - 1)`, so the boundary itself… |
| `QA-FX-039` | an empty version was pinned with nothing marking it empty: whatever assembles from it gets an empty frame, and the refusal lands on somebody who did not send the load |
| `QA-FX-1208` | retiring 'prof-f1b4abb0' left version 1 live — retire marks the current version, so the previous one is uncovered and the profile goes on filling in defaults under a name the register rep… |
| `QA-FX-135` | a lineage 14 deep was defined, past the stated 12 limit. The limit is enforced only inside `provenance`, the recursive walk — which does refuse it, so the chain exists and the question th… |
| `QA-FX-142` | 'a * b' over {'a': 1e+308, 'b': 10.0} evaluates to inf. Every other arithmetic failure here answers null or refuses; an infinity is neither, and it propagates through every mean, sum and … |
| `QA-GOV-045` | a declined attestation moves the record approved -> draft and approved -> amending, and the published machine names no such edge. An examiner reading GET /lifecycle cannot see that declin… |
| `QA-GOV-173` | three spaces discharged a periodic review: the same numbers, re-POSTed, moved the next review date with nothing examined — and `review_note` is stored inside `facts`, so the note is compa… |
| `QA-GOV-203` | 4 models share a cause and the sweep raised nothing, so there is nothing to correlate — see QA-GOV-200 for why |
| `QA-GOV-258` | a confirmed item was answered again as revoked and only the last answer is reported (0 confirmed, 1 revoked): nothing refuses re-answering an item, so what a reviewer first said is not on… |
| `QA-GOV-280` | a model was recorded as its own replacement: the replacement check asks only whether the URN is registered, and the model being retired always is, so the record names a retired model as t… |
| `QA-GOV-282` | 'maya://model/dc-361622dc' is retired and was accepted as the replacement: the check asks whether the URN is registered and never whether it is in service, so the successor chain points a… |
| `QA-GOV-4605` | a model another one reads was decommissioned with its consumers neither notified nor acknowledged — `blast_radius` answers `reaches` and `consumers()` reads `reached`, so the list is alwa… |
| `QA-GOV-4650` | refused 'registry_refused' — a well-formed digest the store does not hold is how a vendor model is registered at all |
| `QA-PLT-200` | both refuse 'nothing_grounded', so a cautious generation and a wholly unsupported one are one fact |

---

## After the twelve

Re-run the whole suite, not the batches. A fix that closed its own case and
broke a neighbour is the outcome this pass exists to catch, and the only way to
see it is the full run:

```bash
.venv/bin/python -m qa.regression_suite.scenario_run
.venv/bin/python -m qa.regression_suite.summary
```

Then the 33 rows still marked *needs-case*, and the 558 published cases that
have not been run.

## What is deliberately not here

**The three rows docs/11 keeps open under ADR-016.** H-2, H-9 and §4.9 are one
finding in three costumes, inert under one topology and live under another.
They stay open rather than accepted so that somebody planning a multi-process
deployment still finds them.

**Findings recorded as limitations rather than defects.** Nothing dedupes a
human-raised finding; no status vocabulary is checked on the findings register;
the tiering lattice cannot rank a non-financial harm above a financial one.
Each is written down where it was found, and each is a decision rather than a
repair.
