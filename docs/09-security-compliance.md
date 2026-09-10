# 09 — Security: what runs, what a deployment owes, and what nobody does yet

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [04 — Architecture](04-architecture.md).

---

Every security defect this platform has had was the same defect twice removed: **a control that was
true of a design and false of the deployment.**

- *"No ambient cookie authority, so CSRF does not apply"* described [ADR-011](adr/ADR-011-decoupled-frontend.md)'s
  decoupled front end. What runs is a Jinja interface under a session cookie, so ambient authority is
  exactly what it has, and there was no token for as long as the sentence stood.
- *"Three independent layers, with Postgres row-level security as the last line"* described a schema
  with no RLS in it. There was one layer.
- *"The person who raised a finding may not close it"* searched the evidence chain under the
  finding's own id, found nothing, and **permitted everything**.
- *"The chain verifies"* re-linked each node's **stored** content hash, which proves the links are
  intact and says nothing about whether the thing linked is still what was recorded. An edited
  payload left a chain that verified and a record that lied.

None of those was a lie when written. Each was true of an intention. So this document is organised
around the distinction that would have caught all four, and every control table carries it:

| Where it runs | Meaning | What you may rely on |
|---|---|---|
| **Code** | Enforced by this repository, with a named file and, where one exists, a named test | The control operates wherever MAYA is deployed |
| **Deployment** | The code exposes the setting or the shape; somebody has to configure or operate it | Nothing, until an operator has done it — so it is an obligation, not a control |
| **Not built** | Designed and absent | Nothing. Plan as if it does not exist, because it does not |

A control in the third column is not a failure of honesty; it is the part of this document worth
reading first. §8 is the threat model, and it comes **after** the controls rather than before them,
because a threat table read first invites a reader to assume every row's controls exist.

---

## 1. Ambient authority

A session cookie is **ambient**: the browser sends it whether or not the page that triggered the
request came from us. That single property generates most of this section, and both defects it caused
were live.

### 1.1 Cross-site request forgery, and where the boundary falls

The cookie is `SameSite=Strict`, which is a real defence and is **somebody else's** — enforced by the
browser, removable by a client that does not implement it or an intermediary that strips the
attribute, and its removal invisible from here. Defence in depth is not a slogan in that situation:
it is the difference between a control we enforce and a control we hope for.

So there is a token as well, and the boundary it applies to is the part worth stating:

> **A state-changing method whose authority came from the session cookie — and nothing else.**

| Request | Token required | Because |
|---|---|---|
| `POST`/`PUT`/`DELETE` under a session cookie | **yes** | the authority is ambient |
| `POST` under HTTP Basic | no | the browser never sends that header unprompted; a caller who can set it already holds the credential |
| `GET`/`HEAD`/`OPTIONS` | no | nothing changes |
| `/login`, `/auth/login`, `/auth/callback` | no | they *establish* the session; there is no token to carry yet |

Requiring a token from a Basic-authenticated service client would protect nothing while breaking
every engine and script — which is how a security control ends up switched off in configuration.

| Property | Detail | Where it runs |
|---|---|---|
| Enforcement point | One middleware in `run_maya_web.py`, not a check in each route. There are **155 mutating endpoints**, and a control 125 places have to remember will be missing from the 126th | Code (`core/authz/csrf.py`) |
| Exemptions | **Exact paths, never prefixes.** A prefix exemption grows silently as routes are added beneath it — asserted in `tests/test_web_security.py` | Code |
| Token lifetime | **Per session, not per form.** A single-use token breaks the back button, breaks two tabs, and breaks every page that posts more than once. A control people route around is worse than one they never had, because it also reports success | Code |
| Minting | Lazily, on first render — so a session predating the control gets a token instead of silently skipping the check. There is no upgrade step whose absence disables it | Code |
| Comparison | `hmac.compare_digest`. It is the one place this codebase compares a secret, and a byte-by-byte `==` leaks the prefix through timing | Code |
| Transport | The `x-maya-csrf` header, or a `csrf_token` form field for the pages that post without JavaScript. A form body is read **once** and stashed on the request, because consuming it in middleware would make the route see a missing field rather than a middleware that ate the request | Code |
| Refusal | `csrf_token_invalid` → **403**, not 400. The request was understood; it is the authority behind it that is not accepted | Code |

**Middleware ordering is load-bearing.** The guard is registered *before* the session middleware,
which places it *inside* it — Starlette wraps later-added middleware on the outside, and a CSRF guard
running before the session is decoded has no session to compare a token against. It failed loudly,
which is the only reason this is a note rather than an incident.

The browser half is [08 §6](08-ui-ux.md): a `<meta>` tag, a jQuery hook, a `fetch` wrapper, and a
hidden field stamped into every posting form — same-origin only, because sending the token to another
host hands over the thing it exists to withhold.

### 1.2 The open redirect

`POST /login` honoured whatever `next` carried. `/login?next=https://evil.example/phish` sent the
browser there immediately after somebody typed real credentials into the real form on the real
domain. **That is the whole of a credential-phishing attack**, and the redirect is the part that
makes the link look legitimate — the part that was ours to remove. The same door stood open on the
SSO path, where the target survived a round trip through the identity provider, so it is bounded
before it is *remembered* rather than before it is followed.

`routes/base.py::local_path` accepts only a path. A scheme, a host, a protocol-relative `//host`, the
backslash spellings browsers normalise, and the control characters they strip before resolving a URL
are each **replaced by the fallback rather than sanitised** — a redirect target somebody had to
repair is a redirect target nobody understands.

### 1.3 The session cookie itself

| Setting | Value | Where it runs |
|---|---|---|
| `SameSite` | `strict` | Code |
| `HttpOnly` | Starlette's default on the session cookie | Code |
| `Secure` | `auth.session_https_only`, **defaulting to false** | **Deployment.** It was hard-coded false, so the cookie never carried `Secure` even behind TLS and there was no key to set. There is now a key, and it still has to be set |
| Max age | 8 hours (`auth.session_max_age`) | Deployment |
| Signing secret | `auth.session_secret` | **Deployment.** Four values ship in this repository and are therefore public. Starting on one of them logs a warning naming the consequence: anybody with a copy of the source can forge a signed-in session as any user, including `admin`, with no password. The fallback stays — refusing to start would be worse for a workstation — but it can no longer be done by accident quietly |

### 1.4 The response headers

