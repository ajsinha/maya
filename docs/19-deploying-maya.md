# 19 — Deploying MAYA

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [04 — Architecture](04-architecture.md) and
[09 — Security and compliance](09-security-compliance.md).

---

## 1. What this document is for

`docs/10` used to file deployment under *somebody's operational work, not
code*. That was true of the **operating** and false of the **artefacts**: a firm
cannot deploy a governance register safely from a README, and every unstated
default in a chart is a deployment that runs and is quietly wrong.

So the artefacts exist — `Dockerfile`, `deploy/compose.yaml`, `deploy/helm` — and
this document is about the decisions inside them. It is short on YAML and long on
why, because the YAML is in the repository and the reasoning is not repeated
anywhere else.

**What it is not** is a runbook for a particular bank's platform. Multi-region
topology, backup and restore, TLS termination and secret management are somebody
else's components, and §6 says what MAYA needs from each rather than how to build
it.

## 2. The five things that must be true, in order

A deployment that gets the first wrong does not benefit from getting the rest
right. `GET /health/ready` and `GET /api/v1/row-level-security` answer the first
four; the fifth needs a person.

| | What | If it is wrong |
|---|---|---|
| **1** | The **signing key and session secret** are not the published defaults | Anybody with a copy of this repository can forge a warrant, or a signed-in session as `admin` with no password. A published **session secret on an address other machines can reach now refuses to start**, because a warning on the one instance where it matters is the weakest control shape there is; bound to `127.0.0.1` it still starts and still warns, since a workstation is not the deployment this protects. The **warrant signing key** is still a warning only |
| **2** | The application connects as a role that **owns nothing and is not a superuser** | Every row-level policy is decorative and nothing about the configuration looks wrong |
| **3** | The **WORM anchor store is durable** and, with several replicas, shared | An anchor written to a container filesystem disappears on restart. Worse than no anchoring, because the readiness report said the chain was anchored |
| **4** | **Something runs the governance batch** | An instance where nothing runs it is indistinguishable from an estate with nothing outstanding. Attestation lapses, silent monitors, overdue findings and anchoring are all recorded by it, and none raises itself |
| **5** | Somebody **reads the start-up warnings** | Every one of the above says so at boot. They scroll past once — which is the argument that turned the session secret from a warning into a refusal, and the argument for doing the same to anything else on this list that can name the condition under which it is dangerous |

## 3. The image

Two stages, and the split is about attack surface rather than size. The build
stage compiles a wheel and writes a cache; the runtime stage copies the installed
tree and nothing else, so a compiler, a package-index client and a pip cache full
of URLs never reach the image that runs in production.

**It runs as uid 10001.** A numeric uid, because a Kubernetes `runAsUser` has to
name a number and an image that only has a name forces the deployment to guess.

**No build-cache mount.** It makes a local build faster and a CI build
non-reproducible, and an image that cannot be rebuilt byte-for-byte from a tag
has an SBOM describing something nobody can reproduce.

**The data directory is created and chowned before the `VOLUME` declaration**,
and this is not a stylistic ordering. Docker seeds a fresh volume from whatever
is at the mount point in the image, **ownership included** — so a directory that
does not exist yet produces a volume owned by root that uid 10001 cannot write.
Found by running the image rather than reading it: the container started, failed
at `mkdir /app/data/artifacts`, and the only symptom was a health check that
never went green.

**The health check asks about the evidence chain**, not whether the port answers.
A process serving a broken chain is one that should not take traffic.

## 4. The database, and the two roles

The schema is applied by an **owner**. The application connects as somebody else
and owns nothing.

This is not tidiness. `FORCE ROW LEVEL SECURITY` binds the table owner, and a
table's owner is whoever ran the DDL — so a deployment where the application owns
its own tables has policies that bind nobody.

One level below that, and the trap worth stating loudest:

> **A superuser bypasses row-level security entirely, `FORCE` or not.** Verified
> against a real PostgreSQL 16 rather than reasoned about. A deployment can apply
> every policy perfectly, connect as `postgres`, and have nothing — with a
> configuration that looks entirely correct.

`GET /api/v1/row-level-security` therefore reports the connecting role's
exemption *above* the table flags, because that fact decides whether any of the
rest of it is true. It also reports `enabled` and `forced` separately:
enabled-without-forced is the configuration that looks right in a screenshot.

And the backstop is narrower than the control, by design. Only `legal_entity` is
policed; `domain` is a scope dimension the application still applies everywhere
and no policy covers. The columns derive from `core.authz.scope.DIMENSIONS`, so
adding a scope dimension puts it in one of two published lists rather than
silently in neither.

**There are no migrations**, and that is a position rather than a gap. One typed
schema, `--repair-schema` to add what a deployed database lacks, and a drift
check on `/admin/evidence` — because the DDL is applied with `CREATE TABLE IF NOT
EXISTS`, so an existing table is skipped and a column added in a later release is
never created. An instance can otherwise run for weeks on a schema that does not
match its own release and fail inside a workflow.

## 5. The chart, and what it refuses to render

A chart that renders is a chart somebody installs, so the place to refuse a
configuration that cannot be safe is **before it reaches a cluster**.

| Refused | Because |
|---|---|
| No `secrets.databaseUrlSecret` | a literal ends up in `helm get values`, in the release history, and in whatever ships the values file into the cluster |
| No `secrets.sessionSecret` | the cookie is signed with the published default, and anybody with the repository can forge a session as any user |
| No `secrets.warrantSigningKeySecret` | per-audience keys are *derived* from this root, so a published root is every engine's key at once |
| `ReadWriteOnce` with `replicaCount > 1` | one pod holds the anchor volume and the others cannot anchor. Anchoring then happens intermittently on one pod while the readiness report says the chain is anchored |
| `worm.enabled: false` | tamper evidence then rests on the chain agreeing with itself, which a rewritten chain does perfectly |

