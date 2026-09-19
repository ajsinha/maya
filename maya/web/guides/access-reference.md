# Roles, access and licences reference

Whether a person or a program may do something in MAYA is decided by one pure function, `can(principal, action, object)`, which every surface calls — the web UI, the REST API, the SDK and the CLI. This reference is the complete rulebook behind it: roles and their capabilities, namespaces, grants and their conditions, API-key scope, and the data licences that travel with the data.

## Three layers

| Layer | Question it answers | Can it widen access? |
|---|---|---|
| **Roles** | Does one of your roles allow this kind of action on this kind of object at all? | No: it is the ceiling. |
| **Grants** | Does a grant on this object, its ownership or its namespace open it to you? | Only up to the ceiling. |
| **Conditions and licences** | What of the data may you actually see or take away? | Never: they only take away. |

## Capabilities and actions

A role holds **capability letters** per object type:

| Letter | Capability |
|---|---|
| `C` | create |
| `R` | read |
| `U` | update |
| `A` | approve |
| `P` | pin or seal |
| `G` | grant and revoke access |
| `Q` | request a pin (for someone with `P` to approve) |

Every authorization check names an **action**, and each action needs one letter:

| Action | Letter needed | Notes |
|---|---|---|
| `read`, `download` | `R` | |
| `create` | `C` | Creating needs only the role capability, not a grant. |
| `update`, `submit` | `U` | |
| `approve` | `A` | |
| `pin`, `seal` | `P` | |
| `request_pin` | `Q` | Holding `P` also satisfies it. |
| `grant`, `revoke` | `G` | |
| `admin` | `C` | |

## The shipped roles

MAYA ships eight roles. Their capabilities are data, seeded at every start: a built-in role whose capabilities were changed in the database is restored to the table below. To change what a group of people can do, create a custom role.

| Role | Purpose |
|---|---|
| `admin` | Users, roles, SSO, system settings, storage, workflow policy |
| `feature_designer` | Feature definitions, schemas, resolution rules, sources |
| `feature_manager` | Approval of features and feature sets, pin authorization |
| `model_designer` | Model definitions, formula, Python artifact, LaTeX specification |
| `model_developer` | Training warrants, parameter upload, experiment iteration |
| `model_manager` | Approval of models, warrants and parameter sets |
| `model_owner` | Access policy for a model and its lineage; accountable for its use |
| `techops` | Runtime health, job queues, retries, storage compaction, backups |

### The capability matrix

| Object type | `admin` | `feature_designer` | `feature_manager` | `model_designer` | `model_developer` | `model_manager` | `model_owner` | `techops` |
|---|---|---|---|---|---|---|---|---|
| `feature` | CRUG | CRU | RA | R | R | R | R | R |
| `feature_pin` | P | Q | AP | — | Q | — | — | R |
| `featureset` | CRUG | CRU | RAP | R | CRU | R | R | R |
| `model` | CRUG | R | R | CRU | R | RA | RG | R |
| `artifact` | CRU | — | R | CRU | RU | RA | R | R |
| `specdoc` | CRU | — | R | CRU | RU | RA | R | R |
| `training_warrant` | CRUG | — | R | R | CRU | RAP | RG | R |
| `parameter_set` | CRU | — | — | R | CRU | RA | R | R |
| `execution_warrant` | CRUG | — | — | R | R | CRUAP | RG | R |
| `users` | CRUG | — | — | — | — | — | — | R |
| `jobs` | CRU | R | R | R | R | R | R | CRU |
| `namespace` | CRUG | — | — | — | — | — | — | — |
| `workflow_policy` | CRUAG | — | — | — | — | — | — | — |

A person holding several roles holds the union of their letters. Roles reach a person directly or through a group.

!!! note "Some duties check a role, not a letter"
    A few operational actions are reserved by role name rather than by capability: the audit explorer, integrity verification, lake maintenance, job retry, custody anchors, webhooks and the event stream are for `admin` and `techops`; the effective configuration, sessions, SQL connections, the estate export and search reindexing are for `admin`.