There were none. Every page here renders model names, finding titles and document
titles that people supplied, and nothing stopped an injected `<script src>` from
loading — so a stored-injection defect anywhere in the register became a
credential theft in the browser. Six headers now go on **every** response,
including the API's:

| Header | Value | What it stops |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'` with `script-src`/`style-src` also allowing `'unsafe-inline'`, `img-src 'self' data:`, `connect-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'` | An injected script or style **from another origin**, a page framed for clickjacking, a rewritten `<base>`, and a form posted somewhere else |
| `X-Frame-Options` | `DENY` | The same clickjacking, for the proxies that strip CSP |
| `X-Content-Type-Options` | `nosniff` | A stored document served as `text/plain` being executed as script because a browser guessed |
| `Referrer-Policy` | `same-origin` | A URL carrying a model URN and a semver appearing in somebody else's referrer log |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` | Capabilities nothing here uses being available to injected code |

**`'unsafe-inline'` is in the policy and it is a decision, not an oversight.**
Several pages carry inline handlers and `<style>` blocks. A policy that broke
them would be switched off within a week, which is strictly worse than one that
blocks the external-origin case and says so in writing. Removing it means moving
those blocks out first, which is its own change and is in [10](10-roadmap.md).

**The strictness cost something, and that is the point.** `script-src 'self'`
made FastAPI's `/docs` and `/redoc` blank on every instance, because both load
Swagger UI and ReDoc from `cdn.jsdelivr.net`. The fix was **not** a CDN
exception — a hole opened in the policy for a documentation page, on a platform
whose argument is that nothing here calls out, is the wrong trade. Swagger UI is
vendored beside bootstrap and jquery; `/redoc` is gone rather than blank. That
this took two milestones to notice is itself the finding: nothing tested a page
the framework generates rather than a template this repository owns.

---

## 2. Identity, and the four questions it answers

Authorisation here is four separate questions, deliberately kept apart. Collapsing any two of them is
how a validator in the UK entity ends up approving a US model.

| Question | Mechanism | §|
|---|---|---|
| Who is this? | Password, HTTP Basic, or SSO | 2.1, 2.2 |
| What may they do? | 8 roles over a closed vocabulary of **83 permissions** | 2.3 |
| What may they do it **to**? | Scope: legal entity × domain | 2.4 |
| What does their own history forbid? | Segregation of duties, read from the evidence chain | 2.5 |

### 2.1 Local credentials

**Password.** PBKDF2-HMAC-SHA256, **200,000 iterations**, a 32-hex-character salt per principal. A
successful verification is cached for **60 seconds** under a per-process peppered key that never
holds the password — and the cache shortens the key derivation and **never the decision**: `status`
is re-read from the store on every request, so suspending a principal takes effect immediately. An
unknown username is hashed against a dummy salt, so a wrong name costs what a wrong password costs.

**HTTP Basic**, for services, against that same register — one identity store rather than two. A
malformed `Authorization` header is treated as **absent** rather than as an error, because a broken
header and a missing one should not be distinguishable to a prober.

### 2.2 Single sign-on

The authorisation-code flow with **PKCE, a state parameter and a nonce** — all checked, and PKCE used
even when a client secret is configured, because the secret protects the client and PKCE protects the
authorisation code. Discovery must yield an issuer matching the configured one; the state must match
and be under ten minutes old; the ID token's issuer, audience, expiry, issued-at and nonce are each
checked with 120 seconds of leeway.

**RS256 verification is in the standard library** (`core/authz/jws.py`), for the same reason every
front-end asset is vendored: a governance system that cannot be deployed air-gapped is one somebody
works around. Two details are the whole of why it is written rather than imported:

- The verifier **constructs** the padded block the signature should have produced —
  `00 01 FF…FF 00 || DigestInfo || SHA-256` — and compares the whole of it, rather than parsing what
  it recovers. That is the difference between correct PKCS#1 v1.5 and the Bleichenbacher forgery,
  which works precisely against verifiers that parse.
- It **decides the algorithm itself** rather than reading `alg` from the token. That is the other
  famous way a JWT is accepted with no signature at all.

Alongside: a 2048-bit minimum modulus, and a refusal to try keys in turn when a token carries no
`kid` and the provider publishes several — `ambiguous_key`, because guessing is how a verifier ends
up accepting a signature from a key nobody meant to trust. Tested against genuine OpenSSL-signed
tokens rather than against its own arithmetic.

**What is not mechanical is roles.** An identity provider that grants MAYA roles is one that decides
segregation of duties, and the person administering it is very often the person whose duties are
being segregated. So:

- **Group claims are mapped, never obeyed.** A group with no mapping in `auth.oidc.roles.*` grants
  nothing, and never grants itself.
- **The incompatible-roles check of §2.3 applies to a directory exactly as to a local principal.** A
  group membership mapping to a conflicting pair **refuses the login** rather than accepting both or
  quietly reducing to one — and it is checked *before* the provisioning check, so the lesser problem
  cannot hide the greater.
- **Provisioning on first login is off by default**, because it hands everybody in the directory a
  foothold in the model register.
- The issuer, subject and the groups that produced the roles are recorded on an evidence node, so
  *"why did this person have that role in March"* survives the directory moving on. **The token is
  not** recorded.

**No SAML and no SCIM.** A SAML-only directory is unsupported, and automatic deprovisioning is not
built, so **a leaver is suspended by hand**. That is a real operational obligation, and stating it
here is cheaper than a bank discovering it during an access review.

### 2.3 Roles and permissions

**Eight roles across three lines of defence**, each a named set drawn from a closed vocabulary of
**75 permissions** in `resource:act` form. Two roles are supersets of others *by construction* rather
than by copying, which is what stops the two drifting apart.

| Role | Line | Holds | The sentence that defines it |
|---|---|---|---|
| `model_developer` | First | 25 permissions | *Builds models and features. Cannot approve, tier or validate.* |
| `model_owner` | First | `model_developer` ∪ 17 more = 42 | *Owns a model end to end: registers it, requests its tier, issues warrants.* |
| `validator` | Second | the 16 read permissions ∪ 18 more = 34 | *Second line. Runs effective challenge and closes findings. Never builds.* |
| `model_risk_manager` | Second | `validator` ∪ 16 more = 50 | *Second line with authority: approves versions, moves aliases, sets tiers.* |
| `auditor` | Third | the 16 read permissions ∪ `finding:raise` = 17 | *Reads everything, raises findings, remediates nothing.* |
| `operator` | — | 7 | *Runs the platform and the monitoring batch. No governance authority.* |
| `service` | — | 7 | *A non-human principal. Resolves and executes warrants; signs in to nothing.* |
| `admin` | — | all 72 | *Everything, including principal management. For bootstrap and break-glass.* |

