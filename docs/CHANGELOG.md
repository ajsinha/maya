# Changelog

## 1.0.0 — 2026-09-26

The first release: model governance on top of the 0.3.0 spine — findings, materiality,
periodic review, monitoring, champion and challenger, fairness and explainability
evidence, regulatory inventory exports, LLM application governance and connectors.

**LLM applications, governed like models**

- `/llm` (SDK `llm`, `/api/v1/llm/*`). An application's **version** seals the provider,
  model, system prompt, prompt template (`{placeholders}`), parameters and guardrails in one
  definition hash; editing is allowed only in draft, so an approved definition never
  changes and any change is a new version.
- **Evaluation sets** are the holdout: named cases — the template's variables and the checks
  the answer must pass — hashed as content. Checks are deterministic (`contains`,
  `not_contains`, `equals`, `regex`, `max_chars`, `json` with required keys); no model grades
  another model, because a judgement MAYA cannot reproduce is not evidence it can seal.
- **Guardrails** run on every answer: blocked terms, a length cap, and personal data
  (e-mail addresses, Luhn-valid card numbers, phone numbers). A violation fails the case.
- **Runs** are *recorded* (answers produced anywhere, submitted for scoring) or *live*
  (MAYA calls the provider; Anthropic, through the assistant's client and its API-key
  settings).
- **Approval on evidence**: submission needs a run on the version's own definition, against
  the evaluation set as it now stands, meeting the version's pass rate (all cases by
  default) with no guardrail violation; approval is by a model manager or administrator
  who neither owns the application nor submitted it, and retires the previous approved
  version. Applications appear in the regulatory inventory export, with their evaluation
  evidence and without the model-only fields (tier, findings, reviews) invented.

**Tiering questionnaires, and loose ends**

- **A firm's own materiality questionnaire.** `config/tiering.yaml`
  (`governance.tiering_questionnaire`) holds the questions, the answers each allows and what
  each answer scores, 1 to 3. The owner answers them on the model's governance page (SDK
  `governance.set_profile(answers=...)`); under `rule: max` the highest answer joins the
  measured drivers, under `rule: points` the answers are summed and placed by the file's
  thresholds. An answer the questionnaire does not offer is refused, and a model is shown
  as *undeclared* until every question is answered. Shipped with four questions — automation,
  customer impact, reporting, complexity — to be tuned to policy.
- **Expected shortfall and Cornish–Fisher templates** now compute the normal quantile with
  `N^{-1}` instead of taking it as a constant.
- **The template library is a package**, one module per domain, each well under the
  file-size gate.

**Connectors: MLflow, SageMaker, OpenLineage, Snowflake, Databricks**

- **MLflow import** (`/integrations`, SDK `integrations.import_mlflow` / `fetch_mlflow`). The
  model's `MLmodel` file — uploaded, or fetched for a registered version from the server in
  `integrations.mlflow.tracking_uri` and nowhere else — becomes a black-box draft whose input
  contract is the signature, with flavours, run and model id sealed into the IR as
  provenance. A model logged without a signature, or with a tensor signature, is refused
  rather than guessed at.
- **SageMaker import** from a `DescribeModelPackage` document: image, model data, framework
  and approval status as provenance. SageMaker records no inputs, so they are named by the
  caller or in a `maya:inputs` customer metadata property.
- **OpenLineage export**: every lineage edge, grouped by what it produces, as a `RunEvent`
  (one job per produced object, its sources as inputs) — downloaded, or posted to
  `integrations.openlineage.url` with a bearer token from the environment. Administrators.
- **Snowflake and Databricks SQL sources** through their SQLAlchemy dialects, installed
  where used. Neither has a driver-level read-only session, so a Snowflake URL must name a
  role (which should be read-only), statements time out after five minutes on Snowflake,
  and the SELECT-only check applies as for every source.
- Honest scope: these are tested against the documents each system publishes and a recorded
  HTTP exchange, not yet against a live MLflow server, AWS account or warehouse.

**Fairness and explainability evidence**

- A training warrant's *Fairness & drivers* tab (SDK `evidence`,
  `/api/v1/warrants/training/{id}/evidence`) computes, on the escrowed holdout:
  - **segment metrics** by a column you name — RMSE, MAE, bias and mean prediction per
    segment, the worst-to-best MAE ratio, the widest bias gap, and a flag on any segment
    whose MAE is more than a quarter above the overall figure. Segments below a minimum
    size (20 rows by default) are reported as suppressed, with no figures, since a mean
    over a handful of holdout rows discloses those rows;
  - **permutation importance** — the rise in RMSE when each input is shuffled, seeded and
    repeated. It needs only predictions, so a black box is measured through the sandbox.
- A run reads the holdout, so it counts as one holdout attempt; the result is stored on the
  warrant with the parameters used, and only aggregates are kept.

**Champion and challenger**

- `/governance/challenges` (SDK `challenges`, `/api/v1/challenges`). Two training warrants
  drawn on the same escrowed holdout — equal holdout hashes, so the same rows in the same
  order — are both scored, each attempt counted on its warrant, and compared row by row:
  the metric difference (RMSE or MAE), a paired bootstrap 95% interval with a fixed seed,
  and the share of rows the challenger wins. The verdict is *challenger better* only when
  the whole interval is below zero.
- Warrants on different holdouts, or scoring different targets, are refused rather than
  compared. The decision — promote or retain, with a rationale — is recorded by someone
  who does not own the challenger, and is evidence for a change rather than the change:
  the champion's live warrants are untouched.

**The model inventory, exported for SR 11-7 and SS1/23**

- `/governance` → *Export the model inventory* (SDK `governance.inventory`,
  `GET /governance/inventory?format=xlsx|csv|json&framework=sr11-7|ss1-23|maya`). One row
  per model: purpose, use, type, vendor, owner, tier with its basis and any override,
  exposure, status and approval, the evidence that the implementation computes the model,
  last review and its outcome, next review due, open, overdue and accepted findings, live
  warrants and environments, executions, monitoring status and restrictions on use.