### Custom roles

An administrator (or anyone holding `C` on `users`) can define further roles as named capability sets. Letters are limited to `C R U A P G Q`.

```python
# A read-only auditor role
import maya.sdk as maya
my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
my.admin.create_role("auditor", {"feature": "R", "featureset": "R", "model": "R",
                                 "training_warrant": "R", "execution_warrant": "R"},
                     description="Reads everything, changes nothing")
```

### Users and groups

| Operation | SDK | Rule |
|---|---|---|
| Create a user | `admin.create_user(username, password=…, roles=[…], email=…, display_name=…, is_service=False, desk=None)` | needs `C` on `users` |
| Change details | `admin.update_user(username, email=…, display_name=…, status=…, desk=…)` | only these four fields |
| Replace roles | `admin.set_roles(username, [...])` | unknown roles are refused |
| Create a group | `admin.create_group(name, description=…, roles=[…], members=[…])` | needs `C` on `users` |

A user's **desk** is used by grant conditions (`@user.desk`) and licence populations (`desk:<name>`). A **service account** (`is_service`) cannot sign in with a password; it acts through API keys. Any status other than `active` stops an account from signing in and from using its keys.

## Namespaces

Every catalog object lives in a namespace. A namespace sets its default visibility, its separation-of-duties strictness and whether it is a production namespace.

| Field | Values | Meaning |
|---|---|---|
| `name` | letters, digits, `_`, `-`, `.` | Unique. |
| `parent` | a namespace | Namespaces nest one level only. |
| `preset` | `small_team`, `standard` (default), `regulated` | Sets the expected roles and the SoD level. |
| `sod` | `none`, `two_person`, `strict` | Separation of duties for approvals. |
| `default_visibility` | `namespace_read` (default), `public_read`, `private` | What the namespace gives people without a grant. |
| `production` | `true` / `false` | Production namespaces add the `model_owner` approval to execution warrants in the default policy. |
| `classification` | text, default `internal` | Recorded. |
| `quota_bytes` | integer | Recorded. |

`update` may change `description`, `sod`, `default_visibility`, `quota_bytes`, `classification`, `production`, `preset` and `materialize_policy` (`always`, `on_demand` or `never`; anything else is refused).

### Presets and separation of duties

| Preset | Roles it expects | SoD |
|---|---|---|
| `small_team` | `admin`, `feature_designer`, `model_manager` | `none` |
| `standard` | `admin`, `feature_designer`, `feature_manager`, `model_designer`, `model_developer`, `model_manager` | `two_person` |
| `regulated` | all eight | `strict` |

| SoD | An approver may not be |
|---|---|
| `strict` | the person who created, submitted or last modified the object |
| `two_person` | the person who submitted it (or created it, if it was never submitted) |
| `none` | — no restriction |

With a delegation, both the stand-in and the delegator are held to the rule. `workflow.allow_self_approval` switches the rule off, and is honoured only in dev.

### Scratch namespaces

Every user has a personal `scratch.<username>` namespace: preset `small_team`, SoD `none`, `private`. It belongs to its owner alone — nobody else, except an administrator, can act in it, whatever their roles or grants.

## How a decision is made

For every check, in this order:

1. **Unknown action** — refused.
2. **Role ceiling** — one of your roles must hold the action's letter for the object type. Refused otherwise, whatever grants exist.
3. **API-key scope** — for a key, the action must be in its `actions` list and the object's namespace in its `namespaces` list, when those lists are set.
4. **Object state** — a `sealed` or `retired` object refuses `create`, `update` and `submit` to everyone, administrators included.
5. **Scratch namespace** — someone else's scratch namespace refuses everyone but administrators.
6. **Administrator** — allowed.
7. **Create** — allowed (the ceiling already passed).
8. **Grants and defaults**, evaluated on the object's unexpired grants:

| Step | Rule |
|---|---|
| Explicit deny | A `deny` grant to you refuses, whatever else applies. |
| User grant | A grant to you by name decides, at its level. |
| Group or role grant | The highest level among grants to your groups and roles decides. |
| Everyone | An `everyone` grant decides. |
| Ownership | The owner acts at level `own`. |
| Namespace default | In a `namespace_read` or `public_read` namespace: `read` and `download` for anyone whose role allows them; `approve`, `pin`, `seal` and `request_pin` for anyone whose role holds the capability. Editing still needs ownership or a grant. |
| Otherwise | Refused: no grant, and the namespace is private. |

The first step that applies decides. Every denial names its rule and is counted in `maya_authz_denials_total`. Denied `approve`, `pin`, `seal`, `grant` and `revoke` actions, and every denial on a namespace, are also written to the audit log as `authz.denied`, surviving the request's rollback.

## Grants

A grant opens one object to one principal at one level, optionally with conditions, and expires.

| Field | Values |
|---|---|
| `kind` | `feature`, `featureset`, `model`, `training_warrant`, `execution_warrant`, `namespace` |
| `object_ref` | a `maya://` reference or `namespace/name`; the namespace name for `namespace`; the id for warrants |
| `principal_type` | `user`, `group`, `role`, `everyone` |
| `principal_id` | a username (stored as the user's id), a group name, a role name; ignored for `everyone` |
| `level` | `read`, `read_write`, `approve`, `own`, `admin` |
| `days` | expiry in days, default 90; `null` for no expiry |
| `deny` | `true` makes it an explicit deny |
| `conditions` | row filter, column mask, time bound (below) |

### Levels

| Level | Allows |
|---|---|
| `read` | `read`, `download` |
| `read_write` | the above, `update`, `submit`, `request_pin` |
| `approve` | `read`, `download`, `approve`, `pin`, `seal` |
| `own` | everything in `read_write` and `approve`, plus `grant` and `revoke` |
| `admin` | every action; only an administrator can grant it |

Granting needs the `grant` action on the object (`G` in your roles, and `own` or `admin` on the object, or ownership, or being an administrator).

!!! warning "Inert grants are recorded and flagged"
    A grant can never lift someone above their role ceiling. When a user grant's level needs a letter the user's roles lack — `read_write` needs `U`, `approve` needs `A`, `own` needs `G`, `admin` needs `C` — MAYA still stores it, with an `inert_reason` saying why it does nothing, so the grants page never shows a dead grant as live.

```python
# Read access for a validator, for 30 days, without the out-of-sample period
my.access.grant(kind="feature", object_ref="eq/prices",
                principal_type="user", principal_id="val.jones", level="read", days=30,
                conditions={"time_bound": {"until": "2025-12-31"},
                            "column_mask": {"vol": "hash"}})
print(my.access.grants(kind="feature", ref="eq/prices"))
```

Revoking deletes the grant (`access.revoked`); granting writes `access.granted`. Both are events.

### Conditions

Conditions ride on the grant that decided a read and are applied, in this order, to every frame returned to that principal: previews, downloads, feature set resolutions and training data, live or pinned.

| Condition | Form | Effect |
|---|---|---|
| `row_filter` | an expression in MAYA's expression language | Keeps only matching rows. `@user.username` and `@user.desk` are substituted from the reader; no other `@user` field is allowed. |
| `time_bound` | `{"until": "YYYY-MM-DD"}` | Drops every row whose event date is after the cut-off. |
| `column_mask` | `{attribute: "null" or "hash"}` | The column stays, its values do not. `hash` is SHA-256 of the value's text, so joins still work. |

Conditions are validated when the grant is made, not at first read. When several grants of equal standing apply, they combine to the most restrictive: row filters are AND-ed, masks are unioned (where two grants mask one column differently, `null` beats `hash`), and the earliest cut-off wins.

!!! tip "A filter on a missing column withholds everything"
    If a row filter names a column the frame does not have, the reader gets no rows rather than all of them.

### Recertification

`my.access.recertification()` (`GET /access/recertification`) lists every grant on every object you own, for the periodic review of who still needs what. Grants expire after 90 days unless made otherwise, which keeps the review honest.

## API-key scope

An API key acts as its owner, narrowed:

| Scope | Effect |
|---|---|
| `roles` | Only these of the owner's roles; empty keeps all. A key cannot carry a role its owner lacks. |
| `namespaces` | Objects outside these namespaces are refused. |
| `actions` | Actions outside this list are refused. |
| `cidrs` | Requests from other client addresses are refused. |
| environment | Fixed in the key's text; the key is refused in any other environment. |

A key's principal type is `api_key`, recorded on every audit entry it causes.

## Data licences

A source can declare the terms it was licensed under, in a `licence` block of its definition. MAYA computes every object's **effective licence** as the most restrictive combination of everything it is built from — its own declaration, the parent it extends, the operands it is derived from, the members of a feature set, the feature set behind a warrant — and enforces it at every exit.

### Vocabulary

| Term | Values | Combination |
|---|---|---|
| `vendor` | text | accumulated into `vendors`, for attribution |
| `redistribution` | `none` < `internal` < `external` < `public` | the lowest wins |
| `derived_works` | `forbidden` < `attribution` < `allowed` | the lowest wins |
| `population` | a list of group names and `desk:<name>` entries | the intersection; an empty intersection means nobody |
| `retention_days` | a positive whole number | the shortest wins |
| `notes` | text | not enforced |

| `redistribution` | Means |
|---|---|
| `none` | Viewable and usable inside MAYA; never leaves in bulk. |
| `internal` | Downloads within the firm. |
| `external` | To regulators and counterparties, in a reproducibility bundle. |
| `public` | Anywhere. |

Leaving the block out is the same as `public`, `allowed` and no population limit. An unknown term or an out-of-vocabulary value is a validation error in the definition. Every combined term remembers which source imposed it (`clauses`), so a refusal names the vendor and the object.

```json
{
  "licence": {
    "vendor": "Acme Data",
    "redistribution": "internal",
    "derived_works": "attribution",
    "population": ["desk:rates", "quant-research"],
    "retention_days": 365
  }
}
```

### Where licences are enforced

| Exit | Rule |
|---|---|
| Reading or previewing a feature or feature set | refused to a reader outside the population |
| Downloading a feature | needs `redistribution` of at least `internal` |
| Downloading a feature set | needs at least `internal` |
| Downloading a training warrant's data | needs at least `internal` on its feature set |
| Exporting a reproducibility bundle | needs `external` on the warrant's feature set |
| Building a derived feature | refused when an operand's `derived_works` is `forbidden` |
| Creating a training warrant | refused when the feature set's `derived_works` is `forbidden` |
| Granting access to a feature or feature set with a population | a grant to `everyone` or to a role is refused; a grant to a user or group outside the population is refused |

A refusal is `licence_breach` (451) and, for exports, is written to the audit log as `licence.refused` even though the request failed. `retention_days` is carried into feature download manifests for the recipient; MAYA does not delete data when it lapses.

```python
# Show an object's effective licence
lic = my.custody.licence("feature", "maya://feature/eq/spread@v2")
print(lic["redistribution"], lic["clauses"].get("redistribution"))
print(lic["vendors"], lic["you_may_receive"])
```

`GET /api/v1/licences?kind=feature|featureset&ref=…` returns the same to anyone who may read the object: terms are not secret.

!!! note "MAYA enforces the terms it is given"
    It cannot read a vendor contract. Agree the mapping from contract to vocabulary once, record it in `notes`, and review the licence block like any other part of the definition: it is inside the versioned definition, so changing it makes a new version.

## Where the rules are recorded

| Event | Audit action |
|---|---|
| A grant made or revoked | `access.granted`, `access.revoked` |
| A namespace created or changed | `namespace.created`, `namespace.updated` |
| A role or group created | `role.created`, `group.created` |
| A licence refusal on export | `licence.refused` |
| A denied approval, pin, seal, grant or revocation | `authz.denied` |
| An SSO account provisioned | `user.jit_provisioned` |
