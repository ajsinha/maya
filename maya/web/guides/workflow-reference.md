# Workflow and policy reference

Every governed object in MAYA moves through one workflow engine. What each kind of object may do is a **policy**: plain data, stored in the database, validated when it is edited, and activated by a second administrator. This reference covers the objects, the states, the policy format, the checks, approvals and separation of duties, delegation, break-glass, the policy editor, and the people-facing pieces — queues, comments, campaigns and the recorded challenger.

## Governed objects

| Object type | What moves | Address in `POST /workflow/transitions` |
|---|---|---|
| `feature_version` | one version of a feature | the version's id |
| `featureset_version` | one version of a feature set | the version's id |
| `model_version` | one version of a model | the version's id |
| `parameter_set` | a set of trained parameter values | the parameter set's id |
| `training_warrant` | a training warrant | the warrant's id |
| `execution_warrant` | an execution warrant | the warrant's id |

Each type has its own transition endpoint as well (`/features/{ns}/{name}/versions/{v}/transitions/{t}`, `/warrants/training/{id}/transitions/{t}`, `/parameters/{id}/transitions/{t}` and so on); the generic `POST /workflow/transitions` takes `object_type`, `object_id`, `transition`, `rationale` and `force` and dispatches to the same place.

## States

The shipped policies share one set of states:

| State | Meaning |
|---|---|
| `draft` | Being written. Every object starts here. |
| `in_review` | Submitted; waiting for checks and approvals. |
| `changes_requested` | Sent back to the author. |
| `approved` | Every required approval is in and every check passed. |
| `published` | Released for general use (feature, feature set and model versions). |
| `deprecated` | Superseded; still readable. |
| `retired` | The end of the road. Retired objects are read-only to everyone. |
| `withdrawn` | Pulled from review by its author. |

`approved` and `published` together count as *approved* wherever MAYA asks whether something is approved — a model version a warrant is drawn on, a parameter set an execution warrant uses.

## The shipped policies

| Transition | From | To | Needs | Checks |
|---|---|---|---|---|
| `submit` | `draft`, `changes_requested` | `in_review` | `U` (`C` for parameter sets and execution warrants) | per type, below |
| `request_changes` | `in_review` | `changes_requested` | `A` | — |
| `approve` | `in_review` | `approved` | `A` and the approvals below | per type, below |
| `withdraw` | `in_review` | `withdrawn` | `U` (`C` for execution warrants) | — |
| `publish` | `approved` | `published` | `A` | — (feature, feature set and model versions only) |
| `deprecate` | `approved`, `published` | `deprecated` | `A` | — (feature, feature set and model versions only) |
| `retire` | see below | `retired` | the `admin` role | — |

`retire` starts from `deprecated` for feature, feature set and model versions; from `approved` for parameter sets; from `approved` or `published` for warrants.

### Checks and approvals by type

| Object type | Checks on `submit` | Checks on `approve` | Approvals |
|---|---|---|---|
| `feature_version` | `definition_valid` | `definition_valid`, `quality_passes`, `no_open_blocking_comments` | `feature_manager` ×1 |
| `featureset_version` | `definition_valid` | `definition_valid`, `members_approved`, `no_open_blocking_comments` | `feature_manager` ×1 |
| `model_version` | `formula_typechecks`, `spec_document_complete`, `code_artifact_validated` | those three, `spec_true_build`, `composite_members_mature`, `no_open_blocking_comments` | `model_manager` ×1 |
| `parameter_set` | `parameters_within_bounds` | `parameters_within_bounds`, `data_verified_or_justified`, `no_open_blocking_comments` | `model_manager` ×1 |
| `training_warrant` | `contract_valid`, `leakage_certified` | `contract_valid`, `leakage_certified`, `no_open_blocking_comments` | `model_manager` ×1 |
| `execution_warrant` | `parameters_approved` | `parameters_approved`, `no_open_blocking_comments` | `model_manager` ×1, plus `model_owner` ×1 in a production namespace |

| Object type | SLA in review | Notified on arrival |
|---|---|---|
| `feature_version` | 5 days | `in_review`: feature managers; `approved`, `changes_requested`: the owner |
| `featureset_version` | 5 days | `in_review`: feature managers; `approved`: the owner |
| `model_version` | 5 days | `in_review`: model managers; `approved`, `changes_requested`: the owner |
| `parameter_set` | — | `in_review`: model managers |
| `training_warrant` | — | `in_review`: model managers; `approved`: the owner |
| `execution_warrant` | — | `in_review`: model managers and model owners; `approved`: the owner |

