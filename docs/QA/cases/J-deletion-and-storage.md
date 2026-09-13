## J. Deletion, tombstones and storage reclamation

Hand-written cases for the one act with no workflow, no reversal and no second
signature — and for the two things that happen around it: the cascade over the
other thirty-seven tables carrying a `model_id`, and the reclamation of bytes
nothing references any more.

**The failure this section is really about is not a failed deletion.** It is a
*successful* one followed by a registration. Delete `pd-retail`, register a new
model called `pd-retail`, and every evidence node, closed finding and amendment
naming that URN now reads as though it described the new model. `verify_chain`
passes throughout, because the chain is intact — it is simply about something
else, and no integrity check that operates on hashes can ever see that. Cases
QA-DEL-020 through QA-DEL-027 are that attack.

The second theme is the one that produced this subsystem: **a reference check
that misses a table does not fail, it approves.** Four tables were never read,
and the test guarding against exactly that passed because their names appeared
in prose. Cases QA-DEL-040 onward walk every disposition.

| ID | Area | Case | Expectation | Steps | Why it matters |
|---|---|---|---|---|---|
| QA-DEL-001 | `deletion` | Delete as a non-administrator holding `model:delete` | **refused (deletion_refused, 403)** | grant `model:delete` to a non-admin role; DELETE /models/{name} | the role is checked as well as the permission, so a mistaken grant has to be made twice |
| QA-DEL-002 | `deletion` | Delete with an empty reason | **refused (reason_required, 422)** | DELETE /models/{name} with `reason=""` | an irreversible act with no stated cause is unauditable afterwards |
| QA-DEL-003 | `deletion` | Delete with a whitespace-only reason | **refused (reason_required, 422)** | DELETE with `reason="   "` | `.strip()` must be applied, or the check is decorative |
| QA-DEL-004 | `deletion` | Delete a model covered by a model-scoped legal hold | **refused (under_legal_hold, 423)** | place a hold scoped to the model; DELETE | deleting through a hold is spoliation |
| QA-DEL-005 | `deletion` | Delete a model covered by an estate-wide hold | **refused (under_legal_hold, 423)** | place an estate hold; DELETE any model | an estate hold is a blunt instrument on purpose |
| QA-DEL-006 | `deletion` | Delete a model whose hold was placed by URN rather than id | **refused (under_legal_hold, 423)** | place a hold with `scope_id` = the model's URN; DELETE | this was a real defect: the hold resolved against `model_id` and a URN never matched, so the hold was inert |
| QA-DEL-007 | `deletion` | Delete after the covering hold is lifted | **accepted (200)** | place hold; lift with reason; DELETE | a lifted hold must actually stop refusing |
| QA-DEL-008 | `deletion` | Look for a `force` or `override` parameter on delete | **refused / absent** | read the OpenAPI for DELETE /models/{name} | a hold a deletion could step over would not be a hold |
| QA-DEL-009 | `deletion` | Delete a model that does not exist | **refused (404)** | DELETE /models/no-such-model | must not be the same answer as a successful deletion of nothing |
| QA-DEL-010 | `deletion` | Delete the same model twice | **refused (404 on the second)** | DELETE; DELETE again | the second call must not report success |
| QA-DEL-011 | `deletion` | Confirm the evidence node is appended before the rows go | **accepted; node present** | DELETE; GET the evidence chain filtered to `model_deleted` | a removal that fails halfway must still record who intended it |
| QA-DEL-012 | `deletion` | Verify the chain after a deletion | **reported valid** | DELETE; POST /evidence/verify | the chain survives the deletion by design |
| QA-DEL-013 | `deletion` | Delete on a deployment with no tombstone register wired | **refused (no_tombstone_register, 501)** | construct `LifecycleService` without `tombstones=`; call `delete` | degrading to a deletion that frees the URN is worse than failing |
| QA-DEL-014 | `deletion` | Read the `destroyed` counts on the deletion response | **accepted; counts present** | attach limitations and assumptions; DELETE; read `destroyed` | after the cascade there is nothing left to count |
| QA-DEL-015 | `deletion` | Confirm the response says storage was NOT reclaimed | **accepted; `storage_reclaimed` false** | DELETE; read the response | the bytes are a separate act, and saying otherwise is a claim the platform has not earned |
| QA-DEL-020 | `tombstone` | Register a model at a URN that belonged to a deleted one | **refused (urn_was_deleted, 409)** | register `pd-retail`; DELETE it; register `pd-retail` again | the whole reason the table exists |
| QA-DEL-021 | `tombstone` | Read the refusal's detail for the date and the actor | **refused; detail names both** | as above; read `detail` | somebody told *no* picks another name; somebody told *this belonged to a model Ana destroyed in March* knows whether that is a problem |
| QA-DEL-022 | `tombstone` | Register at a URN that never existed | **accepted (201)** | register a fresh name | a URN free because nobody used it is not a URN free because somebody destroyed what used it |
| QA-DEL-023 | `tombstone` | GET /tombstones/{urn} for a deleted model | **accepted; `deleted` true** | DELETE; GET /tombstones/{urn} | a historical reference must resolve to *there was one* rather than to nothing |
| QA-DEL-024 | `tombstone` | GET /tombstones/{urn} for a URN nobody ever used | **refused (no_such_urn, 404)** | GET /tombstones/urn:maya:model:never | conflating the two is how a mistyped name reads as a deletion |
| QA-DEL-025 | `tombstone` | Confirm the tombstone records the state deleted *from* | **accepted; `status` matches** | delete one model from `draft` and one from `retired`; compare | deleting a draft is housekeeping; deleting a retired model that made decisions for six years is not, and nothing else records which happened |
| QA-DEL-026 | `tombstone` | Confirm a deleted model does not appear in listings | **accepted; absent** | DELETE; GET /models | a tombstone is not a soft delete, and a record alive in one screen and dead in another is the failure mode of that pattern |
| QA-DEL-027 | `tombstone` | Attempt to transition, attest or approve a tombstoned URN | **refused (404 each)** | DELETE; POST each lifecycle transition | the marker carries none of the operational fields |
| QA-DEL-028 | `tombstone` | Look for a route that lifts or reverses a tombstone | **absent** | read the OpenAPI for tombstone paths | restoring would produce an empty model wearing a dead one's identity — the exact confusion the module prevents, arriving through the front door |
| QA-DEL-029 | `tombstone` | GET /tombstones as a principal without `evidence:read` | **refused (403)** | authenticate as a reader without the permission | |
| QA-DEL-040 | `cascade` | Delete a model with an outstanding campaign item | **refused (still_referenced, 409)** | add the model to a campaign; leave the item outstanding; DELETE | a campaign completes when every item is answered; an item naming a deleted model can never be, so the campaign never completes through any state a person can see |
| QA-DEL-041 | `cascade` | Delete a model with an *answered* campaign item | **accepted (200)** | answer the item; DELETE | historical references must not block, or the control is unusable |
| QA-DEL-042 | `cascade` | Delete a model with an unfinished validation | **refused (still_referenced, 409)** | open a validation; DELETE | verified defect: reported `deletable: true` with zero references |
| QA-DEL-043 | `cascade` | Delete a model with a version approval still being collected | **refused (still_referenced, 409)** | open an approval; DELETE | same defect, same cause — the table was never read |
| QA-DEL-044 | `cascade` | Delete a model with a live control waiver | **refused (still_referenced, 409)** | raise a waiver; DELETE | deleting would retire the compensating control with nothing recording that it lapsed |
| QA-DEL-045 | `cascade` | Delete a model with an undischarged approval condition | **refused (still_referenced, 409)** | impose a condition; DELETE | |
| QA-DEL-046 | `cascade` | Delete a model with an export share still readable outside the firm | **refused (still_referenced, 409)** | create a share; DELETE | deleting the model does not withdraw the share |
| QA-DEL-047 | `cascade` | Delete a model with an open breach | **refused (still_referenced, 409)** | breach appetite; DELETE | |
| QA-DEL-048 | `cascade` | Delete a model with an open amendment | **refused (still_referenced, 409)** | open an amendment; DELETE | |
| QA-DEL-049 | `cascade` | Delete a model with an active overlay | **refused (still_referenced, 409)** | apply an overlay; DELETE | |
| QA-DEL-050 | `cascade` | Delete a model with an open elicitation | **refused (still_referenced, 409)** | open an elicitation; DELETE | |
| QA-DEL-051 | `cascade` | Delete a model with an active retrain policy | **refused (still_referenced, 409)** | set a policy; DELETE | |
| QA-DEL-052 | `cascade` | Delete a model with a parallel run in progress | **refused (still_referenced, 409)** | start a parallel run; DELETE | |
| QA-DEL-053 | `cascade` | Confirm the refusal names what refers to it | **refused; detail lists them** | DELETE with three blocking references; read `detail` | somebody told *why* goes and deals with it; somebody told *no* finds another way |
| QA-DEL-054 | `cascade` | Delete a model with limitations and assumptions attached | **accepted; both destroyed** | attach both; DELETE; query the tables | meaningless without the model — dependent, not unimportant |
| QA-DEL-055 | `cascade` | Confirm inference records survive the deletion | **accepted; rows remain** | log an inference; DELETE; query `inference` | a decision the model actually made and somebody relied on is the thing a deletion must not erase |
| QA-DEL-056 | `cascade` | Confirm warrant invocations survive and are counted as kept | **accepted; `(kept)` count present** | invoke; DELETE; read `destroyed` | "nothing was destroyed" and "nothing was there" are different answers |
| QA-DEL-057 | `cascade` | GET /deletion-cascade and compare against the schema | **accepted; 38 rows** | GET; count tables carrying a `model_id` | an operator must not have to discover the disposition by performing it |
| QA-DEL-058 | `cascade` | Add a table with a `model_id` and no disposition | **build fails** | add a column; run `tests/test_tombstones.py` | adding a table must force the decision rather than default to silently unchecked |
| QA-DEL-059 | `cascade` | Confirm a blocking row is never destroyed by the cascade | **accepted; row intact** | force `Cascade.destroy` with a blocking row present; query it | a cascade that could destroy a blocking row would make the refusal decorative |
| QA-DEL-070 | `compaction` | Sweep once with an unreferenced blob present | **accepted; marked, not swept** | write a blob; POST /compaction/sweep; check the file | an upload writes bytes then the row; a sweeper in between sees exactly what an orphan looks like |
| QA-DEL-071 | `compaction` | Sweep twice | **accepted; swept** | POST sweep; POST sweep; check the file | |
| QA-DEL-072 | `compaction` | Add a reference between the two passes | **accepted; mark cleared, blob intact** | sweep; insert a `model_version` naming the digest; sweep twice more | a mark that merely expired would reclaim a live artifact |
| QA-DEL-073 | `compaction` | Two models sharing one checkpoint, delete one | **accepted; blob intact** | two versions on one digest; remove one; sweep twice | content addressing means a per-model delete takes the survivor's bytes |
| QA-DEL-074 | `compaction` | Sweep under an estate-wide legal hold | **refused (under_legal_hold, 423)** | place an estate hold; POST sweep | a refcount says whether bytes are needed; a hold says whether anyone may destroy them, and the first is not an answer to the second |
| QA-DEL-075 | `compaction` | GET /compaction/plan | **accepted; reclaims nothing** | write an orphan; GET plan twice; check the file | the plan must be safe to run repeatedly |
| QA-DEL-076 | `compaction` | POST /compaction/sweep?dry_run=true | **accepted; reports, reclaims nothing** | sweep once; sweep dry; check the file | |
| QA-DEL-077 | `compaction` | Read `not_reclaimable` in the plan | **accepted; Delta bytes and reason** | configure a Delta root with data; GET plan | silently not touching Delta and reporting nothing look identical to an operator staring at disk usage |
| QA-DEL-078 | `compaction` | POST /compaction/vacuum after a cascade | **accepted; file shrinks** | delete a model with many dependents; VACUUM; compare file size | |
| QA-DEL-079 | `compaction` | Mark a model compacted that was never deleted | **refused (no_tombstone, 409)** | call `mark_compacted` for a live URN | not a missing resource — the wrong act |
| QA-DEL-080 | `compaction` | Mark a tombstone compacted twice | **refused (already_compacted, 409)** | mark; mark again | |
| QA-DEL-081 | `compaction` | Run a sweep as a non-administrator | **refused (403)** | authenticate without `admin` | |
| QA-DEL-082 | `compaction` | Add a new column holding a content address and sweep | **build fails** | add a digest column; run `tests/test_compaction.py` | a refcount is only a refcount if it counts every reference; a missed column marks a live blob and then deletes it |
| QA-DEL-083 | `compaction` | Sweep against a store directory that does not exist | **accepted; reports zero** | point at a missing root; sweep | must not report "nothing to reclaim" in a way indistinguishable from a store it could not read |
| QA-DEL-084 | `compaction` | Confirm `.partial` upload files are never marked | **accepted; skipped** | leave a `.partial` in the store; sweep twice | an upload in progress is not an orphan |