Three distinctions in that vocabulary are the kind usually collapsed, and each is collapsed at a
cost:

- **`version:sign` and `version:approve` are separate.** A validator holds the first and never the
  second: signing a quorum is not the same act as approving alone.
- **`policy:author` and `policy:publish` are separate**, and sit with different roles (§5) — and separate *permissions* is not the control. Somebody holding both authored a gate and enacted it alone until `policy:publish` joined the segregation table above, which is what makes the separation a fact about the act rather than a fact about the role matrix.
- **`monitor:observe` and `monitor:evaluate` are separate.** The `service` principal that runs the
  model hands over the scores and stops there. An engine that could both produce a population and
  rule on it would be the only witness to its own model's behaviour.

**Four incompatible pairs**, refused at the point a principal is created *and* at SSO login:

| Pair | Because |
|---|---|
| `model_developer` + `model_risk_manager` | a developer who can also approve versions is a first line approving its own work |
| `model_owner` + `model_risk_manager` | an owner who can also approve and tier their own models defeats second-line challenge |
| `model_developer` + `auditor` | the third line must not build what it audits |
| `model_owner` + `auditor` | the third line must not own what it audits |

`admin` bypasses the conflict check. That is deliberate and it is the break-glass path; it is also
the single most valuable line in an access review of this system.

### 2.4 Scope

Two dimensions — **legal entity** and **domain** — because those are the two a bank organises around:
model risk aggregates by entity, and entities answer to different supervisors; second-line
specialisms divide by domain. An empty tuple on either means unrestricted there, which is deliberate:
enumerating every entity for every principal is the design that makes people grant a wildcard to get
on with their day.

It filters **listings as well as detail reads**, which is the property that matters. A model out of
scope is invisible rather than merely unopenable, because the existence of a model can itself be
sensitive — and because a count that does not add up discloses it anyway.

> **Row-level security is not built.** Earlier drafts described three independent layers with Postgres
> RLS as the last. The shipped schema has no RLS, no session variables and no separate application
> role, so **there is one layer, in the application**. Business unit, geography and classification are
> not scope dimensions. A reader planning a multi-entity deployment should treat defence in depth here
> as **unbuilt** rather than as configured.

### 2.5 Segregation of duties

Enforced, and — this is what distinguishes it from a role matrix — **read from the evidence chain
rather than from a second who-did-what table**. A duty conflict is a question about what a person
*did*, and the chain is the only record of that which cannot disagree with itself. There is nothing
to keep in step, and tampering to clear a conflict breaks the chain.

| Act | Refused when the actor recorded | Because |
|---|---|---|
| `version:approve` | `version_created` against this version | the person who created a version may not approve it |
| `alias:move` | `version_created` against this version | the person who created a version may not promote it into an environment |
| `validation:conclude` | `version_created` against this version | effective challenge requires a validator independent of the build |
| `finding:close` | `finding_raised` **for this finding** | closure must be attested by somebody other than the raiser |
| `finding:extend` | `finding_acknowledged` **for this finding** | an extension is where somebody independent asks whether the date was ever realistic |
| `version:sign` | `version_created` against this version | a quorum is people independent of the build, and only `version:approve` was here — so the rule held where one signature sufficed and lapsed exactly where two were required, which is the opposite of the intended gradient |
| `policy:publish` | `policy_drafted` against this policy | a gate authored and enacted by one person is a gate nobody reviewed. `/policies` said in plain words that the register enforced this while `publish()` never compared the publisher to the author and the act was absent from this table — the same omission as `version:sign`, found the same way |

The last two rows carry a lesson worth keeping. A rule may name the **payload field** carrying the
identity it is about, because an evidence node's *subject* is not always the thing an act concerns: a
finding is raised against the **model**, which is where a reader looks for it and where a compiled
document cites it, while the act being checked is about one **finding**. Without that field the
raiser-may-not-close rule was **inert over HTTP** — it searched under the finding's own id, found
nothing, and permitted everything. A segregation control that silently permits is worse than none,
because it is reported as present. A rule that declares a payload key and is given nothing to match
on now **refuses to guess and matches nothing**, which is loud in the tests rather than silent in
production.

Identity comparison goes through `same_person` everywhere. It was one `!=` in this module for a
while, and that one comparison decides every rule here — so an actor spelled two ways disabled all of
them at once.

The refusal names the act, the actor and the chain position: *"the person who raised a finding may
not close it — j.okafor recorded 'finding_raised' against this subject at evidence #4821."*

**What is not enforced here, by name.** Policy author ≠ publisher is enforced by *permission* (§5)
rather than by an actor comparison, so one person holding both roles could do both. The overlay
proposer ≠ approver rule lives in `core/overlays/`, not here. And there is **no nightly re-sweep** for
conflicts created retrospectively by a role change.

---

## 3. Bytes the platform did not write

A model artifact is the one input that is code. Everything in this section follows from that.

### 3.1 The store: the digest is the address

A version could always *name* an artifact — `artifact_uri` and `artifact_digest` were columns and the
engine verified the digest before loading. What it could not do was **hold** one. The bytes arrived
on disk out of band, which meant the thing the whole chain of custody rests on came by a route the
platform had no view of, and `artifact_uri` was whatever string somebody typed.

`core/artifacts/store.py` is content-addressed, and that is not a storage convenience:

- *"the bytes match the warrant"* is true by construction rather than by a check somebody remembered
  to write;
- storing the same weights twice stores them once, which matters when a challenger differs from its
  champion by a configuration and not a file;
- an artifact **cannot be edited in place**: edited bytes are a different address, and the old
  address still resolves to what was approved.

| Property | Detail |
|---|---|
| Streamed, never buffered | Hashed and written as bytes arrive, into a staging file moved into place only once the whole thing has landed — so a reader never sees half an object under a digest promising the whole one. A model file does not fit in memory twice, and a governance platform should not be the process that discovers this |
| Declared digest | Optional, and **checked** rather than trusted. A mismatch is refused rather than silently stored under the address of what actually arrived — the difference between *"we have the file you meant"* and *"we have a file"* |
| Ceiling | 8 GiB, refused with the reason: a governance platform is not a model store of last resort |
| `verify()` | Re-hashes the bytes on disk. Content addressing makes tampering hard, not impossible — the filesystem is still a filesystem — and *"is the address right"* is a different question from *"are the bytes still what it promises"*, which is why it is a separate call rather than something every read of a multi-gigabyte file does |
| Layout | Two levels of fan-out from the digest, because one directory holding a hundred thousand files is slow on every filesystem that has ever existed |