A chart shipping a working signing key ships a key everybody has, and **a
deployment that runs is one nobody goes back and fixes**. The failure to render
is the control.

Two further decisions worth naming:

**The chart does not deploy a database.** A register whose evidence chain lives
in a StatefulSet the chart also owns is one where a `helm uninstall` can destroy
the record. The anchor PVC carries `helm.sh/resource-policy: keep` for the same
reason — a chart that deleted it on uninstall would make an accident
indistinguishable from a cover-up.

**Liveness and readiness ask different questions.** Readiness points at
`/health/ready`, which verifies the chain. Liveness points at `/health/live`,
which does not — pointing liveness at the chain check restarts every pod in the
fleet the moment verification fails, turning one detected problem into an outage
and destroying the instance somebody could have read to find out what happened.

## 6. The batch, and why it is a CronJob

The in-process scheduler loop is **off** in the chart, and a `CronJob` calls
`POST /api/v1/scheduler/run` instead.

With several replicas an in-process loop runs the batch N times a tick. That is
not merely wasteful: it is **N notifications for one lapse**, and the fourth is
the one somebody mutes. `concurrencyPolicy: Forbid` stops two runs overlapping,
and the job exits non-zero on a refusal — a batch that reports success while
refusing is how an estate goes a month with nothing running.

## 7. What MAYA needs from components it does not own

| | What MAYA needs | What it does about the absence |
|---|---|---|
| **Object storage / WORM** | a durable, ideally immutable, mount for the anchor store | ships a filesystem implementation, reports it as *separation of medium rather than enforcement* |
| **An RFC 3161 authority** | a URL and a certificate trust root | reports itself as **arguing from its own clock** until one is wired, rather than showing a tick |
| **A secret manager** | secret *references*, which the chart takes | refuses to render without them |
| **TLS termination** | a proxy or an ingress | serves HTTP and sets the security headers it can; HSTS is the proxy's |
| **Backup** | a Postgres PITR and a copy of `data/` | `/admin/evidence` reports schema drift; nothing here tests a restore, and §8 says so |
| **A compute cluster** | for an estate-wide monitoring sweep | publishes the statistics contract and computes the metric itself — [18 §3.9](18-the-registers-edges.md) |

## 8. What has been measured, and what has not

`tools/spikes/` turned four of the NFR table's targets into results. Every
figure carries the machine it ran on, because a latency figure without conditions
is a number somebody will quote in a different context.

| | Measured | The finding, which is not the number |
|---|---|---|
| Warrant resolution | warm p99 ≈ 12 ms against a 50 ms target | warm and cold are **close**, because there is no descriptor cache — so the cold target is the only one of the two that means anything |
| Point-in-time join | ≈ 240,000 picks/second | extrapolates to ≈ 50 TB of process memory at the target size. **The target is not reachable in one process at any speed**, which is why the answer is a distributed assembly rather than a faster loop |
| Sandbox escape | 4 of 6 attempts stopped; 2 declared open | it found a **defect**: `RLIMIT_CPU` is cumulative and was set to the warrant's budget flat, so a `max_seconds: 2` warrant killed the artifact before it ran — indistinguishable from a runaway model, and a *tighter* budget made it more likely |
| The register at estate size | list p95 **148 ms** at 10,000 models and **441 ms** at 50,000, against a 500 ms target; detail **1.9 ms**, flat | the paged reads are **sublinear in practice** — a fixed per-request cost dominates below about forty thousand models — and the **fold over the whole estate was 33.4 s at 50,000** because it asked nine questions of every model. Now **7.6 s**, by serving those nine questions from one index per table rather than by rewriting any of them ([10 §2.4a](10-roadmap.md)) |

`docs/spikes/estate.json` holds that fourth result with its conditions, including
which reads were **not** taken and why.

**A correction, kept rather than tidied away.** The first write-up of this said
the fold *did not return inside thirty minutes*. It returned in **33.4 seconds**,
and it now returns in **7.6** — the figure in the table above. The spike that
reported otherwise was sharing a machine with other work, and the number it
produced was about the machine. That is the clearest available illustration of
the rule under this table: a number measured carelessly is worse than a target
honestly labelled, because the target does not claim to be evidence.

**Three things it says about itself, which matter more than the milliseconds.**
The estate was **seeded as rows**, so the write path and evidence-chain
verification at that size are untouched — 6,000 chain nodes in
`tests/test_scale.py` is still the largest this repository has observed. It ran
**single-process on SQLite** with no concurrency, so every figure is a floor. And
the machine was **shared**: the 50,000 figures reproduced across runs to within
1%, while the 10,000 ones varied between 148 and 259 ms for the same read, which
is why the growth ratio is reported with that caveat rather than as a clean
slope.

**Still targets, and therefore still unobserved:** throughput, the fold over an
estate of 50,000, restore time, PostgreSQL, and anything about a multi-node
deployment. A number this platform has never observed is a number it should not
print as though it had.

## 9. Verifying a deployment

In order, and each answers a question the previous one cannot.

```
GET  /health/live                     is the process up
GET  /health/ready                    does the evidence chain verify
GET  /api/v1/row-level-security       is the database backstop real, and is
                                      the connecting role exempt from it
GET  /api/v1/evidence/timestamps      is anything attesting to the chain's age
GET  /admin/evidence                  does the schema match the release
GET  /admin/scheduler                 did the batch actually arrive
GET  /admin/perimeter                 what is this relying on somebody else for
```

Then read the start-up log. Every warning in it is a sentence somebody wrote
because the failure it describes is silent.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