The shipped policies are seeded into the database on first start, from `maya/workflow/default_policies.yaml`. From then on the stored record is the authority; the file is only the initial projection.

## The policy format

A policy is a mapping. Here is the shipped feature-version policy as YAML:

```yaml
# feature_version
states: [draft, in_review, changes_requested, approved, published, deprecated, retired, withdrawn]
transitions:
  submit: {from: [draft, changes_requested], to: in_review, capability: U, checks: [definition_valid]}
  request_changes: {from: [in_review], to: changes_requested, capability: A}
  approve:
    from: [in_review]
    to: approved
    capability: A
    approvals: [{role: feature_manager, count: 1}]
    checks: [definition_valid, quality_passes, no_open_blocking_comments]
  withdraw: {from: [in_review], to: withdrawn, capability: U}
  publish: {from: [approved], to: published, capability: A}
  deprecate: {from: [approved, published], to: deprecated, capability: A}
  retire: {from: [deprecated], to: retired, roles: [admin]}
sla_days: {in_review: 5}
notify: {in_review: [feature_manager], approved: [owner], changes_requested: [owner]}
```

| Key | Meaning |
|---|---|
| `states` | Every state the object may be in. Must include `draft`. |
| `transitions.<name>.from` | The state or list of states it may start from. |
| `transitions.<name>.to` | The state it lands in. |
| `transitions.<name>.capability` | A capability letter the actor needs on the object (checked with grants, like any action): `A` means approve, `U` submit, `C` create, `P` seal, anything else update. |
| `transitions.<name>.roles` | Restrict the transition to people holding one of these roles. |
| `transitions.<name>.checks` | Named checks that must all pass. |
| `transitions.<name>.approvals` | `{role, count}` requirements; `when: prod` applies a requirement only in a production namespace. |
| `sla_days` | How long an object may wait in a state; only `in_review` is used, by the aging list and escalation. |
| `notify` | Who is told when an object lands in a state: role names, or `owner`. |

### What validation refuses

A policy is validated when it is saved, not when it bites. It is refused, with every reason listed, when:

- the initial state `draft` is missing, or there are no transitions;
- a transition starts from or lands in a state not in `states`;
- a check is not a registered check name;
- a role in `roles` or in an approval does not exist (the approval could never be satisfied);
- a capability is not one of `C R U A P G Q`;
- an approval count is below 1;
- a state cannot be reached from `draft`;
- no transition reaches `approved`, which would leave every object permanently unapprovable.

## The checks

| Check | Passes when |
|---|---|
| `definition_valid` | The feature or feature set definition validates and types (a production namespace applies its stricter rules). |
| `quality_passes` | The feature's quality contract passes on a resolved sample of current data, or it declares none. |
| `members_approved` | Every member of a feature set is approved. |
| `formula_typechecks` | The model's formula IR is valid and typechecks. |
| `spec_document_complete` | The specification document is complete. |
| `code_artifact_validated` | The uploaded code artifact passed its validation. |
| `spec_true_build` | The specification PDF is a true Tectonic build. In dev, with `typeset.require_true_build` false, a draft render or no render passes with a note; elsewhere it fails. |
| `composite_members_mature` | A composite model has no member still at maturity `experimental`; a non-composite passes. |
| `contract_valid` | The training warrant's input-contract report is clean. |
| `leakage_certified` | The leakage certificate is `certified` or `certified_with_exceptions`. |
| `parameters_within_bounds` | Every parameter is present and within its declared bounds, and every constant without a declared value is supplied. |
| `data_verified_or_justified` | The parameters were trained on data MAYA issued (the checksum matched), or an `unverified_data` override was justified. |
| `parameters_approved` | The execution warrant's parameter set is approved, or the model has no parameters. |
| `no_open_blocking_comments` | No reviewer comment marked blocking is unresolved. |

A check a policy names but nobody registered fails with "check is not registered". When checks fail, the transition is refused with `not_approved` (409), naming each failed check and its detail; the full results are in the problem's `context.checks`.

## How the engine takes a transition

1. Load the active policy for the object type: the one scoped to the object's namespace first, else the global one (`*`).
2. Refuse a transition that is not in the policy, or that does not start from the object's current state.
3. With `force`, go to break-glass (below).
4. Check the actor: `roles`, then `capability` through the same authorization function as every other action. If that fails and the transition has approvals, try each active delegation to the actor (below).
5. Run every named check; any failure refuses the move.
6. If the transition has approvals, record one and move only when every requirement is met.
7. Move: update the state, record a workflow event with the checks' results and the policy that governed it, write the audit entry, notify, and tell listeners (the challenger).

