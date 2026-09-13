---
title: Administering MAYA
slug: administering-maya
section: Reference
order: 145
icon: sliders
summary: Seven screens about the platform rather than about any model in it — who may act, which rulebook is in force, what runs unattended, whether the record is still intact, what the process is doing right now, and what may execute — plus the line between what a firm configures and what it must not. Each gated by the same permission its API asks for.
audience: Operators, Platform, Model risk
---

# Administering MAYA

Everything here is about the machinery rather than about any model in it. It sits
behind **Admin** in the bar, and each entry appears only if you hold the
permission that screen's API asks for — so the menu you see is not the menu
somebody else sees.

That is deliberate and it is not tidiness. A menu that lists a screen which then
answers *403* teaches people that refusals are noise, and this platform's entire
argument is that a refusal means something.

All of them but **People and roles** are **read-only**: they show you the state
and name the endpoint that changes it. The acts themselves stay where their evidence and their
segregation checks already live, because an administrative act that skipped
those would be the one act in MAYA with no record.

---


## People, roles and keys

Three things an administrator does daily, and until recently all three meant
`curl`.

### People

**`/admin/principals`** adds a principal, changes roles, sets a password,
suspends and reinstates. The screen decides nothing: every act posts to the same
API a script would, and the incompatible-roles check, the scope, the segregation
of duties and the evidence happen where they already did.

The one place it asks a second question is an **incompatible pair**. The server
refuses, the screen reads the refusal and offers to retry as a recorded
exception — because a small firm giving one person two hats *visibly* is better
than a hybrid role that hides it.

### Roles

Roles live in the register. Eight ship with the platform, marked **built-in**,
and may be read and not edited: every document, tutorial and test here names
them, and a vocabulary that can be renamed underneath its own documentation
makes the documentation wrong. Everything else is yours — a *Model Validation
Team Lead*, a *Regional MRM* — defined on the same screen, with every permission
checked against the closed set.

**Two kinds of conflict are checked, and neither catches what the other does.**

*Role pairs* are about **independence** — which line somebody is in.
`auditor + model_developer` has no permission collision at all, since an auditor
holds reads and `finding:raise`; the conflict is that the third line must not
build what it audits, and a permission check cannot see that.

*Permission pairs* are about **capability**, and they exist because a role you
define could otherwise smuggle one past: give one role `version:create` and
`version:approve` together and a check over role *names* sees a single
unfamiliar name and passes it.

### API keys

**`/admin/api-keys`.** A service signing in with a password has three problems a
key does not: the password is a shared secret somebody typed and can retype
elsewhere, it carries every permission the principal holds for as long as the
account exists, and rotating it means changing it in two places at the same
instant or something stops working.

| | |
|---|---|
| Shown once | The secret is in the creation response and nowhere else — not a log, not the evidence chain, not the row. The chain records that a key was issued, to whom, with what scope and until when |
| Always expires | Ninety days by default, a year at most. A key with no practical expiry is a credential nobody ever reviews |
| Narrows, never widens | A key may hold a subset of its principal's permissions — checked **at use**, so a role removed or an account suspended reaches every key immediately |
| Rotated as two keys | Issue the new one, move the caller, revoke the old. A rotation that is one atomic act has a window in which nothing works |
| Revoked, never deleted | The row is what says the key existed; `last_used_at` is what says whether anybody would have noticed losing it |

Send one as `Authorization: Bearer maya_sk_…` or `X-API-Key`, or give the SDK
`Maya(base_url, api_key=…)`.

The list shows the two things worth acting on rather than every key: one **never
used** is one nobody would notice losing, and one **expiring within a fortnight**
is an outage somebody should schedule rather than meet.

## Deleting things, and seeing what would break

**`/dependencies`** answers *where is this used?* — and a delete consults
exactly what it shows. Building those separately is how they come to disagree: a
screen listing three usages while the delete check knows about four says a thing
is safe to remove and then refuses.

A reference is **blocking** or **historical**. A live warrant naming this model
would be left broken; a revoked one records what happened and reads correctly
afterwards. A register in which nothing may ever be deleted because something
once happened grows without bound, so historical references are shown rather
than enforced.