### 3.2 The format list is closed, and one bit on it matters

Eight formats are storable: ONNX, PMML, safetensors, TorchScript, PFA, JSON, tarball, GGUF. The list
is closed because an artifact's format decides how it is loaded, and *"we will work it out at load
time"* is how a pickle gets deserialised in a control plane.

> **Pickle, joblib and `.pth` are not on the list at all.** Not "denied in production with an
> expiring exception" — the store refuses them outright with `unknown_format`. This is stricter than
> the format policy earlier drafts of this document described, and it is the shipped behaviour.

The position is evidence-based: a large fraction of popular public models still ship as pickle,
malicious `.pth` files with embedded remote-access payloads have been published to trusted hubs, and
scanners have both false positives and false negatives. A bank should not accept that class of risk
when ONNX and safetensors exist.

**`EXECUTES_ON_LOAD` is the distinction the rest of the platform reads.** TorchScript and tarballs
run code the platform did not write when they load; the other six do not. The flag is recorded beside
the bytes and travels:

- `describe()` returns it, so the warrant builder does not have to remember which is which;
- `/models/new` renders it against each format in the picker, so the warning is attached to the
  choice rather than left in a document somebody read once ([08 §7](08-ui-ux.md)).

Two smaller decisions are load-bearing. The format is kept in a **sidecar** rather than in the
address, because the address is derived from the content: two artifacts with identical bytes and
different declared formats are the same artifact, and the first declaration stands. And losing a
sidecar costs a lookup rather than an artifact — the format is also on the version manifest.

### 3.3 The sandbox, and the boundary it publishes

Artifact-backed runtimes run in a child process with resource limits taken from the warrant. The
table below is the target; what ships is narrower, and the gap **is** the subsection: a boundary that
is published is one an engineer can plan around, and a boundary that is implied is one somebody
discovers by trusting it.

| Property | Target | As built (`core/execution/sandbox.py`) |
|---|---|---|
| Isolation | gVisor or Kata; one pod per task | A **`spawn`ed** child process, not `fork` — a forked child inherits the parent's open database handles and signal state, and an artifact that crashes holding them is a much messier failure |
| Network | Deny-all egress | **None.** The child shares the network namespace |
| Filesystem | Read-only root, capped `tmpfs` scratch | **None.** The child shares the filesystem |
| Identity | No service-account token, no cloud credentials | Inherited from the parent |
| Limits | CPU, memory, PID, wall clock | `RLIMIT_CPU` and `RLIMIT_AS`, **read from `constraints.resources` on the warrant**, defaulting to 30 s and 2 GB. The wall clock is the CPU budget plus two seconds, so a process that is waiting rather than spinning is still reclaimed |
| Syscalls | Restrictive seccomp profile | **None** |
| Output | Structured result only | A four-kind pipe: `ok`, `refused` (the original refusal re-raised with its code and remediation), `limit`, `failed` |

Two implementation details are load-bearing rather than incidental. The memory budget is **additive
to the interpreter's own footprint**, read from `/proc/self/status`, so a 512 MB budget means 512 MB
for the model rather than for Python and the model together. And the runtime's dependencies are
imported **before** the limit is applied, so a library's import cost is never charged to the model —
otherwise the first ONNX model of the day fails for a reason that has nothing to do with it.

**Which runtimes are isolated:** `onnx` and `pmml`, the artifact-backed ones. `quantlib` is not, and
the reason is stated rather than implied: it loads no artifact, so there is nothing untrusted to
isolate from. A bound callable runs in process by construction and is named as such.

`describe()` publishes the boundary in the words a caller receives — what it protects against: *a
runaway loop, an allocation storm, an artifact crash*; and what it does not: *a deliberately hostile
artifact, because the child shares the filesystem and the network namespace*, and *bound callables,
which run unisolated by construction.*

So `P7` — *the control plane never loads a model artifact in-process* — holds for ONNX and PMML, and
is enforced by a process boundary rather than by a container. **Against a hostile artifact it is not
a control.** Blocking the filesystem and the network needs a container, a VM or seccomp, and
pretending otherwise would be worse than saying so, because a reader who believes this is a security
boundary will put a vendor's binary behind it.

---

## 4. The record

**There is no separate `audit_log` table. The evidence chain is the audit log**, and that is a
deliberate consolidation rather than an omission: two records of who did what are two records that
can disagree, and segregation of duties (§2.5) is decided by reading the chain — which only works if
the chain is the record.

```
evidence_node:  seq · kind · subject_type · subject_id · payload · parents
                contains_personal_data · trust · recorded_at · recorded_by
                content_hash · prev_hash · chain_hash
```

**Two structures, one table.** The `parents` edges form a DAG and say *what supports what*. The
`seq`/`prev_hash` chain is linear and says *what order things happened in*, which is what makes
deleting a leaf and inserting into the past both detectable.

### 4.1 Verification re-derives, and this is where a real defect lived

`verify_chain` recomputes each node's `content_hash` **from the node's own fields** — kind, subject,
payload, parents, actor, trust — and only then checks the links. Re-linking a *stored* content hash
proves the links are intact and says nothing about whether the thing linked is still what was
recorded, so an edited payload left a chain that verified and a record that lied.

The scale suite found it. The unit test that should have found it years earlier was **named for
payload tampering while actually altering the stored hash**: a test passing for a reason other than
its name, which is the failure mode a green suite is worst at showing you. Both are fixed, and four
checks now run in order:

> sequence gap → `prev_hash` → **re-derived `content_hash`** → `chain_hash`

### 4.2 The append path

`L-18` — no personal data in an evidence node — **is enforced in the append path, not in DDL.** A
node flagged `contains_personal_data` stores an empty payload *and is hashed over what it stored*, so
it verifies against itself. Hashing the original would make every such node fail its own
verification, which is the trap the obvious implementation falls into.

The append is **atomic and retried**, and that too was a defect with a governance consequence rather
than an operational one. The chain is a read-then-write — take the head, insert head+1 — and every
statement once opened its own transaction, so two concurrent acts read the same head and the loser
hit the `UNIQUE` on `seq`. Measured at four threads: 7% of appends raised, and every service commits
its own row **before** appending evidence, so twenty-four concurrent registrations produced
twenty-four models and fourteen evidence nodes.