- Built from the records MAYA already keeps, so it cannot drift from them. The two layouts
  are labellings of the same rows; SS1/23's adds the basis of tiering and restrictions on
  use. Each file says it is an aligned layout, not a submission template, and counts the
  models the exporting user could not read rather than leaving them out silently. Every
  export is audited.

**Black boxes are scored blind, in the sandbox**

- A declared black box (a vendor model, or any opaque one) used to be refused at holdout
  scoring: MAYA cannot evaluate a model it cannot read. It can run one it has validated,
  though, so a black box whose code artifact passed the validation ladder is now scored by
  running that artifact in the sandbox on the escrowed holdout's input columns — never the
  target, with no network and no view of storage. MAYA computes the metrics from the
  predictions; the caller sees the metrics and never a row.
- The score records what was run: `scored_in: sandbox`, the sandbox tier and the
  artifact's hash, on the attempt and in the warrant's custody chain. A black box with no
  validated artifact is refused by name, and one that reads the target as an input is
  refused rather than handed the answer.

**Ongoing monitoring dashboards**

- **`/monitoring`** (SDK `monitoring`, `GET /monitoring`, `GET /monitoring/warrants/{id}`)
  reads the executions reported under each sealed warrant as series. The overview grades
  every warrant you can read: *breach* (suspended, or a covenant breached in the last 7
  days), *watch* (a PSI between 0.10 and the covenant, an input null rate at least double
  its median, or a live warrant silent for 30 days) or *ok*.
- A warrant's dashboard draws volume per day and, per input and output, the PSI against
  the covenant's baseline, the null rate and the mean, with the covenant bounds as dashed
  lines and breaches marked on the time axis. The charts are server-drawn SVG in the theme's
  colours: no charting library, nothing for the content security policy to allow.
- Nothing here writes; it is a reading of evidence the covenants already judged, so it
  cannot disagree with them. Offline, unattested runs report nothing and are not graded.

**Model governance: findings, materiality and periodic review**

- **The findings register.** `/governance` (SDK `governance`, `/api/v1/governance/*`). A
  finding has a severity, an owner (the model's, by default), a due date (30, 90, 180 or 365
  days by severity) and a history of every move. Whoever marks it remediated does not
  close it — an independent reviewer confirms the fix or sends it back — and accepting the
  risk instead needs a written reason and is not the model owner's call.
- **Materiality tiers, derived.** Tier 1 (most material) to 3, from the model's use and
  exposure as its owner declares them and from what MAYA measures: live execution warrants,
  executions, and whether it is a black box (one tier higher). An override needs a reason,
  and one that makes the model less material than the evidence says is flagged.
- **Periodic review with teeth.** The tier sets the interval (1, 2 or 3 years, or per
  model). An hourly sweep suspends every live execution warrant of a model whose review is
  overdue, through the same suspension a covenant breach uses; recording a review — by
  someone other than the owner — lifts exactly those suspensions and no others.

**Derivations keep their clock; the formula IR gets the normal quantile**

- **Six algebra operators no longer drop the knowledge clock.** Projection, composition,
  coalescing, aggregation, resampling and case selection built their output from the index
  and attributes alone, so a derived feature arrived without `_knowledge_time` and read as if
  it had always been known. Each now carries the latest knowledge time of the input rows it
  was built from, row by row — the same rule feature-set assembly and pivot already used.
- **`ncdfinv`, the standard normal quantile.** `N^{-1}(p)`, `\Phi^{-1}(p)`, `ncdfinv(p)` and
  `probit(p)` all parse to it; read as a power the superscript would have made it `1/N(p)`,
  which parses, computes and is wrong. It evaluates, generates code, renders and round-trips
  as LaTeX, lifts from Python (`norm.ppf`) and from Excel (`NORM.S.INV`, `NORMSINV`,
  `NORM.INV`). The Basel IRB and parametric VaR templates now compute the quantile instead of
  taking it as an input.

**Models: the translation step on its own (§8.1, §16.2)**

- **The compute-kernel wizard.** Somebody who writes their mathematics in LaTeX had to type
  it into the model designer and find out what MAYA made of it only once a version existed
  to hold it. `/models/kernel` (SDK `models.kernel`, `POST /formula/kernel`) is that
  translation on its own: mathematics in, and back come the LaTeX rendered from the tree
  MAYA parsed rather than from the text that was typed — so a misreading is visible — the
  typed IR a version would store with its hash, the inputs with the role each was given, and
  Python that computes it. It creates nothing and reads nothing, and one button carries the
  formula and the roles into the designer when the translation is right. A formula MAYA
  cannot read is refused here, with the reason, which is the point: the alternative is
  finding out at `models.create`.
- **One function, wherever MAYA generates code.** The reference implementation on a model's
  Code tab was a module — `import math`, `import numpy as np`, `_erfc`, `_ncdf`, `_npdf`,
  then `predict` — six names at module scope, three of which will collide with something in
  whatever codebase the file is pasted into. `to_python` now emits what
  `to_python_kernel` emits: one function, its imports and helpers nested inside it. The
  composite generator does the same, each member becoming a function of `predict` rather
  than a sibling beside it. The three callers are unchanged, because the one name any of
  them asks for is still `predict`.
- **Joint parameter constraints, which bounds cannot express (§8.4).** Bounds are per
  parameter and some conditions are not: a GARCH model is stationary only if
  `alpha + beta < 1`, and each coefficient can sit anywhere in [0, 1] while the pair forecast
  a conditional variance with no finite long-run mean. A model version may now declare
  constraints over its own parameters — an expression, a comparison, a bound, and a reason
  that has to be written down, because the reason is the only thing a modeller sees when the
  constraint fires. They are checked where §8.4 says parameters are checked, on upload, and
  a constraint that reads a feature is refused: it has to hold before any data is seen. Black
  boxes and composites may declare them too, which for a GARCH model — a black box precisely
  because its variance is a state carried between rows — is the one thing about it a reviewer
  can still check arithmetically.

**The front door, the canvas and the preview (§16.1, §16.3, §17.1)**