Deleting a model was previously checked for two things — that the caller was an
administrator and had given a reason — and **thirty-eight tables carry a
`model_id`**. Refusals now name what refers to the thing, because somebody told
*why* can go and deal with it and somebody told *no* finds another way.

**Retiring is almost always the right act instead.** It withdraws a model from
use and keeps every reference readable.

### The identifier does not come back

Deleting a model leaves a **tombstone** — the row that stays, holding what the
model was, the lifecycle state it was deleted *from*, who destroyed it, when,
why, and a count of what went with it. You can see them at the foot of
**Classification and retention**.

The tombstone does one thing that is easy to miss and hard to recover from if
it is absent: **it stops the name being used again.** A model's identifier is
derived from its name. Without the marker, deleting `pd-retail` and registering
a new model called `pd-retail` would give the new model the old one's
identifier — and every piece of evidence, every closed finding and every
amendment naming it would read as though it were about the new model. Nothing
would flag it. The evidence chain would verify perfectly, because the chain
would be intact; it would simply be describing the wrong model.

So registering over a deleted name is refused, and there is no override. If you
need the name back, the answer is that you cannot have it.

A deleted model is **not hidden, and not recoverable**. The record is really
gone: it does not appear in listings and cannot be attested, approved or moved
through the lifecycle. There is no undelete, because restoring one would
produce an empty model wearing a destroyed one's identity, which is the exact
confusion the tombstone exists to prevent.

**What the deletion state records matters.** Deleting a draft nobody ever used
is housekeeping. Deleting a retired model that made decisions for six years is
an act somebody may have to explain, and the tombstone's `status` is the only
thing that survives to say which one happened.

### What goes, and what stays

Every table holding a reference to the model has a **declared disposition**,
published at `GET /deletion-cascade` so you can read it before you act rather
than discover it afterwards:

| | What it means | Examples |
|---|---|---|
| **Blocks** | A live commitment that would be left broken. The deletion is refused and the refusal names it | an unfinished validation, an unanswered campaign item, a live control waiver, an export share somebody outside can still read |
| **Goes** | Meaningless without the model, so it is destroyed with it | limitations, assumptions, the tiering facts, attached files |
| **Stays** | The record that something happened, which still reads correctly because the tombstone keeps the identifier resolving | inferences, invocations, compiled documents |

The **stays** row is the one worth pausing on. An inference is a decision the
model actually made and somebody relied on, and no deletion should be able to
erase it. That is only honest because the tombstone is there — without it, those
records would point at nothing.

### Reclaiming storage

Deleting a model frees almost no disk. A model cannot be deleted while any
version of it exists, so its artifacts were already unreferenced before the
deletion. What accumulates is **whatever nothing points at**, over the life of
the install.

**Classification and retention** shows how much, and *Compaction* reclaims it.
Two things about how it behaves:

- **Nothing is reclaimed the first time it is seen.** An upload writes the file
  and then the record pointing at it, and a sweep passing between the two would
  see something that looks exactly like an orphan. A file has to be unreferenced
  across two separate sweeps before it goes, and one that gains a reference in
  between is left alone.
- **Two models can share one file.** Files are stored by their content, so an
  identical checkpoint used by two models exists once. Reclaiming asks the
  register whether *anything* still points at it, never whether a particular
  model did.

Compaction is refused entirely while an estate-wide legal hold is in force.
Whether bytes are still needed and whether anyone is allowed to destroy them are
different questions, and the first is not an answer to the second.

**Vacuum** is separate and is the part that genuinely follows a deletion: it
rewrites the database so removed rows stop occupying the file. It locks the
database while it runs and needs free space equal to the database's size, so
run it at a quiet moment.

Delta storage is **not** touched by either. The size is reported so you can see
it, but Delta keeps its own transaction log and deleting files underneath it
produces a table that refers to parts that are not there. Compacting a Delta
table is Delta's own operation.

## People and roles

`/admin/principals` — needs `principal:read`

Every principal, the roles they hold, and the column that actually matters: the
**effective** permissions, which is what the union of their roles adds up to.
Somebody holding two roles can do things neither role alone describes, and
reading the role names tells you nothing about that.

Below it, two tables that are easy to confuse and are not the same thing:

- **Roles nobody may hold together.** A static constraint on the *person*. A
  validator who may also approve is not performing effective challenge, whatever
  the org chart says, so the pair is refused at the moment roles are assigned.