The consequence was worse than a missing row. Segregation of duties is decided by reading the chain,
so a lost `version_created` node did not fail closed — it meant *"you cannot approve what you
created"* had nothing to read, and the developer could approve their own version. Retries are
jittered, because without that every loser retries at the same instant and eight threads exhaust
eight attempts without any of them making progress.

### 4.3 Verification has two costs, and they answer different questions

| Call | Cost | Question |
|---|---|---|
| `verify_chain` | O(chain) | *Is the whole chain intact?* The real control. Run on the schedule, where its cost is somebody's decision rather than a side effect |
| `verify_since_checkpoint` | O(nodes since) | *Has anything broken since the last full verification?* What a readiness probe should ask |

The full walk was on the readiness probe and on the dashboard: 2.9 seconds and 83 MB at forty
thousand nodes, and a busy instance reaches a million in half an hour — at which point an
orchestrator takes the node out of service for being slow to say whether it is healthy. The
checkpoint trusts that the chain was intact where it was last verified and checks only what came
after, which is a strictly weaker claim and is labelled as one in the response (`"scope":
"incremental"`).

> **The checkpoint is not an anchor.** It lives in the same database as the chain, so an attacker who
> can rewrite the chain can rewrite the checkpoint. Writing the daily chain head to WORM storage and
> to an RFC-3161 timestamping authority remains **not built**, and until it exists, verification
> compares the chain against itself — and self-consistency of a chain an attacker controls proves
> less than it appears to.

### 4.4 The log is not the audit trail, and is what makes it usable

The chain records what was **decided**; the log records what happened around it. A `warrant_resolved`
node and the six lines preceding it join on the request id, or they do not join at all.

| Property | Detail | Where it runs |
|---|---|---|
| Every line | Carries a **request id** and the **principal**, on a `logging.Filter` installed on the *handler* rather than on a logger — a filter on a logger does not run for records propagating up from its children, and every logger here is a child of the root | Code (`core/log.py`) |
| The identifiers | Ride on **one mutable dict** in a `ContextVar`, not a variable per field. A sync route runs in a threadpool with a *copy* of the context, so a `ContextVar.set` inside it is invisible to the middleware that resumes afterwards; a copied context still points at the same dict, so a write crosses that boundary while a rebind does not | Code |
| Every response | Returns `X-Request-ID`, so a caller can quote it in a bug report | Code |
| One access line per request | Method, path, status and duration, at the level the outcome deserves: ≥500 is an error, ≥400 is a warning, otherwise info. The principal is put on that record **by value** as well as by the filter, because the context is gone by the time anything inspects it | Code |
| An **inbound** request id | Honoured only when it is safe to log. The value reaches a log file, and a newline in it forges an entry — so anything outside `[A-Za-z0-9._:-]{1,64}` is **replaced rather than escaped**, and the response header says which id was used. Honouring an id is what lets one trace span a gateway, a queue and this process; honouring it unchecked is log injection | Code |
| The request id in evidence | Deliberately **absent**. It would change every content hash for a field belonging to a transport rather than to a governance decision | Code |
| JSON lines | Offered, not imposed. A human reading a terminal is served worse by JSON, and an instance nobody ships logs from should not pay for a format only a machine reads | Deployment |

### 4.5 What the record does not cover

| | |
|---|---|
| **Reads are not recorded** | Every governance *act* appends a node — a version created, a tier assessed, an alias moved, a finding raised or closed, a document accepted, a policy published, an SSO login and the groups that produced its roles. Sensitive **reads** — an artifact download, a PII feature preview, an examiner's query — are not. An access-review question about who looked at what has **no answer here**, and `FR-SEC-004` asks for one |
| **Append-only at the database role level** | A target. The shipped schema has no role separation, and the comment in `db/schema/sqlite.sql` saying the application role gets `INSERT` and `SELECT` describes an intention |
| **Retention is unbounded** | Ten-year retention, monthly partitioning and partition-level WORM are targets. Nothing expires today and nothing is partitioned |
| **Justification is required** | For overrides, exceptions, break-glass, alias moves, revocations, decommissioning and tier overrides — enforced where each act lives |

### 4.6 Backing it up, and the one ordering that matters

Two stores hold the record and they must be backed up **together**, in this
order, because they are deliberately not the same medium:

1. **The database** — `data/sqlite/maya.db`, or the PostgreSQL cluster. The
   chain itself lives here.
2. **The anchors** — `data/worm/` by default, wherever `WORMWriter` is pointed.
   Heads copied out of the database so that a rewritten chain can be caught.

The hazard is asymmetric and it is worth stating plainly, because an operator
meeting it for the first time will be meeting it during a restore:

> **Restore a database older than its anchors and the instance is permanently,
> correctly, unclearably in disagreement with itself.** The anchors record a
> head at sequence *n*; the restored chain has fewer nodes than that, or
> different ones. `verify_against_anchors` reports a disagreement and will keep
> reporting it, because a write-once store is write-once — there is no operation
> that removes an anchor, and adding one would defeat the control.

This is the anchoring working exactly as designed. It is what makes the check
worth anything against somebody holding the database, and it is the reason the
two must be snapshotted as a pair rather than on separate schedules.

| Situation | What happens | What to do |
|---|---|---|
| Both restored from the same moment | Chain and anchors agree | Nothing |
| Database restored **older** than the anchors | Permanent, unclearable disagreement on `/admin/evidence` | Restore the anchor root from the same moment; if it is genuinely lost, the honest answer is a **new** anchor root and a recorded note that verification before that date rests on the chain alone |
| Anchors restored older than the database | Fewer anchors to check against; the ones present still hold | Nothing, but the gap is real and should be recorded |
| Anchor root lost entirely | `verify_against_anchors` reports the chain as self-certified | Start a new root. Do not attempt to reconstruct one from the database — an anchor derived from the thing it checks proves nothing |

The artifact store (`data/artifacts/`), attachments and the Delta root carry
content addressed by digest and referenced from the database, so a database
restored ahead of them will name bytes that are not there. They belong in the
same snapshot for the same reason, though the failure is loud rather than
permanent.

---

## 5. Versioned gates

A gate that cannot be changed without a release is a gate people work around; a gate that *can* be
changed without one is a gate that can be **weakened** without one, which is worse. `core/policy/`
makes the first possible without making the second silent.