- **`/` is the landing page when nobody is signed in** and the dashboard when somebody is,
  and signing out returns to it rather than to the sign-in form. A visitor handed a password
  box has been asked "who are you" before being told why they would want an account here, and
  somebody who has just left is not halfway through arriving. The page draws the chain MAYA
  keeps — source, bitemporal feature, sealed pin, typed formula, warrant — and every arrow in
  it is an object MAYA stores, so the illustration and the argument are the same drawing.
- **A lineage node carries its own name.** The canvas drew 30×22px shapes with the label
  floating underneath, so `fit()` zoomed near 3× and magnified every 10px label into 30px of
  overlapping text. Nodes are now boxes sized to their text, the zoom is capped at 1:1, and
  the kind is carried by colour rather than by a shape too small to hold a word; only an
  operator keeps its diamond. A node is named by name and version rather than by a whole ref,
  a pin says that it is a pin, and a parameter set's forty-character hash is cut to the ten
  that identify it here. A fan of edges that all say `parameterized_by` writes that word
  once, and the status line says how many repeats went unnamed, because nothing is hidden
  silently.
- **A preview that shows a command is a preview with a hole in it.** The specification pane
  recognised `\section` only at the start of a paragraph, so an ordinary LaTeX document
  showed the reader `\section{Assumptions}` as text, and so did every other construct the
  renderer did not know. Headings are now found wherever they stand; lists, display-maths
  environments, verbatim blocks and the transparent wrappers render; a `tabular` names itself
  as skipped and says the PDF build carries it; escaped characters are set aside before the
  maths scanner runs, so `\$5` cannot open an equation; and nothing backslash-shaped reaches
  the reader at all. The same pass fixed the markdown that had leaked into the case studies'
  LaTeX specifications — five bolds and eleven italics the PDF build would have printed
  verbatim.
- **An asset a browser cached yesterday no longer lays out today's page.** Every stylesheet
  and script MAYA serves carries a token computed once at import from the newest of them, so
  a deployment invalidates the cache without a page load having to stat the tree. Vendored
  libraries keep their plain URLs: they change when their version does, which is already in
  the path.
- **The brand block carries three lines** — what MAYA is called, what it is, and what it
  undertakes to do — and the footer is one centred line with the copyright, read from
  `maya/core/version.py`, because a year written into a template is a copy that will rot.

**Case studies**

- **Three more worked studies**: 06 IFRS 9 expected credit loss, 10 factor models from CAPM
  to Fama–French, and 11 the Nelson–Siegel yield curve — nine of the numbered fifty now run
  end to end. Study 08's data and declarations are written; its steps are not.
- **A demonstration no longer opens on a change-password form.** An administrator-set
  password must be changed at first sign-in (§12), which is the right rule and is staying, so
  the harness walks each seeded account through the step a person would and the password it
  prints is the one that works.

**Documents**

- **The third deck is a capabilities deck, not a concepts one.**
  `docs/MAYA-Capabilities.pptx` (37 slides) replaces `MAYA-Concepts-and-Formalism.pptx`: the
  product told as what a person does with it, then the IFRS 9 study carried all the way
  through with its findings and refusals, and a closing section on what MAYA does not do. A
  deck commenting on the paper's theory was a second place to keep the theory current; it now
  lives in the paper alone. The other two are `MAYA-Executive-Briefing.pptx` (18) and
  `MAYA-System-Design.pptx` (41).
- **Every document read against the code**, sentence by sentence, and the places it had
  fallen behind marked rather than quietly corrected: specification revision 2.6 (the
  capability matrix, the seam register, the front door, the kernel wizard, the CLI's
  administrative commands, the package layout that was never built), the gate ladder's real
  membership in the plan, and the runbooks for quotas and orphaned fragments, both of which
  still said a control was unbuilt that has been enforced since the audit's batch 1.

**Limits on what one caller can ask (§13.2, §21.1, §24.4)**

- **Uploads are bounded.** A request body past `api.limits.max_body_bytes` (256 MB) is
  refused, by its header or as it streams in.
- **Archives from outside are bounded.** A reproducibility bundle, an estate and an
  `.xlsx` are all zip files; each is now checked before it is read — entry count,
  expanded size, expansion ratio, and no entry that would be written outside it. A
  member is read no further than its entry table declares. The verifier a bundle carries
  checks the same before extracting.
- **Rate, concurrency and time.** A token bucket per caller (the API key id, else the
  session, else the peer) answers `429` with `Retry-After`; above
  `api.limits.max_concurrent` in flight a process answers `503` rather than queueing; a
  request past `api.limits.timeout_seconds` is answered `504`. All three count per
  process, so several web processes multiply them.

**The review screen and the catalog (§10.3, §10.6, §16.2, §16.4)**

- **Review is a review again.** `/workflow/review/{type}/{id}` shows a semantic diff against
  the last approved version — section by section, in words, not JSON — the dependents and
  who owns them, the separation-of-duties level in force and whether it stops *you*, and
  which approvals are outstanding and who can give them. A dependent the reviewer may not
  read is counted, never named. The screen showed a policy from the wrong scope; it now
  shows the one that governs the namespace.
- **Catalog facets**: type, namespace, owner, status, tag and freshness, across features,
  feature sets and models, with cursor paging. Totals stay exact under row-level
  authorization — the facets that are columns narrow the query, and the two that are not
  (tag, freshness) narrow an id set counted in the database.
- **Before you pin**: a preview reports rows, columns, the fill report, the quality contract
  run under the pin's own as-of, a storage estimate, what the namespace holds against its
  quota, and every blocker. The pin control arms only on a clean preview, and disarms when a
  field changes.
- **Disabled controls say why.** A control the caller cannot use carries the rule that would
  refuse it — `can()`'s own words, so the screen cannot promise what the server refuses —
  and offers to request access.
- **Access requests (§11.5)**: request, decide, withdraw, list, with a time-boxed grant on
  approval and both sides audited.
- **`tracking` bindings do something.** A behavioural bump marks every tracking dependant for
  re-approval and tells its owner; an additive one marks nobody; a pinned dependant is
  untouched. Deprecating a member warns the sets that hold it, and a revoked member warrant
  flags the composite execution warrants that embed it.