- **Segregation.** A constraint on the *act*, evaluated against what this
  principal already did to this thing. Whoever developed a version may not
  approve that version — but they may approve a different one. This is checked
  at the act, not at the role, because it depends on history.

Creating a principal, changing roles and suspending an account need
`principal:manage` and go through `POST /api/v1/principals`,
`PUT /api/v1/principals/{username}/roles` and
`POST /api/v1/principals/{username}/suspend`. Each is recorded on the evidence
chain like any other governed act.

## Break-glass

The `admin` role is described as break-glass and is exempt from the
incompatible-roles check. That is not break-glass. It is a standing account that
happens to be powerful, and a standing powerful account is exactly the thing
break-glass exists to replace.

A break-glass **grant** is the audited path: it is asked for with a reason, it is
agreed to by somebody who is not the requester, it ends on its own, and somebody
who was not the user reads afterwards what was done under it.

| Step | Who | Note |
|---|---|---|
| Request | anybody signed in | asking grants nothing, and a platform that refuses people the ability to ask is one where the answer is somebody else's password |
| Authorise | an administrator | cannot be the requester |
| Use | the principal named | four hours, or one hour if it was opened unilaterally |
| Close | anybody signed in | optional; it ends on its own either way |
| Review | an administrator | never the person who used it, and the next request from that person is refused until it happens |

**A unilateral grant is allowed.** At three in the morning there may be only one
person awake, and refusing outright is how an institution ends up with a shared
password in a safe — no name, no reason, no window and no review. A unilateral
grant opens, gets a one-hour window instead of four, is flagged, and its review
is not optional.

**Expiry does not depend on the batch.** A grant is closed to MAYA the instant its
window ends, whether or not `break_glass.expire` has run. The job exists so the
table reads correctly, not to enforce anything.

**Read `unglassed` before anything else on that screen.** You cannot find
break-glass abuse by watching break-glass — anybody misusing emergency access
would simply not open a grant for it. The number that finds it is privileged acts
by an administrator that happened under **no** grant, which MAYA folds out of the
evidence chain rather than taking anybody's word for.

See [Break-glass](/break-glass).

## Policy gates

`/policies` — needs `policy:read`

The four gates a model passes through, what each currently demands, the drafts
nobody has published, and the **drift** each publication caused — read off the
evidence chain rather than recomputed, because a comparison was made against the
rule in force at the time and that rule may since have been superseded twice.

Authoring a gate and putting it in force are separate permissions on purpose.

## Configuring the platform, and what you cannot configure

`GET /configuration/boundary` publishes the line. Read it before you write any
YAML.

> "Configuration as code" done naively to a governance platform is the single
> most effective way to defeat one, because **the gates and the git repository
> end up with the same approval process** — and that process is a pull request
> reviewed by whoever is on shift.

**What you configure** is where your firm's own judgement belongs: your policy
gates, your warrant profiles, your monitoring defaults, your appetite limits,
your retraining policies, your remediation costs.

**What you do not configure** is not a list of things somebody forgot to expose:

| Not configurable | Why |
|---|---|
| The lifecycle state graph | A firm that could add a transition could add one that skips approval — and the graph is the only thing making *approved* mean the same in two institutions |
| The tier lattice | The adjunction between a tier and the controls it owes is the argument, not a setting. A configurable lattice can be made to say tier 1 owes what tier 4 owes |
| The trainability fibration | A class is derived from what a version declares and never asserted. Configuring the derivation would make it an assertion with extra steps |
| The refusal taxonomy | A refusal code is an interface. Renaming one in configuration breaks every caller that handles it — silently, at the moment it fires |
| The evidence chain | Append-only and hash-linked is what makes the record evidence rather than a table |
| Segregation of duties | The incompatible-role pairs are the three lines of defence. Configuring them away is configuring away the reason the platform exists |

### Plan before you apply

`POST /configuration/plan` shows exactly what would change and **which way each
change points**. Read `loosens` first.

*Three rules changed* is not a reviewable sentence. *Two of these three let
something through that is refused today* is.

The direction is computed from the shape of each change rather than asserted by
whoever wrote it — and where the shape gives no reading it comes back `neutral`
and is **not guessed**, because a wrong direction on a review screen is worse
than none: somebody stops reading the diff.