A rule is a **predicate over a closed vocabulary of facts** — comparison, membership, boolean
connectives, `any` and `all` over a generator, six other functions, and no loops, assignment,
function definitions, attribute access or subscripting. That restriction is what makes a rule
something a reviewer can reason about rather than something they have to run. A fact the gate does
not publish is refused **when the rule is written**, because a rule that failed at the moment of a
governance decision would have failed at the worst possible time.

Four gates, each publishing its own facts: `version:approve` (12), `alias:move` (9), `model:mutate`
(5), `warrant:resolve` (8). **There is no `warn` verdict** — a gate that warns is a gate that is not
a gate.

- **A policy ships with its own cases and cannot be published until they pass**, and **at least one
  must be a case it refuses**: a policy nobody has shown to refuse anything is a policy nobody has
  shown to be a gate.
- **Weakening is allowed and never quiet.** On publication the register replays the *outgoing*
  version's cases against the incoming rule and reports every verdict that flipped, bucketed as
  `loosened` or `tightened`, into the evidence node and the log. A change that loosens a gate becomes
  something somebody decided rather than something somebody discovered.
- **Authoring and publishing are separate permissions**, and cases are re-run at publish time rather
  than trusted from the draft.
- **An instance that publishes nothing runs exactly what it ran before**: the built-in rules are the
  default for every gate, expressed in the same language.

And the honest boundary, stated rather than implied: **policy tightens; the code's invariants are the
floor.** A rule runs *in addition to* the checks written in the registry, never instead of them.
Loosening a gate still costs a release — deliberately, because replacing an invariant with a line of
configuration means a typo can weaken the platform and the failure looks like a successful
deployment.

---

## 6. Documents somebody filed

The other half of documentation: the papers people wrote, as against the ones MAYA compiled.

Stored under the **SHA-256 of their bytes**, so the same file is stored once and cannot be edited in
place — changing a byte changes the digest, which is the whole mechanism. They are **re-hashed on the
way out**, and a mismatch raises rather than serves: *"the stored bytes for sha256:… no longer hash
to that digest — the store has been tampered with or has corrupted; do not use this document and
raise an incident."* What an approver accepted is what a reader fetches, **checked rather than
assumed**.

Filed against the **version** they describe rather than the model, because a development document
describes the coefficients it printed and not their replacement; model-level filing exists and has to
be asked for. **Review is segregated twice** — by role grant, and again in the register, so the
person who filed a document cannot accept it even if their role would let them — and that check
precedes the accept/reject branch, so it applies to a rejection too. Rejection requires a reason and
the rejected document stays on file, because the papers that did not pass are the ones a supervisor
asks about. Supersession names what it replaces, so *"which MDD was in force in March"* is
answerable.

Each attachment records whether its bytes are text the platform can genuinely read. **Six media types
qualify** — `text/plain`, `text/markdown`, `text/csv`, `text/html`, `application/json`,
`application/xml` — and PDF and Word are not among them. They are served faithfully and reported as
**not machine-readable**, because that is what they are. There is no extraction pipeline and no
retrieval over document content: the register is *shaped* to support machine review of filed
documents, and that review is **not built**. Saying which is the difference between a roadmap and a
claim.

---

## 7. The platform's own machine assistance

MAYA can ask a language model, and governs its own use on the terms in
[13 — AI in the Platform](13-ai-in-the-platform.md), with the criterion in
[00 §12a](00-mathematical-foundations.md). Three properties belong here because they are security
properties rather than governance ones:

| Control | Implementation | Where it runs |
|---|---|---|
| **What may be cited is fixed before the model is asked** | The evidence is gathered from the register, capped, and named in the prompt. A provider cannot introduce a fact — only a *candidate* fact, which survives exactly as far as its citation does | Code (`core/assist/drafting.py`) |
| **Ungrounded claims are removed, not flagged** | A claim citing nothing or citing something that does not resolve never reaches the output. It is kept separately, which is a more useful artifact than an annotated draft: it is the list of places the model was making things up | Code (`core/assist/grounding.py`) |
| **Nothing a machine produced is evidence until a person attests it**, and never the person who asked | `self_attestation` is a refusal, not a convention | Code (`core/assist/generations.py`) |
| **No AI capability holds a governance credential** | Today this holds because the four `assist:*` permissions are disjoint from every governance permission, and no principal is created for a capability. It is **not** enforced by a check that would fail if somebody added one | Code, weakly — see [13 §7](13-ai-in-the-platform.md) |
| **No remote model is reachable** | Three remote providers **refuse by name**; one deterministic mock works. Egress, confidentiality, reproducibility and cost are named as the four questions a deployment must answer before wiring a real one | Code |

---

## 8. The threat model

Read after the controls, deliberately. The last column is what remains once the controls in the
middle column are taken at exactly their stated strength.