- **Subscriptions work**: follow a feature, set or model and hear when a new version is
  approved or a pin is sealed. A follower who loses read access goes quiet without losing
  the subscription.
- **The missing notices**: a covenant breach and 30-days-to-expiry reach the model manager,
  and a failed quality check reaches the owner. Each sweep is idempotent.

**Observability and operations (§15, §20, §22)**

- **The metrics §20 lists exist** — 42 described families, up from 16, including job wait,
  resolution rows and bytes, Delta file counts and small-file ratio, database pool and slow
  queries, cache hits and misses, pins and bytes per namespace, and queue depth by type.
  A phrase-to-series table fails if a metric is renamed or a claim dropped.
- **SLO recording rules and alerts** ship in `config/prometheus/maya-slo.rules.yml`, every
  alert linking a runbook that must exist and naming a metric MAYA actually exports.
- **Integrity verification runs on a schedule**, deduplicated per window.
- **A restore drill the estate remembers**: `maya admin record-drill` and `maya admin drills`,
  which exits non-zero when a drill is overdue, and a metric that ages.
- **Job fairness**: the queue ranks by each owner's running share, with a per-user
  concurrency cap, and refuses new work with a wait estimate rather than growing without
  bound.
- **A worker process outside the web process**: `python run_maya_web.py --worker` binds no
  port and runs the queue only.
- **Typed configuration**: 148 settings declared with type, default and validator, two of them
  families — `seams.<name>` and `auth.sso.group_role_map.<group>` — whose members are matched
  by prefix because their names are the site's to choose. An unknown
  key in a file refuses startup and names the nearest match; one on the command line is
  reported, because the command line belongs to whatever launched the process.
- **Six more runbooks** — orphaned partitions, Delta small files, database failover, a
  suspected sandbox escape, quota exhaustion, the default password — so all nine §20
  procedures ship. Every command was run against a throwaway estate, and the ones that could
  not be are marked.
- **Logs carry request id, trace id, actor and object ref**, and a module's level can be
  changed at runtime in the process that receives the call.

**Warrants, bundles and parameters**

- **The reproducibility bundle carries what §18.4 asks for.** It omitted the uploaded code
  artifact, the feature-set definition and the member pins behind it; all three are in,
  each hashed in the manifest. Member *data* is not copied twice: the training frame is
  that data, and each member pin's identity and manifest are enough to say which bytes it
  came from.
- **The PSI covenant (§29.5) exists.** `input_psi` watches an attribute's distribution
  against the population the warrant was drawn on — the baseline is taken from the training
  data at creation, so it is fixed and auditable — and a breach suspends the warrant like
  any other. Empty bins are smoothed, so one missing value cannot suspend a warrant, and a
  covenant with no training warrant to take a baseline from is refused with that reason.
- **A stale feature is warned about before the pin, not only after.** The quality contract
  still refuses, but a request now answers "the newest rows arrived 9 days ago; this
  feature's freshness contract allows 2", and a feature's footprint says the same.
- **Fitted parameters can arrive as a file (§9.3):** `.npz` (read with pickle disabled),
  a pickle — **scanned first and refused if it would import or construct anything**, with
  the offending opcode named — or an ONNX graph's initializers, when `onnx` is installed.
  `maya warrant upload-params` takes `--format`, or reads it from the file name, plus
  `--data-checksum`, `--notes` and `--member-alias`.

**Extension points, and the notification channels §25 lists**

- §25 promises that "every axis of variation is a registered plugin implementing a declared
  protocol, discovered by entry point, configured by name". MAYA had the variation — seven
  source drivers, eleven resolution rules, six export formats, three auth providers, five
  calendars, its own search index — and no registry, so none of it was discoverable and a
  third party could add nothing without editing MAYA. `maya/plugins.py` is that registry:
  ten points, each with the protocol §25 declares and what MAYA actually ships at it,
  discovered from `maya.<point>` entry points, listed on an admin **Extensions** page.
  What it lists is what exists; nothing is listed to fill the table.
- **An installed plugin is not a loaded plugin.** An entry-point plugin runs in MAYA's own
  process with MAYA's privileges — it can read the database and the signing key — so §25's
  "untrusted plugins run under the sandbox rules" cannot be true of it. MAYA loads a
  third-party plugin only when `plugins.allow` names it, and a refusal is recorded with
  that reason rather than swallowed, so an operator can see why their plugin is absent. A
  plugin that fails to import is reported too, and does not stop MAYA.
- **Email, Slack and Teams channels**, beside the in-app inbox and signed webhooks that
  already existed. Each is off until configured — a platform that mails people by default
  mails the wrong people the first time it starts — and a channel that cannot send says so
  instead of dropping the notice; the inbox copy is always written first. The webhook URLs
  are secrets, so they live in the environment or the local overlay, which the no-secrets
  gate enforces.

**The fragment collector (§29.3), and a lake that can let go**

- `maya_delta` had no delete, so an unreferenced fragment could only be reclaimed by
  rewriting a whole table. Both backends now remove a partition's files in **one commit** —
  a Delta remove, not a rewrite, so time travel still answers and a vacuum past the
  retention window is what frees the disk.
- On top of that, the collector §29.3 asks for, and what makes it *provably* safe is the
  order of its checks: a fragment is a candidate only when **no pin row of any state** names
  it; the whole pass is refused if any pin was created while it was reading, because a pin
  records its fragments before it seals; and what remains is removed reversibly.
- It runs when an administrator asks — never on a schedule — and a dry run is the default,
  so the list can be read before it goes. `maya admin collect-fragments [--apply]`, or the
  admin Retention page.
- The storage report no longer says orphans are never collected, because now they can be.
- The retention, drill and log-level endpoints moved to their own API router: the admin
  router had reached the gate's limit on public names, and these are the operator's own
  surface anyway.

**Feature-set composition (§6.7, §6.3, §6.2)**