`submit` stamps `submitted_by` and `submitted_at`; reaching `approved` stamps `approved_by` and `approved_at`.

### Approvals and rounds

- Approvals accumulate in **rounds**. A round is counted by `submit` events, so a resubmission after `changes_requested` starts a fresh round and earlier approvals no longer count.
- Each approval is recorded against a role the approver holds that still has an outstanding count. One person approves a round once — directly or through a delegation, not both.
- While requirements remain, the response says what is outstanding (for example `model_owner ×1`) and the object stays `in_review`; `workflow.approval_recorded` is audited.
- An administrator whose roles match no outstanding requirement approves as `admin`, and that approval completes the transition.

### Separation of duties

Before an approval is recorded, the namespace's SoD level is applied to the approver — and, for a delegated approval, to the delegator too:

| SoD | Refused when the approver |
|---|---|
| `strict` | created, submitted or last updated the object |
| `two_person` | submitted it (or created it, if `submitted_by` is empty) |
| `none` | — |

`workflow.allow_self_approval: true` disables this, and is honoured only in dev.

## Delegation

An approver who will be away names a stand-in for a date range, optionally limited to object types.

```python
# Cover two weeks of leave
import maya.sdk as maya
my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
d = my.workflow.delegate(to="priya", starts_on="2026-10-01", ends_on="2026-10-14",
                         object_types=["feature_version", "featureset_version"],
                         reason="Annual leave")
```

| Rule | Behaviour |
|---|---|
| Who may delegate | Anyone whose roles hold `A` on some object type. |
| Who may receive | An active user other than yourself. They are notified at once. |
| When it applies | From `starts_on` to `ends_on`, both inclusive, until revoked. |
| Scope | The listed object types; empty means all. |
| What it grants | Only transitions with approvals. When the stand-in's own roles and grants are not enough, the engine tries each active delegation to them and takes the approval *as the delegator* — if the delegator's roles and grants would have allowed it. |
| The record | The approval is stored with `on_behalf_of` the delegator, and the rationale is suffixed `[as delegate of <delegator>]`. |
| Chaining | None: only delegations made to the person acting are consulted. |
| Revoking | The delegator or an administrator (`DELETE /workflow/delegations/{id}`). |

Creating a delegation is audited as `workflow.delegated`.

## Break-glass

An administrator can force a transition past its checks and approvals:

```python
# Force an approval, on the record
my.features.transition("credit/ltv", 4, "approve", force=True,
                       rationale="Regulator deadline today; full review scheduled 2026-09-21")
```

| Rule | Behaviour |
|---|---|
| Who | The `admin` role only. |
| Reason | A written rationale of at least ten characters. |
| What is skipped | Actor checks, named checks, approvals and SoD. The transition must still exist and start from the current state. |
| What is recorded | The object is marked `force_approved`; the workflow event is `forced`; the audit action is `workflow.break_glass` (also an event); the owner is notified with a `BREAK-GLASS:` prefix even if the policy would not notify them. |
| Review | `GET /workflow/break-glass?days=31` lists forced transitions in the window. |

## Changing a policy

The rules of governance are governed too. A policy change is drafted, validated, previewed, and activated by a **second** administrator; the old version is kept.

```python
# Draft a stricter policy for one namespace, then have another administrator activate it
current = next(p for p in my.workflow.policies()
               if p["object_type"] == "feature_version" and p["state"] == "active")
policy = current["policy"]
policy["transitions"]["approve"]["approvals"] = [{"role": "feature_manager", "count": 2}]
print(my.workflow.validate_policy("feature_version", policy))   # {"errors": [], "impact": {…}}
draft = my.workflow.draft_policy("feature_version", policy, scope="credit",
                                 note="two approvals in credit")
# a different administrator:
my.workflow.activate_policy(draft["id"])
```

| Step | Rule |
|---|---|
| Who | Holders of `U` on `workflow_policy` (the `admin` role). |
| Draft | `draft_policy(object_type, policy, scope="*", note="")`. Refused if invalid. Numbered per object type and scope. Returns the impact preview. |
| Import | `import_policy(object_type, yaml, scope="*")`: the same, from YAML text. |
| Validate | `validate_policy(object_type, policy)`: the errors and the impact, without saving. |
| Impact preview | The live population per state, and which objects the new policy would **strand** (in a state it no longer has) or **block** (in a state with no way out, other than `retired` and `withdrawn`). |
| Activate | Only a `draft`. The drafter cannot activate their own draft (unless self-approval is on in dev). The previous active version for that type and scope becomes `superseded`. |
| Scope | `*` is global; a namespace name scopes the policy to that namespace, which then takes precedence there. |
| Export | `policy_yaml(policy_id)` returns canonical YAML; export → import → export is byte-identical. |