### Applying is a governance act

`POST /configuration/apply` records the diff, the rationale and the author on the
evidence chain. It is not a deployment step, and a configuration that applied
silently would let somebody change every gate in the estate with a git push and
no approval.

**A plan that loosens needs a named approver.** A configuration that tightens can
be a deployment; one that loosens is a decision, and the whole risk of
configuration-as-code is that the two travel in the same pull request.

Each section is still applied through its own register, which keeps its own
approval. There is no path here that writes a policy directly — a second way to
publish a gate is always the one without the signature.

Export reads **the registers in force**, never the last file applied. That is the
difference between a description of the platform and a description of somebody's
intentions, and running an export-then-plan is the only proof that your
repository and your platform agree.

## Regulatory regimes

`/admin/regimes` — needs `regime:read`

A regime is a supervisor's rulebook written down as obligations over a vocabulary
of its own. MAYA holds its state in *its* words, so applying a regime means
translating — and a translation that quietly loses a term has not preserved the
obligation, it has weakened it.

Each regime therefore reports whether its encoding is **consistent**: whether
everything the obligations mention is something MAYA can actually answer. A
regime that fails this refuses to be activated, rather than activating and
abstaining on the parts it cannot see.

Every activated regime answers about a model **separately**, and the answers are
deliberately not merged into one verdict. Two supervisors disagreeing is
information; averaging them away is not.

## Scheduled jobs

`/admin/scheduler` — needs `scheduler:read`

What runs unattended, what each job is for, when it last ran and whether it
succeeded. The health of the **scheduler itself** is the first thing on the
page, because a scheduler nobody notices has stopped is the same failure as a
monitor nobody notices has stopped, one level up.

Every run is recorded on the evidence chain, successful or not. "The batch did
not run" is a governance fact, not an operational one: expiry, staleness and
review dates are all computed by these jobs, and an estate whose jobs stopped
looks exactly like an estate with nothing outstanding.

Running the batch by hand needs `scheduler:run` and records the same evidence a
scheduled run does, so a hand-run is never invisible.

## Evidence integrity

`/admin/evidence` — needs `evidence:read`

Two questions, kept apart, and the distinction is the whole point of the screen.

**The chain against itself.** Every node is walked, and each node's content hash
is *recomputed from its own fields* rather than trusted as stored — so an edited
payload breaks this check and not only a broken link.

**The chain against a second medium.** The anchors are heads copied to
write-once storage outside the database. This is the only check here that
somebody holding the database cannot simply satisfy, because a chain rewritten
from the first node passes the first check perfectly.

Merging the two into a single green tick would be this platform's own recurring
defect: a control that reports success while answering a narrower question than
the reader believes it answered.

**The chain against a clock that is not ours.** Both checks above are arguments
from MAYA's own clock, which is the party being asked making a statement about
itself. The third card is an RFC 3161 timestamp: a token from an authority
outside this platform, over an anchored head.

Read what it proves before relying on it, because it is narrower than the phrase
*tamper-evident* suggests. A token bounds a head **from above only** — it proves
this hash existed *no later than* that time, which is exactly what defeats
writing a chain after the fact and dating it before. It says nothing about how
early the head existed, nothing about whether anything was deleted, and nothing
at all about the period before the first token was taken.

Three states, and `unverified` is a real one. MAYA is not the authority, and it
does **not verify** by default: checking a token means holding a certificate
chain and deciding which roots to trust, which is a decision your security
function has already made for the whole institution. Wire a verifier and the
state can reach `verified`; until then a held token reports as `unverified`,
which is neither *no token* nor *a good one*.

If no authority is wired at all, the screen says so rather than showing a tick.

An anchor is never written for an empty chain. An anchor for sequence zero is a
permanent claim that nothing can ever satisfy, which would make every fresh
instance accuse itself.

## Live log

`/admin/logs` — needs `log:read`

The last lines this process wrote, as it writes them. Until this screen existed
the only way to read MAYA's log was to be the person who started the process,
which meant the operator asked to explain a refusal, and the tester who wanted
to know what the server made of their call, both ended up asking a developer to
read a terminal to them.

**Not the evidence chain.** Evidence records what was *decided*, and is
immutable, hash-linked and exportable. This is a rolling window of what happened
around those decisions, and it ages out. Diagnose with it; cite the other one.