- **A feature set may hold another feature set as a member**, one level deep: a desk panel
  can be built on the firm panel without copying its definition. The nested set's own read
  rule, conditions and approval state govern it, exactly as if it had been opened directly.
- **Fork**: a new set that starts from this one's definition and lets go — as against
  `extends`, which follows the parent's corrections. A fork records where it came from, in
  its definition and in the lineage, which is also what stops the near-copy guard refusing
  it.
- **Version diff**, member by member and policy by policy, on a page with the two versions
  selectable.
- **A boolean filter over the set's own attributes** (`filters.where`), refused at
  resolution if it names something the set does not carry.
- **A point-in-time universe from another feature**: membership is taken on *each row's own
  date*, so a backtest sees the index as it was, not as it is. The universe feature is
  resolved bitemporally like everything else, so "as of 2019" means what was known then.
- **Per-member alignment**: the set declares a mode once and a member may override it — a
  member that arrives late can join as-of while the rest join exactly.

**The assistant drafts, and a manifest a person can read (§29.8, §9.2)**

- **A feature definition drafted from a description and a sample file.** Column names and
  types give the index, the schema and the knowledge-time column; the description gives the
  resolution rules where it says how gaps behave; the sample's nulls give the quality
  checks. The draft is validated exactly as a hand-written definition is, says where each
  part came from, and names what it had to guess. Nothing is created: it comes back for a
  person to read, edit and submit. Only structure is read from the sample — never a row —
  which is what makes the Claude provider's version safe to send.
- **Drafts for the specification sections nobody has written**, from what MAYA can see of
  the model: its inputs, outputs, parameters and formula. Each draft names what it cannot
  know rather than inventing it — no fabricated validation numbers — and a section that has
  been written is left alone.
- **The execution manifest as a PDF** (§9.2 asked for "PDF and JSON"; only the JSON
  existed): what can be run, on what inputs, by whom, until when, with the limits and
  covenants, rendered from the sealed manifest and marked when it came from the draft
  renderer rather than a real LaTeX build.

**The SDK's object shape and its cache (§18.2.4, §18.2.5)**

- The SDK spoke only in dictionaries. It now also speaks the shape the specification
  writes: `client.feature(ref).version(4).pin("q1", as_of=date)` returns a job handle,
  `job.wait(progress=print)` reports as it goes, `pin.to_arrow()` / `.to_pandas()` /
  `.to_polars()` / `.to_file()` give the rows, and `with warrant.data() as ds:` yields the
  frame with `ds.X`, `ds.y` and the checksum a parameter upload must quote.
- Every record **is** still a dict, so nothing that consumed the old return values changed;
  attribute access is added on top, one level at a time, and an unknown field raises an
  error naming the fields that are there.
- **A local cache, for sealed pins only.** A pin is immutable and carries a content hash, so
  a cached copy can be proved identical: the key is that hash and the shape asked for, every
  hit is checked against the bytes' own digest, and a corrupted or edited file is a miss
  rather than an answer. Definitions and live resolutions are never cached, because they
  can change under you. `~/.maya/cache` by default, bounded, least-recently-used eviction,
  `MAYA_CACHE=0` to turn it off.

**Shadow replay: a declared threshold, honest coverage, a budget, and the approver (§29.2)**

- **The model declares what is material.** A model version carries its own
  `shadow_materiality`, and the replay measures against that in preference to its namespace's
  figure and to the configured default — a rate in basis points, a price and a probability are
  material at three different numbers, and only the model knows which it produces. Every
  report entry names the threshold *and* where it came from (`model`, `namespace`, `default`),
  because a report that quietly used the wrong one reads as "nothing moved". A new draft
  inherits the declaration; zero is refused.
- **The sampling owns up to its coverage.** Each entry now states how many rows matched on
  both sides as well as how many were replayed, and the share that covers; the report totals
  the same across warrants; and the basis says plainly that the sample is the most recent rows
  of each index, which is a recency bias and not a random draw.
- **Replaying is gated by a per-namespace budget.** A namespace spends at most
  `workspaces.shadow.budget_rows` row comparisons in a rolling day, or its own
  `shadow_budget_rows`, charged against what the audit log says earlier replays spent — the one
  ledger nothing can quietly adjust. The check is before the work and the charge after it, so
  the first warrant of a day always runs however small the ceiling. A warrant whose namespace
  has spent its budget is reported unreplayed with the figures, never counted as unmoved.
- **The numbers reach the approver.** A version submitted from a workspace carries its shadow
  replay onto the review screen: the summary, the per-model shift, the threshold used and the
  rows it was measured on, beside the list of dependents. §29.2 asked the review screen to read
  "this change moves 3 of 11 dependent models"; it does.
- The governed-change tutorial said an execution warrant in the impact list comes back
  `warrant not found`. It has been replayed for some time; the guide now says so.

**Conditional reads and resumable downloads (§18.1, §18.2.3, §18.2.5)**

- **A read MAYA has already answered costs a round trip and not a body.** Catalog listings,
  the catalog browse and the feature, feature-set and model definition reads carry an
  `ETag` — the hash of the bytes served, because a read is more than its rows and a version
  column would let a changed grant or a changed owner slip past a 304 — and answer
  `If-None-Match` with 304 and nothing else. The SDK holds the last body against that
  validator and re-serves it only when the server says 304, so a scheduler that polls a
  listing every minute pays for the question and not the answer. This is not a cached
  definition in the sense §18.2.1 forbids: nothing is ever handed back that MAYA has not
  just re-affirmed.
- **An edit written against a definition that has since moved is refused.** A draft write on
  a feature, a feature set or a model honours `If-Match`, and the SDK sends the `ETag` of the
  read the edit was written against without being asked. A mismatch raises the same
  `ConflictError` two racing edits already raise. Only an open draft is guarded this way: a
  pin, a sealed warrant, a parameter set and an audit row are appended once and then
  immutable, so there is no overwrite for a precondition to prevent.