| # | Threat | Controls | What remains |
|---|---|---|---|
| **T1** | **Malicious model artifact** — pickle RCE, poisoned weights, a backdoored `.pth` | Closed format list with pickle absent entirely; content addressing; `executes_on_load` recorded and surfaced; sandboxed load for the artifact-backed runtimes (§3) | **The sandbox is not a boundary against a hostile artifact** (§3.3). No opcode scanning, no malware scan, no signature verification, no SBOM attestation |
| **T2** | **Evidence tampering** — altering a validation result or approval after the fact | A linear `seq`/`prev_hash` chain over the derivation DAG; verification **re-derives** each node's content hash from its own fields (§4.1) | No external anchoring, no WORM copy, no append-only database role. Self-consistency of a chain an attacker controls proves less than it appears to |
| **T3** | **Unauthorised model execution** — an unapproved model, or an approved one for an unapproved purpose | Warrant entitlements bound to approved uses; fail-closed resolution; a blocking finding refuses resolution | Use reconciliation — approved use against actual use — is **not built** |
| **T4** | **Model exfiltration** — bulk download of proprietary models | Artifact reads require a permission and a scope | **Reads are not audited** (§4.5). No rate limit, no quota, no anomaly detection, no watermarking |
| **T5** | **Insider tier manipulation** — lowering a tier to escape controls | Tiering is derived and its derivation is stored; overrides require justification and elevated authority | Independent reassessment at validation is procedural |
| **T6** | **Feature poisoning** — corrupting upstream data to shift model behaviour | Data-quality assertions; drift and skew monitors; source lineage in the provenance graph | Anomaly alerting on sources is not built |
| **T7** | **Prompt injection through inventory metadata** — instructions placed in a model description, a feature definition or a vendor document, which the platform's own drafting assistant then reads | The prompt is assembled from evidence nodes, each labelled with its id, and the model is told it may cite only those; a fabricated citation is dropped before a reader sees it (§7). This surface does **not** exist for an ordinary enterprise chatbot | Structural instruction/data separation is by prompt construction, not by a parser. No injection detector (`FR-AI-017` is partly met) |
| **T8** | **Evidence poisoning by an assistant** — machine-created evidence supporting a machine-made claim | Agents may **propose**; only humans and instrumented systems create evidence. A generation is `drafted` until a person other than the requester attests it | Trust is a column on the node and is propagated by the trust semiring; nothing sets it below 1.0 for AI output today |
| **T9** | **Automation bias** — a usually-correct queue trains reviewers to approve without looking | Edit distance recorded on attestation and its **trend** reported; a deterministic sample of accepted generations pulled for independent review regardless of how good they look (`FR-AI-015`, `FR-AI-016`) | Nothing acts on a falling edit distance automatically; somebody has to ask |
| **T10** | **Supply-chain compromise of MAYA itself** | Dependencies pinned; every front-end asset vendored, so there is no CDN in the trust boundary | SBOM per release, signed images, SLSA L3, SCA in CI and reproducible builds are **not built** |
| **T11** | **Cross-entity data leakage** in a multi-entity deployment | Scope filtering in the application, on legal entity and domain, applied to listings as well as detail reads, and to **pages** as well as API calls (§2.4, [08 §1](08-ui-ux.md)) | **Single-layer.** Postgres RLS is designed and not built |
| **T12** | **Session forgery** | The cookie is signed, `SameSite=Strict`, and CSRF-guarded (§1) | The signing secret and the `Secure` flag are both **deployment obligations**, and four published secrets are accepted with a warning rather than refused |
| **T13** | **Denial of the warrant plane** | Warrant resolution is independent of the control plane; descriptors carry a grace window | Independent scaling, regional failover and static fallback are deployment topology, not code |
| **T14** | **Compromised signing key** | Descriptors are signed; the SDK pins a key set | KMS/HSM custody, 90-day rotation with overlapping validity and emergency revocation are **deployment obligations** |
| **T15** | **Malicious or careless policy change** | Policies are versioned, ship with their own cases including a refusing one, and every flipped verdict is reported as `loosened` or `tightened` (§5); publishing is a separate permission from authoring | Author ≠ publisher is enforced by permission, not by actor (§2.5) |

---

## 9. Generative and agentic AI, as a parallel track

SR 26-2 places GenAI and agentic AI **outside** MRM scope while stating that the firm's own risk
management should determine appropriate governance. MAYA's answer is a **parallel track**, so these
systems are governed without pretending they are statistical models.

> **Status.** One half of this is built and one is not. The **two admissible operating modes** and the
> **oracle-or-grounding gate** are enforced in `core/assist/` for the platform's own capabilities
> (§7, [13](13-ai-in-the-platform.md)). The boundary gates, the harm matrix, the evaluation battery
> and the agentic controls below are **design targets** — there is no GenAI boundary determination,
> no autonomy mode on a model version, no eval harness, no guardrail artifact and no tool manifest
> anywhere in the code.

### 9.1 Boundary determination (design)

| Gate | Condition |
|---|---|
| **G1 — No autonomous authority** | The system does not make a substantive decision on its own |
| **G2 — Institutional anchoring** | Output is grounded in approved models, policies or documents — not open-ended generation |
| **G3 — Bounded function** | It performs a defined support task, not general-purpose reasoning |
| **G4 — Feasible oversight** | A human can meaningfully review the output in the time available |

Only two operating modes pass — **collaborative assistance** (a human is engaged throughout) and
**human-approved automation** (the system processes autonomously, a human approves before the output
has effect). Those two, and only those two, are the vocabulary `core/assist/common.py` accepts today.
Anything failing a gate is redesigned or refused, and that decision and its rationale are recorded.

### 9.2 Risk assignment (design)

**Decision proximity × consumer harm potential**, setting evaluation rigour, monitoring frequency and
human-review requirements.

| | Harm: none | inconvenience | financial | rights / credit |
|---|---|---|---|---|
| **Far from decision** | Low | Low | Moderate | High |
| **Informs decision** | Low | Moderate | High | Critical |
| **Drafts the decision** | Moderate | High | Critical | Critical |
| **Executes the decision** | *not permitted without redesign* | | | |

Adverse-action explanation drafting sits at **Critical**: it is consumer-facing, credit-related, and
drafts the text that becomes a legal notice under Reg B.

### 9.3 Evaluation, monitoring and agentic additions (design)

Groundedness, citation accuracy, hallucination rate, adverse-action fidelity, toxicity, PII leakage,
jailbreak attempts and successes, refusal rate, **human edit distance** and human override rate, plus
cost and latency. Every prompt, corpus, base-model, tool or guardrail change re-runs a frozen eval
set before deployment, and a base-model version changing silently under a vendor endpoint is treated
as a change event, detected by canary fingerprinting.

For systems that take actions rather than produce text: a **tool manifest** as a versioned artifact
naming every callable, its blast radius and whether it is reversible; every tool call logged with
arguments and result; irreversible actions requiring human approval regardless of tier; hard caps on
iterations, tokens and cost enforced at the gateway; and a blast-radius assessment at registration.

**Of that list, exactly one thing is built**: human edit distance, recorded on attestation, with its
*trend* reported (§7).

---

## 10. Fair lending and consumer protection

Applies to models in ECOA/Reg B, FCRA, UDAAP or EU AI Act Annex III scope.

> **Status, stated first because the gap here is the largest in this document.** Two columns exist on
> a feature — `protected_basis` and `proxy_risk` — and **nothing consults either of them.** There is
> no policy rule that refuses a protected-basis feature binding into a credit model's contract, and
> the test catalogue holds eight tests, all statistical: MAE, RMSE, Brier, expected-versus-actual,
> AUC, Gini, KS, PSI. **No fairness test exists.** Everything below is a design target, and an
> earlier draft of this section stated the first row as "enforced by the policy engine, not by
> review", which was false.

