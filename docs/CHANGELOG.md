# Changelog

## Unreleased

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
  - nine runbooks (`docs/runbooks/`);
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