- **A download of any size survives a dropped connection.** `/feature-data` and
  `/featureset-data` advertise `Accept-Ranges`, serve a `Range` as 206 with `Content-Range`,
  answer 416 for a range past the end, and honour `If-Range` so a resume onto bytes that
  have moved becomes a fresh whole download instead of two halves of two objects. The SDK
  streams to disk, so an interrupted transfer leaves a part worth keeping, and the sealed-pin
  cache continues from that part with the validator it was fetched under. A resumed download
  ends at exactly the checksum a one-shot download ends at, and a part that fails it is
  dropped rather than cached — a Parquet download that will not read is now a failure and no
  longer excused as "some other shape".

**Retention (§7.3), which was not built at all**

- **Cold pins are named.** MAYA records when a pin was last read (the first read always,
  then at most hourly) and reports which have gone unread past
  `retention.cold_after_days`, with what they hold. Naming is all it does: moving bytes to
  an infrequent-access class needs the object-store backend of §25, and the report says so
  rather than implying a tier exists.
- **A retired pin can be archived**: its rows, manifest and fragment list packed into one
  compressed bundle, stored as a blob, recorded on the pin. Reading it back re-hashes the
  rows against what was sealed, so an archive that rotted is caught rather than served.
  Archiving twice is one archive. The pin's fragments are shared with other pins and are
  **not** deleted — collecting those is the §29.3 collector, still unbuilt.
- `maya admin cold-pins`, `admin archive-pin`, `admin restore-pin`, and an admin
  **Retention** page carrying all of it beside the restore-drill register and per-module
  log levels.
- An object's **owner can now answer an access request for their own object**, as §11.1's
  "owners can always tighten or widen an individual object" says. Before, the role ceiling
  meant only an administrator could — for everyone's objects. An owner still cannot hand
  out an `admin` grant.
- A revoked member warrant flags the composite execution warrants that embed it **at once**
  rather than within the hour.
- The pin preview now quotes the quota's own figure — deduplicated stored bytes — instead
  of summing logical sizes, so the number in the preview is the number the refusal uses.

**Quotas, and what a pin will cost (§7.3)**

- A namespace's `quota_bytes` was stored and read by nothing. It is now checked when a pin
  is requested — against an estimate, before a worker spends minutes — and again against
  the writer's real figure before any byte is stored, so a queue of pins cannot slip past
  a quota while none of them is written yet. A pin refused that late is left `failed` with
  the quota named.
- What is charged is **stored** bytes, counted once per content-addressed fragment: a
  re-pin of unchanged data adds nothing, where charging logical size would bill the same
  bytes again.
- `maya/services/quota.py` reports a namespace's usage, and `features.footprint(ref)`
  answers what a feature holds and what one more pin would store, saying where the figure
  came from (its own last sealed pin, or its declared schema).

**The CLI's missing command groups (§18.3)**

- `maya admin user-list | user-create | user-roles`, `role-list | role-create`,
  `namespace-list | namespace-create` (with `--quota-bytes`), `grant-list | grant-add`,
  and `policy-list | policy-show | policy-import | policy-activate`.
- `maya featureset build <ns/name> <definition.json|yaml> [--submit]`.
- `maya model validate <ref>` — how the formula conforms and what the workflow still
  wants; a draft with no artifact to test reports that rather than failing.
- `maya warrant create <ns/name> --model --featureset --target|--spec`.

**The feature-set algebra (§6.8), which was only `extend` and `project`**