| Control | Design | Today |
|---|---|---|
| **Protected-basis exclusion** | A feature flagged `protected_basis` cannot bind into a credit model's contract, refused by the policy engine rather than by review | The flag is recorded and never read |
| **Proxy testing** | `proxy_risk: high` requires documented business necessity and proxy-discrimination testing before use | The flag is recorded and never read |
| **Disparate impact testing** | Adverse Impact Ratio, statistical parity difference and equal-opportunity difference, computed at validation **and** continuously in monitoring, per protected class | Not built |
| **Less discriminatory alternative search** | A documented, evidenced search retained as evidence — the CFPB's stated expectation | Not built |
| **Reason-code dictionary** | A versioned artifact mapping each feature to a borrower-readable reason and a Reg B category, with legal sign-off recorded | Not built |
| **Reason-code fidelity testing** | For each generated reason: specific to this applicant, causal in the model, accurate against the application data, free of disparate-impact concern | Not built |
| **Explanation availability** | The contract's guarantee `G` includes *"explanation available for every score"*; a model that cannot explain cannot be approved for adverse-action use | The guarantee vocabulary exists; this member of it is not enforced |
| **Record retention** | Application, features, score, reasons and model version retained per FCRA/Reg B | Retention is unbounded and unpartitioned (§4.5) |

---

## 11. Framework mapping

Each row names the MAYA component that would operate the control, so a control-testing exercise
becomes a query rather than a project. **No control library ships** — this is the map, not an
artifact in the code.

| Control | SR 26-2 | SS1/23 | EU AI Act | NIST AI RMF | ISO 42001 | Operated by | Built |
|---|---|---|---|---|---|---|---|
| Complete model inventory | VI | 1.2 | Art. 11 | MAP-1 | 6.1 | Registry | Registry ✓, discovery ✗ |
| Documented scope determination | II | 1.1 | Art. 6 | MAP-1.1 | 6.1.2 | Regime engine | ✓ |
| Risk tiering with rationale | III | 1.3 | Art. 9 | MAP-1.5 | 6.1.2 | Tiering engine | ✓ |
| Named individual accountability | VI | 2.x | Art. 14 | GOVERN-2 | 5.3 | Ownership model | ✓ |
| Segregation of duties | VI | 2.x | — | GOVERN-3 | 5.3 | §2.5, from the chain | ✓ |
| Development standards & testing | IV | 3.1–3.3 | Art. 9, 15 | MEASURE-2 | 8.3 | Lifecycle + test catalogue | ✓ |
| Data governance & representativeness | — | 3.2 | **Art. 10** | MAP-2 | 8.2 | Feature platform | ✓ |
| Independent validation | V | 4.x | Art. 9 | MEASURE-3 | 9.2 | Validation register | Register ✓, workbench ✗ |
| Effective challenge evidenced | III, V | 4.x | — | MEASURE-3.3 | 9.2 | Evidence graph | ✓ |
| Ongoing monitoring | V | 4.x | **Art. 72** | MEASURE-4 | 9.1 | Monitoring | ✓ |
| Automatic event logging | — | — | **Art. 12, 19** | MEASURE-1 | 8.4 | Telemetry + the chain | Governance acts ✓, reads ✗ |
| Technical documentation | VI | 4.x | **Art. 11 / Annex IV** | GOVERN-4 | 7.5 | Document compiler | ✓ |
| Human oversight design | V | 3.x | **Art. 14** | GOVERN-3.2 | 8.1 | Autonomy modes (§9.1) | For machine assistance only |
| Change management | — | 3.3(c) | Art. 43 | MANAGE-4 | 8.1 | Lifecycle + alias gates | ✓ |
| Post-model adjustment control | — | **Principle 5** | — | MANAGE-2 | 8.1 | Overlay register | ✓ |
| Vendor model oversight | **VII** | 2.6 | Art. 25 | GOVERN-6 | 8.1 | `descriptor_only` + reference artifacts | Partial |
| Issue and remediation tracking | VI | 1.2(c)(iii) | Art. 73 | MANAGE-4 | 10.1 | Findings register | ✓ |
| Aggregate risk assessment | **III** | 1.2(b) | — | MAP-5 | 6.1 | Typed composition | Edges ✓, aggregation `L-14` ✗ |
| Access control & audit trail | — | — | Art. 12 | GOVERN-1 | 8.4 | §2, §4 | Writes ✓, reads ✗ |
| Model supply-chain integrity | — | — | Art. 15 | MANAGE-3 | 8.1 | Content-addressed store | Bytes ✓, signing and AI-BOM ✗ |

---

## 12. Business continuity

Every row here is a **deployment obligation**. None of it is code, and a reader should treat the
whole section as a design target rather than as a control that operates.

| Scenario | Response |
|---|---|
| Control plane unavailable | The warrant plane continues; already-authorised production scoring is unaffected; governance changes queue |
| Warrant plane unavailable in a region | Regional failover; the SDK's grace window covers the switch |
| Total outage beyond the grace window | Documented manual break-glass: pre-authorised static descriptors for a named set of Tier 1 production models, held in escrow, dual-controlled, with mandatory post-hoc review of every use |
| Data loss | Postgres PITR; Delta time travel; object-store versioning and cross-region replication; quarterly restore tests with evidence |
| Ransomware | Immutable backups with object lock; a WORM evidence tier; offline chain-head anchors (which §4.3 records as not built) |
| Loss of a key person | No single-person dependency: ownership is a role with a deputy, and policy and configuration are code in git |

**Recovery objectives:** control plane RTO 4 h / RPO 15 min; warrant plane RTO 15 min / RPO 0; the
evidence chain RPO 0 under synchronous replication.

---

## 13. Traceability

| Section | Satisfies |
|---|---|
| §1 Ambient authority | [08 §6](08-ui-ux.md); [11 — Adversarial Review](11-adversarial-review.md), the front-end section |
| §2.3 Roles | `FR-SEC-002` |
| §2.4 Scope | `FR-SEC-002`; finding H-5 in [11](11-adversarial-review.md) |
| §2.5 Segregation | `FR-SEC-004`; [15 §7](15-featuresets-and-parameters.md) |
| §3 Artifacts and sandbox | [ADR-009](adr/ADR-009-no-untrusted-deserialisation.md); `NFR-SEC-002`; `P7` |
| §4 The record | `FR-SEC-004`; `L-18`; finding C-4 in [11](11-adversarial-review.md) |
| §5 Gates | [14 §6](14-detailed-design.md) |
| §7, §9 | [13 — AI in the Platform](13-ai-in-the-platform.md); [00 §12a](00-mathematical-foundations.md); `FR-AI-015`–`FR-AI-017` |
| Build status | [12 §0](12-implementation-plan.md#0-build-status) is authoritative |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