**Not a control.** The screen reads. It cannot change the level, clear the
buffer or write a line — a screen that can quieten the log is a screen that can
hide what it is showing you. Every endpoint under `/api/v1/logs` is a `GET`.

**Not a file tail.** The lines are kept in the process, so the screen works
identically whether the deployment writes to a file, to stdout, to a journal or
to nothing at all — which is the case that matters, because the deployments that
most need a log viewer are the ones where the file belongs to somebody else.

The thing that makes it worth opening is the **request id**. Every response
carries one, and every line written while serving that request carries the same
one, so clicking an id narrows the view to one call end to end across every
module that touched it. `logging.ring` in the configuration sets how many lines
are held; when the window has turned over faster than a reader could keep up,
the screen says so rather than presenting the gap as continuity.

Access lines for stylesheets, fonts and scripts are hidden by default, by a
switch that says so. One page load is thirty of them.

Anything that names itself a credential — `password:`, `api_key=`,
`Authorization: Bearer …` — is blanked as the line is captured rather than as it
is displayed, so the stream, the JSON and the saved file cannot disagree.

## Runtimes and fibres

`/admin/runtimes` — needs `model:read`

One question asked twice.

The **grammar** is what a warrant may say: the verbs, the runtimes that may host
a kernel, where inputs may be bound from and where outputs may be written. The
warrant JSON Schema is generated from this same vocabulary rather than kept
beside it, so a client validating against the schema is validating against what
the platform will actually admit.

The **fibration** is what each trainability class must carry once admitted — its
evidence, its lifecycle, its metrics, its templates. A class with a missing facet
is one the platform would answer questions about by omitting them, so start-up
refuses on a gap rather than booting partial. If the gaps table on this page is
ever populated, the instance should not have started.

## The register's edges

`/admin/perimeter` — needs `policy:read`

Everywhere else in MAYA the record is MAYA's own. This screen is the places where
it is not, and each is **narrower than its name suggests** — which is the reason
there is a screen rather than an API and a paragraph in a design document.

**Installed is not enabled.** A firm's own package can add a test type, a metric
type, a template, a notification channel or a fibre, declared under the
entry-point group `maya.extensions`. Discovery reads packaging metadata and
**imports nothing**. Enabling is a separate act that configuration has to name,
because a control that switched itself on when somebody bumped a dependency is a
control nobody turned on — and one that switched itself *off* the same way is
worse, since the platform would then report a control operating that is not.
`seen` is the ordinary state and not a fault. The closed axes are listed with
what each closure protects, because a closed axis here is the feature rather
than a missing one.

**What another system's export can and cannot say.** MLflow, Unity Catalog and a
git tree can be read — from an **export document** that platform produced, never
from its API, because a governance register holding read credentials to every ML
platform in the bank is the broadest standing access anybody holds. What comes
back is **candidates for triage, never registrations**: the five governance facts
listed on the screen are in no ML platform anywhere, and a register that inferred
them would have manufactured exactly what it exists to hold.

**What a scanner has to send back.** MAYA does not sweep drives, and the reason
is the same one. What it publishes is the contract: the fields a candidate and a
sweep must carry, with the reason for each, and a confidence ceiling strictly
below certainty. A sweep that misses the contract is refused **whole** — keeping
the good rows would make the precision figure grade something other than the
scanner that produced it. Precision is computed from what triage dismissed;
**recall is not computable** and the screen says so, because nothing here knows
what a scanner did not look at.

**What has left the building.** Every export pack shared outside the platform:
who it went to, why, whether it is still live, how many times it was read, and
how many reads were **refused**. A share is a time-boxed link to a *content
digest* and never to a path — a link to a location serves whatever is at that
location later. It is **not an examiner portal** and establishes no identity, and
both facts are published rather than left ambiguous. Revoking one ends access and
does not unsend a document; the record keeps what it already served.