- A feature set can now be **an operation over other feature sets**: it carries a
  `derivation` block (`{operator, operands, options}`) instead of `members`.
  - `union`, `intersect`, `difference`, `join` (under §6.2's alignment modes), `project`,
    `pivot`, `unpivot` and `sample` are the feature algebra's own executors applied to
    whole sets, so a set operation and the equivalent feature operation cannot drift apart.
    `pivot`, `unpivot` and `sample` are new to the algebra, and so are available to
    features too.
  - `override` re-resolves one operand with its policy, filters, grid or alignment
    replaced — applied where resolution happens, not patched onto the result.
  - `sample` is deterministic: a date range, a universe, or a seeded fraction chosen by
    hashing each row's index, so the same spec keeps the same rows on any machine.
  - A derived set pins only over operands that are themselves pinned, and says which are
    not. There is no cascade: pinning another team's feature set is their decision.
  - The near-copy check counts a derived set by its operator and operands, so two
    different derivations are two sets and two identical ones are still refused.

**Governance defects**

- **An approval's `when` condition is read, not guessed.** `prod`, `env == 'prod'`,
  `env != 'prod'` and the `nonprod` forms are understood; the specification's own
  `env == 'prod'` was not, and silently made the approval unconditional. An unreadable
  form is refused when the policy is saved; a stored one asks for the approval rather
  than dropping it.
- **A policy whose approver could never approve is refused.** It saved, and then nothing
  it governed could leave review. MAYA's own shipped policy had this shape: it asks the
  model owner to sign off in a production namespace, and §11's role matrix gave that role
  no approval capability, so **a production namespace could approve no execution warrant
  at all**. The matrix now gives the model owner approval on models and execution
  warrants, and the `standard` namespace preset staffs the owner and techops.
- **A composite is governed as one.** Its structure is checked while it is still a draft
  (cycles — including a reference to an older version of itself — and nesting depth);
  writing one requires read on every member; each member gets a seed derived from the
  warrant's seed; and a training warrant seals only when every trainable member has an
  approved parameter set, whether fitted per member or in one combined set.
- **The escrowed holdout is escrowed.** Its content hash and row count are fixed when the
  warrant is drawn. Scoring recomputes the partition and refuses to answer if it no
  longer hashes the same, because a score against data that moved is not comparable with
  the scores before it.
- **`namespace_read` and `public_read` now differ.** They behaved identically. A
  namespace's people are its owner, anyone granted on it, and holders of the roles its
  preset staffs; `public_read` is anyone signed in.
- **The `delta` source is a source, not a peephole.** It read any path on the server,
  ignored the version asked for, and stamped every row as known *now* — so a resolution
  as of a past instant returned rows that did not exist then. It now reads only inside
  `sources.delta.roots` (the lake root by default), honours an explicit `version` or the
  last commit at or before `as_of_known`, and takes each row's knowledge time from its
  own column or the commit that wrote it.

**Access and governance**

- **The review queue, the SLA aging list and the break-glass report name only what
  the caller may read.** They named every in-review object and forced transition in
  every namespace to anyone signed in. The system's own escalation sweep still sees
  everything. An administrator sees every break-glass event.
- **The lineage graph leaves out what the caller may not read.** `GET /lineage` named
  objects across namespaces. An unreadable object is now absent, counted in a new
  `hidden` field. An operation, parameter set or execution shows only next to
  something readable. A root the caller may not read is `404`. The workspace impact
  view still shows everything downstream of a staged change, which is its purpose.
- **A training warrant keeps what its feature-set reference meant.** A bare name was
  stored as typed and re-resolved on every download and holdout score, so "latest"
  moved under an approved warrant. A bare name is now stored as the version it
  resolved to, and a pin series without a date as the date of the pin found. The
  custody record keeps the reference as given.
- **A model that declares parameters runs only under a named, approved parameter
  set.** An execution warrant drawn from a training warrant without a parameter set
  was approved as "non-trainable", and so was a black box that declares parameters.
  Both are now refused at creation and at the approval check. A parameter set must
  also come from the warrant it is drawn from.
- **Defects found by exercising the runbooks:**
  - An estate load now checks everything before writing anything. It refuses a
    database that holds data, and an estate whose own audit chain does not link.
    It also refuses columns this version does not know, unless `--allow-drop`
    (`import_estate(..., allow_drop=True)`), which names what was dropped.
  - Reinstating a warrant that is not suspended is refused.
  - A custody anchor signed by a key other than this MAYA's is reported.
  - The lake reports its native backend only when that backend's self-check passes.
  - The CLI's `--local` mode runs job workers only, never the webhook dispatcher or
    the scheduler.
  - A disarmed webhook's pending delivery now settles as "webhook is inactive;
    nothing was sent", not "no longer exists".

**Capacity (§24.3)**

- `tools/bench/bench_capacity.py` measures the rest of §24.3, and all four targets pass on
  SQLite ([BENCHMARKS](BENCHMARKS.md#capacity-243)):
  - pin write throughput, 59.7 MB/s (51.4 MB/s on a second run) against 50;
  - 20k feature sets, 10k models and 100k pins, every page p95 under 30 ms;
  - job throughput, 134,962 an hour against 1,000;
  - cold start, 1.26 s against 30 s.
- **Pins get faster to seal:**
  - Sealing verifies a pin by comparing values with what was hashed, instead of
    hashing it twice.
  - Logical-type conversion is vectorised.
  - A pin's fragment files are read in parallel.
  - Rows that all share one layout are hashed from contiguous column slabs.

  Each change is proven equal to the path it replaces.
- **The catalog holds 20k feature sets, 10k models and 100k pins without
  degrading:**
  - A feature's page shows its latest 100 pins and their total, with the rest paged
    at `GET /features/{ns}/{name}/pins` (SDK `features.pins`).
  - List totals under row-level authorization are counted in the database by
    (namespace, owned) group.

**Operations**

- **The restore drill has been performed**, on SQLite and on PostgreSQL 17, and
  recorded in the runbook. It covered backup, restore, disarming, integrity
  verification and anchor verification. This was the first run of the runbook's
  PostgreSQL steps.
- The test suite and the benchmarks remove the storage roots and PostgreSQL databases
  they create. They used to leave them behind until `/tmp` filled.

**Documentation and gates**

- **The gate ladder is complete:** lint, strict typing of `maya/services`, public
  names per module, import cycles, SDK and OpenAPI snapshots, the fallback matrix,
  UI↔SDK parity, protocol literals, browser screenshots, bandit, pip-audit with the
  sandbox tests, and a benchmark regression check. Each rung is proven to catch a
  planted fault. Also new: `maya.testing` and a synthetic market dataset.
- **Added:**
  - 28 architecture decision records (`docs/adr/`);
  - fifteen runbooks (`docs/runbooks/`), the nine §20 asks for among them;
  - the specification audit of 2026-09-19 (`docs/audit/`), with what has been fixed
    since.
- **The research paper and its article are restored and rewritten** against 0.3.0.
  Every claim about the system carries a mark: runs, in part, implemented but
  untested, or not in MAYA.
- **The decks are rebuilt as three:** executive briefing, system design, and concepts
  and formalism. `LICENSE` and `NOTICE` now name the research documents correctly.

## 0.3.0 — 2026-09-19

The SDK is unchanged from 0.2.0 (`CLIENT_VERSION` stays 0.2.0).

- **Single sign-on against a real identity provider.** OIDC and SAML were driven end to
  end against Keycloak 26.4.7, through its own login pages in headless Chrome: sign-in
  with group-mapped roles, SAML signed requests, single logout started by MAYA, and
  logout started by Keycloak. `tests/test_sso_keycloak.py` reruns it when
  `MAYA_TEST_KEYCLOAK_URL` is set. The security guide gives the Keycloak settings that
  worked. SAML back-channel (SOAP) logout is not supported.
- **OIDC logout, both ways.** With `auth.sso.post_logout_redirect_uri`
  (`MAYA_OIDC_POST_LOGOUT_URI`) set and registered with the IdP, signing out of MAYA
  also sends the browser to the issuer's end-session endpoint and back; empty, sign-out
  is local, as before. The IdP can end sessions server to server at
  `POST /api/v1/auth/sso/oidc/backchannel-logout` (SDK `auth.oidc_backchannel_logout`):
  the logout token is checked like an ID token, and must also be fresh, carry the
  logout event, a `sub` or `sid` and a single-use `jti`, and no `nonce`. It ends the
  subject's sessions, only the named one when it carries a `sid`. A token that fails is
  a `400` and is audited. Against Keycloak 26.4, signing out of MAYA ended the Keycloak
  session, and ending a session in Keycloak's admin console ended the MAYA session.
  Keycloak's "sign out all sessions" of a user sent a token for one session only.
- **Feature-set pin materialization** follows the namespace's `materialize_policy`:
  - `always` writes the output at sealing, as before;
  - `on_demand` writes it at the first read;
  - `never` replays it from the member pins on every read.

  Every mode seals the same content hash. A replay is served only if it reproduces that
  hash; otherwise the read fails with `integrity_error`. Integrity verification replays
  unwritten pins.
- **A signed-in session's principal is reused** for `auth.session.principal_cache_seconds`
  (default 2). A sign-out, revocation or access change applies at once in the process
  that made it, and within that time in other web processes. A session still owing a
  second factor is never reused.
- **SC-3 re-measured with that cache.** Three runs on PostgreSQL with 8 web processes
  gave a p95 of 0.34 s, 0.22 s and 0.43 s against a 0.3 s target. It is not met
  reliably, and a dedicated benchmark host to settle it is out of scope by decision.
- **The specification's `.docx` and `.pdf`** are rebuilt from the Markdown at revision
  2.3 by `tools/docs/build_spec.py`, diagrams included.
- **The TSA's signature on a custody timestamp is checked inside MAYA.** Set
  `custody.anchor.tsa_ca_file` (`MAYA_TSA_CA_FILE`) to the authority's CA certificate
  and `openssl ts -verify` checks it when an anchor is made and at every custody
  verification; a token that does not chain to that CA, or answers another head, is
  reported. Set without the file or without `openssl`, MAYA refuses to start. Unset,
  MAYA checks status and imprint only, as before, and names the command to run by
  hand. Tested against a real `openssl` TSA, including the wrong CA and the wrong
  imprint.

**Documentation**

- The README gains *What's shipped*: every delivered capability, where it lives, and
  the tests that prove it. The implementation plan marks each milestone and success
  criterion with what 0.3.0 delivered and what it did not.
- Three things are now stated as **out of scope by the owner's decision**, not as
  pending work: testing the assistant against the live Claude API (its Claude provider
  is verified against a stub only), Windows and macOS (only Linux is exercised, so
  SC-14 is not met), and a dedicated benchmark host (SC-3 stays not met reliably).
- Specification revision 2.3 gains markers for the principal cache (§12) and the
  namespace's `materialize_policy` in D-1 (§26.3), which contradicted the code without
  one.

**Fixed**

- SAML refused Responses that repeat an attribute name, which Keycloak sends by
  default, so every Keycloak SAML sign-in failed.
- The estate import now names a required column the estate cannot fill, instead of
  failing inside the database.

## 0.2.0 — 2026-09-19

Built from specification revision 2.3. The SDK's own version (`CLIENT_VERSION`) is
0.2.0 too; 0.1 clients remain accepted.

**Using MAYA**

- A new shell: top navigation with mega-menu panels, and a card-based help centre with
  four tutorials and thirteen full-reference guides whose examples were run.
- Spreadsheet import lifts an Excel formula graph into the IR. The lift is checked cell
  by cell against the workbook's cached results, and against LibreOffice Calc.
- A Python source driver: a reviewed producer function, run in the sandbox on each pull.
- The assistant as a recorded challenger on every review. Rules are the default;
  Claude is opt-in.
- The workbench shows the 50 most recently changed drafts. Feature and feature-set
  lists take a `state` filter on the latest version.
- The owner of a scratch namespace pins directly. Before, every scratch pin was refused.

**Security**

- SAML 2.0 sign-in, with signed requests and single logout in both directions. An IdP's
  logout request is accepted only when signed. WebAuthn security keys as a second factor.
- Execution warrants: a copy issued for offline use is labelled `unattested`, on the
  copy and on the warrant.
- Defects found by test hardening were fixed, including code execution in
  server-side bundle verification, and review comments and history open to any
  signed-in user rather than to those who may read the object.

**Evidence**

- Bundles re-execute composite models of closed-form members. `maya.sdk.offline`
  evaluates them from the signed member IRs.
- SDK record/replay for both clients; `maya.sdk.offline(bundle)`; real LaTeX builds with
  Tectonic.

**Operations and performance**

- `server.workers`: several web processes on one node over PostgreSQL. On Linux each
  has its own `SO_REUSEPORT` socket. The setting is refused over SQLite.
- Catalog lists check access and load versions in bulk; page latency fell 10–60×.
  Search loads its hits in bulk.
- The health check caches its expensive parts: the audit-chain walk, the default
  password check and the schema digest.
- maya_delta compaction and vacuum on both backends, run daily over every lake table.
- The estate export reads the database as it is, so it works across a schema change.
- Measured: SC-5, SC-4 and 100k-object search pass. SC-3 is close but not met.
  See `docs/BENCHMARKS.md`.
- The suite runs on SQLite and on PostgreSQL 16, 17 and 18.

**Fixed**

- A feature pin whose resolution or lake write failed unexpectedly stayed
  "materializing" for ever. It now ends `failed`.
- Shadow replay could not find execution warrants.
- The event `type` filter matched anywhere; it is now a prefix.
- Review aging ignored namespace policies.
- The CLI refused `--key=value` setting overrides.
- Removed unused configuration keys: `auth.session.token_ttl_minutes` and
  `featureset.pin.materialize`. `server.workers`, also unused before, now does
  something (above). `health.audit_verify_seconds` is new.
- A stray pasted sentence was removed from a configuration comment.

## 0.1.0 — 2026-09-19

First end-to-end build from specification revision 2.1. The version authority is
`maya/core/version.py`; this file is the narrative.

- The spine, working end to end through the UI, API, SDK and CLI: features → feature
  sets → models → training warrants → parameter sets → execution warrants → evidence
  bundles.
- Bitemporal features and content-addressed pins shared as fragments (§29.1, §29.3).
- `maya_delta`, with a native (delta-rs) backend and a pure-Python backend; each reads the other's tables.
- SQLite and PostgreSQL from two generated schema files, switched by `db.dialect`; no
  migration framework; estate export → recreate → import.
- Workflow policy as data, edited in the UI, governed, projected to YAML.
- Gate ladder in `tools/ci/`.

See the README's *Status* and *Not yet* sections for the precise boundary.