Every past workflow event records the id of the policy that governed it, so the rules behind any past decision are recoverable. Drafting and activating are audited as `policy.drafted` and `policy.activated` (also an event).

## Queues, aging and escalation

| View | What it lists |
|---|---|
| `GET /workflow/queue` | Every object in `in_review`, oldest first, with who submitted it, since when, its age in days and `mine` when you submitted it. |
| `GET /workflow/aging` | Items in review longer than `sla_days.in_review` in the policy that governs them. |
| `GET /workflow/population/{object_type}` | How many objects are in each state. |
| `GET /workflow/history?object_type=&object_id=` | Every transition and every approval, in order. |

Every hour the scheduler escalates each overdue item to its namespace's owner — or, when the namespace has none, to every administrator — once per item, and audits `workflow.escalated`.

!!! note "SLA comes from the governing policy"
    Aging and escalation read `sla_days` from the same policy the workflow engine applies to the item: the active policy scoped to its namespace when there is one, otherwise the global (`*`) policy of its type. A namespace that shortens its review SLA is escalated on its own clock.

## Comments

Reviewers comment on any governed object they can read. A comment marked **blocking** holds up every transition that runs `no_open_blocking_comments` until it is resolved. Only the comment's author (or an administrator) resolves it.

```python
# A blocking question, then its resolution
c = my.workflow.comment("feature_version", version_id, "What is the unit of ltv?", blocking=True)
my.workflow.resolve_comment(c["id"])
```

Reading or adding comments and history needs read access to the object that governs the item — the feature for a feature version, the warrant for a parameter set. Comments are audited as `review.commented`.

## Campaigns

A campaign applies one transition to many objects — a re-certification, a mass deprecation — with a per-item result and one audit record.

```python
# Deprecate three model versions in one campaign
out = my.workflow.run_campaign("q3-cleanup", "deprecate",
                               [{"object_type": "model_version", "id": v} for v in version_ids],
                               rationale="Superseded by the Q3 recalibration")
print([(r["id"], r["ok"], r["message"]) for r in out["results"]])
```

Each item is taken separately, with all the usual checks, approvals and SoD; one item failing does not stop the others. The campaign is stored with its results and audited as `campaign.run`.

## The recorded challenger

When an object enters `in_review` and `assistant.enabled` is true, a job writes a **challenge memo**. The challenger covers feature versions, feature set versions and model versions. The memo looks for look-ahead, unbounded fills, schema drift against the last approved version, thin or missing limitations, and a document that no longer matches its formula.

| Property | Behaviour |
|---|---|
| Authority | None. It never approves, blocks or edits; no check reads it. |
| Provider | `assistant.provider`: `rules` (deterministic, no network) or `claude` (also asks Claude; sends definitions, the specification and the formula, never data rows). Each memo names the provider and model that wrote it. |
| Response | The reviewer records a stance: `agree`, `partly` or `disagree`. Anything but `agree` needs a reason of at least ten characters. Audited as `assistant.response_recorded`. |
| On demand | `POST /assistant/memos` queues a fresh memo (202) for one of those three types. |

```python
# Read the memo and record your stance
memo = my.assistant.memos("feature_version", version_id)[0]
for f in memo["findings"]:
    print(f["severity"], f["title"])
my.assistant.respond(memo["id"], "partly", "Agree on the fill cap; the schema change is intended")
```

## Type-specific rules on transitions

| Object | Rule |
|---|---|
| Model version, `deprecate` | Must name a `successor` or give a rationale saying there is none. |
| Parameter set, `approve` | An `unverified_data` set passes `data_verified_or_justified` only with a `justification` on the transition; the justification is stored and audited. |
| Training and execution warrants | Every transition that moves also writes a custody event on the warrant. |
| Sealed or retired objects | `create`, `update` and `submit` are refused to everyone. |

## Events

Every transition that moves emits an event named by the object type and the state reached — `feature_version.in_review`, `model_version.approved`, `execution_warrant.retired`. Break-glass emits `workflow.break_glass`, and activating a policy emits `policy.activated`. Recording an approval that is not yet enough to move emits nothing. Subscribe with a webhook to hear about them.