**A rulebook the bank already has.** A decision table exported as CSV, or a DMN
file out of a BPM suite, read into a rule set **candidate**. Nothing is
imported: what comes back goes through the same check, trial and publish path a
hand-written rule set takes, second-person approval included. The refusals are
the part to read. A cell that is a human judgement — *good credit*, *as agreed*
— is reported rather than guessed at, and a document with any such cell is
refused **whole**, because the rows a parser finds hard are the judgement calls
and those are what a rulebook exists for. A hit policy that cannot map onto
first-match is refused by name with what the approximation would silently
become. And a catch-all is derived from first-match semantics rather than
inferred from the last row's position. A **stored procedure** is not translated
and will not be: SQL is a general language, a translator would be a compiler,
and a wrong compiler produces a rule set nobody can tell is wrong by reading it.

**What a warrant signature proves.** The one panel here that runs the other way:
somebody relies on MAYA rather than MAYA relying on them. Each audience's
signing key is *derived* from its own principal, so a compromised engine can
forge warrants for itself and for nobody else. Read the *does not prove* column
as well: a verifier holds the key it verifies with, so a descriptor is evidence
**to the bank** and not to anybody outside it. If the panel says this instance
signs with a published default key, stop and set `warrants.signing_key` — anyone
with a copy of the repository can forge a warrant it will verify.

An engine collects its own key with `POST /api/v1/warrant-signing/key`. That is
the only endpoint in MAYA that returns a secret; the disclosure is recorded on
the evidence chain, the key is not, and MAYA cannot tell whether the engine
stored it safely.

---

## Backing it up

Two stores, one snapshot. The database holds the evidence chain; `data/worm/`
holds the heads anchored out of it. They must be backed up **together**.

Restore a database older than its anchors and `/admin/evidence` will report a
disagreement permanently — a write-once store has no operation that removes an
anchor, and giving it one would defeat the whole control. That is the anchoring
working, not a fault, and it is the reason the pair is a pair. The full table of
cases is in `docs/09-security-compliance.md` §4.6 in the repository — not
linked, because this page is rendered in the interface and the design
documents are not served with it.

If the anchor root is genuinely lost, do not reconstruct one from the database.
An anchor derived from the thing it checks proves nothing. Start a new root and
record that verification before that date rests on the chain alone.

## Where the feature data lives

Governance state is in the database. Feature values, dataset snapshots,
telemetry and monitoring observations are not — they run to hundreds of
millions of rows, and they live in a **versioned table format** under
`data/delta/`, because a table version *is* the transaction-time clock a
point-in-time read pins to.

Which format is a choice, and there are two:

| | |
|---|---|
| **Delta Lake** | The default. It is what the soak run and every worked example ran against |
| **Apache Iceberg** | For a bank whose lakehouse is already Iceberg, so Trino, Athena or Snowflake can read the feature store directly rather than keeping a second copy of it |

Set it with `MAYA_TABLE_FORMAT=iceberg`, or `data.table_format` in the
configuration file; the environment wins. On Iceberg, the catalog defaults to a
SQLite file inside the warehouse directory, so a laptop needs nothing running
alongside it — `data.iceberg.catalog` points at Glue, Nessie, Polaris or a REST
catalog where a bank already operates one.

**Choose it once, before there is data.** Switching the format on an estate that
already holds feature data **does not move that data**. The old tables are in
the old format, the new store does not see them, and a feature view whose data
it cannot see reads as **empty rather than failing** — which is the worst way
to find this out. Start-up logs a warning naming the format and the root
whenever Iceberg is in use; the live log will show it. Nothing in MAYA converts
between the two.

One thing you may notice either way: a Delta version is `0, 1, 2, …` and an
Iceberg version is a nineteen-digit snapshot id. Both appear in the interface as
the pin a featureset binding carries, and both mean the same thing — *this read
is fixed to these bytes*.

There is a second and unrelated choice underneath Delta: whether the compiled
`deltalake` package or MAYA's own pure-Python `maya_deltalake` does the writing,
for estates that forbid binary wheels. It is chosen automatically, and both
write the real Delta format, so a table written by either opens in Spark and
Databricks. `MAYA_DELTA_BACKEND` overrides it if you need to pin one.

## What is not here

Administration in MAYA is currently *reading* the platform's configuration.
Editing model classes, lifecycle definitions, document templates and the test
catalogue is still API work. **Nothing here sweeps for unregistered models** —
the contract a scanner must meet is published and running one is somebody else's
job — and the connectors read an export rather than reaching into another
platform. The estate is what somebody registered, plus what somebody triaged.
